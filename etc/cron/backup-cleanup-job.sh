#!/bin/bash
#
# Script to run daily cleanups for APDB backups.
#

usage() {
    cat << EOF

Usage: $0 [options] inventory

    inventory is the name of the inventory file.

Available options:

    -h       Print help information
    -d NUM   Number of daily backups to keep, 0 to keep all.
    -w NUM   Number of weekly backups to keep, 0 to keep all.
    -m NUM   Number of monthly backups to keep, 0 to keep all.
    -l       List backups after cleanup.

EOF
}

keep_daily=10
keep_weekly=8
keep_monthly=12
list="no"

while getopts hd:w:m:l opt; do
    case $opt in
        h) usage; exit;;
        d) keep_daily=$OPTARG;;
        w) keep_weekly=$OPTARG;;
        m) keep_monthly=$OPTARG;;
        l) list="yes";;
        \?) usage >&2; exit 1;;
    esac
done

shift $(($OPTIND - 1))
if [ $# -ne 1 ]; then
    (echo "ERROR: expecting a sinle positional arguments."; usage)>&2
    exit 1
fi

inventory="$1"

# Find location of the dax_apdb_deploy.
cd $(dirname $(dirname $(dirname $(readlink -fn $0))))

source setup.sh

# Get the list of backups, we only delete successful backups.
backups_json=$(medusa-backup -i "$inventory" show-backups --json | jq 'map(select(.status == "SUCCESS"))')
#echo $backups_json

# Select backups to delete.
delete_daily=""
if [ $keep_daily -gt 0 ]; then
    delete_daily=$(echo "$backups_json" | \
        jq -r 'map(select(.name | test("^daily-[0-9T]+Z$"))) | sort_by(.start_time) | .[].name' |\
        head -n -$keep_daily)
fi
echo Daily backups to delete: $delete_daily

delete_weekly=""
if [ $keep_weekly -gt 0 ]; then
    delete_weekly=$(echo "$backups_json" | \
        jq -r 'map(select(.name | test("^weekly-[0-9T]+Z$"))) | sort_by(.start_time) | .[].name' |\
        head -n -$keep_weekly)
fi
echo Weekly backups to delete: $delete_weekly

delete_monthly=""
if [ $keep_monthly -gt 0 ]; then
    delete_monthly=$(echo "$backups_json" | \
        jq -r 'map(select(.name | test("^monthly-[0-9T]+Z$"))) | sort_by(.start_time) | .[].name' |\
        head -n -$keep_monthly)
fi
echo Monthly backups to delete: $delete_monthly

echo

# Delete now.
for backup in $delete_daily $delete_monthly $delete_weekly; do
    echo "NOT deleting backup $backup"
    echo command: medusa-backup -i "$inventory" delete-backup "$backup"
done

# And list backups.
if [ $list == "yes" ]; then
    echo
    echo Remaining backups:
    medusa-backup -i "$inventory" show-backups
fi
