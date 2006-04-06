#!/usr/bin/python
# -*- Mode: python -*-
#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# CGI script to process and display queries to CVSdb
#
# This script is part of the ViewCVS package. More information can be
# found at http://www.lyra.org/viewcvs/.
#
# -----------------------------------------------------------------------
#

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

CONF_PATHNAME = None

#########################################################################

import os
import sys
import string
import cgi
import time

import cvsdb
import viewcvs
import ezt

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

def form_to_cvsdb_query(form_data):
    query = cvsdb.CreateCheckinQuery()

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

def cvsroot_name_from_path(cvsroot):
    ## we need to resolve the cvsroot path from the database
    ## to the name given to it in the viewcvs.conf file
    for key, value in cfg.general.cvs_roots.items():
        if value == cvsroot:
            return key

    return None

def build_commit(desc, files):
    ob = _item(num_files=len(files), files=[])
    
    if desc:
        ob.desc = string.replace(cgi.escape(desc), '\n', '<br>')
    else:
        ob.desc = '&nbsp;'

    for commit in files:
        dir_parts = filter(None, string.split(commit.GetDirectory(), '/'))
        if dir_parts \
               and ((dir_parts[0] == 'CVSROOT' and cfg.options.hide_cvsroot) \
                    or cfg.is_forbidden(dir_parts[0])):
            continue
        
        ctime = commit.GetTime()
        if not ctime:
            ctime = "&nbsp";
        else:
            ctime = time.strftime("%y/%m/%d %H:%M", time.localtime(ctime))

        ## make the file link
        file = os.path.join(commit.GetDirectory(), commit.GetFile())
        file_full_path = os.path.join(commit.GetRepository(), file)

        ## if we couldn't find the cvsroot path configured in the 
        ## viewcvs.conf file, then don't make the link
        cvsroot_name = cvsroot_name_from_path(commit.GetRepository())
        if cvsroot_name:
            flink = '<a href="viewcvs.cgi/%s?cvsroot=%s">%s</a>' \
                    % (file, cvsroot_name, file_full_path)
        else:
            flink = file_full_path

        ob.files.append(_item(date=ctime,
                              author=commit.GetAuthor(),
                              link=flink,
                              rev=commit.GetRevision(),
                              branch=commit.GetBranch(),
                              plus=int(commit.GetPlusCount()),
                              minus=int(commit.GetMinusCount()),
                              ))

    return ob

def run_query(form_data):
    query = form_to_cvsdb_query(form_data)
    db = cvsdb.ConnectDatabaseReadOnly()
    db.RunQuery(query)

    if not query.commit_list:
        return [ ]

    commits = [ ]
    files = [ ]

    current_desc = query.commit_list[0].GetDescription()
    for commit in query.commit_list:
        desc = commit.GetDescription()
        if current_desc == desc:
            files.append(commit)
            continue

        commits.append(build_commit(current_desc, files))

        files = [ commit ]
        current_desc = desc

    ## add the last file group to the commit list
    commits.append(build_commit(current_desc, files))

    return commits

def handle_config():
    viewcvs.handle_config()
    global cfg
    cfg = viewcvs.cfg

def main():
    handle_config()
    
    form = cgi.FieldStorage()
    form_data = FormData(form)

    if form_data.valid:
        commits = run_query(form_data)
        query = None
    else:
        commits = [ ]
        query = 'skipped'

    data = {
      'cfg' : cfg,
      'address' : cfg.general.address,
      'vsn' : viewcvs.__version__,

      'repository' : cgi.escape(form_data.repository, 1),
      'branch' : cgi.escape(form_data.branch, 1),
      'directory' : cgi.escape(form_data.directory, 1),
      'file' : cgi.escape(form_data.file, 1),
      'who' : cgi.escape(form_data.who, 1),

      'sortby' : form_data.sortby,
      'date' : form_data.date,

      'query' : query,
      'commits' : commits,
      'num_commits' : len(commits),
      }

    if form_data.hours:
      data['hours'] = form_data.hours
    else:
      data['hours'] = 2

    template = ezt.Template()
    template.parse_file(os.path.join(viewcvs.g_install_dir,
                                     cfg.templates.query))

    viewcvs.http_header()

    # generate the page
    template.generate(sys.stdout, data)

def run_cgi():

  ### be nice to share all this logic with viewcvs.run_cgi

  try:
    main()
  except SystemExit, e:
    # don't catch SystemExit (caused by sys.exit()). propagate the exit code
    sys.exit(e[0])
  except:
    info = sys.exc_info()
    viewcvs.http_header()
    print '<html><head><title>Python Exception Occurred</title></head>'
    print '<body bgcolor=white><h1>Python Exception Occurred</h1>'
    import traceback
    lines = apply(traceback.format_exception, info)
    print '<pre>'
    print cgi.escape(string.join(lines, ''))
    print '</pre>'
    viewcvs.html_footer()


class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
