# This python script permits to test the behaviour of the tparse module.
import sink
import tparse
import sys
tparse.parse(sys.argv[1],sink.DebugSink())
