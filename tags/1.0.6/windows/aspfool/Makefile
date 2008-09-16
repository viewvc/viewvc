aspfool.dll : aspfool.o aspfool.def
	g++ -shared -o aspfool.dll aspfool.o --def aspfool.def -Wl,--add-stdcall-alias

distribution.o : aspfool.cpp
	g++ -O3 -o aspfool.o -c aspfool.cpp

clean :
	rm -f aspfool.o aspfool.dll
