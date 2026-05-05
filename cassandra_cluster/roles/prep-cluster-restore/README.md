prep-cluster-restore
====================

This role prepares environment on remote host suitable for execution of `medusa cluster-restore` command.
Normal way to restore Cassandra cluster is to use `medusa-restore` playbook, but it only works when restoring into the same topology.
The `medusa cluster-restore` command can restore backups to a cluster of different topology, but it needs `cassandra-medusa` package and Cassandra `sstableloader` executable installed on every node.

Here are the steps that this role performs:

- Installs file `~/.bashrc.d/50-squid-proxy.conf` containing envvars for HTTP(S) proxy needed to run `pip install`.
  That file is sourced by `~/.bashrc`, which already has necessary code.
- Creates virtual environment to install `cassandra-medusa` in `{{ medusa_venv }}`.
- Installs `cassandra-medusa` in that virtual environment.
- Installs `~/.bashrc.d/60-activate-medusa-env.conf` file which activates that virtual environment on login, so that `medusa` executable is in the `$PATH`.
- Installs Cassandra in `{{ deploy_folder }}/cassandra`, needed to run `sstableloader`.
- Creates directory `{{ deploy_folder }}/cluster-restore` and copies `medusa.ini` file to that directory.

The `medusa cluster-restore` command should use `--config-file={{ deploy_folder }}/cluster-restore/medusa.ini` option, plus all other.

Requirements
------------

This role depends on Cassandra configuration file installed in `{{ deploy_docker_folder }}`.

`make_credentials` role is used to extract Cassandra credentials from the Vault.
Vault should be authenticated with `vault login`.

Role Variables
--------------

- `deploy_folder` - location for installation of all deployment tools, usually set in group vars.
- `deploy_docker_folder` - location of the docker-based deployment.
- `cassandra_version` - usually set in group vars.
- `medusa_venv` - location of the virtual environment for `cassandra-medusa`, default is `{{ deploy_folder }}/medusa-venv`.
- `cassandra_download_uri` - URL to download Cassandra binary package, default should be OK, it depends on `cassandra_version`.
- `backup_storage_provider`
- `backup_bucket_name`
- `backup_prefix`
- `backup_transfer_max_bandwidth`
- `backup_concurrent_transfers`
- `backup_s3_host`
- `backup_s3_port`

Dependencies
------------

- `make_credentials` role.

Example Playbook
----------------

    - name: "Prepare for cluster restore"
      hosts: "{{ ansible_play_hosts }}"
      gather_facts: false

      roles:
        - prep-cluster-restore


License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
