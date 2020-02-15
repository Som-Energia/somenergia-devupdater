#!/bin/bash

export SANDBOX=~/sandbox
export VIRTUALENV=~/.virtualenvs/blamer

source $VIRTUALENV/bin/activate

cd $SANDBOX/somenergia-devupdater

source cron.config # Has EMILI_FROM and EMILI_TO
export EMILI_CONFIG=$SANDBOX/somenergia-devupdater/dbconfig.py
export REPORTRUN="$VIRTUALENV/bin/reportrun -t $EMILI_TO"
export REMOTEPORT=2200 # for testing tomatic.remote
export PYTHONPATH=$SANDBOX/erp/server/sitecustomize/

EXECUTION_TIMESTAMP="$(date +'%Y-%m-%d-%H-%M-%S')"
echo Checking at $EXECUTION_TIMESTAMP | tee lastrun

eval `ssh-agent -s` 
ssh-add
./pidfile $VIRTUALENV/shameonyou.pid $REPORTRUN -s "CI" results.yaml -- ./teeall lastoutput python ./update.py --execname "$EXECUTION_TIMESTAMP" "$@"

kill $SSH_AGENT_PID

exit 0
