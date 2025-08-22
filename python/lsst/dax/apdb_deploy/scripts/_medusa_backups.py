import asyncio
from datetime import datetime, UTC
from typing import TYPE_CHECKING

from medusa.service.grpc.client import Client
from medusa.service.grpc.medusa_pb2 import StatusType
from prettytable import PrettyTable

from ..inventory import Inventory


def _status_fmt(status: int) -> str:
    for name, value in StatusType.items():
        if status == value:
            return name
    return "???"


def _size_fmt(size: int, suffix: str = "B") -> str:
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(size) < 1024.0:
            return f"{size:3.1f}{unit}{suffix}"
        size /= 1024.0
    return f"{size:.1f}Yi{suffix}"


def _time_fmt(time: int) -> str:
    if time:
        return datetime.fromtimestamp(time).isoformat(sep=" ")
    else:
        return ""


def medusa_make_backup(
    inventory: object, group: str | None, port: int, name: str | None, full: bool, _async: bool
) -> None:
    asyncio.run(
        _make_backup(inventory=inventory, group=group, port=port, name=name, full=full, _async=_async)
    )


def medusa_show_backups(inventory: object, group: str | None, port: int) -> None:
    asyncio.run(_show_backups(inventory=inventory, group=group, port=port))


def medusa_delete_backup(inventory: object, name: str, group: str | None, port: int) -> None:
    asyncio.run(_delete_backup(inventory=inventory, name=name, group=group, port=port))


async def _make_backup(
    *, inventory: object, group: str | None, port: int, name: str | None, full: bool, _async: bool
) -> None:

    mode = "full" if full else "differential"
    if not name:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{ts}-{mode}"

    inv = Inventory(inventory)
    hosts = inv.get_host_names(group)

    backups = {}
    for host in hosts:
        contact = f"{host}:{port}"
        client = Client(contact)
        if _async:
            backups[host] = asyncio.create_task(client.async_backup(name, mode))
        else:
            backups[host] = asyncio.create_task(client.backup(name, mode))

    for host, backup in backups.items():
        await backup


async def _show_backups(*, inventory: object, group: str | None, port: int) -> None:

    inv = Inventory(inventory)
    hosts = inv.get_host_names(group)

    contact = f"{hosts[0]}:{port}"
    client = Client(contact)
    backups = await client.get_backups()

    table = PrettyTable()
    table.field_names = [
        "Backup name",
        "Start Time",
        "Finish Time",
        "Nodes",
        # "Node list",
        "Status",
        "Type",
        "#Objects",
        "Size",
    ]
    for backup in backups:
        # node_list = [f"{node.host} ({node.datacenter}/{node.rack})" for node in backup.nodes]
        # if not node_list:
        #     node_list = [""]

        row = [
            backup.backupName,
            _time_fmt(backup.startTime),
            _time_fmt(backup.finishTime),
            f"{backup.finishedNodes}/{backup.totalNodes}",
            # node_list[0],
            _status_fmt(backup.status),
            backup.backupType,
            str(backup.totalObjects),
            _size_fmt(backup.totalSize),
        ]
        table.add_row(row)

        # remaining hosts
        # for node in node_list[1:]:
        #     row = [""] * len(table.field_names)
        #     row[4] = node
        #     table.add_row(row)

    print(table)


async def _delete_backup(*, inventory: object, name: str, group: str | None, port: int) -> None:

    inv = Inventory(inventory)
    hosts = inv.get_host_names(group)

    contact = f"{hosts[0]}:{port}"
    client = Client(contact)

    await client.delete_backup(name)
