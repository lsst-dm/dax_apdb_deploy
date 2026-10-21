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
import json
import logging
import random

from ansible import constants as C
from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import option_helpers
from ansible.errors import AnsibleError
from ansible.utils.display import Display

from ..pssh import Pssh
from .utils import find_docker_folder, locate_basedir, make_host_map, make_hosts

_log_format = "%(levelname)s: %(name)s - %(message)s"

logging.basicConfig(level=logging.WARNING, format=_log_format)


class PsshCLI(Pssh, CLI):
    """CLI for running parallel-ssh on remote hosts."""

    display = Display()

    name = "ansible-pssh"

    def init_parser(self, desc: str | None = None, epilog: str | None = None) -> None:
        super().init_parser(desc=desc or "Execute command on each host in inventory.", epilog=epilog)

        option_helpers.add_inventory_options(self.parser)
        option_helpers.add_vault_options(self.parser)
        option_helpers.add_basedir_options(self.parser)

        self.parser.add_argument(
            "-u",
            "--user",
            default=C.DEFAULT_REMOTE_USER,
            dest="remote_user",
            help="connect as this user (default=%(default)s)",
        )
        self.parser.add_argument(
            "-d",
            "--chdir-to-docker",
            default=False,
            action="store_true",
            help="Change to docker folder before executing the command.",
        )
        self.parser.add_argument(
            "-1",
            "--single",
            default=False,
            action="store_true",
            help="Execute command on a single host.",
        )
        self.parser.add_argument(
            "-s",
            "--serial",
            default=False,
            action="store_true",
            help="Execute command sequentially on each host.",
        )
        self.parser.add_argument(
            "-r",
            "--randomize",
            default=False,
            action="store_true",
            help="Randomize node list.",
        )
        self.parser.add_argument(
            "-f",
            "--follow",
            default=False,
            action="store_true",
            help="Print output without waiting for command completion.",
        )
        self.parser.add_argument(
            "--json",
            default=False,
            action="store_true",
            help="Print results of execution in json line format.",
        )
        self.parser.add_argument("command", help="Shell command to execute on remote hosts.", nargs="?")

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

        # If --chdir-to-docker option is present then we need --playbook-dir
        # if we are not in the correct directory already. Try to guess where
        # it is.
        if options.chdir_to_docker and not options.basedir:
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

        # get list of hosts to execute against
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

        if not cliargs["command"]:
            raise AnsibleError("COMMAND is required if --list-hosts is not used.")

        if cliargs["randomize"]:
            random.shuffle(hosts)

        if cliargs["single"]:
            del hosts[1:]

        # Find addresses for all hosts.
        host_to_address = make_host_map(hosts, vm)

        deploy_docker_folder: str | None = None
        if cliargs["chdir_to_docker"]:
            deploy_docker_folder = find_docker_folder(hosts, vm, loader)

        rc = self.execute(
            hosts=host_to_address,
            cmd=cliargs["command"],
            user=cliargs.get("remote_user"),
            cd_folder=deploy_docker_folder,
            serial=cliargs["serial"],
            follow=cliargs.get("follow"),
        )

        return rc

    def process_full(
        self,
        host: str,
        stdout: list[str],
        stderr: list[str],
        exit_code: int | None,
        exception: Exception | None,
    ) -> None:
        use_json = context.CLIARGS.get("json")
        if use_json:
            output = {
                "host": str(host),
                "exit_code": exit_code,
                "stdout": "\n".join(stdout),
                "stderr": "\n".join(stderr),
            }
            if exception:
                output["exception"] = str(exception)
                output["status"] = "exception"
            elif exit_code == 0:
                output["status"] = "success"
            else:
                output["status"] = "failure"
            self.display.display(json.dumps(output))
        else:
            self.process_exit(host, exit_code, exception)

            for line in stdout:
                self.display.display(line)
            if stderr:
                self.display.display("[error output]", color="yellow")
                for line in stderr:
                    self.display.display(line, color="yellow")

    def process_output(self, host: str, stdout: list[str], stderr: list[str]) -> None:
        use_json = context.CLIARGS.get("json")
        for line in stdout:
            if use_json:
                message = json.dumps(
                    {
                        "host": str(host),
                        "output": line,
                        "stream": "stdout",
                    }
                )
            else:
                message = f"[{host}] {line}"
            self.display.display(message)

        for line in stderr:
            if use_json:
                message = json.dumps(
                    {
                        "host": str(host),
                        "output": line,
                        "stream": "stderr",
                    }
                )
                self.display.display(message)
            else:
                self.display.display(f"[{host} error] {line}", color="yellow")

    def process_exit(self, host: str, exit_code: int | None, exception: Exception | None) -> None:
        use_json = context.CLIARGS.get("json")
        if use_json:
            output = {
                "host": str(host),
                "exit_code": exit_code,
            }
            if exception:
                output["status"] = "exception"
                output["exception"] = f"{exception}"
            elif exit_code == 0:
                output["status"] = "success"
            else:
                output["status"] = "failure"
            self.display.display(json.dumps(output))
        else:
            if exception:
                self.display.display(f"[EXCEPTION: {host} - {exception}]", color="red")
            elif exit_code == 0:
                self.display.display(f"[SUCCESS: {host}]", color="green")
            else:
                self.display.display(f"[FAILURE: {host} (code={exit_code})]", color="red")


def main(args: list[str] | None = None) -> None:
    """CLI for executing commands on multiple hosts using parallel-ssh.

    Parameters
    ----------
    args : `list`[`str`]
        Command line arguments.
    """
    PsshCLI.cli_executor(args)
