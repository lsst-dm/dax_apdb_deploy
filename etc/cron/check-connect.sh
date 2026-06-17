#!/bin/bash
#
# Script to check connectivity for each cluster node.
#

host=""
port=9042
measurement="cassandra_port_live"
influxdb="pp-influxdb.sdf.slac.stanford.edu"
db=cassandra

usage() {
    cat << EOF

Usage: $0 [options] inventory [...]

    inventory is the name of the inventory file(s).

Available options:

    -h        Print help information
    -s host   Execute check on given node (via ssh).
    -p port   Port number to test (default: $port).
    -m name   Measurement name (default: $measurement).
    -i host   Host name for InfluxDB (default: $influxdb).
    -d db     InfluxDB database name (default: $db).

EOF
}

while getopts hs:p:m:i: opt; do
    case $opt in
        h) usage; exit;;
        s) host=$OPTARG;;
        p) port=$OPTARG;;
        m) measurement=$OPTARG;;
        i) influxdb=$OPTARG;;
        d) db=$OPTARG;;
        \?) usage >&2; exit 1;;
    esac
done

shift $(($OPTIND - 1))

inventories=""
for inventory in "$@"; do
    inventories="$inventories -i $inventory"
done
if [ -z "$inventories" ]; then
    (echo "ERROR: one or more inventories must be given."; usage)>&2
    exit 1
fi

# Find location of the dax_apdb_deploy.
cd $(dirname $(dirname $(dirname $(readlink -fn $0))))

source setup.sh

# Get the list of hosts.
hosts_and_tags=$(\
    ansible-inventory $inventories --list --vars --playbook-dir cassandra_cluster |\
    jq -r '._meta.hostvars | to_entries | .[] | .value | .ansible_host + ":" + .cluster_unique_id' |\
    sort -u | tr '\n' ' '\
)


for host_tag in $hosts_and_tags; do
    host_tag_array=(${host_tag/:/ })
    host_name=${host_tag_array[0]}
    tag=${host_tag_array[1]}

    cmd="nc -zw1 $host_name $port; echo \$?"
    if [ -z "$host" ]; then
        node_output=$(bash -c "$cmd")
    else
        node_output=$(ssh -x "$host" "$cmd")
    fi
    output="$output $host_name:$node_output:$tag"
done

influx_line_format() {
    # Parse results and format as influxdb line format
    time_ns="$(date +%s)000000000"
    echo "# DML"
    echo "# CONTEXT-DATABASE: $db"
    for node_result in $*; do
        node_result=(${node_result//:/ })
        host_name=${node_result[0]}
        tag=${node_result[2]}
        status="0"
        [ ${node_result[1]} = "0" ] && status="1"
        echo "$measurement,host=$host_name,apdb_cluster=$tag can_connect=$status $time_ns"
    done
}

influx_line_format $output | ~/bin/influx-v1 -host $influxdb -database $db -import -path /dev/stdin > /dev/null
