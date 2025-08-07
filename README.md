# dax_apdb_deploy package

This package implements management tools for installing and managing Cassandra clusters used by APDB.
Most of the functionality of this package is based on [Ansible](https://docs.ansible.com/) automation system.


## Initialization

Before using this package one needs to perform a one-time initialization:
- create Python virtual environment in `_venv` directory inside current folder,
- install `ansible` package and its dependencies,
- install necessary Ansible collections defined in `requirements.yml`.

All these steps are executed by running `make setup` which uses `Makefile` in the top-level package folder.

Every new shell will need to activate the virtual environment and set up some environment variables with this command:

    . ./setup.sh


## Ansible inventories

Ansible inventory is a collection of hosts, or groups of hosts, with additional metadata attached.
Each Cassandra cluster is defined in a separate inventory file with the name starting with `inventory` and followed by cluster name, e.g. `inventory-apdb_dev.yaml`.
Inventories are located in the top level directory of this package.

Execution of ansible playbooks requires passing the name of the inventory file, e.g.:

    ansible-playbook -i ../inventory-apdb_dev.yaml site.yml

One can limit the set of nodes with `-l` option, e.g.:

    ansible-playbook -i ../inventory-apdb_dev.yaml -l sdfk8sk003 site.yaml

Some ansible variables will be specific to a cluster.
Defaults for this variables are set in the file `cassandra_cluster/group_vars/all.yml`.
Cluster-specific overrides for these variables appear in the file `cassandra_cluster/group_vars/<cluster_name>.yml`.


## Deployment model

Deployment of Cassandra on a cluster of hosts includes:

- One time setup of each host, this typically requires `sudo` on remote host (enabled by passin `-k` option to ansible command):
  - Creating directories for Cassandra data and logs.
  - Adjusting some kernel parameters for performance.
  - Updating `telegraf` configuration if monitoring is enabled.
- Generation of configuration files for Cassandra and Docker based on variables (in `group_vars/all.yml` and their overrides).
  - These config files are generated on a local host in a `cassandra_cluster/.cache/` folder.
  - Configs are extracted from Cassandra distribution and then patched with necessary overrides.
- If monitoring is enabled (`use_monitoring` variable), then JAR file for Jolokia is downloaded to local host (same `.cache/` folder).
- On each cluster host:
  - Directories are created at a location specified by `deploy_folder` variable.
  - Configuration files are copied from `.cache/` to that location, or some subdirectory.
- If monitoring is enabled:
  - Jolokia JAR file is also copied to each host.


## Bootstrapping the cluster

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


## Ansible playbooks

Here are existing playbooks that are used to perform above tasks.

### site-init.yaml

This playbook performs one-time initialization of the host.
It needs to be run once for every new node, but can be executed again if any changes are made to any tasks.
It requires `sudo` on remote hosts for at least some tasks so it needs to be executed with `-K` option, which will prompt for a password, e.g.:

    ansible-playbook -i <inventory> -K site-init.yml

### site.yaml

This playbook configures each node:

- Downloads and updates Cassandra configuration files.
- Downloads and updates jolokia plugin if needed.
- Copies all config files to remote nodes.
- Copies docker-compose file to remote nodes.

All files are installed in sub-directories in user home directory, no `sudo` access is needed:

    ansible-playbook -i <inventory> site.yml


### up.yaml

This playbook starts Cassandra cluster, bringing up seed nodes first:

    ansible-playbook -i <inventory> up.yml


### down.yaml

This playbook stops Cassandra cluster in a very clean way:

- Drains each Cassandra node (`nodetool drain`).
- Stops compaction (`nodetool stop`).
- Shuts down servers (`nodetool stopdaemon`).
- Stops docker containers.


### accounts.yaml

Initially Cassandra cluster is initialized with one super-user account (with a well-known password) and an anonymous account.
This playbook creates new super-user account, then disables old super-user and anonymous accounts, and creates a new user account using credentials from the Vault.
This playbook needs to be executed once after creating new cluster.


### nodetool.yaml

This playbook executes arbitrary `nodetool` commands on each node.
The command to execute is passed via `cmd` variable (which needs extra quoting if it contains spaces):

    ansible-playbook -i <inventory> -e cmd=info nodetool.yml

Here is how to quote command in case of extra parameters:

    ansible-playbook -i <inventory> -e cmd='"clearsnapshot --all"' nodetool.yml
