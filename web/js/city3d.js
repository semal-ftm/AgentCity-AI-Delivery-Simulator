// Agent City - isometric low-poly 3D city (three.js, loaded as the global THREE).
// Streets, intersections, signals and routes come from the backend road-network graph, so the
// rider drives exactly the edges the environment executed. Buildings are generated per block
// with a seeded random generator, so the city looks the same on every visit.
/* global THREE */

export const ROUTE_COLORS = { A: '#e63995', B: '#13b5a4', C: '#f59e0b', D: '#3b6cf6' };
const ROUTE_ORDER = ['A', 'B', 'C', 'D'];
const ROAD_W = { expressway: 2.0, arterial: 1.7, boulevard: 1.8, street: 0.8, lane: 1.4, link: 1.6 };   // route roads wide, side streets narrow
const CAR_COLORS = [0xd9d9de, 0xb8bcc6, 0x8d95a3, 0x6f7a8a, 0xe8e4da, 0x9aa5b1, 0x7d8a99, 0xc4c9d1];   // muted, so the agent's rider stands out
const DENSITY = { light: 0.5, normal: 0.9, heavy: 2.4 };          // cars per km per direction
const CAR_SPEED = { light: 1.6, normal: 1.05, heavy: 0.28 };      // tiles per second
const SKY = { clear: 0xbfe6ff, rush: 0xffc89a, night: 0x10163a };

function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export class CityView {
  constructor(canvas, world) {
    this.w = world; this.cv = canvas; this.wrap = canvas.parentElement;
    this.streets = Object.fromEntries(world.streets.map(s => [s.id, s]));
    this.view = { marks: {}, focus: [], chosen: null, t: 0, trip: null, phase: 'idle', thought: '', delivered: null, color: '#ffc233' };
    this.time = 0; this.camMode = 'auto';
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 400);
    this.cam = { target: new THREE.Vector3(17, 0, 10), size: 26 };
    this.want = { target: this.cam.target.clone(), size: 26 };
    this.dir = new THREE.Vector3(Math.sin(0.62) * Math.cos(0.72), Math.sin(0.72), Math.cos(0.62) * Math.cos(0.72)).normalize();
    this.buildLights();
    this.buildStatic();
    this.buildOverlay();
    this.bindPointer();
    new ResizeObserver(() => this.resize()).observe(this.wrap);
    this.resize();
    let last = performance.now();
    const loop = now => { const dt = Math.min(0.05, (now - last) / 1000); last = now; this.time += dt; this.frame(dt); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  // ================================================================== materials & helpers
  mat(color, opts = {}) { return new THREE.MeshLambertMaterial({ color, ...opts }); }
  box(w, h, d, material, x, y, z, shadow = true) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    m.position.set(x, y, z); m.castShadow = shadow; m.receiveShadow = true; return m;
  }
  plane(w, d, material, x, y, z) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), material);
    m.rotation.x = -Math.PI / 2; m.position.set(x, y, z); m.receiveShadow = true; return m;
  }
  canvasTex(w, h, draw) {
    const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
    const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4; return t;
  }
  facade(color, kind) {
    // facade texture (one window cell) + an emissive map with lit windows for night
    const key = color + kind;
    this.facades = this.facades || {};
    if (this.facades[key]) return this.facades[key];
    const win = kind === 'glass' ? '#cfe9ff' : kind === 'shop' ? '#ffe9b0' : '#2e3b55';
    const day = this.canvasTex(64, 64, (g, w, h) => {
      g.fillStyle = color; g.fillRect(0, 0, w, h);
      g.fillStyle = 'rgba(0,0,0,0.08)'; g.fillRect(0, h - 6, w, 6);
      g.fillStyle = win; g.globalAlpha = kind === 'glass' ? 0.75 : 0.9;
      kind === 'glass' ? g.fillRect(8, 10, 48, 40) : (g.fillRect(12, 16, 16, 24), g.fillRect(36, 16, 16, 24));
      g.globalAlpha = 1; g.fillStyle = 'rgba(255,255,255,0.35)'; g.fillRect(12, 16, 4, 24);
    });
    const night = this.canvasTex(64, 64, (g, w, h) => {
      g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#ffd27a';
      kind === 'glass' ? g.fillRect(8, 10, 48, 40) : (g.fillRect(12, 16, 16, 24), g.fillRect(36, 16, 16, 24));
    });
    return (this.facades[key] = { day, night });
  }
  building(x, z, w, d, h, color, kind, roofColor) {
    const f = this.facade(color, kind);
    const side = (rw, rh) => {
      const m = this.mat(0xffffff, { map: f.day.clone(), emissiveMap: f.night.clone(), emissive: 0x000000 });
      m.map.repeat.set(Math.max(1, Math.round(rw / 0.7)), Math.max(1, Math.round(rh / 0.75))); m.map.needsUpdate = true;
      m.emissiveMap.repeat.copy(m.map.repeat); m.emissiveMap.needsUpdate = true;
      this.windowMats.push(m); return m;
    };
    const roof = this.mat(roofColor || new THREE.Color(color).multiplyScalar(0.8));
    const mats = [side(d, h), side(d, h), roof, roof, side(w, h), side(w, h)];
    const g = new THREE.Group();
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mats); b.position.y = h / 2; b.castShadow = b.receiveShadow = true; g.add(b);
    const rim = this.box(w + 0.06, 0.08, d + 0.06, this.mat(new THREE.Color(color).multiplyScalar(0.65)), 0, h + 0.04, 0); g.add(rim);
    g.position.set(x, 0.12, z); this.root.add(g); return g;
  }

  // ================================================================== lights & sky
  buildLights() {
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x88aa66, 0.65); this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xffffff, 0.85);
    this.sun.position.set(40, 60, 30); this.sun.target.position.set(17, 0, 11);
    this.sun.castShadow = true; this.sun.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sun.shadow.camera, { left: -32, right: 32, top: 32, bottom: -32, near: 1, far: 160 });
    this.sun.shadow.bias = -0.0008;
    this.scene.add(this.sun, this.sun.target);
    this.ambient = new THREE.AmbientLight(0xffffff, 0.15); this.scene.add(this.ambient);
  }

  // ================================================================== static city
  buildStatic() {
    this.root = new THREE.Group(); this.scene.add(this.root);
    this.windowMats = []; this.lampHeads = []; this.signalHeads = [];
    const W = this.w.w, H = this.w.h;
    // ground (extends past the map so there is no void at the edges)
    this.root.add(this.plane(W + 60, H + 60, this.mat(0x9bd36f), W / 2 - 0.5, -0.02, H / 2 - 0.5));
    // roads
    const asphalt = this.mat(0x464b5a), lane = this.mat(0x5d5f66), expr = this.mat(0x3c4150), side = this.mat(0x8a8f99);
    for (const s of this.w.streets) {
      const w = ROAD_W[s.kind], [a, b] = s.span, len = b - a + (s.axis === 'h' ? 0 : 0);
      const m = s.kind === 'expressway' ? expr : s.kind === 'lane' ? lane : s.kind === 'street' ? side : asphalt;
      const cx = s.axis === 'h' ? (a + b) / 2 : s.at, cz = s.axis === 'h' ? s.at : (a + b) / 2;
      this.root.add(this.plane(s.axis === 'h' ? len + w : w, s.axis === 'h' ? w : len + w, m, cx, 0.01, cz));
    }
    this.buildMarkings();
    this.buildBlocks();
    this.buildCanal();
    this.buildToll();
    this.buildSignals();
    this.buildLamps();
    this.buildLandmarks();
    // dynamic layers
    this.condLayer = new THREE.Group(); this.root.add(this.condLayer);
    this.routeLayer = new THREE.Group(); this.root.add(this.routeLayer);
    this.carLayer = new THREE.Group(); this.root.add(this.carLayer);
    this.setDelivery(1);
    this.rider = this.makeScooter(0xffc233, true); this.rider.scale.setScalar(1.9); this.root.add(this.rider);
    this.beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.45, 3.2, 16, 1, true), new THREE.MeshBasicMaterial({ color: 0xffc233, transparent: true, opacity: 0.28, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending }));
    this.marker = new THREE.Mesh(new THREE.OctahedronGeometry(0.3), new THREE.MeshBasicMaterial({ color: 0xffc233 }));
    this.root.add(this.beacon, this.marker);
    this.ring = new THREE.Mesh(new THREE.RingGeometry(0.65, 0.85, 32), new THREE.MeshBasicMaterial({ color: 0xffc233, transparent: true, opacity: 0.8, depthWrite: false }));
    this.ring.rotation.x = -Math.PI / 2; this.root.add(this.ring);
    this.buildRain();
  }

  buildMarkings() {
    const white = new THREE.MeshBasicMaterial({ color: 0xffffff }), yellow = new THREE.MeshBasicMaterial({ color: 0xffd166 });
    const cross = new Set(); this.w.nodes.forEach(n => cross.add(n.join(',')));
    const dashG = new THREE.PlaneGeometry(0.42, 0.06);
    const dashes = [];
    for (const s of this.w.streets) {
      if (s.kind === 'lane') continue;
      const [a, b] = s.span, offs = s.kind === 'expressway' ? [-0.38, 0.38] : [0];
      for (let p = a + 0.9; p < b - 0.6; p += 0.75) {
        const nearX = this.w.streets.some(o => o.axis !== s.axis && Math.abs(o.at - p) < 0.85 && o.span[0] <= s.at && o.span[1] >= s.at);
        if (nearX) continue;
        for (const o of offs) dashes.push([s.axis === 'h' ? p : s.at + o, s.axis === 'h' ? s.at + o : p, s.axis === 'h', s.kind === 'arterial' || s.kind === 'expressway' && o === 0]);
      }
    }
    const inst = new THREE.InstancedMesh(dashG, white, dashes.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
    dashes.forEach(([x, z, h], i) => { e.set(-Math.PI / 2, 0, h ? 0 : Math.PI / 2); q.setFromEuler(e); m4.compose(new THREE.Vector3(x, 0.025, z), q, new THREE.Vector3(1, 1, 1)); inst.setMatrixAt(i, m4); });
    this.root.add(inst);
    // expressway centre double yellow
    const ex = this.streets.expressway;
    if (ex) for (const o of [-0.04, 0.04]) this.root.add(this.plane(ex.span[1] - ex.span[0], 0.04, yellow, (ex.span[0] + ex.span[1]) / 2, 0.026, ex.at + o));
    // zebra crossings at signalled junctions
    const zg = new THREE.PlaneGeometry(0.12, 0.5), zebra = [];
    for (const [nx, ny] of this.w.signals) {
      const hz = this.halfAt(nx, ny, 'h') + 0.3, hx = this.halfAt(nx, ny, 'v') + 0.3;
      for (const [dx, dz, horiz] of [[0, -hz, true], [0, hz, true], [-hx, 0, false], [hx, 0, false]])
        for (let i = -3; i <= 3; i++) zebra.push([nx + dx + (horiz ? i * 0.17 : 0), ny + dz + (horiz ? 0 : i * 0.17), horiz]);
    }
    const zi = new THREE.InstancedMesh(zg, white, zebra.length);
    zebra.forEach(([x, z, h], i) => { e.set(-Math.PI / 2, 0, h ? 0 : Math.PI / 2); q.setFromEuler(e); m4.compose(new THREE.Vector3(x, 0.027, z), q, new THREE.Vector3(1, 1, 1)); zi.setMatrixAt(i, m4); });
    this.root.add(zi);
  }

  blockList() {
    const vs = this.w.streets.filter(s => s.axis === 'v'), hs = this.w.streets.filter(s => s.axis === 'h');
    const xs = [-3, ...vs.map(s => s.at), this.w.w + 2].sort((a, b) => a - b), ys = [-3, ...hs.map(s => s.at), this.w.h + 2].sort((a, b) => a - b);
    const half = (list, at) => { const s = list.find(t => t.at === at); return s ? ROAD_W[s.kind] / 2 : 0; };
    const out = [];
    for (let i = 0; i < xs.length - 1; i++) for (let j = 0; j < ys.length - 1; j++) {
      const b = { x0: xs[i], x1: xs[i + 1], y0: ys[j], y1: ys[j + 1] };
      b.ix0 = b.x0 + half(vs, b.x0) + 0.18; b.ix1 = b.x1 - half(vs, b.x1) - 0.18;
      b.iy0 = b.y0 + half(hs, b.y0) + 0.18; b.iy1 = b.y1 - half(hs, b.y1) - 0.18;
      b.kind = this.blockKind(b); out.push(b);
    }
    return out;
  }

  blockKind(b) {
    const inside = ([x, z]) => x > b.x0 && x < b.x1 && z > b.y0 && z < b.y1;
    for (const D of Object.values(this.w.deliveries)) {
      if (inside(D.rest_pos)) return 'restaurant';
      if (inside(D.cust_pos)) return 'customer';
    }
    if (b.y0 === 1 && b.y1 === 4) return 'canal';
    if (b.y1 === 1) return 'airport';
    if (b.x0 === 9 && b.y0 === 4) return 'park';
    if (b.x0 === 19 && b.y0 === 16) return 'park';
    if (b.x0 === 14 && b.y0 === 12) return 'plaza';
    if (b.x0 < 0 || b.x1 > this.w.w) return 'edge';
    if (b.y0 === 4) return 'office';
    if (b.y0 === 8) return 'mixed';
    if (b.y0 === 12 || b.y0 === 16) return 'houses';
    return 'shops';
  }

  buildBlocks() {
    const R = rng(42), walk = this.mat(0xd8d3c4), grass = this.mat(0x86c65f);
    this.trees = [];
    for (const b of this.blockList()) {
      const w = b.ix1 - b.ix0, d = b.iy1 - b.iy0, cx = (b.ix0 + b.ix1) / 2, cz = (b.iy0 + b.iy1) / 2;
      if (w <= 0.3 || d <= 0.3) continue;
      const green = ['park', 'canal', 'airport', 'edge', 'customer'].includes(b.kind);
      const slab = this.box(w, 0.12, d, green ? grass : walk, cx, 0.06, cz, false); this.root.add(slab);
      if (!green && b.kind !== 'plaza') this.root.add(this.box(w - 0.5, 0.02, d - 0.5, this.mat(0xcfc8b6), cx, 0.13, cz, false));
      const lot = { x0: b.ix0 + 0.35, x1: b.ix1 - 0.35, z0: b.iy0 + 0.35, z1: b.iy1 - 0.35 };
      if (b.kind === 'office') this.fillLots(lot, R, 'office');
      else if (b.kind === 'mixed') this.fillLots(lot, R, R() > 0.5 ? 'office' : 'shop');
      else if (b.kind === 'shops') this.fillLots(lot, R, 'shop');
      else if (b.kind === 'houses') this.fillLots(lot, R, 'house');
      else if (b.kind === 'park') this.park(b, R);
      else if (b.kind === 'plaza') this.plaza(b);
      else if (b.kind === 'airport') this.warehouses(lot, R);
      else if (b.kind === 'edge') {
        // outer neighbourhoods: small houses on the city side, trees on the outside
        const inner = b.x0 < 0 ? { ...lot, x0: Math.max(lot.x0, lot.x1 - 2.6) } : { ...lot, x1: Math.min(lot.x1, lot.x0 + 2.6) };
        if (b.y0 >= 4 && b.y1 <= 20 && inner.z1 - inner.z0 > 1) this.fillLots(inner, R, 'house');
        for (let k = 0; k < 5; k++) this.trees.push([lerp(lot.x0, lot.x1, R()), lerp(lot.z0, lot.z1, R()), 0.8 + R() * 0.4]);
      }
      // street trees along the block edges, like a tree-lined avenue
      if (!['canal', 'edge', 'airport'].includes(b.kind)) {
        for (let x = b.ix0 + 0.3; x < b.ix1 - 0.2; x += 2.2) { this.trees.push([x, b.iy0 + 0.22, 0.55]); this.trees.push([x, b.iy1 - 0.22, 0.55]); }
      }
    }
    this.countryside(R);
    this.plantTrees();
  }

  countryside(R) {
    // farm fields and woods around the city so the edges of the map are not bare grass
    const W = this.w.w, H = this.w.h, field = [0xc9e27a, 0xe4d27a, 0xa8d86a, 0xd6e89a];
    const ring = [];
    for (let x = -9; x < W + 8; x += 3.2) { ring.push([x, -6.5]); ring.push([x, H + 4.5]); }
    for (let z = -3; z < H + 4; z += 3.2) { ring.push([-8, z]); ring.push([W + 6.5, z]); }
    for (const [x, z] of ring) {
      if (R() < 0.45) { const f = this.plane(2.6, 2.6, this.mat(field[Math.floor(R() * field.length)]), x, 0.005, z); this.root.add(f);
        for (let k = 0; k < 3; k++) this.root.add(this.box(2.4, 0.03, 0.08, this.mat(0x9cbf5a), x, 0.02, z - 0.9 + k * 0.9, false)); }
      else for (let k = 0; k < 4; k++) this.trees.push([x + (R() - 0.5) * 2.6, z + (R() - 0.5) * 2.6, 0.9 + R() * 0.6]);
    }
  }

  fillLots(lot, R, style) {
    const W = lot.x1 - lot.x0, D = lot.z1 - lot.z0;
    const n = style === 'house' ? Math.max(1, Math.round(W / 1.9)) : style === 'shop' ? Math.max(1, Math.round(W / 2.6)) : 1;
    const rows = 1;
    for (let r = 0; r < rows; r++) for (let i = 0; i < n; i++) {
      const x0 = lot.x0 + i * W / n + 0.12, x1 = lot.x0 + (i + 1) * W / n - 0.12;
      const z0 = lot.z0 + r * D / rows + 0.12, z1 = lot.z0 + (r + 1) * D / rows - 0.12;
      const w = x1 - x0, d = z1 - z0, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
      if (style === 'office') {
        const pal = [['#c8553d', 'brick'], ['#e8d8b0', 'brick'], ['#5aa9c9', 'glass'], ['#9aa7b8', 'glass'], ['#d98c5f', 'brick'], ['#7fb3a6', 'glass']][Math.floor(R() * 6)];
        const h = 1.6 + R() * 2.2;
        this.building(cx, cz, Math.min(w * 0.6, 2.0), d * 0.7, h, pal[0], pal[1]);
        if (R() > 0.4) this.root.add(this.box(0.4, 0.3, 0.4, this.mat(0xb0b4bd), cx + w * 0.2, 0.12 + h + 0.15, cz - d * 0.15));
      } else if (style === 'shop') {
        const pal = ['#f08a4b', '#3f7fd6', '#c94fc6', '#f2c14e', '#2fb59a', '#e85d75'][Math.floor(R() * 6)];
        const h = 0.9 + R() * 0.6;
        this.building(cx, cz, w * 0.75, d * 0.7, h, pal, 'shop', 0x8c96a6);
        const stripes = this.canvasTex(64, 16, (g, tw, th) => { for (let k = 0; k < 8; k++) { g.fillStyle = k % 2 ? '#ffffff' : pal; g.fillRect(k * 8, 0, 8, th); } });
        const awn = new THREE.Mesh(new THREE.BoxGeometry(w * 0.75, 0.08, 0.35), this.mat(0xffffff, { map: stripes }));
        awn.position.set(cx, 0.12 + h * 0.55, cz + d * 0.35 + 0.15); awn.rotation.x = 0.35; awn.castShadow = true; this.root.add(awn);
        for (let k = 0; k < 2; k++) this.root.add(this.box(0.28, 0.18, 0.28, this.mat(0xc9ced6), cx - w * 0.2 + k * 0.45, 0.12 + h + 0.09, cz - d * 0.1));
      } else {
        const walls = ['#f6e7c8', '#fde2c0', '#efe0d0', '#f3d9b1', '#e8eef3'][Math.floor(R() * 5)];
        const roof = [0xd9534f, 0xc0643f, 0x8e5a43, 0xb5473a, 0x6d7f99, 0x3d7ea6][Math.floor(R() * 6)];
        const h = 0.6 + R() * 0.25, bw = Math.min(w, 1.2) * 0.85, bd = Math.min(d, 1.2) * 0.85;
        this.building(cx, cz, bw, bd, h, walls, 'brick', 0xffffff);
        const r = new THREE.Mesh(new THREE.CylinderGeometry(0, Math.max(bw, bd) * 0.78, 0.55, 4), this.mat(roof));
        r.rotation.y = Math.PI / 4; r.scale.set(bw / Math.max(bw, bd), 1, bd / Math.max(bw, bd)); r.position.set(cx, 0.12 + h + 0.275, cz); r.castShadow = true; this.root.add(r);
      }
    }
  }

  warehouses(lot, R) {
    const W = lot.x1 - lot.x0, cx = (lot.x0 + lot.x1) / 2, cz = (lot.z0 + lot.z1) / 2;
    if (W < 1) return;
    this.building(cx, cz, W * 0.8, Math.max(0.6, lot.z1 - lot.z0) * 0.9, 0.8, ['#9aa7b8', '#f08a4b', '#3f7fd6'][Math.floor(R() * 3)], 'shop', 0x7d8794);
  }

  park(b, R) {
    const cx = (b.ix0 + b.ix1) / 2, cz = (b.iy0 + b.iy1) / 2;
    const pond = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.0, 0.05, 24), this.mat(0x5fb7e5)); pond.scale.z = 0.6; pond.position.set(cx + 0.4, 0.13, cz); this.root.add(pond);
    this.root.add(this.box((b.ix1 - b.ix0) * 0.9, 0.02, 0.28, this.mat(0xf1e3c4), cx, 0.125, cz + 1.0, false));
    for (let k = 0; k < 9; k++) this.trees.push([lerp(b.ix0 + 0.4, b.ix1 - 0.4, R()), lerp(b.iy0 + 0.4, b.iy1 - 0.4, R()), 0.8 + R() * 0.5]);
  }

  plaza(b) {
    const cx = (b.ix0 + b.ix1) / 2, cz = (b.iy0 + b.iy1) / 2;
    this.root.add(this.box(b.ix1 - b.ix0 - 0.3, 0.03, b.iy1 - b.iy0 - 0.3, this.mat(0xe6dccb), cx, 0.13, cz, false));
    const basin = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.95, 0.2, 24), this.mat(0xcfc6b3)); basin.position.set(cx, 0.2, cz); this.root.add(basin);
    const water = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.05, 24), this.mat(0x5fb7e5)); water.position.set(cx, 0.31, cz); this.root.add(water);
    const jet = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.12, 0.7, 8), this.mat(0xbfe6ff, { transparent: true, opacity: 0.8 })); jet.position.set(cx, 0.6, cz); this.root.add(jet);
  }

  plantTrees() {
    const n = this.trees.length;
    const canopy = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.32, 0), this.mat(0x3f9b4a), n);
    const canopy2 = new THREE.InstancedMesh(new THREE.ConeGeometry(0.3, 0.7, 6), this.mat(0x2e8b57), n);
    const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.05, 0.07, 0.4, 5), this.mat(0x8b5a2b), n);
    canopy.castShadow = canopy2.castShadow = true;
    const m = new THREE.Matrix4(), hide = new THREE.Matrix4().makeScale(0, 0, 0);
    this.trees.forEach(([x, z, s], i) => {
      m.compose(new THREE.Vector3(x, 0.32, z), new THREE.Quaternion(), new THREE.Vector3(s, s, s)); trunk.setMatrixAt(i, m);
      const pine = (Math.floor(x * 7 + z * 3) % 3) === 0;
      m.compose(new THREE.Vector3(x, 0.42 + 0.32 * s, z), new THREE.Quaternion(), new THREE.Vector3(s, s, s));
      canopy.setMatrixAt(i, pine ? hide : m); canopy2.setMatrixAt(i, pine ? m : hide);
    });
    this.root.add(trunk, canopy, canopy2);
  }

  buildCanal() {
    const W = this.w.w;
    this.water = new THREE.Mesh(new THREE.PlaneGeometry(W + 6, 0.95), new THREE.MeshLambertMaterial({ color: 0x4fb3e8, transparent: true, opacity: 0.95 }));
    this.water.rotation.x = -Math.PI / 2; this.water.position.set(W / 2 - 0.5, 0.14, 2.5); this.root.add(this.water);
    for (const s of this.w.streets.filter(t => t.axis === 'v' && t.span[0] <= 2 && t.span[1] >= 3)) {
      const w = ROAD_W[s.kind];
      this.root.add(this.box(w + 0.3, 0.14, 1.3, this.mat(0xc9c2b0), s.at, 0.1, 2.5));
      this.root.add(this.box(w, 0.02, 1.3, this.mat(0x4b5060), s.at, 0.18, 2.5, false));
    }
  }

  buildToll() {
    const [[x0, z], [x1]] = this.w.toll.edge, x = (x0 + x1) / 2;
    const roof = this.box(1.0, 0.1, 2.0, this.mat(0xffd166), x, 1.0, z); this.root.add(roof);
    for (const dz of [-0.8, 0, 0.8]) this.root.add(this.box(0.25, 0.9, 0.25, this.mat(0xef476f), x, 0.5, z + dz));
    this.tollSign = this.labelSprite('TOLL 3 CU', '#1d2340', '#ffd166'); this.tollSign.position.set(x, 1.45, z); this.tollSign.scale.set(1.6, 0.4, 1); this.root.add(this.tollSign);
  }

  buildSignals() {
    const pole = this.mat(0x2b2d42);
    for (const [x, z] of this.w.signals) {
      const ox = this.halfAt(x, z, 'v') + 0.15, oz = this.halfAt(x, z, 'h') + 0.15;
      for (const [dx, dz, horiz] of [[-ox, -oz, true], [ox, oz, true], [ox, -oz, false], [-ox, oz, false]]) {
        this.root.add(this.box(0.06, 0.7, 0.06, pole, x + dx, 0.47, z + dz));
        this.root.add(this.box(0.16, 0.26, 0.16, pole, x + dx, 0.88, z + dz));
        const light = new THREE.Mesh(new THREE.SphereGeometry(0.065, 8, 6), new THREE.MeshBasicMaterial({ color: 0x2dd36f }));
        light.position.set(x + dx, 0.9, z + dz + 0.09); this.root.add(light);
        this.signalHeads.push({ mesh: light, horiz, phase: x * 0.37 + z * 0.21 });
      }
    }
  }

  halfAt(x, z, axis) {
    // half width of the street with this axis passing through intersection (x, z)
    const s = this.w.streets.find(t => t.axis === axis && t.at === (axis === 'h' ? z : x));
    return s ? ROAD_W[s.kind] / 2 : 0.4;
  }

  buildLamps() {
    const pole = this.mat(0x5b6270), spots = [];
    for (const s of this.w.streets.filter(t => ['boulevard', 'arterial', 'expressway', 'link'].includes(t.kind))) {
      const off = ROAD_W[s.kind] / 2 + 0.12;
      for (let p = s.span[0] + 1.6; p < s.span[1] - 0.5; p += 2.6) {
        const nearX = this.w.streets.some(o => o.axis !== s.axis && Math.abs(o.at - p) < 1.1 && o.span[0] <= s.at && o.span[1] >= s.at);
        if (!nearX) spots.push(s.axis === 'h' ? [p, s.at - off] : [s.at + off, p]);
      }
    }
    const poles = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.03, 0.04, 0.9, 5), pole, spots.length);
    this.lampMat = new THREE.MeshBasicMaterial({ color: 0xfff1c1 });
    const heads = new THREE.InstancedMesh(new THREE.SphereGeometry(0.08, 8, 6), this.lampMat, spots.length);
    const glowTex = this.canvasTex(64, 64, (g) => { const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, 'rgba(255,214,140,0.9)'); gr.addColorStop(1, 'rgba(255,214,140,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64); });
    this.glowMat = new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0 });
    const glows = new THREE.InstancedMesh(new THREE.PlaneGeometry(1.8, 1.8), this.glowMat, spots.length);
    const m = new THREE.Matrix4(), rot = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));
    spots.forEach(([x, z], i) => {
      m.makeTranslation(x, 0.55, z); poles.setMatrixAt(i, m);
      m.makeTranslation(x, 1.0, z); heads.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(x, 0.15, z), rot, new THREE.Vector3(1, 1, 1)); glows.setMatrixAt(i, m);
    });
    this.root.add(poles, heads, glows);
  }

  buildLandmarks() {
    this.marks = {};
    for (const [d, D] of Object.entries(this.w.deliveries)) this.marks[d] = this.buildLandmarkPair(D);
  }

  buildLandmarkPair(D) {
    const [rpx, rpz] = D.rest_pos, [cpx, cpz] = D.cust_pos;
    // restaurant: red-and-white building facing its street, with a roof sign
    const g = new THREE.Group();
    const body = this.box(2.6, 1.4, 1.9, this.mat(0xffe8c2), 0, 0.82, 0); g.add(body);
    g.add(this.box(2.7, 0.18, 2.0, this.mat(0xc0392b), 0, 1.6, 0));
    const stripes = this.canvasTex(128, 16, (c, w, h) => { for (let k = 0; k < 12; k++) { c.fillStyle = k % 2 ? '#ffffff' : '#e74c3c'; c.fillRect(k * w / 12, 0, w / 12, h); } });
    const awn = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.08, 0.6), this.mat(0xffffff, { map: stripes })); awn.position.set(0, 1.0, 1.15); awn.rotation.x = 0.4; awn.castShadow = true; g.add(awn);
    g.add(this.box(0.7, 0.8, 0.05, this.mat(0x6b3e26), 0, 0.52, 0.97));
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 0.6), new THREE.MeshBasicMaterial({ map: this.signTex(D.restaurant_name || 'Restaurant'), transparent: true }));
    sign.position.set(0, 2.05, 0.2); g.add(sign);
    g.add(this.box(0.08, 0.5, 0.08, this.mat(0x2b2d42), -0.9, 1.9, 0.1), this.box(0.08, 0.5, 0.08, this.mat(0x2b2d42), 0.9, 1.9, 0.1));
    for (let k = 0; k < 3; k++) { const sc = this.makeScooter(0xef476f, false); sc.position.set(-0.8 + k * 0.8, 0.12, 1.75); sc.rotation.y = Math.PI / 2; g.add(sc); }
    g.position.set(rpx, 0.12, rpz); g.rotation.y = Math.PI * (D.rest_turn || 0); this.root.add(g);
    if (D.rest_turn) sign.rotation.y = Math.PI;   // keep the sign readable from the camera side
    // customer: blue-roofed house with a garden fence
    const h = new THREE.Group();
    h.add(this.box(1.8, 1.0, 1.5, this.mat(0xfff3d6), 0, 0.5, 0));
    const roof = new THREE.Mesh(new THREE.CylinderGeometry(0, 1.45, 0.8, 4), this.mat(0x3b6cf6)); roof.rotation.y = Math.PI / 4; roof.scale.set(1, 1, 0.85); roof.position.y = 1.4; roof.castShadow = true; h.add(roof);
    h.add(this.box(0.4, 0.6, 0.05, this.mat(0xf6bd60), 0, 0.3, -0.77));
    for (let k = -4; k <= 4; k++) h.add(this.box(0.06, 0.3, 0.06, this.mat(0xffffff), k * 0.3, 0.15, -1.25));
    h.position.set(cpx, 0.12, cpz); this.root.add(h);
    return { sign, restPos: new THREE.Vector3(rpx, 2.9, rpz), custPos: new THREE.Vector3(cpx, 1.75, cpz) };
  }

  setDelivery(d) {
    // switch the active source -> destination: its routes, pins, sign and camera framing
    const D = this.w.deliveries[d];
    this.del = d;
    this.w.routes = D.routes; this.w.restaurant = D.restaurant; this.w.customer = D.customer;
    const m = this.marks[d];
    this.restSign = m.sign; this.restPos = m.restPos; this.custPos = m.custPos;
    this.routeLayer.clear();
    this.buildRoutes();
    const xs = [], zs = [];
    for (const r of Object.values(D.routes)) for (const [x, z] of r.path) { xs.push(x); zs.push(z); }
    xs.push(m.restPos.x, m.custPos.x); zs.push(m.restPos.z, m.custPos.z);
    this.routeBox = [Math.min(...xs) - 1.5, Math.max(...xs) + 1.5, Math.min(...zs) - 1.5, Math.max(...zs) + 1.5];
    if (this.ctl && this.camMode !== 'manual') this.setMode('auto');
  }

  signTex(text) {
    return this.canvasTex(512, 128, (g, w, h) => {
      g.fillStyle = '#1d2340'; g.beginPath(); g.roundRect ? g.roundRect(4, 4, w - 8, h - 8, 26) : g.rect(4, 4, w - 8, h - 8); g.fill();
      g.strokeStyle = '#ffd166'; g.lineWidth = 8; g.stroke();
      g.fillStyle = '#ffd166'; g.font = '800 64px Fredoka, Nunito, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(text.toUpperCase(), w / 2, h / 2 + 4, w - 40);
    });
  }

  labelSprite(text, fg, bg) {
    const t = this.canvasTex(256, 64, (g, w, h) => { g.fillStyle = bg; g.fillRect(0, 0, w, h); g.fillStyle = fg; g.font = '800 36px Nunito, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, w / 2, h / 2); });
    return new THREE.Sprite(new THREE.SpriteMaterial({ map: t }));
  }

  makeScooter(color, rider) {
    const g = new THREE.Group();
    g.add(this.box(0.5, 0.12, 0.16, this.mat(0xe9ecef), 0, 0.16, 0));
    g.add(this.box(0.24, 0.24, 0.26, this.mat(color), -0.2, 0.32, 0));
    for (const x of [-0.18, 0.2]) { const w = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.06, 10), this.mat(0x222222)); w.rotation.x = Math.PI / 2; w.position.set(x, 0.08, 0); g.add(w); }
    g.add(this.box(0.04, 0.22, 0.2, this.mat(0x444444), 0.24, 0.3, 0));
    if (rider) {
      g.add(this.box(0.16, 0.26, 0.2, this.mat(0x2b2d42), 0.02, 0.4, 0));
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 8), this.mat(color)); head.position.set(0.04, 0.62, 0); head.castShadow = true; g.add(head);
      this.riderBox = g.children[1]; this.riderHelmet = head;
    }
    g.traverse(o => { if (o.isMesh) o.castShadow = true; });
    return g;
  }

  // ================================================================== routes & conditions
  routePoints(rid) {
    const path = this.w.routes[rid].path, o = (ROUTE_ORDER.indexOf(rid) - 1.5) * 0.3;
    const pts = path.map(([x, y]) => [x, y]);
    const nrm = (a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1; return [-dy / L, dx / L]; };
    return pts.map((p, i) => {
      const n1 = i > 0 ? nrm(pts[i - 1], p) : nrm(p, pts[i + 1]), n2 = i < pts.length - 1 ? nrm(p, pts[i + 1]) : n1;
      const dot = n1[0] * n2[0] + n1[1] * n2[1];
      return [p[0] + (n1[0] + n2[0] - dot * n1[0]) * o, p[1] + (n1[1] + n2[1] - dot * n1[1]) * o];
    });
  }

  ribbon(pts, width, y) {
    const pos = [], idx = [];
    pts.forEach((p, i) => {
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      let dx = b[0] - a[0], dz = b[1] - a[1]; const L = Math.hypot(dx, dz) || 1; dx /= L; dz /= L;
      const nx = -dz * width / 2, nz = dx * width / 2;
      pos.push(p[0] + nx, y, p[1] + nz, p[0] - nx, y, p[1] - nz);
      if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
    });
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
    return g;
  }

  buildRoutes() {
    this.routes = {};
    for (const rid of ROUTE_ORDER) {
      const pts = this.routePoints(rid), col = new THREE.Color(ROUTE_COLORS[rid]);
      // expand corners so the ribbon keeps a constant width at 90-degree turns
      const dense = [];
      for (let i = 0; i < pts.length - 1; i++) { const a = pts[i], b = pts[i + 1]; dense.push(a, [lerp(a[0], b[0], 0.02), lerp(a[1], b[1], 0.02)], [lerp(a[0], b[0], 0.98), lerp(a[1], b[1], 0.98)]); }
      dense.push(pts[pts.length - 1]);
      const glow = new THREE.Mesh(this.ribbon(dense, 1.5, 0.05), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
      const casing = new THREE.Mesh(this.ribbon(dense, 0.68, 0.06), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false, side: THREE.DoubleSide }));
      const line = new THREE.Mesh(this.ribbon(dense, 0.5, 0.07), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.95, depthWrite: false, side: THREE.DoubleSide }));
      glow.renderOrder = 2; casing.renderOrder = 3; line.renderOrder = 4;
      this.routeLayer.add(glow, casing, line);
      // moving chevrons for the chosen route
      const chev = new THREE.InstancedMesh(new THREE.ConeGeometry(0.16, 0.34, 3), new THREE.MeshBasicMaterial({ color: 0xffffff }), 40);
      chev.visible = false; chev.renderOrder = 5; this.routeLayer.add(chev);
      let len = 0; const segs = [];
      for (let i = 0; i < pts.length - 1; i++) { const l = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]); segs.push([pts[i], pts[i + 1], len, l]); len += l; }
      this.routes[rid] = { glow, casing, line, chev, segs, len, pts };
    }
  }

  pointAt(r, d) {
    for (const [a, b, s, l] of r.segs) if (d <= s + l) { const k = (d - s) / l; return [lerp(a[0], b[0], k), lerp(a[1], b[1], k), Math.atan2(b[1] - a[1], b[0] - a[0])]; }
    const [a, b] = r.segs[r.segs.length - 1]; return [b[0], b[1], Math.atan2(b[1] - a[1], b[0] - a[0])];
  }

  setSituation(sit) {
    this.sit = sit;
    const rain = sit.weather === 'rain';
    this.edgeCond = this.w.edges.map(e => ({ ...e, level: sit.traffic[e.zone] || 'normal', flooded: rain && this.streets[e.street].flood_prone }));
    // congestion and flooding overlays
    this.condLayer.clear();
    this.heavyMat = new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.25, depthWrite: false });
    this.floodMat = new THREE.MeshBasicMaterial({ color: 0x4fb3e8, transparent: true, opacity: 0.6, depthWrite: false });
    this.puddles = [];
    for (const e of this.edgeCond) {
      const w = ROAD_W[this.streets[e.street].kind], horiz = e.a[1] === e.b[1];
      const cx = (e.a[0] + e.b[0]) / 2, cz = (e.a[1] + e.b[1]) / 2, L = Math.abs(e.b[0] - e.a[0]) + Math.abs(e.b[1] - e.a[1]);
      if (e.level === 'heavy') { const m = this.plane(horiz ? L - 0.6 : w + 0.25, horiz ? w + 0.25 : L - 0.6, this.heavyMat, cx, 0.03, cz); m.renderOrder = 1; this.condLayer.add(m); }
      if (e.flooded) for (let k = 0; k < Math.round(L * 1.2); k++) {
        const t = (k + 0.5) / Math.round(L * 1.2);
        const p = new THREE.Mesh(new THREE.CircleGeometry(0.42, 16), this.floodMat);
        p.rotation.x = -Math.PI / 2; p.position.set(lerp(e.a[0], e.b[0], t), 0.035, lerp(e.a[1], e.b[1], t)); p.scale.set(1.2, 0.7, 1);
        this.condLayer.add(p); this.puddles.push(p);
      }
    }
    this.spawnCars();
    this.restSign.material.map = this.signTex(sit.order.restaurant); this.restSign.material.needsUpdate = true;
    // lighting and sky per situation
    const night = sit.night, rush = sit.time_of_day === 'rush hour';
    this.scene.background = new THREE.Color(night ? SKY.night : rush ? SKY.rush : SKY.clear);
    this.hemi.intensity = night ? 0.5 : 0.65; this.hemi.color.set(night ? 0x8090d0 : 0xffffff);
    this.sun.intensity = night ? 0.35 : rush ? 0.75 : 0.85; this.sun.color.set(night ? 0x9fb0ff : rush ? 0xffb07a : 0xffffff);
    this.sun.position.set(rush ? 10 : 40, rush ? 22 : 60, rush ? 40 : 30);
    this.ambient.intensity = night ? 0.22 : 0.15;
    this.glowMat.opacity = night ? 0.85 : 0;
    this.lampMat.color.set(night ? 0xffe9a8 : 0xdedede);
    for (const m of this.windowMats) m.emissive.set(night ? 0xffffff : 0x000000);
    this.rainLines.visible = rain;
    this.water.material.color.set(night ? 0x2b5f8a : 0x4fb3e8);
  }

  spawnCars() {
    for (const c of this.cars || []) this.carLayer.remove(c.mesh);
    this.cars = [];
    const R = rng(7), night = this.sit.night;
    for (const e of this.edgeCond) {
      const kind = this.streets[e.street].kind, len = Math.abs(e.b[0] - e.a[0]) + Math.abs(e.b[1] - e.a[1]);
      const n = Math.max(e.level === 'heavy' ? 1 : 0, Math.round(DENSITY[e.level] * e.km * (kind === 'street' ? 0.5 : 1)));
      for (const dir of [1, -1]) for (let i = 0; i < n; i++) {
        const g = new THREE.Group(), col = CAR_COLORS[Math.floor(R() * CAR_COLORS.length)];
        const truck = R() > 0.88;
        if (truck) { g.add(this.box(0.62, 0.32, 0.3, this.mat(0xffffff), -0.08, 0.24, 0)); g.add(this.box(0.22, 0.26, 0.3, this.mat(col), 0.32, 0.21, 0)); }
        else { g.add(this.box(0.56, 0.16, 0.3, this.mat(col), 0, 0.15, 0)); g.add(this.box(0.3, 0.13, 0.26, this.mat(0x2f3e55), -0.04, 0.29, 0)); }
        if (night) g.add(this.box(0.04, 0.05, 0.22, new THREE.MeshBasicMaterial({ color: 0xfff3b0 }), truck ? 0.44 : 0.29, 0.16, 0));
        this.carLayer.add(g);
        this.cars.push({ mesh: g, e, dir, len, u: (i + R() * 0.5) / Math.max(1, n), v: CAR_SPEED[e.level] * (0.8 + R() * 0.4) / Math.max(1, len),
          lane: ROAD_W[kind] * (kind === 'expressway' ? (R() > 0.5 ? 0.34 : 0.16) : 0.24), stop: R() * 6 });
      }
    }
  }

  buildRain() {
    const n = 1800, pos = new Float32Array(n * 6);
    this.drops = Array.from({ length: n }, () => [Math.random() * 40 - 3, Math.random() * 14, Math.random() * 30 - 3, 0.6 + Math.random() * 0.5]);
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.rainLines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xcfe0ff, transparent: true, opacity: 0.55 }));
    this.rainLines.visible = false; this.rainLines.frustumCulled = false; this.root.add(this.rainLines);
  }

  // ================================================================== overlay (HTML labels, tooltips, camera buttons)
  buildOverlay() {
    const L = document.createElement('div'); L.className = 'map-labels'; this.wrap.appendChild(L); this.labelLayer = L;
    this.labels = {};
    const add = (key, cls, html) => { const d = document.createElement('div'); d.className = 'ml ' + cls; d.innerHTML = html; L.appendChild(d); this.labels[key] = d; return d; };
    for (const rid of ROUTE_ORDER) {
      const d = add('r' + rid, 'route-badge', `<b style="--c:${ROUTE_COLORS[rid]}">${rid}</b><i></i>`);
      d.onmouseenter = () => this.showTip(rid, d); d.onmouseleave = () => this.hideTip();
    }
    add('rest', 'pin rest', '🍴 <span>Restaurant</span>');
    add('cust', 'pin cust', '🏠 <span>Customer</span>');
    add('rider', 'rider-tag', '');
    add('bubble', 'bubble', '');
    add('done', 'bubble done', '');
    this.tipEl = add('tip', 'map-tip', '');
    const ctl = document.createElement('div'); ctl.className = 'cam-ctl';
    ctl.innerHTML = `<button data-c="auto" class="on" title="Camera follows the story automatically">🎬 Auto</button><button data-c="overview" title="Show the whole city">🗺 City</button>
      <span class="cam-sep"></span><button data-c="left" title="Move view left">◀</button><button data-c="up" title="Move view up">▲</button><button data-c="down" title="Move view down">▼</button><button data-c="right" title="Move view right">▶</button>
      <span class="cam-sep"></span><button data-c="in" title="Zoom in">＋</button><button data-c="out" title="Zoom out">－</button>`;
    ctl.onclick = e => { const b = e.target.closest('button'); if (b) this.camCommand(b.dataset.c); };
    this.wrap.appendChild(ctl); this.ctl = ctl;
  }

  camCommand(c) {
    const step = this.cv.clientHeight * 0.25;
    const dirs = { left: [step, 0], right: [-step, 0], up: [0, step], down: [0, -step] };
    if (dirs[c]) { this.panScreen(...dirs[c], true); return; }
    if (c === 'in' || c === 'out') { this.want.size = clamp(this.want.size * (c === 'in' ? 0.75 : 1.33), 5, 40); if (this.camMode === 'auto') this.setMode('manual'); return; }
    this.setMode(c === 'overview' ? 'overview' : c);
  }
  setMode(m) { this.camMode = m; this.ctl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.c === m || (m === 'overview' && b.dataset.c === 'overview'))); }

  showTip(rid, el) {
    const lines = this.tip ? this.tip(rid) : null; if (!lines) return;
    this.tipEl.innerHTML = lines.map((l, i) => i ? `<span>${esc(l)}</span>` : `<b>${esc(l)}</b>`).join('');
    this.tipEl.style.display = 'block'; this.tipFor = el;
  }
  hideTip() { this.tipEl.style.display = 'none'; this.tipFor = null; }

  panScreen(dx, dy, smooth = false) {
    // dx/dy in screen pixels: dragging right (dx > 0) moves the city right, i.e. shows more of the left side
    if (this.camMode !== 'manual') this.setMode('manual');
    const k = this.cam.size / this.cv.clientHeight;
    const right = new THREE.Vector3(this.dir.z, 0, -this.dir.x).normalize(), fwd = new THREE.Vector3(-this.dir.x, 0, -this.dir.z).normalize();
    this.want.target.addScaledVector(right, -dx * k).addScaledVector(fwd, dy * k * 1.35);
    this.want.target.x = clamp(this.want.target.x, -4, this.w.w + 3);
    this.want.target.z = clamp(this.want.target.z, -4, this.w.h + 3);
    if (!smooth) this.cam.target.copy(this.want.target);
  }

  bindPointer() {
    let drag = null;
    this.cv.addEventListener('pointerenter', () => { this.hovered = true; });
    this.cv.addEventListener('pointerleave', () => { this.hovered = false; });
    this.cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY }; this.cv.setPointerCapture(e.pointerId); });
    this.cv.addEventListener('pointermove', e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag = { x: e.clientX, y: e.clientY };
      if (Math.abs(dx) + Math.abs(dy) < 1) return;
      this.panScreen(dx, dy);
    });
    const end = () => { drag = null; };
    this.cv.addEventListener('pointerup', end); this.cv.addEventListener('pointercancel', end);
    this.cv.addEventListener('wheel', e => {
      e.preventDefault();
      const touchpadSwipe = !e.ctrlKey && (Math.abs(e.deltaX) > 0.5 || (e.deltaMode === 0 && Math.abs(e.deltaY) < 40 && !Number.isInteger(e.deltaY)));
      if (e.shiftKey || touchpadSwipe) { this.panScreen(-(e.shiftKey ? e.deltaY : e.deltaX), e.shiftKey ? 0 : -e.deltaY); return; }   // two-finger swipe = move
      this.want.size = clamp(this.want.size * (e.deltaY > 0 ? 1.12 : 0.89), 5, 40);                                        // wheel / pinch = zoom
      if (this.camMode === 'auto') this.setMode('manual');
    }, { passive: false });
    window.addEventListener('keydown', e => {
      if (!this.hovered || e.target.matches('input, select, textarea')) return;
      const step = this.cv.clientHeight * 0.12, m = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
      if (m) { e.preventDefault(); e.stopImmediatePropagation(); this.panScreen(...m, true); }
    }, true);
    this.cv.addEventListener('dblclick', () => this.setMode('auto'));
  }

  setView(v) { Object.assign(this.view, v); }

  resize() {
    const r = this.wrap.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    this.renderer.setSize(r.width, r.height, false);
    this.aspect = r.width / r.height;
    this.frame(0);
  }

  // ================================================================== per frame
  riderPose() {
    const v = this.view, trip = v.trip, [rx, rz] = this.w.restaurant;
    if (!trip) return { x: rx, z: rz + 0.0, ang: 0, wait: true };
    const t = v.t;
    if (t < trip.prep_min) return { x: rx, z: rz, ang: 0, wait: true, prep: t / trip.prep_min };
    const segs = trip.segments, o = (ROUTE_ORDER.indexOf(trip.route) - 1.5) * 0.3;
    for (const s of segs) {
      if (t <= s.end || s === segs[segs.length - 1]) {
        const k = clamp((t - s.start) / Math.max(0.001, s.drive), 0, 1), ang = Math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]);
        return { x: lerp(s.a[0], s.b[0], k) - Math.sin(ang) * o, z: lerp(s.a[1], s.b[1], k) + Math.cos(ang) * o, ang, seg: s, wait: k >= 1 && t < s.end };
      }
    }
  }

  frame(dt) {
    if (!this.sit || !this.aspect) { this.renderer.render(this.scene, this.camera); return; }
    const v = this.view, t = this.time;
    // cars
    for (const c of this.cars) {
      let sp = c.v;
      if (c.e.level === 'heavy') sp *= (Math.sin(t * 1.2 + c.stop) > 0.25 ? 1 : 0.1);
      c.u = (c.u + sp * dt) % 1;
      const k = c.dir > 0 ? c.u : 1 - c.u, ang = Math.atan2((c.e.b[1] - c.e.a[1]) * c.dir, (c.e.b[0] - c.e.a[0]) * c.dir);
      const nx = -Math.sin(ang), nz = Math.cos(ang);
      c.mesh.position.set(lerp(c.e.a[0], c.e.b[0], k) + nx * c.lane, 0.02, lerp(c.e.a[1], c.e.b[1], k) + nz * c.lane);
      c.mesh.rotation.y = -ang;
    }
    // signals
    for (const s of this.signalHeads) {
      const ph = (t + s.phase) % 8, amber = (ph > 3.6 && ph < 4.2) || ph > 7.6, green = (ph < 3.6) === s.horiz;
      s.mesh.material.color.set(amber ? 0xffbe0b : green ? 0x2dd36f : 0xff3b30);
    }
    if (this.heavyMat) this.heavyMat.opacity = 0.22 + 0.08 * Math.sin(t * 3);
    for (const [i, p] of (this.puddles || []).entries()) p.scale.set(1.2 + 0.1 * Math.sin(t * 2 + i), 0.7, 1);
    // routes
    const chosen = v.chosen;
    for (const rid of ROUTE_ORDER) {
      const r = this.routes[rid], m = chosen === rid ? 'chosen' : (v.marks[rid] || (chosen ? 'faded' : 'normal'));
      const pulse = 0.5 + 0.5 * Math.sin(t * 6), focus = v.focus.includes(rid);
      const col = new THREE.Color(m === 'unknown' ? '#8b90a8' : ROUTE_COLORS[rid]);
      r.line.material.color.copy(col); r.glow.material.color.copy(col);
      r.line.material.opacity = { chosen: 1, rejected: 0.35, unknown: 0.6, faded: 0.25, candidate: 1, checking: 1, normal: 0.95 }[m] ?? 0.95;
      r.casing.material.opacity = { rejected: 0.3, faded: 0.2, unknown: 0.5 }[m] ?? 0.9;
      r.glow.material.opacity = m === 'chosen' ? 0.45 : (m === 'checking' || (focus && m !== 'normal' && m !== 'rejected')) ? 0.2 + 0.25 * pulse : 0;
      r.line.scale.y = 1;
      r.chev.visible = m === 'chosen';
      if (r.chev.visible) {
        const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), n = r.chev.count;
        for (let i = 0; i < n; i++) {
          const d = ((i / n) * r.len + t * 2.2) % r.len, [x, z, ang] = this.pointAt(r, d);
          q.setFromEuler(new THREE.Euler(0, -ang, -Math.PI / 2));
          m4.compose(new THREE.Vector3(x, 0.1, z), q, new THREE.Vector3(1, 1, 1)); r.chev.setMatrixAt(i, m4);
        }
        r.chev.instanceMatrix.needsUpdate = true;
      }
    }
    // rider
    const p = this.riderPose();
    const col = new THREE.Color(v.color || '#ffc233');
    if (this.riderBox) this.riderBox.material.color.copy(col);
    if (this.riderHelmet) this.riderHelmet.material.color.copy(col);
    this.rider.position.set(p.x, 0.04 + (p.wait && !v.trip ? 0 : Math.abs(Math.sin(t * 14)) * 0.015), p.z);
    this.rider.rotation.y = -p.ang;
    this.ring.position.set(p.x, 0.08, p.z); this.ring.material.color.copy(col);
    this.beacon.position.set(p.x, 1.6, p.z); this.beacon.material.color.copy(col);
    this.marker.position.set(p.x, 3.4 + 0.15 * Math.sin(t * 3), p.z); this.marker.rotation.y = t * 2; this.marker.material.color.copy(col);
    const sc = 1 + 0.15 * Math.sin(t * 5); this.ring.scale.set(sc, sc, sc);
    // rain
    if (this.rainLines.visible) {
      const a = this.rainLines.geometry.attributes.position.array, tx = this.cam.target.x, tz = this.cam.target.z;
      this.drops.forEach((d, i) => {
        d[1] -= dt * 14 * d[3]; if (d[1] < 0) { d[1] = 14; d[0] = tx - 22 + Math.random() * 44; d[2] = tz - 18 + Math.random() * 36; }
        a.set([d[0], d[1], d[2], d[0] + 0.08, d[1] - 0.45, d[2] + 0.05], i * 6);
      });
      this.rainLines.geometry.attributes.position.needsUpdate = true;
    }
    this.updateCamera(dt, p);
    this.renderer.render(this.scene, this.camera);
    this.updateLabels(p);
  }

  updateCamera(dt, p) {
    const v = this.view, mode = this.camMode;
    const riding = v.trip && ['act', 'respond', 'result'].includes(v.phase);
    if (mode === 'auto') {
      if (riding) { this.want.target.set(p.x, 0, p.z); this.want.size = v.phase === 'act' ? 11 : 13; }
      else { const [x0, x1, z0, z1] = this.routeBox; this.want.target.set((x0 + x1) / 2, 0, (z0 + z1) / 2); this.want.size = this.fitSize(); }
    } else if (mode === 'overview') { this.want.target.set(16.5, 0, 11); this.want.size = this.fitSize(true); }
    else if (mode === 'follow') { this.want.target.set(p.x, 0, p.z); }
    const k = dt ? 1 - Math.exp(-dt * 3) : 1;
    this.cam.target.lerp(this.want.target, k); this.cam.size = lerp(this.cam.size, this.want.size, k);
    const s = this.cam.size / 2;
    Object.assign(this.camera, { left: -s * this.aspect, right: s * this.aspect, top: s, bottom: -s });
    this.camera.position.copy(this.cam.target).addScaledVector(this.dir, 80);
    this.camera.lookAt(this.cam.target); this.camera.updateProjectionMatrix();
  }

  fitSize(all) {
    // vertical extent needed to show the routes (or the whole city) at this aspect ratio
    const [x0, x1, z0, z1] = this.routeBox || [2, 31, 0, 17.5];
    const pts = all ? [[-1, -1], [34, -1], [-1, 23], [34, 23]] : [[x0, z0], [x1, z0], [x0, z1], [x1, z1]];
    const cx = all ? 16.5 : (x0 + x1) / 2, cz = all ? 11 : (z0 + z1) / 2;
    const cam = this.camera.clone(); cam.position.set(cx, 0, cz).addScaledVector(this.dir, 80); cam.lookAt(cx, 0, cz); cam.updateMatrixWorld();
    const inv = cam.matrixWorldInverse; let mx = 0, my = 0;
    for (const [x, z] of pts) for (const y of [0, 1.5]) { const q = new THREE.Vector3(x, y, z).applyMatrix4(inv); mx = Math.max(mx, Math.abs(q.x)); my = Math.max(my, Math.abs(q.y)); }
    return Math.max(my * 2, (mx * 2) / this.aspect) * 1.04;
  }

  project(x, y, z) {
    const q = new THREE.Vector3(x, y, z).project(this.camera);
    return [(q.x + 1) / 2 * this.cv.clientWidth, (1 - q.y) / 2 * this.cv.clientHeight];
  }

  updateLabels(p) {
    const v = this.view, L = this.labels, W = this.cv.clientWidth;
    const place = (el, x, y, z) => {
      let [sx, sy] = this.project(x, y, z);
      if (el.classList.contains('bubble') || el.classList.contains('rider-tag')) { const half = Math.min(el.offsetWidth, W) / 2 + 8; sx = clamp(sx, half, W - half); }
      el.style.transform = `translate(${sx}px, ${sy}px)`;
    };
    const mi = this.del === 2 ? { A: 3, B: 1, C: 3, D: 2 } : { A: 2, B: 5, C: 3, D: 6 };
    for (const rid of ROUTE_ORDER) {
      const r = this.routes[rid], [a, b] = [r.pts[mi[rid]], r.pts[mi[rid] + 1]], el = L['r' + rid];
      place(el, (a[0] + b[0]) / 2, 0.3, (a[1] + b[1]) / 2);
      const m = v.chosen === rid ? 'chosen' : v.marks[rid] || (v.chosen ? 'faded' : '');
      el.className = 'ml route-badge ' + m;
      el.querySelector('i').textContent = { chosen: '✓', rejected: '✕', unknown: '?', checking: '…' }[m] || '';
    }
    place(L.rest, this.restPos.x, this.restPos.y, this.restPos.z);
    L.rest.querySelector('span').textContent = this.sit.order.restaurant;
    place(L.cust, this.custPos.x, this.custPos.y, this.custPos.z);
    const thinking = ['observe', 'reason', 'decide'].includes(v.phase);
    L.rider.style.display = thinking ? 'none' : 'block';
    L.rider.style.setProperty('--c', v.color); L.rider.textContent = '🛵 ' + (v.riderName || 'Rider') + ' agent'; place(L.rider, p.x, 3.9, p.z);
    let text = '', cls = 'bubble';
    if (thinking && v.thought) { text = '💭 ' + v.thought; cls += ' think'; }
    else if (v.phase === 'act' && p.prep !== undefined) text = `👨‍🍳 Waiting for the food… ${Math.round(p.prep * 100)}%`;
    else if (p.seg && p.seg.incident && v.t > p.seg.start && v.t < p.seg.end) { text = '⚠ ' + p.seg.incident.split(' (')[0]; cls += ' warn'; }
    else if (p.wait && v.trip && v.phase === 'act') { text = '🚦 Red light'; }
    L.bubble.style.display = text ? 'block' : 'none';
    if (text) { L.bubble.className = 'ml ' + cls; L.bubble.textContent = text; place(L.bubble, p.x, 4.5, p.z); }
    if (v.delivered) {
      L.done.style.display = 'block'; L.done.className = 'ml bubble done ' + (v.delivered.on_time ? 'ok' : 'late');
      L.done.textContent = v.delivered.on_time ? '🎉 Delivered on time!' : `⏰ Late by ${v.delivered.late_min.toFixed(1)} min`;
      place(L.done, this.custPos.x, this.custPos.y + 1.6, this.custPos.z);
    } else L.done.style.display = 'none';
    if (this.tipFor) { const r = this.tipFor.getBoundingClientRect(), w = this.wrap.getBoundingClientRect(); this.tipEl.style.transform = `translate(${Math.min(r.left - w.left + 24, w.width - 300)}px, ${r.top - w.top + 24}px)`; }
  }
}
