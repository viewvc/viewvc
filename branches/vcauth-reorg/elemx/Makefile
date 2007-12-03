TARGETS = python/elx-python java/elx-java

all : $(TARGETS)

CFLAGS = -g -Wpointer-arith -Wwrite-strings -Wshadow -Wall
CPPFLAGS = -Ipython -Ijava -I.

# the scanner depends on tokens generated from python.y
python/scanner.c : python/python.c

# the keywords also need the tokens in python.h
python/py_keywords.c : python/python.c

# we need the scanner tokens in py_scan.h and keywords in py_keywords.h
python/elx-python.o : python/elx-python.c python/py_keywords.c

# we need java.[ch] generated first to get the tokens in java.h
java/j_scan.c : java/java.c java/j_keywords.c

# the keywords also need the tokens in java.h
java/j_keywords.c : java/java.c

# we need the scanner tokens in j_scan.h and keywords in j_keywords.h
java/elx-java.o : java/elx-java.c java/j_keywords.c java/java.c


python/elx-python : python/elx-python.o python/scanner.o python/python.o \
			python/py_keywords.o elx-common.o
	$(CC) -o $@ $^

java/elx-java : java/elx-java.o java/j_scan.o java/java.o java/j_keywords.o \
			elx-common.o
	$(CC) -o $@ $^

clean :
	rm -f *.o
	rm -f python/*.o python/python.[ch] python/py_keywords.[ch]
	rm -f java/*.o java/java.[ch] java/j_keywords.[ch] java/j_scan.[ch]
	rm -f python/*.output java/*.output
	rm -f $(TARGETS)

.SUFFIXES:
.SUFFIXES: .c .y .shilka .o

%.c : %.y
	@d="`echo $@ | sed 's/\.c//'`" ; \
	echo msta -d -enum -v -o $$d $< ; \
	msta -d -enum -v -o $$d $<

%.c : %.shilka
	@d="`echo $@ | sed 's,/[^/]*$$,,'`" ; \
	f="`echo $< | sed 's,.*/,,'`" ; \
	echo shilka -length -no-definitions -interface $$f ; \
	(cd $$d && shilka -length -no-definitions -interface $$f)
