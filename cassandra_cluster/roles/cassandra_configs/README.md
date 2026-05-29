cassandra_configs
=================

This role generates configuration files for Cassandra.
Files are generated locally by downloading Cassandra source tarball, extracting configuration files from it, and patching those files.
Generated files are store in a local cache directory (`.cache/cassandra-cassandra-{version}/conf/`).

Requirements
------------

- Internet access for downloading tarball (unless `cassandra_configs_download_url` variable is redefined).

Role Variables
--------------

Role default variables:

- `cassandra_configs_tar` - name of the source tarball, default: `cassandra-{{ cassandra_version }}.tar.gz`.
- `cassandra_configs_download_url` - URL for downloading source tarball, default: `https://github.com/apache/cassandra/archive/refs/tags/{{ cassandra_configs_tar }}`.
- `cassandra_configs_conf_in_tar` - path to the config directory in tarball, default: `cassandra-cassandra-{{ cassandra_version }}/conf`.
- `cassandra_configs_unpacked_conf` - directory where config files are unpacked, default: `{{ local_cache }}/{{ cassandra_configs_conf_in_tar }}`.
- `num_tokens` - number of tokens per Cassandra node, default: 4.

⚠️ NOTE:
Role tasks use hardcoded names for configuration files, and one of the files include JVM version number (e.g. `jvm11-server.options`).
When `cassandra_version` changes it may be necessary to update file name in `tasks/main.yml`.

Dependencies
------------

The role uses variables defined elsewhere:

- `cassandra_version` - Cassandra version number (e.g. `4.10.0`).
- `local_cache` - filesystem directory path on local host used to cache downloaded and generated files.
- `group_local_cache` - filesystem directory path on local host  used to cache group-specific generated files.
- `use_password` - boolean specifying whether Cassandra will use password authentication.

Example Playbook
----------------

A typical example of role use:

    - name: "Generate config files on local host"
      hosts: "{{ ansible_play_hosts[0] }}"
      serial: 1
      gather_facts: false
      roles:
        - cassandra_configs

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
