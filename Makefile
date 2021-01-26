CC=g++
CFLAGS=--std=c++17 -Wall -Irapidjson/include -Ipybind11/include $(shell python3-config --includes) -Iinclude

all: data/schemav1.json demo libcorrection

data/%.json: correctionlib/%.py
	mkdir -p data
	python $<

build/%.o: src/%.cc
	mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@

demo: build/demo.o build/correction.o
	$(CC) $^ -o $@

libcorrection: build/python.o build/correction.o
	$(CC) -fPIC -shared -undefined dynamic_lookup $^ -o $@$(shell python3-config --extension-suffix)

clean:
	rm -rf data/*
	rm -rf build/*
	rm -f demo

.PHONY: all clean
