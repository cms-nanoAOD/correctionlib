PYTHON=python
PYEXT=$(shell $(PYTHON)-config --extension-suffix 2>/dev/null || echo ".so")
PYINC=$(shell $(PYTHON)-config --includes)
DARWIN := $(shell uname|grep Darwin)
ifdef DARWIN
	LIBLDFLAG=-install_name @rpath/libcorrectionlib.so
	PYLDFLAG=-undefined dynamic_lookup -Wl,-rpath,'@loader_path/lib'
else
	LIBLDFLAG=
	PYLDFLAG=-Wl,-rpath,'$$ORIGIN/lib'
endif
OSXFLAG=$(shell uname|grep -q Darwin && echo "-undefined dynamic_lookup")
# lwtnn needs header-only Eigen and Boost (property_tree); point these at your installation
EIGEN_INC ?= /usr/include/eigen3
BOOST_INC ?= /usr/include
CFLAGS=--std=c++17 -O3 -Wall -fPIC -Irapidjson/include -Ipybind11/include -Icpp-peglib -Ixxhash -Ipcg-cpp/include $(PYINC) -Iinclude -Ilwtnn/include -I$(EIGEN_INC) -I$(BOOST_INC)
LWTNN_SRCS=Exceptions LightweightNeuralNetwork LightweightGraph NanReplacer FastInputPreprocessor FastGraph Stack lightweight_nn_streamers parse_json
LWTNN_OBJS=$(patsubst %,build/lwtnn_%.o,$(LWTNN_SRCS))
PREFIX ?= correctionlib
# version from the nearest tag, falling back to 0.0.0 when tags are unavailable (e.g. shallow clones)
STRVER=$(or $(shell git describe --tags 2>/dev/null),0.0.0)
MAJOR=$(or $(shell echo $(STRVER)|sed -n "s/^v\?\([0-9]\+\)\..*/\1/p"),0)
MINOR=$(or $(shell echo $(STRVER)|sed -n "s/^v\?[0-9]\+\.\([0-9]\+\).*/\1/p"),0)

.PHONY: build all clean install pythonbinding

all: pythonbinding

include/correctionlib_version.h: include/version.h.in
	sed "s/@CORRECTIONLIB_SKBUILD_PROJECT_VERSION@/$(STRVER)/;s/@CORRECTIONLIB_VERSION_MAJOR@/$(MAJOR)/;s/@CORRECTIONLIB_VERSION_MINOR@/$(MINOR)/" $< > $@

build/%.o: src/%.cc include/correctionlib_version.h
	mkdir -p build
	$(CXX) $(CFLAGS) -c $< -o $@

build/lwtnn_%.o: lwtnn/src/%.cxx
	mkdir -p build
	$(CXX) $(CFLAGS) -w -c $< -o $@

lib/libcorrectionlib.so: build/correction.o build/formula_ast.o build/detail_impl.o build/lwtnn.o $(LWTNN_OBJS)
	mkdir -p lib
	$(CXX) -pthread -lz -fPIC -shared $(LIBLDFLAG) $^ -o $@

pythonbinding: build/python.o lib/libcorrectionlib.so
	$(CXX) -fPIC -shared $(PYLDFLAG) $< -Llib -lcorrectionlib -o _core$(PYEXT)
	touch __init__.py

install: pythonbinding
	mkdir -p $(PREFIX)/include
	mkdir -p $(PREFIX)/lib
	install -m 644 include/correction.h $(PREFIX)/include
	install -m 644 include/correctionlib_version.h $(PREFIX)/include
	install -m 755 _core$(PYEXT) $(PREFIX)
	install -m 755 lib/libcorrectionlib.so $(PREFIX)/lib
	install -m 644 __init__.py $(PREFIX)

clean:
	rm -rf build lib
	rm -f demo
	rm -f data/examples.json*
	rm -f include/correctionlib_version.h
	rm -f __init__.py _core*
