all : elx-python

CFLAGS = -g -Wpointer-arith -Wwrite-strings -Wshadow -Wall
CPPFLAGS = -I..

# the scanner depends on tokens generated from python.y
scanner.c : python.c

# the keywords also need the tokens in python.h
py_keywords.c : python.c

# we need the scanner tokens in py_scan.h and keywords in py_keywords.h
elx-python.o : elx-python.c py_keywords.c

elx-python : elx-python.o scanner.o python.o py_keywords.o
	gcc -o $@ $^

clean :
	rm -f *.o python.[ch] py_keywords.[ch] elx-python
	rm -f *.output

.SUFFIXES:
.SUFFIXES: .c .y .shilka .o

%.c : %.y
	msta -d -enum -v $<

%.c : %.shilka
	shilka -length -no-definitions -interface $<
