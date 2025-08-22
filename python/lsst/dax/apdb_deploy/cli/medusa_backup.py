import argparse

from .. import scripts


def main() -> int | None:
    """CLI for interacting with medusa gRPC service(s)."""

    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(title="available subcommands", required=True)
    _create_make_backup(subparsers)
    _create_show_backups(subparsers)
    _create_delete_backup(subparsers)

    args = parser.parse_args()

    kwargs = vars(args)
    method = kwargs.pop("method")
    method(**kwargs)


def _create_show_backups(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("show-backups", help="Show existing backups.")
    parser.add_argument(
        "inventory", type=argparse.FileType(), help="Path to Ansible inventory file."
    )
    parser.add_argument(
        "-g",
        "--group",
        default="",
        help="Host group in inventory file, default is to use first group.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=50051,
        help="Medusa service port number, default: %(defalt)s.",
    )
    parser.set_defaults(method=scripts.medusa_show_backups)


def _create_make_backup(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("make-backup", help="Make new backup.")
    parser.add_argument(
        "inventory", type=argparse.FileType(), help="Path to Ansible inventory file."
    )
    parser.add_argument(
        "-g",
        "--group",
        default="",
        help="Host group in inventory file, default is to use first group.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=50051,
        help="Medusa service port number, default: %(default)s.",
    )
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
        help="Make full backup, default is incremental backup.",
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


def _create_delete_backup(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("delete-backup", help="Delete existing backup.")
    parser.add_argument(
        "inventory", type=argparse.FileType(), help="Path to Ansible inventory file."
    )
    parser.add_argument("name", type=str, help="Backup name.")
    parser.add_argument(
        "-g",
        "--group",
        default="",
        help="Host group in inventory file, default is to use first group.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=50051,
        help="Medusa service port number, default: %(default)s.",
    )
    parser.set_defaults(method=scripts.medusa_delete_backup)
