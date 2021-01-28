PYTHON=python3
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

all: build demo libcorrection

build:
	mkdir -p build

build/%.o: src/%.cc
	$(CXX) $(CFLAGS) -c $< -o $@

demo: build/demo.o build/correction.o
	$(CXX) $(LDFLAGS) $^ -o $@

libcorrection: build/python.o build/correction.o
	$(CXX) $(LDFLAGS) -fPIC -shared $(OSXFLAG) $^ -o $@$(PYEXT)

clean:
	rm -rf build
	rm -f demo
	rm -f libcorrection*

.PHONY: all clean
