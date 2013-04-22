#include <stdio.h>
#include <stdlib.h>

#include "java.h"
#include "j_keywords.h"
#include "elx.h"

/* from j_scan.c */
extern int yylex(void);
extern void yylex_start(int *error_flag);
extern void yylex_finish(void);
extern const char *get_identifier(void);

static const char *fname;
static int saw_error = 0;

static int lineno = 1;
static int hpos = 1;
static int fpos = 0;

static int token_start = 0;
static int start_lineno;
static int start_hpos;

static elx_context_t *ectx;


//#define DEBUG_SCANNER

/* if we're debugging, then the scanner looks for this var */
int yysdebug = 0;

/* and the parser looks for this */
int yydebug = 1;


void yyserror(const char *msg)
{
    fprintf(stderr, "%s:%d:%d: lex error: %s\n",
            fname, start_lineno, start_hpos, msg);
    saw_error = 1;
}

void yyerror(const char *msg)
{
    fprintf(stderr, "%s:%d:%d: parse error: %s\n",
            fname, start_lineno, start_hpos, msg);
    saw_error = 1;
}

int yyslex(void)
{
    int c = fgetc(ectx->input_fp);

    if (c == EOF)
        return -1;      /* tell lexer we're done */

    ++fpos;
    if (c == '\n')
    {
        hpos = 1;
        ++lineno;
    }
    else
        ++hpos;

//    printf("char: '%c'\n", c);

    return c;
}

void issue_token(char which)
{
    const char *ident = NULL;

    if (ELX_DEFINES_SYM(which))
        ident = get_identifier();
    else
        ident = NULL;

    elx_issue_token(ectx, which, token_start, fpos - token_start + 1, ident);
}

void mark_token_start(void)
{
    token_start = fpos;
    start_lineno = lineno;
    start_hpos = hpos;
}

#ifdef DEBUG_SCANNER

void gen_scan_tokens(void)
{
    while (1)
    {
        int v = yylex();

        if (v == TK_IDENTIFIER)
            printf("%d-%d: %d '%s'\n",
                   token_start, fpos-1, v, get_identifier());
        else
            printf("%d-%d: %d\n", token_start, fpos-1, v);

        /* end of parse? */
        if (v <= 0)
            break;
    }
}

#else /* DEBUG_SCANNER */

static void gen_elx_tokens(void)
{
    /* ### what to do with the result? should have seen/set saw_error */
    (void) yyparse();
}

#endif /* DEBUG_SCANNER */

int main(int argc, const char **argv)
{
    int errcode;

    ectx = elx_process_args(argc, argv);

    yylex_start(&errcode);
    if (errcode)
    {
        fprintf(stderr, "error: yylex_start: %d\n", errcode);
        return EXIT_FAILURE;
    }

    elx_open_files(ectx);

#ifdef DEBUG_SCANNER
    gen_scan_tokens();
#else
    gen_elx_tokens();
#endif

    yylex_finish();
    elx_close_files(ectx);

    if (saw_error)
        return EXIT_FAILURE;
    return EXIT_SUCCESS;
}
