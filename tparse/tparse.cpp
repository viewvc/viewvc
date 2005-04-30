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
#ifndef __USE_XOPEN
#define __USE_XOPEN
#endif
#include <time.h>

#define Whitespace(c) (c == ' ' || c == '\t' || c == '\014' || c == '\n' || \
                       c == '\r')
#define Token_term(c) (c == ' ' || c == '\t' || c == '\014' || c == '\n' || \
                       c == '\r' || c == ';')
#define isdigit(c) ((c-'0')<10)



void rcstoken::init(const char *mydata, size_t mylen)
{
  size = DEFAULT_TOKEN_SIZE;
  length = 0;
  delta = DEFAULT_TOKEN_DELTA;
  data = NULL;
  if (mydata && mylen)
    append(mydata, mylen);
};

void rcstoken::append(const char *b, size_t b_len)
{
  if (b || b_len)
    {
      grow(length + b_len + 1);
      memcpy(&data[length], b, b_len);
      length += b_len;
      data[length] = 0;
    }
};

void rcstoken::grow(size_t new_size)
{
  if ((! data) || (new_size > size))
    {
      while (new_size > size)
        size += delta;

      data = (char*) realloc(data, size);
    };
};

rcstoken *rcstoken::copy_begin_end(size_t begin, size_t end)
{
  return new rcstoken(&data[begin], end - begin);
};

rcstoken *rcstoken::copy_begin_len(size_t begin, size_t len)
{
  return new rcstoken(&data[begin], len);
};


/*--------- Tokenparser class -----------*/
rcstoken *TokenParser::get()
{
  rcstoken *token;

  if (backget)
  {
    token = backget;
    backget = NULL;
    return token;
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

  token = new rcstoken();
  if (buf[idx] == ';')
  {
    idx++;
    (*token) = ';';
    return token;
  }

  if (buf[idx] != '@')
  {
    int end = idx + 1;
    while (1)
    {
      while ( (end < buflength) && !(Token_term(buf[end])) )
        end++;
      token->append(buf + idx, end - idx);
      if (end < buflength)
      {
        idx = end;
        return token;
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
        token->append(buf + idx, buflength - idx);
      idx = buflength;
      continue;
    }
    if ( i == buflength - 1)
    {
      token->append(buf + idx, i - idx);
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
      token->append(buf + idx, i - idx + 1);
      idx = i + 2;
      continue;
    }
    if ((i - idx) > 0)
      token->append(buf + idx, i - idx);
    idx = i + 1;
    return token;
  }
};


void TokenParser::unget(rcstoken *token)
{
  if (backget)
  {
    throw RCSParseError("Ungetting a token while already having "
                        "an ungetted token.");
  }
  backget = token;
}

/*--------- tparseParser class -----------*/
int tparseParser::parse_rcs_admin()
{
  while (1)
  {
    rcstoken *token = tokenstream->get();
    if (isdigit((*token)[0]))
    {
      tokenstream->unget(token);
      return 0;
    }
    if (*token == "head")
    {
      delete token;
      if (sink->set_head_revision(token = tokenstream->get()))
      {
        delete token;
        return 1;
      }
      tokenstream->matchsemicol();
      delete token;
      continue;
    }
    if (*token == "branch")
    {
      rcstoken *branch = tokenstream->get();
      if (*branch != ';')
      {
        if (sink->set_principal_branch(branch))
        {
          delete branch;
          delete token;
          return 1;
        }
        delete branch;
        tokenstream->matchsemicol();
      }
      delete token;
      continue;
    }
    if (*token == "symbols")
    {
      while (1)
      {
        rcstoken *tag, *rev;
        char *second;
        delete token;
        token = tokenstream->get();
        if (*token == ';')
          break;

        /*FIXME: this does not allow "<tag> : <rev>"
          which the spec does allow */
        second = index(token->data, ':');
        tag = token->copy_begin_len(0, second - token->data);
        second++;
        rev = new rcstoken(second);
        if (sink->define_tag(tag, rev))
        {
          delete tag;
          delete rev;
          delete token;
          return 1;
        }
        delete tag;
        delete rev;
      }
      continue;
    }
    if (*token == "comment")
    {
      delete token;
      if (sink->set_comment(token = tokenstream->get()))
      {
        delete token;
        return 1;
      }
      tokenstream->matchsemicol();
      delete token;
      continue;
    }
    if (*token == "locks" ||
        *token == "strict" ||
        *token == "expand" ||
        *token == "access")
    {
      while (1)
      {
        rcstoken *tag = tokenstream->get();
        if (*tag == ';')
          {
            delete tag;
            break;
          }
        delete tag;
      }
      delete token;
      continue;
    }
    delete token;
  }
};

int tparseParser::parse_rcs_tree()
{
  while (1)
  {
    rcstoken *revision;
    rcstoken *date;
    long timestamp;
    rcstoken *author;
    rcstoken *hstate;
    rcstoken *next;
    Branche *branches = NULL;
    struct tm tm;
    revision = tokenstream->get();
    if (*revision == "desc")
    {
      tokenstream->unget(revision);
      return 0;
    }
    // Parse date
    tokenstream->match("date");
    date = tokenstream->get();
    tokenstream->matchsemicol();
    memset ((void *) &tm, 0, sizeof(struct tm));
    if (strptime(date->data, "%y.%m.%d.%H.%M.%S", &tm) == NULL)
      strptime(date->data, "%Y.%m.%d.%H.%M.%S", &tm);
    timestamp = mktime(&tm);
    delete date;
    tokenstream->match("author");
    author = tokenstream->get();
    tokenstream->matchsemicol();
    tokenstream->match("state");
    hstate = new rcstoken();
    while (1)
    {
      rcstoken *token = tokenstream->get();
      if (*token == ';')
      {
        break;
      }
      if (hstate->length)
        (*hstate) += ' ';
      (*hstate) += *token;
      delete token;
    }
    tokenstream->match("branches");
    while (1)
    {
      rcstoken *token = tokenstream->get();
      if (*token == ';')
        break;

      branches = new Branche(token, branches);
    }
    tokenstream->match("next");
    next = tokenstream->get();
    if (*next == ';')
      /* generate null token */
      next = new rcstoken();
    else
      tokenstream->matchsemicol();
    /*
     * 	there are some files with extra tags in them. for example:
     *	owner	640;
     *	group	15;
     *	permissions	644;
     *	hardlinks	@configure.in@;
     *	this is "newphrase" in RCSFILE(5). we just want to skip over these.
     */

    while (1)
    {
      rcstoken *token = tokenstream->get();
      if (*token == "desc" || isdigit((*token)[0]))
      {
        tokenstream->unget(token);
        break;
      };
      delete token;
      while ( (*(token = tokenstream->get())) == ';')
        delete token;
    }

    if (sink->define_revision(revision, timestamp, author,
                              hstate, branches, next))
      {
        delete revision;
        delete author;
        delete hstate;
        delete branches;
        delete next;
        return 1;
      }
    delete revision;
    delete author;
    delete hstate;
    delete branches;
    delete next;
  }
  return 0;
}

int tparseParser::parse_rcs_description()
{
  rcstoken *token;
  tokenstream->match("desc");
  if (sink->set_description(token = tokenstream->get()))
  {
    delete token;
    return 1;
  }
  delete token;

  return 0;
}

int tparseParser::parse_rcs_deltatext()
{
  rcstoken *revision;
  rcstoken *log;
  rcstoken *text;
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
    {
      delete revision;
      delete log;
      delete text;
      return 1;
    }
    delete revision;
    delete log;
    delete text;
  }
  return 0;
}
