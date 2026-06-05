CC=gcc
CFLAGS=-Wall -Wextra -std=c11 -Iexamples

.PHONY: all analyze generate capture replay test clean show-report show-warnings sample-run

all: test

analyze:
	python3 tools/analyze.py examples/sample.c examples/sample.h compute generated

generate: analyze
	python3 tools/generate_harness.py generated/compute_report.json generated

capture_compute: generate generated/harness_compute_capture.c examples/sample.c examples/sample.h
	$(CC) $(CFLAGS) -o capture_compute generated/harness_compute_capture.c examples/sample.c

replay_compute: generate generated/harness_compute_replay.c examples/sample.c examples/sample.h
	$(CC) $(CFLAGS) -o replay_compute generated/harness_compute_replay.c examples/sample.c

capture: capture_compute
	./capture_compute

replay: replay_compute
	./replay_compute

test: capture replay

sample-run:
	$(CC) $(CFLAGS) -o sample_main examples/sample_main.c examples/sample.c
	./sample_main

show-report: analyze
	python3 -m json.tool generated/compute_report.json

show-warnings: analyze
	python3 -m json.tool generated/annotations.required.json

clean:
	rm -f capture_compute replay_compute sample_main
	rm -rf generated/* testcases/case_001
