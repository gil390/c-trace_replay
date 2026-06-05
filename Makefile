CC=gcc
CFLAGS=-Wall -Wextra -std=c11 -Iexamples
SRC?=examples/sample.c
HDR?=examples/sample.h
FUNC?=compute
OUT?=generated
REPORT=$(OUT)/$(FUNC)_report.json
ANNOTATIONS=$(OUT)/$(FUNC)_annotations.required.json
HARNESS_CAPTURE=$(OUT)/harness_compute_capture.c
HARNESS_REPLAY=$(OUT)/harness_compute_replay.c

.PHONY: all analyze generate capture replay test clean show-report show-warnings sample-run

all: test

analyze:
	python3 tools/analyze.py $(SRC) $(HDR) $(FUNC) $(OUT)

generate: analyze
	python3 tools/generate_harness.py $(REPORT) $(OUT)

capture_compute: generate $(HARNESS_CAPTURE) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o capture_compute $(HARNESS_CAPTURE) $(SRC)

replay_compute: generate $(HARNESS_REPLAY) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o replay_compute $(HARNESS_REPLAY) $(SRC)

capture: capture_compute
	./capture_compute

replay: replay_compute
	./replay_compute

test: capture replay

sample-run:
	$(CC) $(CFLAGS) -o sample_main examples/sample_main.c examples/sample.c
	./sample_main

show-report: analyze
	python3 -m json.tool $(REPORT)

show-warnings: analyze
	python3 -m json.tool $(ANNOTATIONS)

clean:
	rm -f capture_compute replay_compute sample_main
	rm -rf generated/* testcases/case_001
