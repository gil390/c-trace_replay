#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 5:
    print('usage: analyze.py <source.c> <header.h> <function> <outdir>', file=sys.stderr)
    sys.exit(2)

src_path = Path(sys.argv[1])
hdr_path = Path(sys.argv[2])
func_name = sys.argv[3]
outdir = Path(sys.argv[4])
outdir.mkdir(parents=True, exist_ok=True)
src = src_path.read_text()
hdr = hdr_path.read_text()


def make_report():
    return {
        'source': str(src_path),
        'function': func_name,
        'return_type': None,
        'parameters': [],
        'globals_read': [],
        'globals_written': [],
        'calls': [],
        'access_sets': {'read_set': [], 'write_set': []},
        'inferred_captures': {'before': [], 'after': []},
        'warnings': [],
        'annotation_required': []
    }


def add_unique(items, item):
    if item not in items:
        items.append(item)


def add_access(report, set_name, symbol, expr, rng, reason):
    add_unique(report['access_sets'][set_name], {
        'symbol': symbol,
        'expr': expr,
        'range': rng,
        'reason': reason,
    })


def finalize_report(report):
    for r in report['access_sets']['read_set']:
        add_unique(report['inferred_captures']['before'], r)
    for w in report['access_sets']['write_set']:
        add_unique(report['inferred_captures']['after'], w)
        if w['symbol'] in report['globals_written'] and not any(
            item['symbol'] == w['symbol'] for item in report['inferred_captures']['before']
        ):
            add_unique(report['inferred_captures']['before'], w)

    covered = {
        x['symbol'].split('->')[0].split('.')[0]
        for x in report['access_sets']['read_set'] + report['access_sets']['write_set']
    }
    for p in report['parameters']:
        if '*' in p['type'] and p['name'] not in covered:
            warning = {
                'level': 'warning',
                'symbol': p['name'],
                'message': 'pointer parameter not sufficiently characterized by analysis'
            }
            annotation = {
                'symbol': p['name'],
                'reason': 'pointer size/direction not inferred',
                'example': {'size_expr': 'TODO', 'direction': 'in|out|inout'}
            }
            add_unique(report['warnings'], warning)
            add_unique(report['annotation_required'], annotation)

    return report


def write_report(report):
    (outdir / f'{func_name}_report.json').write_text(json.dumps(report, indent=2))
    (outdir / f'{func_name}_annotations.required.json').write_text(json.dumps({
        'annotation_required': report['annotation_required'],
        'warnings': report['warnings'],
    }, indent=2))
    print('ANALYZE OK')
    print(f"backend: {report.get('backend', 'unknown')}")
    print(f"warnings: {len(report['warnings'])}, annotations required: {len(report['annotation_required'])}")


def token_text(cursor):
    return ' '.join(t.spelling for t in cursor.get_tokens()).strip()


def compact_expr(text):
    text = re.sub(r'\s*(->|\.)\s*', r'\1', text)
    text = re.sub(r'\s*\[\s*', '[', text)
    text = re.sub(r'\s*\]\s*', ']', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def display_type(typ):
    return re.sub(r'\s+', ' ', typ.spelling).strip()


def cursor_children(cursor):
    return list(cursor.get_children())


def is_in_file(cursor, path):
    loc = cursor.location
    return bool(loc.file) and Path(str(loc.file)).resolve() == path.resolve()


def is_assignment_lhs(cursor, parents):
    parent = parents.get(cursor.hash)
    if not parent:
        return False
    text = token_text(parent)
    children = cursor_children(parent)
    is_first_child = bool(children) and children[0].hash == cursor.hash
    if parent.kind.name == 'BINARY_OPERATOR' and is_first_child:
        return bool(re.search(r'(^|[^=!<>])=(?!=)', text))
    if parent.kind.name == 'COMPOUND_ASSIGNMENT_OPERATOR' and is_first_child:
        return True
    if parent.kind.name == 'UNARY_OPERATOR':
        return '++' in text or '--' in text
    return False


def is_readwrite(cursor, parents):
    parent = parents.get(cursor.hash)
    if not parent:
        return False
    text = token_text(parent)
    children = cursor_children(parent)
    is_first_child = bool(children) and children[0].hash == cursor.hash
    if parent.kind.name == 'COMPOUND_ASSIGNMENT_OPERATOR' and is_first_child:
        return True
    if parent.kind.name == 'UNARY_OPERATOR':
        return '++' in text or '--' in text
    return False


def range_from_index(index_text, loop_bounds):
    index_text = compact_expr(index_text)
    if index_text in loop_bounds:
        return f'0..{loop_bounds[index_text]}-1'
    modulo = re.search(r'%\s*(\d+)', index_text)
    if modulo:
        return f'0..{int(modulo.group(1)) - 1}'
    return index_text


def build_parent_map(cursor, parents):
    for child in cursor.get_children():
        parents[child.hash] = cursor
        build_parent_map(child, parents)


def detect_loop_bounds(cursor):
    bounds = {}
    for child in cursor.get_children():
        if child.kind.name == 'FOR_STMT':
            text = token_text(child)
            match = re.search(r'\b(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\s*;', text)
            if match:
                bounds[match.group(1)] = match.group(2)
        bounds.update(detect_loop_bounds(child))
    return bounds


def find_function(cursor, source_path):
    for child in cursor.get_children():
        if (child.kind.name == 'FUNCTION_DECL'
                and child.spelling == func_name
                and child.is_definition()
                and is_in_file(child, source_path)):
            return child
        found = find_function(child, source_path)
        if found:
            return found
    return None


def analyze_with_clang():
    try:
        from clang.cindex import Config, Index
    except ModuleNotFoundError as exc:
        raise RuntimeError('python bindings for clang are not installed') from exc

    candidates = [
        '/usr/lib/libclang.so',
        '/usr/lib/llvm/lib/libclang.so',
        '/usr/lib/llvm-18/lib/libclang.so',
        '/usr/lib/llvm-17/lib/libclang.so',
        '/usr/lib/llvm-16/lib/libclang.so',
    ]
    if not Config.loaded:
        for candidate in candidates:
            if Path(candidate).exists():
                Config.set_library_file(candidate)
                break

    parse_args = [f'-I{hdr_path.parent}', '-std=c11']
    try:
        resource_dir = subprocess.check_output(
            ['clang', '-print-resource-dir'],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        if resource_dir:
            parse_args.extend(['-resource-dir', resource_dir])
    except (OSError, subprocess.SubprocessError):
        pass
    for include_dir in ['/usr/include', '/usr/local/include']:
        if Path(include_dir).exists():
            parse_args.append(f'-I{include_dir}')

    index = Index.create()
    tu = index.parse(
        str(src_path),
        args=parse_args,
    )

    report = make_report()
    report['backend'] = 'clang'

    diagnostics = [str(d) for d in tu.diagnostics]
    for diagnostic in diagnostics:
        report['warnings'].append({'level': 'info', 'message': diagnostic})

    fn = find_function(tu.cursor, src_path)
    if not fn:
        report['warnings'].append({'level': 'error', 'message': 'function body not found'})
        return finalize_report(report)

    report['return_type'] = display_type(fn.result_type)
    report['parameters'] = [
        {'name': arg.spelling, 'type': display_type(arg.type)}
        for arg in fn.get_arguments()
    ]

    parents = {}
    build_parent_map(fn, parents)
    loop_bounds = detect_loop_bounds(fn)

    def visit(cursor):
        kind = cursor.kind.name

        if kind == 'CALL_EXPR':
            children = cursor_children(cursor)
            args = [compact_expr(token_text(c)) for c in children[1:]]
            callee = cursor.referenced.spelling if cursor.referenced else cursor.spelling
            if callee and callee != func_name:
                add_unique(report['calls'], {
                    'name': callee,
                    'args': args,
                    'indirect': cursor.referenced is None,
                    'risk': 'low' if cursor.referenced else 'unknown',
                    'reasons': [] if cursor.referenced else ['unresolved callee'],
                })

        elif kind == 'ARRAY_SUBSCRIPT_EXPR':
            children = cursor_children(cursor)
            if len(children) >= 2:
                base = compact_expr(token_text(children[0]))
                index_text = compact_expr(token_text(children[1]))
                expr = f'{base}[{index_text}]'
                set_name = 'write_set' if is_assignment_lhs(cursor, parents) else 'read_set'
                reason = 'array write detected' if set_name == 'write_set' else 'array read detected'
                add_access(report, set_name, base, expr, range_from_index(index_text, loop_bounds), reason)
                if is_readwrite(cursor, parents):
                    add_access(report, 'read_set', base, expr, range_from_index(index_text, loop_bounds), 'array read detected')

        elif kind == 'MEMBER_REF_EXPR':
            parent = parents.get(cursor.hash)
            if parent and parent.kind.name == 'ARRAY_SUBSCRIPT_EXPR':
                pass
            else:
                expr = compact_expr(token_text(cursor))
                if any(
                    item['symbol'] == expr and item['range'] != 'scalar'
                    for item in report['access_sets']['read_set'] + report['access_sets']['write_set']
                ):
                    for child in cursor.get_children():
                        visit(child)
                    return
                set_name = 'write_set' if is_assignment_lhs(cursor, parents) else 'read_set'
                reason = 'struct field write detected' if set_name == 'write_set' else 'struct field read detected'
                add_access(report, set_name, expr, expr, 'scalar', reason)
                if is_readwrite(cursor, parents):
                    add_access(report, 'read_set', expr, expr, 'scalar', 'struct field read detected')

        elif kind == 'DECL_REF_EXPR' and cursor.referenced:
            ref = cursor.referenced
            if ref.kind.name == 'VAR_DECL' and ref.semantic_parent.kind.name == 'TRANSLATION_UNIT':
                name = ref.spelling
                if name.startswith('g_'):
                    if is_assignment_lhs(cursor, parents):
                        add_unique(report['globals_written'], name)
                        add_access(report, 'write_set', name, name, 'scalar', 'global write')
                        if is_readwrite(cursor, parents):
                            add_unique(report['globals_read'], name)
                            add_access(report, 'read_set', name, name, 'scalar', 'global read')
                    else:
                        add_unique(report['globals_read'], name)
                        add_access(report, 'read_set', name, name, 'scalar', 'global read')

        for child in cursor.get_children():
            visit(child)

    visit(fn)

    if any(call['indirect'] for call in report['calls']):
        report['warnings'].append({'level': 'warning', 'message': 'unresolved or indirect call detected'})
    if any('->' in item['expr'] or '.' in item['expr'] for item in report['access_sets']['read_set']):
        report['warnings'].append({'level': 'info', 'message': 'field access detected; recursive callee analysis recommended'})

    return finalize_report(report)


def analyze_with_regex():
    report = make_report()
    report['backend'] = 'regex-fallback'
    report['warnings'].append({
        'level': 'warning',
        'message': 'clang backend unavailable; using legacy regex fallback'
    })

    func_decl_re = re.compile(
        r'(?P<return_type>[A-Za-z_][\w\s\*]*?)\s+'
        + re.escape(func_name)
        + r'\s*\((?P<params>[^)]*)\)\s*(?P<end>[;{])',
        re.MULTILINE
    )

    def parse_param(param):
        param = param.strip()
        if not param or param == 'void':
            return None
        param = re.sub(r'\[[^\]]*\]\s*$', ' *', param).strip()
        match = re.match(r'(?P<type>.+?[\s\*]+)(?P<name>[A-Za-z_]\w*)$', param)
        if not match:
            return {'name': param.split()[-1].replace('*', '').strip(), 'type': param}
        typ = re.sub(r'\s+', ' ', match.group('type')).strip()
        return {'name': match.group('name'), 'type': typ}

    match = func_decl_re.search(hdr + "\n" + src)
    if match:
        report['return_type'] = re.sub(r'\s+', ' ', match.group('return_type')).strip()
        report['parameters'] = [
            parsed for parsed in (parse_param(p) for p in match.group('params').split(','))
            if parsed
        ]

    body_match = next((m for m in func_decl_re.finditer(src) if m.group('end') == '{'), None)
    if not body_match:
        report['warnings'].append({'level': 'error', 'message': 'function body not found'})
        return finalize_report(report)

    start = body_match.end()
    depth = 1
    i = start
    while i < len(src) and depth:
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
        i += 1
    body = src[start:i - 1]

    for call_match in re.finditer(r'\b([A-Za-z_]\w*)\s*\(([^(){};]*)\)', body):
        name = call_match.group(1)
        if name in {'if', 'for', 'while', 'switch', 'return', 'sizeof'}:
            continue
        args = [a.strip() for a in call_match.group(2).split(',') if a.strip()]
        add_unique(report['calls'], {'name': name, 'args': args, 'indirect': False, 'risk': 'low', 'reasons': []})

    globals_found = set(re.findall(r'(?:extern\s+)?(?:uint\d+_t|int|size_t)\s+(g_\w+)\b', hdr + '\n' + src))
    for global_name in sorted(globals_found):
        if re.search(r'\b' + global_name + r'\b', body):
            if re.search(r'\b' + global_name + r'\s*(\+\+|--|[+\-*/%]?=)', body):
                report['globals_written'].append(global_name)
                report['globals_read'].append(global_name)
            else:
                report['globals_read'].append(global_name)

    loop_bounds = {}
    for loop_match in re.finditer(r'for\s*\([^;]*\b(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\s*;', body):
        loop_bounds[loop_match.group(1)] = loop_match.group(2)

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            continue
        assign = re.match(r'(.+?)\s*=\s*(.+);', stripped)
        if not assign:
            continue
        lhs, rhs = assign.group(1).strip(), assign.group(2).strip()
        arr_lhs = re.search(r'([A-Za-z_]\w*(?:->\w+)?)\s*\[([^\]]+)\]', lhs)
        if arr_lhs:
            base, idx = arr_lhs.group(1), arr_lhs.group(2).strip()
            add_access(report, 'write_set', base, f'{base}[{idx}]', range_from_index(idx, loop_bounds), 'array write detected')
        for base, idx in re.findall(r'([A-Za-z_]\w*(?:->\w+)?)\s*\[([^\]]+)\]', rhs):
            idx = idx.strip()
            add_access(report, 'read_set', base, f'{base}[{idx}]', range_from_index(idx, loop_bounds), 'array read detected')
        for base, field in re.findall(r'\b(\w+)->(\w+)\b', rhs):
            if not re.search(re.escape(base + '->' + field) + r'\s*\[', rhs):
                add_access(report, 'read_set', f'{base}->{field}', f'{base}->{field}', 'scalar', 'struct field read detected')

    for base, field in re.findall(r'\b(\w+)->(\w+)\b', body):
        if re.search(re.escape(base + '->' + field) + r'\s*\[', body):
            continue
        add_access(report, 'read_set', f'{base}->{field}', f'{base}->{field}', 'scalar', 'struct field read detected')

    for global_name in report['globals_read']:
        add_access(report, 'read_set', global_name, global_name, 'scalar', 'global read')
    for global_name in report['globals_written']:
        add_access(report, 'write_set', global_name, global_name, 'scalar', 'global write')

    if re.search(r'while\s*\([^)]*\*', body):
        report['warnings'].append({'level': 'warning', 'message': 'content-dependent pointer loop detected; annotation may be required'})
    if re.search(r'->\w+\s*\)', body):
        report['warnings'].append({'level': 'info', 'message': 'pointer/field passed to call; recursive callee analysis recommended'})

    return finalize_report(report)


try:
    analyzed_report = analyze_with_clang()
except Exception as exc:
    analyzed_report = analyze_with_regex()
    analyzed_report['warnings'].append({
        'level': 'warning',
        'message': f'clang backend failed: {exc}'
    })

write_report(analyzed_report)
