PYTHON ?= python3

.PHONY: all test benchmark

all: test

test:
	$(PYTHON) -m unittest discover -s tests

benchmark:
	$(PYTHON) benchmarks/benchmark.py
