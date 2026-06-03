jolokia_download
================

This role downloads Jolokia tarball and extracts Jolokia agent JAR to a cache on a local host.
If `need_jolokia` variable is set to false then the role does not do anything.

Requirements
------------

- Internet access for downloading tarball (unless `jolokia_download_url` variable is redefined).

Role Variables
--------------

`defaults/main.yaml` variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `jolokia_download_tar` | name of the tarball to download | `jolokia-{{ jolokia_version }}-bin.tar.gz` |
| `jolokia_download_url` | URL for downloading Jolokia tarball | `https://github.com/jolokia/jolokia/releases/download/v{{ jolokia_version }}/{{ jolokia_download_tar }}` |
| `jolokia_download_agent_path` | path of the Jolokia agent in the tarball | `jolokia-{{ jolokia_version }}/agents/jolokia-jvm.jar` |
| `jolokia_download_jar` | name of the Jolokia agent JAR in local cache | `jolokia-jvm-{{ jolokia_version }}.jar` |

The role uses variables defined elsewhere:

| Variable | Description |
|----------|-------------|
| `need_jolokia` | boolean, if false then the role does not do anything |
| `jolokia_version` | Jolokia version string |
| `local_cache` | filesystem directory path on local host used to cache downloaded and generated files |

Dependencies
------------

None.

Example Playbook
----------------

A typical example of role use:

    - name: "Generate config files on local host"
      hosts: "{{ ansible_play_hosts[0] }}"
      serial: 1
      gather_facts: false
      roles:
        - jolokia_download

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
