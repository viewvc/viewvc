# -*-python-*-
#
# Copyright (C) 1999-2025 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------

import os
import re
import tempfile
from io import BytesIO
from operator import attrgetter
import vclib
from . import rcsparse
from . import blame

# TODO: The functionality shared with bincvs should probably be moved
# to a separate module
from .bincvs import (
    BaseCVSRepository,
    Revision,
    Tag,
    _file_log,
    _log_path,
    _path_join,
)


class CCVSRepository(BaseCVSRepository):
    def dirlogs(self, path_parts, rev, entries, options):
        """see vclib.Repository.dirlogs docstring

        rev can be a tag name or None. if set only information from revisions
        matching the tag will be retrieved

        Option values recognized by this implementation:

          cvs_subdirs
            boolean. true to fetch logs of the most recently modified file in each
            subdirectory

        Option values returned by this implementation:

          cvs_tags, cvs_branches
            lists of tag and branch names encountered in the directory
        """
        if self.itemtype(path_parts, rev) != vclib.DIR:  # does auth-check
            raise vclib.Error("Path '%s' is not a directory." % (_path_join(path_parts)))
        entries_to_fetch = []
        for entry in entries:
            if vclib.check_path_access(self, path_parts + [entry.name], None, rev):
                entries_to_fetch.append(entry)

        subdirs = options.get("cvs_subdirs", 0)

        dirpath = self._getpath(path_parts)
        alltags = {"MAIN": "", "HEAD": "1.1"}  # all the tags seen in the files of this dir

        for entry in entries_to_fetch:
            entry.rev = entry.date = entry.author = None
            entry.dead = entry.absent = entry.log = entry.lockinfo = None
            path = _log_path(entry, dirpath, subdirs, self.path_encoding)
            if path:
                entry.path = path
                try:
                    rcsparse.parse(
                        open(self._getfspath(path), "rb"),
                        InfoSink(entry, rev, alltags, self.content_encoding),
                    )
                except IOError as e:
                    entry.errors.append("rcsparse error: %s" % e)
                except RuntimeError as e:
                    entry.errors.append("rcsparse error: %s" % e)
                except rcsparse.RCSStopParser:
                    pass

        branches = options["cvs_branches"] = []
        tags = options["cvs_tags"] = []
        for name, rev in alltags.items():
            if Tag(None, rev).is_branch:
                branches.append(name)
            else:
                tags.append(name)

    def itemlog(self, path_parts, rev, sortby, first, limit, options):
        """see vclib.Repository.itemlog docstring

        rev parameter can be a revision number, a branch number, a tag name,
        or None. If None, will return information about all revisions, otherwise,
        will only return information about the specified revision or branch.

        Option values returned by this implementation:

          cvs_tags
            dictionary of Tag objects for all tags encountered
        """
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % (_path_join(path_parts)))

        path = self.rcsfile(path_parts, 1)
        sink = TreeSink(self.content_encoding)
        rcsparse.parse(open(self._getfspath(path), "rb"), sink)
        filtered_revs = _file_log(
            list(sink.revs.values()), sink.tags, sink.lockinfo, sink.default_branch, rev
        )
        for rev in filtered_revs:
            if rev.prev and len(rev.number) == 2:
                rev.changed = rev.prev.next_changed
        options["cvs_tags"] = sink.tags

        # Both of Revision.date and Revision.number are sortable, not None
        if sortby == vclib.SORTBY_DATE:
            filtered_revs.sort(key=attrgetter("date", "number"), reverse=True)
        elif sortby == vclib.SORTBY_REV:
            filtered_revs.sort(key=attrgetter("number"), reverse=True)

        if len(filtered_revs) < first:
            return []
        if limit:
            return filtered_revs[first : (first + limit)]
        return filtered_revs

    def rawdiff(self, path_parts1, rev1, path_parts2, rev2, diff_type, options={}, is_text=True):
        if self.itemtype(path_parts1, rev1) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % (_path_join(path_parts1)))
        if self.itemtype(path_parts2, rev2) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % (_path_join(path_parts2)))

        fd1, temp1 = tempfile.mkstemp()
        os.fdopen(fd1, "wb").write(self.openfile(path_parts1, rev1, {})[0].getvalue())
        fd2, temp2 = tempfile.mkstemp()
        os.fdopen(fd2, "wb").write(self.openfile(path_parts2, rev2, {})[0].getvalue())

        r1 = self.itemlog(path_parts1, rev1, vclib.SORTBY_DEFAULT, 0, 0, {})[-1]
        r2 = self.itemlog(path_parts2, rev2, vclib.SORTBY_DEFAULT, 0, 0, {})[-1]

        info1 = (self.rcsfile(path_parts1, root=1, v=0), r1.date, r1.string)
        info2 = (self.rcsfile(path_parts2, root=1, v=0), r2.date, r2.string)

        diff_args = vclib._diff_args(diff_type, options)
        encoding = self.content_encoding if is_text else None

        return vclib._diff_fp(
            temp1, temp2, info1, info2, self.utilities.diff or "diff", diff_args, encoding=encoding
        )

    def annotate(self, path_parts, rev=None, include_text=False):
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % (_path_join(path_parts)))
        source = blame.BlameSource(
            self._getfspath(self.rcsfile(path_parts, 1)), rev, include_text, self.content_encoding
        )
        return source, source.revision

    def revinfo(self, rev):
        raise vclib.UnsupportedFeature

    def openfile(self, path_parts, rev, options):
        if self.itemtype(path_parts, rev) != vclib.FILE:  # does auth-check
            raise vclib.Error("Path '%s' is not a file." % (_path_join(path_parts)))
        path = self.rcsfile(path_parts, 1)
        sink = COSink(rev, self.content_encoding)
        rcsparse.parse(open(self._getfspath(path), "rb"), sink)
        revision = sink.last and sink.last.string
        return BytesIO(b"".join(sink.sstext.text)), revision


class MatchingSink(rcsparse.Sink):
    """Superclass for sinks that search for revisions based on tag or number"""

    def __init__(self, find, encoding):
        """Initialize with tag name or revision number string to match against"""
        if not find or find == "MAIN" or find == "HEAD":
            self.find = None
        else:
            self.find = find

        self.find_tag = None
        self.encoding = encoding

    def set_principal_branch(self, branch_number):
        if self.find is None:
            self.find_tag = Tag(None, self._to_str(branch_number))

    def define_tag(self, name, revision):
        if self._to_str(name) == self.find:
            self.find_tag = Tag(None, self._to_str(revision))

    def admin_completed(self):
        if self.find_tag is None:
            if self.find is None:
                self.find_tag = Tag(None, "")
            else:
                try:
                    self.find_tag = Tag(None, self.find)
                except ValueError:
                    pass

    def _to_str(self, b):
        if isinstance(b, bytes):
            return b.decode(self.encoding, "backslashreplace")
        return b


class InfoSink(MatchingSink):
    def __init__(self, entry, tag, alltags, encoding):
        MatchingSink.__init__(self, tag, encoding)
        self.entry = entry
        self.alltags = alltags
        self.matching_rev = None
        self.perfect_match = 0
        self.lockinfo = {}
        self.saw_revision = False

    def define_tag(self, name, revision):
        MatchingSink.define_tag(self, name, revision)
        self.alltags[self._to_str(name)] = self._to_str(revision)

    def admin_completed(self):
        MatchingSink.admin_completed(self)
        if self.find_tag is None:
            # tag we're looking for doesn't exist
            if self.entry.kind == vclib.FILE:
                self.entry.absent = 1
            raise rcsparse.RCSStopParser

    def parse_completed(self):
        if not self.saw_revision:
            self.entry.absent = 1

    def set_locker(self, rev, locker):
        self.lockinfo[self._to_str(rev)] = self._to_str(locker)

    def define_revision(self, revision, date, author, state, branches, next):
        self.saw_revision = True

        if self.perfect_match:
            return

        tag = self.find_tag
        rev = Revision(
            self._to_str(revision), date, self._to_str(author), self._to_str(state) == "dead"
        )
        rev.lockinfo = self.lockinfo.get(self._to_str(revision))

        # perfect match if revision number matches tag number or if
        # revision is on trunk and tag points to trunk.  imperfect match
        # if tag refers to a branch and either a) this revision is the
        # highest revision so far found on that branch, or b) this
        # revision is the branchpoint.
        perfect = (rev.number == tag.number) or (not tag.number and len(rev.number) == 2)
        if perfect or (
            tag.is_branch
            and (
                (
                    tag.number == rev.number[:-1]
                    and (not self.matching_rev or rev.number > self.matching_rev.number)
                )
                or (rev.number == tag.number[:-1])
            )
        ):
            self.matching_rev = rev
            self.perfect_match = perfect

    def set_revision_info(self, revision, log, text):
        if self.matching_rev:
            if self._to_str(revision) == self.matching_rev.string:
                self.entry.rev = self.matching_rev.string
                self.entry.date = self.matching_rev.date
                self.entry.author = self.matching_rev.author
                self.entry.dead = self.matching_rev.dead
                self.entry.lockinfo = self.matching_rev.lockinfo
                self.entry.absent = 0
                self.entry.log = self._to_str(log)
                raise rcsparse.RCSStopParser
        else:
            raise rcsparse.RCSStopParser


class TreeSink(rcsparse.Sink):
    d_command = re.compile(rb"^d(\d+)\s(\d+)")
    a_command = re.compile(rb"^a(\d+)\s(\d+)")

    def __init__(self, encoding):
        self.revs = {}
        self.tags = {}
        self.head = None
        self.default_branch = None
        self.lockinfo = {}
        self.encoding = encoding

    def set_head_revision(self, revision):
        self.head = self._to_str(revision)

    def set_principal_branch(self, branch_number):
        self.default_branch = self._to_str(branch_number)

    def set_locker(self, rev, locker):
        self.lockinfo[self._to_str(rev)] = self._to_str(locker)

    def define_tag(self, name, revision):
        # check !tags.has_key(tag_name)
        self.tags[self._to_str(name)] = self._to_str(revision)

    def define_revision(self, revision, date, author, state, branches, next):
        # check !revs.has_key(revision)
        self.revs[self._to_str(revision)] = Revision(
            self._to_str(revision), date, self._to_str(author), self._to_str(state) == "dead"
        )

    def set_revision_info(self, revision, log, text):
        # check revs.has_key(revision)
        rev = self.revs[self._to_str(revision)]
        rev.log = self._to_str(log)

        changed = None
        added = 0
        deled = 0
        if self.head != self._to_str(revision):
            changed = 1
            lines = text.split(b"\n")
            idx = 0
            while idx < len(lines):
                command = lines[idx]
                dmatch = self.d_command.match(command)
                idx = idx + 1
                if dmatch:
                    deled = deled + int(dmatch.group(2))
                else:
                    amatch = self.a_command.match(command)
                    if amatch:
                        count = int(amatch.group(2))
                        added = added + count
                        idx = idx + count
                    elif command:
                        raise vclib.Error(
                            "error while parsing deltatext: %s" % self._to_str(command)
                        )

        if len(rev.number) == 2:
            rev.next_changed = changed and "+%i -%i" % (deled, added)
        else:
            rev.changed = changed and "+%i -%i" % (added, deled)

    def _to_str(self, b):
        if isinstance(b, bytes):
            return b.decode(self.encoding, "backslashreplace")
        return b


def _msplit(s):
    r"""Split (bytes) S into an array of lines.

    Only \n is a line separator. The line endings are part of the lines."""

    lines = [line + b"\n" for line in s.split(b"\n")]
    if lines[-1] == b"\n":
        del lines[-1]
    else:
        lines[-1] = lines[-1][:-1]
    return lines


class StreamText:
    d_command = re.compile(rb"^d(\d+)\s(\d+)\n")
    a_command = re.compile(rb"^a(\d+)\s(\d+)\n")

    def __init__(self, text):
        self.text = _msplit(text)

    def command(self, cmd):
        start_line = None
        adjust = 0
        add_lines_remaining = 0
        diffs = _msplit(cmd)
        if len(diffs) == 0:
            return
        if diffs[0] == b"":
            del diffs[0]
        for command in diffs:
            if add_lines_remaining > 0:
                # Insertion lines from a prior "a" command
                # Note: Don't check if we insert a string which does not end
                # with b'\n' before an existing line. Some CVS implementation
                # can produce such edit commands.
                self.text.insert(start_line + adjust, command)
                add_lines_remaining = add_lines_remaining - 1
                adjust = adjust + 1
                continue
            dmatch = self.d_command.match(command)
            amatch = self.a_command.match(command)
            if dmatch:
                # "d" - Delete command
                start_line = int(dmatch.group(1))
                count = int(dmatch.group(2))
                begin = start_line + adjust - 1
                del self.text[begin : (begin + count)]
                adjust = adjust - count
            elif amatch:
                # "a" - Add command
                start_line = int(amatch.group(1))
                count = int(amatch.group(2))
                add_lines_remaining = count
            else:
                raise RuntimeError("Error parsing diff commands")


def secondnextdot(s, start):
    # find the position the second dot after the start index.
    return s.find(".", s.find(".", start) + 1)


class COSink(MatchingSink):
    def __init__(self, rev, encoding):
        MatchingSink.__init__(self, rev, encoding)

    def set_head_revision(self, revision):
        self.head = Revision(self._to_str(revision))
        self.last = None
        self.sstext = None

    def admin_completed(self):
        MatchingSink.admin_completed(self)
        if self.find_tag is None:
            raise vclib.InvalidRevision(self.find)

    def set_revision_info(self, revision, log, text):
        tag = self.find_tag
        rev = Revision(self._to_str(revision))

        if rev.number == tag.number:
            self.log = self._to_str(log)

        depth = len(rev.number)

        if rev.number == self.head.number:
            assert self.sstext is None
            self.sstext = StreamText(text)
        elif depth == 2 and tag.number and rev.number >= tag.number[:depth]:
            assert len(self.last.number) == 2
            assert rev.number < self.last.number
            self.sstext.command(text)
        elif (
            depth > 2
            and rev.number[: (depth - 1)] == tag.number[: (depth - 1)]
            and (rev.number <= tag.number or len(tag.number) == depth - 1)
        ):
            assert len(rev.number) - len(self.last.number) in (0, 2)
            assert rev.number > self.last.number
            self.sstext.command(text)
        else:
            rev = None

        if rev:
            self.last = rev
