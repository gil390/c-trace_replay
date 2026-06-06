#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print('usage: generate_harness.py <report.json> <outdir>', file=sys.stderr)
    sys.exit(2)

report_path = Path(sys.argv[1])
report = json.loads(report_path.read_text())
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)

func = report['function']
case_path = Path('testcases') / f'{func}.case.json'

if report.get('annotation_required'):
    print('GENERATION STOPPED: unresolved annotations required')
    for annotation in report['annotation_required']:
        print(f" - {annotation['symbol']}: {annotation['reason']}")
    sys.exit(1)

if not case_path.exists():
    print(f'GENERATION STOPPED: missing case description {case_path}', file=sys.stderr)
    sys.exit(1)

case = json.loads(case_path.read_text())
bindings = case.get('bindings', {})


def c_string(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def safe_name(text):
    return re.sub(r'[^A-Za-z0-9_]', '_', text).strip('_') or 'value'


def binding_key(symbol):
    if symbol in bindings:
        return symbol
    root = symbol.split('->')[0].split('.')[0]
    if root in bindings:
        return root
    return None


def binding_for(symbol):
    key = binding_key(symbol)
    return bindings.get(key) if key else None


def binding_id(symbol):
    key = binding_key(symbol)
    return safe_name(key or symbol)


def unique_symbols(accesses):
    seen = set()
    result = []
    for access in accesses:
        symbol = access['symbol']
        key = binding_key(symbol)
        dedupe_key = key or symbol
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(symbol)
    return result


def declaration(var, zero=False):
    init = '{0}' if zero else var.get('init')
    suffix = f"[{var['array']}]" if 'array' in var else ''
    if init is None:
        return f"    {var['type']} {var['name']}{suffix};"
    return f"    {var['type']} {var['name']}{suffix} = {init};"


def require_binding(symbol):
    binding = binding_for(symbol)
    if not binding:
        raise SystemExit(f'GENERATION STOPPED: no binding for symbol {symbol}')
    return binding


def save_line(case_dir, symbol, phase):
    binding = require_binding(symbol)
    ident = binding_id(symbol)
    return f'    save_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]});'


def load_line(case_dir, symbol, phase):
    binding = require_binding(symbol)
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_{phase}\\n"); return 1; }}'


def expected_decl(symbol):
    binding = require_binding(symbol)
    ident = binding_id(symbol)
    return f'    uint8_t expected_{ident}[{binding["size"]}];'


def expected_load_line(case_dir, symbol):
    binding = require_binding(symbol)
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_expected.bin", expected_{ident}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_expected\\n"); return 1; }}'


def compare_line(symbol):
    binding = require_binding(symbol)
    ident = binding_id(symbol)
    return f'''
    if (memcmp({binding["expr"]}, expected_{ident}, {binding["size"]}) != 0) {{
        printf("REPLAY FAIL: {ident} mismatch\\n");
        ok = 0;
    }}'''


header_path = Path(report.get('header', 'examples/sample.h'))
include_path = Path('../') / header_path
case_dir = case.get('case_dir', f'testcases/{func}_case_001')
return_type = report.get('return_type') or 'int'
is_void = return_type == 'void'
call_args = ', '.join(case.get('arguments') or [p['name'] for p in report.get('parameters', [])])
before_symbols = unique_symbols(report.get('inferred_captures', {}).get('before', []))
for extra in case.get('extra_before', []):
    if extra not in before_symbols:
        before_symbols.append(extra)
after_symbols = unique_symbols(report.get('access_sets', {}).get('write_set', []))

common = f'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "{c_string(str(include_path))}"

static int save_bin(const char *path, const void *data, size_t size)
{{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    if (fwrite(data, 1, size, f) != size) {{ fclose(f); return -1; }}
    fclose(f);
    return 0;
}}

static int load_bin(const char *path, void *data, size_t size)
{{
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    if (fread(data, 1, size, f) != size) {{ fclose(f); return -1; }}
    fclose(f);
    return 0;
}}

static void dump_u8(const char *label, const uint8_t *p, size_t n)
{{
    printf("%s:", label);
    for (size_t i=0; i<n; i++) printf(" %u", p[i]);
    printf("\\n");
}}
'''

capture_decls = '\n'.join(declaration(var) for var in case.get('variables', []))
replay_decls = '\n'.join(declaration(var) for var in case.get('variables', []))
before_saves = '\n'.join(save_line(case_dir, symbol, 'before') for symbol in before_symbols)
before_loads = '\n'.join(load_line(case_dir, symbol, 'before') for symbol in before_symbols)
after_saves = '\n'.join(save_line(case_dir, symbol, 'expected') for symbol in after_symbols)
expected_decls = '\n'.join(expected_decl(symbol) for symbol in after_symbols)
expected_loads = '\n'.join(expected_load_line(case_dir, symbol) for symbol in after_symbols)
comparisons = '\n'.join(compare_line(symbol) for symbol in after_symbols)
dump_lines = []
for symbol in after_symbols:
    binding = require_binding(symbol)
    if binding.get('dump_u8'):
        dump_lines.append(f'    dump_u8("expected {binding_id(symbol)}", (const uint8_t *){binding["expr"]}, {binding["size"]});')
dumps = '\n'.join(dump_lines)

capture_call = (
    f'    {func}({call_args});'
    if is_void else
    f'    {return_type} ret = {func}({call_args});'
)
replay_call = (
    f'    {func}({call_args});'
    if is_void else
    f'    {return_type} ret = {func}({call_args});'
)
return_save = '' if is_void else f'    save_bin("{case_dir}/return_expected.bin", &ret, sizeof(ret));'
return_decl = '' if is_void else f'    {return_type} expected_ret;'
return_load = '' if is_void else f'    if (load_bin("{case_dir}/return_expected.bin", &expected_ret, sizeof(expected_ret)) != 0) {{ printf("REPLAY FAIL: cannot load return_expected\\n"); return 1; }}'
return_compare = '' if is_void else '''
    if (ret != expected_ret) {
        printf("REPLAY FAIL: return mismatch\\n");
        ok = 0;
    }'''

capture = common + f'''
int main(void)
{{
    system("mkdir -p {case_dir}");

{capture_decls}

{before_saves}

{capture_call}

{after_saves}
{return_save}

    printf("CAPTURE OK: testcase written in {case_dir}\\n");
{dumps}
    return 0;
}}
'''

replay = common + f'''
int main(void)
{{
{replay_decls}
{return_decl}

{before_loads}

{expected_decls}
{expected_loads}
{return_load}

{replay_call}

    int ok = 1;
{return_compare}
{comparisons}

    if (ok) printf("REPLAY PASS\\n");
    return ok ? 0 : 1;
}}
'''

(outdir / f'harness_{func}_capture.c').write_text(capture)
(outdir / f'harness_{func}_replay.c').write_text(replay)
print('GENERATE OK')
