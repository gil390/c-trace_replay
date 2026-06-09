#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZE = ROOT / 'tools' / 'analyze.py'
GENERATE = ROOT / 'tools' / 'generate_harness.py'
OUT = ROOT / 'generated'
TRACE_DIR = ROOT / 'testcases' / 'compute_trace_001'


def run(cmd):
    subprocess.run(cmd, cwd=ROOT, check=True)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    shutil.rmtree(TRACE_DIR, ignore_errors=True)
    OUT.mkdir(exist_ok=True)

    run([sys.executable, str(ANALYZE), 'examples/sample.c', 'examples/sample.h', 'compute', str(OUT)])
    run([sys.executable, str(GENERATE), str(OUT / 'compute_report.json'), str(OUT), '--mode', 'trace'])
    run([
        'gcc', '-Wall', '-Wextra', '-std=c11', '-Iexamples',
        '-o', str(OUT / 'trace_capture_compute'),
        str(OUT / 'trace_compute_capture.c'), 'examples/sample.c'
    ])
    run([str(OUT / 'trace_capture_compute')])

    manifest_path = TRACE_DIR / 'manifest.json'
    require(manifest_path.exists(), 'trace capture should write manifest.json')
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get('function') == 'compute', 'manifest should identify the function')
    require(manifest.get('mode') == 'trace', 'manifest should identify trace mode')
    require(manifest.get('call_count') == 3, 'manifest should record three calls by default')
    for idx in range(1, 4):
        require((TRACE_DIR / f'call_{idx:06d}').is_dir(), f'call_{idx:06d} directory should exist')

    run([
        'gcc', '-Wall', '-Wextra', '-std=c11', '-Iexamples',
        '-o', str(OUT / 'trace_replay_compute'),
        str(OUT / 'trace_compute_replay.c'), 'examples/sample.c'
    ])
    run([str(OUT / 'trace_replay_compute')])
    print('TRACE TESTS PASS')


if __name__ == '__main__':
    main()
