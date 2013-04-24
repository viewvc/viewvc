#ifndef ELX_H
#define ELX_H

#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


#define ELX_COMMENT     'C'     /* a comment */
#define ELX_STRING      'S'     /* a string constant */
#define ELX_KEYWORD     'K'     /* a language keyword */
#define ELX_GLOBAL_FDEF 'F'     /* function defn in global (visible) scope */
#define ELX_LOCAL_FDEF  'L'     /* function defn in local (hidden) scope */
#define ELX_METHOD_DEF  'M'     /* method definition */
#define ELX_FUNC_REF    'R'     /* function reference / call */

#define ELX_DEFINES_SYM(c) ((c) == ELX_GLOBAL_FDEF || (c) == ELX_LOCAL_FDEF \
                            || (c) == ELX_METHOD_DEF)


typedef struct
{
    /* input filename */
    const char *input_fn;

    /* output filenames: element extractions, and symbols */
    const char *elx_fn;
    const char *sym_fn;

    /* file pointers for each of the input/output files */
    FILE *input_fp;
    FILE *elx_fp;
    FILE *sym_fp;

} elx_context_t;

elx_context_t *elx_process_args(int argc, const char **argv);

void elx_open_files(elx_context_t *ec);
void elx_close_files(elx_context_t *ec);


void elx_issue_token(elx_context_t *ec,
                     char which, int start, int len,
                     const char *symbol);


#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* ELX_H */
