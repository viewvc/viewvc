
#include <stdlib.h>
#include <ctype.h>
#include <assert.h>
#include <string.h>

#include "python.h"     /* get the TK_ values */
#include "scanner.h"

#define SCANNER_EMPTY (SCANNER_EOF - 1) /* -2 */
#define SCANNER_TABSIZE 8
#define SCANNER_MAXINDENT 100
#define SCANNER_MAXIDLEN  200

typedef struct
{
    get_char_t getfunc;
    void *user_ctx;

    char saved;
    int was_newline;    /* was previous character a newline? */

    int start;          /* start position of last token returned */
    int start_col;
    int start_line;

    int fpos;           /* file position */
    int lineno;         /* file line number */
    int line_pos;       /* file position of current line's first char */

    int nesting_level;

    int indent;                         /* which indent */
    int indents[SCANNER_MAXINDENT];     /* the set of indents */

    int dedent_count;                   /* how many DEDENTs to issue */

    int skip_newline;   /* skip the newline after a blank_line + comment */

    int idlen;
    char identifier[SCANNER_MAXIDLEN];  /* accumulated identifier */

} scanner_ctx;


static int next_char(scanner_ctx *ctx)
{
    int c;

    ++ctx->fpos;

    if (ctx->saved == SCANNER_EMPTY)
    {
        return (*ctx->getfunc)(ctx->user_ctx);
    }

    c = ctx->saved;
    ctx->saved = SCANNER_EMPTY;
    return c;
}

static void backup_char(scanner_ctx *ctx, int c)
{
    assert(ctx->saved == SCANNER_EMPTY);
    ctx->saved = c;
    ctx->was_newline = 0;       /* we may have put it back */
    --ctx->fpos;
}

/* called to note that we've moved on to another line */
static void on_next_line(scanner_ctx *ctx)
{
    ctx->line_pos = ctx->fpos;
    ++ctx->lineno;
}

void *scanner_begin(get_char_t getfunc, void *user_ctx)
{
    scanner_ctx *ctx = malloc(sizeof(*ctx));

    memset(ctx, 0, sizeof(*ctx));
    ctx->getfunc = getfunc;
    ctx->user_ctx = user_ctx;
    ctx->saved = SCANNER_EMPTY;
    ctx->lineno = 1;

    return ctx;
}

int scanner_get_token(void *opaque_ctx)
{
    scanner_ctx *ctx = opaque_ctx;
    int c;
    int c2;
    int blank_line;

    if (ctx->dedent_count)
    {
        --ctx->dedent_count;
        return TK_DEDENT;
    }

  nextline:
    blank_line = 0;
    /* if we're at the start of the line, then get the indentation level */
    if (ctx->fpos == ctx->line_pos)
    {
        int col = 0;

        while (1)
        {
            c = next_char(ctx);
            if (c == ' ')
                ++col;
            else if (c == '\t')
                col = (col / SCANNER_TABSIZE + 1) * SCANNER_TABSIZE;
            else if (c == '\f')         /* ^L / formfeed */
                col = 0;
            else
                break;
        }
        backup_char(ctx, c);

        if (c == '#' || c == '\n')
        {
            /* this is a "blank" line and doesn't count towards indentation,
               and it doesn't produce NEWLINE tokens */
            blank_line = 1;
        }

        /* if it isn't blank, and we aren't inside nesting expressions, then
           we need to handle INDENT/DEDENT */
        if (!blank_line && ctx->nesting_level == 0)
        {
            int last_indent = ctx->indents[ctx->indent];

            if (col == last_indent)
            {
                /* no change */
            }
            else if (col > last_indent)
            {
                if (ctx->indent == SCANNER_MAXINDENT - 1)
                {
                    /* oops. too deep. */
                    return E_TOO_MANY_INDENTS;
                }
                ctx->indents[++ctx->indent] = col;
                return TK_INDENT;
            }
            else /* col < last_indent */
            {
                /* find the previous indentation that matches this one */
                while (ctx->indent > 0
                       && col < ctx->indents[ctx->indent])
                {
                    ++ctx->dedent_count;
                    --ctx->indent;
                }
                if (col != ctx->indents[ctx->indent])
                {
                    /* oops. dedent doesn't match any indent. */
                    return E_DEDENT_MISMATCH;
                }

                /* deliver one dedent now */
                --ctx->dedent_count;
                return TK_DEDENT;
            }
        } /* !blank_line ... */
    } /* start of line */

    /* start here if we see a line continuation */
 read_more:

    do {
        c = next_char(ctx);
    } while (c == ' ' || c == '\t' || c == '\f');

    /* here is where the token starts */
    ctx->start = ctx->fpos;
    ctx->start_line = ctx->lineno;
    ctx->start_col = ctx->fpos - ctx->line_pos;

    /* comment? */
    if (c == '#')
    {
        do {
            c = next_char(ctx);
        } while (c != SCANNER_EOF && c != '\n');

        /* if we are suppressing newlines because this is a blank line, then
           leave a marker to skip the newline, next time through. */
        if (blank_line && c == '\n')
            ctx->skip_newline = 1;

        /* put back whatever we sucked up */
        backup_char(ctx, c);

        return TK_COMMENT;
    }

    /* Look for an identifier */
    if (isalpha(c) || c == '_')
    {
        ctx->idlen = 0;

        /* is this actually a string? */
        if (c == 'r' || c == 'R')
        {
            ctx->identifier[ctx->idlen++] = c;
            c = next_char(ctx);
            if (c == '"' || c == '\'')
                goto parse_string;
        }
        else if (c == 'u' || c == 'U')
        {
            ctx->identifier[ctx->idlen++] = c;
            c = next_char(ctx);
            if (c == 'r' || c == 'R')
            {
                ctx->identifier[ctx->idlen++] = c;
                c = next_char(ctx);
            }
            if (c == '"' || c == '\'')
                goto parse_string;
        }

        while (isalnum(c) || c == '_') {
            /* store the character if there is room for it, and room left
               for a null-terminator. */
            if (ctx->idlen < SCANNER_MAXIDLEN-1)
                ctx->identifier[ctx->idlen++] = c;
            c = next_char(ctx);
        }
        backup_char(ctx, c);

        /* ### check for a keyword */
        return TK_IDENTIFIER;
    }

    if (c == '\n')
    {
        on_next_line(ctx);

        /* don't report NEWLINE tokens for blank lines or nested exprs */
        if (blank_line || ctx->nesting_level > 0 || ctx->skip_newline)
        {
            ctx->skip_newline = 0;
            goto nextline;
        }

        return TK_NEWLINE;
    }

    if (c == '.')
    {
        c = next_char(ctx);
        if (isdigit(c))
            goto parse_fraction;
        backup_char(ctx, c);
        return '.';
    }

    if (isdigit(c))
    {
        if (c == '0')
        {
            c = next_char(ctx);
            if (c == 'x' || c == 'X')
            {
                do {
                    c = next_char(ctx);
                } while (isxdigit(c));
                goto skip_fp;
            }
            else if (isdigit(c))
            {
                do {
                    c = next_char(ctx);
                } while (isdigit(c));
            }
            if (c == '.')
                goto parse_fraction;
            if (c == 'e' || c == 'E')
                goto parse_exponent;
            if (c == 'j' || c == 'J')
                goto parse_imaginary;
        skip_fp:
            /* this point: parsed an octal, decimal, or hexadecimal */

            if (c == 'l' || c == 'L')
            {
                /* we consumed just enough. stop and return a NUMBER */
                return TK_NUMBER;
            }

            /* consumed too much. backup and return a NUMBER */
            backup_char(ctx, c);
            return TK_NUMBER;
        }

        /* decimal number */
        do {
            c = next_char(ctx);
        } while (isdigit(c));

        if (c == 'l' || c == 'L')
        {
            /* we consumed just enogh. stop and return a NUMBER */
            return TK_NUMBER;
        }

        if (c == '.')
        {
        parse_fraction:
            do {
                c = next_char(ctx);
            } while (isdigit(c));
        }

        if (c == 'e' || c == 'E')
        {
        parse_exponent:
            c = next_char(ctx);
            if (c == '+' || c == '-')
                c = next_char(ctx);
            if (!isdigit(c))
            {
                backup_char(ctx, c);
                return E_BAD_NUMBER;
            }
            do {
                c = next_char(ctx);
            } while (isdigit(c));
        }

        if (c == 'j' || c == 'J')
        {
        parse_imaginary:
            c = next_char(ctx);
        }

        /* one too far. backup and return a NUMBER */
        backup_char(ctx, c);
        return TK_NUMBER;

    } /* isdigit */

parse_string:
    if (c == '\'' || c == '"')
    {
        int second_quote_pos = ctx->fpos + 1;
        int which_quote = c;
        int is_triple = 0;
        int quote_count = 0;

        while (1)
        {
            c = next_char(ctx);
            if (c == '\n')
            {
                on_next_line(ctx);

                if (!is_triple)
                    return E_UNTERM_STRING;
                quote_count = 0;
            }
            else if (c == SCANNER_EOF)
            {
                return E_UNTERM_STRING;
            }
            else if (c == which_quote)
            {
                ++quote_count;
                if (ctx->fpos == second_quote_pos)
                {
                    c = next_char(ctx);
                    if (c == which_quote)
                    {
                        is_triple = 1;
                        quote_count = 0;
                        continue;
                    }
                    /* we just read one past the empty string. back up. */
                    backup_char(ctx, c);
                }

                /* this quote may have terminated the string */
                if (!is_triple || quote_count == 3)
                    return TK_STRING;
            }
            else if (c == '\\')
            {
                c = next_char(ctx);
                if (c == SCANNER_EOF)
                    return E_UNTERM_STRING;
                if (c == '\n')
                    on_next_line(ctx);
                quote_count = 0;
            }
            else
            {
                quote_count = 0;
            }
        }

        /* NOTREACHED */
    }

    /* line continuation */
    if (c == '\\')
    {
        c = next_char(ctx);
        if (c != '\n')
            return E_BAD_CONTINUATION;

        on_next_line(ctx);
        goto read_more;
    }

    /* look for operators */

    /* the nesting operators */
    if (c == '(' || c == '[' || c == '{')
    {
        ++ctx->nesting_level;
        return c;
    }
    if (c == ')' || c == ']' || c == '}')
    {
        --ctx->nesting_level;
        return c;
    }

    /* look for up-to-3-char ops */
    if (c == '<' || c == '>' || c == '*' || c == '/')
    {
        c2 = next_char(ctx);
        if (c == c2)
        {
            c2 = next_char(ctx);
            if (c2 != '=')
            {
                /* oops. one too far. */
                backup_char(ctx, c2);
            }
            return TK_OPERATOR;
        }

        if (c == '<' && c2 == '>')
            return TK_OPERATOR;

        if (c2 != '=')
        {
            /* one char too far. */
            backup_char(ctx, c2);
        }
        return TK_OPERATOR;
    }

    /* look for 2-char ops */
    if (c == '=' || c == '!' || c == '+' || c == '-'
        || c == '|' || c == '%' || c == '&' || c == '^')
    {
        c2 = next_char(ctx);
        if (c2 == '=')
            return TK_OPERATOR;

        /* oops. too far. */
        backup_char(ctx, c2);
        return TK_OPERATOR;
    }

    /* ### should all of these return 'c' ? */
    if (c == ':' || c == ',' || c == ';' || c == '`')
        return c;

    /* as a unary operator, this must be a TK_OPERATOR */
    if (c == '~')
        return TK_OPERATOR;

    /* if we have an EOF, then just return it */
    if (c == SCANNER_EOF)
        return SCANNER_EOF;

    /* unknown input */
    return E_UNKNOWN_TOKEN;
}

void scanner_identifier(void *opaque_ctx, const char **ident, int *len)
{
    scanner_ctx *ctx = opaque_ctx;

    ctx->identifier[ctx->idlen] = '\0';
    *ident = ctx->identifier;
    *len = ctx->idlen;
}

void scanner_token_range(void *opaque_ctx, int *start, int *end)
{
    scanner_ctx *ctx = opaque_ctx;

    *start = ctx->start;
    *end = ctx->fpos;
}

void scanner_token_linecol(void *opaque_ctx,
                           int *sline, int *scol, int *eline, int *ecol)
{
    scanner_ctx *ctx = opaque_ctx;

    *sline = ctx->start_line;
    *scol = ctx->start_col;

    *eline = ctx->lineno;
    *ecol = ctx->fpos - ctx->line_pos;
}

void scanner_end(void *ctx)
{
    free(ctx);
}
