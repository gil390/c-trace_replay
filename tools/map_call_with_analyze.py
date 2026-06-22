#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / 'configuration' / 'config.json'
DEFAULT_CLANG_CANDIDATES = [
    '/usr/lib/libclang.so',
    '/usr/lib/llvm/lib/libclang.so',
    '/usr/lib/llvm-18/lib/libclang.so',
    '/usr/lib/llvm-17/lib/libclang.so',
    '/usr/lib/llvm-16/lib/libclang.so',
]
SOURCE_SUFFIXES = {'.c'}


def load_clang_candidates():
    if not CONFIG_PATH.exists():
        return DEFAULT_CLANG_CANDIDATES

    try:
        config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'invalid JSON in {CONFIG_PATH}: {exc.msg}') from exc

    if not isinstance(config, dict):
        raise RuntimeError(f'{CONFIG_PATH}: config must be a JSON object')

    candidates = None
    for key in ('clang_candidates', 'clang_library_candidates', 'candidates'):
        if key in config:
            candidates = config[key]
            break
    if candidates is None and isinstance(config.get('clang'), dict):
        candidates = config['clang'].get('candidates')
    if candidates is None:
        return DEFAULT_CLANG_CANDIDATES
    if not isinstance(candidates, list) or not all(isinstance(candidate, str) for candidate in candidates):
        raise RuntimeError(f'{CONFIG_PATH}: clang candidates must be a list of strings')

    return [str(Path(candidate).expanduser()) for candidate in candidates]


def configure_clang():
    try:
        from clang.cindex import Config, Index
    except ModuleNotFoundError as exc:
        raise RuntimeError('python bindings for clang are not installed') from exc

    if not Config.loaded:
        for candidate in load_clang_candidates():
            if Path(candidate).exists():
                Config.set_library_file(candidate)
                break

    return Index


def clang_resource_args():
    try:
        resource_dir = subprocess.check_output(
            ['clang', '-print-resource-dir'],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return []

    if resource_dir:
        return ['-resource-dir', resource_dir]
    return []


def location_dict(cursor):
    loc = cursor.location
    if not loc or not loc.file:
        return None
    return {
        'file': str(Path(str(loc.file))),
        'line': loc.line,
        'column': loc.column,
    }


def extent_dict(cursor):
    start = cursor.extent.start
    end = cursor.extent.end
    if not start or not start.file:
        return None
    return {
        'file': str(Path(str(start.file))),
        'start_line': start.line,
        'start_column': start.column,
        'end_line': end.line,
        'end_column': end.column,
    }


def token_text(cursor):
    return ' '.join(token.spelling for token in cursor.get_tokens()).strip()


def cursor_children(cursor):
    return list(cursor.get_children())


def is_under(path, root):
    try:
        Path(path).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def cursor_file(cursor):
    loc = cursor.location
    if not loc or not loc.file:
        return None
    return Path(str(loc.file)).resolve()


def is_project_cursor(cursor, root):
    path = cursor_file(cursor)
    return bool(path) and is_under(path, root)


def function_key(cursor):
    loc = location_dict(cursor) or {}
    return f'{loc.get("file", "")}:{loc.get("line", 0)}:{loc.get("column", 0)}:{cursor.spelling}'


def function_id(cursor, root):
    loc = cursor.location
    file_path = Path(str(loc.file)).resolve() if loc and loc.file else Path('<unknown>')
    try:
        file_label = file_path.relative_to(root.resolve())
    except ValueError:
        file_label = file_path
    return f'{file_label}:{loc.line if loc else 0}:{cursor.spelling}'


def discover_sources(source_dir):
    return sorted(
        path
        for path in source_dir.rglob('*')
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )


def load_compile_commands(path):
    if not path:
        return {}

    db_path = Path(path)
    if db_path.is_dir():
        db_path = db_path / 'compile_commands.json'
    if not db_path.exists():
        raise RuntimeError(f'compile commands file not found: {db_path}')

    try:
        entries = json.loads(db_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'invalid JSON in {db_path}: {exc.msg}') from exc

    if not isinstance(entries, list):
        raise RuntimeError(f'{db_path}: compile commands must be a JSON array')

    commands = {}
    for entry in entries:
        if not isinstance(entry, dict) or 'file' not in entry:
            continue
        directory = Path(entry.get('directory') or db_path.parent)
        file_path = Path(entry['file'])
        if not file_path.is_absolute():
            file_path = directory / file_path
        if 'arguments' in entry and isinstance(entry['arguments'], list):
            argv = [str(arg) for arg in entry['arguments']]
        elif 'command' in entry and isinstance(entry['command'], str):
            argv = shlex.split(entry['command'])
        else:
            continue
        commands[str(file_path.resolve())] = args_from_compile_command(argv, file_path.resolve(), directory.resolve())
    return commands


def make_compile_path_absolute(value, directory):
    path = Path(value)
    if path.is_absolute():
        return value
    return str((directory / path).resolve())


def args_from_compile_command(argv, source_path, directory):
    args = []
    skip_next = False
    path_next = None
    skip_with_value = {'-o', '-MF', '-MT', '-MQ'}
    include_with_value = {'-I', '-isystem', '-iquote', '-idirafter'}
    drop_flags = {'-c', '-S', '-E'}

    for index, arg in enumerate(argv[1:]):
        if skip_next:
            skip_next = False
            continue
        if path_next:
            args.append(path_next)
            args.append(make_compile_path_absolute(arg, directory))
            path_next = None
            continue
        if arg in drop_flags:
            continue
        if arg in skip_with_value:
            skip_next = True
            continue
        if arg in include_with_value:
            path_next = arg
            continue
        if arg.startswith('-I') and len(arg) > 2:
            args.append('-I' + make_compile_path_absolute(arg[2:], directory))
            continue
        if arg == str(source_path) or (Path(arg).name == source_path.name and index == len(argv[1:]) - 1):
            continue
        args.append(arg)

    return args


def default_parse_args(source_dir, std, include_dirs):
    args = [f'-I{source_dir}', f'-std={std}']
    args.extend(clang_resource_args())
    for include_dir in include_dirs:
        args.append(f'-I{include_dir}')
    for include_dir in ['/usr/include', '/usr/local/include']:
        if Path(include_dir).exists():
            args.append(f'-I{include_dir}')
    return args


def maybe_auto_compile_commands(source_dir):
    candidate = source_dir / 'compile_commands.json'
    if candidate.exists():
        return candidate
    return None


def collect_call(cursor, root):
    children = cursor_children(cursor)
    args = [token_text(child) for child in children[1:]]
    referenced = cursor.referenced
    direct_function = referenced is not None and referenced.kind.name == 'FUNCTION_DECL'
    callee_name = referenced.spelling if referenced and referenced.spelling else cursor.spelling
    call = {
        'name': callee_name or '<unknown>',
        'args': args,
        'indirect': not direct_function,
        'location': location_dict(cursor),
    }
    if direct_function:
        call['target'] = {
            'id': function_id(referenced, root),
            'location': location_dict(referenced),
        }
    else:
        call['target'] = None
        call['reasons'] = ['unresolved callee']
    return call


def collect_calls(cursor, root):
    calls = []

    def visit(node):
        if node.kind.name == 'CALL_EXPR':
            calls.append(collect_call(node, root))
        for child in node.get_children():
            visit(child)

    visit(cursor)
    return calls


def resolve_project_targets(functions):
    by_name = {}
    by_location = {}
    for fn in functions.values():
        by_name.setdefault(fn['name'], []).append(fn)
        loc = fn.get('location') or {}
        by_location[(loc.get('file'), loc.get('line'), loc.get('column'))] = fn

    for fn in functions.values():
        for call in fn['calls']:
            target = call.get('target')
            if target:
                loc = target.get('location') or {}
                resolved = by_location.get((loc.get('file'), loc.get('line'), loc.get('column')))
                if resolved:
                    target['id'] = resolved['id']
                    target['location'] = resolved['location']
                    target['project_function'] = True
                    continue

            name_matches = by_name.get(call['name'], [])
            if len(name_matches) == 1:
                resolved = name_matches[0]
                call['target'] = {
                    'id': resolved['id'],
                    'location': resolved['location'],
                    'project_function': True,
                }
                continue

            if target:
                target['project_function'] = False


def collect_edges(functions):
    edges = {}
    for fn in functions.values():
        for call in fn['calls']:
            target = call.get('target') or {}
            target_id = target.get('id')
            location = call.get('location') or {}
            edge_key = (
                fn['id'],
                target_id or call['name'],
                location.get('file', ''),
                location.get('line', 0),
                location.get('column', 0),
            )
            edges[edge_key] = {
                'from': fn['id'],
                'from_name': fn['name'],
                'to': target_id,
                'to_name': call['name'],
                'indirect': call['indirect'],
                'project_function': bool(target.get('project_function')),
                'location': call.get('location'),
            }
    return edges


def walk_functions(cursor, root):
    for child in cursor.get_children():
        if (
            child.kind.name == 'FUNCTION_DECL'
            and child.is_definition()
            and child.spelling
            and is_project_cursor(child, root)
        ):
            yield child
        yield from walk_functions(child, root)


def empty_map(source_dir, compile_commands):
    return {
        'source_dir': str(source_dir),
        'compile_commands': str(compile_commands) if compile_commands else None,
        'backend': 'clang',
        'functions': [],
        'edges': [],
        'diagnostics': [],
        'warnings': [],
    }



def safe_path_part(value):
    return ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in str(value))


def default_header_for_source(source):
    candidate = source.with_suffix('.h')
    if candidate.exists():
        return candidate
    return source


def analysis_output_dir(base_dir, source_dir, source_path):
    try:
        rel_parent = source_path.parent.resolve().relative_to(source_dir.resolve())
    except ValueError:
        rel_parent = Path(safe_path_part(source_path.parent.resolve()))
    return base_dir / rel_parent / safe_path_part(source_path.stem)


def run_function_analysis(fn, source_dir, analyze_script, analyze_header, analyze_outdir):
    loc = fn.get('location') or {}
    source_file = loc.get('file')
    if not source_file:
        return None, {
            'level': 'warning',
            'function': fn.get('name'),
            'message': 'analysis skipped: function source location missing',
        }

    source_path = Path(source_file).resolve()
    header_path = Path(analyze_header).resolve() if analyze_header else default_header_for_source(source_path)
    fn_outdir = analysis_output_dir(analyze_outdir, source_dir, source_path)
    fn_outdir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(analyze_script),
        str(source_path),
        str(header_path),
        fn.get('name', ''),
        str(fn_outdir),
    ]
    completed = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    report_path = fn_outdir / f"{fn.get('name', '')}_report.json"
    if completed.returncode != 0:
        return None, {
            'level': 'warning',
            'function': fn.get('name'),
            'source': str(source_path),
            'message': 'analysis failed',
            'returncode': completed.returncode,
            'stdout': completed.stdout.strip(),
            'stderr': completed.stderr.strip(),
        }
    if not report_path.exists():
        return None, {
            'level': 'warning',
            'function': fn.get('name'),
            'source': str(source_path),
            'message': f'analysis report not found: {report_path}',
            'stdout': completed.stdout.strip(),
            'stderr': completed.stderr.strip(),
        }

    try:
        analysis = json.loads(report_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        return None, {
            'level': 'warning',
            'function': fn.get('name'),
            'source': str(source_path),
            'message': f'analysis report invalid JSON: {exc.msg}',
            'report_path': str(report_path),
        }

    summary = {
        'report_path': str(report_path),
        'header': str(header_path),
        'globals_read': analysis.get('globals_read', []),
        'globals_written': analysis.get('globals_written', []),
        'locals': analysis.get('locals', []),
        'access_sets': analysis.get('access_sets', {'read_set': [], 'write_set': []}),
        'warnings': analysis.get('warnings', []),
        'annotation_required': analysis.get('annotation_required', []),
    }
    return summary, None


def enrich_functions_with_analysis(report, source_dir, analyze_script, analyze_header, analyze_outdir):
    analyze_script = Path(analyze_script).resolve()
    analyze_outdir = Path(analyze_outdir).resolve()
    if not analyze_script.exists():
        raise RuntimeError(f'analyze script not found: {analyze_script}')

    report['analysis'] = {
        'enabled': True,
        'script': str(analyze_script),
        'header': str(Path(analyze_header).resolve()) if analyze_header else None,
        'outdir': str(analyze_outdir),
    }

    for fn in report.get('functions', []):
        analysis, warning = run_function_analysis(
            fn,
            source_dir,
            analyze_script,
            analyze_header,
            analyze_outdir,
        )
        if warning:
            report['warnings'].append(warning)
            fn['analysis'] = {'status': 'failed', 'warning': warning}
        else:
            fn['analysis'] = analysis


def map_calls(source_dir, out_path, compile_commands, std, include_dirs, analyze=False, analyze_script=None, analyze_header=None, analyze_outdir=None):
    Index = configure_clang()
    index = Index.create()
    sources = discover_sources(source_dir)
    compile_args = load_compile_commands(compile_commands)
    base_args = default_parse_args(source_dir, std, include_dirs)
    report = empty_map(source_dir, compile_commands)
    functions = {}

    if not sources:
        report['warnings'].append({'level': 'warning', 'message': 'no C source files found'})

    for source in sources:
        args = compile_args.get(str(source.resolve()), base_args)
        try:
            tu = index.parse(str(source), args=args)
        except Exception as exc:
            report['warnings'].append({
                'level': 'error',
                'source': str(source),
                'message': f'failed to parse source: {exc}',
            })
            continue

        for diagnostic in tu.diagnostics:
            report['diagnostics'].append({
                'source': str(source),
                'message': str(diagnostic),
                'severity': getattr(diagnostic, 'severity', None),
            })

        for fn in walk_functions(tu.cursor, source_dir):
            key = function_key(fn)
            if key in functions:
                continue
            calls = collect_calls(fn, source_dir)
            fn_id = function_id(fn, source_dir)
            functions[key] = {
                'id': fn_id,
                'name': fn.spelling,
                'display_name': fn.displayname,
                'result_type': fn.result_type.spelling,
                'location': location_dict(fn),
                'extent': extent_dict(fn),
                'calls': calls,
            }

    resolve_project_targets(functions)
    edges = collect_edges(functions)
    report['functions'] = sorted(functions.values(), key=lambda item: item['id'])
    report['edges'] = sorted(edges.values(), key=lambda item: (
        item['from'],
        item['to_name'],
        item['location']['file'] if item.get('location') else '',
        item['location']['line'] if item.get('location') else 0,
    ))
    if analyze:
        default_script = Path(__file__).resolve().parent / 'analyze.py'
        default_outdir = out_path.parent / 'function_analysis'
        enrich_functions_with_analysis(
            report,
            source_dir,
            analyze_script or default_script,
            analyze_header,
            analyze_outdir or default_outdir,
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def parse_args():
    parser = argparse.ArgumentParser(
        description='Build a JSON call map for C sources using clang/libclang.',
    )
    parser.add_argument('source_dir', help='directory containing C sources')
    parser.add_argument('out_json', help='output JSON path')
    parser.add_argument(
        '--compile-commands',
        default=None,
        help='path to compile_commands.json or to its directory; auto-detected in source_dir when present',
    )
    parser.add_argument('--std', default='c11', help='C standard used when no compile_commands.json is available')
    parser.add_argument(
        '-I',
        '--include',
        action='append',
        default=[],
        dest='include_dirs',
        help='extra include directory used when no compile_commands.json is available',
    )
    parser.add_argument(
        '--analyze-functions',
        action='store_true',
        help='run analyze.py for every discovered project function and embed a memory-access summary in the call map JSON',
    )
    parser.add_argument(
        '--analyze-script',
        default=None,
        help='path to analyze.py; default: analyze.py next to map_call.py',
    )
    parser.add_argument(
        '--analyze-header',
        default=None,
        help='header passed to analyze.py for every function; default: <source>.h if present, otherwise the source file itself',
    )
    parser.add_argument(
        '--analyze-outdir',
        default=None,
        help='directory where per-function analyze.py reports are written; default: <out_json_dir>/function_analysis',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    out_path = Path(args.out_json)
    if not source_dir.exists() or not source_dir.is_dir():
        print(f'MAP_CALL ERROR: source directory not found: {source_dir}', file=sys.stderr)
        return 2

    compile_commands = args.compile_commands
    if compile_commands is None:
        compile_commands = maybe_auto_compile_commands(source_dir)

    try:
        report = map_calls(
            source_dir,
            out_path,
            compile_commands,
            args.std,
            [Path(include_dir).resolve() for include_dir in args.include_dirs],
            analyze=args.analyze_functions,
            analyze_script=Path(args.analyze_script).resolve() if args.analyze_script else None,
            analyze_header=Path(args.analyze_header).resolve() if args.analyze_header else None,
            analyze_outdir=Path(args.analyze_outdir).resolve() if args.analyze_outdir else None,
        )
    except Exception as exc:
        print(f'MAP_CALL ERROR: clang backend unavailable or failed: {exc}', file=sys.stderr)
        return 1

    print('MAP_CALL OK')
    print(f'functions: {len(report["functions"])}, edges: {len(report["edges"])}')
    print(f'output: {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
