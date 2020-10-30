all: data/schemav1.json demo
.PHONY: all

include/rapidjson.pin:
	curl https://github.com/Tencent/rapidjson/archive/v1.1.0.tar.gz -L | tar xz \
		&& cp -r rapidjson-1.1.0/include/rapidjson include/ \
		&& rm -rf rapidjson-1.1.0
	touch $@

data/%.json: correctionlib/%.py
	mkdir -p data
	python $<

demo: src/demo.cc include/rapidjson.pin
	g++ --std=c++11 -Iinclude src/demo.cc -o $@

clean:
	rm -rf include/rapidjson*
	rm -rf data/*
	rm -f demo
