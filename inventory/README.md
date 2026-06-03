Inventories
===========

This folder contains Ansible inventory files, currently there is one inventory file per Cassandra cluster.
The inventories define hosts that are included into cluster and a number of variables either for the whole cluster or individual hosts.

Each inventory must define unique group for the cluster (e.g. `apdb_prod` in `apdb_prod.yaml` inventory).
This group name is used to specialize other variables in a matching file in `cassandra_cluster/group_vars/` directory.
As an example `apdb_prod` group will load variables from `cassandra_cluster/group_vars/apdb_prod.yaml` file in addition to `cassandra_cluster/group_vars/all.yaml`.

In addition to top-level group the inventories define rack groups, even though right now we only have one rack in each inventory.
Top-level group defines `node_datacenter` variable, and its children rack group(s) define `node_rack` variables which are Cassandra datacenter name and rack names.

One or more hosts in inventory have to be chose as seed node, this is done by `cassandra_seed: true` variable for them.
For small cluster with one to three nodes its reasonable to have just a single seed node, larger clusters should use two seed nodes.

When restoring a new cluster from the old cluster backup using `medusa-restore` playbook the hosts should define per-host `restore_from` variable.
Check README from `medusa_restore` role for an example.
