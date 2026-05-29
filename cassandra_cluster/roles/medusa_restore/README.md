medusa_restore
==============

This role restores Cassandra backup made earlier by medusa service (using `medusa-backup make-backup ...` command).
Restore must be performed on the cluster with the same number of nodes, ideally with the same host names.
If host names differ from names in a backup, one has to use per-node `restore_from` variable (defined in inventory file).

Restore is performed by running `medusa` service in a special restore mode.
When restore is complete `medusa` service stops, one has to wait until service stops on all nodes before trying to bring up the cluster.

Note that when restoring from a different cluster medusa configuration should point to a backup location of the old cluster.
After restore new cluster configuration may need to point to a different backup location.

Requirements
------------

- Cluster must be down, both `cassandra` and `medusa` services must be stopped.
- Data directory must exist, but be empty, it is created by `remote_folders` role or `site-init.yaml` playbook.
- Both Cassandra, Medusa, and `docker-compose.yaml` configuration files must be up to date, use `site.yaml` playbook for that.
- If host names of a new cluster differ from the host names in backup, edit inventory and add `restore_from` variable to each node (and remove it after restore).

Role Variables
--------------

The role uses variables defined elsewhere:

| Variable | Description |
|----------|-------------|
| `backup_name` | name of the backup to restore, typically provided via extra variable (`-e backup_name=...`) |
| `data_dir` | directory on remote hosts for Cassandra data |
| `deploy_docker_folder` | location of the deployment folder on remote hosts |
| `backup_service_name` | name of docker Medusa service |

Dependencies
------------

Role dependencies:

- `community.docker.docker_compose_v2_run`

Example Playbook
----------------

A typical example of role use:

    - name: "Restore cluster from backup"
      hosts: all
      gather_facts: false

      roles:
        - medusa_restore

An example of inventory with `restore_from` variables set for host name remapping.
Note that medusa is configured in a way that it uses host name in backups without domain.
If medusa configuration changes `restore_from` may need domain name in it:

    new_cluster:
      hosts:
        new-host-001:
          ansible_host: new-host-001.example.com
          restore_from: old-host-001
          cassandra_seed: true
        new-host-002:
          ansible_host: new-host-002.example.com
          restore_from: old-host-002
        new-host-003:
          ansible_host: new-host-003.example.com
          restore_from: old-host-003

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
