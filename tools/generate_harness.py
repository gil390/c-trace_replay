#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

if len(sys.argv) not in {3, 5}:
    print('usage: generate_harness.py <report.json> <outdir> [--mode single|trace]', file=sys.stderr)
    sys.exit(2)

report_path = Path(sys.argv[1])
report = json.loads(report_path.read_text())
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
mode = 'single'
if len(sys.argv) == 5:
    if sys.argv[3] != '--mode' or sys.argv[4] not in {'single', 'trace'}:
        print('usage: generate_harness.py <report.json> <outdir> [--mode single|trace]', file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[4]

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
    symbol = re.sub(r'\s+', ' ', str(symbol)).strip()
    previous = None
    while previous != symbol:
        previous = symbol
        symbol = symbol.strip()
        symbol = symbol.lstrip('&*').strip()
        if symbol.startswith('(') and ')' in symbol:
            inner = symbol[1:symbol.find(')')].strip()
            rest = symbol[symbol.find(')') + 1:].strip()
            if re.match(r'^[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*\s*\**$', inner) and rest:
                symbol = rest
            elif rest == '':
                symbol = inner
    match = re.search(r'\b[A-Za-z_]\w*\b', symbol)
    return match.group(0) if match else symbol.split('->')[0].split('.')[0].split('[')[0]


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
    if is_non_observable_local(symbol):
        return None
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
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} {phase}. */'
        return f'    /* TODO: save {c_string(symbol)} {phase}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    save_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]});'


def load_line(case_dir, symbol, phase):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} {phase}. */'
        return f'    /* TODO: load {c_string(symbol)} {phase}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_{phase}.bin", {binding["expr"]}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_{phase}\\n"); return 1; }}'


def expected_decl(symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} expected storage. */'
        return f'    /* TODO: expected storage for {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    uint8_t expected_{ident}[{binding["size"]}];'


def expected_load_line(case_dir, symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} expected load. */'
        return f'    /* TODO: load expected {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'    if (load_bin("{case_dir}/{ident}_expected.bin", expected_{ident}, {binding["size"]}) != 0) {{ printf("REPLAY FAIL: cannot load {ident}_expected\\n"); return 1; }}'


def compare_line(symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} compare. */'
        return f'    /* TODO: compare {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'''
    if (memcmp({binding["expr"]}, expected_{ident}, {binding["size"]}) != 0) {{
        printf("REPLAY FAIL: {ident} mismatch\\n");
        ok = 0;
    }}'''


def trace_extent_from_access(name):
    accesses = report.get('access_sets', {}).get('read_set', []) + report.get('access_sets', {}).get('write_set', [])
    for access in accesses:
        if root_symbol(access['symbol']) != name:
            continue
        rng = access.get('range')
        match = re.match(r'0\.\.([A-Za-z_]\w*)-1$', str(rng))
        if match:
            return match.group(1)
    return None


def trace_binding_for_param(param):
    name = param['name']
    typ = param.get('type', 'int')
    if '*' not in typ:
        return {'expr': f'&{name}', 'size': f'sizeof({name})'}
    extent = trace_extent_from_access(name)
    if extent:
        return {'expr': name, 'size': f'({extent}) * sizeof(*{name})'}
    return {'expr': name, 'size': f'sizeof(*{name})'}


def trace_bindings():
    result = {}
    for param in report.get('parameters', []):
        result[param['name']] = trace_binding_for_param(param)
    for access in report.get('access_sets', {}).get('read_set', []) + report.get('access_sets', {}).get('write_set', []):
        root = root_symbol(access['symbol'])
        if root.startswith('g_') and root not in result:
            result[root] = {'expr': f'&{root}', 'size': f'sizeof({root})'}
    return result


def trace_unique_symbols(accesses, trace_binding_map):
    seen = set()
    result = []
    for access in accesses:
        symbol = access['symbol']
        if is_non_observable_local(symbol):
            continue
        root = root_symbol(symbol)
        dedupe_key = root if root in trace_binding_map else symbol
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(symbol)
    return result


def trace_binding_for(symbol, trace_binding_map):
    root = root_symbol(symbol)
    return trace_binding_map.get(symbol) or trace_binding_map.get(root)


def trace_binding_id(symbol, trace_binding_map):
    root = root_symbol(symbol)
    return safe_name(root if root in trace_binding_map else symbol)


def trace_save_line(symbol, phase, trace_binding_map):
    binding = trace_binding_for(symbol, trace_binding_map)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} {phase}. */'
        add_required(symbol, 'no trace binding inferred for symbol', {
            'expr': 'TODO',
            'size_expr': 'TODO',
        })
        return f'    /* TODO: trace save {c_string(symbol)} {phase}: no binding inferred. */'
    ident = trace_binding_id(symbol, trace_binding_map)
    return (
        f'    snprintf(path, sizeof(path), "%s/{ident}_{phase}.bin", call_dir);\n'
        f'    save_bin(path, {binding["expr"]}, {binding["size"]});'
    )


def trace_load_line(symbol, phase):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'    /* skipped non-observable local {c_string(symbol)} {phase}. */'
        return f'    /* TODO: trace load {c_string(symbol)} {phase}: no binding inferred. */'
    ident = binding_id(symbol)
    return (
        f'        snprintf(path, sizeof(path), "%s/{ident}_{phase}.bin", call_dir);\n'
        f'        if (load_bin(path, {binding["expr"]}, {binding["size"]}) != 0) {{ printf("TRACE REPLAY FAIL: cannot load {ident}_{phase} for call %zu\\n", call_id); return 1; }}'
    )


def trace_expected_decl(symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'        /* skipped non-observable local {c_string(symbol)} expected storage. */'
        return f'        /* TODO: expected storage for {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'        uint8_t expected_{ident}[{binding["size"]}];'


def trace_expected_load_line(symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'        /* skipped non-observable local {c_string(symbol)} expected load. */'
        return f'        /* TODO: trace load expected {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return (
        f'        snprintf(path, sizeof(path), "%s/{ident}_expected.bin", call_dir);\n'
        f'        if (load_bin(path, expected_{ident}, {binding["size"]}) != 0) {{ printf("TRACE REPLAY FAIL: cannot load {ident}_expected for call %zu\\n", call_id); return 1; }}'
    )


def trace_compare_line(symbol):
    binding = require_binding(symbol)
    if not binding:
        if is_non_observable_local(symbol):
            return f'        /* skipped non-observable local {c_string(symbol)} compare. */'
        return f'        /* TODO: trace compare {c_string(symbol)}: no binding inferred. */'
    ident = binding_id(symbol)
    return f'''
        if (memcmp({binding["expr"]}, expected_{ident}, {binding["size"]}) != 0) {{
            printf("TRACE REPLAY FAIL: {ident} mismatch for call %zu\\n", call_id);
            ok = 0;
        }}'''


def wrapper_signature(wrapper_name):
    params = report.get('parameters', [])
    if not params:
        return f'{return_type} {wrapper_name}(void)'
    return f'{return_type} {wrapper_name}(' + ', '.join(f'{p["type"]} {p["name"]}' for p in params) + ')'


def generate_trace_harness():
    trace_dir = f'testcases/{func}_trace_001'
    wrapper_name = f'__ctrace_capture_{func}'
    param_call_args = ', '.join(p['name'] for p in report.get('parameters', []))
    capture_call_args = param_call_args
    if not capture_call_args:
        capture_call_args = ''
    trace_binding_map = trace_bindings()
    trace_before_symbols = trace_unique_symbols(report.get('inferred_captures', {}).get('before', []), trace_binding_map)
    for extra in generated_case.get('extra_before', []):
        if extra not in trace_before_symbols:
            trace_before_symbols.append(extra)
    trace_after_symbols = trace_unique_symbols(report.get('access_sets', {}).get('write_set', []), trace_binding_map)
    trace_before_saves = '\n'.join(trace_save_line(symbol, 'before', trace_binding_map) for symbol in trace_before_symbols)
    trace_after_saves = '\n'.join(trace_save_line(symbol, 'expected', trace_binding_map) for symbol in trace_after_symbols)
    standalone_decls = '\n'.join(declaration(var) for var in generated_case.get('variables', []))
    standalone_args = ', '.join(generated_case.get('arguments') or [p['name'] for p in report.get('parameters', [])])
    replay_before_loads = '\n'.join(trace_load_line(symbol, 'before') for symbol in before_symbols)
    replay_expected_decls = '\n'.join(trace_expected_decl(symbol) for symbol in after_symbols)
    replay_expected_loads = '\n'.join(trace_expected_load_line(symbol) for symbol in after_symbols)
    replay_comparisons = '\n'.join(trace_compare_line(symbol) for symbol in after_symbols)
    trace_return_save = '' if is_void else '    snprintf(path, sizeof(path), "%s/return_expected.bin", call_dir);\n    save_bin(path, &ret, sizeof(ret));'
    trace_return_decl = '' if is_void else f'        {return_type} expected_ret;'
    trace_return_load = '' if is_void else '        snprintf(path, sizeof(path), "%s/return_expected.bin", call_dir);\n        if (load_bin(path, &expected_ret, sizeof(expected_ret)) != 0) { printf("TRACE REPLAY FAIL: cannot load return_expected for call %zu\\n", call_id); return 1; }'
    trace_return_compare = '' if is_void else '''
        if (ret != expected_ret) {
            printf("TRACE REPLAY FAIL: return mismatch for call %zu\\n", call_id);
            ok = 0;
        }'''
    wrapper_call = (
        f'    {func}({param_call_args});'
        if is_void else
        f'    {return_type} ret = {func}({param_call_args});'
    )
    wrapper_return = '' if is_void else '    return ret;'
    replay_call_stmt = (
        f'        {func}({call_args});'
        if is_void else
        f'        {return_type} ret = {func}({call_args});'
    )

    trace_common = common + f'''
#define CTRACE_TRACE_DIR "{trace_dir}"

static size_t __attribute__((unused)) __ctrace_call_count = 0;
static int __attribute__((unused)) __ctrace_manifest_registered = 0;

static void __attribute__((unused)) make_dir(const char *path)
{{
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", path);
    system(cmd);
}}

static void __attribute__((unused)) call_dir_path(char *buf, size_t size, size_t call_id)
{{
    snprintf(buf, size, "%s/call_%06zu", CTRACE_TRACE_DIR, call_id);
}}

static size_t __attribute__((unused)) __ctrace_next_call_id(void)
{{
    __ctrace_call_count++;
    return __ctrace_call_count;
}}

static void __attribute__((unused)) __ctrace_write_manifest(void)
{{
    char path[4096];
    snprintf(path, sizeof(path), "%s/manifest.json", CTRACE_TRACE_DIR);
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "{{\\n");
    fprintf(f, "  \\"function\\": \\"{func}\\",\\n");
    fprintf(f, "  \\"mode\\": \\"trace\\",\\n");
    fprintf(f, "  \\"call_count\\": %zu,\\n", __ctrace_call_count);
    fprintf(f, "  \\"calls\\": [\\n");
    for (size_t i = 1; i <= __ctrace_call_count; i++) {{
        fprintf(f, "    {{\\"id\\": %zu, \\"dir\\": \\"call_%06zu\\"}}%s\\n",
                i, i, i == __ctrace_call_count ? "" : ",");
    }}
    fprintf(f, "  ]\\n");
    fprintf(f, "}}\\n");
    fclose(f);
}}

static size_t __attribute__((unused)) __ctrace_manifest_call_count(void)
{{
    char path[4096];
    char text[4096];
    snprintf(path, sizeof(path), "%s/manifest.json", CTRACE_TRACE_DIR);
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    size_t n = fread(text, 1, sizeof(text) - 1, f);
    fclose(f);
    text[n] = '\\0';
    char *p = strstr(text, "\\"call_count\\"");
    if (!p) return 0;
    p = strchr(p, ':');
    if (!p) return 0;
    return (size_t)strtoull(p + 1, NULL, 10);
}}
'''

    capture = trace_common + f'''
{wrapper_signature(wrapper_name)}
{{
    char call_dir[1024];
    char path[4096];
    size_t call_id = __ctrace_next_call_id();
    make_dir(CTRACE_TRACE_DIR);
    if (!__ctrace_manifest_registered) {{
        atexit(__ctrace_write_manifest);
        __ctrace_manifest_registered = 1;
    }}
    call_dir_path(call_dir, sizeof(call_dir), call_id);
    make_dir(call_dir);

{trace_before_saves}

{wrapper_call}

{trace_after_saves}
{trace_return_save}

    printf("TRACE CAPTURE: call_%06zu written\\n", call_id);
{wrapper_return}
}}

int main(void)
{{
{standalone_decls}

    for (size_t i = 0; i < CTRACE_DEFAULT_TRACE_CALLS; i++) {{
        {'        ' if standalone_args else ''}{wrapper_name}({standalone_args});
    }}

    printf("TRACE CAPTURE OK: %zu calls written in %s\\n", __ctrace_call_count, CTRACE_TRACE_DIR);
    return 0;
}}
'''

    replay = trace_common + f'''
int main(void)
{{
    size_t call_count = __ctrace_manifest_call_count();
    if (call_count == 0) {{
        printf("TRACE REPLAY FAIL: empty or missing manifest in %s\\n", CTRACE_TRACE_DIR);
        return 1;
    }}

    int ok = 1;
    for (size_t call_id = 1; call_id <= call_count; call_id++) {{
        char call_dir[1024];
        char path[4096];
        call_dir_path(call_dir, sizeof(call_dir), call_id);

{standalone_decls}
{trace_return_decl}

{replay_before_loads}

{replay_expected_decls}
{replay_expected_loads}
{trace_return_load}

{replay_call_stmt}
{trace_return_compare}
{replay_comparisons}
    }}

    if (ok) printf("TRACE REPLAY PASS: %zu calls\\n", call_count);
    return ok ? 0 : 1;
}}
'''

    (outdir / f'trace_{func}_capture.c').write_text(capture)
    (outdir / f'trace_{func}_replay.c').write_text(replay)


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

#ifndef CTRACE_DEFAULT_TRACE_CALLS
#define CTRACE_DEFAULT_TRACE_CALLS 3
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

if mode == 'trace':
    generate_trace_harness()
    annotations_path = outdir / f'{func}_annotations.required.json'
    if required_annotations:
        annotations_path.write_text(json.dumps({
            'annotation_required': required_annotations,
            'warnings': report.get('warnings', []),
        }, indent=2))
    elif annotations_path.exists():
        annotations_path.unlink()
    if required_annotations:
        print(f'TRACE GENERATE OK: inferred trace harness with {len(required_annotations)} annotations required')
    else:
        print('TRACE GENERATE OK')
    sys.exit(0)

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
