#!/bin/bash

user=$1

if [ "$USER" != "postgres" ]; then
	echo should be run as postgres user
	exit -1
fi

echo "local all '${user}' peer" >> /etc/postgresql/*/main/pg_hba.conf
createuser -w -s "${user}"



