# This file is part of dax_apdb_deploy.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
from collections import defaultdict
from datetime import datetime
from operator import attrgetter
from typing import Any

from ansible import constants as C
from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import option_helpers
from ansible.utils.display import Display
from rich.console import Console
from rich.table import Column, Table

from ..pssh import Pssh
from .utils import find_docker_folder, locate_basedir, make_host_map, make_hosts

_log_format = "%(levelname)s: %(name)s - %(message)s"

logging.basicConfig(level=logging.WARNING, format=_log_format)


@dataclasses.dataclass(slots=True)
class SSTableInfo:
    """Collection of information about a single SSTable."""

    sstable: str
    first_token: int = 0
    last_token: int = 0
    min_timestamp: float = 0.0
    max_timestamp: float = 0.0
    sstable_level: int = 0
    compression_ratio: float = 0.0
    total_columns_set: int = 0
    total_rows: int = 0
    token_space_coverage: float = 0.0
    estimated_cardinality: int = 0

    @property
    def token_range(self) -> int:
        return self.last_token - self.first_token + 1


class SSTableInfoCLI(Pssh, CLI):
    """CLI for running parallel-ssh on remote hosts.

    Parameters
    ----------
    *args
        Positional parameters, passed to the base class.
    **kwargs
        Keyword parameters, passed to the base class.
    """

    display = Display()

    name = "sstable-info"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        # Indexed by host and table name.
        self._sstable_data: dict[str, dict[str, SSTableInfo]] = defaultdict(dict)
        # Indexed by host name.
        self._current_sstable: dict[str, SSTableInfo] = {}

    def init_parser(self, desc: str | None = None, epilog: str | None = None) -> None:
        super().init_parser(desc=desc or "Dump information about sstables.", epilog=epilog)

        option_helpers.add_inventory_options(self.parser)
        option_helpers.add_vault_options(self.parser)
        option_helpers.add_basedir_options(self.parser)

        self.parser.add_argument(
            "-u",
            "--user",
            default=C.DEFAULT_REMOTE_USER,
            dest="remote_user",
            help="Connect as this user (default=%(default)s)",
        )
        self.parser.add_argument(
            "--json",
            default=False,
            action="store_true",
            help="Print results of execution in json line format.",
        )
        self.parser.add_argument(
            "-s",
            "--sort",
            default="sstable",
            choices=[
                "sstable",
                "first_token",
                "min_timestamp",
                "total_rows",
                "token_space_coverage",
                "token_range",
            ],
            metavar="FIELD",
            help="Sort field, one of [%(choices)s] (default=%(default)s).",
        )
        self.parser.add_argument("keyspace", help="Keyspace name.")
        self.parser.add_argument("table", help="Table name.")

    def post_process_args(self, options: argparse.Namespace) -> argparse.Namespace:
        """Post process command line arguments.

        Parameters
        ----------
        options : `argparse.Namespace`
            Parsed command line arguments.

        Returns
        -------
        options : `argparse.Namespace`
            Validated and possibly updated command line arguments.
        """
        options = super().post_process_args(options)

        # We need --playbook-dir if we are not in the correct directory
        # already. Try to guess where it is.
        if not options.basedir:
            options.basedir = locate_basedir()
        return options

    def run(self) -> int:
        try:
            rc = self._run()
            return rc
        except SystemExit:
            raise
        except BaseException:
            logging.exception("Execution failed.")
            return 1

    def _run(self) -> int:
        super().run()

        # Initialize needed objects
        loader, inventory, vm = self._play_prereqs()
        cliargs = context.CLIARGS

        # Find addresses for all hosts.
        hosts = make_hosts(inventory, cliargs["subset"])
        if not hosts:
            self.display.warning("No hosts matched, nothing to do")
            return 0

        # just listing hosts?
        if cliargs["listhosts"]:
            self.display.display(f"  hosts ({len(hosts)}):")
            for host in hosts:
                self.display.display(f"    {host}")
            return 0

        host_to_address = make_host_map(hosts, vm)
        deploy_docker_folder = find_docker_folder(hosts, vm, loader)

        keyspace = cliargs["keyspace"]
        table = cliargs["table"]
        data_dir = f"/var/lib/cassandra/data/{keyspace}/"
        cmd = f'./cmd bash -c "/opt/cassandra/tools/bin/sstablemetadata {data_dir}/{table}-*/*-Data.db"'
        rc = self.execute(
            hosts=host_to_address,
            cmd=cmd,
            user=cliargs.get("remote_user"),
            cd_folder=deploy_docker_folder,
            serial=False,
            follow=True,
        )

        return rc

    def process_output(self, host: str, stdout: list[str], stderr: list[str]) -> None:
        for line in stdout:
            if line.startswith("SSTable: "):
                name = line.split("/")[-1]
                sstable_info = SSTableInfo(sstable=name)
                self._sstable_data[host][name] = sstable_info
                self._current_sstable[host] = sstable_info
            elif line.startswith("Minimum timestamp:"):
                # Convert microseconds to UNIX time. In Cassandra 4.1 timestamp
                # is printed as
                #    Minimum timestamp: 1780607110899865 (06/04/2026 21:05:10)
                # but in Cassandra 5.0 it is
                #    Minimum timestamp: 07/16/2026 18:14:32 (1784225672933620)
                timestamp = line.split()[-1].lstrip("(").rstrip(")")
                if not timestamp.isdigit():
                    timestamp = line.split()[2]
                self._current_sstable[host].min_timestamp = float(timestamp) / 1e6
            elif line.startswith("Maximum timestamp:"):
                timestamp = line.split()[-1].lstrip("(").rstrip(")")
                if not timestamp.isdigit():
                    timestamp = line.split()[2]
                self._current_sstable[host].max_timestamp = float(timestamp) / 1e6
            elif line.startswith("Compression ratio:"):
                self._current_sstable[host].compression_ratio = float(line.split()[-1])
            elif line.startswith("First token:"):
                self._current_sstable[host].first_token = int(line.split()[-2])
            elif line.startswith("Last token:"):
                self._current_sstable[host].last_token = int(line.split()[-2])
            elif line.startswith("SSTable Level:"):
                self._current_sstable[host].sstable_level = int(line.split()[-1])
            elif line.startswith("totalColumnsSet:"):
                self._current_sstable[host].total_columns_set = int(line.split()[-1])
            elif line.startswith("totalRows:"):
                self._current_sstable[host].total_rows = int(line.split()[-1])
            elif line.startswith("Local token space coverage:"):
                self._current_sstable[host].token_space_coverage = float(line.split()[-1])
            elif line.startswith("Estimated cardinality:"):
                self._current_sstable[host].estimated_cardinality = int(line.split()[-1])

        for line in stderr:
            self.display.display(f"[{host} error] {line}", color="yellow")

    def process_exit(self, host: str, exit_code: int | None, exception: Exception | None) -> None:
        if exception:
            self.display.display(f"[EXCEPTION: {host} - {exception}]", color="red")
        elif exit_code != 0:
            self.display.display(f"[FAILURE: {host} (code={exit_code})]", color="red")
        else:
            use_json = context.CLIARGS.get("json")
            if use_json:
                tables = {
                    sstable: dataclasses.asdict(info)
                    for sstable, info in sorted(self._sstable_data[host].items())
                }
                output = {"host": host, "tables": tables}
                self.display.display(json.dumps(output))
            else:
                # Order them.
                field = context.CLIARGS.get("sort")
                sstables = sorted(self._sstable_data[host].values(), key=attrgetter(field))

                table = Table(
                    Column(header="#", justify="right"),
                    "sstable",
                    Column(header="first_token", justify="right"),
                    Column(header="last_token", justify="right"),
                    Column(header="token_range (%)", justify="right"),
                    "min_timestamp",
                    "max_timestamp",
                    Column(header="level", justify="right"),
                    Column(header="comp.ratio", justify="right"),
                    Column(header="total_columns", justify="right"),
                    Column(header="total_rows", justify="right"),
                    Column(header="token covrg.%", justify="right"),
                    Column(header="cardinality", justify="right"),
                    title=f"Host: {host}",
                )

                for num, info in enumerate(sstables):
                    range_percent = info.token_range / 2**64 * 100.0
                    table.add_row(
                        str(num + 1),
                        info.sstable,
                        str(info.first_token),
                        str(info.last_token),
                        f"{info.token_range} ({range_percent:2.0f})",
                        datetime.fromtimestamp(info.min_timestamp).isoformat(" "),
                        datetime.fromtimestamp(info.max_timestamp).isoformat(" "),
                        str(info.sstable_level),
                        f"{info.compression_ratio:.3f}",
                        str(info.total_columns_set),
                        str(info.total_rows),
                        f"{info.token_space_coverage * 100.0:.2f}",
                        str(info.estimated_cardinality),
                    )

                console = Console()
                console.print(table)


def main(args: list[str] | None = None) -> None:
    """CLI for executing commands on multiple hosts using parallel-ssh.

    Parameters
    ----------
    args : `list`[`str`]
        Command line arguments.
    """
    SSTableInfoCLI.cli_executor(args)
