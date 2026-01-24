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
hosts=$(ansible-inventory $inventories --list | jq -r '._meta.hostvars | to_entries | .[] | .value.ansible_host' | sort -u | tr '\n' ' ')

# Command to execute for checking
cmd="for h in $hosts; do nc -zw1 \$h 9042; echo \$h:\$?; done"
if [ -z "$host" ]; then
    output=$(bash -c "$cmd")
else
    output=$(ssh -x $host "$cmd")
fi


influx_line_format() {
    # Parse results and format as influxdb line format
    time_ns="$(date +%s)000000000"
    echo "# DML"
    echo "# CONTEXT-DATABASE: $db"
    for node_result in $*; do
        node_result=(${node_result/:/ })
        host_name=${node_result[0]}
        status="0"
        [ ${node_result[1]} = "0" ] && status="1"
        echo "$measurement,host=$host_name can_connect=$status $time_ns"
    done
}

influx_line_format $output | ~/bin/influx-v1 -host $influxdb -database $db -import -path /dev/stdin > /dev/null
