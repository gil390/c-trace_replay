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
case = json.loads(case_path.read_text()) if case_path.exists() else {}
bindings = dict(case.get('bindings', {}))
required_annotations = list(report.get('annotation_required', []))
locals_by_name = {item['name']: item for item in report.get('locals', [])}


def c_string(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def safe_name(text):
    return re.sub(r'[^A-Za-z0-9_]', '_', text).strip('_') or 'value'


def root_symbol(symbol):
    return symbol.split('->')[0].split('.')[0].split('[')[0]


def is_non_observable_local(symbol):
    local = locals_by_name.get(root_symbol(symbol))
    return bool(local) and local.get('observable') is not True


def binding_key(symbol):
    if symbol in bindings:
        return symbol
    root = root_symbol(symbol)
    if root in bindings:
        return root
    return None


def binding_for(symbol):
    key = binding_key(symbol)
    return bindings.get(key) if key else None


def binding_id(symbol):
    key = binding_key(symbol)
    return safe_name(key or symbol)


def add_required(symbol, reason, example=None):
    item = {'symbol': symbol, 'reason': reason}
    if example:
        item['example'] = example
    if item not in required_annotations:
        required_annotations.append(item)


def unique_symbols(accesses):
    seen = set()
    result = []
    for access in accesses:
        symbol = access['symbol']
        if is_non_observable_local(symbol):
            continue
        key = binding_key(symbol)
        dedupe_key = key or root_symbol(symbol)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(symbol)
    return result


def declaration(var):
    init = var.get('init')
    suffix = f"[{var['array']}]" if 'array' in var else ''
    if init is None:
        return f"    {var['type']} {var['name']}{suffix};"
    return f"    {var['type']} {var['name']}{suffix} = {init};"


def strip_type_qualifiers(typ):
    return re.sub(r'\b(const|volatile|restrict)\b', '', typ).strip()


def pointer_base_type(typ):
    typ = strip_type_qualifiers(typ)
    if '*' not in typ:
        return None
    return re.sub(r'\s*\*+\s*$', '', typ).strip()


def scalar_init(typ):
    return '0' if '*' not in typ else 'NULL'


def is_pointer_param(param):
    return '*' in param.get('type', '')


def is_array_like_pointer(name, accesses):
    for access in accesses:
        if root_symbol(access['symbol']) == name and access.get('range') != 'scalar':
            return True
    return False


def is_byte_type(typ):
    return strip_type_qualifiers(typ) in {
        'char',
        'signed char',
        'unsigned char',
        'uint8_t',
        'int8_t',
    }


def infer_case_from_report():
    variables = []
    arguments = []
    accesses = report.get('access_sets', {}).get('read_set', []) + report.get('access_sets', {}).get('write_set', [])
    annotated_symbols = {item.get('symbol') for item in required_annotations}

    for param in report.get('parameters', []):
        name = param['name']
        typ = param.get('type', 'int')

        if name in bindings:
            arguments.append(bindings[name].get('argument', name))
            continue

        if is_pointer_param(param):
            base_type = pointer_base_type(typ)
            if not base_type or base_type == 'void':
                variables.append({'type': 'uint8_t', 'name': name, 'array': 'CTRACE_DEFAULT_LEN', 'init': '{0}'})
                arguments.append(name)
                bindings[name] = {'expr': name, 'size': f'sizeof({name})'}
                add_required(name, 'pointer base type not inferred precisely', {
                    'size_expr': f'sizeof({name})',
                    'direction': 'in|out|inout'
                })
                continue

            if is_array_like_pointer(name, accesses) or is_byte_type(base_type) or name in annotated_symbols:
                variables.append({'type': base_type, 'name': name, 'array': 'CTRACE_DEFAULT_LEN', 'init': '{0}'})
                arguments.append(name)
                bindings[name] = {'expr': name, 'size': f'sizeof({name})'}
            else:
                storage_name = f'{name}_value'
                variables.append({'type': base_type, 'name': storage_name, 'init': '{0}'})
                arguments.append(f'&{storage_name}')
                bindings[name] = {'expr': f'&{storage_name}', 'size': f'sizeof({storage_name})'}
            continue

        variables.append({'type': typ, 'name': name, 'init': 'CTRACE_DEFAULT_LEN' if typ == 'size_t' else scalar_init(typ)})
        arguments.append(name)
        bindings[name] = {'expr': f'&{name}', 'size': f'sizeof({name})'}

    for access in accesses:
        symbol = root_symbol(access['symbol'])
        if symbol.startswith('g_') and symbol not in bindings:
            bindings[symbol] = {'expr': f'&{symbol}', 'size': f'sizeof({symbol})'}

    return {
        'case_dir': f'testcases/{func}_case_001',
        'variables': variables,
        'arguments': arguments,
        'extra_before': [],
    }


if case:
    generated_case = {
        'case_dir': case.get('case_dir', f'testcases/{func}_case_001'),
        'variables': case.get('variables', []),
        'arguments': case.get('arguments') or [p['name'] for p in report.get('parameters', [])],
        'extra_before': case.get('extra_before', []),
    }
else:
    generated_case = infer_case_from_report()


def require_binding(symbol):
    binding = binding_for(symbol)
    if not binding:
        add_required(symbol, 'no binding inferred for symbol', {
            'expr': 'TODO',
            'size_expr': 'TODO',
        })
    return binding


def save_line(case_dir, symbol, phase):
    binding = require_binding(symbol)
    if not binding:
        return f'    /* TODO: save {c_string(symbol)} {phase}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    save_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]});'


def load_line(case_dir, symbol, phase):
    binding = require_binding(symbol)
    if not binding:
        return f'    /* TODO: load {c_string(symbol)} {phase}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_{phase}\\n"); return 1; }}'


def expected_decl(symbol):
    binding = require_binding(symbol)
    if not binding:
        return f'    /* TODO: expected storage for {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    uint8_t expected_{ident}[{binding["size"]}];'


def expected_load_line(case_dir, symbol):
    binding = require_binding(symbol)
    if not binding:
        return f'    /* TODO: load expected {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_expected.bin", expected_{ident}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_expected\\n"); return 1; }}'


def compare_line(symbol):
    binding = require_binding(symbol)
    if not binding:
        return f'    /* TODO: compare {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'''
    if (memcmp({binding["expr"]}, expected_{ident}, {binding["size"]}) != 0) {{
        printf("REPLAY FAIL: {ident} mismatch\\n");
        ok = 0;
    }}'''


def warnings_comment():
    notes = []
    for warning in report.get('warnings', []):
        message = warning.get('message', str(warning))
        notes.append(f' * warning: {message}')
    for annotation in required_annotations:
        notes.append(f' * annotation required: {annotation.get("symbol", "?")}: {annotation.get("reason", "?")}')
    if not notes:
        return ''
    return '/*\n' + '\n'.join(c_string(note) for note in notes) + '\n */\n'


header_path = Path(report.get('header', 'examples/sample.h'))
include_path = Path('../') / header_path
case_dir = generated_case.get('case_dir', f'testcases/{func}_case_001')
return_type = report.get('return_type') or 'int'
is_void = return_type == 'void'
call_args = ', '.join(generated_case.get('arguments') or [p['name'] for p in report.get('parameters', [])])
before_symbols = unique_symbols(report.get('inferred_captures', {}).get('before', []))
for extra in generated_case.get('extra_before', []):
    if extra not in before_symbols:
        before_symbols.append(extra)
after_symbols = unique_symbols(report.get('access_sets', {}).get('write_set', []))

common = warnings_comment() + f'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "{c_string(str(include_path))}"

#ifndef CTRACE_DEFAULT_LEN
#define CTRACE_DEFAULT_LEN 4
#endif

static int __attribute__((unused)) save_bin(const char *path, const void *data, size_t size)
{{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    if (fwrite(data, 1, size, f) != size) {{ fclose(f); return -1; }}
    fclose(f);
    return 0;
}}

static int __attribute__((unused)) load_bin(const char *path, void *data, size_t size)
{{
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    if (fread(data, 1, size, f) != size) {{ fclose(f); return -1; }}
    fclose(f);
    return 0;
}}

static void __attribute__((unused)) dump_u8(const char *label, const uint8_t *p, size_t n)
{{
    printf("%s:", label);
    for (size_t i=0; i<n; i++) printf(" %u", p[i]);
    printf("\\n");
}}
'''

capture_decls = '\n'.join(declaration(var) for var in generated_case.get('variables', []))
replay_decls = '\n'.join(declaration(var) for var in generated_case.get('variables', []))
before_saves = '\n'.join(save_line(case_dir, symbol, 'before') for symbol in before_symbols)
before_loads = '\n'.join(load_line(case_dir, symbol, 'before') for symbol in before_symbols)
after_saves = '\n'.join(save_line(case_dir, symbol, 'expected') for symbol in after_symbols)
expected_decls = '\n'.join(expected_decl(symbol) for symbol in after_symbols)
expected_loads = '\n'.join(expected_load_line(case_dir, symbol) for symbol in after_symbols)
comparisons = '\n'.join(compare_line(symbol) for symbol in after_symbols)
dump_lines = []
for symbol in after_symbols:
    binding = require_binding(symbol)
    if binding and binding.get('dump_u8'):
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

annotations_path = outdir / f'{func}_annotations.required.json'
if required_annotations:
    annotations_path.write_text(json.dumps({
        'annotation_required': required_annotations,
        'warnings': report.get('warnings', []),
    }, indent=2))
elif annotations_path.exists():
    annotations_path.unlink()

if case:
    print(f'GENERATE OK: used {case_path}')
elif required_annotations:
    print(f'GENERATE OK: inferred harness with {len(required_annotations)} annotations required')
else:
    print('GENERATE OK: inferred harness from report')
