/*
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
# This file has been rewritten in C++ from the rcsparse.py file by
# Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewCVS project.
# Information is available at:
#    http://viewcvs.sourceforge.net/
#
# This file was originally based on portions of the blame.py script by
# Curt Hagenlocher.
#
# -----------------------------------------------------------------------
#
*/ 
/*
   This C++ library offers an API to a performance oriented RCSFILE parser.
   It does little syntax checking.
 
   Version: $Id$	
*/

#include "tparse.h"
#define __USE_XOPEN
#include <time.h>

#define Whitespace(c) (c == ' ' || c == '\t' || c == '\014' || c == '\n' || c == '\r')
#define Token_term(c) (c == ' ' || c == '\t' || c == '\014' || c == '\n' || \
    c == '\r' || c == ';')
#define isdigit(c) ((c-'0')<10)

/*--------- Tokenparser class -----------*/
char * TokenParser::get()
{
  ostrstream ost;
  if (backget)
  {
    char *ret;
    ret = backget;
    backget = NULL;
    return ret;
  }

  while (1)
  {
    if (idx == buflength)
    {
      input->read(buf, CHUNK_SIZE);
      if ( (buflength = input->gcount()) == 0 )
        return NULL;
      idx = 0;
    }
    if (!Whitespace(buf[idx]))
      break;
    idx++;
  }
  if (buf[idx] == ';')
  {
    idx++;
    return semicol;
  }

  if (buf[idx] != '@')
  {
    int end = idx + 1;
    while (1)
    {
      while ( (end < buflength) && !(Token_term(buf[end])) )
        end++;
      ost.write(buf + idx, end - idx);
      if (end < buflength)
      {
        idx = end;
        ost.put('\0');
        return ost.str();
      }
      input->read(buf, CHUNK_SIZE);
      buflength = input->gcount();
      idx = 0;
      end = 0;
    }
  }
  idx++;
  while (1)
  {
    int i;
    if (idx == buflength)
    {
      idx = 0;
      input->read(buf, CHUNK_SIZE);
      if ( (buflength = input->gcount()) == 0 )
        throw RCSIllegalCharacter("Unterminated string: @ missing!");
    }
    //i=strchr(buf+idx,'@');
    for (i = idx;i < buflength && (buf[i] != '@');i++)
      ;
    if (i == buflength)
    {
      if ((buflength - idx) > 0)
        ost.write(buf + idx, buflength - idx);
      idx = buflength;
      continue;
    }
    if ( i == buflength - 1)
    {
      ost.write(buf + idx, i - idx);
      idx = 0;
      buf[0] = '@';
      input->read(buf + 1, CHUNK_SIZE - 1);
      if ( (buflength = input->gcount()) == 0 )
        throw RCSIllegalCharacter("Unterminated string: @ missing!");
      buflength++;
      continue;
    }
    if (buf[i + 1] == '@')
    {
      ost.write(buf + idx, i - idx + 1);
      idx = i + 2;
      continue;
    }
    if ((i - idx) > 0)
      ost.write(buf + idx, i - idx);
    idx = i + 1;
    ost.put('\0');
    return ost.str();
  }
};

void TokenParser::unget(char *token)
{
  if (backget)
  {
    throw RCSParseError("Ungetting a token while already having an ungetted token.");
  }
  backget = token;
}

/*--------- tparseParser class -----------*/
int tparseParser::parse_rcs_admin()
{
  while (1)
  {
    char *token = tokenstream->get();
    if (isdigit(token[0]))
    {
      tokenstream->unget(token);
      return 0;
    }
    if (strcmp(token, "head") == 0)
    {
      if (sink->set_head_revision(tokenstream->get()))
      {
        delstr(token);
        return 1;
      }
      tokenstream->matchsemicol();
      delstr(token);
      continue;
    }
    if (strcmp(token, "branch") == 0)
    {
      char *branch = tokenstream->get();
      if (branch != tokenstream->semicol)
      {
        if (sink->set_principal_branch(branch))
        {
          delstr(token);
          return 1;
        }
        tokenstream->matchsemicol();
      }
      delstr(token);
      continue;
    }
    if (strcmp(token, "symbols") == 0)
    {
      while (1)
      {
        char *tag = tokenstream->get();
        char *second;
        if (tag == tokenstream->semicol)
          break;
        second = index(tag, ':');
        second[0] = '\0';
        second++;
        if (sink->define_tag(tag, second))
        {
          delstr(token);
          return 1;
        }
      }
      delstr(token);
      continue;
    }
    if (strcmp(token, "comment") == 0)
    {
      if (sink->set_comment(tokenstream->get()))
      {
        delstr(token);
        return 1;
      }
      tokenstream->matchsemicol();
      delstr(token);
      continue;
    }
    if ((strcmp(token, "locks") == 0) ||
        (strcmp(token, "strict") == 0) ||
        (strcmp(token, "expand") == 0) ||
        (strcmp(token, "access") == 0))
    {
      while (1)
      {
        char *tag = tokenstream->get();
        if (tag == tokenstream->semicol)
          break;
        delstr(tag);
      }
      delstr(token);
      continue;
    }
    delstr(token);
  }
};

int tparseParser::parse_rcs_tree()
{
  while (1)
  {
    char *revision;
    char *date;
    long timestamp;
    char *author;
    ostrstream *state;
    char *hstate;
    char *next;
    Branche *branches = NULL;
    struct tm tm;
    revision = tokenstream->get();
    if (strcmp(revision, "desc") == 0)
    {
      tokenstream->unget(revision);
      return 0;
    }
    // Parse date
    tokenstream->match("date");
    date = tokenstream->get();
    tokenstream->matchsemicol();
    memset ((void *) &tm, 0, sizeof(struct tm));
    if (strptime(date, "%y.%m.%d.%H.%M.%S", &tm) == NULL)
      strptime(date, "%Y.%m.%d.%H.%M.%S", &tm);
    timestamp = mktime(&tm);
    delstr(date);
    tokenstream->match("author");
    author = tokenstream->get();
    tokenstream->matchsemicol();
    tokenstream->match("state");
    state = new ostrstream();
    while (1)
    {
      char *token = tokenstream->get();
      if (token == tokenstream->semicol)
      {
        break;
      }
      if (state->pcount())
        state->put(' ');
      (*state) << token;
      delstr(token);
    }
    state->put('\0');
    hstate = state->str();
    delete state;
    state = NULL;
    tokenstream->match("branches");
    while (1)
    {
      char *token = tokenstream->get();
      if (token == tokenstream->semicol)
      {
        break;
      }
      if (branches == NULL)
        branches = new Branche(token, NULL);
      else
        branches = new Branche(token, branches);
    }
    tokenstream->match("next");
    next = tokenstream->get();
    if (next == tokenstream->semicol)
      next = NULL;
    else
      tokenstream->matchsemicol();
    /**
         * 	there are some files with extra tags in them. for example:
         *	owner	640;
      	 *	group	15;
      	 *	permissions	644;
      	 *	hardlinks	@configure.in@;
      	 *	this is "newphrase" in RCSFILE(5). we just want to skip over these.
    **/

    while (1)
    {
      char *token = tokenstream->get();
      if ( (strcmp(token, "desc") == 0) || isdigit(token[0]) )
      {
        tokenstream->unget(token);
        break;
      };
      delstr(token);
      while ( (token = tokenstream->get()) != tokenstream->semicol)
        delstr(token);
    }

    if (sink->define_revision(revision, timestamp, author, hstate, branches, next))
      return 1;
  }
  return 0;
}

int tparseParser::parse_rcs_description()
{
  tokenstream->match("desc");
  return (this->sink->set_description(tokenstream->get()));
}

int tparseParser::parse_rcs_deltatext()
{
  char *revision;
  char *log;
  char *text;
  while (1)
  {
    revision = tokenstream->get();
    if (revision == NULL)
      break;
    tokenstream->match("log");
    log = tokenstream->get();
    tokenstream->match("text");
    text = tokenstream->get();
    if (sink->set_revision_info(revision, log, text))
      return 1;
  }
  return 0;
}
