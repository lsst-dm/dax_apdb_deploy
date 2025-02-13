This package implements management tools for installing and managing Cassandra clusters used by APDB.
Most of the functionality of this package is based on [Ansible](https://docs.ansible.com/) automation system.


Initialization
==============

Before using this package one needs to perform a one-time initialization:
- create Python virtual environment in `_venv` directory inside current folder,
- install `ansible` package and its dependencies,
- install necessary Ansible collections defined in `requirements.yml`.

All these steps are executed by running `make setup` which uses `Makefile` in the top-level package folder.

Every new shell will need to activate the virtual environment and set up some environment variables with this command:

    . ./setup.sh


Ansible inventories
===================

Ansible inventory is a collection of hosts, or groups of hosts, with additional metadata attached.
Complete inventory is defined in `inventory.yml` file, as there are multiple APDB clusters, we define independent host groups for each cluster.

Per-cluster host groups are defined with the group name corresponding to cluster name, e.g. `apdb_dev`.
Ansible playbooks that operate on clusters require `cluster` variable to be set one of the cluster names defined in inventory, e.g.:

    ansible-playbook -e cluster=apdb_test site.yml

The `inventory.yml` is the default inventory, as specified in `ansible.yml`.
There may be additional inventories, e.g. for testing purposes, they can be specified using `-i inventory-file` option of ansible commands.
