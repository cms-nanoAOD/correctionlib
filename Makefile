PYTHON=python
PYEXT=$(shell $(PYTHON)-config --extension-suffix 2>/dev/null || echo ".so")
SCRAM := $(shell command -v scram)
ifdef SCRAM
	PYINC=-I$(shell $(SCRAM) tool tag $(PYTHON) INCLUDE)
else
	PYINC=$(shell $(PYTHON)-config --includes)
endif
OSXFLAG=$(shell uname|grep -q Darwin && echo "-undefined dynamic_lookup")
CFLAGS=--std=c++17 -O3 -Wall -fPIC -Irapidjson/include -Ipybind11/include -Icpp-peglib $(PYINC) -Iinclude
LDFLAGS=-pthread

.PHONY: build all clean

all: demo

build/%.o: src/%.cc
	mkdir -p build
	$(CXX) $(CFLAGS) -c $< -o $@

demo: build/demo.o build/correction.o build/formula_ast.o
	$(CXX) $(LDFLAGS) $^ -o $@

correctionlib: build/python.o build/correction.o build/formula_ast.o
	mkdir -p correctionlib
	$(CXX) $(LDFLAGS) -fPIC -shared $(OSXFLAG) $^ -o correctionlib/_core$(PYEXT)
	touch correctionlib/__init__.py

clean:
	rm -rf build
	rm -f demo
	rm -rf correctionlib
