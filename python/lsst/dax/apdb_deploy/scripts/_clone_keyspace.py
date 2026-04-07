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
import logging
import os
import re
import subprocess

from cassandra.auth import AuthProvider, PlainTextAuthProvider
from cassandra.cluster import Cluster
from prettytable import PrettyTable

_LOG = logging.getLogger(__name__)

_KS_PLACEHOLDER = "${KEYSPACE}"

_CREATE_TABLE_RE = re.compile('(.*CREATE TABLE )([^.]+)([.].*)', re.DOTALL)


def _check_dsbulk() -> None:
    """Check that dsbulk application can be executed."""
    try:
        subprocess.run(("dsbulk", "--version"), capture_output=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to execute dsbulk, check $PATH: {exc}") from None

def _make_auth_provider(username: str | None, password: str | None) -> AuthProvider | None:
    """Make Cassandra authentication provider instance."""
    if username and password:
        return PlainTextAuthProvider(username=username, password=password)
    return None


def _make_cluster(hosts: list[str], port: int, username: str | None, password: str | None) -> Cluster:
    # Use first two hosts for contact points.
    contact_points = hosts[:2]
    return Cluster(
        contact_points=contact_points,
        port=port,
        auth_provider=_make_auth_provider(username, password),
    )


def _replace_ks_name(statement: str) -> str:
    """Replace keyspace name in CREATE TABLE with a placeholder"""
    return _CREATE_TABLE_RE.sub(f"\\1{_KS_PLACEHOLDER}\\3", statement)


def clone_list_keyspaces(hosts: list[str], port: int, username: str | None, password: str | None) -> None:
    """List keyspaces that exist in the cluster.

    Parameters
    ----------
    hosts : `list` [`str`]
        Names of the hosts in the cluster.
    port : `int`
        CQL port number.
    username : `str` or `None`
        Cassandra user name.
    password : `str` or `None`
        Cassandra password.
    """
    asyncio.run(_list_keyspaces(hosts=hosts, port=port, username=username, password=password))


def clone_dump_keyspace(
    keyspace: str, destination: str, hosts: list[str], port: int, username: str | None, password: str | None
) -> None:
    """Dump keyspace schema and data to a specified directory.

    Parameters
    ----------
    keyspace : `str`
        Keyspace name.
    destination : `str`
        Folder name to store data to, will be created if does not exist.
    hosts : `list` [`str`]
        Names of the hosts in the cluster.
    port : `int`
        CQL port number.
    username : `str` or `None`
        Cassandra user name.
    password : `str` or `None`
        Cassandra password.
    """
    asyncio.run(
        _dump_keyspace(
            keyspace=keyspace,
            destination=destination,
            hosts=hosts,
            port=port,
            username=username,
            password=password,
        )
    )


async def _list_keyspaces(*, hosts: list[str], port: int, username: str | None, password: str | None) -> None:
    with _make_cluster(hosts, port, username, password) as cluster:
        with cluster.connect() as session:
            query = "SELECT keyspace_name, replication FROM system_schema.keyspaces"
            result = session.execute(query)
            rows = sorted(result)

            if rows:
                columns = [[row[i] for row in rows] for i in range(2)]
                table = PrettyTable()
                table.add_column("Keyspace", columns[0], "l")
                table.add_column("Replication", columns[1], "l")
                print(table)


async def _dump_keyspace(
    keyspace: str, destination: str, hosts: list[str], port: int, username: str | None, password: str | None
) -> None:
    # Need dsbulk, check that it can be found.
    _check_dsbulk()

    # Create destination if does not exist.
    dsbulk_logs = os.path.join(destination, "dsbulk_log")
    os.makedirs(dsbulk_logs, exist_ok=True)
    manifest: list[str] = []

    # Check that keyspace exists.
    with _make_cluster(hosts, port, username, password) as cluster:
        with cluster.connect() as session:
            query = "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = '%s'"
            result = session.execute(query, [keyspace])
            if not result:
                raise ValueError(f"Keyspace {keyspace!r} does not exist.")

            # Get the list of tables.
            query = "SELECT table_name FROM system_schema.tables WHERE keyspace_name = '%s'"
            result = session.execute(query, [keyspace])
            tables = sorted(row[0] for row in result)
            if not tables:
                raise ValueError(f"Keyspace {keyspace!r} does not have any tables.")

            # Dump schema for all tables but do not include CREATE KEYSPACE.
            with open(os.path.join(destination, "schema.cql"), "w") as out:
                for table in tables:
                    query = f'DESCRIBE "{keyspace}"."{table}"'
                    result = session.execute(query)
                    table_schema = result.one().create_statement
                    table_schema = _replace_ks_name(table_schema)
                    print(f"{table_schema}\n", file=out)
            manifest.append("schema.cql")

    with open(os.path.join(destination, "tables.txt"), "w") as out:
        for table in tables:
            print(table, file=out)
    manifest.append("tables.txt")

    for table in tables:
        file_name = _dump_table(
            host=hosts[0],
            port=port,
            keyspace=keyspace,
            table=table,
            destination=destination,
            username=username,
            password=password,
        )
        manifest.append(file_name)

    # Finally write manifest.
    with open(os.path.join(destination, "manifest.txt"), "w") as out:
        for name in manifest:
            print(name, file=out)


def _dump_table(
    host: str,
    port: int,
    keyspace: str,
    table: str,
    destination: str,
    username: str | None,
    password: str | None,
) -> str:
    """Dump table contents as CSV file."""
    output_file = f"{table}.csv.gz"
    output_path = os.path.join(destination, output_file)
    log_dir = os.path.join(destination, "_dsbulk_log")
    os.makedirs(log_dir, exist_ok=True)

    cmd = [
        "dsbulk",
        "unload",
        "-h",
        f'["{host}"]',
        "-port",
        str(port),
        "-k",
        keyspace,
        "-t",
        table,
        "-logDir",
        log_dir,
        "--log.verbosity",
        "quiet",
    ]
    if username:
        cmd += ["-u", username]
    if password:
        cmd += ["-p", password, "--driver.advanced.auth-provider.class=PlainTextAuthProvider"]

    # In dsbulk compression with output to stdout does not work, it crashes
    # and/or makes corrupted file. Instead do usual pipe from uncompressed
    # stream to gzip.
    fd = None
    _LOG.info("Dumping table %s to file %s", table, output_path)
    try:
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_DIRECT)
        try:
            dsbulk = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            gzip = subprocess.Popen(("gzip", "-9"), stdin=dsbulk.stdout, stdout=fd)
            dsbulk.stdout.close()
            gzip.wait()
        except Exception as exc:
            raise RuntimeError(f"Failed to execute dsbulk unload: {exc}") from None
    except Exception as exc:
        raise RuntimeError(f"Failed to open output file: {exc}") from None
    finally:
        if fd is not None:
            os.close(fd)

    return output_file
