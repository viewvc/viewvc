
%token TK_COMMENT TK_IDENTIFIER TK_NUMBER
%token TK_OPERATOR TK_STRING
%token TK_INDENT TK_DEDENT TK_NEWLINE

%token KR_and KR_assert KR_break KR_class KR_continue KR_def
%token KR_del KR_elif KR_else KR_except KR_exec KR_finally
%token KR_for KR_from KR_global KR_if KR_import KR_in KR_is
%token KR_lambda KR_not KR_or KR_pass KR_print KR_raise
%token KR_return KR_try KR_while KR_yield

%start file_input

%{
#include "elx.h"

void yyerror(const char *msg);
int yylex(void);

/* ### should come from an elx-python.h or something */
void issue_token(char which);
%}

%export {
/* the main parsing function */
int yyparse(void);

/* need to define the 'not found' in addition to the regular keywords */
#define KR__not_found 0
}

%%

file_input: (TK_NEWLINE | stmt)*

NAME: TK_IDENTIFIER

funcdef: KR_def NAME { issue_token(ELX_LOCAL_FDEF); } parameters ':' suite
parameters: '(' [varargslist] ')'
varargslist: paramdef (',' paramdef)* [',' [varargsdef]]
           | varargsdef
	   ;
/* the TK_OPERATOR represents '*' or '**' */
varargsdef: TK_OPERATOR NAME [',' TK_OPERATOR NAME]
paramdef: fpdef [TK_OPERATOR test]
fpdef: NAME | '(' fplist ')'
fplist: fpdef (',' fpdef)* [',']

stmt: simple_stmt | compound_stmt
simple_stmt: small_stmt (';' small_stmt)* [';'] TK_NEWLINE
small_stmt: expr_stmt | print_stmt | raise_stmt
	  | import_stmt | global_stmt | exec_stmt | assert_stmt
          | KR_del exprlist
	  | KR_pass
	  | KR_break
	  | KR_continue
	  | KR_return [testlist]
	  | KR_yield testlist
	  ;

/* expr_stmt is normally assignment, which we get thru TK_OPERATOR in 'expr' */
expr_stmt: testlist

/* a print normally allows '>> test'; since that is a TK_OPERATOR, we
   get it as part of 'factor'. this rule also allows for a trailing
   comma in '>> test,' which the normal print doesn't */
print_stmt: KR_print [test (',' test)* [',']]

raise_stmt: KR_raise [test [',' test [',' test]]]

/* the TK_OPERATOR represents '*' */
import_stmt: KR_import dotted_as_name (',' dotted_as_name)*
           | KR_from dotted_name KR_import (TK_OPERATOR | import_as_name (',' import_as_name)*)
import_as_name: NAME [NAME NAME]
dotted_as_name: dotted_name [NAME NAME]
dotted_name: NAME ('.' NAME)*
global_stmt: KR_global NAME (',' NAME)*
exec_stmt: KR_exec expr [KR_in test [',' test]]
assert_stmt: KR_assert test [',' test]

compound_stmt: if_stmt | while_stmt | for_stmt | try_stmt | funcdef | classdef
if_stmt: KR_if test ':' suite (KR_elif test ':' suite)* [KR_else ':' suite]
while_stmt: KR_while test ':' suite [KR_else ':' suite]
for_stmt: KR_for exprlist KR_in testlist ':' suite [KR_else ':' suite]
try_stmt: KR_try ':' suite (except_clause ':' suite)+
           [KR_else ':' suite] | KR_try ':' suite KR_finally ':' suite
/* NB compile.c makes sure that the default except clause is last */
except_clause: KR_except [test [',' test]]
suite: simple_stmt | TK_NEWLINE TK_INDENT stmt+ TK_DEDENT

test: test_factor (test_op test_factor | KR_is [KR_not] factor)*
      [TK_OPERATOR lambdef] | lambdef
test_op: bin_op | KR_in
test_factor: KR_not* factor

expr: factor (expr_op factor)*
expr_op: bin_op | KR_is [KR_not]

factor: TK_OPERATOR* atom trailer*

bin_op: TK_OPERATOR | KR_or | KR_and | KR_not KR_in

atom: '(' [testlist] ')' | '[' [listmaker] ']' | '{' [dictmaker] '}'
    | '`' testlist_no_trailing '`' | TK_IDENTIFIER | TK_NUMBER | TK_STRING+
listmaker: test ( list_for | (',' test)* [','] )
lambdef: KR_lambda [varargslist] ':' test
trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
subscriptlist: subscript (',' subscript)* [',']
subscript: '.' '.' '.' | test | [test] ':' [test] [sliceop]
sliceop: ':' [test]
exprlist: expr (',' expr)* [',']
testlist: test (',' test)* [',']
testlist_no_trailing: test (',' test)*
testlist_safe: test [(',' test)+ [',']] /* doesn't match: test, */
dictmaker: test ':' test (',' test ':' test)* [',']

classdef: KR_class NAME ['(' testlist ')'] ':' suite

/* arguments are normally 'keyword = test; since '=' is TK_OPERATOR, we
   match keyword arguments as part of 'test' (in 'expr').
   
   the vararg portion is normally '* test' or '** test'; since '*' and
   '**' are TK_OPERATOR, we match varargs as part of 'test' (in
   'factor')
   
   thus, all argument forms are simply 'test'
   
   varargs does not normally allow a trailing comma, but we can
   simplify things and allow a match
*/
arglist: test (',' test)* [',']

list_iter: list_for | list_if
list_for: KR_for exprlist KR_in testlist_safe [list_iter]
list_if: KR_if test [list_iter]
