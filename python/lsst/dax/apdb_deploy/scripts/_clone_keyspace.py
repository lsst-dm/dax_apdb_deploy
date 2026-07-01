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
import fnmatch
import gzip
import json
import logging
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import ExitStack
from string import Template
from typing import Literal

from cassandra.auth import AuthProvider, PlainTextAuthProvider
from cassandra.cluster import Cluster, Session
from cassandra.policies import RoundRobinPolicy
from prettytable import PrettyTable

from lsst.resources import ResourcePath

_LOG = logging.getLogger(__name__)

_KS_PLACEHOLDER = "${KEYSPACE}"
_EXISTS_PLACEHOLDER = "${IF_NOT_EXISTS}"

_CREATE_TABLE_RE = re.compile("(.*CREATE TABLE )([^.]+)([.].*)", re.DOTALL)

# Location of the dsbulk log files relative to other dumped files.
_DSBULK_LOG = "_dsbulk_log"


def clone_list_keyspaces(*, hosts: list[str], port: int, username: str | None, password: str | None) -> None:
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
    _list_keyspaces(hosts=hosts, port=port, username=username, password=password)


def clone_dump_keyspace(
    *,
    keyspace: str,
    destination: str,
    hosts: list[str],
    port: int,
    username: str | None,
    password: str | None,
    table_patterns: list[str],
    jobs: int,
    bundle: Literal["tar", "zip"] | None,
    tmp_dir: str | None,
) -> None:
    """Dump keyspace schema and data to a specified directory, archive, or
    a remote URL.

    Parameters
    ----------
    keyspace : `str`
        Keyspace name.
    destination : `str`
        Local folder name, archive name, or a remote URL to store data to.
        Folder will be created if does not exist.
    hosts : `list` [`str`]
        Names of the hosts in the cluster.
    port : `int`
        CQL port number.
    username : `str` or `None`
        Cassandra user name.
    password : `str` or `None`
        Cassandra password.
    table_patterns : `list` [`str`]
        List of patterns, tables will be dumped if they match one of the
        patterns, if empty then all tables will be dumped.
    jobs : `int`
        Number of concurrent jobs.
    bundle : `str` or `None`
        If not `None` then bundle all files into a single archive, can be
        either "tar" or "zip".
    tmp_dir : `str` or `None`
        Location of temporary folder to store intermediate files, must be
        specified if ``bundle`` is not `None`or when ``destination`` is a
        remote URL; ignored otherwise.
    """
    with ExitStack() as exit_stack:
        asyncio.run(
            _dump_keyspace(
                keyspace=keyspace,
                destination=destination,
                hosts=hosts,
                port=port,
                username=username,
                password=password,
                table_patterns=table_patterns,
                jobs=jobs,
                bundle=bundle,
                tmp_dir=tmp_dir,
                exit_stack=exit_stack,
            )
        )


def clone_load_keyspace(
    *,
    keyspace: str,
    folder: str,
    hosts: list[str],
    port: int,
    username: str | None,
    password: str | None,
    table_patterns: list[str],
    skip_existing_tables: bool,
    jobs: int,
    max_concurrent_queries: str | None,
    dry_run: bool,
) -> None:
    """Load keyspace data from a specified directory.

    Parameters
    ----------
    keyspace : `str`
        Keyspace name.
    folder : `str`
        Folder name to load data from.
    hosts : `list` [`str`]
        Names of the hosts in the cluster.
    port : `int`
        CQL port number.
    username : `str` or `None`
        Cassandra user name.
    password : `str` or `None`
        Cassandra password.
    table_patterns : `list` [`str`]
        List of patterns, tables will be loaded if they match one of the
        patterns, if empty then all tables will be loaded.
    skip_existing_tables : `bool`
        If `True` then loading will be skipped for the tables that already
        exist in the keyspace.
    jobs : `int`
        Number of concurrent jobs.
    max_concurrent_queries : `str` or `None`
        Limit number of concurrent queries.
    dry_run : `bool`
        If `True` print actions but do not restore.
    """
    asyncio.run(
        _load_keyspace(
            keyspace=keyspace,
            folder=folder,
            hosts=hosts,
            port=port,
            username=username,
            password=password,
            table_patterns=table_patterns,
            skip_existing_tables=skip_existing_tables,
            jobs=jobs,
            max_concurrent_queries=max_concurrent_queries,
            dry_run=dry_run,
        )
    )


def _list_keyspaces(*, hosts: list[str], port: int, username: str | None, password: str | None) -> None:
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
    *,
    keyspace: str,
    destination: str,
    hosts: list[str],
    port: int,
    username: str | None,
    password: str | None,
    table_patterns: list[str],
    jobs: int,
    bundle: Literal["tar", "zip"] | None,
    tmp_dir: str | None,
    exit_stack: ExitStack,
) -> None:
    # Need dsbulk, check that it can be found.
    _check_dsbulk()

    # Validate bundle mode destination path.
    dst_resource = ResourcePath(destination)
    tmp_path: ResourcePath | None = None
    if bundle is not None:
        if bundle not in ("tar", "zip"):
            raise ValueError(f"Unexpected bundle type: {bundle}.")
        if dst_resource.isdir():
            raise ValueError(f"Destination {dst_resource!r} cannot be a directory.")
        if dst_resource.getExtension().lower() != f".{bundle}":
            raise ValueError(
                f"Destination extension {dst_resource.getExtension()!r} "
                f"does not match bundle type {bundle!r}."
            )
    else:
        if not dst_resource.isdir():
            raise ValueError(f"Destination {dst_resource!r} must be a directory.")

    # Make a temporary folder from which we can copy/transfer files.
    if bundle is not None or not dst_resource.isLocal:
        if not tmp_dir:
            raise ValueError("Temporary directory must be specified.")
        os.makedirs(tmp_dir, exist_ok=True)
        temp_directory = tempfile.TemporaryDirectory(dir=tmp_dir)
        exit_stack.enter_context(temp_directory)
        tmp_path = ResourcePath(temp_directory.name)

    dump_location = tmp_path if tmp_path is not None else dst_resource

    # Create destination if does not exist.
    dsbulk_logs = dump_location.join(_DSBULK_LOG)
    dsbulk_logs.mkdir()
    manifest: list[str] = []

    # Get schema for all tables to be dumped.
    schema = _table_schema(keyspace, hosts, port, username, password, table_patterns)
    with open(dump_location.join("schema.json").ospath, "w") as out:
        json.dump(schema, out)
    manifest.append("schema.json")

    t0 = time.time()

    tables = sorted(schema)
    n_tasks = max(jobs, 1)
    tasks: list[asyncio.Task] = []
    exceptions = []
    while True:
        while tables and len(tasks) < n_tasks:
            task = asyncio.create_task(
                _dump_table(
                    host=hosts[0],
                    port=port,
                    keyspace=keyspace,
                    table=tables.pop(0),
                    destination=dump_location.ospath,
                    username=username,
                    password=password,
                )
            )
            tasks.append(task)
        if not tasks:
            break
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        tasks = list(pending)
        for task in done:
            if exc := task.exception():
                exceptions.append(exc)
            else:
                file_name = await task
                manifest.append(file_name)

    if exceptions:
        raise BaseExceptionGroup("One or more operations failed", exceptions)

    # Finally write manifest, it is a marker that dump is complete.
    with open(dump_location.join("manifest.txt").ospath, "w") as out:
        for name in sorted(manifest):
            print(name, file=out)

    t1 = time.time()

    _LOG.info("Total time for dump: %.2f sec", t1 - t0)

    if bundle is not None:
        local_bundle_path = dst_resource
        if not dst_resource.isLocal:
            local_bundle_path = dump_location.join(dst_resource.basename())

        if bundle == "tar":
            _make_tarball(dump_location, manifest, local_bundle_path)
        elif bundle == "zip":
            _make_zip(dump_location, manifest, local_bundle_path)
        else:
            raise ValueError(f"Unexpected bundle type {bundle}")

        if local_bundle_path != dst_resource:
            _LOG.info("Transferring bundle to %s", dst_resource)
            dst_resource.transfer_from(local_bundle_path, transfer="move")

    elif not dst_resource.isLocal:
        # Transfer individual files to remote.
        _LOG.info("Transferring files to %s", dst_resource)
        for local_path in _walk_files(dump_location):
            rel_path = local_path.relative_to(dump_location)
            assert rel_path is not None, "must be relative"
            remote_path = dst_resource.join(rel_path)
            remote_path.transfer_from(local_path, transfer="move")


async def _dump_table(
    *,
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
    log_dir = os.path.join(destination, _DSBULK_LOG)
    os.makedirs(log_dir, exist_ok=True)

    # Command to dump table data in CSV format to stdout.
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
        file_obj = os.fdopen(fd, "wb")
    except Exception as exc:
        raise RuntimeError(f"Failed to open output file: {exc}") from exc
    try:
        shell_cmd = shlex.join(cmd) + " | gzip -9"
        dsbulk = await asyncio.create_subprocess_shell(
            shell_cmd, stdin=asyncio.subprocess.DEVNULL, stdout=file_obj
        )
        returncode = await dsbulk.wait()
        if returncode != 0:
            raise RuntimeError(f"Failed to execute dsbulk for table {table}: return code = {returncode}")
    except Exception as exc:
        raise RuntimeError(f"Failed to execute dsbulk unload for table {table}: {exc}") from exc
    finally:
        file_obj.close()

    _LOG.info("Finished dumping table %s", table)
    return output_file


async def _load_keyspace(
    *,
    keyspace: str,
    folder: str,
    hosts: list[str],
    port: int,
    username: str | None,
    password: str | None,
    table_patterns: list[str],
    skip_existing_tables: bool,
    jobs: int,
    max_concurrent_queries: str | None,
    dry_run: bool,
) -> None:
    # Need dsbulk, check that it can be found.
    _check_dsbulk()

    # Check that folder is there.
    if not os.path.isdir(folder):
        raise ValueError(f"Folder {folder!r} does not exist or is not a directory.")

    # Check manifest.
    manifest_path = os.path.join(folder, "manifest.txt")
    if not os.path.isfile(manifest_path):
        raise ValueError(f"Manifest file {manifest_path!r} does not exist, dump may be incomplete.")

    # Read schema.
    schema_path = os.path.join(folder, "schema.json")
    with open(schema_path) as f:
        schema = json.load(f)
        if not isinstance(schema, dict):
            raise TypeError("Unexpected type of schema object in schema.json.")
        if not schema:
            raise ValueError("Empty dictionary found in schema.json.")

    options = []
    if max_concurrent_queries is not None:
        options.append(f"{max_concurrent_queries=}")
    if options:
        _LOG.info("Using restore options %s", " ".join(options))

    # Check that all explicitly requested tables exist in the dump.
    if table_patterns:
        tables_to_load = []
        for pattern in table_patterns:
            if matching_tables := fnmatch.filter(schema, pattern):
                tables_to_load += matching_tables
            else:
                raise ValueError(f"Pattern {pattern!r} does not match any table name.")
        tables_to_load = sorted(set(tables_to_load))
    else:
        tables_to_load = sorted(schema)

    exceptions = []
    with _make_cluster(hosts, port, username, password) as cluster:
        with cluster.connect() as session:
            query = "SELECT keyspace_name FROM system_schema.keyspaces where keyspace_name ='%s'"
            result = session.execute(query, (keyspace,))
            if len(list(result)) == 0:
                raise LookupError(
                    f"Keyspace {keyspace!r} does not exist in destination cluster, "
                    "it has to be created first."
                )

            # Find existing tables.
            existing_tables = set(_keyspace_tables(session, keyspace))

            if existing_tables and not skip_existing_tables:
                raise ValueError(
                    "Keyspace already contains some tables, "
                    "use --skip-existing-tables option if you want to avoid restoring them."
                )

            # Create all tables first.
            for table in tables_to_load:
                if skip_existing_tables and table in existing_tables:
                    continue
                # Generate table schema and create the table.
                _LOG.info("Creating table %s", table)
                if not dry_run:
                    table_schema_template = Template(schema[table])
                    table_ddl = table_schema_template.substitute(KEYSPACE=keyspace, IF_NOT_EXISTS="")
                    session.execute(table_ddl, timeout=600.0)

            t0 = time.time()

            n_tasks = max(jobs, 1)
            tasks: list[asyncio.Task] = []
            while True:
                while tables_to_load and len(tasks) < n_tasks:
                    table = tables_to_load.pop(0)

                    if skip_existing_tables and table in existing_tables:
                        _LOG.info("Table %s already exists, skipping.", table)
                        continue

                    task = asyncio.create_task(
                        _load_table(
                            host=hosts[0],
                            port=port,
                            keyspace=keyspace,
                            table=table,
                            folder=folder,
                            username=username,
                            password=password,
                            max_concurrent_queries=max_concurrent_queries,
                            dry_run=dry_run,
                        )
                    )
                    tasks.append(task)

                if not tasks:
                    break

                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)

                for task in done:
                    if exc := task.exception():
                        exceptions.append(exc)

            t1 = time.time()

            _LOG.info("Total time for restore: %.2f sec", t1 - t0)

    if exceptions:
        raise BaseExceptionGroup("One or more operations failed", exceptions)


async def _load_table(
    *,
    host: str,
    port: int,
    keyspace: str,
    table: str,
    folder: str,
    username: str | None,
    password: str | None,
    max_concurrent_queries: str | None,
    dry_run: bool,
) -> None:
    """Dump table contents as CSV file."""
    input_file = f"{table}.csv.gz"
    input_path = os.path.join(folder, input_file)

    # dsbulk does not handle empty CSV files, skip them.
    with gzip.open(input_path) as f:
        data = f.read(1)
        if not data:
            _LOG.info("Skip restoring table %s, file %s is empty.", table, input_path)
            return

    _LOG.info("Restoring table %s from file %s", table, input_path)
    if dry_run:
        return

    log_dir = os.path.join(folder, _DSBULK_LOG)
    os.makedirs(log_dir, exist_ok=True)

    # Command to load table data in CSV format from stdin.
    cmd = [
        "dsbulk",
        "load",
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
    if max_concurrent_queries:
        cmd += ["--engine.maxConcurrentQueries", max_concurrent_queries]

    # Run gunzip and pipe its output to dsbulk.
    fd = None
    try:
        fd = os.open(input_path, os.O_RDONLY | os.O_DIRECT)
    except Exception as exc:
        raise RuntimeError(f"Failed to open input file: {exc}") from None

    try:
        shell_cmd = "gunzip |" + shlex.join(cmd)
        dsbulk = await asyncio.create_subprocess_shell(shell_cmd, stdin=fd)
        returncode = await dsbulk.wait()
        if returncode != 0:
            raise RuntimeError(f"Failed to execute dsbulk for table {table}: return code = {returncode}")
    except Exception as exc:
        raise RuntimeError(f"Failed to execute dsbulk load for table {table}: {exc}") from None
    finally:
        os.close(fd)

    _LOG.info("Finished restoring table %s", table)


def _walk_files(path: ResourcePath) -> Iterator[ResourcePath]:
    """Find all files in a specified directory."""
    for rp, _, files in path.walk():
        for file_name in files:
            yield rp.join(file_name)


def _make_tarball(dump_location: ResourcePath, manifest: list[str], local_bundle_path: ResourcePath) -> None:
    """Make a tarball with all files in manifest plus manifest itself and
    dsbulk log files.
    """
    # We are not compressing tar, bulk of data is already compressed.
    _LOG.info("Creating tarball %s", local_bundle_path)
    members = manifest + ["manifest.txt", _DSBULK_LOG]
    try:
        with tarfile.open(local_bundle_path.ospath, "w") as tar:
            for member in members:
                member_path = dump_location.join(member)
                tar.add(member_path.ospath, member)
                # Delete file after adding it to a tarball, could avoid running
                # out of disk space on large backups. We do not care to remove
                # dsbulk logs as they are small and will be removed when tmp
                # directory is removed.
                if member != _DSBULK_LOG:
                    member_path.remove()
    except Exception:
        # Delete partial tarball on any errors.
        try:
            local_bundle_path.remove()
        except Exception:
            pass
        raise


def _make_zip(dump_location: ResourcePath, manifest: list[str], local_bundle_path: ResourcePath) -> None:
    """Make a zip archive with all files in manifest plus manifest itself and
    dsbulk log files.
    """
    _LOG.info("Creating zip archive %s", local_bundle_path)
    members = manifest + ["manifest.txt"]
    try:
        # We are not compressing zip, bulk of data is already compressed.
        with zipfile.ZipFile(local_bundle_path.ospath, "w", compression=zipfile.ZIP_STORED) as archive:
            for member in members:
                member_path = dump_location.join(member)
                archive.write(member_path.ospath, member)
                # Delete file after adding it to archive.
                member_path.remove()

            # And all dsbulk log files.
            for local_path in _walk_files(dump_location.join(_DSBULK_LOG)):
                archive.write(local_path.ospath, local_path.relative_to(dump_location))

    except Exception:
        # Delete partial archive on any errors.
        try:
            local_bundle_path.remove()
        except Exception:
            pass
        raise


def _table_schema(
    keyspace: str,
    hosts: list[str],
    port: int,
    username: str | None,
    password: str | None,
    table_patterns: list[str],
) -> dict[str, str]:
    """Extract schema definition for all tables to be dumped.

    Returns a dict with a table name as a key and "CREATE TABLE" template as a
    value.
    """
    with _make_cluster(hosts, port, username, password) as cluster:
        with cluster.connect() as session:
            # Check that keyspace exists.
            query = "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = '%s'"
            result = session.execute(query, [keyspace])
            if not result:
                raise ValueError(f"Keyspace {keyspace!r} does not exist.")

            # Get the list of tables.
            tables = sorted(_keyspace_tables(session, keyspace))
            if not tables:
                raise ValueError(f"Keyspace {keyspace!r} does not have any tables.")
            if table_patterns:
                tables_to_dump: set[str] = set()
                for pattern in table_patterns:
                    if matching_tables := fnmatch.filter(tables, pattern):
                        tables_to_dump.update(matching_tables)
                    else:
                        raise ValueError(f"Pattern {pattern!r} does not match any table name.")
                tables = sorted(tables_to_dump)

            # Dump schema for all tables but do not include CREATE KEYSPACE.
            schema = {}
            for table in tables:
                query = f'DESCRIBE "{keyspace}"."{table}"'
                result = session.execute(query)
                table_schema = result.one().create_statement
                table_schema = _replace_ks_name(table_schema)
                schema[table] = table_schema

            return schema


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
        load_balancing_policy=RoundRobinPolicy(),
        protocol_version=5,
    )


def _keyspace_tables(session: Session, keyspace: str) -> list[str]:
    """Get the list of tables in a keyspace."""
    query = "SELECT table_name FROM system_schema.tables WHERE keyspace_name = '%s'"
    result = session.execute(query, [keyspace])
    return [row[0] for row in result]


def _replace_ks_name(statement: str) -> str:
    """Replace keyspace name in CREATE TABLE with a placeholder"""
    return _CREATE_TABLE_RE.sub(f"\\1{_EXISTS_PLACEHOLDER} {_KS_PLACEHOLDER}\\3", statement)
