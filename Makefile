.PHONY: all cpp python test test-cpp test-python benchmark clean

all: cpp

cpp:
	$(MAKE) -C cpp

test: test-cpp test-python

test-cpp:
	$(MAKE) -C cpp test

test-python:
	python3 -m unittest discover -s tests

benchmark:
	$(MAKE) -C cpp run_benchmark

clean:
	$(MAKE) -C cpp clean
	find . -type d -name "__pycache__" -exec rm -rf {} +
