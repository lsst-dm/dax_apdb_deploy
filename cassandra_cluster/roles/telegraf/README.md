Role Name
=========

This role installs configuration files and scripts for telegraf service that collect additional metrics from Cassandra cluster.
New files are installed only if `/etc/telegraf/telegraf.d` directory exists on remote host.

Following files are installed:
- `/etc/telegraf/telegraf.d/90-cassandra.conf` - collects metrics from JVM and Cassandra using Jolokia agent.
- `/etc/telegraf/telegraf.d/cassandra-metrics-rename.py` - filter script used by above config file to normalize metrics names.
- `/etc/telegraf/telegraf.d/90-zfs.conf` - collects metrics from ZFS.
- `/etc/telegraf/telegraf.d/zpool-health.py` - script used by above config file to generate additional metrics for ZFS health.

If any of the files are updated then telegraf service is restarted.

Requirements
------------

The role requires sudo privileges.

Role Variables
--------------

`defaults/main.yaml` variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `telegraf_config_path` | location of telegraf config files | `/etc/telegraf/telegraf.d` |


Dependencies
------------

None.

Example Playbook
----------------

A typical example of role use:

    - name: "Configure telegraf"
      hosts: "{{ ansible_play_hosts }}"
      gather_facts: false
      become: true
      roles:
        - telegraf

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
