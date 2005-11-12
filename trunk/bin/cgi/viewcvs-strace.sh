#!/bin/sh
#
# Set this script up with something like:
#
#   ScriptAlias /viewcvs-strace /home/gstein/src/viewcvs/cgi/viewcvs-strace.sh
#
thisdir="`dirname $0`"
exec strace -q -r -o /tmp/v-strace.log "${thisdir}/viewcvs.cgi"
