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

from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import option_helpers as opt_help
from ansible.errors import AnsibleError
from ansible.utils.display import Display

from .. import scripts

display = Display()


class MedusaClI(CLI):
    """CLI for running parallel-ssh on remote hosts."""

    name = "medusa-backup"

    def init_parser(self) -> None:
        super().init_parser(
            usage="usage: %prog [options] command",
            desc="Execute command on each host in inventory.",
        )

        opt_help.add_inventory_options(self.parser)
        opt_help.add_vault_options(self.parser)

        self.parser.add_argument(
            "--port",
            type=int,
            default=50051,
            help="Medusa service port number, default: %(default)s.",
        )

        subparsers = self.parser.add_subparsers(title="available subcommands", required=True)
        self._create_make_backup(subparsers)
        self._create_show_backups(subparsers)
        self._create_delete_backup(subparsers)
        self._create_purge_backups(subparsers)

    def _create_show_backups(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("show-backups", help="Show existing backups.")
        parser.set_defaults(method=scripts.medusa_show_backups)

    def _create_make_backup(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("make-backup", help="Make new backup.")
        parser.add_argument(
            "-n",
            "--name",
            default=None,
            help="Backup name, default is to use current time to construct a name.",
        )
        parser.add_argument(
            "-f",
            "--full",
            default=False,
            action="store_true",
            help="Make full backup, default is differential backup.",
        )
        parser.add_argument(
            "-a",
            "--async",
            dest="_async",
            default=False,
            action="store_true",
            help="Run backup in async mode.",
        )
        parser.set_defaults(method=scripts.medusa_make_backup)

    def _create_delete_backup(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("delete-backup", help="Delete existing backup.")
        parser.add_argument("name", type=str, help="Backup name.")
        parser.set_defaults(method=scripts.medusa_delete_backup)

    def _create_purge_backups(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(
            "purge-backups",
            help="Delete obsolete backups based on max_backup_age and max_backup_count.",
        )
        parser.set_defaults(method=scripts.medusa_purge_backups)

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
        for host in hosts:
            host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
            host_address.append(host_var["ansible_host"])
        kwargs["hosts"] = host_address

        drop_keys = {
            "version",
            "verbosity",
            "inventory",
            "listhosts",
            "subset",
            "vault_ids",
            "ask_vault_pass",
            "vault_password_files",
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
    MedusaClI.cli_executor(args)
