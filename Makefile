all: data/schemav1.json demo
.PHONY: all

data/%.json: correctionlib/%.py
	mkdir -p data
	python $<

demo: src/demo.cc
	g++ --std=c++17 -Irapidjson/include -Ipybind11/include -Iinclude src/demo.cc -o $@

clean:
	rm -rf data/*
	rm -f demo
