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
RW_SRC?=examples/rw_cases.c
RW_HDR?=examples/rw_cases.h
RW_OUT?=$(OUT)/rw_cases
RW_FUNCS=rw_array_read_write rw_array_compound rw_array_increment \
	rw_pointer_read rw_pointer_write rw_pointer_inout \
	rw_struct_field_read rw_struct_field_write rw_struct_field_inout rw_struct_array_read \
	rw_global_read rw_global_write rw_global_inout \
	rw_call_with_pointer rw_conditional_read rw_dynamic_index rw_content_dependent_loop

.PHONY: all analyze generate capture replay test clean show-report show-warnings sample-run test-rw-cases

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

test-rw-cases:
	@mkdir -p $(RW_OUT)
	@for func in $(RW_FUNCS); do \
		$(PYTHON) tools/analyze.py $(RW_SRC) $(RW_HDR) $$func $(RW_OUT) > $(RW_OUT)/$$func.log || exit 1; \
		backend=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(r.get('backend'))"); \
		warnings=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(len(r.get('warnings', [])))"); \
		annotations=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(len(r.get('annotation_required', [])))"); \
		printf "%-32s backend=%s warnings=%s annotations=%s\n" "$$func" "$$backend" "$$warnings" "$$annotations"; \
	done

clean:
	rm -rf generated/* testcases/case_001
