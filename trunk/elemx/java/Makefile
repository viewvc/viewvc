all : elx-java

CFLAGS = -g -Wpointer-arith -Wwrite-strings -Wshadow -Wall -DYYDEBUG=1
CPPFLAGS = -I..

# we need java.[ch] generated first to get the tokens in java.h
j_scan.o : j_scan.c java.c j_keywords.c

# the keywords also need the tokens in java.h
j_keywords.o : j_keywords.c java.c

# we need the scanner tokens in j_scan.h and keywords in j_keywords.h
elx-java.o : elx-java.c j_keywords.c java.c

elx-java : elx-java.o j_scan.o java.o j_keywords.o
	$(CC) -o $@ $^

clean :
	rm -f *.o java.[ch] j_keywords.[ch] j_scan.[ch] elx-java
	rm -f *.output

.SUFFIXES:
.SUFFIXES: .c .y .shilka .o

%.c : %.y
	msta -d -enum -v $<

%.c : %.shilka
	shilka -length -no-definitions -interface $<
