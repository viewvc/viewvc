/*
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
# This file has been rewritten in C++ from the rcsparse.py file by
# Lucas Bruand <lucas.bruand@ecl2002.ec-lyon.fr>
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewVC
# distribution or at http://viewvc.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewvc.org/
#
# -----------------------------------------------------------------------
#
# This software is being maintained as part of the ViewVC project.
# Information is available at:
#    http://viewvc.org/
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
#include <ctime>   /* for strptime */


using namespace std;

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
rcstoken *TokenParser::get(int allow_eof)
{
  auto_ptr<rcstoken> token;

  if (backget)
  {
    token.reset(backget);
    backget = NULL;

    return token.release();
  }

  token.reset(new rcstoken());
  while (1)
  {
    if (idx == buflength)
    {
      input->read(buf, CHUNK_SIZE);
      if ( (buflength = input->gcount()) == 0 )
      {
        if (allow_eof)
          return token.release();
        else
          throw RCSParseError("Unexpected end of file.");
      };

      idx = 0;
    }
    if (!Whitespace(buf[idx]))
      break;
    idx++;
  }

  if (buf[idx] == ';')
  {
    idx++;
    (*token) = ';';
    return token.release();
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
        return token.release();
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
    return token.release();
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
void tparseParser::parse_rcs_admin()
{
  while (1)
  {
    auto_ptr<rcstoken> token(tokenstream->get(FALSE));

    if (isdigit((*token)[0]))
    {
      tokenstream->unget(token.release());
      return;
    }
    if (*token == "head")
    {
      token.reset(tokenstream->get(FALSE));
      sink->set_head_revision(*token);

      tokenstream->match(';');
      continue;
    }
    if (*token == "branch")
    {
      token.reset(tokenstream->get(FALSE));
      if (*token != ';')
      {
        sink->set_principal_branch(*token);

        tokenstream->match(';');
      }
      continue;
    }
    if (*token == "symbols")
    {
      while (1)
      {
        auto_ptr<rcstoken> tag, rev;
        char *second;
        //        delete token;
        token.reset(tokenstream->get(FALSE));
        if (*token == ';')
          break;

        second = index(token->data, ':');
        if (second)
        {
          tag.reset(token->copy_begin_len(0, second - token->data));
          second++;
          rev.reset(new rcstoken(second));
        }
        else
        {
          tag = token;
          tokenstream->match(':');
          rev.reset(tokenstream->get(FALSE));
        };
        sink->define_tag(*tag, *rev);
      }
      continue;
    }
    if (*token == "comment")
    {
      token.reset(tokenstream->get(FALSE));
      sink->set_comment((*token));

      tokenstream->match(';');
      continue;
    }
    if (*token == "locks" ||
        *token == "strict" ||
        *token == "expand" ||
        *token == "access")
    {
      while (1)
      {
        token.reset(tokenstream->get(FALSE));
        if (*token == ';')
          break;
      }
      continue;
    }
  }
};

void tparseParser::parse_rcs_tree()
{
  while (1)
  {
    auto_ptr<rcstoken> revision, date, author, hstate, next;
    long timestamp;
    tokenlist branches;
    struct tm tm;

    revision.reset(tokenstream->get(FALSE));
    if (*revision == "desc")
    {
      tokenstream->unget(revision.release());
      return;
    }

    // Parse date
    tokenstream->match("date");
    date.reset(tokenstream->get(FALSE));
    tokenstream->match(";");

    memset ((void *) &tm, 0, sizeof(struct tm));
    if (strptime((*date).data, "%y.%m.%d.%H.%M.%S", &tm) == NULL)
      strptime((*date).data, "%Y.%m.%d.%H.%M.%S", &tm);
    timestamp = mktime(&tm);


    tokenstream->match("author");
    author.reset(tokenstream->get(FALSE));
    tokenstream->match(';');

    tokenstream->match("state");
    hstate.reset(new rcstoken());
    while (1)
    {
      auto_ptr<rcstoken> token;
      token.reset(tokenstream->get(FALSE));
      if (*token == ';')
        break;

      if ((*hstate).length)
        (*hstate) += ' ';
      (*hstate) += *token;
    }

    tokenstream->match("branches");
    while (1)
      {
        auto_ptr<rcstoken> token;
        token.reset(tokenstream->get(FALSE));
        if (*token == ';')
          break;

        branches.push_front((*token));
      }

    tokenstream->match("next");
    next.reset(tokenstream->get(FALSE));
    if (*next == ';')
      /* generate null token */
      next.reset(new rcstoken());
    else
      tokenstream->match(';');

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
        auto_ptr<rcstoken> token;
        token.reset(tokenstream->get(FALSE));

        if ((*token == "desc") || isdigit((*token)[0]) )
          {
            tokenstream->unget(token.release());
            break;
          };

        while (*token != ";")
          token.reset(tokenstream->get(FALSE));
      }

    sink->define_revision(*revision, timestamp, *author,
                          *hstate, branches, *next);
  }
  return;
}

void tparseParser::parse_rcs_description()
{
  auto_ptr<rcstoken> token;
  tokenstream->match("desc");

  token.reset(tokenstream->get(FALSE));
  sink->set_description(*token);
}

void tparseParser::parse_rcs_deltatext()
{
  auto_ptr<rcstoken> revision, log, text;

  while (1)
  {
    revision.reset(tokenstream->get(TRUE));
    if ((*revision).null_token())
      break;

    tokenstream->match("log");
    log.reset(tokenstream->get(FALSE));

    tokenstream->match("text");
    text.reset(tokenstream->get(FALSE));

    sink->set_revision_info(*revision, *log, *text);
  }
  return;
}
