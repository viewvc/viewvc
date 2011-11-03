%token KR_abstract
%token KR_boolean KR_break KR_byte /* KR_byvalue */
%token KR_case /* KR_cast */ KR_catch KR_char KR_class /* KR_const */ KR_continue
%token KR_default KR_do KR_double
%token KR_else KR_extends
%token KR_false KR_final KR_finally KR_float KR_for /* KR_future */
/* %token KR_generic KR_goto */
%token KR_if KR_implements KR_import /* KR_inner */ KR_instanceof KR_int KR_interface
%token KR_long
%token KR_native KR_new KR_null
/* %token KR_operator KR_outer */
%token KR_package KR_private KR_protected KR_public
%token /* KR_rest */ KR_return
%token KR_short KR_static KR_super KR_switch KR_synchronized
%token KR_this KR_throw KR_throws KR_transient KR_true KR_try
%token /* KR_var */ KR_void KR_volatile
%token KR_while

%token TK_OP_ASSIGN TK_OPERATOR TK_IDENTIFIER TK_LITERAL
%token TK_DIM TK_INC_DEC

%start CompilationUnit

/* the standard if/then/else conflict */
/* %expect 1 */

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

TypeSpecifier
	: TypeName
	| TypeNameDims
	;

TypeNameDims
	: TypeName TK_DIM+
	;

TypeNameDot
	: NamePeriod
	| PrimitiveType '.'
	;

TypeName
	: PrimitiveType
	| NamePeriod TK_IDENTIFIER
	| TK_IDENTIFIER
	;

NamePeriod
	: TK_IDENTIFIER '.'
	| NamePeriod TK_IDENTIFIER '.'
	;

TypeNameList
	: TypeName / ','
	;

PrimitiveType
	: KR_boolean
	| KR_byte
	| KR_char
	| KR_double
	| KR_float
	| KR_int
	| KR_long
	| KR_short
	| KR_void
	;

CompilationUnit
	: PackageStatement [ImportStatements] [TypeDeclarations]
	|                   ImportStatements  [TypeDeclarations]
	|                                      TypeDeclarations
	;

PackageStatement
	: KR_package (TK_IDENTIFIER / '.') ';'
	;

TypeDeclarations
	: TypeDeclaration+
	;

TypeDeclaration
	: ClassDeclaration
	| InterfaceDeclaration
	;

ImportStatements
	: ImportStatement+
	;

ImportStatement
	: KR_import TK_IDENTIFIER ('.' TK_IDENTIFIER)* [".*"] ';'
	;
/*
QualifiedName
	: TK_IDENTIFIER / '.'
	;
*/
ClassDeclaration
        : [Modifiers] KR_class TK_IDENTIFIER [Super] [Interfaces] ClassBody
	;

Modifiers
	: Modifier+
	;

Modifier
	: KR_abstract
	| KR_final
	| KR_public
	| KR_protected
	| KR_private
	| KR_static
	| KR_transient
	| KR_volatile
	| KR_native
	| KR_synchronized
	;

Super
	: KR_extends TypeNameList
	;

Interfaces
	: KR_implements TypeNameList
	;

ClassBody
	: '{' FieldDeclaration* '}'
	;

FieldDeclaration
	: FieldVariableDeclaration
	| MethodDeclaration
	| ConstructorDeclaration
	| StaticInitializer
	;

FieldVariableDeclaration
	: [Modifiers] TypeSpecifier VariableDeclarators ';'
	;

VariableDeclarators
	: VariableDeclarator / ','
	;

VariableDeclarator
	: DeclaratorName ['=' VariableInitializer]
	;

VariableInitializer
	: Expression
        | '{' [ArrayInitializers] '}'
        ;

ArrayInitializers
	: VariableInitializer ( ',' [VariableInitializer] )*
	;

MethodDeclaration
	: [Modifiers] TypeSpecifier MethodDeclarator [Throws] MethodBody
	;

MethodDeclarator
	: DeclaratorName '(' [ParameterList] ')' TK_DIM*
	;

ParameterList
	: Parameter / ','
	;

Parameter
	: TypeSpecifier DeclaratorName
	;

DeclaratorName
	: TK_IDENTIFIER TK_DIM*
        ;

Throws
	: KR_throws TypeNameList
	;

MethodBody
	: Block
	| ';'
	;

ConstructorDeclaration
	: [Modifiers] ConstructorDeclarator [Throws] Block
	;

ConstructorDeclarator
	: TypeName '(' [ParameterList] ')'
	;

StaticInitializer
	: KR_static Block
	;

InterfaceDeclaration
	: [Modifiers] KR_interface TK_IDENTIFIER [ExtendsInterfaces] InterfaceBody
	;

ExtendsInterfaces
	: KR_extends TypeNameList
        ;

InterfaceBody
	: '{' FieldDeclaration+ '}'
	;

Block
	: '{' LocalVariableDeclarationOrStatement* '}'
        ;

LocalVariableDeclarationOrStatement
	: LocalVariableDeclarationStatement
	| Statement
	;

LocalVariableDeclarationStatement
	: TypeSpecifier VariableDeclarators ';'
	;

Statement
	: EmptyStatement
	| LabeledStatement
	| ExpressionStatement ';'
        | SelectionStatement
        | IterationStatement
	| JumpStatement
	| GuardingStatement
	| Block
	;

EmptyStatement
	: ';'
        ;

LabeledStatement
	: TK_IDENTIFIER ':' LocalVariableDeclarationOrStatement
        | KR_case ConstantExpression ':' LocalVariableDeclarationOrStatement
	| KR_default ':' LocalVariableDeclarationOrStatement
        ;

ExpressionStatement
	: Expression
	;

SelectionStatement
	: KR_if '(' Expression ')' Statement [KR_else Statement]
        | KR_switch '(' Expression ')' Block
        ;

IterationStatement
	: KR_while '(' Expression ')' Statement
	| KR_do Statement KR_while '(' Expression ')' ';'
	| KR_for '(' ForInit ForExpr [ForIncr] ')' Statement
	;

ForInit
	: ExpressionStatements ';'
	| LocalVariableDeclarationStatement
	| ';'
	;

ForExpr
	: [Expression] ';'
	;

ForIncr
	: ExpressionStatements
	;

ExpressionStatements
	: ExpressionStatement / ','
	;

JumpStatement
	: KR_break [TK_IDENTIFIER] ';'
        | KR_continue [TK_IDENTIFIER] ';'
	| KR_return [Expression] ';'
	| KR_throw Expression ';'
	;

GuardingStatement
	: KR_synchronized '(' Expression ')' Statement
	| KR_try Block Finally
	| KR_try Block Catches
	| KR_try Block Catches Finally
	;

Catches
	: Catch+
	;

Catch
	: KR_catch '(' TypeSpecifier [TK_IDENTIFIER] ')' Block
	;

Finally
	: KR_finally Block
	;

ArgumentList
	: Expression / ','
	;

PrimaryExpression
	: TK_LITERAL
	| KR_true | KR_false
	| KR_this
	| KR_null
	| KR_super
	| '(' Expression ')'
	;

PostfixExpression
	: PrimaryExpression Trailers

	| TypeName AltTrailers
	| TypeNameDot FollowsPeriod Trailers
	| TypeNameDot DimAllocation TypeTrailers
	| TypeNameDims TypeTrailers

	| KR_new TypeName AltTrailers
	| KR_new TypeNameDims TypeTrailers
        ;

DimAllocation
	: KR_new TypeNameDims
	;

PostfixDims
	: TK_DIM+ '.' KR_class
	;

FollowsPeriod
	: KR_this
	| KR_class
	| KR_super
	| KR_new TypeName NoPeriodsTrailer
	;

NoPeriodsTrailer
	: '[' Expression ']'
	| '(' [ArgumentList] ')'
	;

NoDimTrailer
	: NoPeriodsTrailer
	| '.' (FollowsPeriod | TK_IDENTIFIER)
	;

AnyTrailer
	: NoDimTrailer
	| PostfixDims
	;

Trailers
	: (AnyTrailer | DimAllocation NoDimTrailer)* [DimAllocation]
	;

AltTrailers
	: NoPeriodsTrailer Trailers
	|
	;

TypeTrailers
	: NoDimTrailer Trailers
	|
	;

CastablePrefixExpression
	: PostfixExpression [TK_INC_DEC]
	| LogicalUnaryOperator CastExpression
	;

LogicalUnaryOperator
	: '~'
	| '!'
	;

UnaryOperator
	: '+'
	| '-'
	| TK_INC_DEC
	;

/* note: we don't actually have grammar for a cast. we just rely on:
   (expr) (argument)
   as our parse match */
CastExpression
	: /* '(' PrimitiveType ')' CastExpression
	| '(' NamePeriod TK_IDENTIFIER TK_DIM TK_DIM* ')' CastablePrefixExpression
	| '(' NamePeriod TK_IDENTIFIER ')' CastablePrefixExpression
	| '(' TK_IDENTIFIER TK_DIM TK_DIM* ')' CastablePrefixExpression
	| '(' TK_IDENTIFIER ')' CastablePrefixExpression
	| */ UnaryOperator CastExpression
	| CastablePrefixExpression
	;

BinaryExpression
	: CastExpression
	| BinaryExpression TK_BINARY CastExpression
	| BinaryExpression KR_instanceof TypeSpecifier
	;

ConditionalExpression
	: BinaryExpression
	| BinaryExpression '?' Expression ':' ConditionalExpression
	;

AssignmentExpression
	: ConditionalExpression [AssignmentOperator AssignmentExpression]
	;

AssignmentOperator
	: '='
	| TK_OP_ASSIGN
	;

Expression
	: AssignmentExpression
        ;

ConstantExpression
	: ConditionalExpression
	;

/*
TK_OPERATOR : OP_LOR | OP_LAND
	    | OP_EQ | OP_NE | OP_LE | OP_GE
	    | OP_SHL | OP_SHR | OP_SHRR
	    ;
*/
TK_BINARY : TK_OPERATOR | '+' | '-' | '*'
