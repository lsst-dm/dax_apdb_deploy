cassandra_accounts
==================

This role creates new accounts in Cassandra database - one new superuser account and one new regular account.
Default superuser account `cassandra` is disabled.

This role needs to be executed on a single host once after a new Cassandra cluster is brought up.

Requirements
------------

- CLuster should be up and running and configured with `authenticator: PasswordAuthenticator`.
- The `cqlsh` script is installed on remote nodes in deployment folder.
- Superuser account `cassandra` exists with the same password.
- User name and password are defined in the Vault for both superuser and regular user account.
- Vault authentication must be setup on local node (`vault login`).


Role Variables
--------------

This role does not define local variables, but it uses a few variables defined at global level:

- `service_name` - Cassandra service name.
- `deploy_docker_folder` - location of the deployment folder on remote hosts.
- `hashi_vault_mount_point` - vault mount point (prefix).
- `hashi_vault_super_path` - path to superuser secret in the Vault relative to the mount point. The secret must have two keys - `username` and `password`.
- `hashi_vault_user_path` - path to regular user secret in the Vault relative to the mount point.

Dependencies
------------

- `community.docker.docker_compose_v2_exec`
- `community.cassandra.cassandra_cqlsh`
  - `cqlsh_cmd` needs to be set to the location of `cqlsh` script on remote host (`{{ deploy_docker_folder }}/cqlsh`)
- `community.hashi_vault.vault_kv2_get`

Example Playbook
----------------

A typical example of role use:

    - name: "Setup cassandra accounts"
      serial: 1
      hosts: "{{ ansible_play_hosts[0] }}"
      gather_facts: false
      roles:
        - cassandra_accounts

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
