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

LIBRARY_DIR = None
CONF_PATHNAME = None
HTML_TEMPLATE_DIR = None

# Adjust sys.path to include our library directory
import sys

if LIBRARY_DIR:
  sys.path.insert(0, LIBRARY_DIR)
else:
  sys.path[:0] = ['../lib']	# any other places to look?

#########################################################################

import os, string, cgi, time, cvsdbapi


## tuple of alternating row colors
Colors = ("#ccccee", "#ffffff")


def HTMLHeader():
    print "Content-type: text/html"
    print
    

def FormToCheckinQuery(form):
    query = cvsdbapi.CreateCheckinQuery()

    if form.has_key("repository"):
        temp = form["repository"].value
        query.SetRepository(temp)
        
    if form.has_key("branch"):
        temp = form["branch"].value
        query.SetBranch(temp)
        
    if form.has_key("directory"):
        temp = form["directory"].value
        query.SetDirectory(temp)

    if form.has_key("file"):
        temp = form["file"].value
        query.SetFile(temp)

    if form.has_key("who"):
        temp = form["who"].value
        query.SetAuthor(temp)

    if form.has_key("sortby"):
        temp = form["sortby"].value
        if temp == "date":
            query.SetSortMethod(query.SORT_DATE)
        elif temp == "author":
            query.SetSortMethod(query.SORT_AUTHOR)
        else:
            query.SetSortMethod(query.SORT_FILE)

    if form.has_key("date"):
        temp = form["date"].value
        if temp == "hours":
            if form.has_key("hours"):
                hours = string.atoi(form["hours"].value)
            else:
                hours = 2
            query.SetFromDateHoursAgo(hours)
        elif temp == "day":
            query.SetFromDateDaysAgo(1)
        elif temp == "week":
            query.SetFromDateDaysAgo(7)
        elif temp == "month":
            query.SetFromDateDaysAgo(31)
            
    return query


def PrintCommitRow(commit, color):
    cTime = commit.GetTime()
    if not cTime:
        cTime = "&nbsp";
    else:
        cTime = time.strftime("%y/%m/%d %H:%M", time.localtime(cTime))
    
    cAuthor = commit.GetAuthor()
    if not cAuthor:
        cAuthor = "&nbsp";
    
    cFile = os.path.join(commit.GetDirectory(), commit.GetFile())
    if not cFile:
        cFile = "&nbsp";
    
    cRevision = commit.GetRevision()
    if not cRevision:
        cRevision = "&nbsp";
    
    cBranch = commit.GetBranch()
    if not cBranch:
        cBranch = "&nbsp";

    cPlusMinus = '%d/%d' % (commit.GetPlusCount(), commit.GetMinusCount())
    
    cDescription = commit.GetDescription()
    if not cDescription:
        cDescription = "&nbsp";
    else:
        cDescription = cgi.escape(cDescription)
        cDescription = string.replace(cDescription, '\n', '<br>')
    
    print '<tr bgcolor="%s"><td align=left valign=top>%s</td>\
           <td align=left valign=top>%s</td>\
           <td align=left valign=top>%s</td>\
           <td align=left valign=top>%s</td>\
           <td align=left valign=top>%s</td>\
           <td aligh=left valign=top>%s</td>\
           <td align=left valign=top>%s</td></tr>' % (
        color, cTime, cAuthor, cFile, cRevision, cBranch,
        cPlusMinus, cDescription)


def PrintCommitRows(commit_list):
    color_index = 0
    for commit in commit_list:
        PrintCommitRow(commit, Colors[color_index])
        color_index = (color_index + 1) % len(Colors)


g_iColorIndex = 0
def CommitCallback(commit):
    global g_iColorIndex
    PrintCommitRow(commit, Colors[g_iColorIndex])
    g_iColorIndex = (g_iColorIndex + 1) % len(Colors)


def RunQuery(query):
    query.SetCommitCB(CommitCallback)
    db = cvsdbapi.ConnectDatabaseReadOnly()
    db.RunQuery(query)


class HTMLTemplate:
    def __init__(self, filename):
        self.template = open(filename, 'r').read()

    def Print1(self):
        index = string.find(self.template, '<!-- INSERT QUERY ROWS -->')
        print self.template[:index]

    def Print2(self):
        index = string.find(self.template, '<!-- INSERT QUERY ROWS -->')
        print self.template[index:]


def Main():
    HTMLHeader()

    template_path = os.path.join(HTML_TEMPLATE_DIR, "querytemplate.html")
    template = HTMLTemplate(template_path)
    template.Print1()
    
    form = cgi.FieldStorage()
    query = FormToCheckinQuery(form)
    RunQuery(query)
    
    template.Print2()


if __name__ == '__main__':
    Main()
