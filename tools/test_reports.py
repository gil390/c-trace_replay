#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZE = ROOT / 'tools' / 'analyze.py'


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


def main():
    checks = [
        check_compute,
        check_pointer_inout,
        check_call_ambiguity,
        check_content_loop,
        check_extra_forms,
    ]
    for check in checks:
        check()
        print(f'PASS {check.__name__}')
    print('REPORT TESTS PASS')


if __name__ == '__main__':
    main()
