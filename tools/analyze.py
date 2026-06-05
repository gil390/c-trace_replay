#!/usr/bin/env python3
import json, re, sys
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

report = {
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

FUNC_DECL_RE = re.compile(
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
    m = re.match(r'(?P<type>.+?[\s\*]+)(?P<name>[A-Za-z_]\w*)$', param)
    if not m:
        return {'name': param.split()[-1].replace('*', '').strip(), 'type': param}
    typ = re.sub(r'\s+', ' ', m.group('type')).strip()
    return {'name': m.group('name'), 'type': typ}

# function prototype params
params = []
m = FUNC_DECL_RE.search(hdr + "\n" + src)
if m:
    report['return_type'] = re.sub(r'\s+', ' ', m.group('return_type')).strip()
    for p in m.group('params').split(','):
        parsed = parse_param(p)
        if parsed:
            params.append(parsed)
report['parameters'] = params

# Extract function body approximately
fm = next((match for match in FUNC_DECL_RE.finditer(src) if match.group('end') == '{'), None)
if not fm:
    report['warnings'].append({'level':'error','message':'function body not found'})
else:
    start = fm.end(); depth=1; i=start
    while i < len(src) and depth:
        if src[i] == '{': depth += 1
        elif src[i] == '}': depth -= 1
        i += 1
    body = src[start:i-1]

    # calls excluding language keywords and target function itself
    for cm in re.finditer(r'\b([A-Za-z_]\w*)\s*\(([^(){};]*)\)', body):
        name = cm.group(1)
        if name in {'if','for','while','switch','return','sizeof'}: continue
        args = [a.strip() for a in cm.group(2).split(',') if a.strip()]
        report['calls'].append({'name': name, 'args': args, 'indirect': False, 'risk': 'low', 'reasons': []})

    # globals: externs from header or definitions in src
    globals_found = set(re.findall(r'(?:extern\s+)?(?:uint\d+_t|int|size_t)\s+(g_\w+)\b', hdr+'\n'+src))
    for g in sorted(globals_found):
        if re.search(r'\b'+g+r'\b', body):
            if re.search(r'\b'+g+r'\s*(\+\+|--|[+\-*/%]?=)', body):
                report['globals_written'].append(g)
                report['globals_read'].append(g)
            else:
                report['globals_read'].append(g)

    # detect for var < bound
    loop_bounds = {}
    for lm in re.finditer(r'for\s*\([^;]*\b(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\s*;', body):
        loop_bounds[lm.group(1)] = lm.group(2)

    def add_unique(listname, item):
        if item not in report['access_sets'][listname]:
            report['access_sets'][listname].append(item)

    # assignment array writes and RHS reads
    for line in body.splitlines():
        s=line.strip()
        # skip declarations of local scalars
        if not s or s.startswith('//'): continue
        am = re.match(r'(.+?)\s*=\s*(.+);', s)
        if am:
            lhs, rhs = am.group(1).strip(), am.group(2).strip()
            arr_lhs = re.search(r'([A-Za-z_]\w*(?:->\w+)?)\s*\[([^\]]+)\]', lhs)
            if arr_lhs:
                base, idx = arr_lhs.group(1), arr_lhs.group(2).strip()
                rng = None
                if idx in loop_bounds:
                    rng = f'0..{loop_bounds[idx]}-1'
                elif re.match(r'\w+\s*%\s*(\d+)', idx):
                    rng = '0..'+re.search(r'%(\s*)(\d+)', idx).group(2)
                add_unique('write_set', {'symbol':base,'expr':f'{base}[{idx}]','range':rng or idx,'reason':'array write detected'})
            for base, idx in re.findall(r'([A-Za-z_]\w*(?:->\w+)?)\s*\[([^\]]+)\]', rhs):
                idx=idx.strip(); rng=None
                if idx in loop_bounds: rng=f'0..{loop_bounds[idx]}-1'
                elif '%' in idx:
                    mm=re.search(r'%\s*(\d+)', idx)
                    if mm: rng=f'0..{int(mm.group(1))-1}'
                add_unique('read_set', {'symbol':base,'expr':f'{base}[{idx}]','range':rng or idx,'reason':'array read detected'})
            for base, field in re.findall(r'\b(\w+)->(\w+)\b', rhs):
                # avoid duplicating table as struct_ref when array already added
                if not re.search(re.escape(base+'->'+field)+r'\s*\[', rhs):
                    add_unique('read_set', {'symbol':f'{base}->{field}','expr':f'{base}->{field}','range':'scalar','reason':'struct field read detected'})

    # struct field reads in conditions and expressions
    for base, field in re.findall(r'\b(\w+)->(\w+)\b', body):
        if re.search(re.escape(base+'->'+field)+r'\s*\[', body):
            continue
        if not any(x.get('symbol') == f'{base}->{field}' for x in report['access_sets']['read_set']):
            add_unique('read_set', {'symbol':f'{base}->{field}','expr':f'{base}->{field}','range':'scalar','reason':'struct field read detected'})

    # globals as read/write sets
    for g in report['globals_read']:
        add_unique('read_set', {'symbol':g,'expr':g,'range':'scalar','reason':'global read'})
    for g in report['globals_written']:
        add_unique('write_set', {'symbol':g,'expr':g,'range':'scalar','reason':'global write'})

    # Ambiguities: pointer params not covered by inferred read/write sets
    covered = {x['symbol'].split('->')[0] for x in report['access_sets']['read_set']+report['access_sets']['write_set']}
    for p in params:
        if '*' in p['type'] and p['name'] not in covered:
            report['warnings'].append({'level':'warning','symbol':p['name'],'message':'pointer parameter not sufficiently characterized by analysis'})
            report['annotation_required'].append({'symbol':p['name'],'reason':'pointer size/direction not inferred','example':{'size_expr':'TODO','direction':'in|out|inout'}})

    # Dynamic pattern warnings
    if re.search(r'while\s*\([^)]*\*', body):
        report['warnings'].append({'level':'warning','message':'content-dependent pointer loop detected; annotation may be required'})
    if re.search(r'->\w+\s*\)', body):
        report['warnings'].append({'level':'info','message':'pointer/field passed to call; recursive callee analysis recommended'})

    # inferred captures: read before, write after, globals written before+after if inout
    for r in report['access_sets']['read_set']:
        report['inferred_captures']['before'].append(r)
    for w in report['access_sets']['write_set']:
        report['inferred_captures']['after'].append(w)
        if w['symbol'] in report['globals_written'] and not any(x['symbol']==w['symbol'] for x in report['inferred_captures']['before']):
            report['inferred_captures']['before'].append(w)

(outdir/f'{func_name}_report.json').write_text(json.dumps(report, indent=2))
(outdir/f'{func_name}_annotations.required.json').write_text(json.dumps({'annotation_required': report['annotation_required'], 'warnings': report['warnings']}, indent=2))
print('ANALYZE OK')
print(f"warnings: {len(report['warnings'])}, annotations required: {len(report['annotation_required'])}")
