#!/bin/bash
#
# Script to run daily backups of APDB Cassandra cluster.
#

usage() {
    cat << EOF

Usage: $0 [options] inventory

    inventory is the name of the inventory file.

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
if [ $# -eq 0 ]; then
    (echo "ERROR: Mising required argument."; usage)>&2
    exit 1
fi
if [ $# -gt 1 ]; then
    (echo "ERROR: Extra arguments on command line."; usage)>&2
    exit 1
fi

inventory="$1"

# Find location of the dax_apdb_deploy.
cd $(dirname $(dirname $(dirname $(readlink -fn $0))))

source setup.sh

# Make backup, do not waitt to finish.
name="daily-$(date --utc +%Y%m%dT%H%M%SZ)"
medusa-backup -i "$inventory" make-backup --name="$name" $async

# And list backups.
if [ $list == "yes" ]; then
    medusa-backup -i "$inventory" show-backups
fi
