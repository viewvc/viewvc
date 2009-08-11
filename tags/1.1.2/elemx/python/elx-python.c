#include <stdio.h>
#include <stdlib.h>

#include "scanner.h"
#include "python.h"
#include "py_keywords.h"
#include "elx.h"

extern int yylex(void);

static const char *fname;
static int saw_error = 0;
static void *scan_ctx;
static elx_context_t *ectx;

void yyerror(const char *msg)
{
    int sl, sc, el, ec;

    scanner_token_linecol(scan_ctx, &sl, &sc, &el, &ec);
    fprintf(stderr, "%s:%d:%d: parse error: %s\n", fname, sl, sc, msg);
    saw_error = 1;
}

int reader(void *user_ctx)
{
    FILE *inf = user_ctx;
    int c = fgetc(inf);

    if (c == EOF)
        return SCANNER_EOF;

//    printf("char: '%c'\n", c);

    return c;
}

void issue_token(char which)
{
    int start;
    int end;
    const char *ident = NULL;

    scanner_token_range(scan_ctx, &start, &end);

    if (ELX_DEFINES_SYM(which))
    {
        int length;

        scanner_identifier(scan_ctx, &ident, &length);
    }

    elx_issue_token(ectx, which, start, end - start + 1, ident);
}

int yylex(void)
{
    int v;

    do {
        v = scanner_get_token(scan_ctx);

        if (v == TK_COMMENT)
        {
            issue_token(ELX_COMMENT);
        }
    } while (v == TK_COMMENT);

    /* is this identifier a keyword? */
    if (v == TK_IDENTIFIER)
    {
        const char *ident;
        int length;
        int kw;

        scanner_identifier(scan_ctx, &ident, &length);
#if 0
        printf("id=%s\n", ident);
#endif

        kw = KR_find_keyword(ident, length);
        if (kw != KR__not_found)
        {
            v = kw;
            issue_token(ELX_KEYWORD);
        }
    }
    else if (v == TK_STRING)
    {
        issue_token(ELX_STRING);
    }

//    printf("token=%d\n", v);

    return v;
}

#ifdef DEBUG_SCANNER

void gen_scan_tokens(void)
{
    while (1)
    {
        int v = scanner_get_token(scan_ctx);
        int sl, sc, el, ec;

        scanner_token_linecol(scan_ctx, &sl, &sc, &el, &ec);
        if (v == TK_NEWLINE)
            printf("%d,%d: NEWLINE\n", sl, sc);
        else if (v == TK_INDENT)
            printf("%d,%d: INDENT\n", el, ec);
        else if (v == TK_DEDENT)
            printf("%d,%d: DEDENT\n", el, ec);
        else
            printf("%d,%d-%d,%d: %d\n", sl, sc, el, ec, v);

        /* end of parse? */
        if (v <= 0)
            break;
    }
}

#endif /* DEBUG_SCANNER */

static void gen_elx_tokens(void)
{
    /* ### what to do with the result? should have seen/set saw_error */
    (void) yyparse();
}

int main(int argc, const char **argv)
{
    ectx = elx_process_args(argc, argv);
    elx_open_files(ectx);

    scan_ctx = scanner_begin(reader, ectx->input_fp);

#ifdef DEBUG_SCANNER
    gen_scan_tokens();
#else
    gen_elx_tokens();
#endif

    scanner_end(scan_ctx);
    elx_close_files(ectx);

    if (saw_error)
        return EXIT_FAILURE;
    return EXIT_SUCCESS;
}
