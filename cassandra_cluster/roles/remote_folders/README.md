remote_folders
==============

This role creates directories on remote hosts used for installation of deployment tools.

Requirements
------------

Role Variables
--------------

`defaults/main.yaml` variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `deploy_folder` | location for deployment tools | `{{ ansible_env.HOME }}/apdb_deploy` |
| `deploy_docker_folder` | location for all docker-compose files | `{{ deploy_folder }}/docker` |

Dependencies
------------

None.

Example Playbook
----------------

A typical example of role use:

    - name: "Create deployment folders"
      hosts: all
      gather_facts: true

      roles:
        - remote_folders

License
-------

GNU General Public License v3.0 or later.

See LICENCING to see the full text.

Author Information
------------------

Managed by LSST DM team: https://github.com/lsst-dm/dax_apdb_deploy
