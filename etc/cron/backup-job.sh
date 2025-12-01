#!/bin/bash
#
# Script to run daily backups of APDB Cassandra cluster.
#

usage() {
    cat << EOF

Usage: $0 [options] inventory prefix

    inventory is the name of the inventory file.
    prefix is a prefix for backup name, e.g. "daily", "weekly".

Available options:

    -h   Print help information
    -w   Wait until backup finishes.
    -l   List backups after making a new backup.

EOF
}

async="-a"
list="no"

while getopts hwl opt; do
    case $opt in
        h) usage; exit;;
        w) async="";;
        l) list="yes";;
        \?) usage >&2; exit 1;;
    esac
done

shift $(($OPTIND - 1))
if [ $# -ne 2 ]; then
    (echo "ERROR: expecting two positional arguments."; usage)>&2
    exit 1
fi

inventory="$1"
prefix="$2"

# Find location of the dax_apdb_deploy.
cd $(dirname $(dirname $(dirname $(readlink -fn $0))))

source setup.sh

# Make backup, do not waitt to finish.
name="${prefix}-$(date --utc +%Y%m%dT%H%M%SZ)"
echo "Making new backup $name"
medusa-backup -i "$inventory" make-backup --name="$name" $async

# And list backups.
if [ $list == "yes" ]; then
    echo
    medusa-backup -i "$inventory" show-backups
fi
