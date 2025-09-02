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
from ansible.utils.display import Display
from pssh.clients import ParallelSSHClient

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

        self.parser.add_argument(
            "-u",
            "--user",
            default=C.DEFAULT_REMOTE_USER,
            dest="remote_user",
            help="connect as this user (default=%(default)s)",
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

        # Find addresses for all hosts.
        address_to_host = {}
        for host in hosts:
            host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
            address_to_host[host_var["ansible_host"]] = host

        if not cliargs["command"]:
            raise AnsibleError("COMMAND is required if --list-hosts is not used.")

        user = cliargs.get("user")
        client = ParallelSSHClient(list(address_to_host), user=user)
        results = client.run_command(cliargs["command"], stop_on_errors=False)
        client.join(results)
        for result in results:
            host = address_to_host[result.host]

            # Have to read full output before asking for exit code.
            stdout = list(result.stdout)
            stderr = list(result.stderr)

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


def main(args: list[str] | None = None) -> None:
    """CLI for executing commands on multiple hosts using parallel-ssh.

    Parameters
    ----------
    args : `list`[`str`]
        Command line arguments.
    """
    PsshCLI.cli_executor(args)
