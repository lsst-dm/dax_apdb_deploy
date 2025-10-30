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

import asyncio
from datetime import UTC, datetime

from medusa.service.grpc.client import Client
from medusa.service.grpc.medusa_pb2 import StatusType
from prettytable import PrettyTable


def _status_fmt(status: int) -> str:
    for name, value in StatusType.items():
        if status == value:
            return name
    return "???"


def _size_fmt(size: int, suffix: str = "B") -> str:
    fsize = float(size)
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(fsize) < 1024.0:
            return f"{fsize:3.1f}{unit}{suffix}"
        fsize /= 1024.0
    return f"{fsize:.1f}Yi{suffix}"


def _time_fmt(time: int) -> str:
    if time:
        return datetime.fromtimestamp(time).isoformat(sep=" ")
    else:
        return ""


def medusa_make_backup(hosts: list[str], port: int, name: str | None, full: bool, _async: bool) -> None:
    asyncio.run(_make_backup(hosts=hosts, port=port, name=name, full=full, _async=_async))


def medusa_show_backups(hosts: list[str], port: int) -> None:
    asyncio.run(_show_backups(hosts=hosts, port=port))


def medusa_delete_backup(hosts: list[str], name: str, port: int) -> None:
    asyncio.run(_delete_backup(hosts=hosts, name=name, port=port))


def medusa_purge_backups(hosts: list[str], port: int) -> None:
    asyncio.run(_purge_backups(hosts=hosts, port=port))


async def _make_backup(*, hosts: list[str], port: int, name: str | None, full: bool, _async: bool) -> None:
    mode = "full" if full else "differential"
    if not name:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{ts}-{mode}"

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


async def _show_backups(*, hosts: list[str], port: int) -> None:
    contact = f"{hosts[0]}:{port}"
    client = Client(contact)
    backups = await client.get_backups()

    table = PrettyTable()
    table.field_names = [
        "Backup name",
        "Start Time",
        "Finish Time",
        "Nodes",
        "Status",
        "Type",
        "#Objects",
        "Size",
    ]
    for backup in backups:
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

    print(table)


async def _delete_backup(*, hosts: list[str], name: str, port: int) -> None:
    contact = f"{hosts[0]}:{port}"
    client = Client(contact)

    # Have to check backup status first to refresh internal state of the
    # service, otherwise it may complain that backup is not know.
    status = await client.get_backup_status(name)
    if status == StatusType.UNKNOWN:
        raise ValueError(f"Backup {name} is not known.")

    await client.delete_backup(name)


async def _purge_backups(*, hosts: list[str], port: int) -> None:
    contact = f"{hosts[0]}:{port}"
    client = Client(contact)
    await client.purge_backups()
