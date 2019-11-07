#!/bin/bash

user=$1
hbafile=$(psql -At -c 'SHOW hba_file')

if [ "$USER" != "postgres" ]; then
	echo should be run as postgres user
	exit -1
fi

echo "local all '${user}' peer" >> $hbafile
createuser -w -s "${user}"



