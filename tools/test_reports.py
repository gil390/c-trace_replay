#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZE = ROOT / 'tools' / 'analyze.py'
GENERATE = ROOT / 'tools' / 'generate_harness.py'


def run_analyze(src, hdr, func):
    outdir = Path(tempfile.mkdtemp(prefix=f'ctrace_{func}_'))
    subprocess.run(
        [sys.executable, str(ANALYZE), src, hdr, func, str(outdir)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads((outdir / f'{func}_report.json').read_text())


def symbols(report, set_name):
    return {item['symbol'] for item in report['access_sets'][set_name]}


def annotation_symbols(report):
    return {item['symbol'] for item in report['annotation_required']}


def locals_by_name(report):
    return {item['name']: item for item in report.get('locals', [])}


def warnings_for_symbol(report, symbol):
    return [item for item in report.get('warnings', []) if item.get('symbol') == symbol]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_compute():
    report = run_analyze('examples/sample.c', 'examples/sample.h', 'compute')
    require(report.get('backend') == 'clang', 'compute should use clang backend')
    require('input' in symbols(report, 'read_set'), 'compute should read input')
    require('ctx->table' in symbols(report, 'read_set'), 'compute should read ctx->table')
    require('ctx->scale' in symbols(report, 'read_set'), 'compute should read ctx->scale')
    require('output' in symbols(report, 'write_set'), 'compute should write output')
    require('g_counter' in symbols(report, 'write_set'), 'compute should write g_counter')
    require(not report['annotation_required'], 'compute should not require annotations')

    locals_ = locals_by_name(report)
    require({'i', 'local', 'f'} <= set(locals_),
            'compute should list discovered function-local variables')
    require(locals_['local']['type'] == 'uint8_t',
            'compute local variable should include its type')
    require(locals_['local']['storage'] == 'automatic',
            'compute local variable should be marked automatic')
    require(locals_['local']['observable'] is False,
            'compute local automatic variable should be marked non-observable')


def check_pointer_inout():
    report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_pointer_inout')
    require('value' in symbols(report, 'read_set'), 'rw_pointer_inout should read value')
    require('value' in symbols(report, 'write_set'), 'rw_pointer_inout should write value')
    require(not report['annotation_required'], 'rw_pointer_inout should not require annotations')


def check_call_ambiguity():
    report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_call_with_pointer')
    require('buffer' in annotation_symbols(report), 'rw_call_with_pointer should require buffer annotation')
    require(any('callee effects not analyzed' in item['reason'] for item in report['annotation_required']),
            'rw_call_with_pointer should explain callee ambiguity')


def check_content_loop():
    report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_content_dependent_loop')
    require({'src', 'dst'} <= annotation_symbols(report),
            'rw_content_dependent_loop should require src and dst annotations')


def check_extra_forms():
    typedef_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_typedef_array')
    require('input' in symbols(typedef_report, 'read_set'), 'rw_typedef_array should read input')
    require('output' in symbols(typedef_report, 'write_set'), 'rw_typedef_array should write output')

    nested_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_nested_struct_field')
    require('outer->inner.value' in symbols(nested_report, 'read_set'),
            'rw_nested_struct_field should read outer->inner.value')
    require('dst' in symbols(nested_report, 'write_set'), 'rw_nested_struct_field should write dst')

    macro_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_macro_write')
    require('ctx' in annotation_symbols(macro_report),
            'rw_macro_write should require ctx annotation until macro expansion is handled')

    callback_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_function_pointer_call')
    require('buffer' in annotation_symbols(callback_report),
            'rw_function_pointer_call should require buffer annotation')


def check_local_observability():
    temp_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_struct_temp')
    temp_locals = locals_by_name(temp_report)
    require('v' in temp_locals, 'local struct temp should list v as local')
    require(temp_locals['v']['storage'] == 'automatic', 'local struct temp v should be automatic')
    require(temp_locals['v']['observable'] is False, 'automatic local struct should be non-observable')
    require('v' not in symbols(temp_report, 'read_set'), 'automatic local should not enter read_set')
    require('v' not in symbols(temp_report, 'write_set'), 'automatic local should not enter write_set')
    require('v.x' not in symbols(temp_report, 'read_set'), 'automatic local field should not enter read_set')
    require('v.x' not in symbols(temp_report, 'write_set'), 'automatic local field should not enter write_set')
    require('dst' in symbols(temp_report, 'write_set'), 'observable output pointer should remain in write_set')

    output_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_struct_output')
    require('v' in locals_by_name(output_report), 'local output should list v as local')
    require('out' in symbols(output_report, 'write_set'), 'local output should keep observable output writes')
    require('v' not in symbols(output_report, 'read_set'), 'local output should not capture local v reads')


def check_local_address_escapes():
    call_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_address_escape_call')
    require(any('call argument' in item['message'] for item in warnings_for_symbol(call_report, 'v')),
            'address escape through call argument should be warned')
    require('v' not in symbols(call_report, 'read_set'), 'escaped automatic local should not enter read_set')

    global_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_address_escape_global')
    require(any('assignment' in item['message'] for item in warnings_for_symbol(global_report, 'v')),
            'address escape through assignment should be warned')
    require('g_rw_escaped_vector' in symbols(global_report, 'write_set'),
            'global receiving escaped address should remain observable')

    return_report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_address_escape_return')
    require(any('return value' in item['message'] for item in warnings_for_symbol(return_report, 'v')),
            'address escape through return should be warned')


def check_local_static_state():
    report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_static_state')
    locals_ = locals_by_name(report)
    require('acc' in locals_, 'local static should be listed')
    require(locals_['acc']['storage'] == 'static', 'local static should be marked static')
    require(locals_['acc']['observable'] == 'persistent_internal',
            'local static should be marked persistent internal')
    require('acc' in annotation_symbols(report), 'local static should require instrumentation annotation')
    require('acc' not in symbols(report, 'read_set'), 'local static should not get a direct read binding')
    require('acc' not in symbols(report, 'write_set'), 'local static should not get a direct write binding')


def check_generator_skips_stale_local_capture():
    report = run_analyze('examples/rw_cases.c', 'examples/rw_cases.h', 'rw_local_struct_temp')
    stale_access = {
        'symbol': 'v.x',
        'expr': 'v.x',
        'range': 'scalar',
        'reason': 'stale local field from older analyzer',
    }
    report['access_sets']['read_set'].append(stale_access)
    report['inferred_captures']['before'].append(stale_access)

    outdir = Path(tempfile.mkdtemp(prefix='ctrace_generate_stale_local_'))
    report_path = outdir / 'rw_local_struct_temp_report.json'
    report_path.write_text(json.dumps(report))
    subprocess.run(
        [sys.executable, str(GENERATE), str(report_path), str(outdir)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    generated = (outdir / 'harness_rw_local_struct_temp_capture.c').read_text()
    require('no binding inferred' not in generated,
            'generator should not emit missing binding for non-observable locals')
    require('v.x' not in generated,
            'generator should omit stale non-observable local capture')


def main():
    checks = [
        check_compute,
        check_pointer_inout,
        check_call_ambiguity,
        check_content_loop,
        check_extra_forms,
        check_local_observability,
        check_local_address_escapes,
        check_local_static_state,
        check_generator_skips_stale_local_capture,
    ]
    for check in checks:
        check()
        print(f'PASS {check.__name__}')
    print('REPORT TESTS PASS')


if __name__ == '__main__':
    main()
