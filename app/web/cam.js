// cam.js: the player camera (2026-10-27). A 3D view from one player's (or the referee's) eyes,
// made from the same 1 Hz tracking the pitch uses, and in step with the replay clock.
//
//   - Players are capsules in their kit colors with their shirt number above them; the officials
//     are yellow. The ball is drawn at its height from the flights (ballZ in app.js).
//   - By default the head follows the ball. Hold the middle mouse button (or the left button) and
//     move the mouse to turn the head; the turn stays until "Look at the ball". The arrow keys do
//     the same when the view has focus. The mouse wheel zooms (field of view), and never scrolls
//     the page while the pointer is over the view.
//   - three.js (MIT, r149, app/web/vendor) loads only when the camera opens.
//
// app.js keeps its code private, so it calls makeCam with what the camera needs (S, $, TXT,
// cssColor, ballZ, offPitch, OFFICIAL_MARK) and gets back open(id), close(), frame() and words().
window.makeCam = (D) => {
  const { S, $, TXT, cssColor, ballZ, offPitch, OFFICIAL_MARK } = D;
  const W = {
    en: { player: 'Player camera', ref: 'Referee camera', ball: 'Look at the ball', close: 'Close',
          hint: 'Hold the middle mouse button (or the left button) and move the mouse to turn his head. Arrow keys work too. Scroll to zoom. A simulation from the tracking data: players are capsules.',
          hud: (n, kmh, d) => `${n}  ·  ${kmh} km/h  ·  ball ${d} m away`, loading: 'Loading the 3D view...',
          fail: 'The 3D view needs WebGL, which this browser has turned off.', watch: (n) => `Player camera: ${n}`, refBtn: 'Referee camera',
          aria: (n) => `3D view from ${n}'s eyes. Arrow keys turn the head.` },
    es: { player: 'Cámara del jugador', ref: 'Cámara del árbitro', ball: 'Mirar al balón', close: 'Cerrar',
          hint: 'Mantenga pulsado el botón central del ratón (o el izquierdo) y mueva el ratón para girar la cabeza. También con las flechas. La rueda acerca la vista. Simulación a partir del seguimiento: los jugadores son cápsulas.',
          hud: (n, kmh, d) => `${n}  ·  ${kmh} km/h  ·  balón a ${d} m`, loading: 'Cargando la vista 3D...',
          fail: 'La vista 3D necesita WebGL, que este navegador tiene desactivado.', watch: (n) => `Cámara de ${n}`, refBtn: 'Cámara del árbitro',
          aria: (n) => `Vista 3D desde los ojos de ${n}. Las flechas giran la cabeza.` },
  };
  const EYE = 1.7, BALL_R = 0.17;                  // eye height; the ball is drawn 1.5x its real size so it reads at distance
  const st = { open: false, id: null, three: null, look: { yaw: 0, pitch: 0 }, head: null, drag: null, fov: 70, last: 0 };
  const w = () => W[S.lang] || W.en;
  const X = (x) => x - 52.5, Z = (y) => y - 34;     // pitch metres to the 3D world (y up)

  function loadThree() {
    if (window.THREE) return Promise.resolve();
    return new Promise((ok, bad) => {
      const s = document.createElement('script'); s.src = 'vendor/three.min.js'; s.onload = ok; s.onerror = bad; document.head.append(s);
    });
  }
  function label(text, bg, fg) {                    // a number or a letter above a head
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    g.fillStyle = bg; g.beginPath(); g.arc(32, 32, 30, 0, Math.PI * 2); g.fill();
    g.fillStyle = fg; g.font = '800 34px "Barlow Condensed", "Arial Narrow", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text, 32, 34);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthWrite: false }));
    sp.scale.set(0.55, 0.55, 1); return sp;
  }
  function strip(scene, mat, x1, y1, x2, y2) {        // a pitch line as a thin flat strip, so it reads in perspective
    const len = Math.hypot(x2 - x1, y2 - y1), m = new THREE.Mesh(new THREE.PlaneGeometry(len, 0.12), mat);
    m.rotation.x = -Math.PI / 2; m.rotation.z = -Math.atan2(y2 - y1, x2 - x1);
    m.position.set(X((x1 + x2) / 2), 0.012, Z((y1 + y2) / 2)); scene.add(m);
  }
  function rect(scene, mat, x, y, wd, h) {
    strip(scene, mat, x, y, x + wd, y); strip(scene, mat, x + wd, y, x + wd, y + h);
    strip(scene, mat, x + wd, y + h, x, y + h); strip(scene, mat, x, y + h, x, y);
  }
  function build() {
    const T = S.track, canvas = $('cam-canvas');
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0b0f1c'); scene.fog = new THREE.Fog('#0b0f1c', 70, 160);
    scene.add(new THREE.HemisphereLight('#dfe8ff', '#1b3a26', 0.9));
    const sun = new THREE.DirectionalLight('#ffffff', 0.7); sun.position.set(-30, 60, 20); scene.add(sun);
    // The pitch, its mowing stripes, the lines and the goals.
    const grass = new THREE.Mesh(new THREE.PlaneGeometry(125, 88), new THREE.MeshLambertMaterial({ color: '#1f5c3a' }));
    grass.rotation.x = -Math.PI / 2; scene.add(grass);
    const stripeMat = new THREE.MeshLambertMaterial({ color: '#246842' });
    for (let k = 1; k < 12; k += 2) {
      const s = new THREE.Mesh(new THREE.PlaneGeometry(105 / 12, 68), stripeMat);
      s.rotation.x = -Math.PI / 2; s.position.set(X(k * 105 / 12 + 105 / 24), 0.005, 0); scene.add(s);
    }
    const line = new THREE.MeshBasicMaterial({ color: '#e9efe9' });
    rect(scene, line, 0, 0, 105, 68); strip(scene, line, 52.5, 0, 52.5, 68);
    rect(scene, line, 0, 13.84, 16.5, 40.32); rect(scene, line, 88.5, 13.84, 16.5, 40.32);
    rect(scene, line, 0, 24.84, 5.5, 18.32); rect(scene, line, 99.5, 24.84, 5.5, 18.32);
    const ring = new THREE.Mesh(new THREE.RingGeometry(9.09, 9.21, 96), line); ring.rotation.x = -Math.PI / 2; ring.position.y = 0.012; scene.add(ring);
    for (const x of [11, 52.5, 94]) { const d = new THREE.Mesh(new THREE.CircleGeometry(0.18, 16), line); d.rotation.x = -Math.PI / 2; d.position.set(X(x), 0.013, 0); scene.add(d); }
    const post = new THREE.MeshLambertMaterial({ color: '#ffffff' }), net = new THREE.MeshBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0.12, side: THREE.DoubleSide });
    for (const [gx, back] of [[0, -1.6], [105, 1.6]]) {
      for (const gy of [30.34, 37.66]) { const p = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.44, 10), post); p.position.set(X(gx), 1.22, Z(gy)); scene.add(p); }
      const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 7.32, 10), post); bar.rotation.x = Math.PI / 2; bar.position.set(X(gx), 2.44, 0); scene.add(bar);
      const n = new THREE.Mesh(new THREE.PlaneGeometry(7.32, 2.44), net); n.rotation.y = Math.PI / 2; n.position.set(X(gx) + back, 1.22, 0); scene.add(n);
    }
    // A plain stadium for a sense of place: advertising boards with a lime edge, then four stands.
    const board = new THREE.MeshLambertMaterial({ color: '#1a1726' }), edge = new THREE.MeshBasicMaterial({ color: '#c6f432' });
    const stand = new THREE.MeshLambertMaterial({ color: '#262b3d' });
    for (const sgn of [-1, 1]) {
      const b1 = new THREE.Mesh(new THREE.BoxGeometry(111, 0.9, 0.12), board); b1.position.set(0, 0.45, sgn * 38); scene.add(b1);
      const e1 = new THREE.Mesh(new THREE.BoxGeometry(111, 0.06, 0.14), edge); e1.position.set(0, 0.9, sgn * 38); scene.add(e1);
      const b2 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.9, 60), board); b2.position.set(sgn * 58, 0.45, 0); scene.add(b2);
      const e2 = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.06, 60), edge); e2.position.set(sgn * 58, 0.9, 0); scene.add(e2);
      const s1 = new THREE.Mesh(new THREE.BoxGeometry(130, 14, 18), stand); s1.position.set(0, 4, sgn * 50); s1.rotation.x = sgn * 0.45; scene.add(s1);
      const s2 = new THREE.Mesh(new THREE.BoxGeometry(18, 14, 100), stand); s2.position.set(sgn * 70, 4, 0); s2.rotation.z = -sgn * 0.45; scene.add(s2);
    }
    // Players: capsules 1.8 m tall in the kit color (a keeper is lighter), the number above.
    const kit = { home: cssColor('--home'), away: cssColor('--away') };
    // A figure: a group at the feet, so it can face where it runs, lean into a run and bob with
    // each stride. The capsule is the body; a darker band at the front of the head shows which
    // way he faces; the shorts are a darker band at the hips.
    const shade = new THREE.MeshLambertMaterial({ color: '#15121f' });
    function figure(color, r, len) {
      const g = new THREE.Group(), mat = new THREE.MeshLambertMaterial({ color });
      const body = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 4, 14), mat); body.position.y = len / 2 + r; g.add(body);
      const face = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.13, 0.3), shade); face.position.set(r - 0.02, len + r + 0.1, 0); g.add(face);
      const hips = new THREE.Mesh(new THREE.CylinderGeometry(r + 0.012, r + 0.012, 0.22, 14), shade); hips.position.y = 0.78; g.add(hips);
      scene.add(g); return { g, mat };
    }
    const people = T.players.map((p) => {
      const color = new THREE.Color(kit[p.team]); if (p.goalkeeper) color.lerp(new THREE.Color('#ffffff'), 0.45);
      const f = figure(color, 0.33, 1.14);
      const tag = label(String(p.number), kit[p.team], cssColor(`--${p.team}-on`) || '#ffffff');
      scene.add(tag); return { body: f.g, mat: f.mat, tag, id: p.id, yaw: 0, phase: 0, v: [0, 0], px: null, py: null };
    });
    const officials = (T.officials || []).map((o) => {
      const f = figure(new THREE.Color('#e8d23a'), 0.31, 1.12);
      const tag = label(OFFICIAL_MARK[o.id] || '?', '#e8d23a', '#0e0c16');
      scene.add(tag); return { body: f.g, mat: f.mat, tag, id: o.id, yaw: 0, phase: 0, v: [0, 0], px: null, py: null };
    });
    const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 20, 14), new THREE.MeshLambertMaterial({ color: '#ffffff', emissive: '#555555' }));
    const shadow = new THREE.Mesh(new THREE.CircleGeometry(0.22, 16), new THREE.MeshBasicMaterial({ color: '#000000', transparent: true, opacity: 0.45 }));
    shadow.rotation.x = -Math.PI / 2; scene.add(ball, shadow);
    const camera = new THREE.PerspectiveCamera(st.fov, 16 / 9, 0.1, 400);
    st.three = { renderer, scene, camera, people, officials, ball, shadow, kitKey: `${kit.home}|${kit.away}` };
  }
  function recolor() {                               // the viewer changed a kit color
    const kit = { home: cssColor('--home'), away: cssColor('--away') }, key = `${kit.home}|${kit.away}`;
    if (!st.three || st.three.kitKey === key) return;
    st.three.kitKey = key;
    S.track.players.forEach((p, i) => {
      const c = new THREE.Color(kit[p.team]); if (p.goalkeeper) c.lerp(new THREE.Color('#ffffff'), 0.45);
      st.three.people[i].mat.color = c;
    });
  }
  function who(id) {
    const T = S.track, i = T.players.findIndex((p) => p.id === id);
    if (i >= 0) { const p = T.players[i]; return { slot: 2 + 2 * i, name: `${p.number} ${p.name}`, idx: i, official: false }; }
    const j = (T.officials || []).findIndex((o) => o.id === id);
    return j >= 0 ? { slot: 46 + 2 * j, name: TXT[S.lang].officialName[id] || id, idx: j, official: true } : null;
  }
  function size() {
    const wd = $('cam-canvas').clientWidth, h = Math.round(wd * 9 / 16);
    if (st.three && wd > 0 && st.size !== wd) {
      st.size = wd; st.three.renderer.setSize(wd, h, false); st.three.camera.aspect = wd / h; st.three.camera.updateProjectionMatrix();
    }
  }
  function frame() {
    if (!st.open || !st.three || !S.track || !S.motion) return;
    const T = S.track, me = who(st.id); if (!me) return;
    // Positions from motion.js: smooth curves, the ball at its exact touches, nobody faster than a sprint.
    const M = S.motion, C = M.live(S.t), at = (k) => C[k];
    const { people, officials, ball, shadow, camera, renderer, scene } = st.three;
    recolor(); size();
    const now = performance.now(), dt = Math.min(0.1, (now - (st.last || now)) / 1000); st.last = now;
    const dSim = Math.max(0, Math.min(1.0, S.t - (st.lastT ?? S.t))); st.lastT = S.t;
    const bxm = at(0), bym = at(1);
    // Velocity from the drawn positions over match time (so it does not depend on the replay
    // speed), smoothed; paused, it keeps the last value.
    function velocity(o, x, y) {
      if (o.px == null || dSim <= 0 || dSim > 0.99) { if (o.px == null || dSim > 0.99) o.v = [0, 0]; }
      else { const k = Math.min(1, dSim / 0.25); o.v = [o.v[0] + ((x - o.px) / dSim - o.v[0]) * k, o.v[1] + ((y - o.py) / dSim - o.v[1]) * k]; }
      o.px = x; o.py = y; return o.v;
    }
    // Face where he runs; standing, face the ball. Lean into a run; bob once a stride.
    function pose(o, k, height) {
      const x = at(k), y = at(k + 1), [vx, vy] = velocity(o, x, y), sp = Math.hypot(vx, vy);
      const want = sp > 1.2 ? Math.atan2(vy, vx) : Math.atan2(bym - y, bxm - x);
      const turn = Math.atan2(Math.sin(want - o.yaw), Math.cos(want - o.yaw));
      o.yaw += turn * Math.min(1, dt * 7);
      o.phase += dSim * Math.PI * (1.6 + 0.35 * sp);
      const bob = sp > 0.5 ? Math.min(0.07, 0.01 * sp) * Math.abs(Math.sin(o.phase)) : 0;
      o.body.position.set(X(x), bob, Z(y));
      o.body.rotation.set(0, -o.yaw, -Math.min(0.16, sp * 0.02));
      o.tag.position.set(X(x), height + bob, Z(y));
      return { sp, bob };
    }
    const meK = me.slot, mine = { sp: 0, bob: 0 };
    T.players.forEach((p, i) => {
      const o = people[i], gone = offPitch(p);
      const isMe = !me.official && i === me.idx;
      o.body.visible = o.tag.visible = !gone && !isMe;
      if (gone) return;
      const r = pose(o, 2 + 2 * i, 2.15);
      if (isMe) Object.assign(mine, r);
      else o.tag.visible = Math.hypot(at(2 + 2 * i) - at(meK), at(3 + 2 * i) - at(meK + 1)) > 4;   // a number right in front of the eyes would fill the view
    });
    officials.forEach((o, j) => {
      const isMe = me.official && j === me.idx; o.body.visible = o.tag.visible = !isMe;
      const r = pose(o, 46 + 2 * j, 2.1);
      if (isMe) Object.assign(mine, r);
    });
    const bz = ballZ(S.t), bx = X(bxm), bzz = Z(bym);
    ball.position.set(bx, BALL_R + bz, bzz); shadow.position.set(bx, 0.015, bzz);
    // The eyes: the player's position at eye height, with his stride's bob. The head follows the
    // ball, smoothly, plus the viewer's own turn (yaw left and right, pitch up and down).
    const ex = X(at(meK)), ez = Z(at(meK + 1)), eye = EYE + mine.bob * 0.6;
    camera.position.set(ex, eye, ez);
    const dx = bx - ex, dz = bzz - ez, dist = Math.hypot(dx, dz);
    // With the ball at his feet, the head keeps its direction and looks a little down.
    const near = dist < 1.5 && st.head;
    const yawBall = near ? st.head.yaw : Math.atan2(dz, dx), pitchBall = near ? -0.35 : Math.atan2(BALL_R + bz - eye, Math.max(dist, 0.5));
    if (!st.head) st.head = { yaw: yawBall, pitch: pitchBall };
    const k = Math.min(1, dt * 5), dy = Math.atan2(Math.sin(yawBall - st.head.yaw), Math.cos(yawBall - st.head.yaw));
    st.head.yaw += dy * k; st.head.pitch += (pitchBall - st.head.pitch) * k;
    const yaw = st.head.yaw + st.look.yaw, pitch = Math.max(-1.2, Math.min(1.2, st.head.pitch + st.look.pitch));
    camera.lookAt(ex + Math.cos(yaw) * Math.cos(pitch), eye + Math.sin(pitch), ez + Math.sin(yaw) * Math.cos(pitch));
    if (camera.fov !== st.fov) { camera.fov = st.fov; camera.updateProjectionMatrix(); }
    renderer.render(scene, camera);
    // The lower third: who, his speed this second, how far the ball is.
    const hud = w().hud(me.name, Math.round(mine.sp * 3.6), Math.round(Math.hypot(dist, bz)));
    if ($('cam-hud').textContent !== hud) $('cam-hud').textContent = hud;
  }
  let wordsKey = '';
  function words() {
    const key = `${S.lang}|${st.open}|${st.id}|${S.pick ? S.pick.value : ''}|${S.trackState}`;
    if (key === wordsKey) return;
    wordsKey = key;
    const t = w(), me = st.open && S.track ? who(st.id) : null;
    $('cam-title').textContent = me && me.official ? t.ref : t.player;
    $('cam-ball').textContent = t.ball; $('cam-close').textContent = t.close; $('cam-hint').textContent = t.hint;
    if (me) $('cam-canvas').setAttribute('aria-label', t.aria(me.name));
    $('cam-ref').textContent = t.refBtn;
    const m = S.pick && S.moment, p = m && S.track ? S.track.players.find((x) => x.name === m.actor) : null;
    $('cam-player').hidden = !p; $('cam-ref').hidden = !m || !S.track;
    if (p) { $('cam-player').textContent = t.watch(`${p.number} ${p.name}`); $('cam-player').dataset.id = p.id; }
  }
  async function open(id) {
    if (!S.track || S.trackState !== 'ready') return;
    st.id = id; st.look = { yaw: 0, pitch: 0 }; st.head = null; st.open = true;
    $('cam').hidden = false; words();
    $('cam-hud').textContent = w().loading;
    try { await loadThree(); if (!st.three) build(); }
    catch (e) { $('cam-hud').textContent = w().fail; return; }
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    $('cam').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' });
  }
  function close() { st.open = false; $('cam').hidden = true; }
  // Turning the head: middle (or left) button held, then move. The middle button would start the
  // browser's auto-scroll, so its default is stopped.
  const c = () => $('cam-canvas');
  function setup() {
    c().addEventListener('pointerdown', (e) => {
      if (e.button !== 1 && e.button !== 0) return;
      e.preventDefault(); c().setPointerCapture(e.pointerId); st.drag = { x: e.clientX, y: e.clientY }; c().classList.add('turning');
    });
    c().addEventListener('pointermove', (e) => {
      if (!st.drag) return;
      const k = (st.fov / 70) * 0.005;
      st.look.yaw += (e.clientX - st.drag.x) * k; st.look.pitch -= (e.clientY - st.drag.y) * k;
      st.look.pitch = Math.max(-1.2, Math.min(1.2, st.look.pitch)); st.drag = { x: e.clientX, y: e.clientY };
    });
    const end = () => { st.drag = null; c().classList.remove('turning'); };
    c().addEventListener('pointerup', end); c().addEventListener('pointercancel', end);
    c().addEventListener('mousedown', (e) => { if (e.button === 1) e.preventDefault(); });   // no auto-scroll
    c().addEventListener('auxclick', (e) => { if (e.button === 1) e.preventDefault(); });
    c().addEventListener('wheel', (e) => { e.preventDefault(); st.fov = Math.max(25, Math.min(95, st.fov * (e.deltaY < 0 ? 1 / 1.1 : 1.1))); }, { passive: false });
    c().addEventListener('keydown', (e) => {
      const step = 0.08, map = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
      if (!map[e.key]) return;
      e.preventDefault(); st.look.yaw += map[e.key][0]; st.look.pitch = Math.max(-1.2, Math.min(1.2, st.look.pitch + map[e.key][1]));
    });
    $('cam-ball').addEventListener('click', () => { st.look = { yaw: 0, pitch: 0 }; st.fov = 70; });
    $('cam-close').addEventListener('click', close);
    $('cam-player').addEventListener('click', () => open($('cam-player').dataset.id));
    $('cam-ref').addEventListener('click', () => open('ref'));
  }
  setup();
  return { open, close, frame, words, get isOpen() { return st.open; }, get id() { return st.id; } };
};
