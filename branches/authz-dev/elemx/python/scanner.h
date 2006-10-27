#ifndef SCANNER_H
#define SCANNER_H


#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


/* constants and errors returned by the scanner */
enum
{
    SCANNER_EOF = -1,           /* returned by get_char_t and
                                   scanner_get_token to symbolize EOF */

    E_TOO_MANY_INDENTS = -100,  /* too many indents */
    E_DEDENT_MISMATCH,          /* no matching indent */
    E_BAD_CONTINUATION,         /* character occurred after \ */
    E_BAD_NUMBER,               /* parse error in a number */
    E_UNKNOWN_TOKEN,            /* dunno what we found */
    E_UNTERM_STRING             /* unterminated string constant */
};

typedef int (*get_char_t)(void *user_ctx);

void *scanner_begin(get_char_t getfunc, void *user_ctx);

int scanner_get_token(void *ctx);

void scanner_identifier(void *ctx, const char **ident, int *len);
void scanner_token_range(void *ctx, int *start, int *end);
void scanner_token_linecol(void *ctx,
                           int *sline, int *scol, int *eline, int *ecol);

void scanner_end(void *ctx);


#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* SCANNER_H */
