# dax_apdb_deploy package

This package implements management tools for installing and managing Cassandra clusters used by APDB.
Most of the functionality of this package is based on [Ansible](https://docs.ansible.com/) automation system.


## Initialization

Before using this package one needs to perform a one-time initialization:
- create Python virtual environment in `_venv` directory inside current folder,
- install `ansible` package and its dependencies,
- install necessary Ansible collections defined in `requirements.yml`.

All these steps are executed by running `make setup` which uses `Makefile` in the top-level package folder.

NOTE: at this time some dependencies cannot use Python 3.13, 3.12 should be used instead.

Every new shell will need to activate the virtual environment and set up some environment variables with this command:

    . ./setup.sh


## Ansible inventories

Ansible inventory is a collection of hosts, or groups of hosts, with additional metadata attached.
Each Cassandra cluster is defined in a separate inventory file with the name starting with `inventory` and followed by cluster name, e.g. `inventory-apdb_int.yaml`.
Inventories are located in the top level directory of this package.

Execution of ansible playbooks requires passing the name of the inventory file, e.g.:

    ansible-playbook -i inventory/apdb_dev.yaml cassandra_cluster/site.yml

One can limit the set of nodes with `-l` option, e.g.:

    ansible-playbook -i inventory/apdb_dev.yaml -l sdfk8sk012 cassandra_cluster/site.yaml

Some ansible variables will be specific to a cluster.
Defaults for this variables are set in the file `cassandra_cluster/group_vars/all.yml`.
Cluster-specific overrides for these variables appear in the file `cassandra_cluster/group_vars/<cluster_name>.yml`.

## User accounts

Cassandra services run from a special service account (`rubincas`) on each cluster host.
Kerberos authentication is used for connecting to cluster nodes via SSH:
- user executing Ansible roles needs to have their principal added to `~rubincas/.k5login` on each node (message `usdf-help`),
- user need to have a valid Kerberos token by executing `kinit`.

Some Ansible roles require `root` privileges, but `rubincas` is not allowed to `sudo`.
To execute such role the user needs to use their own account and be granted `sudo` privileges.

To run Ansible role from user account with sudo one adds `--ask-become-pass --user $USER` and optionally `--ask-pass` options to Ansible commands (or short options `-K -u $USER` and `-k`).
Cluster nodes do not have home directories for regular users, but it is possible to create them under existing `/sdf/home` folder and add `.k5login` file to avoid using `--ask-pass` options.


## Deployment model

Deployment of Cassandra on a cluster of hosts includes:

- One time setup of each host, this typically requires `sudo` on remote host:
  - Creating directories for Cassandra data and logs.
  - Adjusting some kernel parameters for performance.
  - Updating `telegraf` configuration if monitoring is enabled.
- Generation of configuration files for Cassandra and Docker based on variables (in `group_vars/all.yml` and their overrides).
  - These config files are generated on a local host in a `cassandra_cluster/.cache/` folder.
  - Configs are extracted from Cassandra distribution and then patched with necessary overrides.
- If monitoring is enabled (`use_monitoring` variable), then JAR file for Jolokia is downloaded to local host (same `.cache/` folder).
- On each cluster host:
  - Directories are created at a location specified by `deploy_folder` and `deploy_folder_docker` variables.
  - Configuration files are copied from `.cache/` to that location, or some subdirectory.
- If monitoring is enabled:
  - Jolokia JAR file is also copied to each host.


## Bootstrapping the cluster

Very first start of the multi-node cluster needs special care:

- The nodes have to be brought up one at a time to avoid conflicts in token allocation.
- Seed nodes have to be brought up first.
- If authentication is enabled (should be true for any reasonable setup):
  - Using default initial credentials (`cassandra`/`cassandra`) create new super-user account.
  - Using new super-user account delete default `cassandra` account.
  - Create an additional non-super-user account and allowing it to create keyspaces.

To serialize startup of the seed nodes we need to know when the node is actually up before starting another one.
The easiest way to do that is to probe native client port `9042` and wait until it responds (with a reasonable timeout).


## Ansible playbooks

The `cassandra_cluster` directory contains a number of playbooks for cluster management.
See `cassandra_cluster/README.md` for their detailed description.

Here are examples of management procedures that use playbooks.


### Bootstrapping a new cluster

After creating a new inventory file (e.g. `cluster.yaml`) and corresponding group vars (in `cassandra_cluster/group_vars/cluster.yml`) this sequence of commands can be executed:

    # Create data directories on all nodes.
    $ ansible-playbook -i inventory/cluster.yaml -u $USER -K cassandra_cluster/site-init.yml
    # Install deployment tools.
    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/site.yml
    # Start the cluster.
    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/bootstrap.yml
    # Create new Cassandra accounts.
    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/accounts.yml


### Stopping cluster gracefully

    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/down.yml


### Bringing cluster up

    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/up.yml


### Rolling restart of Cassandra services

    $ ansible-playbook -i inventory/cluster.yaml cassandra_cluster/rolling-restart.yml


## Executing shell commands

The `ansible-pssh` script can be used to execute arbitrary shell commands on remote nodes.
It uses Ansible inventory to determine which hosts to use for execution.
An example of running a simple command on all hosts:

    ansible-pssh -i inventory/apdb_dev.yaml "ls -l"

A `-d` option can be used to change current working directory to the location of docker-compose configuration, and it also needs `--playbook-dir` option:

    ansible-pssh -i inventory/apdb_dev.yaml -d --playbook-dir=cassandra_cluster "docker compose ps"

A `-1` option can be specified to limit execution to a single host, first in the inventory list:

    ansible-pssh -i inventory/apdb_dev.yaml -d --playbook-dir=cassandra_cluster -1 "./nodetool status"

By default `ansible-pssh` waits until execution of all commands completes to print their output.
A `-f` option can be used to print output of the remote commands as soon as it appears, prefixing each line with the remote host name.


## Making backups

The `medusa-backup` script is used to manage Cassandra backups.
It is implemented on top of [cassandra-medusa](https://github.com/thelastpickle/cassandra-medusa) and uses Ansible inventory to determine the set of hosts in a cluster.
In current setup `cassandra-medusa` runs as gRPC service on each node in a cluster, and `medusa-backup` sends commands to these services.

Backups are stored in S3 bucket, its location is determined by the configuration file in `cassandra_cluster/roles/medusa_configs` role.

To list existing backups:

    medusa-backup -i inventory/apdb_dev.yaml show-backups

To create a new backup (`-a` is for async mode):

    medusa-backup -i inventory/apdb_dev.yaml make-backup -a

To delete a backup:

    medusa-backup -i inventory/apdb_dev.yaml delete-backup <backup-name>


## Restoring backups

The `medusa-restore` playbook can be used to restore the full cluster or one or more nodes.
This playbook does a complete restore of all keyspaces, there is no option for selective restore of a keyspace or a table.
The services have to be stopped before restore can start and data directory must exist (created with `site-init` playbook).

The name of a backup to restore is passed as a variable.
If `medusa` service is not running it is possible to lookup backup names in S3 bucket which hosts backups.

An example of full cluster restore:

    ansible-playbook -i <inventory> -e backup_name=backup-20251014 medusa-restore.yml

Single-node restore can be done by limiting set of nodes with `-l` option:

    ansible-playbook -i <inventory> -l sdfk8sk007 -e backup_name=backup-20251014 medusa-restore.yml


## Backups with dsbulk

In addition to `cassandra-medusa`-based backups there is an option to dump contents of the Cassandra tables in CSV format and restore the tables later.
This approach uses [dsbulk tool](https://docs.datastax.com/en/dsbulk/overview/dsbulk-about.html) from DataStax.
The speed of dump/restore with `dsbulk` is significantly lower than that of `cassandra-medusa`, but it provides more flexibility.
In particular, `dsbulk` is the only option for restoring data into a cluster of different topology.

A wrapper script in `bin/clone-keyspace` implements a number of options to simplify common operations:
- selection of the tables to dump/restore,
- bundling all dumped tables and metadata into a single tarball or a ZIP archive,
- uploading dumped data to an S3 bucket.

The volume of the data produced by dump operation can be very high, to store intermediate results a temporary location with sufficient free space will be needed.

An example of dumping all `DiaObject*` tables to a ZIP archive on S3:

    clone-keyspace -i inventory/apdb_dev.yaml --use-vault dump-keyspace \
       -t 'DiaObject*' -j 4 -b zip --tmp-dir /sdf/scratch/rubin/apdb/... \
       keyspace s3://profile@bucket/archives/DiaObject-20260701.zip

As the other tools in this package `clone-keyspace` uses Ansible configuration for cluster-specific information.
The `-i` option specifies an inventory file for Cassandra cluster.
The `--use-vault` option will read Cassandra password from the Hashi Vault using path configured in Ansible.
Uploading files to an S3 bucket requires credentials being setup in `~/.lsst/aws-credentials.ini`.

In addition to compressed CSV files the dump includes two additional files:
- `schema.json` with the schema of the dumped tables,
- `manifest.txt` with the list of the files produced by the command.

These files are used to restore the tables into an active Cassandra cluster.
The data to be restored need to be copied to a local directory and unpacked in advance.

And example of the restore command that restores a single table:

    clone-keyspace -i inventory/apdb_dev.yaml --use-vault load-keyspace \
      -t DiaObjectLast keyspace /sdf/scratch/rubin/apdb/some-directory

The restore operation can cause significant resource use on server side, it needs to be monitored.
If timeouts or errors happen during restore it is recommended to use `--max-concurrent-queries` option with a low setting (64 may be a good start).
It is also recommended to restore one table at a time, with some delay between tables to reduce stress on cluster.
