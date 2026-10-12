// Small dependency-free SVG charts with hover tooltips.
const NS = 'http://www.w3.org/2000/svg';
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let tipEl;
function tip() {
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'chart-tip'; document.body.appendChild(tipEl); }
  return tipEl;
}
export function showTip(ev, html) { const t = tip(); t.innerHTML = html; t.style.display = 'block'; const x = Math.min(ev.clientX + 14, innerWidth - t.offsetWidth - 8); t.style.left = x + 'px'; t.style.top = (ev.clientY + 14) + 'px'; }
export function hideTip() { tip().style.display = 'none'; }

/**
 * Horizontal bar chart, one bar per category.
 * rows: [{label, value, sub?, highlight?}]  opts: {unit, digits, max, ref:{value,label}, better:'low'|'high', title}
 */
export function hbar(el, rows, opts = {}) {
  const d = opts.digits ?? 1, unit = opts.unit || '';
  const max = opts.max ?? (Math.max(...rows.map(r => r.value), opts.ref ? opts.ref.value : 0) * 1.12 || 1);
  const min = Math.min(0, ...rows.map(r => r.value));
  const span = max - min || 1;
  const W = 460, rowH = 30, labelW = 118, top = 8, H = top + rows.length * rowH + 22;
  const x = v => labelW + (v - min) / span * (W - labelW - 50);
  let s = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(opts.title || '')}">`;
  for (let k = 0; k <= 4; k++) { const v = min + span * k / 4, xx = x(v); s += `<line x1="${xx}" y1="${top}" x2="${xx}" y2="${H - 20}" class="grid"/><text x="${xx}" y="${H - 6}" class="tick" text-anchor="middle">${(+v.toFixed(span < 10 ? 1 : 0))}</text>`; }
  if (min < 0) s += `<line x1="${x(0)}" y1="${top}" x2="${x(0)}" y2="${H - 20}" class="zero"/>`;
  rows.forEach((r, i) => {
    const y = top + i * rowH + 5, x0 = x(Math.min(0, r.value)), w = Math.max(2, Math.abs(x(r.value) - x(0)));
    s += `<g class="bar-row${r.highlight ? ' hl' : ''}" data-i="${i}">
      <rect x="0" y="${y - 4}" width="${W}" height="${rowH}" class="hit"/>
      <text x="${labelW - 8}" y="${y + 14}" class="lbl" text-anchor="end">${esc(r.label)}</text>
      <rect x="${x0}" y="${y + 2}" width="${w}" height="${rowH - 12}" rx="4" class="bar${r.value < 0 ? ' neg' : ''}"/>
      <text x="${r.value < 0 ? x(0) + 6 : x0 + w + 6}" y="${y + 14}" class="val" text-anchor="start">${r.value.toFixed(d)}${unit}</text></g>`;
  });
  if (opts.ref) { const xx = x(opts.ref.value); s += `<line x1="${xx}" y1="${top - 4}" x2="${xx}" y2="${H - 20}" class="ref"/><text x="${xx + 4}" y="${top + 6}" class="ref-lbl">${esc(opts.ref.label)}</text>`; }
  s += '</svg>';
  el.innerHTML = s;
  el.querySelectorAll('.bar-row').forEach(g => {
    const r = rows[+g.dataset.i];
    g.addEventListener('mousemove', ev => showTip(ev, `<b>${esc(r.label)}</b><br>${esc(opts.title || '')}: <b>${r.value.toFixed(d)}${unit}</b>${r.sub ? '<br>' + esc(r.sub) : ''}`));
    g.addEventListener('mouseleave', hideTip);
    if (opts.onClick) g.addEventListener('click', () => opts.onClick(r));
  });
}

/** Learning curve: raw episode rewards (faint dots) + moving average line, with crosshair tooltip. */
export function curve(el, points, opts = {}) {
  const W = 620, H = 230, L = 44, R = 12, T = 12, B = 30;
  if (!points.length) { el.innerHTML = '<p class="muted">No training yet.</p>'; return; }
  const n = points.length;
  const ys = points.map(p => p.reward);
  const lo = Math.max(-35, Math.min(...ys)), hi = Math.max(...ys, 10);
  const X = i => L + (i / Math.max(1, n - 1)) * (W - L - R), Y = v => T + (hi - Math.max(lo, v)) / (hi - lo) * (H - T - B);
  const step = Math.max(1, Math.floor(n / 600));
  let s = `<svg viewBox="0 0 ${W} ${H}" class="chart curve" role="img" aria-label="Learning reward progression">`;
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${L - 6}" y="${Y(v) + 4}" class="tick" text-anchor="end">${v.toFixed(0)}</text>`; }
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" class="zero"/>`;
  for (let i = 0; i < n; i += step) s += `<circle cx="${X(i)}" cy="${Y(ys[i])}" r="1.6" class="dot"/>`;
  s += `<path d="${points.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p.avg).toFixed(1)}`).join('')}" class="line"/>`;
  for (let k = 0; k <= 4; k++) { const i = Math.round((n - 1) * k / 4); s += `<text x="${X(i)}" y="${H - 8}" class="tick" text-anchor="middle">${points[i].episode}</text>`; }
  s += `<text x="${W - R}" y="${H - 8}" class="tick" text-anchor="end" dy="-14">episode</text>`;
  s += `<line class="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" style="display:none"/><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" class="hit"/></svg>`;
  el.innerHTML = s;
  const svg = el.querySelector('svg'), cross = svg.querySelector('.cross');
  svg.querySelector('.hit').addEventListener('mousemove', ev => {
    const r = svg.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width * W;
    const i = Math.max(0, Math.min(n - 1, Math.round((fx - L) / (W - L - R) * (n - 1)))), p = points[i];
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.style.display = '';
    showTip(ev, `<b>Episode ${p.episode}</b><br>reward ${p.reward.toFixed(2)}<br>moving average ${p.avg.toFixed(2)}<br>ε = ${p.epsilon}`);
  });
  svg.querySelector('.hit').addEventListener('mouseleave', () => { cross.style.display = 'none'; hideTip(); });
}

/** Stacked horizontal bar of utility contributions (one row per route). */
export function stack(rows, keys, colors, max = 100) {
  return rows.map(r => `<div class="stack-row${r.highlight ? ' hl' : ''}"><span class="rb" style="--c:${r.color}">${r.label}</span><div class="stack">${keys.map(k =>
    `<i style="width:${(r.parts[k] / max * 100).toFixed(2)}%;background:${colors[k]}" title="${k}: ${r.parts[k].toFixed(1)}"></i>`).join('')}</div><b>${r.total.toFixed(1)}</b></div>`).join('');
}
