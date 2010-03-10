#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#include "elx.h"

#define ELX_ELEMS_EXT   ".elx"
#define ELX_SYMBOLS_EXT ".els"


static void usage(const char *progname)
{
    fprintf(stderr, "USAGE: %s FILENAME\n", progname);
    exit(1);
}

static const char * build_one(const char *base, int len, const char *suffix)
{
    int slen = strlen(suffix);
    char *fn;

    fn = malloc(len + slen + 1);
    memcpy(fn, base, len);
    memcpy(fn + len, suffix, slen);
    fn[len + slen] = '\0';

    return fn;
}

elx_context_t *elx_process_args(int argc, const char **argv)
{
    elx_context_t *ec;
    const char *input_fn;
    const char *p;
    int len;

    /* ### in the future, we can expand this for more options */

    if (argc != 2)
    {
        usage(argv[0]);
        /* NOTREACHED */
    }

    input_fn = argv[1];

    p = strrchr(input_fn, '.');
    if (p == NULL)
        len = strlen(input_fn);
    else
        len = p - argv[1];

    ec = malloc(sizeof(*ec));
    ec->input_fn = input_fn;
    ec->elx_fn = build_one(input_fn, len, ELX_ELEMS_EXT);
    ec->sym_fn = build_one(input_fn, len, ELX_SYMBOLS_EXT);

    return ec;
}

void elx_open_files(elx_context_t *ec)
{
    const char *fn;
    const char *op;

    if ((ec->input_fp = fopen(ec->input_fn, "r")) == NULL)
    {
        fn = ec->input_fn;
        op = "reading";
        goto error;
    }
    if ((ec->elx_fp = fopen(ec->elx_fn, "w")) == NULL)
    {
        fn = ec->elx_fn;
        op = "writing";
        goto error;
    }
    if ((ec->sym_fp = fopen(ec->sym_fn, "w")) == NULL)
    {
        fn = ec->sym_fn;
        op = "writing";
        goto error;
    }
    return;

  error:
    fprintf(stderr, "ERROR: file \"%s\" could not be opened for %s.\n       %s\n",
            fn, op, strerror(errno));
    exit(2);
}

void elx_close_files(elx_context_t *ec)
{
    fclose(ec->input_fp);
    fclose(ec->elx_fp);
    fclose(ec->sym_fp);
}

void elx_issue_token(elx_context_t *ec,
                     char which, int start, int len,
                     const char *symbol)
{
    fprintf(ec->elx_fp, "%c %d %d\n", which, start, len);

    if (ELX_DEFINES_SYM(which))
    {
        fprintf(ec->sym_fp, "%s %d %s\n", symbol, start, ec->input_fn);
    }
}
