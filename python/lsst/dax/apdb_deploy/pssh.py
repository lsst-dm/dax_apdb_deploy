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

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping

from pssh.clients.ssh import ParallelSSHClient, SSHClient
from pssh.exceptions import Timeout
from pssh.output import HostOutput

_LOG = logging.getLogger(__name__)


class Pssh(ABC):
    """Wrapper class for executing SSH commands on remote nodes, subclasses
    have to implement ``process_*`` methods.
    """

    def execute(
        self,
        hosts: Mapping[str, str],
        cmd: str,
        user: str | None,
        cd_folder: str | None = None,
        serial: bool = False,
        follow: bool = False,
    ) -> int:
        """Execute command on remote hosts.

        Parameters
        ----------
        hosts : `~collections.abc.Mapping` [`str`, `str`]
            Mapping of the short host names to their addresses or FQDNs.
        cmd : `str`
            Command to execute.
        user : `str` or `None`
            Remote user name.
        cd_folder : `str`, optional
            Directory to change to before executing.
        serial : `bool`, optional
            If `True` then serialize execution.
        follow : `bool`, optional
            Do not wait for command completion to process the information.

        Returns
        -------
        rc : `int`
            Zero is returned on successful completion of all remote processes.
            If any remote execution generates local exception then 1 is
            returned. If any remote process finishes with non-zero return code
            then one of those non-zero codes is returned.
        """
        address_to_host = {val: key for key, val in hosts.items()}
        if len(address_to_host) != len(hosts):
            raise ValueError(f"Duplicate host addresses: {list(hosts.values())}")

        if cd_folder:
            cmd = f"cd '{cd_folder}'; {cmd}"

        results: list[HostOutput] = []
        if serial:
            clients = [
                SSHClient(
                    host_address,
                    user=user,
                    gssapi_auth=True,
                )
                for host_address in address_to_host
            ]
            if follow:
                for client in clients:
                    result = client.run_command(cmd, use_pty=True, read_timeout=0.1)
                    self._exec_follow([result], address_to_host)
                    results.append(result)
                self._summarize(results, address_to_host)
            else:
                for client in clients:
                    result = client.run_command(cmd)
                    self._exec_wait([result], address_to_host)
                    results.append(result)
        else:
            client = ParallelSSHClient(list(address_to_host), user=user, gssapi_auth=True)
            if follow:
                results = client.run_command(cmd, use_pty=True, read_timeout=0.1, stop_on_errors=False)
                self._exec_follow(results, address_to_host)
                client.join(results)
                self._summarize(results, address_to_host)
            else:
                results = client.run_command(cmd, stop_on_errors=False)
                client.join(results)
                self._exec_wait(results, address_to_host)

        if any(result.exception for result in results):
            return 1
        for result in results:
            if result.exit_code != 0:
                return result.exit_code

        return 0

    def _exec_wait(self, results: list[HostOutput], address_to_host: Mapping[str, str]) -> None:
        for result in results:
            host = address_to_host[result.host]

            # Have to read full output before asking for exit code.
            stdout = list(result.stdout) if result.stdout is not None else []
            stderr = list(result.stderr) if result.stderr is not None else []
            self.process_full(host, stdout, stderr, result.exit_code, result.exception)

    def _exec_follow(self, results: list[HostOutput], address_to_host: Mapping[str, str]) -> None:
        finished = []
        while results:
            for result in results:
                host = address_to_host[result.host]

                stdout = []
                stderr = []

                try:
                    for line in result.stdout:
                        stdout.append(line)
                except Timeout:
                    _LOG.debug("Timeout reading stdout")

                try:
                    for line in result.stderr:
                        stderr.append(line)
                except Timeout:
                    _LOG.debug("Timeout reading stderr")

                if stdout or stderr:
                    self.process_output(host, stdout, stderr)

                if result.exception or result.exit_code is not None:
                    finished.append(result)

            results = [result for result in results if result not in finished]

    def _summarize(self, results: list[HostOutput], address_to_host: Mapping[str, str]) -> None:
        for result in results:
            host = address_to_host[result.host]
            self.process_exit(host, result.exit_code, result.exception)
            result.client.close_channel(result.channel)

    def process_full(
        self,
        host: str,
        stdout: list[str],
        stderr: list[str],
        exit_code: int | None,
        exception: Exception | None,
    ) -> None:
        """Process complete output from one host.

        Parameters
        ----------
        host : `str`
            Short host name.
        stdout : `list` [`str`]
            Lines from standard output.
        stderr : `list` [`str`]
            Lines from standard error stream.
        exit_code : `int` or `None`
            Session exit code, 0 for successful completion, `None` if exception
            had occurred.
        exception : `Exception` or `None`
            Exception raised by remote execution.

        Notes
        -----
        This method is called when ``follow`` is `False`.
        """
        self.process_output(host, stdout, stderr)
        self.process_exit(host, exit_code, exception)

    @abstractmethod
    def process_output(self, host: str, stdout: list[str], stderr: list[str]) -> None:
        """Process full or partial output streams from one host.

        Parameters
        ----------
        host : `str`
            Short host name.
        stdout : `list` [`str`]
            Lines from standard output.
        stderr : `list` [`str`]
            Lines from standard error stream.

        Notes
        -----
        This method is called repeatedly of remote command execution when
        ``follow`` is `True. Each call receives a partial content of stdout and
        stderr streams. On process completion ``process_exit`` is called.
        """
        raise NotImplementedError()

    @abstractmethod
    def process_exit(self, host: str, exit_code: int | None, exception: Exception | None) -> None:
        """Process exit code and/or an exception from one host.

        Parameters
        ----------
        host : `str`
            Short host name.
        exit_code : `int` or `None`
            Session exit code, 0 for successful completion, `None` if exception
            had occurred.
        exception : `Exception` or `None`
            Exception raised by remote execution.

        Notes
        -----
        This method is called on completion of remote command execution when
        ``follow`` is `True.
        """
        raise NotImplementedError()
