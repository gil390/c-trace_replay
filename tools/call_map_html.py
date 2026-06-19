#!/usr/bin/env python3
import argparse
import html
import json
import sys
from pathlib import Path


def load_call_map(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'invalid JSON in {path}: {exc.msg}') from exc
    if not isinstance(data, dict):
        raise RuntimeError(f'{path}: expected a JSON object')
    if not isinstance(data.get('functions'), list) or not isinstance(data.get('edges'), list):
        raise RuntimeError(f'{path}: expected fields "functions" and "edges"')
    return data


def render_html(data):
    payload = (
        json.dumps(data, separators=(',', ':'))
        .replace('&', '\\u0026')
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
    )
    title = 'Call Map'
    source_dir = data.get('source_dir') or ''
    return f'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-2: #eef2f7;
      --text: #17202a;
      --muted: #657384;
      --line: #d7dee8;
      --strong: #143a5a;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b91c1c;
      --shadow: 0 10px 24px rgba(21, 35, 52, .12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
      overflow: hidden;
    }}
    .app {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 360px;
      height: 100vh;
      min-height: 520px;
    }}
    aside, main {{
      min-width: 0;
      min-height: 0;
    }}
    .left, .right {{
      background: var(--panel);
      border-color: var(--line);
      overflow: auto;
    }}
    .left {{ border-right: 1px solid var(--line); }}
    .right {{ border-left: 1px solid var(--line); }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 14px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 2px;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .controls {{
      display: grid;
      gap: 10px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
    }}
    input[type="search"] {{
      width: 100%;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }}
    .toggles {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    label.toggle {{
      display: flex;
      align-items: center;
      gap: 7px;
      min-height: 30px;
      color: var(--muted);
      font-size: 12px;
      user-select: none;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}
    .stat {{
      min-width: 0;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
    }}
    .stat b {{
      display: block;
      font-size: 17px;
      line-height: 1.15;
      color: var(--strong);
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }}
    .list {{
      padding: 8px;
    }}
    .fn {{
      width: 100%;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: inherit;
      padding: 8px;
      text-align: left;
      cursor: pointer;
    }}
    .fn:hover, .fn.active {{
      background: #edf7f5;
      border-color: #b8dcd7;
    }}
    .fn-name {{
      min-width: 0;
      font-weight: 650;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .fn-file {{
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .badge {{
      min-width: 26px;
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      text-align: center;
    }}
    .graph {{
      position: relative;
      background:
        linear-gradient(rgba(23, 32, 42, .045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(23, 32, 42, .045) 1px, transparent 1px);
      background-size: 28px 28px;
    }}
    canvas {{
      display: block;
      width: 100%;
      height: 100%;
      cursor: grab;
    }}
    canvas.dragging {{ cursor: grabbing; }}
    .toolbar {{
      position: absolute;
      top: 12px;
      right: 12px;
      display: flex;
      gap: 8px;
      z-index: 1;
    }}
    .icon-btn {{
      width: 34px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: rgba(255,255,255,.92);
      color: var(--text);
      box-shadow: var(--shadow);
      cursor: pointer;
      font-size: 16px;
      line-height: 1;
    }}
    .details {{
      padding: 14px;
    }}
    .details h2 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .signature {{
      margin-top: 6px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .section {{
      margin-top: 18px;
    }}
    .section h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--strong);
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
    }}
    .row-name {{
      font-weight: 620;
      overflow-wrap: anywhere;
    }}
    .row-meta {{
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .pill {{
      align-self: start;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      color: #fff;
      background: var(--accent);
      white-space: nowrap;
    }}
    .pill.external {{ background: var(--accent-2); }}
    .pill.indirect {{ background: var(--danger); }}
    .empty {{
      color: var(--muted);
      padding: 10px 0;
    }}
    @media (max-width: 980px) {{
      body {{ overflow: auto; }}
      .app {{
        grid-template-columns: 1fr;
        grid-template-rows: auto 62vh auto;
        height: auto;
      }}
      .left, .right {{
        border: 0;
        max-height: none;
      }}
      .graph {{ min-height: 520px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="left">
      <div class="topbar">
        <h1>Call Map</h1>
        <div class="meta">{html.escape(str(source_dir))}</div>
      </div>
      <div class="controls">
        <input id="search" type="search" placeholder="Filtrer" autocomplete="off">
        <div class="toggles">
          <label class="toggle"><input id="projectOnly" type="checkbox"> projet seul</label>
          <label class="toggle"><input id="showIndirect" type="checkbox" checked> indirects</label>
        </div>
        <div class="stats">
          <div class="stat"><b id="fnCount">0</b><span>fonctions</span></div>
          <div class="stat"><b id="edgeCount">0</b><span>appels</span></div>
          <div class="stat"><b id="diagCount">0</b><span>diagnostics</span></div>
        </div>
      </div>
      <div id="functionList" class="list"></div>
    </aside>
    <main class="graph">
      <div class="toolbar">
        <button id="zoomIn" class="icon-btn" title="Zoom avant">+</button>
        <button id="zoomOut" class="icon-btn" title="Zoom arriere">-</button>
        <button id="focusNeighborhood" class="icon-btn" title="Regrouper le voisinage">N</button>
        <button id="resetView" class="icon-btn" title="Recentrer">R</button>
        <button id="exportLayout" class="icon-btn" title="Exporter les positions">E</button>
        <button id="importLayout" class="icon-btn" title="Importer les positions">I</button>
      </div>
      <input id="layoutFile" type="file" accept="application/json,.json" hidden>
      <canvas id="graph"></canvas>
    </main>
    <aside class="right">
      <div id="details" class="details"></div>
    </aside>
  </div>
  <script id="callMapData" type="application/json">{payload}</script>
  <script>
(() => {{
  const data = JSON.parse(document.getElementById('callMapData').textContent);
  const functions = data.functions || [];
  const edges = data.edges || [];
  const byId = new Map(functions.map(fn => [fn.id, fn]));
  const incoming = new Map();
  const outgoing = new Map();
  for (const edge of edges) {{
    if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
    outgoing.get(edge.from).push(edge);
    if (edge.to) {{
      if (!incoming.has(edge.to)) incoming.set(edge.to, []);
      incoming.get(edge.to).push(edge);
    }}
  }}

  const canvas = document.getElementById('graph');
  const ctx = canvas.getContext('2d');
  const listEl = document.getElementById('functionList');
  const detailsEl = document.getElementById('details');
  const searchEl = document.getElementById('search');
  const projectOnlyEl = document.getElementById('projectOnly');
  const showIndirectEl = document.getElementById('showIndirect');
  const fnCountEl = document.getElementById('fnCount');
  const edgeCountEl = document.getElementById('edgeCount');
  const diagCountEl = document.getElementById('diagCount');
  const layoutFileEl = document.getElementById('layoutFile');
  let selectedId = functions[0]?.id || null;
  let view = {{ x: 0, y: 0, scale: 1 }};
  let dragging = null;
  let panning = null;

  const state = {{
    nodes: [],
    nodeById: new Map(),
    visibleEdges: [],
  }};

  function fileLine(loc) {{
    if (!loc) return '';
    const file = String(loc.file || '').split('/').slice(-2).join('/');
    return `${{file}}:${{loc.line || 0}}`;
  }}

  function nodeRadius(fn) {{
    const out = outgoing.get(fn.id)?.length || 0;
    const inc = incoming.get(fn.id)?.length || 0;
    return Math.max(24, Math.min(44, 24 + (out + inc) * 2));
  }}

  function rebuildGraph() {{
    const term = searchEl.value.trim().toLowerCase();
    const projectOnly = projectOnlyEl.checked;
    const showIndirect = showIndirectEl.checked;
    const visibleFns = functions.filter(fn => {{
      if (!term) return true;
      return `${{fn.name}} ${{fn.id}} ${{fn.display_name || ''}}`.toLowerCase().includes(term);
    }});
    const visibleIds = new Set(visibleFns.map(fn => fn.id));
    const visibleEdges = edges.filter(edge => {{
      if (!visibleIds.has(edge.from)) return false;
      if (edge.to && !visibleIds.has(edge.to) && edge.project_function) return false;
      if (projectOnly && !edge.project_function) return false;
      if (!showIndirect && edge.indirect) return false;
      return true;
    }});

    const cols = Math.max(1, Math.ceil(Math.sqrt(visibleFns.length)));
    const spacingX = 210;
    const spacingY = 150;
    const nodes = visibleFns.map((fn, index) => {{
      const col = index % cols;
      const row = Math.floor(index / cols);
      const existing = state.nodeById.get(fn.id);
      return {{
        id: fn.id,
        fn,
        x: existing?.x ?? col * spacingX,
        y: existing?.y ?? row * spacingY,
        vx: 0,
        vy: 0,
        r: nodeRadius(fn),
      }};
    }});
    state.nodes = nodes;
    state.nodeById = new Map(nodes.map(node => [node.id, node]));
    state.visibleEdges = visibleEdges;
    fnCountEl.textContent = visibleFns.length;
    edgeCountEl.textContent = visibleEdges.length;
    diagCountEl.textContent = (data.diagnostics || []).length;
    renderList(visibleFns);
    renderDetails();
    tickLayout(80);
    draw();
  }}

  function tickLayout(iterations) {{
    for (let i = 0; i < iterations; i++) {{
      for (const a of state.nodes) {{
        for (const b of state.nodes) {{
          if (a === b) continue;
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist2 = Math.max(80, dx * dx + dy * dy);
          const force = 1800 / dist2;
          a.vx += dx * force;
          a.vy += dy * force;
        }}
      }}
      for (const edge of state.visibleEdges) {{
        if (!edge.to) continue;
        const a = state.nodeById.get(edge.from);
        const b = state.nodeById.get(edge.to);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const force = (dist - 185) * 0.004;
        a.vx += dx / dist * force;
        a.vy += dy / dist * force;
        b.vx -= dx / dist * force;
        b.vy -= dy / dist * force;
      }}
      for (const node of state.nodes) {{
        node.vx *= 0.78;
        node.vy *= 0.78;
        node.x += node.vx;
        node.y += node.vy;
      }}
    }}
  }}

  function renderList(fns) {{
    listEl.innerHTML = '';
    for (const fn of fns) {{
      const button = document.createElement('button');
      button.className = 'fn' + (fn.id === selectedId ? ' active' : '');
      button.innerHTML = `
        <span class="fn-name">${{escapeHtml(fn.name)}}</span>
        <span class="badge">${{outgoing.get(fn.id)?.length || 0}}</span>
        <span class="fn-file">${{escapeHtml(fileLine(fn.location))}}</span>
      `;
      button.addEventListener('click', () => selectNode(fn.id, {{ center: true }}));
      listEl.appendChild(button);
    }}
  }}

  function renderDetails() {{
    const fn = byId.get(selectedId);
    if (!fn) {{
      detailsEl.innerHTML = '<div class="empty">Aucune fonction sélectionnée</div>';
      return;
    }}
    const out = outgoing.get(fn.id) || [];
    const inc = incoming.get(fn.id) || [];
    detailsEl.innerHTML = `
      <h2>${{escapeHtml(fn.name)}}</h2>
      <div class="signature">${{escapeHtml(fn.display_name || fn.id)}}</div>
      <div class="section">
        <h3>Source</h3>
        <div class="row"><div class="row-name">${{escapeHtml(fileLine(fn.location))}}</div><span class="pill">définie</span></div>
      </div>
      <div class="section">
        <h3>Appels sortants</h3>
        ${{rowsForEdges(out, true)}}
      </div>
      <div class="section">
        <h3>Appels entrants</h3>
        ${{rowsForEdges(inc, false)}}
      </div>
    `;
  }}

  function rowsForEdges(items, outgoingRows) {{
    if (!items.length) return '<div class="empty">Aucun</div>';
    return items.map(edge => {{
      const label = outgoingRows ? edge.to_name : edge.from_name;
      const cls = edge.indirect ? ' indirect' : edge.project_function ? '' : ' external';
      const kind = edge.indirect ? 'indirect' : edge.project_function ? 'projet' : 'externe';
      const args = (byId.get(edge.from)?.calls || []).find(call => call.location?.line === edge.location?.line && call.name === edge.to_name)?.args || [];
      return `
        <div class="row">
          <div class="row-name">${{escapeHtml(label || '<unknown>')}}</div>
          <span class="pill${{cls}}">${{kind}}</span>
          <div class="row-meta">${{escapeHtml(fileLine(edge.location))}}${{args.length ? ' · ' + escapeHtml(args.join(', ')) : ''}}</div>
        </div>
      `;
    }}).join('');
  }}

  function visibleFunctions() {{
    const term = searchEl.value.trim().toLowerCase();
    return functions.filter(fn => {{
      return !term || `${{fn.name}} ${{fn.id}} ${{fn.display_name || ''}}`.toLowerCase().includes(term);
    }});
  }}

  function selectNode(id, options = {{}}) {{
    selectedId = id;
    renderList(visibleFunctions());
    renderDetails();
    if (options.center) centerOnNode(id, Math.max(view.scale, .85));
    draw();
  }}

  function resize() {{
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }}

  function worldToScreen(x, y) {{
    return {{ x: x * view.scale + view.x, y: y * view.scale + view.y }};
  }}

  function screenToWorld(x, y) {{
    return {{ x: (x - view.x) / view.scale, y: (y - view.y) / view.scale }};
  }}

  function draw() {{
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.save();
    ctx.translate(view.x, view.y);
    ctx.scale(view.scale, view.scale);

    for (const edge of state.visibleEdges) {{
      const a = state.nodeById.get(edge.from);
      const b = edge.to ? state.nodeById.get(edge.to) : null;
      if (!a) continue;
      if (b) drawEdge(a, b, edge);
      else drawExternalEdge(a, edge);
    }}
    for (const node of state.nodes) drawNode(node);
    ctx.restore();
  }}

  function drawEdge(a, b, edge) {{
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.max(1, Math.hypot(dx, dy));
    const sx = a.x + dx / dist * a.r;
    const sy = a.y + dy / dist * a.r;
    const ex = b.x - dx / dist * b.r;
    const ey = b.y - dy / dist * b.r;
    ctx.strokeStyle = edge.indirect ? '#b91c1c' : '#516170';
    ctx.lineWidth = edge.project_function ? 1.8 : 1.2;
    ctx.setLineDash(edge.indirect || !edge.project_function ? [6, 5] : []);
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    ctx.setLineDash([]);
    drawArrow(ex, ey, Math.atan2(dy, dx), ctx.strokeStyle);
  }}

  function drawExternalEdge(a, edge) {{
    const angle = ((edge.to_name || '').length % 12) / 12 * Math.PI * 2;
    const ex = a.x + Math.cos(angle) * (a.r + 58);
    const ey = a.y + Math.sin(angle) * (a.r + 58);
    ctx.strokeStyle = edge.indirect ? '#b91c1c' : '#b45309';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    ctx.setLineDash([]);
    drawArrow(ex, ey, angle, ctx.strokeStyle);
  }}

  function drawArrow(x, y, angle, color) {{
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - Math.cos(angle - .45) * 9, y - Math.sin(angle - .45) * 9);
    ctx.lineTo(x - Math.cos(angle + .45) * 9, y - Math.sin(angle + .45) * 9);
    ctx.closePath();
    ctx.fill();
  }}

  function drawNode(node) {{
    const selected = node.id === selectedId;
    const out = outgoing.get(node.id)?.length || 0;
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
    ctx.fillStyle = selected ? '#0f766e' : '#ffffff';
    ctx.fill();
    ctx.lineWidth = selected ? 4 : 1.5;
    ctx.strokeStyle = selected ? '#99f6e4' : '#9aabba';
    ctx.stroke();
    ctx.fillStyle = selected ? '#ffffff' : '#17202a';
    ctx.font = '600 12px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    fitText(node.fn.name, node.x, node.y - 4, node.r * 1.55);
    ctx.fillStyle = selected ? '#dffcf7' : '#657384';
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText(String(out), node.x, node.y + 13);
  }}

  function fitText(text, x, y, maxWidth) {{
    let value = text;
    while (ctx.measureText(value).width > maxWidth && value.length > 4) {{
      value = value.slice(0, -2);
    }}
    if (value !== text) value += '...';
    ctx.fillText(value, x, y);
  }}

  function nodeAt(x, y) {{
    const p = screenToWorld(x, y);
    for (let i = state.nodes.length - 1; i >= 0; i--) {{
      const node = state.nodes[i];
      if (Math.hypot(node.x - p.x, node.y - p.y) <= node.r) return node;
    }}
    return null;
  }}

  function centerOnNode(id, targetScale = view.scale) {{
    const node = state.nodeById.get(id);
    if (!node) return;
    const rect = canvas.getBoundingClientRect();
    view.scale = Math.max(.08, Math.min(3, targetScale));
    view.x = rect.width / 2 - node.x * view.scale;
    view.y = rect.height / 2 - node.y * view.scale;
  }}

  function centerBoundsForNodes(ids, maxScale = 1.35) {{
    const nodes = ids.map(id => state.nodeById.get(id)).filter(Boolean);
    if (!nodes.length) return;
    const rect = canvas.getBoundingClientRect();
    const minX = Math.min(...nodes.map(node => node.x - node.r)) - 80;
    const maxX = Math.max(...nodes.map(node => node.x + node.r)) + 80;
    const minY = Math.min(...nodes.map(node => node.y - node.r)) - 80;
    const maxY = Math.max(...nodes.map(node => node.y + node.r)) + 80;
    const scale = Math.min(
      rect.width / Math.max(1, maxX - minX),
      rect.height / Math.max(1, maxY - minY),
      maxScale,
    );
    view.scale = Math.max(.08, scale);
    view.x = (rect.width - (minX + maxX) * view.scale) / 2;
    view.y = (rect.height - (minY + maxY) * view.scale) / 2;
  }}

  function arrangeAroundSelected() {{
    const selected = state.nodeById.get(selectedId);
    if (!selected) return;
    const outgoingProject = uniqueEdges(state.visibleEdges.filter(edge => edge.from === selectedId && edge.to && state.nodeById.has(edge.to)), 'to');
    const incomingProject = uniqueEdges(state.visibleEdges.filter(edge => edge.to === selectedId && state.nodeById.has(edge.from)), 'from');
    const centerX = selected.x;
    const centerY = selected.y;
    selected.x = centerX;
    selected.y = centerY;
    selected.vx = 0;
    selected.vy = 0;

    placeRing(outgoingProject.map(edge => edge.to), centerX, centerY, 210, -65, 65);
    placeRing(incomingProject.map(edge => edge.from), centerX, centerY, 210, 115, 245);
    const ids = [selectedId, ...outgoingProject.map(edge => edge.to), ...incomingProject.map(edge => edge.from)];
    centerBoundsForNodes([...new Set(ids)], 1.45);
    draw();
  }}

  function exportLayout() {{
    const layout = {{
      format: 'ctrace-call-map-layout',
      version: 1,
      source_dir: data.source_dir || null,
      selected_id: selectedId,
      view: {{ x: view.x, y: view.y, scale: view.scale }},
      nodes: state.nodes.map(node => ({{
        id: node.id,
        name: node.fn.name,
        x: Math.round(node.x * 1000) / 1000,
        y: Math.round(node.y * 1000) / 1000,
      }})),
    }};
    const blob = new Blob([JSON.stringify(layout, null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'call_map_layout.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }}

  function importLayoutFile(file) {{
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {{
      try {{
        const layout = JSON.parse(String(reader.result || ''));
        applyLayout(layout);
      }} catch (error) {{
        window.alert('Layout JSON invalide: ' + error.message);
      }}
    }};
    reader.readAsText(file, 'utf-8');
  }}

  function applyLayout(layout) {{
    if (!layout || !Array.isArray(layout.nodes)) {{
      window.alert('Layout invalide: champ nodes manquant');
      return;
    }}
    let applied = 0;
    for (const item of layout.nodes) {{
      const node = state.nodeById.get(item.id);
      if (!node || !Number.isFinite(item.x) || !Number.isFinite(item.y)) continue;
      node.x = item.x;
      node.y = item.y;
      node.vx = 0;
      node.vy = 0;
      applied++;
    }}
    if (layout.selected_id && byId.has(layout.selected_id)) {{
      selectedId = layout.selected_id;
      renderList(visibleFunctions());
      renderDetails();
    }}
    if (layout.view && Number.isFinite(layout.view.x) && Number.isFinite(layout.view.y) && Number.isFinite(layout.view.scale)) {{
      view = {{
        x: layout.view.x,
        y: layout.view.y,
        scale: Math.max(.08, Math.min(3, layout.view.scale)),
      }};
    }} else if (selectedId) {{
      centerOnNode(selectedId);
    }}
    draw();
    if (!applied) window.alert('Aucune position applicable dans ce layout');
  }}

  function uniqueEdges(items, key) {{
    const seen = new Set();
    return items.filter(edge => {{
      const value = edge[key];
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    }});
  }}

  function placeRing(ids, centerX, centerY, radius, startDeg, endDeg) {{
    const uniqueIds = [...new Set(ids)];
    if (!uniqueIds.length) return;
    const spread = uniqueIds.length === 1 ? 0 : endDeg - startDeg;
    const offset = uniqueIds.length === 1 ? (startDeg + endDeg) / 2 : startDeg;
    uniqueIds.forEach((id, index) => {{
      const node = state.nodeById.get(id);
      if (!node) return;
      const angleDeg = offset + (uniqueIds.length === 1 ? 0 : spread * index / (uniqueIds.length - 1));
      const angle = angleDeg * Math.PI / 180;
      const localRadius = radius + Math.floor(index / 10) * 90;
      node.x = centerX + Math.cos(angle) * localRadius;
      node.y = centerY + Math.sin(angle) * localRadius;
      node.vx = 0;
      node.vy = 0;
    }});
  }}

  function resetView() {{
    const rect = canvas.getBoundingClientRect();
    if (!state.nodes.length) {{
      view = {{ x: rect.width / 2, y: rect.height / 2, scale: 1 }};
      draw();
      return;
    }}
    const xs = state.nodes.map(n => n.x);
    const ys = state.nodes.map(n => n.y);
    const minX = Math.min(...xs) - 120;
    const maxX = Math.max(...xs) + 120;
    const minY = Math.min(...ys) - 100;
    const maxY = Math.max(...ys) + 100;
    const scale = Math.min(rect.width / Math.max(1, maxX - minX), rect.height / Math.max(1, maxY - minY), 1.25);
    view.scale = Math.max(.08, scale);
    view.x = (rect.width - (minX + maxX) * view.scale) / 2;
    view.y = (rect.height - (minY + maxY) * view.scale) / 2;
    draw();
  }}

  function escapeHtml(value) {{
    return String(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
  }}

  canvas.addEventListener('pointerdown', event => {{
    const node = nodeAt(event.offsetX, event.offsetY);
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('dragging');
    if (node) {{
      selectNode(node.id);
      dragging = {{ node, last: screenToWorld(event.offsetX, event.offsetY) }};
    }} else {{
      panning = {{ x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y }};
    }}
  }});
  canvas.addEventListener('pointermove', event => {{
    if (dragging) {{
      const p = screenToWorld(event.offsetX, event.offsetY);
      dragging.node.x += p.x - dragging.last.x;
      dragging.node.y += p.y - dragging.last.y;
      dragging.last = p;
      draw();
    }} else if (panning) {{
      view.x = panning.viewX + event.clientX - panning.x;
      view.y = panning.viewY + event.clientY - panning.y;
      draw();
    }}
  }});
  canvas.addEventListener('pointerup', () => {{
    dragging = null;
    panning = null;
    canvas.classList.remove('dragging');
  }});
  canvas.addEventListener('wheel', event => {{
    event.preventDefault();
    const before = screenToWorld(event.offsetX, event.offsetY);
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    view.scale = Math.max(.08, Math.min(3, view.scale * factor));
    const after = worldToScreen(before.x, before.y);
    view.x += event.offsetX - after.x;
    view.y += event.offsetY - after.y;
    draw();
  }}, {{ passive: false }});

  searchEl.addEventListener('input', rebuildGraph);
  projectOnlyEl.addEventListener('change', rebuildGraph);
  showIndirectEl.addEventListener('change', rebuildGraph);
  document.getElementById('zoomIn').addEventListener('click', () => {{ view.scale = Math.min(3, view.scale * 1.2); draw(); }});
  document.getElementById('zoomOut').addEventListener('click', () => {{ view.scale = Math.max(.08, view.scale / 1.2); draw(); }});
  document.getElementById('focusNeighborhood').addEventListener('click', arrangeAroundSelected);
  document.getElementById('resetView').addEventListener('click', resetView);
  document.getElementById('exportLayout').addEventListener('click', exportLayout);
  document.getElementById('importLayout').addEventListener('click', () => layoutFileEl.click());
  layoutFileEl.addEventListener('change', () => {{
    importLayoutFile(layoutFileEl.files && layoutFileEl.files[0]);
    layoutFileEl.value = '';
  }});
  window.addEventListener('resize', resize);

  rebuildGraph();
  resize();
  resetView();
}})();
  </script>
</body>
</html>
'''


def parse_args():
    parser = argparse.ArgumentParser(description='Convert a call map JSON into a standalone HTML viewer.')
    parser.add_argument('call_map_json', help='input JSON produced by tools/map_call.py')
    parser.add_argument('out_html', help='output HTML path')
    return parser.parse_args()


def main():
    args = parse_args()
    in_path = Path(args.call_map_json)
    out_path = Path(args.out_html)
    if not in_path.exists():
        print(f'CALL_MAP_HTML ERROR: input not found: {in_path}', file=sys.stderr)
        return 2
    try:
        data = load_call_map(in_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_html(data), encoding='utf-8')
    except Exception as exc:
        print(f'CALL_MAP_HTML ERROR: {exc}', file=sys.stderr)
        return 1
    print('CALL_MAP_HTML OK')
    print(f'output: {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
