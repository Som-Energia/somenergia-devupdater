#!/bin/bash

export SANDBOX=~/sandbox
export VIRTUALENV=~/.virtualenvs/blamer

source $VIRTUALENV/bin/activate
source cron.config # Has EMILI_FROM and EMILI_TO

export EMILI_CONFIG=$SANDBOX/somenergia-devupdater/dbconfig.py
export REPORTRUN="$VIRTUALENV/bin/reportrun -t $EMILI_TO"
export REMOTEPORT=2200 # for testing tomatic.remote
export PYTHONPATH=$SANDBOX/erp/server/sitecustomize/

cd $SANDBOX/somenergia-devupdater

echo Checking at $(date +"%Y-%m-%d-%H-%M-%S" ) | tee lastrun

eval `ssh-agent -s` 
ssh-add
./pidfile $VIRTUALENV/shameonyou.pid $REPORTRUN --always -s "CI" results.yaml -- ./teeall lastoutput python ./update.py "$@"

kill $SSH_AGENT_PID

exit 0
