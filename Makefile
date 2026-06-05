CC=gcc
PYTHON?=python3
CFLAGS=-Wall -Wextra -std=c11 -Iexamples
SRC?=examples/sample.c
HDR?=examples/sample.h
FUNC?=compute
OUT?=generated
REPORT=$(OUT)/$(FUNC)_report.json
ANNOTATIONS=$(OUT)/$(FUNC)_annotations.required.json
HARNESS_CAPTURE=$(OUT)/harness_compute_capture.c
HARNESS_REPLAY=$(OUT)/harness_compute_replay.c
CAPTURE_BIN=$(OUT)/capture_compute
REPLAY_BIN=$(OUT)/replay_compute
SAMPLE_BIN=$(OUT)/sample_main

.PHONY: all analyze generate capture replay test clean show-report show-warnings sample-run

all: test

analyze:
	$(PYTHON) tools/analyze.py $(SRC) $(HDR) $(FUNC) $(OUT)

generate: analyze
	$(PYTHON) tools/generate_harness.py $(REPORT) $(OUT)

capture_compute: generate $(HARNESS_CAPTURE) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(CAPTURE_BIN) $(HARNESS_CAPTURE) $(SRC)

replay_compute: generate $(HARNESS_REPLAY) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(REPLAY_BIN) $(HARNESS_REPLAY) $(SRC)

capture: capture_compute
	./$(CAPTURE_BIN)

replay: replay_compute
	./$(REPLAY_BIN)

test: capture replay

sample-run:
	$(CC) $(CFLAGS) -o $(SAMPLE_BIN) examples/sample_main.c examples/sample.c
	./$(SAMPLE_BIN)

show-report: analyze
	$(PYTHON) -m json.tool $(REPORT)

show-warnings: analyze
	$(PYTHON) -m json.tool $(ANNOTATIONS)

clean:
	rm -rf generated/* testcases/case_001
