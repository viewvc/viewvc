%start token
%scanner

%local {
#include "elx.h"

/* from elx-java.c */
void yyserror(const char *msg);
int yyslex(void);

/* for the TK_ symbols, generated from java.y */
#include "java.h"

/* for keyword recognition */
#include "j_keywords.h"

extern void issue_token(char which);
extern void mark_token_start(void);

#define MAX_IDENT 200
static int idlen;
static char identifier[MAX_IDENT+1];
#define INIT_IDENT(c) (identifier[0] = (c), idlen = 1)
#define ADD_IDENT(c) if (idlen == MAX_IDENT) return E_IDENT_TOO_LONG; \
                     else identifier[idlen++] = (c)

/* ### is there a better place? */
#define E_IDENT_TOO_LONG  (-100)

static int lookup(void);
}


%%

token : pure_ws* { mark_token_start(); } slash_op

slash_op : "/=" { return TK_OPERATOR; }
	 | comment token
	 | '/' { return TK_OPERATOR; }
	 | one_token
	 |
	 ;

one_token : t_identifier { return lookup(); }
	  | t_literal { return TK_LITERAL; }
	  | t_operator { return TK_OPERATOR; }
	  | t_chars { return yysprev_char; }
	  | t_inc_dec { return TK_INC_DEC; }
	  | t_bracket
          ;

t_identifier : alpha { INIT_IDENT(yysprev_char); }
	       ( alphanum { ADD_IDENT(yysprev_char); } )*

alpha : 'a' - 'z' | 'A' - 'Z' | '_' | '$'
alphanum : alpha | digit

digit : '0' - '9'
hexdigit : digit | 'a' - 'f' | 'A' - 'F'
octal : '0' - '7'

t_literal : number | string | char_constant

number : ('1' - '9') digit* decimal_suffix
       | '.' digit+ [exponent] [float_suffix]
       | '0' (('x' | 'X') hexdigit+ | octal+) decimal_suffix
       ;
decimal_suffix : ('.' digit* [exponent] [float_suffix])
	       | 'l' | 'L'
	       | /* nothing */
	       ;
exponent : ('e' | 'E') ['+' | '-'] digit+
float_suffix : 'f' | 'F' | 'd' | 'D'

string : '"' string_char* '"' { issue_token(ELX_STRING); }
string_char : '\1' -> '"' | '"' <-> '\\' | '\\' <- '\377' | '\\' '\1' - '\377'

char_constant : '\'' one_char '\''
one_char : '\1' -> '\'' | '\'' <-> '\\' | '\\' <- '\377' | '\\' '\1' - '\377'

comment : ( "//" line_comment_char* '\n'
	  | "/*" (block_comment_char | '*' block_non_term_char)* "*/"
	  ) { issue_token(ELX_COMMENT); }
	;
line_comment_char : '\1' -> '\n' | '\n' <- '\377'
block_comment_char : '\1' -> '*' | '*' <- '\377'
block_non_term_char : '\1' -> '/' | '/' <- '\377'

t_operator : "<<" | ">>" | ">>>"
           | ">=" | "<=" | "==" | "!=" | "&&" | "||"
	   | "*=" | "%=" | "+=" | "-=" | "<<=" | ">>="
	   | ">>>=" | "&=" | "^=" | "|="
	   | '<' | '>' | '%' | '^' | '&' | '|'
	   ;
t_inc_dec : "++" | "--"

/* note: could not use ws* ; the '[' form would only reduce on $end
   rather than "any" character. that meant we could not recognize '['
   within the program text. separating out the cases Does The Right
   Thing */
t_bracket : '[' { return '['; }
	  | '[' ']' { return TK_DIM; }
	  | '[' ws+ ']' { return TK_DIM; }
	  ;

t_chars : ',' | ';' | '.' | '{' | '}' | '=' | '(' | ')' | ':'
        | ']' | '!' | '~' | '+' | '-' | '*' | '?'
	;

ws : pure_ws | comment

pure_ws : ' ' | '\t' | '\n' | '\f'

%%

static int lookup(void)
{
    int kw = KR_find_keyword(identifier, idlen);

    if (kw == KR__not_found)
    {
        /* terminate so user can grab an identifier string */
        identifier[idlen] = '\0';
        return TK_IDENTIFIER;
    }
    
    issue_token(ELX_KEYWORD);
    return kw;
}

const char *get_identifier(void)
{
    return identifier;
}
