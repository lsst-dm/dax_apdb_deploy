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
import logging
import os
from typing import Any

import hvac
from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import option_helpers
from ansible.errors import AnsibleError
from ansible.utils.display import Display

from .. import scripts
from .utils import locate_basedir

_log_format = "%(asctime)s %(levelname)s %(name)s - %(message)s"

logging.basicConfig(level=logging.INFO, format=_log_format)

display = Display()


class CloneKeyspaceClI(CLI):
    """CLI for running clone/restore operations for a single keyspace."""

    name = "clone-keyspace"

    def init_parser(self) -> None:
        super().init_parser(
            desc="Dump a keyspace to CSV and restore dump.",
        )

        option_helpers.add_inventory_options(self.parser)
        option_helpers.add_vault_options(self.parser)
        option_helpers.add_basedir_options(self.parser)

        self.parser.add_argument(
            "--port",
            type=int,
            default=9042,
            help="Cassandra port number, default: %(default)s.",
        )
        self.parser.add_argument(
            "--use-vault",
            action="store_true",
            help="Use Vault to access credentials.",
        )
        self.parser.add_argument(
            "--username",
            default=None,
            help="Cassandra user name, typically superuser name.",
        )
        self.parser.add_argument(
            "--password",
            default=None,
            help="Cassandra password.",
        )

        subparsers = self.parser.add_subparsers(title="available subcommands", required=True)
        self._create_list_keyspaces(subparsers)
        self._create_dump_keyspace(subparsers)
        self._create_load_keyspace(subparsers)

    def _create_list_keyspaces(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("list-keyspaces", help="Show existing keyspaces.")
        parser.set_defaults(method=scripts.clone_list_keyspaces)

    def _create_dump_keyspace(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("dump-keyspace", help="Dump keyspace to a folder.")
        parser.add_argument("keyspace", type=str, help="Keyspace name.")
        parser.add_argument(
            "destination", type=str, help="Folder to dump files, will be created if does not exist."
        )
        parser.add_argument(
            "-j",
            "--jobs",
            type=int,
            default=1,
            metavar="COUNT",
            help="Number of concurrent jobs, default: %(default)s.",
        )
        parser.set_defaults(method=scripts.clone_dump_keyspace)

    def _create_load_keyspace(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("load-keyspace", help="Load keyspace deta from a folder.")
        parser.add_argument("keyspace", type=str, help="Keyspace name.")
        parser.add_argument("folder", type=str, help="Folder with keyspace data created by dump-keyspace.")
        parser.add_argument(
            "-t",
            "--table-pattern",
            dest="table_patterns",
            type=str,
            action="append",
            default=[],
            help=(
                "Only restore specified tables, argument is a pattern that matches one or more table names, "
                "can be used multiple times."
            ),
        )
        parser.add_argument(
            "--skip-existing-tables", action="store_true", help="Do not restore existing tables."
        )
        parser.add_argument(
            "-j",
            "--jobs",
            type=int,
            default=1,
            metavar="COUNT",
            help="Number of concurrent jobs, default: %(default)s.",
        )
        parser.add_argument(
            "--max-concurrent-queries",
            type=str,
            default=None,
            metavar="COUNT",
            help="Limit number cincurrent queries, one of AUTO, <N>, <N>C default: AUTO.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Do not restore, only print actions.")
        parser.set_defaults(method=scripts.clone_load_keyspace)

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

        # If --use-vault option is present then we need --playbook-dir
        # if we are not in the correct directory already. Try to guess where
        # it is.
        if options.use_vault and not options.basedir:
            options.basedir = locate_basedir()
        return options

    def _use_vault(self, cliargs: dict[str, Any], host_vars: dict[str, Any]) -> None:
        """Retrieve username and password from the Vault."""
        if host_vars["credentials_source"] != "hashi_vault":
            raise AnsibleError(
                "Cannot read credentials from the vault as credentials_source "
                f"is set to unexpected value {host_vars['credentials_source']}."
            )

        # Service URL comes from $VAULT_ADDR
        if "VAULT_ADDR" not in os.environ:
            raise AnsibleError("Vault access requires VAULT_ADDR envvar.")

        client = hvac.Client()
        if not client.is_authenticated():
            raise AnsibleError("Vault client is not authenticated.")

        mount_point = host_vars["hashi_vault_mount_point"]
        vault_path = host_vars["hashi_vault_super_path"]
        response = client.secrets.kv.read_secret_version(vault_path, mount_point=mount_point)
        vault_data = response["data"]["data"]
        cliargs["username"] = vault_data["username"]
        cliargs["password"] = vault_data["password"]

    def run(self) -> int:
        try:
            self._run()
            return 0
        except SystemExit:
            raise
        except BaseException:
            logging.exception("Execution failed.")
            return 1

    def _run(self) -> None:
        super().run()

        # Initialize needed objects
        loader, inventory, vm = self._play_prereqs()

        cliargs = context.CLIARGS

        # get list of hosts to execute against
        try:
            hosts = self.get_host_list(inventory, cliargs["subset"])
        except AnsibleError:
            if cliargs["subset"]:
                raise
            else:
                display.warning("No hosts matched, nothing to do")
                return

        # just listing hosts?
        if cliargs["listhosts"]:
            display.display(f"  hosts ({len(hosts)}):")
            for host in hosts:
                display.display(f"    {host}")
            return

        kwargs = dict(cliargs)

        # Find addresses for all hosts.
        host_address = []
        host_var = {}
        for host in hosts:
            host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
            host_address.append(host_var["ansible_host"])
        kwargs["hosts"] = host_address

        if cliargs["use_vault"] and not (cliargs["username"] and cliargs["password"]):
            self._use_vault(kwargs, host_var)

        drop_keys = {
            "version",
            "verbosity",
            "inventory",
            "listhosts",
            "subset",
            "vault_ids",
            "ask_vault_pass",
            "vault_password_files",
            "basedir",
            "flush_cache",
            "use_vault",
        }
        for key in drop_keys:
            kwargs.pop(key, None)

        method = kwargs.pop("method")
        method(**kwargs)


def main(args: list[str] | None = None) -> None:
    """CLI for interacting with medusa gRPC service(s).

    Parameters
    ----------
    args : `list`[`str`]
        Command line arguments.
    """
    CloneKeyspaceClI.cli_executor(args)
