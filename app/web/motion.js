// motion.js: smooth movement between the 1 Hz tracking frames (2026-10-27).
//
// The tracking has one position a second for each player. Drawn as straight lines, every player
// turns sharply once a second, and the ball skips the touches that happen between two seconds
// (about 4 in 10 touches). This module samples the match at any time instead:
//
//   ball     moves from touch to touch at the exact event times (track.touches, from the
//            events): a struck ball slows as it arrives; a run with the ball moves at dribbling
//            speed. The height still comes from the flights (ballZ in app.js).
//   players  follow a smooth curve through their 1 Hz positions (a Catmull-Rom spline), and are
//            drawn to the ball when they play it or receive it: a receiver starts to move to the
//            spot as early as he needs (about 3.5 m/s on top of his own movement), stands just
//            behind the ball when he plays it, keeps it at his feet between his own touches, and
//            eases back to his place afterwards at the same pace.
//   officials follow the smooth curve only.
//
// The offside line and the offside rings still use the 1 Hz frames, so every offside decision
// stays exactly as the events record it. frame(t) returns positions in metres, in the frame
// order: [ball x, ball y, x and y for each of the 22 players, x and y for each official].
window.makeMotion = (track) => {
  const F = track.frames, N = F.length - 1, NP = track.players.length, NV = F[0].length;
  const K = track.touches || [];
  const KT = K.map((k) => k[0]);
  const mine = Array.from({ length: NP }, () => []);       // per player: indexes into K
  K.forEach((k, i) => { if (k[3] >= 0 && k[3] < NP) mine[k[3]].push(i); });
  const mineT = mine.map((list) => list.map((i) => K[i][0]));
  const FEET = 0.45;                                       // the ball is this far in front of him
  const REL = 3.5;                                         // average m/s on top of his own movement, to reach the
                                                           // spot or get back to his place (peaks at about 1.5x)

  function search(arr, t) {                                // last index with arr[i] <= t, or -1
    let lo = 0, hi = arr.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
    return k;
  }
  function spline(k, t) {                                  // value k (decimetres) at time t, in metres
    const f = Math.max(0, Math.min(N, Math.floor(t))), u = Math.max(0, Math.min(1, t - f));
    const p0 = F[Math.max(0, f - 1)][k], p1 = F[f][k], p2 = F[Math.min(N, f + 1)][k], p3 = F[Math.min(N, f + 2)][k];
    const v = 0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u);
    return v / 10;
  }
  const smooth = (x) => { const c = Math.max(0, Math.min(1, x)); return c * c * (3 - 2 * c); };
  function ballAt(t) {
    if (!K.length) return [spline(0, t), spline(1, t)];
    const i = search(KT, t);
    if (i < 0) return [K[0][1], K[0][2]];
    if (i >= K.length - 1) return [K[i][1], K[i][2]];
    const a = K[i], b = K[i + 1], span = b[0] - a[0];
    let u = span <= 0 ? 1 : (t - a[0]) / span;
    const moved = Math.hypot(b[1] - a[1], b[2] - a[2]) > 0.3;
    if (moved && !(a[3] >= 0 && a[3] === b[3])) u = 1 - Math.pow(1 - u, 1.35);   // a struck ball slows down
    return [a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }
  function dirAt(i) {                                      // where the ball goes from touch i (unit vector)
    for (const [p, q] of [[i, i + 1], [i - 1, i]]) {
      if (p < 0 || q >= K.length) continue;
      const dx = K[q][1] - K[p][1], dy = K[q][2] - K[p][2], d = Math.hypot(dx, dy);
      if (d > 0.3) return [dx / d, dy / d];
    }
    return [0, 0];
  }
  function feet(x, y, d) { return [x - d[0] * FEET, y - d[1] * FEET]; }
  // Where player s is drawn at time t: his smooth curve, pulled to the ball near his touches.
  function playerAt(s, t, ball) {
    const kx = 2 + 2 * s, base = [spline(kx, t), spline(kx + 1, t)];
    const list = mine[s]; if (!list.length) return base;
    const j = search(mineT[s], t);
    const p = j >= 0 ? list[j] : -1, n = j + 1 < list.length ? list[j + 1] : -1;
    // Between two of his own touches with nobody else on the ball: he has it at his feet.
    if (p >= 0 && n === p + 1) {
      const d = Math.hypot(K[n][1] - ball[0], K[n][2] - ball[1]) > 0.3
        ? [(K[n][1] - ball[0]) / Math.hypot(K[n][1] - ball[0], K[n][2] - ball[1]), (K[n][2] - ball[1]) / Math.hypot(K[n][1] - ball[0], K[n][2] - ball[1])]
        : dirAt(n);
      return feet(ball[0], ball[1], d);
    }
    // Two blends, one after the other, so the position never jumps when both are active (a one-two):
    // first toward the next touch, then toward the last one.
    let q = base, wIn = 0;
    if (n >= 0) {                                          // running to meet the ball
      const tn = K[n][0], spot = feet(K[n][1], K[n][2], dirAt(n));
      const gap = Math.hypot(spline(kx, tn) - spot[0], spline(kx + 1, tn) - spot[1]);
      // Not before he has played his last ball (no chasing his own pass), and never instantly.
      const start = Math.min(tn - 0.3, Math.max(tn - Math.min(5.0, Math.max(0.35, gap / REL)), p >= 0 ? K[p][0] + 0.3 : -1e9));
      if (t >= start) { wIn = smooth((t - start) / (tn - start)); q = [q[0] + (spot[0] - q[0]) * wIn, q[1] + (spot[1] - q[1]) * wIn]; }
    }
    if (p >= 0) {                                          // just played it: he eases back to his place
      const tp = K[p][0], spot = feet(K[p][1], K[p][2], dirAt(p));
      const gap = Math.hypot(spline(kx, tp) - spot[0], spline(kx + 1, tp) - spot[1]);
      // The next touch takes over as it comes (so he arrives exactly on it).
      const back = (1 - smooth((t - tp) / Math.max(0.5, Math.min(5.0, gap / REL)))) * (1 - wIn);
      if (back > 0) q = [q[0] + (spot[0] - q[0]) * back, q[1] + (spot[1] - q[1]) * back];
    }
    return q;
  }
  let memoT = null, memo = null;
  function frame(t) {
    if (t === memoT) return memo;
    const out = new Float64Array(NV), ball = ballAt(t);
    out[0] = ball[0]; out[1] = ball[1];
    for (let s = 0; s < NP; s++) { const q = playerAt(s, t, ball); out[2 + 2 * s] = q[0]; out[3 + 2 * s] = q[1]; }
    for (let k = 2 + 2 * NP; k < NV; k++) out[k] = spline(k, t);
    memoT = t; memo = out; return out;
  }
  // What the screen draws while the replay runs: the same positions, but nobody moves faster than
  // a sprint (10.5 m/s) from one drawn frame to the next. Where the 1 Hz data asks for more (a
  // player far from a ball he must play), he arrives a moment late instead of jumping. A jump in
  // the clock (scrubbing, a pick) draws the exact positions.
  const LIMIT = 10.5;
  let liveT = null, livePos = null;
  function live(t) {
    const target = frame(t);
    if (liveT === t && livePos) return livePos;
    const dtm = liveT == null ? Infinity : t - liveT;
    if (!livePos || dtm <= 0 || dtm > 1.0) { livePos = Float64Array.from(target); liveT = t; return livePos; }
    const out = Float64Array.from(target), step = LIMIT * dtm;
    for (let k = 2; k < NV; k += 2) {
      const dx = target[k] - livePos[k], dy = target[k + 1] - livePos[k + 1], d = Math.hypot(dx, dy);
      if (d > step) { out[k] = livePos[k] + dx / d * step; out[k + 1] = livePos[k + 1] + dy / d * step; }
    }
    livePos = out; liveT = t; return out;
  }
  return { frame, live, ball: ballAt };
};
