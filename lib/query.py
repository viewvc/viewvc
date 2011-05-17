#!/usr/bin/env python
# -*-python-*-
#
# Copyright (C) 1999-2010 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.org/license-1.html.
#
# For more information, visit http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# CGI script to process and display queries to CVSdb
#
# This script is part of the ViewVC package. More information can be
# found at http://viewvc.org
#
# -----------------------------------------------------------------------

import os
import sys
import string
import time

import cvsdb
import viewvc
import ezt
import debug
import urllib
import fnmatch

class FormData:
    def __init__(self, form):
        self.valid = 0
        
        self.repository = ""
        self.branch = ""
        self.directory = ""
        self.file = ""
        self.who = ""
        self.sortby = ""
        self.date = ""
        self.hours = 0

        self.decode_thyself(form)
        
    def decode_thyself(self, form):
        try:
            self.repository = string.strip(form["repository"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
        
        try:
            self.branch = string.strip(form["branch"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.directory = string.strip(form["directory"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.file = string.strip(form["file"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.who = string.strip(form["who"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.sortby = string.strip(form["sortby"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        
        try:
            self.date = string.strip(form["date"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        
        try:
            self.hours = int(form["hours"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        except ValueError:
            pass
        else:
            self.valid = 1
        
## returns a tuple-list (mod-str, string)
def listparse_string(str):
    return_list = []

    cmd = ""
    temp = ""
    escaped = 0
    state = "eat leading whitespace"

    for c in str:
        ## handle escaped charactors
        if not escaped and c == "\\":
            escaped = 1
            continue

        ## strip leading white space
        if state == "eat leading whitespace":
            if c in string.whitespace:
                continue
            else:
                state = "get command or data"

        ## parse to '"' or ","
        if state == "get command or data":

            ## just add escaped charactors
            if escaped:
                escaped = 0
                temp = temp + c
                continue

            ## the data is in quotes after the command
            elif c == "\"":
                cmd = temp
                temp = ""
                state = "get quoted data"
                continue

            ## this tells us there was no quoted data, therefore no
            ## command; add the command and start over
            elif c == ",":
                ## strip ending whitespace on un-quoted data
                temp = string.rstrip(temp)
                return_list.append( ("", temp) )
                temp = ""
                state = "eat leading whitespace"
                continue

            ## record the data
            else:
                temp = temp + c
                continue
                
        ## parse until ending '"'
        if state == "get quoted data":
            
            ## just add escaped charactors
            if escaped:
                escaped = 0
                temp = temp + c
                continue

            ## look for ending '"'
            elif c == "\"":
                return_list.append( (cmd, temp) )
                cmd = ""
                temp = ""
                state = "eat comma after quotes"
                continue

            ## record the data
            else:
                temp = temp + c
                continue

        ## parse until ","
        if state == "eat comma after quotes":
            if c in string.whitespace:
                continue

            elif c == ",":
                state = "eat leading whitespace"
                continue

            else:
                print "format error"
                sys.exit(1)

    if cmd or temp:
        return_list.append((cmd, temp))

    return return_list

def decode_command(cmd):
    if cmd == "r":
        return "regex"
    elif cmd == "l":
        return "like"
    else:
        return "exact"

def form_to_cvsdb_query(cfg, form_data):
    query = cvsdb.CreateCheckinQuery()
    query.SetLimit(cfg.cvsdb.row_limit)

    if form_data.repository:
        for cmd, str in listparse_string(form_data.repository):
            cmd = decode_command(cmd)
            query.SetRepository(str, cmd)
        
    if form_data.branch:
        for cmd, str in listparse_string(form_data.branch):
            cmd = decode_command(cmd)
            query.SetBranch(str, cmd)
        
    if form_data.directory:
        for cmd, str in listparse_string(form_data.directory):
            cmd = decode_command(cmd)
            query.SetDirectory(str, cmd)

    if form_data.file:
        for cmd, str in listparse_string(form_data.file):
            cmd = decode_command(cmd)
            query.SetFile(str, cmd)

    if form_data.who:
        for cmd, str in listparse_string(form_data.who):
            cmd = decode_command(cmd)
            query.SetAuthor(str, cmd)

    if form_data.sortby == "author":
        query.SetSortMethod("author")
    elif form_data.sortby == "file":
        query.SetSortMethod("file")
    else:
        query.SetSortMethod("date")

    if form_data.date:
        if form_data.date == "hours" and form_data.hours:
            query.SetFromDateHoursAgo(form_data.hours)
        elif form_data.date == "day":
            query.SetFromDateDaysAgo(1)
        elif form_data.date == "week":
            query.SetFromDateDaysAgo(7)
        elif form_data.date == "month":
            query.SetFromDateDaysAgo(31)
            
    return query

def prev_rev(rev):
    '''Returns a string representing the previous revision of the argument.'''
    r = string.split(rev, '.')
    # decrement final revision component
    r[-1] = str(int(r[-1]) - 1)
    # prune if we pass the beginning of the branch
    if len(r) > 2 and r[-1] == '0':
        r = r[:-2]
    return string.join(r, '.')

def is_forbidden(cfg, cvsroot_name, module):
    '''Return 1 if MODULE in CVSROOT_NAME is forbidden; return 0 otherwise.'''

    # CVSROOT_NAME might be None here if the data comes from an
    # unconfigured root.  This interfaces doesn't care that the root
    # isn't configured, but if that's the case, it will consult only
    # the base and per-vhost configuration for authorizer and
    # authorizer parameters.
    if cvsroot_name:
        authorizer, params = cfg.get_authorizer_and_params_hack(cvsroot_name)
    else:
        authorizer = cfg.options.authorizer
        params = cfg.get_authorizer_params()
        
    # If CVSROOT_NAME isn't configured to use an authorizer, nothing
    # is forbidden.  If it's configured to use something other than
    # the 'forbidden' authorizer, complain.  Otherwise, check for
    # forbiddenness per the PARAMS as expected.
    if not authorizer:
        return 0
    if authorizer != 'forbidden':    
        raise Exception("The 'forbidden' authorizer is the only one supported "
                        "by this interface.  The '%s' root is configured to "
                        "use a different one." % (cvsroot_name))
    forbidden = params.get('forbidden', '')
    forbidden = map(string.strip, filter(None, string.split(forbidden, ',')))
    default = 0
    for pat in forbidden:
        if pat[0] == '!':
            default = 1
            if fnmatch.fnmatchcase(module, pat[1:]):
                return 0
        elif fnmatch.fnmatchcase(module, pat):
            return 1
    return default
    
def build_commit(server, cfg, desc, files, cvsroots, viewvc_link):
    ob = _item(num_files=len(files), files=[])
    ob.log = desc and string.replace(server.escape(desc), '\n', '<br />') or ''

    for commit in files:
        repository = commit.GetRepository()
        directory = commit.GetDirectory()
        cvsroot_name = cvsroots.get(repository)

        ## find the module name (if any)
        try:
            module = filter(None, string.split(directory, '/'))[0]
        except IndexError:
            module = None

        ## skip commits we aren't supposed to show
        if module and ((module == 'CVSROOT' and cfg.options.hide_cvsroot) \
                       or is_forbidden(cfg, cvsroot_name, module)):
            continue

        ctime = commit.GetTime()
        if not ctime:
            ctime = "&nbsp;"
        else:
          if (cfg.options.use_localtime):
            ctime = time.strftime("%y/%m/%d %H:%M %Z", time.localtime(ctime))
          else:
            ctime = time.strftime("%y/%m/%d %H:%M", time.gmtime(ctime)) \
                    + ' UTC'
        
        ## make the file link
        try:
            file = (directory and directory + "/") + commit.GetFile()
        except:
            raise Exception, str([directory, commit.GetFile()])

        ## If we couldn't find the cvsroot path configured in the
        ## viewvc.conf file, or we don't have a VIEWVC_LINK, then
        ## don't make the link.
        if cvsroot_name and viewvc_link:
            flink = '[%s] <a href="%s/%s?root=%s">%s</a>' % (
                    cvsroot_name, viewvc_link, urllib.quote(file),
                    cvsroot_name, file)
            if commit.GetType() == commit.CHANGE:
                dlink = '%s/%s?root=%s&amp;view=diff&amp;r1=%s&amp;r2=%s' % (
                    viewvc_link, urllib.quote(file), cvsroot_name,
                    prev_rev(commit.GetRevision()), commit.GetRevision())
            else:
                dlink = None
        else:
            flink = '[%s] %s' % (repository, file)
            dlink = None

        ob.files.append(_item(date=ctime,
                              author=commit.GetAuthor(),
                              link=flink,
                              rev=commit.GetRevision(),
                              branch=commit.GetBranch(),
                              plus=int(commit.GetPlusCount()),
                              minus=int(commit.GetMinusCount()),
                              type=commit.GetTypeString(),
                              difflink=dlink,
                              ))

    return ob

def run_query(server, cfg, form_data, viewvc_link):
    query = form_to_cvsdb_query(cfg, form_data)
    db = cvsdb.ConnectDatabaseReadOnly(cfg)
    db.RunQuery(query)

    commit_list = query.GetCommitList()
    if not commit_list:
        return [ ], 0

    row_limit_reached = query.GetLimitReached()

    commits = [ ]
    files = [ ]

    cvsroots = {}
    viewvc.expand_root_parents(cfg)
    rootitems = cfg.general.svn_roots.items() + cfg.general.cvs_roots.items()
    for key, value in rootitems:
        cvsroots[cvsdb.CleanRepository(value)] = key

    current_desc = commit_list[0].GetDescription()
    for commit in commit_list:
        desc = commit.GetDescription()
        if current_desc == desc:
            files.append(commit)
            continue

        commits.append(build_commit(server, cfg, current_desc, files,
                                    cvsroots, viewvc_link))

        files = [ commit ]
        current_desc = desc

    ## add the last file group to the commit list
    commits.append(build_commit(server, cfg, current_desc, files,
                                cvsroots, viewvc_link))

    # Strip out commits that don't have any files attached to them.  The
    # files probably aren't present because they've been blocked via
    # forbiddenness.
    def _only_with_files(commit):
        return len(commit.files) > 0
    commits = filter(_only_with_files, commits)
  
    return commits, row_limit_reached

def main(server, cfg, viewvc_link):
  try:

    form = server.FieldStorage()
    form_data = FormData(form)

    if form_data.valid:
        commits, row_limit_reached = run_query(server, cfg,
                                               form_data, viewvc_link)
        query = None
    else:
        commits = [ ]
        row_limit_reached = 0
        query = 'skipped'

    docroot = cfg.options.docroot
    if docroot is None and viewvc_link:
        docroot = viewvc_link + '/' + viewvc.docroot_magic_path
        
    data = ezt.TemplateData({
      'cfg' : cfg,
      'address' : cfg.general.address,
      'vsn' : viewvc.__version__,
      'repository' : server.escape(form_data.repository),
      'branch' : server.escape(form_data.branch),
      'directory' : server.escape(form_data.directory),
      'file' : server.escape(form_data.file),
      'who' : server.escape(form_data.who),
      'docroot' : docroot,
      'sortby' : form_data.sortby,
      'date' : form_data.date,
      'query' : query,
      'row_limit_reached' : ezt.boolean(row_limit_reached),
      'commits' : commits,
      'num_commits' : len(commits),
      'rss_href' : None,
      'hours' : form_data.hours and form_data.hours or 2,
      })

    # generate the page
    server.header()
    template = viewvc.get_view_template(cfg, "query")
    template.generate(server.file(), data)

  except SystemExit, e:
    pass
  except:
    exc_info = debug.GetExceptionData()
    server.header(status=exc_info['status'])
    debug.PrintException(server, exc_info) 

class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
