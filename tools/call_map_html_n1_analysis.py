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
    .actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 12px;
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
    .field {{
      display: grid;
      gap: 5px;
      margin-top: 10px;
    }}
    .field label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .field input, .field textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      font: inherit;
      color: var(--text);
      background: #fff;
    }}
    .field textarea {{
      min-height: 76px;
      resize: vertical;
    }}
    .text-btn {{
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
      color: var(--text);
      cursor: pointer;
      font: inherit;
      padding: 5px 9px;
    }}
    .text-btn.danger {{
      color: var(--danger);
      background: #fff5f5;
      border-color: #f3b8b8;
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

    .analysis-panel {{
      position: absolute;
      left: 12px;
      bottom: 12px;
      z-index: 3;
      width: min(620px, calc(100% - 24px));
      max-height: min(70vh, 680px);
      display: none;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255,255,255,.97);
      box-shadow: var(--shadow);
    }}
    .analysis-panel.visible {{ display: block; }}
    .analysis-header {{
      position: sticky;
      top: 0;
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
      padding: 12px 14px;
      background: #fff;
      border-bottom: 1px solid var(--line);
    }}
    .analysis-title {{ min-width: 0; }}
    .analysis-title b {{
      display: block;
      color: var(--strong);
      font-size: 15px;
      overflow-wrap: anywhere;
    }}
    .analysis-title span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .analysis-body {{ padding: 12px 14px 14px; }}
    .analysis-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .analysis-card {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      padding: 10px;
    }}
    .analysis-card h4 {{
      margin: 0 0 8px;
      font-size: 12px;
      color: var(--strong);
      text-transform: uppercase;
    }}
    .analysis-list {{
      margin: 0;
      padding-left: 18px;
      color: var(--text);
      font-size: 12px;
    }}
    .analysis-list li {{
      margin: 4px 0;
      overflow-wrap: anywhere;
    }}
    .analysis-pre {{
      margin: 10px 0 0;
      max-height: 240px;
      overflow: auto;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 980px) {{
      .analysis-panel {{
        position: static;
        width: auto;
        max-height: none;
        margin: 10px;
      }}
      .analysis-grid {{ grid-template-columns: 1fr; }}
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
          <label class="toggle"><input id="directOnly" type="checkbox"> n+1 seul</label>
          <label class="toggle"><input id="groupMode" type="checkbox"> sélection groupe</label>
        </div>
        <div class="actions">
          <button id="applyGroupFilter" class="text-btn">Voir groupe n+1</button>
          <button id="clearGroupFilter" class="text-btn">Tout afficher</button>
        </div>
        <div class="hint">En mode groupe : clic sur plusieurs fonctions, puis “Voir groupe n+1”.</div>
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
        <button id="createGroup" class="icon-btn" title="Creer une boite logique">G</button>
        <button id="resetView" class="icon-btn" title="Recentrer">R</button>
        <button id="exportLayout" class="icon-btn" title="Exporter les positions">E</button>
        <button id="importLayout" class="icon-btn" title="Importer les positions">I</button>
        <button id="toggleAnalysis" class="icon-btn" title="Afficher/masquer analyse mémoire">A</button>
      </div>
      <input id="layoutFile" type="file" accept="application/json,.json" hidden>
      <canvas id="graph"></canvas>
      <div id="analysisPanel" class="analysis-panel"></div>
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
  const directOnlyEl = document.getElementById('directOnly');
  const groupModeEl = document.getElementById('groupMode');
  const applyGroupFilterEl = document.getElementById('applyGroupFilter');
  const clearGroupFilterEl = document.getElementById('clearGroupFilter');
  const fnCountEl = document.getElementById('fnCount');
  const edgeCountEl = document.getElementById('edgeCount');
  const diagCountEl = document.getElementById('diagCount');
  const layoutFileEl = document.getElementById('layoutFile');
  const analysisPanelEl = document.getElementById('analysisPanel');
  const toggleAnalysisEl = document.getElementById('toggleAnalysis');
  let selectedId = functions[0]?.id || null;
  let selectedGroupId = null;
  const selectedIds = new Set(selectedId ? [selectedId] : []);
  let groupFilterIds = null;
  let analysisVisible = false;
  let view = {{ x: 0, y: 0, scale: 1 }};
  let dragging = null;
  let panning = null;

  const state = {{
    nodes: [],
    nodeById: new Map(),
    visibleEdges: [],
    groups: [],
    groupSeq: 1,
  }};

  function fileLine(loc) {{
    if (!loc) return '';
    const file = String(loc.file || '').split('/').slice(-2).join('/');
    return `${{file}}:${{loc.line || 0}}`;
  }}

  function nodeGeometry(fn) {{
    ctx.save();
    ctx.font = '600 12px system-ui, sans-serif';
    const maxTextWidth = 360;
    const lines = wrapTextLines(fn.name, maxTextWidth, 3);
    const measured = Math.max(...lines.map(line => ctx.measureText(line).width), 40);
    ctx.restore();
    const w = Math.ceil(measured + 34);
    const h = Math.ceil(30 + lines.length * 16);
    const r = Math.hypot(w, h) / 2;
    return {{ w, h, r, lines }};
  }}

  function rebuildGraph() {{
    const term = searchEl.value.trim().toLowerCase();
    const projectOnly = projectOnlyEl.checked;
    const showIndirect = showIndirectEl.checked;
    const directOnly = directOnlyEl.checked;
    const baseIds = groupFilterIds || null;
    const visibleFns = functions.filter(fn => {{
      if (baseIds && !baseIds.has(fn.id)) return false;
      if (!term) return true;
      return `${{fn.name}} ${{fn.id}} ${{fn.display_name || ''}}`.toLowerCase().includes(term);
    }});
    const visibleIds = new Set(visibleFns.map(fn => fn.id));
    const visibleEdges = edges.filter(edge => {{
      if (!visibleIds.has(edge.from)) return false;
      if (edge.to && !visibleIds.has(edge.to) && edge.project_function) return false;
      if (projectOnly && !edge.project_function) return false;
      if (!showIndirect && edge.indirect) return false;
      if (directOnly && groupFilterIds) {{
        const fromSeed = selectedIds.has(edge.from);
        if (!fromSeed) return false;
      }}
      return true;
    }});

    const cols = Math.max(1, Math.ceil(Math.sqrt(visibleFns.length)));
    const spacingX = 340;
    const spacingY = 170;
    const nodes = visibleFns.map((fn, index) => {{
      const col = index % cols;
      const row = Math.floor(index / cols);
      const existing = state.nodeById.get(fn.id);
      const geom = nodeGeometry(fn);
      return {{
        id: fn.id,
        fn,
        x: existing?.x ?? col * spacingX,
        y: existing?.y ?? row * spacingY,
        vx: 0,
        vy: 0,
        w: geom.w,
        h: geom.h,
        r: geom.r,
        labelLines: geom.lines,
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
      button.className = 'fn' + (selectedIds.has(fn.id) ? ' active' : '');
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
    const group = state.groups.find(item => item.id === selectedGroupId);
    if (group) {{
      renderGroupDetails(group);
      return;
    }}
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

  function renderGroupDetails(group) {{
    const visibleCount = group.nodeIds.filter(id => state.nodeById.has(id)).length;
    detailsEl.innerHTML = `
      <h2>${{escapeHtml(group.title || 'Groupe logique')}}</h2>
      <div class="signature">${{visibleCount}} fonction(s) visibles · ${{group.nodeIds.length}} fonction(s) dans le groupe</div>
      <div class="section">
        <h3>Edition</h3>
        <div class="field">
          <label for="groupTitle">Titre</label>
          <input id="groupTitle" value="${{escapeHtml(group.title || '')}}">
        </div>
        <div class="field">
          <label for="groupComment">Commentaire</label>
          <textarea id="groupComment">${{escapeHtml(group.comment || '')}}</textarea>
        </div>
        <div class="field">
          <button id="deleteGroup" class="text-btn danger">Supprimer la boite</button>
        </div>
      </div>
      <div class="section">
        <h3>Fonctions</h3>
        ${{group.nodeIds.map(id => `<div class="row"><div class="row-name">${{escapeHtml(byId.get(id)?.name || id)}}</div><div class="row-meta">${{escapeHtml(id)}}</div></div>`).join('') || '<div class="empty">Aucune</div>'}}
      </div>
    `;
    document.getElementById('groupTitle').addEventListener('input', event => {{
      group.title = event.target.value;
      draw();
    }});
    document.getElementById('groupComment').addEventListener('input', event => {{
      group.comment = event.target.value;
      draw();
    }});
    document.getElementById('deleteGroup').addEventListener('click', () => {{
      state.groups = state.groups.filter(item => item.id !== group.id);
      selectedGroupId = null;
      renderDetails();
      draw();
    }});
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


  function hasAnalysis(fn) {{
    return !!(fn && fn.analysis && typeof fn.analysis === 'object');
  }}

  function formatAccess(item) {{
    if (!item || typeof item !== 'object') return escapeHtml(String(item));
    const parts = [];
    if (item.symbol) parts.push(String(item.symbol));
    if (item.expr && item.expr !== item.symbol) parts.push(String(item.expr));
    if (item.range) parts.push('range=' + String(item.range));
    if (item.reason) parts.push(String(item.reason));
    if (item.location) parts.push(fileLine(item.location));
    return escapeHtml(parts.join(' · ') || JSON.stringify(item));
  }}

  function formatLocal(item) {{
    if (!item || typeof item !== 'object') return escapeHtml(String(item));
    const parts = [];
    if (item.name) parts.push(String(item.name));
    if (item.type) parts.push(String(item.type));
    if (item.storage) parts.push('storage=' + String(item.storage));
    if (Object.prototype.hasOwnProperty.call(item, 'observable')) parts.push('observable=' + String(item.observable));
    if (item.location) parts.push(fileLine(item.location));
    return escapeHtml(parts.join(' · ') || JSON.stringify(item));
  }}

  function listHtml(items, formatter = null) {{
    if (!Array.isArray(items) || !items.length) return '<div class="empty">Aucun</div>';
    return '<ul class="analysis-list">' + items.map(item => `<li>${{formatter ? formatter(item) : escapeHtml(String(item))}}</li>`).join('') + '</ul>';
  }}

  function warningsHtml(items) {{
    if (!Array.isArray(items) || !items.length) return '<div class="empty">Aucun</div>';
    return '<ul class="analysis-list">' + items.map(item => {{
      if (!item || typeof item !== 'object') return `<li>${{escapeHtml(String(item))}}</li>`;
      const parts = [];
      if (item.level) parts.push('[' + item.level + ']');
      if (item.symbol) parts.push(item.symbol);
      if (item.message) parts.push(item.message);
      if (item.reason) parts.push(item.reason);
      if (item.location) parts.push(fileLine(item.location));
      return `<li>${{escapeHtml(parts.join(' · ') || JSON.stringify(item))}}</li>`;
    }}).join('') + '</ul>';
  }}

  function renderAnalysisPanel() {{
    if (!analysisVisible) {{
      analysisPanelEl.classList.remove('visible');
      analysisPanelEl.innerHTML = '';
      return;
    }}
    analysisPanelEl.classList.add('visible');
    const fn = byId.get(selectedId);
    if (!fn) {{
      analysisPanelEl.innerHTML = '<div class="analysis-header"><div class="analysis-title"><b>Analyse mémoire</b><span>Aucune fonction sélectionnée</span></div><button id="closeAnalysis" class="text-btn">Fermer</button></div>';
      document.getElementById('closeAnalysis').addEventListener('click', () => toggleAnalysis(false));
      return;
    }}
    if (!hasAnalysis(fn)) {{
      analysisPanelEl.innerHTML = `
        <div class="analysis-header">
          <div class="analysis-title"><b>Analyse mémoire : ${{escapeHtml(fn.name)}}</b><span>Aucune analyse générée pour cette fonction</span></div>
          <button id="closeAnalysis" class="text-btn">Fermer</button>
        </div>
        <div class="analysis-body"><div class="empty">Le champ <b>analysis</b> est absent du JSON pour cette fonction.</div></div>
      `;
      document.getElementById('closeAnalysis').addEventListener('click', () => toggleAnalysis(false));
      return;
    }}
    const a = fn.analysis || {{}};
    const access = a.access_sets || {{}};
    analysisPanelEl.innerHTML = `
      <div class="analysis-header">
        <div class="analysis-title">
          <b>Analyse mémoire : ${{escapeHtml(fn.name)}}</b>
          <span>${{escapeHtml(fn.display_name || fn.id)}}</span>
        </div>
        <button id="closeAnalysis" class="text-btn">Fermer</button>
      </div>
      <div class="analysis-body">
        <div class="analysis-grid">
          <div class="analysis-card"><h4>Globals lus</h4>${{listHtml(a.globals_read || [])}}</div>
          <div class="analysis-card"><h4>Globals écrits</h4>${{listHtml(a.globals_written || [])}}</div>
          <div class="analysis-card"><h4>Read set</h4>${{listHtml(access.read_set || [], formatAccess)}}</div>
          <div class="analysis-card"><h4>Write set</h4>${{listHtml(access.write_set || [], formatAccess)}}</div>
          <div class="analysis-card"><h4>Variables locales</h4>${{listHtml(a.locals || [], formatLocal)}}</div>
          <div class="analysis-card"><h4>Warnings</h4>${{warningsHtml(a.warnings || [])}}</div>
          <div class="analysis-card"><h4>Annotations requises</h4>${{warningsHtml(a.annotation_required || [])}}</div>
        </div>
        <pre class="analysis-pre">${{escapeHtml(JSON.stringify(a, null, 2))}}</pre>
      </div>
    `;
    document.getElementById('closeAnalysis').addEventListener('click', () => toggleAnalysis(false));
  }}

  function toggleAnalysis(force) {{
    analysisVisible = typeof force === 'boolean' ? force : !analysisVisible;
    renderAnalysisPanel();
  }}

  function visibleFunctions() {{
    const term = searchEl.value.trim().toLowerCase();
    return functions.filter(fn => {{
      if (groupFilterIds && !groupFilterIds.has(fn.id)) return false;
      return !term || `${{fn.name}} ${{fn.id}} ${{fn.display_name || ''}}`.toLowerCase().includes(term);
    }});
  }}

  function selectNode(id, options = {{}}) {{
    selectedId = id;
    selectedGroupId = null;
    if (groupModeEl.checked) {{
      if (selectedIds.has(id)) selectedIds.delete(id);
      else selectedIds.add(id);
      if (!selectedIds.size) selectedIds.add(id);
    }} else {{
      selectedIds.clear();
      selectedIds.add(id);
    }}
    renderList(visibleFunctions());
    renderDetails();
    renderAnalysisPanel();
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

    drawGroups();
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

  function drawGroups() {{
    for (const group of state.groups) {{
      const bounds = groupBounds(group);
      if (!bounds) continue;
      group._bounds = bounds;
      const selected = group.id === selectedGroupId;
      ctx.fillStyle = selected ? 'rgba(15, 118, 110, .16)' : 'rgba(20, 58, 90, .08)';
      ctx.strokeStyle = selected ? '#0f766e' : '#7d8fa2';
      ctx.lineWidth = selected ? 2.5 : 1.4;
      ctx.setLineDash(selected ? [] : [8, 6]);
      roundRect(bounds.x, bounds.y, bounds.w, bounds.h, 10);
      ctx.fill();
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#143a5a';
      ctx.font = '700 14px system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(group.title || 'Groupe logique', bounds.x + 14, bounds.y + 12);
      if (group.comment) {{
        ctx.fillStyle = '#657384';
        ctx.font = '12px system-ui, sans-serif';
        drawWrappedText(group.comment, bounds.x + 14, bounds.y + 34, Math.max(80, bounds.w - 28), 15, 3);
      }}
    }}
  }}

  function groupBounds(group) {{
    const nodes = group.nodeIds.map(id => state.nodeById.get(id)).filter(Boolean);
    if (!nodes.length) return null;
    const minX = Math.min(...nodes.map(node => node.x - node.r)) - 44;
    const maxX = Math.max(...nodes.map(node => node.x + node.r)) + 44;
    const minY = Math.min(...nodes.map(node => node.y - node.r)) - 72;
    const maxY = Math.max(...nodes.map(node => node.y + node.r)) + 40;
    return {{ x: minX, y: minY, w: maxX - minX, h: maxY - minY }};
  }}

  function roundRect(x, y, w, h, r) {{
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }}

  function drawWrappedText(text, x, y, maxWidth, lineHeight, maxLines) {{
    const words = String(text).split(/\\s+/).filter(Boolean);
    let line = '';
    let lines = 0;
    for (const word of words) {{
      const test = line ? line + ' ' + word : word;
      if (ctx.measureText(test).width > maxWidth && line) {{
        ctx.fillText(line, x, y + lines * lineHeight);
        lines++;
        line = word;
        if (lines >= maxLines) return;
      }} else {{
        line = test;
      }}
    }}
    if (line && lines < maxLines) ctx.fillText(line, x, y + lines * lineHeight);
  }}

  function edgePointOnRect(from, to) {{
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    if (!dx && !dy) return {{ x: from.x, y: from.y }};
    const halfW = (from.w || from.r * 2) / 2;
    const halfH = (from.h || from.r * 2) / 2;
    const scale = Math.min(
      Math.abs(dx) > 0 ? halfW / Math.abs(dx) : Infinity,
      Math.abs(dy) > 0 ? halfH / Math.abs(dy) : Infinity,
    );
    return {{ x: from.x + dx * scale, y: from.y + dy * scale }};
  }}

  function drawEdge(a, b, edge) {{
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const start = edgePointOnRect(a, b);
    const end = edgePointOnRect(b, a);
    ctx.strokeStyle = edge.indirect ? '#b91c1c' : '#516170';
    ctx.lineWidth = edge.project_function ? 1.8 : 1.2;
    ctx.setLineDash(edge.indirect || !edge.project_function ? [6, 5] : []);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
    ctx.setLineDash([]);
    drawArrow(end.x, end.y, Math.atan2(dy, dx), ctx.strokeStyle);
  }}

  function drawExternalEdge(a, edge) {{
    const angle = ((edge.to_name || '').length % 12) / 12 * Math.PI * 2;
    const target = {{
      x: a.x + Math.cos(angle) * ((a.w || a.r * 2) / 2 + 70),
      y: a.y + Math.sin(angle) * ((a.h || a.r * 2) / 2 + 70),
    }};
    const start = edgePointOnRect(a, target);
    ctx.strokeStyle = edge.indirect ? '#b91c1c' : '#b45309';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(target.x, target.y);
    ctx.stroke();
    ctx.setLineDash([]);
    drawArrow(target.x, target.y, angle, ctx.strokeStyle);
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
    const selected = selectedIds.has(node.id);
    const out = outgoing.get(node.id)?.length || 0;
    const x = node.x - node.w / 2;
    const y = node.y - node.h / 2;
    ctx.fillStyle = selected ? '#0f766e' : '#ffffff';
    ctx.strokeStyle = selected ? '#99f6e4' : '#9aabba';
    ctx.lineWidth = selected ? 3 : 1.5;
    ctx.setLineDash([]);
    roundRect(x, y, node.w, node.h, 10);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = selected ? '#ffffff' : '#17202a';
    ctx.font = '600 12px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const lines = node.labelLines && node.labelLines.length ? node.labelLines : [node.fn.name];
    const lineHeight = 16;
    const startY = node.y - ((lines.length - 1) * lineHeight) / 2 - 6;
    lines.forEach((line, index) => ctx.fillText(line, node.x, startY + index * lineHeight));

    ctx.fillStyle = selected ? '#dffcf7' : '#657384';
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText(`${{out}} appel(s)`, node.x, node.y + node.h / 2 - 12);
  }}

  function wrapTextLines(text, maxWidth, maxLines) {{
    const value = String(text || '');
    if (!value) return [''];
    const parts = value.split(/([_:.\\/-])/).filter(part => part !== '');
    const lines = [];
    let line = '';
    for (let index = 0; index < parts.length; index++) {{
      const part = parts[index];
      const test = line + part;
      const isLastAllowedLine = lines.length >= maxLines - 1;
      if (!isLastAllowedLine && line && ctx.measureText(test).width > maxWidth) {{
        lines.push(line);
        line = part;
      }} else {{
        line = test;
      }}
    }}
    if (line) lines.push(line);
    if (lines.length > maxLines) {{
      const head = lines.slice(0, maxLines - 1);
      const tail = lines.slice(maxLines - 1).join('');
      return [...head, tail];
    }}
    return lines;
  }}

  function nodeAt(x, y) {{
    const p = screenToWorld(x, y);
    for (let i = state.nodes.length - 1; i >= 0; i--) {{
      const node = state.nodes[i];
      if (p.x >= node.x - node.w / 2 && p.x <= node.x + node.w / 2 && p.y >= node.y - node.h / 2 && p.y <= node.y + node.h / 2) return node;
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

  function createGroupFromSelected() {{
    if (!selectedId || !state.nodeById.has(selectedId)) return;
    const outIds = state.visibleEdges.filter(edge => edge.from === selectedId && edge.to && state.nodeById.has(edge.to)).map(edge => edge.to);
    const inIds = state.visibleEdges.filter(edge => edge.to === selectedId && state.nodeById.has(edge.from)).map(edge => edge.from);
    const nodeIds = [...new Set([selectedId, ...outIds, ...inIds])];
    const fn = byId.get(selectedId);
    const title = window.prompt('Titre de la boite', fn ? fn.name : 'Groupe logique');
    if (title === null) return;
    const comment = window.prompt('Commentaire', '') || '';
    const group = {{
      id: 'group_' + state.groupSeq++,
      title: title.trim() || 'Groupe logique',
      comment,
      nodeIds,
    }};
    state.groups.push(group);
    selectedGroupId = group.id;
    renderDetails();
    draw();
  }}

  function exportLayout() {{
    const layout = {{
      format: 'ctrace-call-map-layout',
      version: 1,
      source_dir: data.source_dir || null,
      selected_id: selectedId,
      view: {{ x: view.x, y: view.y, scale: view.scale }},
      groups: state.groups.map(group => ({{
        id: group.id,
        title: group.title,
        comment: group.comment,
        nodeIds: group.nodeIds,
      }})),
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
      selectedIds.clear();
      selectedIds.add(selectedId);
      selectedGroupId = null;
      renderList(visibleFunctions());
      renderDetails();
    }}
    if (Array.isArray(layout.groups)) {{
      state.groups = layout.groups
        .filter(group => group && Array.isArray(group.nodeIds))
        .map((group, index) => ({{
          id: String(group.id || 'group_' + (index + 1)),
          title: String(group.title || 'Groupe logique'),
          comment: String(group.comment || ''),
          nodeIds: [...new Set(group.nodeIds.filter(id => byId.has(id)))],
        }}));
      state.groupSeq = state.groups.length + 1;
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

  function groupAt(x, y) {{
    const p = screenToWorld(x, y);
    for (let i = state.groups.length - 1; i >= 0; i--) {{
      const bounds = groupBounds(state.groups[i]);
      if (!bounds) continue;
      if (p.x >= bounds.x && p.x <= bounds.x + bounds.w && p.y >= bounds.y && p.y <= bounds.y + bounds.h) {{
        return state.groups[i];
      }}
    }}
    return null;
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


  function computeDirectNeighborhood(seedIds) {{
    const ids = new Set(seedIds);
    for (const edge of edges) {{
      if (seedIds.has(edge.from) && edge.to && edge.project_function) ids.add(edge.to);
    }}
    return ids;
  }}

  function applyGroupFilter() {{
    if (!selectedIds.size) return;
    directOnlyEl.checked = true;
    groupFilterIds = computeDirectNeighborhood(selectedIds);
    rebuildGraph();
    centerBoundsForNodes([...groupFilterIds], 1.45);
    draw();
  }}

  function clearGroupFilter() {{
    groupFilterIds = null;
    directOnlyEl.checked = false;
    rebuildGraph();
    resetView();
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
    const group = node ? null : groupAt(event.offsetX, event.offsetY);
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('dragging');
    if (node) {{
      selectNode(node.id);
      dragging = {{ node, last: screenToWorld(event.offsetX, event.offsetY) }};
    }} else if (group) {{
      selectedGroupId = group.id;
      renderDetails();
      draw();
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
  directOnlyEl.addEventListener('change', rebuildGraph);
  applyGroupFilterEl.addEventListener('click', applyGroupFilter);
  clearGroupFilterEl.addEventListener('click', clearGroupFilter);
  document.getElementById('zoomIn').addEventListener('click', () => {{ view.scale = Math.min(3, view.scale * 1.2); draw(); }});
  document.getElementById('zoomOut').addEventListener('click', () => {{ view.scale = Math.max(.08, view.scale / 1.2); draw(); }});
  document.getElementById('focusNeighborhood').addEventListener('click', arrangeAroundSelected);
  document.getElementById('createGroup').addEventListener('click', createGroupFromSelected);
  document.getElementById('resetView').addEventListener('click', resetView);
  document.getElementById('exportLayout').addEventListener('click', exportLayout);
  document.getElementById('importLayout').addEventListener('click', () => layoutFileEl.click());
  toggleAnalysisEl.addEventListener('click', () => toggleAnalysis());
  layoutFileEl.addEventListener('change', () => {{
    importLayoutFile(layoutFileEl.files && layoutFileEl.files[0]);
    layoutFileEl.value = '';
  }});
  window.addEventListener('resize', resize);

  rebuildGraph();
  resize();
  renderAnalysisPanel();
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
