CC=gcc
PYTHON?=python3
CFLAGS=-Wall -Wextra -std=c11 -Iexamples
SRC?=examples/sample.c
HDR?=examples/sample.h
FUNC?=compute
OUT?=generated
REPORT=$(OUT)/$(FUNC)_report.json
ANNOTATIONS=$(OUT)/$(FUNC)_annotations.required.json
HARNESS_CAPTURE=$(OUT)/harness_$(FUNC)_capture.c
HARNESS_REPLAY=$(OUT)/harness_$(FUNC)_replay.c
TRACE_CAPTURE=$(OUT)/trace_$(FUNC)_capture.c
TRACE_REPLAY=$(OUT)/trace_$(FUNC)_replay.c
CAPTURE_BIN=$(OUT)/capture_$(FUNC)
REPLAY_BIN=$(OUT)/replay_$(FUNC)
TRACE_CAPTURE_BIN=$(OUT)/trace_capture_$(FUNC)
TRACE_REPLAY_BIN=$(OUT)/trace_replay_$(FUNC)
SAMPLE_BIN=$(OUT)/sample_main
RW_SRC?=examples/rw_cases.c
RW_HDR?=examples/rw_cases.h
RW_OUT?=$(OUT)/rw_cases
MAP_SRC_DIR?=examples
CALL_MAP?=$(OUT)/call_map.json
CALL_MAP_HTML?=$(OUT)/call_map.html
RW_FUNCS=rw_array_read_write rw_array_compound rw_array_increment \
	rw_pointer_read rw_pointer_write rw_pointer_inout \
	rw_struct_field_read rw_struct_field_write rw_struct_field_inout rw_struct_array_read \
	rw_global_read rw_global_write rw_global_inout \
	rw_call_with_pointer rw_conditional_read rw_dynamic_index rw_content_dependent_loop \
	rw_typedef_array rw_nested_struct_field rw_macro_write rw_function_pointer_call
RW_FUNCS+=rw_local_struct_temp rw_local_struct_output \
	rw_local_address_escape_call rw_local_address_escape_global rw_local_address_escape_return \
	rw_local_static_state rw_module_global_vector_inout

.PHONY: all analyze generate capture replay test trace-generate trace-capture-build trace-replay-build trace-capture trace-replay trace-test clean show-report show-warnings sample-run map-calls call-map-html test-rw-cases test-reports test-trace

all: test

analyze:
	$(PYTHON) tools/analyze.py $(SRC) $(HDR) $(FUNC) $(OUT)

generate: analyze
	$(PYTHON) tools/generate_harness.py $(REPORT) $(OUT)

trace-generate: analyze
	$(PYTHON) tools/generate_harness.py $(REPORT) $(OUT) --mode trace

capture_build: generate $(HARNESS_CAPTURE) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(CAPTURE_BIN) $(HARNESS_CAPTURE) $(SRC)

replay_build: generate $(HARNESS_REPLAY) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(REPLAY_BIN) $(HARNESS_REPLAY) $(SRC)

capture: capture_build
	./$(CAPTURE_BIN)

replay: replay_build
	./$(REPLAY_BIN)

test: capture replay

trace-capture-build: trace-generate $(TRACE_CAPTURE) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(TRACE_CAPTURE_BIN) $(TRACE_CAPTURE) $(SRC)

trace-replay-build: trace-generate $(TRACE_REPLAY) $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(TRACE_REPLAY_BIN) $(TRACE_REPLAY) $(SRC)

trace-capture: trace-capture-build
	./$(TRACE_CAPTURE_BIN)

trace-replay: trace-replay-build
	./$(TRACE_REPLAY_BIN)

trace-test: trace-capture trace-replay

sample-run:
	$(CC) $(CFLAGS) -o $(SAMPLE_BIN) examples/sample_main.c examples/sample.c
	./$(SAMPLE_BIN)

show-report: analyze
	$(PYTHON) -m json.tool $(REPORT)

show-warnings: analyze
	@if [ -f $(ANNOTATIONS) ]; then \
		$(PYTHON) -m json.tool $(ANNOTATIONS); \
	else \
		echo "No required annotations for $(FUNC)"; \
	fi

map-calls:
	$(PYTHON) tools/map_call.py $(MAP_SRC_DIR) $(CALL_MAP)

call-map-html: map-calls
	$(PYTHON) tools/call_map_html.py $(CALL_MAP) $(CALL_MAP_HTML)

test-rw-cases:
	@mkdir -p $(RW_OUT)
	@for func in $(RW_FUNCS); do \
		$(PYTHON) tools/analyze.py $(RW_SRC) $(RW_HDR) $$func $(RW_OUT) > $(RW_OUT)/$$func.log || exit 1; \
		backend=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(r.get('backend'))"); \
		warnings=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(len(r.get('warnings', [])))"); \
		annotations=$$($(PYTHON) -c "import json; r=json.load(open('$(RW_OUT)/' + '$$func' + '_report.json')); print(len(r.get('annotation_required', [])))"); \
		printf "%-32s backend=%s warnings=%s annotations=%s\n" "$$func" "$$backend" "$$warnings" "$$annotations"; \
	done

test-reports:
	$(PYTHON) tools/test_reports.py

test-trace:
	$(PYTHON) tools/test_trace.py

clean:
	rm -rf generated/* testcases/*_case_001 testcases/*_trace_001 testcases/case_001
