medusa_configs
==============

This role generates config and credentials files for Medusa and copies them to remote hosts.
If `use_backups` variable is set o false then this role does not do anything.

Requirements
------------

As this role uses `make_credentials` role, its requirements needs to be satisfied.

Role Variables
--------------

`defaults/main.yaml` variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `backup_storage_provider` | Storage provider for medusa | `s3_compatible` |
| `backup_aws_key_file` | path to S3 credentials in medusa container, name is determined by docker-compose.yaml secrets for medusa service | `/run/secrets/medusa-minio-credentials` |
| `backup_transfer_max_bandwidth` | Max bandwidth for backup transfers (for each node) | `512MiB` |
| `backup_concurrent_transfers` | umber of concurrent transfers | 3 |

These variables need to be set to use this role:
| Variable | Description |
|----------|-------------|
| `backup_bucket_name` | S3 bucket name, needs to be set |
| `backup_hashi_vault_aws_path` | path to S3 credentials in Hashi Vault, needs to be set |
| `backup_prefix` | Additional prefix for backups, default: empty |
| `backup_s3_host` | name of the S3 backup host, needs to be set |
| `backup_s3_port` | port number for S3 service, needs to be set |

The role uses variables defined elsewhere:

| Variable | Description |
|----------|-------------|
| `use_backups` | boolean specifying whether medusa is needed |
| `cassandra_user_uid` | UID for the account used to run Medusa service in Docker container |
| `deploy_docker_folder` | location of the deployment folder on remote hosts |

Dependencies
------------

Roles used by this role:

- `make_credentials`

Example Playbook
----------------

A typical example of role use:

    - name: "Copy files to remote nodes"
      hosts: all
      gather_facts: false
      roles:
        - medusa_configs

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
