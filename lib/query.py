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
import traceback

import cvsdb
import viewcvs

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
    cvsroot_name = ""
    for (key, value) in cfg.general.cvs_roots.items():
        if value == cvsroot:
            cvsroot_name = key
            break
    return cvsroot_name

def html_commit_list(commit_list, color):
    rs = len(commit_list)

    ## one description for these commits
    desc = commit_list[0].GetDescription()
    if not desc:
        desc = "&nbsp";
    else:
        desc = cgi.escape(desc)
        desc = string.replace(desc, "\n", "<br>")
    
    for commit in commit_list:
        ctime = commit.GetTime()
        if not ctime:
            ctime = "&nbsp";
        else:
            ctime = time.strftime("%y/%m/%d %H:%M", time.localtime(ctime))

        author = commit.GetAuthor() or "&nbsp"

        ## make the file link
        file = os.path.join(commit.GetDirectory(), commit.GetFile())
        file_full_path = os.path.join(commit.GetRepository(), file)

        ## if we couldn't find the cvsroot path configured in the 
        ## viewcvs.conf file, then don't make the link
        cvsroot_name = cvsroot_name_from_path(commit.GetRepository())
        if cvsroot_name:
            flink = "<a href=\"viewcvs.cgi/%s?cvsroot=%s\">%s</a>" % (
                file, cvsroot_name, file_full_path)
        else:
            flink = file_full_path

        revision = commit.GetRevision() or "&nbsp"
        branch = commit.GetBranch() or "&nbsp"
        plusminus = "%d/%d" % (commit.GetPlusCount(), commit.GetMinusCount())

        print "<tr bgcolor=%s>" % (color)
        print "<td align=left valign=top>%s</td>" % (ctime)
        print "<td align=left valign=top>%s</td>" % (author)
        print "<td align=left valign=top>%s</td>" % (flink)
        print "<td align=left valign=top>%s</td>" % (revision)
        print "<td align=left valign=top>%s</td>" % (branch)
        print "<td align=left valign=top>%s</td>" % (plusminus)

        if commit == commit_list[0]:
            print "<td align=left valign=top rowspan=%d>%s</td>" % (rs,desc)
        print "</tr>"
    
def run_query(form_data):
    query = form_to_cvsdb_query(form_data)
    db = cvsdb.ConnectDatabaseReadOnly()
    db.RunQuery(query)

    print "<p><b>%d</b> matches found.</p>" % (len(query.commit_list))
    
    print "<table width=100%% border=0 cellspacing=0 cellpadding=2>"
    print " <tr bgcolor=#88ff88>"
    print "  <th align=left valign=top>Date</th>"
    print "  <th align=left valign=top>Author</th>"
    print "  <th align=left valign=top>File</th>"
    print "  <th align=left valign=top>Revision</th>"
    print "  <th align=left valign=top>Branch</th>"
    print "  <th align=left valign=top>+/-</th>"
    print "  <th align=left valign=top>Description</th>"
    print " </tr>"

    commit_num = 0
    commit_list = []
    current_desc = None

    if len(query.commit_list):
        current_desc = query.commit_list[0].GetDescription()
        
    for commit in query.commit_list:
        desc = commit.GetDescription()
        
        if current_desc == desc:
            commit_list.append(commit)
            continue

        html_commit_list(commit_list, cfg.colors.even_odd[commit_num % 2])
        commit_list = [commit]
        current_desc = desc
        commit_num = commit_num + 1

    ## display the last commit_list
    if len(commit_list):
        html_commit_list(commit_list, cfg.colors.even_odd[commit_num % 2])

    print " <tr bgcolor=#88ff88>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print "  <th align=left valign=top>&nbsp</th>"
    print " </tr>"
    print "</table>"

def html_left_form_table(form_data):
    rp = string.replace(cgi.escape(form_data.repository), "\"", "&quot")
    br = string.replace(cgi.escape(form_data.branch), "\"", "&quot")
    di = string.replace(cgi.escape(form_data.directory), "\"", "&quot")
    fi = string.replace(cgi.escape(form_data.file), "\"", "&quot")
    wh = string.replace(cgi.escape(form_data.who), "\"", "&quot")

    print "<table>"
    print " <tr>"
    print "  <td align=right>CVS Repository:</td>"
    print "  <td>"
    print "   <input type=text name=repository size=40 value=\"%s\">" % (rp)
    print "  </td>"
    print " </tr>"
    print " <tr>"
    print "  <td align=right>CVS Branch:</td>"
    print "  <td>"
    print "   <input type=text name=branch size=40 value=\"%s\">" % (br)
    print "  </td>"
    print " </tr>"
    print " <tr>"
    print "  <td align=right>Directory:</td>"
    print "  <td>"
    print "   <input type=text name=directory size=40 value=\"%s\">" % (di)
    print "  </td>"
    print " </tr>"
    print " <tr>"
    print "  <td align=right>File:</td>"
    print "  <td>"
    print "   <input type=text name=file size=40 value=\"%s\">" % (fi)
    print "  </td>"
    print " </tr>"
    print " <tr>"
    print "  <td align=right>Author:</td>"
    print "  <td>"
    print "   <input type=text name=who size=40 value=\"%s\">" % (wh)
    print "  </td>"
    print " </tr>"
    print "</table>"

def html_right_form_table(form_data):
    fs = ""
    as = ""
    ds = ""
    if form_data.sortby == "file":
        fs = "selected"
    elif form_data.sortby == "author":
        as = "selected"
    else:
        ds = "selected"

    hr = 2
    if form_data.hours:
        hr = form_data.hours

    hc = ""
    dc = ""
    wc = ""
    mc = ""
    ac = ""
    if form_data.date == "month":
        mc = "checked"
    elif form_data.date == "week":
        wc = "checked"
    elif form_data.date == "day":
        dc = "checked"
    elif form_data.date == "all":
        ac = "checked"
    else:
        hc = "checked"
    
    print "<table>"
    print " <tr>"
    print "  <td align=left>Sort By:</td>"
    print "  <td>"
    print "   <select name=sortby>"
    print "    <option value=date %s>Date</option>" % (ds)
    print "    <option value=author %s>Author</option>" % (as)
    print "    <option value=file %s>File</option>" % (fs)
    print "   </select>"
    print "  </td>"
    print " </tr>"
    print " <tr>"
    print "  <td colspan=2>"
    print "   <table border=0 cellspacing=0 cellpadding=0>"
    print "    <tr>"
    print "     <td>Date:</td>"
    print "    </tr>"
    print "    <tr>"
    print "     <td><input type=radio name=date value=hours %s></td>" % (hc)
    print "     <td>In the last"
    print "       <input type=text name=hours value=%d size=4>hours" % (hr)
    print "     </td>"
    print "    </tr>"
    print "    <tr>"
    print "     <td><input type=radio name=date value=day %s></td>" % (dc)
    print "     <td>In the last day</td>"
    print "    </tr>"
    print "    <tr>"
    print "     <td><input type=radio name=date value=week %s></td>" % (wc)
    print "     <td>In the last week</td>"
    print "    </tr>"
    print "    <tr>"
    print "     <td><input type=radio name=date value=month %s></td>" % (mc)
    print "     <td>In the last month</td>"
    print "    </tr>"
    print "    <tr>"
    print "     <td><input type=radio name=date value=all %s></td>" % (ac)
    print "     <td>Since the beginning of time</td>"
    print "    </tr>"
    print "   </table>"
    print "  </td>"
    print " </tr>"
    print "</table>"

def html_form(form_data):
    print "<form method=get action=\"query.cgi\">"

    print "<table border=0 cellspacing=0 cellpadding=2 "\
          " width=100%% bgcolor=e6e6e6>"
    print " <tr>"
    print "  <td>"
    print "   <table>"
    print "    <tr>"
    print "     <td valign=top>"
    html_left_form_table(form_data)
    print "     </td>"
    print "     <td valign=top>"
    html_right_form_table(form_data)
    print "     </td>"
    print "    </tr>"
    print "   </table>"
    print "  </td>"
    print "  <td>"
    print "   <input type=submit value=\"Search\">"
    print "  </td>"
    print " </tr>"
    print "</table>"

    print "</form>"

def html_header(title):
    viewcvs.html_header(title)
    print cfg.text.cvsdb_intro 

def handle_config():
    viewcvs.handle_config()
    global cfg
    cfg = viewcvs.cfg

def main():
    handle_config()
    
    form = cgi.FieldStorage()
    form_data = FormData(form)
    
    html_header(cfg.general.main_title)
    html_form(form_data)
    
    if form_data.valid:
        run_query(form_data)

    viewcvs.html_footer()

def run_cgi():
  try:
    main()
  except SystemExit, e:
    # don't catch SystemExit (caused by sys.exit()). propagate the exit code
    sys.exit(e[0])
  except:
    info = sys.exc_info()
    viewcvs.html_header('Python Exception Occurred')
    import traceback
    lines = apply(traceback.format_exception, info)
    print '<pre>'
    print cgi.escape(string.join(lines, ''))
    print '</pre>'
    viewcvs.html_footer()
