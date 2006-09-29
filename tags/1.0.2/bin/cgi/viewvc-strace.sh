#!/bin/sh
#
# Set this script up with something like:
#
#   ScriptAlias /viewvc-strace /home/gstein/src/viewvc/cgi/viewvc-strace.sh
#
thisdir="`dirname $0`"
exec strace -q -r -o /tmp/v-strace.log "${thisdir}/viewvc.cgi"
