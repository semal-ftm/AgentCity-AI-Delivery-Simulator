// Agent City - application controller: state, playback, controls and the secondary views.
import { CityView, ROUTE_COLORS } from './city3d.js';
import { renderStep, PHASES, esc, rb } from './panel.js';
import { hbar, curve } from './charts.js';

const MIN_PER_SEC = 2.4;      // simulated minutes per real second at 1x (a 24-minute delivery ≈ 10 s)
const DWELL = 3.6;            // seconds a reasoning step stays on screen at 1x
const PHASE_COLOR = { observe: '#4cc9f0', reason: '#9d7bff', decide: '#ffc233', act: '#06d6a0', respond: '#ff9f6b', result: '#ef476f' };
const AGENT_ICON = { simple_reflex: '⚡', model_based: '🗂', goal_based: '🎯', utility_based: '⚖', learning: '🧠', hierarchical: '🪜', contextual: '🧭' };
const SIT_ICON = { 1: '☀️', 2: '🚦', 3: '⛈️' };

const $ = id => document.getElementById(id);
const S = { init: null, sit: 1, agent: 'simple_reflex', run: null, step: -1, t: 0, playing: false, speed: 1, runIndex: 0,
  dwell: 0, watched: {}, view: 'sim', compare: null, cmpSit: 1, bookKey: 'simple_reflex', token: 0, loading: false, mindTab: 'reason', delivery: 1 };
let city;

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const agentMeta = k => S.init.agents.find(a => a.key === k);
const sitData = id => (S.init.situations_by_delivery[S.delivery] || S.init.situations).find(s => s.id === id);
const delData = d => S.init.world.deliveries[d || S.delivery];
function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('on'), 2600); }

// ======================================================================= boot
async function boot() {
  const ld = document.createElement('div'); ld.className = 'loading'; ld.textContent = 'Building the city…'; document.body.appendChild(ld);
  try { S.init = await api('/api/init'); } catch (e) { ld.textContent = 'Could not reach the simulator: ' + e.message; return; }
  window.WORLD = S.init.world;
  ld.remove();
  if (S.init.api_version !== 4) {
    const w = document.createElement('div'); w.className = 'stale-warning';
    w.innerHTML = '⚠ The simulator server that is running is an <b>older version</b>, so some panels (like “Why this route?”) will be empty. Close the old server window (Ctrl+C) and start it again with <code>python app.py</code>, then refresh this page.';
    document.body.prepend(w);
  }
  city = new CityView($('city'), S.init.world);
  city.tip = routeTip;
  bindControls();
  const q = new URLSearchParams(location.hash.slice(1));             // deep link: #sit=3&agent=goal_based&step=9&view=compare
  if (q.get('agent') && agentMeta(q.get('agent'))) S.agent = q.get('agent');
  if (q.get('step')) S.pendingStep = +q.get('step') - 1;
  if (q.get('play')) S.autoplay = true;
  if (q.get('speed')) { S.speed = +q.get('speed') || 1; $('speed').value = String(S.speed); }
  if (q.get('del') && delData(+q.get('del'))) setDelivery(+q.get('del'), false);
  selectSituation(+q.get('sit') || 1);
  if (q.get('view')) { S.cmpSit = +q.get('sit') || 1; setView(q.get('view')); }
  if (q.get('tab')) setMindTab(q.get('tab'));
  if (q.get('theme')) applyTheme(q.get('theme'));
  let last = performance.now();
  const loop = now => { const dt = Math.min(0.1, (now - last) / 1000); last = now; tick(dt); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}

// ----- light / dark background
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('theme', t); } catch (e) { /* storage blocked: theme still applies for this visit */ }
  $('themeBtn').textContent = t === 'light' ? '🌙 Dark mode' : '☀️ Light mode';
}

function bindControls() {
  applyTheme(document.documentElement.dataset.theme || 'light');
  $('themeBtn').onclick = () => applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  $('tabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setView(b.dataset.view); });
  $('btnStart').onclick = start;
  $('btnPause').onclick = togglePause;
  $('btnReset').onclick = () => { reset(); };
  $('btnNext').onclick = () => { S.playing = false; next(); };
  $('btnPrev').onclick = () => { S.playing = false; prev(); };
  $('speed').onchange = e => { S.speed = +e.target.value; };
  $('btnCompare').onclick = () => { S.cmpSit = S.sit; setView('compare'); };
  $('mindTabs').onclick = e => { const b = e.target.closest('button'); if (b) setMindTab(b.dataset.t); };
  document.addEventListener('keydown', e => {
    if (S.view !== 'sim' || e.target.matches('input, select')) return;
    if (e.code === 'Space') { e.preventDefault(); S.step < 0 ? start() : togglePause(); }
    else if (city && city.hovered && e.key.startsWith('Arrow')) return;   // over the map, arrows move the view
    else if (e.key === 'ArrowRight') { S.playing = false; next(); }
    else if (e.key === 'ArrowLeft') { S.playing = false; prev(); }
    else if (e.key === 'r' || e.key === 'R') reset();
    else if (/^[1-7]$/.test(e.key)) selectAgent(S.init.agents[+e.key - 1].key);
  });
}

// ======================================================================= selection
function selectSituation(id) {
  S.sit = id; S.run = null; reset(false);
  city.setSituation(sitData(id));
  renderSituations(); renderAgents(); renderBanner(); renderMind(); loadRun();
}

function selectAgent(key) {
  if (key === S.agent && S.run) { reset(); return; }       // same agent again: back to the Start button
  S.agent = key; S.run = null; reset(false);
  renderAgents(); renderMind(); loadRun();
}

async function loadRun() {
  const token = ++S.token;
  S.loading = true; S.run = null; reset(false); renderIntro();
  try {
    const run = await api('/api/run', { situation: S.sit, agent: S.agent, run_index: S.runIndex, delivery: S.delivery });
    if (token !== S.token) return;
    S.run = run;
  } catch (e) { toast('Error: ' + e.message); }
  S.loading = false;
  renderAll();
  if (S.run && S.pendingStep != null) { const k = S.pendingStep; S.pendingStep = null; goStep(k); }
  if (S.run && S.autoplay) { S.autoplay = false; start(); }
}

// ======================================================================= playback
function start() {
  if (!S.run) return;
  S.rcClosed = false;
  if (S.step < 0 || S.step >= S.run.steps.length - 1) goStep(0);
  S.playing = true; renderControls();
}
function togglePause() { if (!S.run) return; if (S.step < 0) return start(); S.playing = !S.playing; if (S.playing && S.step >= S.run.steps.length - 1) goStep(0); renderControls(); }
function reset(render = true) { S.playing = false; S.rcClosed = false; S.step = -1; S.t = 0; S.dwell = 0; if (render) renderAll(); }
function next() { if (!S.run) return; if (S.step < S.run.steps.length - 1) goStep(S.step + 1); else { S.playing = false; renderControls(); } }
function prev() { if (!S.run) return; if (S.step > 0) goStep(S.step - 1); else reset(); }

function goStep(k) {
  const steps = S.run.steps;
  S.step = Math.max(0, Math.min(steps.length - 1, k)); S.dwell = 0;
  const st = steps[S.step];
  S.t = st.phase === 'act' ? st.t[0] : st.t[1];     // stored timestamps: restoring a step never recomputes anything
  if (st.kind === 'result') {
    const t = S.run.trip; S.watched[`${S.delivery}:${S.sit}:${S.agent}`] = { route: t.route, on_time: t.on_time, reward: t.reward };
    renderAgents();
  }
  renderAll();
}

function dwellFor(st) { return (['utility', 'table', 'context', 'task', 'goal-test', 'state', 'result', 'response'].includes(st.kind) ? DWELL * 1.4 : DWELL); }

function tick(dt) {
  if (S.view !== 'sim' || !city) return;
  if (S.playing && S.run && S.step >= 0) {
    const st = S.run.steps[S.step];
    if (st.phase === 'act') {
      S.t += dt * MIN_PER_SEC * S.speed;
      if (S.t >= st.t[1]) { S.t = st.t[1]; advance(); }
    } else {
      S.dwell += dt * S.speed;
      if (S.dwell >= dwellFor(st)) advance();
    }
  }
  updateCity(); renderBottom();
}
function advance() { if (S.step < S.run.steps.length - 1) goStep(S.step + 1); else { S.playing = false; renderControls(); } }

// ======================================================================= map
function cumulativeMarks() {
  const m = {};
  if (!S.run) return m;
  for (let i = 0; i <= S.step; i++) { const s = S.run.steps[i]; if (['observe', 'reason', 'decide'].includes(s.phase)) Object.assign(m, s.marks || {}); }
  return m;
}
function decideIndex() { return S.run ? S.run.steps.findIndex(s => s.phase === 'decide') : -1; }

function updateCity() {
  const r = S.run, st = r && S.step >= 0 ? r.steps[S.step] : null;
  const dIdx = decideIndex();
  city.setView({
    marks: st ? cumulativeMarks() : {}, focus: st ? st.focus || [] : [],
    chosen: st && S.step >= dIdx ? r.decision.route : null,
    t: S.t, trip: st && ['act', 'respond', 'result'].includes(st.phase) ? r.trip : null,
    phase: st ? st.phase : 'idle', thought: st ? thought(st) : '',
    delivered: st && st.phase === 'result' ? r.trip : null, color: agentMeta(S.agent).color, riderName: agentMeta(S.agent).short,
  });
}
function thought(st) { return st.title.replace(/^Percept /, 'Seeing ').replace(/^Action: /, ''); }

function routeTip(rid) {
  const w = S.init.world.routes[rid], sit = sitData(S.sit), tr = S.run && S.run.truth[rid];
  const lvl = sit.traffic[w.key_zone] || 'normal';
  const m = cumulativeMarks()[rid];
  return [`Route ${rid} · ${w.name}`, w.summary,
    tr ? `${tr.distance_km} km · ${tr.signals} traffic lights${tr.toll ? ' · toll ' + tr.toll + ' CU' : ''}${tr.flood_km ? ' · flooding' : ''}` : '',
    `Ground truth now: ${lvl} traffic${tr ? ` → about ${tr.travel_min.toFixed(1)} min ride, safety ${tr.safety.toFixed(2)}` : ''}`,
    m ? `Agent's view: ${m}` : ''].filter(Boolean);
}

// ======================================================================= render: left panel
// ----- choose the source -> destination (delivery 1 is the default; delivery 2 is the optional new one)
function setDelivery(d, reload = true) {
  S.delivery = d;
  S.init.learning = S.init.learning_by_delivery[d];
  city.setDelivery(d);
  S.compare = null;
  if (reload) selectSituation(S.sit);
  else renderDeliveries();
}
function renderDeliveries() {
  const items = Object.entries(S.init.world.deliveries);
  $('delPick').innerHTML = `<div class="del-label">📍 Source → destination</div><div class="del-btns">${items.map(([d, D]) =>
    `<button class="${+d === S.delivery ? 'on' : ''}" data-d="${d}" title="${esc(D.from)} → ${esc(D.to)}"><b>${+d === 1 ? '🏠' : '🆕'} ${esc(D.title)}</b><small>${esc(D.direction)}</small></button>`).join('')}</div>`;
  $('delPick').querySelectorAll('button').forEach(b => b.onclick = () => { if (+b.dataset.d !== S.delivery) setDelivery(+b.dataset.d); });
}

function renderSituations() {
  renderDeliveries();
  $('sitList').innerHTML = S.init.situations.map(b => sitData(b.id)).map(s => `<button class="sit${s.id === S.sit ? ' on' : ''}" data-id="${s.id}">
    <span class="ico">${SIT_ICON[s.id]}</span><span><b>${s.id}. ${esc(s.name)}</b><small>${s.clock} · ${s.weather} · deadline ${s.order.deadline_min} min${s.order.urgent ? ' · urgent' : ''}</small></span></button>`).join('');
  $('sitList').querySelectorAll('.sit').forEach(b => b.onclick = () => selectSituation(+b.dataset.id));
}

function renderAgents() {
  $('agentList').innerHTML = S.init.agents.map((a, i) => {
    const w = S.watched[`${S.delivery}:${S.sit}:${a.key}`];
    return `<button class="agent${a.key === S.agent ? ' on' : ''}" data-key="${a.key}" style="--c:${a.color}" title="Key ${i + 1}">
      <span class="avatar">${AGENT_ICON[a.key]}</span><span><b>${esc(a.name)}</b><small>${esc(a.architecture)}</small></span>
      ${w ? `<span class="watched" title="Watched in this situation">${rb(w.route)}${w.on_time ? '<span class="ok">✓</span>' : '<span class="bad">✕</span>'}</span>` : '<span></span>'}</button>`;
  }).join('');
  $('agentList').querySelectorAll('.agent').forEach(b => b.onclick = () => selectAgent(b.dataset.key));
}

function renderControls() {
  const has = !!S.run, last = has ? S.run.steps.length - 1 : 0;
  $('btnStart').disabled = !has;
  $('btnStart').textContent = S.step >= last && has && S.step >= 0 ? '↻ Replay simulation' : S.step >= 0 ? '▶ Restart from step 1' : '▶ Start simulation';
  if (S.step >= 0 && S.step < last) $('btnStart').textContent = '▶ Restart from step 1';
  $('btnPause').textContent = S.playing ? '⏸ Pause' : '▶ Resume';
  $('btnPause').disabled = !has || S.step < 0;
  $('btnPrev').disabled = !has || S.step < 0;
  $('btnNext').disabled = !has || S.step >= last;
}

// ======================================================================= render: map overlays
function renderBanner() {
  const s = sitData(S.sit);
  $('sitBanner').title = s.description;
  $('sitBanner').innerHTML = `<span class="tag del">📍 ${esc(s.order.restaurant)} → ${esc(s.order.customer.split(',')[0])}</span><b>${SIT_ICON[s.id]} Situation ${s.id}: ${esc(s.name)}</b>
    <span class="tag">🕘 ${s.clock}</span><span class="tag">${s.weather === 'rain' ? '🌧 Rain' : '☀ Clear'}${s.night ? ' · night' : ''}</span>
    <span class="tag">⏱ Deadline ${s.order.deadline_min} min</span>${s.order.urgent ? '<span class="tag hot">🔥 Urgent</span>' : ''}<span class="desc">${esc(s.description)}</span>`;
}

function renderLegend() {
  const m = cumulativeMarks(), chosen = S.run && S.step >= decideIndex() && S.step >= 0 ? S.run.decision.route : null;
  $('routeLegend').innerHTML = ['A', 'B', 'C', 'D'].map(r => {
    const st = chosen === r ? 'chosen' : m[r] || '';
    return `<div>${rb(r)} ${esc(S.init.world.routes[r].name.split(' (')[0])}</div><div class="st ${st}">${st ? { chosen: '✓ chosen', rejected: '✕ rejected', unknown: '? unseen', checking: '… checking', candidate: 'candidate' }[st] || st : ''}</div>`;
  }).join('');
}

function renderIntro() {
  const el = $('mapIntro'), a = agentMeta(S.agent), s = sitData(S.sit);
  if (S.step >= 0) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = S.loading ? `<h2>Preparing the delivery…</h2><p>The ${esc(a.name)} is receiving its percepts.</p>`
    : `<h2>${AGENT_ICON[a.key]} ${esc(a.name)}</h2><p>Situation ${s.id}: ${esc(s.name)}. Watch the agent observe the city, reason, choose a route and ride it.</p><button class="btn go" id="introStart">▶ Start simulation</button>`;
  const b = $('introStart'); if (b) b.onclick = start;
}

function renderBottom() {
  const el = $('mapBottom');
  if (!S.run || S.step < 0) { el.hidden = true; return; }
  el.hidden = false;
  const st = S.run.steps[S.step], trip = S.run.trip, dl = trip.deadline_min, mx = Math.max(trip.total_min, dl) * 1.04;
  const ph = PHASES.find(p => p[0] === st.phase);
  el.innerHTML = `<span class="ph" style="background:${PHASE_COLOR[st.phase]}">${ph[2]} ${ph[1]}</span><span class="tt">${esc(st.title)}</span>
    <span class="clock">⏱ ${S.t.toFixed(1)} / ${dl} min</span><div class="bar"><i style="width:${S.t / mx * 100}%"></i><u style="left:${dl / mx * 100}%"></u></div>`;
}

// ======================================================================= render: mind panel
function setMindTab(t) {
  S.mindTab = t;
  $('mindTabs').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  $('reasonPane').hidden = t !== 'reason'; $('whyPane').hidden = t !== 'why'; $('rulesPane').hidden = t !== 'rules';
  $('memoryPane').hidden = t !== 'memory';
  renderWhy(); renderRules(); renderMemory();
}

// ----- Learning agent: its real learned memory, its learning history, and the customer feedback log
const FB_KEY = 'learningFeedback';
function loadFeedback() { try { return JSON.parse(localStorage.getItem(FB_KEY) || '[]'); } catch (e) { return S.fbMem || []; } }
function saveFeedback(list) { S.fbMem = list; try { localStorage.setItem(FB_KEY, JSON.stringify(list)); } catch (e) { /* keep in memory only */ } }
const SIT_SHORT = (id, d) => `${d && d !== 1 ? 'Delivery ' + d + ' · ' : ''}S${id} ${sitData(id) ? sitData(id).short : ''}`;
const describeState = s => {
  const [w, u, tr] = s.split('|'), lv = { L: 'light', N: 'normal', H: 'heavy', '?': 'unknown' };
  return `${w === 'rain' ? 'rain' : 'clear weather'}, ${u === 'urgent' ? 'urgent order' : 'normal order'}; traffic ` + tr.split(' ').map(x => `${x[0]} ${lv[x[1]]}`).join(', ');
};

function renderMemory() {
  $('memTabBtn').hidden = S.agent !== 'learning';
  if (S.agent !== 'learning' && S.mindTab === 'memory') { setMindTab('reason'); return; }
  if (S.mindTab !== 'memory') return;
  const L = S.init.learning, row = L.test_states[S.sit], sit = sitData(S.sit);
  const vals = Object.values(row.q), lo = Math.min(0, ...vals), hi = Math.max(1, ...vals);
  const learnStep = S.run && S.step >= 0 ? S.run.steps.slice(0, S.step + 1).find(s => s.kind === 'learn') : null;
  const ep = h => `<li><b>#${h.episode}</b> ${h.situation ? 'Situation ' + h.situation : 'random situation'} · ${h.explored ? '🎲 tried something new' : '⭐ used its experience'}:
      route ${rb(h.action)}, ${h.minutes} min ${h.on_time ? '<span class="ok">on time</span>' : '<span class="bad">late</span>'}, score <b class="${h.reward >= 0 ? 'ok' : 'bad'}">${h.reward >= 0 ? '+' : ''}${h.reward.toFixed(1)}</b>
      <span class="mem-chg">memory of ${h.action}: ${h.q_old.toFixed(2)} → <b>${h.q_new.toFixed(2)}</b></span></li>`;
  const fb = loadFeedback();
  const stars = n => '★'.repeat(n) + '☆'.repeat(5 - n);
  $('memoryPane').innerHTML = `
    <div class="mem-intro">The Learning agent's memory is a table of what it has learned from <b>${L.episodes} practice deliveries</b>. For every kind of situation it remembers how well each route scored on average. It is saved in <code>${esc(L.q_file || 'data/q_table.json')}</code>${S.delivery !== 1 ? ' (a separate memory for this delivery)' : ''}.</div>
    <div class="mem-tiles"><div><small>Practice deliveries</small><b>${L.episodes}</b></div><div><small>Situations remembered</small><b>${L.states}</b></div>
      <div><small>Avg score, first ${L.window}</small><b class="bad">${L.first_avg}</b></div><div><small>Avg score, last ${L.window}</small><b class="ok">${L.last_avg}</b></div></div>

    <h4>What it remembers about this situation</h4>
    <p class="mem-sub">Situation ${sit.id}: ${esc(sit.name)}, which the agent sees as <i>${esc(describeState(row.state))}</i>.</p>
    <div class="qbars">${Object.entries(row.q).map(([a, v]) => `<div class="qb${a === row.greedy ? ' hl' : ''}">${rb(a)}<div class="qtrack"><i style="left:${(Math.min(0, v) - lo) / (hi - lo) * 100}%;width:${Math.abs(v) / (hi - lo) * 100}%;background:${v < 0 ? '#ef476f' : ROUTE_COLORS[a]}"></i><u style="left:${-lo / (hi - lo) * 100}%"></u></div><b>${v.toFixed(2)}</b><small>tried ${row.n[a]}×</small></div>`).join('')}</div>
    <p class="mem-sub">Bars show the average score each route earned here. ${row.greedy ? `Its best memory is route ${rb(row.greedy)}, so that is what it chooses.` : 'It has no memory of this situation yet.'}</p>

    ${learnStep ? `<h4>Learned from this delivery</h4><div class="mem-update">This delivery scored <b>${learnStep.data.reward >= 0 ? '+' : ''}${learnStep.data.reward.toFixed(2)}</b>, so its memory of route ${rb(learnStep.data.action)} moved from <b>${learnStep.data.q_old.toFixed(3)}</b> to <b>${learnStep.data.q_new.toFixed(3)}</b> (this was visit number ${learnStep.data.visits}).</div>` : ''}

    <h4>Learning history</h4>
    <p class="mem-sub">How its memory changed while practising. At first it tried routes at random; later it mostly used its experience.</p>
    <h5 class="mem-h5">First practice deliveries</h5><ol class="mem-hist">${L.first_episodes.map(ep).join('')}</ol>
    <h5 class="mem-h5">Latest practice deliveries</h5><ol class="mem-hist">${(L.last_episodes || []).map(ep).join('')}</ol>

    <h4>Customer feedback history <small>(${fb.length})</small></h4>
    <p class="mem-sub">Ratings given after Learning-agent deliveries. They are kept here as a record for review; the route values above come from the delivery scores.</p>
    ${fb.length ? `<div class="fb-list">${fb.slice().reverse().map(f => `<div class="fb-item"><div class="fb-top"><span class="stars">${stars(f.stars)}</span><span>${esc(SIT_SHORT(f.sit, f.delivery))} · route ${rb(f.route)} · ${f.minutes} min ${f.on_time ? '<span class="ok">on time</span>' : '<span class="bad">late</span>'}</span></div>
        ${f.tags.length ? `<div class="fb-tags">${f.tags.map(t => `<span>${esc(t)}</span>`).join('')}</div>` : ''}${f.comment ? `<p>“${esc(f.comment)}”</p>` : ''}<small>${esc(f.when)}</small></div>`).join('')}</div>
      <button class="btn sm" id="fbClear">Clear feedback history</button>` : '<div class="why-empty">No feedback yet. Run the Learning agent and rate the delivery on the result card.</div>'}`;
  const c = $('fbClear'); if (c) c.onclick = () => { saveFeedback([]); renderMemory(); };
}

// ----- 'Rules': the agent's complete rulebook, readable at any pace; rules used in this run are marked
function renderRules() {
  if (S.mindTab !== 'rules') return;
  const a = agentMeta(S.agent), r = S.run, decided = r && S.step >= 0 && S.step >= decideIndex();
  const used = new Set(decided ? (r.fired_rules || []) : []);
  $('rulesPane').innerHTML = `<div class="rules-intro">These are all the rules the <b>${esc(a.name)}</b> follows when it chooses a route. This list stays still, so you can read it at your own pace.
      ${decided ? '<span class="ok">The rules marked ✓ are the ones it used in this delivery.</span>' : 'Once the agent has made its choice, the rules it used are marked ✓.'}</div>`
    + a.rulebook.map(sec => `<div class="rb-sec"><h4>${esc(sec.title)}</h4>${sec.rules.map(x => `<div class="rb-rule${used.has(x.id) ? ' used' : ''}">
        <b class="rid">${esc(x.id)}</b>
        <div class="rtext">${esc(x.text)}</div>
        ${used.has(x.id) ? '<em>✓ used</em>' : ''}</div>`).join('')}</div>`).join('');
}

// ----- 'Why this route?': the agent's own reason for every route + what each route would actually have delivered
function renderWhy() {
  try { renderWhyInner(); }
  catch (e) { $('whyPane').innerHTML = `<div class="why-empty"><b>Could not show the explanation.</b><p>${esc(e.message)}</p></div>`; }
}
function renderWhyInner() {
  const el = $('whyPane'), r = S.run, a = agentMeta(S.agent);
  const ready = r && S.step >= 0 && S.step >= decideIndex();
  $('whyDot').hidden = !ready || S.mindTab === 'why';
  if (S.mindTab !== 'why') return;
  if (!r) { el.innerHTML = '<div class="why-empty">Loading…</div>'; return; }
  if (!ready) {
    el.innerHTML = `<div class="why-empty"><div class="big">🧭</div><b>Start the simulation first.</b><p>As soon as the ${esc(a.name)} decides, this tab shows which route it took, on what basis, and why every other route was not selected.</p>
      <button class="btn go" id="whyStart">▶ Start simulation</button></div>`;
    $('whyStart').onclick = start;
    return;
  }
  if (!r.route_reasons || !r.route_outcomes) {
    el.innerHTML = '<div class="why-empty"><div class="big">⚠</div><b>This run came from an older server.</b><p>Stop the running server (Ctrl+C in its window), start it again with <code>python app.py</code> and refresh the page.</p></div>';
    return;
  }
  const R = r.route_reasons, O = r.route_outcomes, ch = r.decision.route, best = r.best_route, sit = sitData(S.sit);
  const order = [ch, ...['A', 'B', 'C', 'D'].filter(x => x !== ch)];
  const label = { chosen: '✓ Chosen', rejected: '✕ Not chosen', 'not considered': '– Never looked at' };
  const cards = order.map(rt => {
    const n = R[rt] || { status: 'not considered', reason: '' }, o = O[rt], cls = n.status.replace(' ', '-');
    return `<div class="why-card ${cls}" style="--c:${ROUTE_COLORS[rt]}">
      <div class="wc-head">${rb(rt)}<b>${esc(S.init.world.routes[rt].name)}</b><span class="wc-pill">${label[n.status]}</span></div>
      <p>${esc(n.reason)}</p>
      <div class="wc-out"><span>What would have happened on this route</span> (average of ${o.runs} trial deliveries): about <b>${Math.round(o.time)} minutes</b>,
        on time in <span class="${o.on_time >= 90 ? 'ok' : 'bad'}">${o.on_time}%</span> of trials, score <b class="${o.reward >= 0 ? 'ok' : 'bad'}">${o.reward >= 0 ? '+' : ''}${o.reward}</b>.${rt === best ? ' <span class="best">★ This route actually did best.</span>' : ''}</div></div>`;
  }).join('');
  const verdict = ch === best
    ? `<div class="why-verdict ok">✓ Good choice: route ${ch} is also the route that actually did best in this situation.</div>`
    : `<div class="why-verdict bad">✕ Looking back, route ${best} would have been the better choice: its average score was ${O[best].reward >= 0 ? '+' : ''}${O[best].reward}, compared with ${O[ch].reward >= 0 ? '+' : ''}${O[ch].reward} for route ${ch}. The explanations above show which weakness of the ${esc(a.short)} agent led to this.</div>`;
  el.innerHTML = `<div class="why-top">Situation ${sit.id}: ${esc(sit.name)} · the <b>${esc(a.name)}</b> chose route ${rb(ch)}${r.decision.notify_customer ? ' and warned the customer that the order may be late' : ''}</div>
    <div class="why-basis"><small>Why it chose this route</small>${esc(r.decision.reason)}.</div>${cards}${verdict}
    <p class="hint">Each explanation was written by the agent while it was deciding. The "what would have happened" lines come from simulating every route 200 times in the same conditions.</p>`;
}
function renderMind() {
  const a = agentMeta(S.agent);
  $('mindHead').innerHTML = `<span class="avatar" style="--c:${a.color}">${AGENT_ICON[a.key]}</span><div><h2>${esc(a.name)}</h2><small>${esc(a.architecture)}</small></div>
    <button class="btn" id="howBtn">📐 Diagram</button>`;
  renderRules();
  $('howBtn').onclick = () => { S.bookKey = a.key; setView('book'); };
}

function renderPhases() {
  const cur = S.run && S.step >= 0 ? S.run.steps[S.step].phase : null;
  const idx = cur ? PHASES.findIndex(p => p[0] === cur) : -1;
  $('phases').innerHTML = PHASES.map(([k, l, ic], i) => `<div class="${i < idx ? 'done' : i === idx ? 'on' : ''}" style="--pc:${PHASE_COLOR[k]}"><span>${ic}</span>${l}</div>`).join('');
}

function renderStepCard() {
  const el = $('stepCard'), a = agentMeta(S.agent);
  if (!S.run || S.step < 0) {
    el.innerHTML = `<div class="intro"><h3>What this agent does</h3><p>${esc(a.info.definition)}</p><p><b>Principle:</b> ${esc(a.info.principle)}</p>
      <p class="hint">Press <b>Start</b>. Every step on the right is read from the agent's own execution trace: the rules it matched, its memory, its predictions, scores and Q-values.</p></div>`;
    return;
  }
  const st = S.run.steps[S.step];
  el.innerHTML = `<div class="sh"><h3>${esc(st.title)}</h3><span class="sn">step ${S.step + 1} / ${S.run.steps.length}</span></div>${renderStep(st, S.run)}`;
}

function renderLog() {
  const el = $('stepLog');
  if (!S.run) { el.innerHTML = ''; return; }
  const n = S.run.steps.length;
  el.innerHTML = S.run.steps.slice(0, Math.max(0, S.step + 1)).map((s, i) => `<li class="${i === S.step ? 'on' : 'done'}" data-i="${i}" style="--pc:${PHASE_COLOR[s.phase]}"><i></i><span>${i + 1}. ${esc(s.title)}</span></li>`).join('')
    + (S.step < n - 1 ? `<li class="muted"><i style="opacity:.3"></i><span>${n - 1 - S.step} more step(s)…</span></li>` : '');
  el.querySelectorAll('li[data-i]').forEach(li => li.onclick = () => { S.playing = false; goStep(+li.dataset.i); });
}

function renderTimeline() {
  const el = $('timeline');
  if (!S.run) { el.innerHTML = '<span class="empty">Loading the agent\'s timeline…</span>'; return; }
  el.innerHTML = S.run.steps.map((s, i) => `<button class="tl ${i === S.step ? 'on' : i < S.step ? 'done' : ''}" data-i="${i}" data-n="${i + 1}" style="--pc:${PHASE_COLOR[s.phase]}" title="${i + 1}. ${esc(s.phase)}: ${esc(i <= S.step ? s.title : '')}"></button>`).join('');
  el.querySelectorAll('.tl').forEach(b => b.onclick = () => { S.playing = false; goStep(+b.dataset.i); });
}

function renderResultCard() {
  const el = $('mapResult'), r = S.run;
  const show = r && S.step >= 0 && r.steps[S.step].phase === 'result' && !S.rcClosed;
  el.hidden = !show;
  if (!show) return;
  const t = r.trip, m = r.mc, a = agentMeta(S.agent), i = S.init.agents.findIndex(x => x.key === S.agent), nxt = S.init.agents[(i + 1) % S.init.agents.length];
  el.innerHTML = `<button class="rc-close" id="rcClose" title="Close">✕</button><div class="rc-head ${t.on_time ? 'ok' : 'late'}">${t.on_time ? '🎉 On time' : '⏰ Late'} <span>${esc(a.short)} chose route ${rb(t.route)}</span></div>
    <div class="rc-grid"><div><small>Time</small><b>${t.total_min.toFixed(1)}<i>/${t.deadline_min}m</i></b></div><div><small>Cost</small><b>${t.cost.toFixed(2)}<i> CU</i></b></div>
    <div><small>Safety</small><b>${t.safety.toFixed(2)}</b></div><div><small>Reward</small><b class="${t.reward >= 0 ? 'ok' : 'bad'}">${t.reward >= 0 ? '+' : ''}${t.reward.toFixed(2)}</b></div></div>
    <p>Over ${m.runs} runs of this decision: <b>${m.on_time}%</b> on time, mean reward <b>${m.reward >= 0 ? '+' : ''}${m.reward}</b>.</p>
    ${S.agent === 'learning' ? feedbackForm() : ''}
    <div class="rc-btns"><button class="btn go" id="rcNext">▶ Same situation, next agent: ${esc(nxt.short)}</button>
    <button class="btn" id="rcWhy">🧭 Why this route?</button><button class="btn" id="rcCmp">📊 Compare</button><button class="btn" id="rcReplay">↻ Replay</button></div>`;
  $('rcWhy').onclick = () => setMindTab('why');
  $('rcClose').onclick = closeResultCard;
  if (S.agent === 'learning') bindFeedback(t);
  $('rcNext').onclick = () => { selectAgent(nxt.key); S.autoplay = true; };
  $('rcCmp').onclick = () => { S.cmpSit = S.sit; setView('compare'); };
  $('rcReplay').onclick = () => { goStep(0); S.playing = true; renderControls(); };
}

// ----- feedback form on the Learning agent's result card
const FB_TAGS = ['Fast delivery', 'Food was hot', 'Too slow', 'Food was cold', 'Food spilled', 'Risky road'];
function feedbackForm() {
  const key = `${S.sit}:${S.runIndex}`;
  if (S.fbSent === key) return `<div class="fb-done">✓ Thanks! Your feedback was saved to the Learning agent's history. <button class="link" id="fbOpen">View memory</button></div>`;
  const f = S.fb && S.fb.key === key ? S.fb : (S.fb = { key, stars: 0, tags: [], comment: '' });
  return `<div class="fb-form"><b>Rate this delivery</b>
    <div class="fb-stars">${[1, 2, 3, 4, 5].map(n => `<button data-s="${n}" class="${n <= f.stars ? 'on' : ''}" title="${n} star${n > 1 ? 's' : ''}">★</button>`).join('')}</div>
    <div class="fb-tagpick">${FB_TAGS.map(t => `<button data-t="${t}" class="${f.tags.includes(t) ? 'on' : ''}">${t}</button>`).join('')}</div>
    <div class="fb-send"><input id="fbComment" placeholder="Comment (optional)" value="${esc(f.comment)}" maxlength="140">
    <button class="btn" id="fbSave" ${f.stars ? '' : 'disabled'}>Submit ⏎</button></div>
    ${f.stars ? '' : '<small class="fb-hint">Choose 1–5 stars, then press Enter or Submit.</small>'}</div>`;
}
function bindFeedback(t) {
  const o = $('fbOpen'); if (o) { o.onclick = () => setMindTab('memory'); return; }
  const f = S.fb, el = $('mapResult');
  el.querySelectorAll('.fb-stars button').forEach(b => b.onclick = () => { f.stars = +b.dataset.s; renderResultCard(); });
  el.querySelectorAll('.fb-tagpick button').forEach(b => b.onclick = () => { const x = b.dataset.t; f.tags = f.tags.includes(x) ? f.tags.filter(y => y !== x) : [...f.tags, x]; renderResultCard(); });
  $('fbComment').oninput = e => { f.comment = e.target.value; };
  $('fbComment').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); if (f.stars) $('fbSave').click(); else toast('Choose 1–5 stars first'); } };
  $('fbSave').onclick = () => {
    saveFeedback([...loadFeedback(), { delivery: S.delivery, sit: S.sit, route: t.route, minutes: t.total_min.toFixed(1), on_time: t.on_time, stars: f.stars, tags: f.tags, comment: f.comment.trim(), when: new Date().toLocaleString() }]);
    S.fbSent = f.key; toast('✓ Feedback submitted. You can see it in the 💾 Memory tab.'); closeResultCard(); renderMemory();
  };
}

function closeResultCard() { S.rcClosed = true; renderResultCard(); }

function renderAll() { renderWhy(); renderRules(); renderMemory(); renderIntro(); renderResultCard(); renderControls(); renderPhases(); renderStepCard(); renderLog(); renderTimeline(); renderLegend(); renderBottom(); }

// ======================================================================= views
function setView(v) {
  S.view = v;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  document.querySelectorAll('.view').forEach(m => m.classList.toggle('on', m.id === 'view-' + v));
  if (v === 'compare') renderCompare();
  if (v === 'book') renderBook();
}

async function renderCompare() {
  if (!S.compare || S.compareDel !== S.delivery) {
    $('cmpTable').innerHTML = '<tbody><tr><td class="muted">Running all seven agents on all three situations…</td></tr></tbody>';
    S.compare = await api('/api/compare_all?delivery=' + S.delivery); S.compareDel = S.delivery;
  }
  $('cmpTabs').innerHTML = Object.entries(S.init.world.deliveries).map(([d, D]) => `<button class="del ${+d === S.delivery ? 'on' : ''}" data-del="${d}">${+d === 1 ? '🏠' : '🆕'} ${esc(D.title)}</button>`).join('') + '<span class="seg-sep"></span>' + S.init.situations.map(s => `<button class="${s.id === S.cmpSit ? 'on' : ''}" data-id="${s.id}">${SIT_ICON[s.id]} ${s.id}. ${esc(s.short)}</button>`).join('');
  $('cmpTabs').querySelectorAll('button').forEach(b => b.onclick = () => { if (b.dataset.del) { if (+b.dataset.del !== S.delivery) { setDelivery(+b.dataset.del); renderCompare(); } return; } S.cmpSit = +b.dataset.id; renderCompare(); });
  const C = S.compare.find(c => c.situation === S.cmpSit), rows = C.rows, sit = sitData(S.cmpSit);
  $('cmpSub').textContent = `${delData().title}: ${sit.order.restaurant} → ${sit.order.customer.split(',')[0]} · ${sit.name} · deadline ${sit.order.deadline_min} min · ${C.runs} runs per decision, seed ${C.seed}`;
  $('cmpTable').innerHTML = `<thead><tr><th>Agent</th><th>Route</th><th>Basis of the decision</th><th>Forecast</th><th>Delivery time</th><th>Cost (CU)</th><th>Safety</th><th>On time</th><th>Incidents</th><th>Reward</th><th>Utility</th></tr></thead><tbody>
    ${rows.map(r => `<tr data-key="${r.agent}"><td><div class="agent-cell"><span class="avatar" style="--c:${r.color}">${AGENT_ICON[r.agent]}</span><b>${esc(r.name)}</b></div></td>
    <td>${rb(r.route)}${r.notify ? ' 📣' : ''}</td><td class="muted reason-cell">${esc(r.reason)}</td><td>${r.predicted != null ? r.predicted + ' min' : '—'}</td>
    <td>${r.time} min <small class="muted">±${r.time_sd}</small></td><td>${r.cost}</td><td>${r.safety}</td>
    <td><span class="pill ${r.on_time >= 90 ? 'ok' : 'bad'}">${r.on_time}%</span></td><td>${r.incidents}%</td><td><b class="${r.reward >= 0 ? 'ok' : 'bad'}">${r.reward >= 0 ? '+' : ''}${r.reward}</b></td><td>${r.utility != null ? r.utility.toFixed(1) : '—'}</td></tr>`).join('')}</tbody>`;
  $('cmpTable').querySelectorAll('tbody tr').forEach(tr => tr.onclick = () => openAgent(S.cmpSit, tr.dataset.key));
  const mk = (key, d) => rows.map(r => ({ label: r.short, value: r[key], sub: `route ${r.route}`, highlight: r.agent === S.agent, key: r.agent }));
  const click = r => openAgent(S.cmpSit, r.key);
  hbar($('chTime'), mk('time'), { unit: ' min', title: 'Mean delivery time', ref: { value: sit.order.deadline_min, label: 'deadline' }, onClick: click });
  hbar($('chOnTime'), mk('on_time'), { unit: '%', title: 'Deliveries on time', max: 100, onClick: click });
  hbar($('chReward'), mk('reward'), { digits: 2, title: 'Mean reward', onClick: click });
  curve($('chLearn'), S.init.learning.curve);
  $('learnNote').textContent = `Learning agent: mean reward ${S.init.learning.first_avg} in the first ${S.init.learning.window} episodes → ${S.init.learning.last_avg} in the last ${S.init.learning.window}.`;
  const agents = S.init.agents;
  $('matrix').innerHTML = `<thead><tr><th>Agent</th>${S.compare.map(c => `<th>${SIT_ICON[c.situation]} ${esc(sitData(c.situation).short)}</th>`).join('')}<th>Mean reward</th></tr></thead><tbody>
    ${agents.map(a => { const cells = S.compare.map(c => c.rows.find(r => r.agent === a.key)); const mean = cells.reduce((s, r) => s + r.reward, 0) / cells.length;
      return `<tr data-key="${a.key}"><td><div class="agent-cell"><span class="avatar" style="--c:${a.color}">${AGENT_ICON[a.key]}</span><b>${esc(a.name)}</b></div></td>
      ${cells.map((r, i) => `<td data-sit="${S.compare[i].situation}">${rb(r.route)} <span class="pill ${r.on_time >= 90 ? 'ok' : 'bad'}">${r.on_time}%</span></td>`).join('')}
      <td><b class="${mean >= 0 ? 'ok' : 'bad'}">${mean >= 0 ? '+' : ''}${mean.toFixed(2)}</b></td></tr>`; }).join('')}</tbody>`;
  $('matrix').querySelectorAll('td[data-sit]').forEach(td => td.onclick = e => { e.stopPropagation(); openAgent(+td.dataset.sit, td.parentElement.dataset.key); });
  renderConclusion();
}

// ----- comparison and conclusion, written from the measured results
function renderConclusion() {
  const agents = S.init.agents, C = S.compare;
  const mean = k => C.reduce((s, c) => s + c.rows.find(r => r.agent === k).reward, 0) / C.length;
  const lines = C.map(c => {
    const sit = sitData(c.situation), byRoute = {};
    c.rows.forEach(r => (byRoute[r.route] = byRoute[r.route] || []).push(r));
    const best = Object.keys(byRoute).sort((a, b) => byRoute[b][0].reward - byRoute[a][0].reward)[0];
    const groups = Object.entries(byRoute).sort((a, b) => b[1][0].reward - a[1][0].reward).map(([rt, rs]) =>
      `${rs.map(r => esc(r.short)).join(', ')} → ${rb(rt)} (${rs[0].on_time}% on time, reward ${rs[0].reward >= 0 ? '+' : ''}${rs[0].reward})`).join('; ');
    const worse = c.rows.filter(r => r.route !== best).map(r => `<li><b>${esc(r.short)}</b> chose ${rb(r.route)}: ${esc(r.reason)}.</li>`).join('');
    return `<h4>${SIT_ICON[c.situation]} Situation ${c.situation}: ${esc(sit.name)}</h4><p>${groups}.</p>${worse ? `<ul>${worse}</ul>` : '<p class="muted">All agents chose the same route.</p>'}`;
  }).join('');
  $('comparison').innerHTML = lines + `<p class="hint">Same information and the same evaluation for every agent: the differences come only from each architecture's way of using that information (rules only, memory, goal test, weighted utility, learned values, subtasks or context).</p>`;
  const rank = agents.map(a => ({ a, m: mean(a.key) })).sort((x, y) => y.m - x.m);
  const noTrain = rank.filter(x => x.a.key !== 'learning'), topNT = noTrain[0].m;
  const tied = noTrain.filter(x => Math.abs(x.m - topNT) < 0.01).map(x => x.a);
  const rec = tied.find(a => a.key === 'contextual') || tied[0];
  const learn = rank.find(x => x.a.key === 'learning');
  $('conclusion').innerHTML = `<ol class="rank">${rank.map(x => `<li><span class="avatar" style="--c:${x.a.color}">${AGENT_ICON[x.a.key]}</span>${esc(x.a.name)}<b class="${x.m >= 0 ? 'ok' : 'bad'}">${x.m >= 0 ? '+' : ''}${x.m.toFixed(2)}</b></li>`).join('')}</ol>
    <p><b>Most suitable for this scenario: ${esc(rec.name)}.</b> Among the agents that need no training it has the best mean reward over the three situations (${topNT >= 0 ? '+' : ''}${topNT.toFixed(2)}${tied.length > 1 ? `, shared with ${tied.filter(a => a !== rec).map(a => esc(a.short)).join(', ')}` : ''}).
    ${rec.key === 'contextual' ? 'It recognises the situation (calm, congested, storm + urgent) and switches strategy, so it handles missing sensor data and the urgent rainy delivery while staying easy to explain.' : ''}</p>
    <p>The Learning agent scored ${learn.m >= 0 ? '+' : ''}${learn.m.toFixed(2)}${learn === rank[0] ? ', the highest overall,' : ''} but only after ${S.init.learning.episodes} simulated training deliveries, and it only knows situations similar to those it was trained on.
    Fixed rules without a deadline (Simple Reflex) and fixed utility weights (Utility-Based) did worst in the urgent storm.</p>`;
}

function openAgent(sit, key) {
  setView('sim');
  S.agent = key;
  if (sit !== S.sit) selectSituation(sit); else { S.run = null; renderAgents(); renderMind(); loadRun(); }
}

function renderBook() {
  const items = S.init.agents.map(a => [a.key, a.name, a.color]);
  const cur = S.bookKey;
  const nav = `<div class="book-nav">${items.map(([k, n, c]) => `<button class="agent${k === cur ? ' on' : ''}" data-key="${k}" style="--c:${c}"><span class="avatar">${AGENT_ICON[k] || '🏙'}</span><span><b>${esc(n)}</b></span><span></span></button>`).join('')}</div>`;
  let body;
  if (cur === 'system') {
    body = `<h2>System architecture</h2><p class="arch">How the simulator is put together.</p><img src="/api/diagram/system.svg" alt="System architecture diagram">
      <div class="book-grid"><div><h4>Engine</h4><p>Road network graph (intersections and road segments), traffic and weather simulators, route evaluation and a delivery environment that executes the chosen route edge by edge with random variation, red lights and incidents.</p></div>
      <div><h4>Agents</h4><p>Seven independent Python classes with the same perceive → decide interface. Each writes its own reasoning trace; the dashboard only displays it.</p></div>
      <div><h4>Evaluation</h4><p>One performance measure for all: +10 on time, −0.8 per late minute (−5 more if urgent), −0.3 × cost, −15 × (1 − safety), −10 per incident. Every decision is executed 200 times with the same seeds for all agents.</p></div>
      <div><h4>Dashboard</h4><p>Standard-library Python HTTP server and a dependency-free browser app: canvas city, SVG charts and diagrams.</p></div></div>`;
  } else {
    const a = agentMeta(cur), I = a.info;
    body = `<h2>${AGENT_ICON[a.key]} ${esc(a.name)}</h2><p class="arch">${esc(a.architecture)}</p>
      <img src="/api/diagram/${a.key}.svg" alt="${esc(a.name)} architecture diagram">
      <div class="book-grid"><div><h4>Definition</h4><p>${esc(I.definition)}</p></div><div><h4>Working principle</h4><p>${esc(I.principle)}</p></div>
      <div><h4>Implementation in this project</h4><p>${esc(I.logic)}</p></div><div><h4>Example decision</h4><p>${esc(I.example)}</p></div>
</div>
      <p style="margin-top:14px"><button class="btn go" style="width:auto" id="bookWatch">▶ Watch this agent deliver</button></p>`;
  }
  $('book').innerHTML = nav + `<div class="book-body">${body}</div>`;
  $('book').querySelectorAll('.book-nav .agent').forEach(b => b.onclick = () => { S.bookKey = b.dataset.key; renderBook(); });
  const w = $('bookWatch'); if (w) w.onclick = () => openAgent(S.sit, cur);
}

boot();
