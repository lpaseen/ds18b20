#!/bin/bash
#Purpose: make sure ds18b20 temp values are logged

# add this to cron by adding a line like
# * * * * * /home/pi/src/Log_temp_cron.sh

#make sure it only run once
(
    flock -n 42 || exit 0
    BINDIR="${0%/*}"
    CONFDIR=${BINDIR}
    DATADIR=${BINDIR}/data
    LOGDIR=${BINDIR}/logs
    echo "Starting a new process of ${BINDIR}/log_temp.py with pid PID=$$"
    # this script does not exit
    # it does read info once a minute
    unbuffer ${BINDIR}/log_temp.py --configfile=${CONFDIR}/config.ini --outfile=${DATADIR}/Log_temp-$(date +%Y).csv --statefile=${DATADIR}/Log_furnace-$(date +\%Y).csv 1>${LOGDIR}/Log_temp-$(date +%F_%H%M).log  2>&1
) 42>/run/lock/Log_temp_cron.lock
