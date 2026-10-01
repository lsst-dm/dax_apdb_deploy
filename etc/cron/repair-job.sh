#!/bin/bash
#
# Script to run repairs of APDB Cassandra cluster.
#

usage() {
    cat << EOF

Usage: $0 [options] inventory [keyspace tables ...]

    inventory is the name of the inventory file.

Available options:

    -h   Print help information

EOF
}

while getopts h opt; do
    case $opt in
        h) usage; exit;;
        \?) usage >&2; exit 1;;
    esac
done

shift $(($OPTIND - 1))
if [ $# -eq 0 ]; then
    (echo "ERROR: expecting one or more positional arguments."; usage)>&2
    exit 1
fi

inventory="$1"
shift 1

# Find location of the dax_apdb_deploy.
cd $(dirname $(dirname $(dirname $(readlink -fn $0))))

source setup.sh

# Make backup, do not waitt to finish.
log="logs/repair-$(date +%Y%m%dT%H%M%S).log"
echo "Running repair job, log: $log"

ansible-pssh -i "$inventory" -d --randomize --serial --follow "./nodetool repair -pr -j 4 -- $*" |& \
    tee "$log" | \
    egrep '^[[].*[]]$'
