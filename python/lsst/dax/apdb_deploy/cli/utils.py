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

__all__ = ["find_docker_folder", "locate_basedir", "make_host_map", "make_hosts"]

import os
from collections.abc import Iterable

from ansible.cli import CLI, DataLoader, InventoryManager, VariableManager
from ansible.errors import AnsibleError
from ansible.inventory.host import Host
from ansible.template import Templar


def locate_basedir() -> str:
    """Locate basedir folder.

    Returns
    -------
    basedir : `str`
        Location of basedir.

    Raises
    ------
    AnsibleError
        Raised if cannot locate basedir.
    """
    cwd = os.getcwd()
    candidates = (cwd, os.path.join(cwd, "cassandra_cluster"))
    for basedir in candidates:
        files = os.listdir(basedir)
        if os.path.basename(basedir) == "cassandra_cluster" and "roles" in files:
            return basedir

    raise AnsibleError("Cannot locate playbook folder, use --playbook-dir to specify basedir.")


def make_hosts(inventory: InventoryManager, subset: str) -> list[Host]:
    """Make a list of the short host names.

    Parameters
    ----------
    inventory
        Ansible inventory.
    subset
        Pattern which specifies inventory subset.

    Returns
    -------
    hosts
        List of Ansible `Host` instances.

    Raises
    ------
    AnsibleError
        Raised if ``subset`` does not match any hosts in inventory.
    """
    # get list of hosts to execute against
    try:
        hosts = list(CLI.get_host_list(inventory, subset))
    except AnsibleError:
        if subset:
            raise
        else:
            return []
    return hosts


def make_host_map(hosts: Iterable[Host], vm: VariableManager) -> dict[str, str]:
    """Make a mapping of the short host names to their addresses or FQDNs.

    Parameters
    ----------
    hosts
        List of Ansible `Host` instances.
    vm
        Ansible variable manager.

    Returns
    -------
    hosts_map
        Mapping of the short host names to their addresses or FQDNs.

    Raises
    ------
    AnsibleError
        Raised if ``subset`` does not match any hosts in inventory.
    """
    # Find addresses for all hosts.
    host_to_address = {}
    for host in hosts:
        host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
        host_to_address[str(host)] = str(host_var["ansible_host"])

    return host_to_address


def find_docker_folder(hosts: Iterable[str], vm: VariableManager, loader: DataLoader) -> str:
    """Find location of docker deployment folder on remote hosts.

    Parameters
    ----------
    hosts
        Short names of remote hosts.
    vm
        Ansible variable manager.
    loader
        Ansible data loader.

    Returns
    -------
    folder
        Name of the folder with docker deployment.

    Raises
    ------
    AnsibleError
        Raised if cannot find values of Ansible variables or if folders are
        different on different hosts.
    """
    deploy_docker_folders: set[str] = set()
    for host in hosts:
        host_var = vm.get_vars(host=host, include_hostvars=False, stage="all")
        if deploy_docker_folder := host_var.get("deploy_docker_folder"):
            templar = Templar(loader, host_var)
            deploy_docker_folders.add(templar.template(deploy_docker_folder))

    if not deploy_docker_folders:
        raise AnsibleError("deploy_docker_folder is unknown, use --playbook-dir to specify basedir.")
    if len(deploy_docker_folders) > 1:
        raise AnsibleError("Multiple deploy_docker_folder values, cannot proceed.")
    return deploy_docker_folders.pop()
