#!/usr/bin/python
# -*- Mode: python -*-
#
# CGI script to process and display queries to CVSdb
#
# -----------------------------------------------------------------------
# Copyright (C) 2000 Jay Painter. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth below:
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
# -----------------------------------------------------------------------
#
# For tracking purposes, this software is identified by:
#   $Id$
#
# -----------------------------------------------------------------------

## BOOTSTRAP
import sys, os, string
_viewcvs_root = string.strip(open("/etc/viewcvs/root", "r").read())
sys.path.append(os.path.join(_viewcvs_root, "lib"))
##

import cgi, cvsdbapi

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
    ctDate = commit.GetDate()
    if not ctDate:
        cDate = "&nbsp";
    else:
        cDate = '%d/%d/%d %d:%d:%d' % ctDate
    
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
        color, cDate, cAuthor, cFile, cRevision, cBranch,
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

    template_path = os.path.join(
        _viewcvs_root, "html-templates", "querytemplate.html")
    template = HTMLTemplate(template_path)
    template.Print1()
    
    form = cgi.FieldStorage()
    query = FormToCheckinQuery(form)
    RunQuery(query)
    
    template.Print2()


if __name__ == '__main__':
    Main()
