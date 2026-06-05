#!/usr/bin/env python3
import json, sys
from pathlib import Path

if len(sys.argv) != 3:
    print('usage: generate_harness.py <report.json> <outdir>', file=sys.stderr)
    sys.exit(2)
report = json.loads(Path(sys.argv[1]).read_text())
outdir = Path(sys.argv[2]); outdir.mkdir(parents=True, exist_ok=True)
if report.get('annotation_required'):
    print('GENERATION STOPPED: unresolved annotations required')
    for a in report['annotation_required']:
        print(f" - {a['symbol']}: {a['reason']}")
    sys.exit(1)

common = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../examples/sample.h"

static int save_bin(const char *path, const void *data, size_t size)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    if (fwrite(data, 1, size, f) != size) { fclose(f); return -1; }
    fclose(f);
    return 0;
}

static int load_bin(const char *path, void *data, size_t size)
{
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    if (fread(data, 1, size, f) != size) { fclose(f); return -1; }
    fclose(f);
    return 0;
}

static void dump_u8(const char *label, const uint8_t *p, size_t n)
{
    printf("%s:", label);
    for (size_t i=0; i<n; i++) printf(" %u", p[i]);
    printf("\n");
}
'''

capture = common + r'''
int main(void)
{
    system("mkdir -p testcases/case_001");

    Context ctx = {
        .table = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16},
        .scale = 2
    };
    size_t len = 8;
    uint8_t input[8] = {10,20,30,40,50,60,70,80};
    uint8_t output[8] = {0};

    save_bin("testcases/case_001/ctx_before.bin", &ctx, sizeof(ctx));
    save_bin("testcases/case_001/input_before.bin", input, len);
    save_bin("testcases/case_001/g_mode_before.bin", &g_mode, sizeof(g_mode));
    save_bin("testcases/case_001/g_counter_before.bin", &g_counter, sizeof(g_counter));

    int ret = compute(&ctx, input, output, len);

    save_bin("testcases/case_001/output_expected.bin", output, len);
    save_bin("testcases/case_001/g_counter_after.bin", &g_counter, sizeof(g_counter));
    save_bin("testcases/case_001/return_expected.bin", &ret, sizeof(ret));
    save_bin("testcases/case_001/len.bin", &len, sizeof(len));

    printf("CAPTURE OK: testcase written in testcases/case_001\n");
    dump_u8("expected output", output, len);
    return 0;
}
'''

replay = common + r'''
int main(void)
{
    Context ctx;
    size_t len = 0;
    uint8_t input[256] = {0};
    uint8_t output[256] = {0};
    uint8_t expected[256] = {0};
    uint32_t expected_counter = 0;
    int expected_ret = 0;

    if (load_bin("testcases/case_001/len.bin", &len, sizeof(len)) != 0 || len > sizeof(input)) {
        printf("REPLAY FAIL: cannot load len\n"); return 1;
    }
    if (load_bin("testcases/case_001/ctx_before.bin", &ctx, sizeof(ctx)) != 0) {
        printf("REPLAY FAIL: cannot load ctx\n"); return 1;
    }
    if (load_bin("testcases/case_001/input_before.bin", input, len) != 0) {
        printf("REPLAY FAIL: cannot load input\n"); return 1;
    }
    if (load_bin("testcases/case_001/g_mode_before.bin", &g_mode, sizeof(g_mode)) != 0) {
        printf("REPLAY FAIL: cannot load g_mode\n"); return 1;
    }
    if (load_bin("testcases/case_001/g_counter_before.bin", &g_counter, sizeof(g_counter)) != 0) {
        printf("REPLAY FAIL: cannot load g_counter\n"); return 1;
    }
    if (load_bin("testcases/case_001/output_expected.bin", expected, len) != 0) {
        printf("REPLAY FAIL: cannot load expected output\n"); return 1;
    }
    if (load_bin("testcases/case_001/g_counter_after.bin", &expected_counter, sizeof(expected_counter)) != 0) {
        printf("REPLAY FAIL: cannot load expected counter\n"); return 1;
    }
    if (load_bin("testcases/case_001/return_expected.bin", &expected_ret, sizeof(expected_ret)) != 0) {
        printf("REPLAY FAIL: cannot load expected return\n"); return 1;
    }

    int ret = compute(&ctx, input, output, len);

    int ok = 1;
    if (ret != expected_ret) {
        printf("REPLAY FAIL: return=%d expected=%d\n", ret, expected_ret);
        ok = 0;
    }
    if (g_counter != expected_counter) {
        printf("REPLAY FAIL: g_counter=%u expected=%u\n", g_counter, expected_counter);
        ok = 0;
    }
    if (memcmp(output, expected, len) != 0) {
        printf("REPLAY FAIL: output mismatch\n");
        dump_u8("expected", expected, len);
        dump_u8("got     ", output, len);
        ok = 0;
    }

    if (ok) printf("REPLAY PASS\n");
    return ok ? 0 : 1;
}
'''
(outdir/'harness_compute_capture.c').write_text(capture)
(outdir/'harness_compute_replay.c').write_text(replay)
print('GENERATE OK')
