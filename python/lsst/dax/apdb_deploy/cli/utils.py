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

import os

from ansible.errors import AnsibleError


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
