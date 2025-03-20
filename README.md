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

Some ansible variables will be specific to a cluster.
Defaults for this variables are set in the file `cassandra_cluster/group_vars/all.yml`.
Cluster-specific overrides for these variables appear in the file `cassandra_cluster/group_vars/<cluster_name>.yml`.


Deployment model
================

Deployment of Cassandra on a cluster of hosts includes:

- Generation of configuration files for Cassandra and Docker based on variables (in `group_vars/all.yml` and their overrides).
  - These config files are generated on a local host in a `cassandra_cluster/.cache/` folder.
  - Configs are extracted from Cassandra distribution and then patched with necessary overrides.
- If monitoring is enabled (`use_monitoring` variable), then JAR file for Jolokia is downloaded to local host (same `.cache/` folder).
- On each cluster host:
  - Directories are created at a location specified by `deploy_folder` variable.
  - Configuration files are copied from `.cache/` to that location, or some subdirectory.
- If monitoring is enabled:
  - Jolokia JAR file is also copied to each host.
  - Telegraf config file and filter script are copied to `/etc/telegraf/telegraf.d/` directory, this requires `sudo`.


Bootstrapping the cluster
-------------------------

Very first start of the multi-node cluster needs special care:

- It is recommended to bring up seed nodes first, sequentially, one-by-one.
- Once all seed nodes are up, all other nodes can be started.
- If authentication is enabled (should be true for any reasonable setup):
  - Using default initial credentials (`cassandra`/`cassandra`) create new super-user account.
  - Using new super-user accout delete default `cassandra` account.
  - Create additional non-super-user accounts, typically allowing them to create keyspaces.

Non-trivial part here is how to realize that bootstrap is needed.
Potentially we can always start cluster in the same order - first seed nodes sequentially, then all the rest.
One can check the existence of `cassandra` account to decide whether we need to create other accounts.

To serialize startup of the seed nodes we need to know when the node is actually up before starting another one.
The easiest way to do that is to probe native client port `9042` and wait until it responds (with a reasonable timeout).
