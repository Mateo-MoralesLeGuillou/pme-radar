/* Vidéo pme-radar : moteur d'animation déterministe.
 * Chaque image est une fonction pure du temps t (secondes) : renderFrame(t) positionne le DOM et
 * redessine les canvas. Aucune animation CSS ni requestAnimationFrame : le rendu image par image
 * (render.js) est donc exactement reproductible.
 * Fil rouge : les 343 sociétés du run réel (Hauts-de-Seine) apparaissent sur le radar, traversent le
 * pipeline (29 exclues, 35 qualifiées), puis la caméra plonge sur une cible (échantillon synthétique).
 */
"use strict";
(function () {
  const W = 1920, H = 1080, TAU = Math.PI * 2, GOLD = 2.399963;
  const C = {
    cyan: [37, 194, 245], soft: [196, 208, 255], red: [255, 107, 129], amber: [255, 181, 71],
    grey: [98, 104, 150], white: [242, 244, 255],
  };
  // La scène de pré-due diligence (dd) est insérée après la fiche de score : les scènes suivantes
  // gardent leurs animations, on leur passe simplement un temps local décalé de SHIFT.
  const SHIFT = 14.0;
  const DURATION = 77.0 + SHIFT;
  const T = {
    s1: [0, 7.6], s2: [6.9, 16.6], s3: [15.0, 31.3], s4: [30.2, 42.7], dd: [41.9, 56.1],
    s5: [41.9 + SHIFT, 54.1 + SHIFT], s6: [53.3 + SHIFT, 64.5 + SHIFT],
    s7: [63.7 + SHIFT, 70.9 + SHIFT], s8: [70.2 + SHIFT, DURATION],
  };

  // ---------------------------------------------------------------- outils
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${clamp(a).toFixed(3)})`;
  const mix = (c1, c2, t) => [0, 1, 2].map((i) => Math.round(lerp(c1[i], c2[i], clamp(t))));
  const E = {
    lin: (t) => t,
    in3: (t) => t * t * t,
    out3: (t) => 1 - Math.pow(1 - t, 3),
    io3: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    out5: (t) => 1 - Math.pow(1 - t, 5),
    io5: (t) => (t < 0.5 ? 16 * Math.pow(t, 5) : 1 - Math.pow(-2 * t + 2, 5) / 2),
    outBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  };
  /** Progression 0→1 entre s et s+d, avec courbe d'accélération. */
  const P = (t, s, d, e = E.out3) => e(clamp((t - s) / d));
  /** Fenêtre : apparition [s, s+fi], disparition [e-fo, e]. */
  const win = (t, s, e, fi = 0.6, fo = 0.6) => Math.min(P(t, s, fi), 1 - P(t, e - fo, fo, E.in3));
  const mod = (a, m) => ((a % m) + m) % m;
  const bez = (p0, p1, p2, s) => [
    (1 - s) * (1 - s) * p0[0] + 2 * (1 - s) * s * p1[0] + s * s * p2[0],
    (1 - s) * (1 - s) * p0[1] + 2 * (1 - s) * s * p1[1] + s * s * p2[1],
  ];
  function rng(seed) {
    let s = seed >>> 0;
    return () => {
      s = (s + 0x6d2b79f5) >>> 0;
      let x = s;
      x = Math.imul(x ^ (x >>> 15), x | 1);
      x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffle(arr, r) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
  function $(tag, cls, parent, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    parent.appendChild(e);
    return e;
  }
  function place(e, x, y, extra) {
    e.style.left = `${x}px`; e.style.top = `${y}px`;
    if (extra) Object.assign(e.style, extra);
    return e;
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  /** Texte découpé en mots masqués (révélation par glissement). */
  function words(parent, text, cls, x, y, style) {
    const box = place($("div", `abs ${cls || ""}`, parent), x, y, style);
    const spans = [];
    text.split(" ").forEach((w, i, all) => {
      const m = $("span", "w", box);
      spans.push($("span", "", m, esc(w)));
      if (i < all.length - 1) box.appendChild(document.createTextNode(" "));
    });
    return { box, spans };
  }
  function reveal(spans, t, start, stagger = 0.05, dur = 0.75) {
    spans.forEach((s, i) => {
      const p = P(t, start + i * stagger, dur, E.out5);
      s.style.transform = `translateY(${((1 - p) * 110).toFixed(1)}%)`;
      s.style.opacity = p.toFixed(3);
    });
  }
  const fr = (n) => String(Math.round(n));

  // Icônes au trait (dessinées progressivement grâce à pathLength=1)
  const ICONS = {
    data: ["M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z", "M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6", "M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"],
    search: ["M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13z", "M15.5 15.5l5 5"],
    gauge: ["M4 16a8 8 0 0 1 16 0", "M12 16l4.5-5", "M3 20h18"],
    target: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M8 12.2l2.8 2.8 5.4-6"],
    nomail: ["M3 6h18v12H3z", "M3 7l9 6 9-6", "M2.5 3.5l19 17"],
    shield: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z", "M8.5 12l2.5 2.5 4.5-5"],
    check: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M7.5 12.3l3 3 6-6.6"],
  };
  function icon(name, color = "#25c2f5", width = 1.7) {
    const paths = ICONS[name]
      .map((d) => `<path class="draw" pathLength="1" d="${d}" stroke-dasharray="1" stroke-dashoffset="1"/>`)
      .join("");
    return `<svg viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
  }
  function drawIcon(root, p) {
    root.querySelectorAll(".draw").forEach((d, i, all) => {
      const q = clamp(p * all.length - i * 0.6);
      d.setAttribute("stroke-dashoffset", (1 - q).toFixed(3));
    });
  }

  // ---------------------------------------------------------------- arrière-plan
  const bgDots = (() => {
    const r = rng(11);
    return Array.from({ length: 150 }, () => ({ x: r() * W, y: r() * H, z: 0.25 + r() * 0.75, ph: r() * TAU }));
  })();
  function drawBg(ctx, t) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const gx = W * 0.5 + Math.sin(t * 0.11) * 300, gy = H * 0.42 + Math.cos(t * 0.09) * 140;
    const g = ctx.createRadialGradient(gx, gy, 0, gx, gy, 950);
    g.addColorStop(0, "rgba(70,70,150,0.30)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    for (const d of bgDots) {
      const x = mod(d.x + t * 14 * d.z, W), y = mod(d.y - t * 6 * d.z, H);
      const a = (0.1 + 0.1 * Math.sin(t * 1.2 + d.ph)) * d.z;
      ctx.fillStyle = `rgba(150,170,255,${a.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(x, y, 0.5 + 1.3 * d.z, 0, TAU);
      ctx.fill();
    }
  }

  // ---------------------------------------------------------------- radar
  const OMEGA = TAU / 3.0; // un tour en 3 s
  const sweepAngle = (t, o) => -Math.PI / 2 + (t - o.tSweep) * OMEGA;
  const firstPass = (b, o) => o.tSweep + mod(b.th + Math.PI / 2, TAU) / OMEGA;

  function drawRadar(ctx, t, o, blips) {
    const { cx, cy, R } = o;
    if (o.alpha <= 0.002 || R < 2) return;
    ctx.save();
    ctx.globalAlpha = o.alpha;
    const grow = P(t, o.t0, 1.0, E.out3);
    const disc = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
    disc.addColorStop(0, "rgba(42,42,86,0.70)");
    disc.addColorStop(1, "rgba(22,22,46,0.30)");
    ctx.fillStyle = disc;
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(0.1, R * grow), 0, TAU);
    ctx.fill();
    ctx.lineWidth = Math.max(1, R / 150);
    for (let i = 1; i <= 4; i++) {
      const pr = P(t, o.t0 + 0.1 * i, 1.1, E.io3);
      if (pr <= 0) continue;
      ctx.strokeStyle = rgba(C.cyan, i === 4 ? 0.5 : 0.14 + 0.04 * i);
      ctx.beginPath();
      ctx.arc(cx, cy, (R * i) / 4, -Math.PI / 2, -Math.PI / 2 + TAU * pr);
      ctx.stroke();
    }
    const cp = P(t, o.t0 + 0.5, 0.8);
    ctx.strokeStyle = rgba(C.cyan, 0.1 * cp);
    ctx.beginPath();
    ctx.moveTo(cx - R * cp, cy); ctx.lineTo(cx + R * cp, cy);
    ctx.moveTo(cx, cy - R * cp); ctx.lineTo(cx, cy + R * cp);
    ctx.stroke();
    if (t > o.tSweep) {
      const a = sweepAngle(t, o), sp = P(t, o.tSweep, 0.6), span = 1.3;
      const cg = ctx.createConicGradient(a - span, cx, cy);
      cg.addColorStop(0, rgba(C.cyan, 0));
      cg.addColorStop(span / TAU - 0.001, rgba(C.cyan, 0.36 * sp));
      cg.addColorStop(span / TAU, rgba(C.cyan, 0));
      cg.addColorStop(1, rgba(C.cyan, 0));
      ctx.fillStyle = cg;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, R, a - span, a);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = rgba(C.cyan, 0.95 * sp);
      ctx.lineWidth = Math.max(1.2, R / 100);
      ctx.shadowColor = rgba(C.cyan, 0.9);
      ctx.shadowBlur = R / 10;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + R * Math.cos(a), cy + R * Math.sin(a));
      ctx.stroke();
      ctx.shadowBlur = 0;
      if (blips && R > 50) {
        const k = R / 285;
        for (const b of blips) {
          const td = firstPass(b, o);
          if (t < td) continue;
          const since = mod(a - b.th, TAU) / OMEGA;
          const glow = Math.exp(-since * 2.3) * (t - td < 0.05 ? (t - td) / 0.05 : 1);
          const x = cx + b.r * R * Math.cos(b.th), y = cy + b.r * R * Math.sin(b.th);
          const q = b.q ? P(t, o.qualFrom + b.r * 0.8, 0.7) : 0;
          let col = mix(C.soft, C.white, glow), rad = (1.7 + 2.3 * glow) * k, al = 0.32 + 0.68 * glow;
          if (q > 0) {
            col = mix(col, C.cyan, q);
            rad = lerp(rad, 4.6 * k, q);
            al = lerp(al, 1, q);
            ctx.fillStyle = rgba(C.cyan, 0.17 * q * (0.75 + 0.25 * Math.sin(t * 3 + b.th * 5)));
            ctx.beginPath();
            ctx.arc(x, y, rad * 3.2, 0, TAU);
            ctx.fill();
          }
          ctx.fillStyle = rgba(col, al);
          ctx.beginPath();
          ctx.arc(x, y, rad, 0, TAU);
          ctx.fill();
        }
      }
    }
    ctx.fillStyle = rgba(C.cyan, 1);
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(2, R / 55), 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  // ---------------------------------------------------------------- construction
  window.init = function (F, A) {
    const layer = document.getElementById("layer");
    const fx = document.getElementById("fx").getContext("2d");
    const bg = document.getElementById("bg").getContext("2d");
    const fade = document.getElementById("fade");
    const SCENES = [];
    const CUES = [];
    const scene = (span, update, shift = 0) => {
      const root = $("div", "scene", layer);
      const sc = { start: span[0], end: span[1], root, update, shift };
      SCENES.push(sc);
      return sc;
    };
    const N = F.run.sourced, NX = F.run.excluded, NQ = F.run.qualified;

    // --- sociétés (particules) : catégories, positions de grille, ordre d'émission
    const r = rng(2026);
    const ids = shuffle([...Array(N).keys()], r);
    const cat = new Array(N).fill("low");
    ids.slice(0, NX).forEach((i) => (cat[i] = "excl"));
    ids.slice(NX, NX + NQ).forEach((i) => (cat[i] = "qual"));
    const order = shuffle([...Array(N).keys()], r);
    const COLS = 21, ROWS = Math.ceil(N / COLS), GX = 1440, GY = 548, SP = 37;
    const SRC = [500, 520], X1 = 880, X2 = 1260, X3 = 1640, Y = 520;
    const D1 = 1.0, D2 = 1.0, D3 = 1.05, DROP = 0.9, EMIT0 = 16.9, EMIT = 5.4;
    const counters = { excl: 0, low: 0, qual: 0 };
    const comp = [...Array(N).keys()].map((i) => {
      const col = i % COLS, row = Math.floor(i / COLS);
      const gx = GX + (col - (COLS - 1) / 2) * SP + (r() - 0.5) * 9;
      const gy = GY + (row - (ROWS - 1) / 2) * SP + (r() - 0.5) * 9;
      const k = order[i];
      const c = {
        i, cat: cat[i], grid: [gx, gy], ph: r() * TAU, amber: r() < 0.22,
        appear: 7.5 + (Math.hypot(gx - GX, gy - GY) / 430) * 1.1 + r() * 0.15,
        flyDelay: (col / COLS) * 0.75 + r() * 0.2,
        src: [SRC[0] + 4.1 * Math.sqrt(k) * Math.cos(k * GOLD), SRC[1] + 4.1 * Math.sqrt(k) * Math.sin(k * GOLD)],
        te: EMIT0 + (k / (N - 1)) * EMIT, lane: (r() - 0.5) * 70,
      };
      const n = counters[c.cat]++;
      const centers = { excl: [X1, 845, 7.6], low: [X2, 850, 6.3], qual: [X3, Y, 8.4] };
      const [bx, by, sp] = centers[c.cat];
      c.rest = [bx + sp * Math.sqrt(n) * Math.cos(n * GOLD), by + sp * Math.sqrt(n) * Math.sin(n * GOLD)];
      return c;
    });
    // les mêmes sociétés sont les points du radar (les qualifiées s'y allument déjà)
    const blips = comp.map((c) => ({ r: 0.12 + 0.84 * Math.sqrt(r()), th: r() * TAU, q: c.cat === "qual" }));

    function flowPos(c, t) {
      let u = t - c.te;
      if (u < D1) {
        const s = E.io3(u / D1);
        return [lerp(c.src[0], X1, s), lerp(c.src[1], Y, s) + c.lane * Math.sin(Math.PI * s) * 0.8];
      }
      u -= D1;
      if (c.cat === "excl") return bez([X1, Y], [X1 + 50, Y + 150], c.rest, E.io3(clamp(u / DROP)));
      if (u < D2) {
        const s = E.io3(u / D2);
        return [lerp(X1, X2, s), Y + c.lane * Math.sin(Math.PI * s)];
      }
      u -= D2;
      if (c.cat === "low") return bez([X2, Y], [X2 + 50, Y + 150], c.rest, E.io3(clamp(u / DROP)));
      const s = E.io3(clamp(u / D3));
      return [lerp(X2, c.rest[0], s), lerp(Y, c.rest[1], s) + c.lane * 0.5 * Math.sin(Math.PI * s)];
    }
    function compPos(c, t) {
      const f0 = 14.7 + c.flyDelay, f1 = f0 + 0.95;
      if (t < f0) {
        let [x, y] = c.grid;
        const j = P(t, 12.0, 0.8) * (1 - P(t, 13.4, 0.6)) * 2.6;
        x += Math.sin(t * 9 + c.ph) * j;
        y += Math.cos(t * 7.3 + c.ph) * j;
        return [x, y];
      }
      if (t < f1) {
        const s = E.io3((t - f0) / 0.95);
        return bez(c.grid, [lerp(c.grid[0], c.src[0], 0.5), Math.min(c.grid[1], c.src[1]) - 160], c.src, s);
      }
      if (t < c.te) {
        const k = 1 + 0.035 * Math.sin(t * 2.2 + c.ph);
        return [SRC[0] + (c.src[0] - SRC[0]) * k, SRC[1] + (c.src[1] - SRC[1]) * k];
      }
      return flowPos(c, t);
    }
    function compStyle(c, t) {
      let col = C.soft, a = 0.8, rad = 3.1, halo = 0;
      if (t < 14.7) {
        if (c.amber) {
          const pulse = win(t, 10.15 + c.ph * 0.12, 12.3, 0.35, 0.6);
          col = mix(col, C.amber, pulse); a += 0.2 * pulse; rad += 1.0 * pulse;
        }
        const grey = P(t, 12.0, 0.8) * (1 - P(t, 13.4, 0.6));
        col = mix(col, C.grey, grey * 0.9); a = lerp(a, 0.45, grey);
      }
      if (t >= c.te) {
        const u = t - c.te;
        if (c.cat === "excl" && u > D1 - 0.1) { col = mix(C.soft, C.red, P(u, D1 - 0.1, 0.3)); a = 0.92; }
        if (c.cat !== "excl" && u > D1 + D2 - 0.1) {
          const k = P(u, D1 + D2 - 0.1, 0.3);
          if (c.cat === "qual") { col = mix(C.soft, C.cyan, k); rad = lerp(3.1, 4.7, k); halo = k; a = 1; }
          else { col = mix(C.soft, C.grey, k); a = lerp(0.8, 0.55, k); }
        }
      }
      return [col, a, rad, halo];
    }
    const camera = (t) => {
      const z = 1 + 1.35 * P(t, 28.9, 2.2, E.io5);
      return { z, fx: X3, fy: Y };
    };
    function drawCompanies(t) {
      if (t < 7.3 || t > 31.3) return;
      const cam = camera(t), alpha = 1 - P(t, 29.9, 1.3, E.in3);
      fx.save();
      fx.setTransform(cam.z, 0, 0, cam.z, cam.fx - cam.z * cam.fx, cam.fy - cam.z * cam.fy);
      fx.globalAlpha = alpha;
      for (const c of comp) {
        const app = P(t, c.appear, 0.55, E.outBack);
        if (app <= 0) continue;
        const [x, y] = compPos(c, t);
        const [col, a, rad, halo] = compStyle(c, t);
        if (halo > 0) {
          fx.fillStyle = rgba(C.cyan, 0.16 * halo);
          fx.beginPath(); fx.arc(x, y, rad * 3.1, 0, TAU); fx.fill();
        }
        fx.fillStyle = rgba(col, a);
        fx.beginPath(); fx.arc(x, y, Math.max(0.1, rad * app), 0, TAU); fx.fill();
      }
      fx.restore();
    }

    // --- marque persistante (coin supérieur gauche)
    const brand = $("div", "brand", layer, `<img src="${A.logo}" alt=""><b>pme<i>-</i>radar</b>`);
    const brandUpdate = (t) => { brand.style.opacity = win(t, 7.0, 70.6 + SHIFT, 0.7, 0.6).toFixed(3); };

    // ================================================================ S1 · radar
    const s1 = scene(T.s1, (t) => {
      const ex = P(t, 6.2, 1.3, E.io3);
      drawRadar(fx, t, {
        cx: lerp(960, 79, ex), cy: lerp(400, 67, ex), R: lerp(285, 23, ex),
        alpha: 1 - P(t, 7.0, 0.55), t0: 0.15, tSweep: 0.7, qualFrom: 3.7,
      }, blips);
      const out = 1 - P(t, 5.9, 0.8, E.in3);
      s1title.forEach((sp, i) => {
        const p = P(t, 2.1 + i * 0.045, 0.85, E.out5);
        sp.style.transform = `translateY(${((1 - p) * 70 - ex * 30).toFixed(1)}px)`;
        sp.style.opacity = (p * out).toFixed(3);
      });
      reveal(s1tag.spans, t, 3.0, 0.045);
      s1tag.box.style.opacity = out.toFixed(3);
    });
    const t1 = place($("div", "abs center display letters", s1.root), 0, 712, { fontSize: "136px" });
    const s1title = "pme-radar".split("").map((ch) => $("span", ch === "-" ? "cyan" : "", t1, ch));
    const s1tag = words(s1.root, "Repérer les PME à transmettre, à partir de l'open data.", "center", 0, 880, {
      fontSize: "40px", color: "#c9cdf0", fontWeight: "500",
    });
    blips
      .map((b) => ({ b, td: firstPass(b, { tSweep: 0.7 }) }))
      .filter(({ b, td }) => b.q && td > 0.9 && td < 3.6)
      .slice(0, 8)
      .forEach(({ td }) => CUES.push({ t: td, type: "blip" }));

    // ================================================================ S2 · le problème
    const s2 = scene(T.s2, (t) => {
      const out = 1 - P(t, 14.5, 0.9, E.in3);
      s2.root.style.opacity = out.toFixed(3);
      const p = P(t, 7.7, 1.6, E.out3);
      s2count.textContent = fr(N * p);
      s2count.style.opacity = P(t, 7.5, 0.5).toFixed(3);
      s2count.style.transform = `translateY(${((1 - P(t, 7.5, 0.9, E.out5)) * 40).toFixed(1)}px)`;
      reveal(s2l1.spans, t, 8.3, 0.05);
      reveal(s2l2.spans, t, 8.8, 0.04);
      reveal(s2l3.spans, t, 10.0, 0.05);
      reveal(s2l4.spans, t, 11.9, 0.05);
      reveal(s2l5.spans, t, 13.4, 0.06);
    });
    const s2count = place($("div", "abs display cyan", s2.root, "0"), 120, 205, {
      fontSize: "210px", fontWeight: "800", fontVariantNumeric: "tabular-nums",
    });
    const s2l1 = words(s2.root, "PME ciblées par la thèse", "", 128, 440, { fontSize: "46px", fontWeight: "650" });
    const s2l2 = words(s2.root, "rien que dans les Hauts-de-Seine (run réel).", "muted", 128, 505, { fontSize: "29px" });
    const s2l3 = words(s2.root, "Des dirigeants qui approchent de la retraite.", "", 128, 625, { fontSize: "38px", fontWeight: "500" });
    const s2l4 = words(s2.root, "Mais aucun signal clair pour savoir qui appeler.", "", 128, 690, { fontSize: "38px", fontWeight: "500" });
    const s2l5 = words(s2.root, "pme-radar fait le tri.", "display cyan", 128, 800, { fontSize: "60px" });
    CUES.push({ t: 9.3, type: "tick" });

    // ================================================================ S3 · pipeline
    const s3 = scene(T.s3, (t) => {
      const cam = camera(t);
      s3.root.style.transform = `translate(${cam.fx}px,${cam.fy}px) scale(${cam.z}) translate(${-cam.fx}px,${-cam.fy}px)`;
      const out = 1 - P(t, 29.9, 1.3, E.in3);
      s3.root.style.opacity = (P(t, 15.4, 0.6) * out).toFixed(3);
      reveal(s3head.spans, t, 15.6, 0.05);
      reveal(s3cap.spans, t, 16.1, 0.03);
      s3pills.forEach((pl, i) => {
        const p = P(t, 15.9 + i * 0.15, 0.7, E.out5);
        pl.style.opacity = p.toFixed(3);
        pl.style.transform = `translateX(${((1 - p) * -60).toFixed(1)}px)`;
      });
      // activité des nœuds : particules qui les franchissent en ce moment
      let a1 = 0, a2 = 0, a3 = 0, n1 = 0, nx = 0, n2 = 0, nl = 0, nq = 0;
      for (const c of comp) {
        const u = t - c.te;
        if (u >= D1) n1++;
        if (Math.abs(u - D1) < 0.12) a1++;
        if (c.cat === "excl" && u >= D1 + DROP * 0.85) nx++;
        if (c.cat !== "excl") {
          if (u >= D1 + D2) n2++;
          if (Math.abs(u - D1 - D2) < 0.12) a2++;
          if (c.cat === "low" && u >= D1 + D2 + DROP * 0.85) nl++;
          if (c.cat === "qual") {
            if (u >= D1 + D2 + D3 * 0.9) nq++;
            if (Math.abs(u - D1 - D2 - D3) < 0.15) a3++;
          }
        }
      }
      const act = [0.2, clamp(a1 / 5), clamp(a2 / 5), clamp(a3 / 2)];
      s3nodes.forEach((nd, i) => {
        const p = P(t, 16.0 + i * 0.25, 0.7, E.outBack);
        nd.el.style.transform = `scale(${p.toFixed(3)})`;
        nd.el.style.boxShadow = `0 0 ${(18 + 40 * act[i]).toFixed(0)}px rgba(37,194,245,${(0.2 + 0.6 * act[i]).toFixed(2)})`;
        drawIcon(nd.el, P(t, 16.3 + i * 0.25, 0.9, E.io3));
        nd.label.style.opacity = P(t, 16.4 + i * 0.25, 0.6).toFixed(3);
      });
      const show = (el, start, text) => { el.style.opacity = P(t, start, 0.5).toFixed(3); if (text !== undefined) el.querySelector(".n").textContent = text; };
      show(s3c0, 15.9, fr(N * P(t, 14.7, 1.7)));
      show(s3c1, 17.6, fr(n1));
      show(s3cx, 18.4, fr(nx));
      show(s3c2, 18.6, fr(n2));
      show(s3cl, 19.4, fr(nl));
      show(s3c3, 19.6, fr(nq));
      s3pct.style.opacity = P(t, lastQual + 0.2, 0.6).toFixed(3);
      // liaisons et bacs (canvas, sous la même caméra)
      fx.save();
      fx.setTransform(cam.z, 0, 0, cam.z, cam.fx - cam.z * cam.fx, cam.fy - cam.z * cam.fy);
      fx.globalAlpha = out;
      const lp = P(t, 15.9, 1.4, E.io3);
      const grad = fx.createLinearGradient(SRC[0], 0, X3, 0);
      grad.addColorStop(0, rgba(C.cyan, 0.08));
      grad.addColorStop(1, rgba(C.cyan, 0.45));
      fx.strokeStyle = grad;
      fx.lineWidth = 2;
      fx.beginPath(); fx.moveTo(SRC[0] + 60, Y); fx.lineTo(lerp(SRC[0] + 60, X3, lp), Y); fx.stroke();
      const bins = [[X1, 845, 62, C.red, 18.2], [X2, 850, 125, C.grey, 18.4]];
      for (const [bx, by, br, bc, bs] of bins) {
        const bp = P(t, bs, 0.8, E.io3);
        fx.setLineDash([6, 8]);
        fx.strokeStyle = rgba(bc, 0.55 * bp);
        fx.beginPath(); fx.arc(bx, by, br, -Math.PI / 2, -Math.PI / 2 + TAU * bp); fx.stroke();
        fx.setLineDash([]);
      }
      const rp = P(t, 18.6, 0.8, E.io3);
      fx.strokeStyle = rgba(C.cyan, 0.5 * rp);
      fx.beginPath(); fx.arc(X3, Y, 70, -Math.PI / 2, -Math.PI / 2 + TAU * rp); fx.stroke();
      fx.restore();
    });
    const s3head = words(s3.root, "De l'open data à une liste courte.", "display center", 0, 118, { fontSize: "60px" });
    const s3cap = words(s3.root, `Run réel · Hauts-de-Seine (92) · ${F.run.date} · chiffres agrégés`, "center muted", 0, 205, { fontSize: "24px" });
    const s3pills = [
      ["API Recherche d'entreprises", "identité, dirigeants, CA"],
      ["BODACC", "procédures collectives"],
      ["Ratios BCE / INPI", "EBE, endettement"],
    ].map(([a, b], i) => place($("div", "pill", s3.root, `${esc(a)}<small>${esc(b)}</small>`), 40, 300 + i * 92));
    const NODES = [
      [SRC[0], "data", "Sourcing", "thèse : NAF, taille, zone"],
      [X1, "search", "Enrichissement", "âge, marges, holdings"],
      [X2, "gauge", "Score /100", "déterministe, explicable"],
      [X3, "target", "Liste courte", `seuil de ${F.threshold}/100`],
    ];
    const s3nodes = NODES.map(([x, ic, title, sub]) => {
      const el = place($("div", "node", s3.root, icon(ic)), x, Y);
      const label = place($("div", "node-label", s3.root, `<div class="t">${esc(title)}</div><div class="s">${esc(sub)}</div>`), x, Y - 150);
      return { el, label };
    });
    const count = (x, y, cls, label) => place($("div", `count ${cls}`, s3.root, `<div class="n">0</div><div class="l">${esc(label)}</div>`), x, y);
    const s3c0 = count(SRC[0], 618, "", "sociétés sourcées");
    const s3c1 = count(X1, 590, "", "analysées");
    const s3cx = count(X1, 925, "red", "exclues · procédure collective");
    const s3c2 = count(X2, 590, "", "notées");
    const s3cl = count(X2, 985, "muted", `sous le seuil de ${F.threshold}`);
    const s3c3 = count(X3, 605, "cyan", "qualifiées");
    const pct = ((100 * NQ) / F.run.scored).toFixed(1).replace(".", ",");
    const s3pct = place($("div", "abs muted", s3.root, `soit ${pct} % des sociétés notées`), X3 - 180, 700, {
      width: "360px", textAlign: "center", fontSize: "19px",
    });
    const lastQual = Math.max(...comp.filter((c) => c.cat === "qual").map((c) => c.te + D1 + D2 + D3 * 0.9));
    CUES.push({ t: lastQual, type: "tick" });

    // ================================================================ S4 · score explicable
    const det = F.target.detail.filter((d) => d.max > 0);
    const CARD = { x: 890, y: 140, w: 960, h: 800 };
    const s4 = scene(T.s4, (t) => {
      const ent = P(t, 30.3, 1.2, E.out5), ex = P(t, 41.8, 0.85, E.in3);
      card.style.opacity = (P(t, 30.3, 0.5) * (1 - ex)).toFixed(3);
      card.style.transform = `translate(${(-260 * ex).toFixed(1)}px,${(Math.sin(t * 0.9) * 5).toFixed(2)}px) scale(${lerp(0.45, 1, ent).toFixed(4)})`;
      card.style.filter = `blur(${((1 - ent) * 10).toFixed(1)}px)`;
      const lout = 1 - P(t, 41.6, 0.7, E.in3);
      reveal(s4h1.spans, t, 30.9, 0.06);
      reveal(s4h2.spans, t, 31.2, 0.06);
      reveal(s4sub.spans, t, 31.8, 0.025);
      [s4h1, s4h2, s4sub].forEach((w) => (w.box.style.opacity = lout.toFixed(3)));
      s4tag.style.opacity = (P(t, 32.6, 0.6) * lout).toFixed(3);
      let total = 0;
      rows.forEach((rw, i) => {
        const st = 31.9 + i * 0.5;
        const pin = P(t, st, 0.5, E.out5), pf = P(t, st + 0.15, 0.55, E.out3);
        rw.el.style.opacity = pin.toFixed(3);
        rw.el.style.transform = `translateX(${((1 - pin) * 40).toFixed(1)}px)`;
        rw.fill.style.width = `${((det[i].points / det[i].max) * 100 * pf).toFixed(2)}%`;
        rw.pts.textContent = `${fr(det[i].points * pf)}/${det[i].max}`;
        total += det[i].points * pf;
      });
      const shown = Math.min(F.target.score, total);
      ring.setAttribute("stroke-dashoffset", (RING_C * (1 - shown / 100)).toFixed(2));
      ringNum.innerHTML = `${fr(shown)}<div style="font-size:17px;color:#9aa0c8;font-weight:600;letter-spacing:0;margin-top:-4px">/100</div>`;
      const pulse = Math.sin(clamp((t - scoreDone) / 0.5) * Math.PI) * 0.08;
      ringBox.style.transform = `scale(${(1 + pulse).toFixed(4)})`;
      const ok = P(t, scoreDone + 0.15, 0.5, E.outBack);
      okTag.style.opacity = clamp(ok).toFixed(3);
      okTag.style.transform = `scale(${lerp(0.6, 1, ok).toFixed(3)})`;
      const okc = P(t, scoreDone + 0.4, 0.5, E.outBack);
      confTag.style.opacity = clamp(okc).toFixed(3);
      confTag.style.transform = `scale(${lerp(0.6, 1, okc).toFixed(3)})`;
    });
    const s4h1 = words(s4.root, "Un score sur 100,", "display", 120, 300, { fontSize: "66px" });
    const s4h2 = words(s4.root, "critère par critère.", "display cyan", 120, 384, { fontSize: "66px" });
    const s4sub = words(s4.root, "Déterministe, explicable, réglable sans une ligne de code.", "muted", 122, 500, {
      fontSize: "29px", width: "700px", lineHeight: "1.4",
    });
    const s4tag = place($("div", "abs tag synth", s4.root, "Cible synthétique · échantillon de démo"), 124, 625);
    const card = place($("div", "card", s4.root), CARD.x, CARD.y, { width: `${CARD.w}px`, height: `${CARD.h}px`, transformOrigin: "50% 50%" });
    const head = place($("div", "abs card-head", card), 40, 36, { width: "600px" });
    head.innerHTML = `<h3>${esc(F.target.name)}</h3><p>${esc(F.target.city)} (${esc(F.target.department)}) · ${esc(F.target.naf_label)}</p>`;
    head.querySelector("p").style.cssText = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
    const RING_R = 66, RING_C = TAU * RING_R;
    const ringBox = place($("div", "abs", card), CARD.w - 210, 22, { width: "170px", height: "170px" });
    const thr = (F.threshold / 100) * TAU - Math.PI / 2;
    ringBox.innerHTML = `<svg viewBox="0 0 170 170" width="170" height="170">
      <circle cx="85" cy="85" r="${RING_R}" fill="none" stroke="#2c2c4d" stroke-width="13"/>
      <circle class="ring" cx="85" cy="85" r="${RING_R}" fill="none" stroke="#25c2f5" stroke-width="13" stroke-linecap="round"
        stroke-dasharray="${RING_C.toFixed(2)}" stroke-dashoffset="${RING_C.toFixed(2)}" transform="rotate(-90 85 85)"/>
      <line x1="${(85 + 54 * Math.cos(thr)).toFixed(1)}" y1="${(85 + 54 * Math.sin(thr)).toFixed(1)}"
        x2="${(85 + 79 * Math.cos(thr)).toFixed(1)}" y2="${(85 + 79 * Math.sin(thr)).toFixed(1)}" stroke="#ffb547" stroke-width="4" stroke-linecap="round"/></svg>`;
    const ring = ringBox.querySelector(".ring");
    const ringNum = place($("div", "ring-num", ringBox), 0, 50, { width: "170px", fontSize: "48px", lineHeight: "1" });
    const rows = det.map((d, i) => {
      const el = place($("div", "row", card), 40, 200 + i * 57);
      el.style.left = "40px";
      const label = d["critère"].replace(/\s*\(.*\)\s*$/, "");
      el.innerHTML = `<div class="lab">${esc(label)}</div><div class="track"><div class="fill"></div></div><div class="pts">0</div><div class="det">${esc(d["détail"])}</div>`;
      return { el, fill: el.querySelector(".fill"), pts: el.querySelector(".pts") };
    });
    const okTag = place($("div", "abs tag ok", card, `Qualifiée · seuil de ${F.threshold}/100`), 40, 728, { transformOrigin: "0 50%", fontSize: "16px" });
    const confTag = place($("div", "abs tag", card, `Fiabilité des données · ${Math.round(F.target.confidence * 100)} %`), 330, 728, {
      transformOrigin: "0 50%", fontSize: "16px", color: "#c8cbec", border: "1px solid rgba(154,160,200,.45)", background: "rgba(154,160,200,.08)",
    });
    const scoreDone = 31.9 + (det.length - 1) * 0.5 + 0.7;
    CUES.push({ t: scoreDone, type: "ding" });

    // ================================================================ DD · rapport de pré-due diligence
    const D = F.dd;
    const eurFR = (v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2).replace(".", ",")} M€` : `${Math.round(v / 1e3)} k€`);
    const multFR = (v) => `${v.toFixed(2).replace(".", ",")}x`;
    const PANEL = { x: 900, y: 150, w: 940, h: 780 };
    const VMAX = D.ev_high * 1.3;
    const RECO_T = 52.3;
    const PAGE_POS = [[1010, 175, -7], [1230, 205, -1], [1450, 240, 6]];
    const sdd = scene(T.dd, (t) => {
      const lout = 1 - P(t, 55.1, 0.8, E.in3);
      reveal(ddH1.spans, t, 42.3, 0.06);
      reveal(ddH2.spans, t, 42.6, 0.06);
      reveal(ddSub.spans, t, 43.3, 0.025);
      [ddH1, ddH2, ddSub].forEach((w) => (w.box.style.opacity = lout.toFixed(3)));
      ddChecks.forEach((ck, i) => {
        const p = P(t, 44.6 + i * 0.4, 0.6, E.out5);
        ck.style.opacity = (p * lout).toFixed(3);
        ck.style.transform = `translateX(${((1 - p) * -30).toFixed(1)}px)`;
        drawIcon(ck, P(t, 44.7 + i * 0.4, 0.7, E.io3));
      });
      // pages du rapport : arrivée en éventail, puis envol quand le panneau apparaît
      const away = P(t, 46.0, 0.9, E.in3);
      pages.forEach((pg, i) => {
        const p = P(t, 42.4 + i * 0.3, 1.1, E.out5), rz = PAGE_POS[i][2];
        pg.style.opacity = (P(t, 42.4 + i * 0.3, 0.4) * (1 - away)).toFixed(3);
        pg.style.transform = `perspective(1600px) translate(${(lerp(520, 0, p) + away * 280).toFixed(1)}px,${(lerp(60, 0, p) - away * 40).toFixed(1)}px) rotateY(${lerp(-38, 0, p).toFixed(2)}deg) rotate(${(rz * p).toFixed(2)}deg) scale(${lerp(1, 0.75, away).toFixed(3)})`;
      });
      // panneau de synthèse du dossier
      const ent = P(t, 46.3, 1.0, E.out5), ex = P(t, 55.2, 0.85, E.in3);
      panel.style.opacity = (P(t, 46.3, 0.5) * (1 - ex)).toFixed(3);
      panel.style.transform = `translateY(${(Math.sin(t * 0.9) * 4).toFixed(2)}px) scale(${(lerp(0.9, 1, ent) * lerp(1, 0.94, ex)).toFixed(4)})`;
      // valeur d'entreprise : la fourchette s'ouvre depuis son milieu
      const vr = P(t, 47.1, 0.9, E.io3), mid = (D.ev_low + D.ev_high) / 2;
      const lo = lerp(mid, D.ev_low, vr), hi = lerp(mid, D.ev_high, vr);
      evFill.style.left = `${((100 * lo) / VMAX).toFixed(2)}%`;
      evFill.style.width = `${((100 * (hi - lo)) / VMAX).toFixed(2)}%`;
      evLo.textContent = eurFR(lo);
      evHi.textContent = eurFR(hi);
      evLo.style.left = `${((100 * lo) / VMAX).toFixed(2)}%`;
      evHi.style.left = `${((100 * hi) / VMAX).toFixed(2)}%`;
      [evLo, evHi, evCap].forEach((e) => (e.style.opacity = P(t, 47.2, 0.5).toFixed(3)));
      // montage : dette senior, crédit vendeur, fonds propres
      const parts = [D.senior_debt, D.vendor_loan, D.equity], total = parts.reduce((a, b) => a + b, 0);
      segs.forEach((sg, i) => {
        sg.style.width = `${(((100 * parts[i]) / total) * P(t, 48.2 + i * 0.45, 0.6, E.out3)).toFixed(2)}%`;
      });
      segLabels.forEach((lb, i) => (lb.style.opacity = P(t, 48.4 + i * 0.45, 0.4).toFixed(3)));
      cov.style.opacity = P(t, 49.8, 0.5).toFixed(3);
      drawIcon(cov, P(t, 49.85, 0.6, E.io3));
      ddSignals.forEach((ch, i) => {
        const p = P(t, 50.3 + i * 0.25, 0.5, E.outBack);
        ch.style.opacity = clamp(p).toFixed(3);
        ch.style.transform = `scale(${lerp(0.7, 1, p).toFixed(3)})`;
      });
      qHead.style.opacity = P(t, 50.9, 0.4).toFixed(3);
      qCount.textContent = fr(D.questions_total * P(t, 51.0, 0.9, E.out3));
      qLines.forEach((q, i) => {
        const p = P(t, 51.3 + i * 0.35, 0.5, E.out5);
        q.style.opacity = p.toFixed(3);
        q.style.transform = `translateX(${((1 - p) * 30).toFixed(1)}px)`;
      });
      const sp = P(t, RECO_T, 0.45, E.outBack);
      reco.style.opacity = (clamp(P(t, RECO_T, 0.15)) * (1 - ex)).toFixed(3);
      reco.style.transform = `rotate(-6deg) scale(${lerp(2.2, 1, sp).toFixed(3)})`;
    });
    const ddH1 = words(sdd.root, "Le rapport de deal flow,", "display", 120, 210, { fontSize: "64px" });
    const ddH2 = words(sdd.root, "prêt pour la due diligence.", "display cyan", 120, 292, { fontSize: "64px" });
    const ddSub = words(sdd.root, "Pour chaque cible : valeur, montage, risques et questions à poser au cédant.", "muted", 122, 405, {
      fontSize: "27px", width: "700px", lineHeight: "1.4",
    });
    const ddChecks = ["Thèse d'investissement, points de vigilance", "Valorisation, sensibilité, financement",
      "Plan de DD et demandes d'informations", "Recommandation et prochaines étapes"].map((txt, i) =>
      place($("div", "check", sdd.root, `${icon("check")}<span>${esc(txt)}</span>`), 124, 548 + i * 58));
    const pages = D.pages.map((file, i) => {
      const img = place($("img", "page", sdd.root), PAGE_POS[i][0], PAGE_POS[i][1], { transformOrigin: "50% 50%" });
      img.src = `${A.shots}/${file}`;
      return img;
    });
    const panel = place($("div", "card", sdd.root), PANEL.x, PANEL.y, { width: `${PANEL.w}px`, height: `${PANEL.h}px`, transformOrigin: "50% 50%" });
    const mlo = String(D.multiple_low).replace(".", ","), mhi = String(D.multiple_high).replace(".", ",");
    const LEVEL_CLASS = { "élevé": "high", moyen: "mid", info: "info" };
    panel.innerHTML = `
      <div class="abs card-head" style="left:40px;top:32px;width:860px"><h3>${esc(F.target.name)}</h3>
        <p>Dossier de pré-due diligence · cible synthétique</p></div>
      <div class="abs ddl" style="left:40px;top:132px">Valeur d'entreprise indicative</div>
      <div class="abs evtrack" style="left:40px;top:170px;width:860px"><div class="evfill"></div>
        <div class="evlab lo"></div><div class="evlab hi"></div></div>
      <div class="abs muted evcap" style="left:40px;top:232px;font-size:17px">${mlo}x à ${mhi}x l'EBE de ${eurFR(D.ebe)} (exercice ${D.ebe_year})</div>
      <div class="abs ddl" style="left:40px;top:284px">Montage indicatif · milieu de fourchette</div>
      <div class="abs stackbar" style="left:40px;top:320px;width:860px"><i class="sg1"></i><i class="sg2"></i><i class="sg3"></i></div>
      <div class="abs seglabels" style="left:40px;top:378px;width:860px">
        <span><i class="sq sg1"></i>Dette senior ${eurFR(D.senior_debt)}</span>
        <span><i class="sq sg2"></i>Crédit vendeur ${eurFR(D.vendor_loan)}</span>
        <span><i class="sq sg3"></i>Fonds propres ${eurFR(D.equity)} · ${Math.round(D.equity_share * 100)} %</span></div>
      <div class="abs check cov" style="left:40px;top:424px;font-size:20px">${icon("check")}<span>Couverture du service de la dette : ${multFR(D.coverage)} · ${D.coverage >= D.min_coverage ? "confortable" : "tendue"}</span></div>
      <div class="abs ddl" style="left:40px;top:486px">Signaux factuels</div>
      <div class="abs ddsig" style="left:40px;top:518px;width:860px">${D.signals.slice(0, 3).map((x) =>
        `<span class="ddchip lv-${LEVEL_CLASS[x.level] || "info"}">${esc(x.level)} · ${esc(x.title)}</span>`).join("")}</div>
      <div class="abs ddl qhead" style="left:40px;top:592px">Questions de due diligence · <b class="qn">0</b> questions, ${D.themes} thèmes</div>
      ${D.questions.slice(0, 3).map((q, i) =>
        `<div class="abs qline" style="left:40px;top:${628 + i * 42}px;width:860px"><b class="${D.triggered[i] ? "trig" : ""}">●</b>${esc(q)}</div>`).join("")}`;
    const evFill = panel.querySelector(".evfill"), evLo = panel.querySelector(".evlab.lo"), evHi = panel.querySelector(".evlab.hi");
    const evCap = panel.querySelector(".evcap"), cov = panel.querySelector(".cov"), qHead = panel.querySelector(".qhead");
    const qCount = panel.querySelector(".qn");
    const segs = [...panel.querySelectorAll(".stackbar i")], segLabels = [...panel.querySelectorAll(".seglabels span")];
    const ddSignals = [...panel.querySelectorAll(".ddchip")], qLines = [...panel.querySelectorAll(".qline")];
    const reco = place($("div", "stamp go", sdd.root, `Recommandation : ${esc(D.recommendation)}`), PANEL.x + 520, PANEL.y + 34, {
      transformOrigin: "50% 50%", fontSize: "19px", padding: "11px 18px",
    });
    CUES.push({ t: 42.6, type: "click" }, { t: 42.9, type: "click" }, { t: 43.2, type: "click" },
      { t: 47.4, type: "tick" }, { t: 49.4, type: "tick" }, { t: RECO_T + 0.1, type: "stamp" });

    // ================================================================ S5 · l'IA rédige
    const WIN = { x: 940, y: 140, w: 880, h: 800 };
    const body = F.draft.body;
    const TYPE0 = 44.4, TYPE1 = 50.4, STAMP = 50.9;
    const s5 = scene(T.s5, (t) => {
      const ent = P(t, 42.1, 1.1, E.out5), ex = P(t, 53.2, 0.85, E.in3);
      mail.style.opacity = (P(t, 42.1, 0.5) * (1 - ex)).toFixed(3);
      mail.style.transform = `perspective(1800px) rotateY(${lerp(-24, 0, ent).toFixed(2)}deg) translate(${lerp(180, 0, ent).toFixed(1)}px,${(Math.sin(t * 0.8 + 1) * 5).toFixed(2)}px) scale(${lerp(1, 0.9, ex).toFixed(3)})`;
      const lout = 1 - P(t, 53.0, 0.7, E.in3);
      reveal(s5h1.spans, t, 42.5, 0.07);
      reveal(s5h2.spans, t, 43.1, 0.07);
      reveal(s5sub.spans, t, 43.8, 0.022);
      [s5h1, s5h2, s5sub].forEach((w) => (w.box.style.opacity = lout.toFixed(3)));
      s5checks.forEach((ck, i) => {
        const p = P(t, 45.0 + i * 0.35, 0.6, E.out5);
        ck.style.opacity = (p * lout).toFixed(3);
        ck.style.transform = `translateX(${((1 - p) * -30).toFixed(1)}px)`;
        drawIcon(ck, P(t, 45.1 + i * 0.35, 0.7, E.io3));
      });
      s5flagLabel.style.opacity = (P(t, 47.6, 0.5) * lout).toFixed(3);
      s5chips.forEach((ch, i) => {
        const p = P(t, 47.8 + i * 0.3, 0.6, E.outBack);
        ch.style.opacity = (clamp(p) * lout).toFixed(3);
        ch.style.transform = `scale(${lerp(0.7, 1, p).toFixed(3)})`;
      });
      const subj = F.draft.subject;
      subjEl.textContent = subj.slice(0, Math.round(subj.length * P(t, 43.5, 0.8, E.lin)));
      const n = Math.round(body.length * P(t, TYPE0, TYPE1 - TYPE0, E.lin));
      bodyText.textContent = body.slice(0, n);
      const typing = t > TYPE0 && t < TYPE1 + 0.1;
      caret.style.opacity = typing || Math.floor(t * 2.2) % 2 === 0 ? "1" : "0";
      const sp = P(t, STAMP, 0.45, E.outBack);
      stamp.style.opacity = (clamp(P(t, STAMP, 0.15)) * (1 - ex)).toFixed(3);
      stamp.style.transform = `rotate(-7deg) scale(${lerp(2.3, 1, sp).toFixed(3)})`;
    }, SHIFT);
    const s5h1 = words(s5.root, "L'IA rédige.", "display", 120, 210, { fontSize: "74px" });
    const s5h2 = words(s5.root, "L'humain décide.", "display cyan", 120, 300, { fontSize: "74px" });
    const s5sub = words(s5.root, "Mini-thèse, signaux d'alerte et brouillon d'approche pour chaque cible qualifiée.", "muted", 122, 420, {
      fontSize: "27px", width: "720px", lineHeight: "1.4",
    });
    const s5checks = ["Mini-thèse en trois lignes", "Brouillon d'approche personnalisé", "Le score ne dépend jamais de l'IA"].map((txt, i) =>
      place($("div", "check", s5.root, `${icon("check")}<span>${esc(txt)}</span>`), 124, 548 + i * 58));
    const s5flagLabel = place($("div", "abs muted", s5.root, "SIGNAUX D'ALERTE À VÉRIFIER"), 124, 760, {
      fontSize: "16px", fontWeight: "700", letterSpacing: ".1em",
    });
    const s5chips = F.target.red_flags.slice(0, 2).map((txt, i) =>
      place($("div", "chip amber", s5.root, esc(txt)), 124, 796 + i * 58, { transformOrigin: "0 50%" }));
    const mail = place($("div", "window", s5.root), WIN.x, WIN.y, { width: `${WIN.w}px`, height: `${WIN.h}px`, transformOrigin: "60% 50%" });
    mail.innerHTML = `<div class="bar"><i style="background:#ff6b81"></i><i style="background:#ffb547"></i><i style="background:#2ee6a6"></i>
      <span>Brouillon · ${esc(F.target.name)}</span></div>
      <div class="field"><b>À</b>${esc(F.draft.to)}</div>
      <div class="field"><b>Objet</b><span class="subj"></span></div>
      <div class="body"><span class="txt"></span><span class="caret"></span></div>`;
    const subjEl = mail.querySelector(".subj"), bodyText = mail.querySelector(".txt"), caret = mail.querySelector(".caret");
    const stamp = place($("div", "stamp", s5.root, "À RELIRE · AUCUN ENVOI AUTOMATIQUE"), WIN.x + 380, WIN.y + 690, { transformOrigin: "50% 50%" });
    CUES.push({ t: TYPE0 + SHIFT, type: "type_start" }, { t: TYPE1 + SHIFT, type: "type_end" }, { t: STAMP + 0.12 + SHIFT, type: "stamp" });

    // ================================================================ S6 · dashboard
    const VW = 1320, VH = VW / 1.6, FR = { x: 300, y: 175 }, BAR = 44, s = VW / 1440;
    const toStage = ([x, y]) => [FR.x + x * s, FR.y + BAR + y * s];
    const s6 = scene(T.s6, (t) => {
      const p = P(t, 53.5, 2.2, E.io5), ex = P(t, 63.8, 0.7, E.in3);
      browser.style.opacity = (P(t, 53.5, 0.6) * (1 - ex)).toFixed(3);
      browser.style.transform = `perspective(2200px) rotateX(${lerp(24, 0, p).toFixed(2)}deg) rotateY(${lerp(-28, 0, p).toFixed(2)}deg) rotateZ(${lerp(6, 0, p).toFixed(2)}deg) translateY(${lerp(150, 0, p).toFixed(1)}px) scale(${lerp(0.76, 1, p) * lerp(1, 0.92, ex)})`;
      const hout = 1 - P(t, 63.6, 0.6, E.in3);
      reveal(s6h.spans, t, 54.6, 0.05);
      reveal(s6sub.spans, t, 55.0, 0.03);
      s6h.box.style.opacity = s6sub.box.style.opacity = hout.toFixed(3);
      // états du dashboard : liste des cibles -> filtrée (score ≥ 80) -> fiche ouverte depuis le tableau
      imgB.style.opacity = P(t, 57.4, 0.5, E.io3).toFixed(3);
      const sl = P(t, 59.5, 0.8, E.io5);
      imgA.style.transform = imgB.style.transform = `translateY(${(-VH * sl).toFixed(1)}px)`;
      const zoom = P(t, 60.6, 3.0, E.io3);
      imgC.style.transform = `translateY(${(VH * (1 - sl)).toFixed(1)}px) scale(${lerp(1, 1.18, zoom).toFixed(4)})`;
      // curseur
      const [ax, ay] = toStage(F.layout.slider_from), [bx, by] = toStage(F.layout.slider_to);
      const tabXY = toStage(F.layout.open);
      let cx = 1180, cy = 900;
      const m1 = P(t, 56.0, 0.9, E.io3), drag = P(t, 57.0, 1.0, E.io3), m2 = P(t, 58.7, 0.6, E.io3);
      cx = lerp(lerp(lerp(cx, ax, m1), bx, drag), tabXY[0], m2);
      cy = lerp(lerp(lerp(cy, ay, m1), by, drag), tabXY[1], m2);
      const press = (t > 57.0 && t < 58.1) || (t > 59.25 && t < 59.42) ? 0.86 : 1;
      cursor.style.opacity = (P(t, 55.9, 0.3) * (1 - P(t, 60.0, 0.4))).toFixed(3);
      cursor.style.transform = `translate(${(cx - 4).toFixed(1)}px,${(cy - 3).toFixed(1)}px) scale(${press})`;
      const kp = win(t, 58.1, 59.4, 0.25, 0.4);
      hl.style.opacity = kp.toFixed(3);
      hl.style.boxShadow = `0 0 ${(20 + 25 * Math.sin(t * 7) ** 2).toFixed(0)}px rgba(37,194,245,.65)`;
      co1.style.opacity = win(t, 57.3, 59.3, 0.3, 0.3).toFixed(3);
      co1.style.transform = `translate(${(cx + 36).toFixed(1)}px,${(cy - 78).toFixed(1)}px)`;
      co2.style.opacity = win(t, 58.3, 59.4, 0.3, 0.3).toFixed(3);
      co3.style.opacity = (P(t, 61.0, 0.5) * hout).toFixed(3);
      co3.style.transform = `translateY(${((1 - P(t, 61.0, 0.6, E.out5)) * 20).toFixed(1)}px)`;
    }, SHIFT);
    const s6h = words(s6.root, "Tout le pipeline, en un coup d'œil.", "display center", 0, 44, { fontSize: "54px" });
    const s6sub = words(s6.root, "Chercher, filtrer, ouvrir la fiche complète d'une cible.", "center muted", 0, 118, { fontSize: "25px" });
    const browser = place($("div", "browser", s6.root), FR.x, FR.y, { width: `${VW}px` });
    browser.innerHTML = `<div class="bar"><i style="background:#ff6b81"></i><i style="background:#ffb547"></i><i style="background:#2ee6a6"></i><u>localhost:8501 · pme-radar</u></div>
      <div class="viewport" style="height:${VH}px"><img class="a" src="${A.shots}/screener.png"><img class="b" src="${A.shots}/screener_filtered.png" style="opacity:0"><img class="c" src="${A.shots}/company.png" style="transform-origin:50% 45%"></div>`;
    const imgA = browser.querySelector(".a"), imgB = browser.querySelector(".b"), imgC = browser.querySelector(".c");
    const [kx0, ky0, kx1, ky1] = F.layout.count;
    const KPI = { x0: kx0 - 8, y0: ky0 - 4, x1: kx1 + 8, y1: ky1 + 4 };
    const [hx0, hy0] = toStage([KPI.x0 - 6, KPI.y0 - 6]), [hx1, hy1] = toStage([KPI.x1 + 6, KPI.y1 + 6]);
    const hl = place($("div", "hl", s6.root), hx0, hy0, { width: `${hx1 - hx0}px`, height: `${hy1 - hy0}px`, opacity: 0 });
    const cursor = place($("div", "cursor", s6.root), 0, 0, { transformOrigin: "4px 3px" });
    cursor.innerHTML = `<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 2.5l14 11.2-6.3.9 3.6 7.1-2.9 1.4-3.5-7.2L4 20.4z" fill="#fff" stroke="#0d0d1d" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
    const co1 = place($("div", "callout", s6.root, "Score minimum, recherche, sélections rapides…"), 0, 0, { opacity: 0 });
    const co2 = place($("div", "callout", s6.root, "Liste recalculée à chaque filtre"), hx0, hy1 + 18, { opacity: 0 });
    const co3 = place($("div", "callout", s6.root, "Fiche entreprise : chiffres clés, valorisation, due diligence"), FR.x + VW / 2, FR.y + BAR + VH - 36, { opacity: 0, marginLeft: "-290px", width: "580px", textAlign: "center" });
    CUES.push({ t: 57.0 + SHIFT, type: "click" }, { t: 58.1 + SHIFT, type: "click" }, { t: 59.28 + SHIFT, type: "click" });

    // ================================================================ S7 · confiance
    const TILES = [
      ["gauge", "Score déterministe", "Barèmes en YAML, chaque point est justifié."],
      ["nomail", "Aucun envoi automatique", "Des brouillons, relus par un humain."],
      ["shield", "RGPD dès la conception", "Mention d'opposition, données minimisées."],
      ["data", "Open data, sans clé", "Tourne de bout en bout, gratuitement."],
    ];
    const s7 = scene(T.s7, (t) => {
      const out = 1 - P(t, 70.2, 0.7, E.in3);
      s7.root.style.opacity = out.toFixed(3);
      reveal(s7h.spans, t, 64.1, 0.06);
      tiles.forEach((tl, i) => {
        const p = P(t, 64.6 + i * 0.22, 0.8, E.out5);
        tl.style.opacity = p.toFixed(3);
        tl.style.transform = `translateY(${((1 - p) * 70 + Math.sin(t * 1.1 + i * 1.3) * 4).toFixed(1)}px)`;
        drawIcon(tl, P(t, 64.9 + i * 0.22, 1.0, E.io3));
      });
      stats.forEach((st, i) => {
        const p = P(t, 66.6 + i * 0.3, 0.7, E.out5);
        st.el.style.opacity = p.toFixed(3);
        st.el.style.transform = `translateY(${((1 - p) * 24).toFixed(1)}px)`;
      });
      stats[0].el.querySelector("b").textContent = fr(F.tests * P(t, 66.6, 1.4, E.out3));
    }, SHIFT);
    const s7h = words(s7.root, "Conçu pour la confiance.", "display center", 0, 150, { fontSize: "64px" });
    const tiles = TILES.map(([ic, title, txt], i) =>
      place($("div", "tile", s7.root, `${icon(ic)}<h4>${esc(title)}</h4><p>${esc(txt)}</p>`), 135 + i * 420, 330));
    const statRow = place($("div", "abs", s7.root), 0, 760, {
      left: "0", right: "0", display: "flex", justifyContent: "center", gap: "90px",
    });
    const stats = [
      ["0", "tests automatisés"],
      ["CI", "verte · Python 3.11 à 3.13"],
      ["MIT", "code ouvert"],
    ].map(([b, txt]) => ({ el: $("div", "stat", statRow, `<b>${b}</b>${esc(txt)}`) }));
    CUES.push({ t: 68.0 + SHIFT, type: "tick" });

    // ================================================================ S8 · conclusion
    const s8 = scene(T.s8, (t) => {
      const o = { cx: 960, cy: 375, R: 235 * lerp(0.6, 1, P(t, 70.3, 1.2, E.out5)), alpha: P(t, 70.3, 0.8), t0: 70.3, tSweep: 70.9, qualFrom: 71.6 };
      drawRadar(fx, t, o, blips);
      s8title.forEach((sp, i) => {
        const p = P(t, 71.2 + i * 0.045, 0.85, E.out5);
        sp.style.transform = `translateY(${((1 - p) * 60).toFixed(1)}px)`;
        sp.style.opacity = p.toFixed(3);
      });
      reveal(s8tag.spans, t, 71.9, 0.05);
      const cp = P(t, 72.6, 0.8, E.outBack);
      cta.style.opacity = clamp(cp).toFixed(3);
      cta.style.transform = `translateX(-50%) scale(${lerp(0.8, 1, cp).toFixed(3)})`;
      s8note.style.opacity = P(t, 73.4, 0.8).toFixed(3);
    }, SHIFT);
    const t8 = place($("div", "abs center display letters", s8.root), 0, 665, { fontSize: "120px" });
    const s8title = "pme-radar".split("").map((ch) => $("span", ch === "-" ? "cyan" : "", t8, ch));
    const s8tag = words(s8.root, "Un radar d'origination pour search funds.", "center", 0, 815, { fontSize: "38px", color: "#c9cdf0", fontWeight: "500" });
    const cta = place($("div", "cta", s8.root, esc(F.repo)), 960, 890, { transformOrigin: "50% 50%" });
    const s8note = place($("div", "abs center muted", s8.root, "Démo sur données synthétiques · chiffres du run réel agrégés"), 0, 990, { fontSize: "19px" });
    blips
      .map((b) => ({ b, td: firstPass(b, { tSweep: 70.9 }) }))
      .filter(({ b, td }) => b.q && td > 71.0 && td < 73.6)
      .slice(0, 5)
      .forEach(({ td }) => CUES.push({ t: td + SHIFT, type: "blip" }));

    // transitions sonores
    [6.3, 14.6, 28.9, 41.7, 41.7 + SHIFT, 53.3 + SHIFT, 63.6 + SHIFT, 70.1 + SHIFT].forEach((tt) => CUES.push({ t: tt, type: "whoosh" }));
    CUES.sort((a, b) => a.t - b.t);

    window.CUES = CUES;
    window.DURATION = DURATION;
    window.SECTIONS = {
      groove: [7.2, 63.6 + SHIFT], hats: [15.4, 63.6 + SHIFT], arp: [15.4, 63.6 + SHIFT],
      breath: [63.6 + SHIFT, 70.2 + SHIFT], outro: [70.2 + SHIFT, DURATION],
    };
    window.renderFrame = function (t) {
      drawBg(bg, t);
      fx.setTransform(1, 0, 0, 1, 0, 0);
      fx.clearRect(0, 0, W, H);
      drawCompanies(t);
      for (const sc of SCENES) {
        const on = t >= sc.start && t <= sc.end;
        sc.root.style.display = on ? "block" : "none";
        if (on) sc.update(t - sc.shift);
      }
      brandUpdate(t);
      fade.style.opacity = Math.max(1 - P(t, 0, 0.5), P(t, DURATION - 1.0, 1.0, E.io3)).toFixed(3);
    };
    window.renderFrame(0);
    return { duration: DURATION, cues: CUES.length };
  };
})();
