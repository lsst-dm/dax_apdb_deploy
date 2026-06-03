make_credentials
================

This role can extract various types of credentials from potentially multiple sources.
For now only Hashi Vault is supported as a source.

Requirements
------------

If using Hashi Vault:

- `VAULT_ADDR` environment variable has to be set to the URL of the Vault.
- Vault needs to be authenticated with `vault login`.
- `hashi_vault` module depends on `hvac` Python module.
- The role is executed on local host.

Role Variables
--------------

`defaults/main.yaml` variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `credentials_var` | name of the variable that will contain resulting credentials | `credentials` |
| `hashi_vault_mount_point` | Hashi Vault mount point for credentials | `secret` |

These variables need to be set to use this role:

| Variable | Description |
|----------|-------------|
| `credentials_source` | credential source, set it to "hashi_vault" to use Hashi Vault |
| `credentials_account` | type of credentials to extract |

`credentials_account` has to be set to one of the following:
  - `cassandra_user` to return credential for Cassandra regular user,
  - `cassandra_super` to return credential for Cassandra superuser,
  - `backup_s3` to return credential for S3 bucket used for backups.

When `credentials_source` is set to "hashi_vault" these variables needs to be set:

- `hashi_vault_user_path` - path of the secret for Cassandra regular user account. Secret has to define `username` or `user`, and `password` attributes.
- `hashi_vault_super_path` - path of the secret for Cassandra superuser account. Secret has to define `username` or `user`, and `password` attributes.
- `backup_hashi_vault_aws_path` - path of the secret for S3 bucket.  Secret has to define `access_key` and `secret_key` attributes.
- `hashi_vault_mount_point` may need to be changed if mount point is different.

When credentials are successfully extracted the role sets a variable whose name is defined by `credentials_var` to an object with two attributes:

- `username` and `password` for Cassandra accounts,
- `access_key` and `secret_key` for S3 bucket credentials.

Dependencies
------------

Roles used by this role:

- `community.hashi_vault.vault_kv2_get` module (when `credentials_source` is set to "hashi_vault")

Example Playbook
----------------

Simple example of extracting user credentials:

    - name: "Get credentials for Cassandra"
      import_role:
        name: make_credentials
      vars:
        credentials_account: "cassandra_user"
        credentials_var: "_user_credentials"

    - ansible.builtin.set_fact:
        cassandra_username: "{{ _user_credentials.username }}"
        cassandra_password: "{{ _user_credentials.password }}"


License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
