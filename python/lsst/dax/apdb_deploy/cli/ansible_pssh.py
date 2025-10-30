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

from ansible import constants as C
from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import option_helpers
from ansible.errors import AnsibleError
from ansible.template import Templar
from ansible.utils.display import Display
from pssh.clients import ParallelSSHClient
from pssh.exceptions import Timeout

display = Display()


class PsshCLI(CLI):
    """CLI for running parallel-ssh on remote hosts."""

    name = "ansible-pssh"

    def init_parser(self) -> None:
        super().init_parser(
            usage="usage: %prog [options] command",
            desc="Execute command on each host in inventory.",
        )

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
            "-f",
            "--follow",
            default=False,
            action="store_true",
            help="Print output without waiting for command completion.",
        )
        self.parser.add_argument("command", help="Shell command to execute on tremote hosts.", nargs="?")

    def post_process_args(self, options: argparse.Namespace) -> argparse.Namespace:
        options = super().post_process_args(options)
        return options

    def run(self) -> None:
        super().run()

        # Initialize needed objects
        loader, inventory, vm = self._play_prereqs()

        cliargs = context.CLIARGS

        # get list of hosts to execute against
        try:
            hosts = self.get_host_list(inventory, cliargs["subset"])
        except AnsibleError:
            if context.CLIARGS["subset"]:
                raise
            else:
                hosts = []
                display.warning("No hosts matched, nothing to do")

        # just listing hosts?
        if cliargs["listhosts"]:
            display.display(f"  hosts ({len(hosts)}):")
            for host in hosts:
                display.display(f"    {host}")
            return

        if not cliargs["command"]:
            raise AnsibleError("COMMAND is required if --list-hosts is not used.")

        if cliargs["single"]:
            del hosts[1:]

        # Find addresses for all hosts.
        address_to_host = {}
        deploy_docker_folders: set[str] = set()
        for host in hosts:
            host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
            address_to_host[host_var["ansible_host"]] = host
            if deploy_docker_folder := host_var.get("deploy_docker_folder"):
                templar = Templar(loader, host_var)
                deploy_docker_folders.add(templar.template(deploy_docker_folder))

        command = cliargs["command"]
        if cliargs["chdir_to_docker"]:
            if not deploy_docker_folders:
                raise AnsibleError("deploy_docker_folder is unknown, use --playbook-dir to specify basedir.")
            if len(deploy_docker_folders) > 1:
                raise AnsibleError("Multiple deploy_docker_folder values, cannot proceed.")
            deploy_docker_folder = deploy_docker_folders.pop()
            command = f"cd '{deploy_docker_folder}'; {command}"

        user = cliargs.get("remote_user")
        client = ParallelSSHClient(list(address_to_host), user=user)
        if cliargs.get("follow"):
            self._exec_follow(client, command, address_to_host)
        else:
            self._exec_wait(client, command, address_to_host)

    def _exec_wait(self, client: ParallelSSHClient, command: str, address_to_host: dict[str, str]) -> None:
        results = client.run_command(command, stop_on_errors=False)
        for result in results:
            host = address_to_host[result.host]

            # Have to read full output before asking for exit code.
            stdout = list(result.stdout) if result.stdout is not None else []
            stderr = list(result.stderr) if result.stderr is not None else []

            if result.exception:
                display.display(f"[EXCEPTION: {host} - {result.exception}]", color="red")
            elif result.exit_code == 0:
                display.display(f"[SUCCESS: {host}]", color="green")
            else:
                display.display(f"[FAILURE: {host} (code={result.exit_code})]", color="red")

            for line in stdout:
                display.display(line)
            if stderr:
                display.display("[error output]", color="yellow")
                for line in stderr:
                    display.display(line, color="yellow")

    def _exec_follow(self, client: ParallelSSHClient, command: str, address_to_host: dict[str, str]) -> None:
        results = client.run_command(command, stop_on_errors=False, use_pty=True, read_timeout=0.1)
        finished = []
        while results:
            for result in results:
                host = address_to_host[result.host]

                try:
                    for line in result.stdout:
                        display.display(f"[{host}] {line}")
                except Timeout:
                    pass

                try:
                    for line in result.stderr:
                        display.display(f"[{host} error] {line}", color="yellow")
                except Timeout:
                    pass

                if result.exit_code is not None:
                    finished.append(result)

            results = [result for result in results if result not in finished]

        for result in finished:
            host = address_to_host[result.host]
            if result.exception:
                display.display(f"[EXCEPTION: {host} - {result.exception}]", color="red")
            elif result.exit_code == 0:
                display.display(f"[SUCCESS: {host}]", color="green")
            else:
                display.display(f"[FAILURE: {host} (code={result.exit_code})]", color="red")

            result.client.close_channel(result.channel)

        client.join(finished)


def main(args: list[str] | None = None) -> None:
    """CLI for executing commands on multiple hosts using parallel-ssh.

    Parameters
    ----------
    args : `list`[`str`]
        Command line arguments.
    """
    PsshCLI.cli_executor(args)
