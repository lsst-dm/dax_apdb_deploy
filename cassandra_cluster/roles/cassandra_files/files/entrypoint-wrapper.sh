#!/bin/sh

set -e

# Copy our local config to standard location (cp may fail, just overwrite)
cat /cassandra_yaml > $CASSANDRA_CONF/cassandra.yaml

# Call entryypoint, location of the script is from Cassandra Dockerfile.
exec /usr/local/bin/docker-entrypoint.sh "$@"
