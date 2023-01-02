# -*-python-*-
#
# Copyright (C) 1999-2023 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

import sys
from subprocess import Popen, PIPE, STDOUT


class CommandReadPipe:
    def __init__(self, cmd, args, is_text=False, capture_err=True):
        self._eof = False
        self._process = Popen(
            (cmd,) + tuple(args),
            universal_newlines=is_text,
            stdout=PIPE,
            stderr=(capture_err and STDOUT or None),
            close_fds=(sys.platform != "win32"),
        )

    def _eofcheck(self, buf):
        if not buf:
            self._eof = True
        return buf

    def read(self, len=0):
        return self._eofcheck(self._process.stdout.read(len))

    def readline(self):
        return self._eofcheck(self._process.stdout.readline())

    def readlines(self):
        return self._eofcheck(self._process.stdout.readlines())

    def eof(self):
        return self._eof

    def close(self):
        if self._process:
            status = self._process.poll()
            if status is None:
                self._process.kill()

    def __del__(self):
        self.close()


def popen(cmd, args, is_text=False, capture_err=True):
    return CommandReadPipe(cmd, args, is_text, capture_err)
