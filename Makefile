CC=g++
SCRAM := $(shell command -v scram)
ifdef SCRAM
	PYINC=-I$(shell $(SCRAM) tool tag python3 INCLUDE)
else
	PYINC=$(shell python3-config --includes)
endif
OSXFLAG=$(shell uname|grep -q Darwin && echo "-undefined dynamic_lookup")
CFLAGS=--std=c++17 -O3 -Wall -fPIC -Irapidjson/include -Ipybind11/include $(PYINC) -Iinclude

all: data/schemav1.json demo libcorrection

data/%.json: correctionlib/%.py
	mkdir -p data
	python3 $<

build/%.o: src/%.cc
	mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@

demo: build/demo.o build/correction.o
	$(CC) $^ -o $@

libcorrection: build/python.o build/correction.o
	$(CC) -fPIC -shared $(OSXFLAG) $^ -o $@$(shell python3-config --extension-suffix)

clean:
	rm -rf data/schemav*
	rm -rf build/*
	rm -f demo
	rm -f libcorrection.*

.PHONY: all clean
