// Renders one step of an agent's trace. Every number shown comes from the step's data,
// which the agent itself wrote while deciding (see agents/*.py).
import { ROUTE_COLORS } from './city3d.js';
import { stack } from './charts.js';

export const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const PHASES = [
  ['observe', 'Observe', '👁'], ['reason', 'Reason', '🧠'], ['decide', 'Decide', '🎯'],
  ['act', 'Act', '🛵'], ['respond', 'Respond', '🌧'], ['result', 'Result', '🏁'],
];
const LV = { light: 'Light', normal: 'Normal', heavy: 'Heavy' };
export const rb = (r, extra = '') => `<span class="rb${extra}" style="--c:${ROUTE_COLORS[r] || '#888'}">${r}</span>`;
const lvl = v => v ? `<span class="lv lv-${v}">${LV[v] || v}</span>` : '<span class="lv lv-none">no report</span>';
const num = (v, d = 1) => (v === null || v === undefined) ? '—' : (+v).toFixed(d);

export function renderStep(step, run) {
  const d = step.data || {};
  const body = (WIDGETS[step.kind] || (() => ''))(d, step, run);
  const snap = step.snapshot ? renderSnapshot(step.snapshot, step) : '';
  return `<div class="step-text">${esc(step.text)}</div>${body}${snap}`;
}

function renderSnapshot(s, step) {
  if (s.tasks && !(step.data && step.data.tasks)) return tasks(s.tasks);
  if (s.state && step.phase !== 'observe') return `<div class="mini-state">Internal state · order status: <b>${esc(s.state.order_status)}</b> · current route: ${s.state.current_route ? rb(s.state.current_route) : '—'}</div>`;
  return '';
}

function tasks(list, running) {
  const icon = { pending: '○', running: '◐', completed: '●' };
  return `<ol class="tasks">${list.map((t, i) => `<li class="t-${t.status}${t.id === running ? ' now' : ''}">
    <span class="ti">${icon[t.status]}</span><div><b>${i + 1}. ${esc(t.name)}</b> <em>${t.status}</em>
    ${t.deps.length ? `<small>needs ${t.deps.map(d => list.findIndex(x => x.id === d) + 1).join(', ')}</small>` : ''}
    ${t.result ? `<p>${esc(t.result)}</p>` : ''}</div></li>`).join('')}</ol>`;
}

function reportTable(reports, weather) {
  return `<div class="chips">${Object.entries(reports).map(([r, v]) => `<div class="chip">${rb(r)} ${lvl(v)}</div>`).join('')}
    <div class="chip">${weather === 'rain' ? '🌧 Rain' : '☀ Clear'}</div></div>`;
}

function estTable(rows, cols) {
  const C = {
    km: ['km', r => num(r.km, 1)], travel: ['ride', r => num(r.travel) + 'm'], arrival: ['arrive', r => num(r.arrival) + 'm'],
    adj: ['arrive*', r => num(r.arrival_adj) + 'm'], slack: ['slack', r => `<span class="${r.slack >= 0 ? 'ok' : 'bad'}">${r.slack >= 0 ? '+' : ''}${num(r.slack)}</span>`],
    cost: ['cost', r => num(r.cost, 2)], safety: ['safety', r => num(r.safety, 2)],
    goal: ['goal', r => r.goal ? '<span class="ok">✓ met</span>' : '<span class="bad">✕ fails</span>'],
    flags: ['', r => [r.flooded ? '🌊' : '', r.toll ? '💰' : '', r.note ? `<small>${esc(r.note)}</small>` : ''].join(' ')],
  };
  return `<table class="tbl"><thead><tr><th>route</th>${cols.map(c => `<th>${C[c][0]}</th>`).join('')}</tr></thead><tbody>
    ${rows.map(r => `<tr>${'<td>' + rb(r.route) + '</td>'}${cols.map(c => `<td>${C[c][1](r)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

function rulesTable(rules) {
  const st = { fired: ['✓ fired', 'ok'], false: ['✕ false', 'bad'], skipped: ['skipped', 'mut'], 'not checked': ['…', 'mut'] };
  return `<div class="rules">${rules.map(r => `<div class="rule r-${r.status.replace(' ', '-')}"><b>${r.id}</b><div>${esc(r.if)}<br><span>${esc(r.then)}</span></div><em class="${st[r.status][1]}">${st[r.status][0]}</em></div>`).join('')}</div>`;
}

function stateCol(title, st) {
  if (!st || !st.traffic) return `<div class="scol"><h5>${title}</h5><p class="muted">empty</p></div>`;
  const rows = Object.entries(st.traffic).map(([r, v]) => `<div>${rb(r)} ${lvl(v.level)} <small>${v.source}${v.seen ? ' @' + v.seen : ''}${v.age ? ` · ${v.age}m old` : ''}</small></div>`).join('');
  return `<div class="scol"><h5>${title}</h5>${rows || '<p class="muted">no beliefs yet</p>'}
    <div class="smeta">weather: ${esc(st.weather || '?')}${st.flooded && st.flooded.length ? ` · flooded: ${st.flooded.join(', ')}` : ''}</div></div>`;
}

const WIDGETS = {
  env: (d, s, run) => {
    const sc = run.scenario, o = sc.order;
    return `<div class="sit-grid">
      <div><small>Time</small><b>${sc.clock}</b><span>${esc(sc.time_of_day)}</span></div>
      <div><small>Weather</small><b>${sc.weather === 'rain' ? '🌧 Rain' : '☀ Clear'}</b><span>${sc.night ? 'night' : 'daylight'}</span></div>
      <div><small>Deadline</small><b>${o.deadline_min} min</b><span>${o.urgent ? '🔥 urgent' : 'standard'}</span></div>
      <div><small>Food</small><b>${esc(o.food)}</b><span>ready in ${o.prep_min} min</span></div></div>
      <table class="tbl"><thead><tr><th>route</th><th>road</th><th>km</th><th>lights</th><th></th></tr></thead><tbody>
      ${Object.entries(run.truth).map(([r, t]) => `<tr><td>${rb(r)}</td><td>${esc(window.WORLD.routes[r].name)}</td><td>${num(t.distance_km)}</td><td>${t.signals}</td><td>${t.toll ? '💰 toll' : ''}${t.flood_km ? ' 🌊 floods' : ''}</td></tr>`).join('')}
      </tbody></table><p class="hint">True traffic is drawn on the map (red glow = heavy). The agent only learns about it through its percepts.</p>`;
  },
  percept: d => reportTable(d.reports, d.weather),
  forget: d => `<div class="forgot">${reportTable(d.forgotten, '')}</div>`,
  state: (d, s) => {
    if (d.previous) return `<div class="state3">${stateCol('Previous state', d.previous)}<div class="sarrow">→<small>percept</small></div>${stateCol('Updated state', d.updated)}</div>
      ${d.changes && d.changes.length ? `<ul class="changes">${d.changes.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}`;
    if (d.state) return `<div class="chips">${Object.entries(d.state).map(([r, v]) => `<div class="chip">${rb(r)} ${esc(v)}</div>`).join('')}</div>${d.rules ? rulesTable(d.rules) : ''}`;
    return '';
  },
  rule: d => rulesTable(d.rules || []),
  table: d => {
    const cols = d.class ? ['arrival', 'adj', 'slack', 'cost', 'safety', 'flags'] : ['km', 'arrival', 'slack', 'cost', 'safety', 'flags'];
    return estTable(d.rows || [], cols) + (d.excluded && Object.keys(d.excluded).length ? `<ul class="changes">${Object.entries(d.excluded).map(([r, w]) => `<li>${rb(r)} excluded: ${esc(w)}</li>`).join('')}</ul>` : '') + (d.rules ? rulesTable(d.rules) : '');
  },
  goal: d => `<div class="goal-card"><div class="gc-ico">🎯</div><div><b>arrival ≤ ${d.deadline} min</b><span>prep ${d.prep} min → ride budget ${d.budget} min</span></div></div>
    <div class="chips">${Object.entries(d.beliefs).map(([r, v]) => `<div class="chip">${rb(r)} ${esc(v)}</div>`).join('')}</div>`,
  'goal-test': d => goalBars(d.rows, d.deadline) + estTable(d.rows, ['km', 'arrival', 'slack', 'goal']),
  'goal-fail': d => estTable(d.rows, ['km', 'arrival', 'slack', 'goal']),
  utility: d => {
    const W = d.weights, colors = { time: '#4cc9f0', safety: '#06d6a0', cost: '#ffc233', distance: '#c77dff' };
    const rows = (d.rows || []).map(r => ({ label: r.route, color: ROUTE_COLORS[r.route], parts: r.contrib, total: r.utility, highlight: r.route === d.chosen }));
    return `<div class="legend">${Object.keys(W).map(k => `<span><i style="background:${colors[k]}"></i>${k} ×${W[k]}</span>`).join('')}</div>
      ${stack(rows, Object.keys(W), colors)}
      <table class="tbl"><thead><tr><th>route</th><th>Time</th><th>Safety</th><th>Cost</th><th>Dist.</th><th>U</th></tr></thead><tbody>
      ${(d.rows || []).map(r => `<tr class="${r.route === d.chosen ? 'hl' : ''}"><td>${rb(r.route)}</td><td>${num(r.scores.time, 0)}</td><td>${num(r.scores.safety, 0)}</td><td>${num(r.scores.cost, 0)}</td><td>${num(r.scores.distance, 0)}</td><td><b>${num(r.utility)}</b></td></tr>`).join('')}
      </tbody></table><p class="hint">Scores are 0–100: Time = 100 × fastest/this, Cost = 100 × cheapest/this, Distance = 100 × shortest/this, Safety = 100 × predicted safety.</p>`;
  },
  q: d => {
    if (!d.q) return '';
    const vals = Object.values(d.q), lo = Math.min(0, ...vals), hi = Math.max(1, ...vals);
    return `<div class="qstate"><small>state s</small><code>${esc(d.state)}</code><span>${esc(d.meaning)}</span></div>
      <div class="qbars">${Object.entries(d.q).map(([a, v]) => `<div class="qb${a === d.chosen ? ' hl' : ''}">${rb(a)}<div class="qtrack"><i style="left:${(Math.min(0, v) - lo) / (hi - lo) * 100}%;width:${Math.abs(v) / (hi - lo) * 100}%;background:${v < 0 ? '#ef476f' : ROUTE_COLORS[a]}"></i><u style="left:${(-lo) / (hi - lo) * 100}%"></u></div><b>${num(v, 2)}</b><small>n=${d.n[a]}</small></div>`).join('')}</div>
      ${d.episodes !== undefined ? `<p class="hint">Q-table learned from ${d.episodes} training episodes. n = how many deliveries taught each value.</p>` : ''}`;
  },
  task: d => tasks(d.tasks, d.running),
  context: d => {
    const c = d.context;
    const f = [['Weather', c.weather + (c.night ? ' · night' : '')], ['Time', c.time_of_day], ['Urgent', c.urgent ? 'yes' : 'no'],
      ['Heavy routes', c.heavy_routes.join(', ') || 'none'], ['Missing reports', c.missing_reports.join(', ') || 'none'],
      ['Old info', c.stale.join(', ') || 'none'], ['Food', c.food + (c.spill_sensitive ? ' (spill-sensitive)' : '')], ['Best-case slack', c.slack + ' min']];
    return `<div class="ctx">${f.map(([k, v]) => `<div><small>${k}</small><b>${esc(v)}</b></div>`).join('')}</div>
      ${d.strategy ? `<div class="strategy"><span class="ctx-class">${esc(d.strategy.label)}</span><div><b>${esc(d.strategy.objective)}</b>${d.strategy.safety_floor ? ` · safety ≥ ${d.strategy.safety_floor}` : ''}<p>${esc(d.strategy.text)}</p></div></div>` : ''}`;
  },
  decision: (d, s, run) => `<div class="decision" style="--c:${ROUTE_COLORS[run.decision.route]}">${rb(run.decision.route, ' big')}<div><b>Route ${run.decision.route}: ${esc(window.WORLD.routes[run.decision.route].name)}</b>
      <span>${run.decision.predicted_total_min != null ? `agent's forecast: arrive at ${num(run.decision.predicted_total_min)} min` : 'no forecast (reflex agent)'}${run.decision.notify_customer ? ' · 📣 customer notified' : ''}</span></div></div>
      ${d.tasks ? tasks(d.tasks) : ''}${d.rules ? rulesTable(d.rules) : ''}`,
  pickup: (d, s, run) => progress(s, run),
  ride: (d, s, run) => `<div class="chips"><div class="chip">🛣 ${num(d.km)} km</div><div class="chip">${lvl(d.level)} traffic</div><div class="chip">⏱ ${num(d.drive)} min</div>${d.wait > 0.05 ? `<div class="chip">🚦 ${num(d.wait)} min</div>` : ''}${d.incident ? `<div class="chip bad">⚠ incident</div>` : ''}</div>${progress(s, run)}`,
  response: d => {
    const mx = Math.max(d.actual, d.predicted || 0) * 1.05;
    const bar = (label, v, cls) => `<div class="rbar"><span>${label}</span><div><i class="${cls}" style="width:${v / mx * 100}%"></i></div><b>${num(v)}</b></div>`;
    return `${bar('free-flow ride', d.free_flow, 'c1')}${bar('actual driving', d.driving, 'c2')}${bar('red lights', d.signals, 'c3')}
      ${d.predicted != null ? bar("agent's forecast (total)", d.predicted, 'c4') : ''}${bar('actual total', d.actual, 'c5')}
      <ul class="events">${d.events.filter(e => e.kind !== 'signal').map(e => `<li class="ev-${e.kind}"><b>${num(e.t)}m</b> ${esc(e.text)}</li>`).join('')}</ul>`;
  },
  result: d => {
    const t = d.trip, m = d.mc;
    return `<div class="tiles">
      <div class="tile ${t.on_time ? 'good' : 'badt'}"><small>Delivery time</small><b>${num(t.total_min)}<i>/${t.deadline_min} min</i></b><span>${t.on_time ? 'on time' : 'late ' + num(t.late_min) + ' min'}</span></div>
      <div class="tile"><small>Cost</small><b>${num(t.cost, 2)}<i> CU</i></b><span>${num(t.distance_km)} km</span></div>
      <div class="tile"><small>Safety</small><b>${num(t.safety, 2)}</b><span>${t.incident ? '⚠ incident' : 'no incident'}</span></div>
      <div class="tile ${t.reward >= 0 ? 'good' : 'badt'}"><small>Reward</small><b>${t.reward >= 0 ? '+' : ''}${num(t.reward, 2)}</b><span>performance measure</span></div></div>
      <div class="mc"><b>Same decision, ${m.runs} simulated runs:</b> on time ${m.on_time}% · mean ${m.time} min (±${m.time_sd}) · cost ${m.cost} · safety ${m.safety} · incidents ${m.incidents}% · mean reward ${m.reward >= 0 ? '+' : ''}${m.reward}</div>`;
  },
  learn: d => `<div class="learn"><div><small>Q before</small><b>${num(d.q_old, 3)}</b></div><div class="op">+ ${d.alpha} × (</div><div><small>reward</small><b>${num(d.reward, 2)}</b></div><div class="op">− ${num(d.q_old, 2)}) =</div><div class="hl"><small>Q after</small><b>${num(d.q_new, 3)}</b></div></div>
    <p class="hint">State ${esc(d.state)}, action ${d.action}, visit #${d.visits}. α = max(0.02, 1/n).</p>`,
};

function goalBars(rows, deadline) {
  const mx = Math.max(deadline, ...rows.map(r => r.arrival)) * 1.08;
  return `<div class="gbars">${rows.map(r => `<div class="gb">${rb(r.route)}<div class="gtrack"><i class="${r.goal ? 'ok' : 'bad'}" style="width:${r.arrival / mx * 100}%"></i><u style="left:${deadline / mx * 100}%"></u></div><b>${num(r.arrival)}m</b></div>`).join('')}
    <div class="gleg"><u></u> deadline ${deadline} min</div></div>`;
}

function progress(s, run) {
  const tot = run.trip.total_min, dl = run.trip.deadline_min, mx = Math.max(tot, dl) * 1.04;
  return `<div class="prog"><div class="ptrack"><i style="width:${s.t[1] / mx * 100}%"></i><u style="left:${dl / mx * 100}%"></u></div><small>${num(s.t[1])} / ${dl} min (deadline)</small></div>`;
}
