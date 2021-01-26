CC=g++
PYTHON=python3
PYEXT=$(shell $(PYTHON)-config --extension-suffix 2>/dev/null || echo ".so")
SCRAM := $(shell command -v scram)
ifdef SCRAM
	PYINC=-I$(shell $(SCRAM) tool tag $(PYTHON) INCLUDE)
else
	PYINC=$(shell $(PYTHON)-config --includes)
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
	$(CC) -fPIC -shared $(OSXFLAG) $^ -o $@$(PYEXT)

clean:
	rm -rf data/schemav*
	rm -rf build/*
	rm -f demo
	rm -f libcorrection.*

.PHONY: all clean
