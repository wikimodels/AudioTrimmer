"use strict";

const canvas = document.getElementById("wave");
const ctx = canvas.getContext("2d");
const PAD = 20, HANDLE_W = 9, MIN_PPX = 0.5;

const state = {
  durMs: 0, sel: [0, 0], pos: 0,
  viewStart: 0, ppx: 0,        // ms per pixel; 0 => fit
  buffer: null, file: null, fileName: null,
  peaks: [], peaksStart: 0, peaksEnd: 0, peaksKey: "",
  ctx_: null, srcNode: null, gain: null,
  playing: false, playStartCtx: 0, playStartMs: 0,
  drag: null, dragOrigin: 0, panStart: 0, moveSelOrigin: null, pressX: 0,
};

const $ = (id) => document.getElementById(id);

function fmt(ms, tenths = true) {
  if (ms < 0) ms = 0;
  const t = Math.floor(ms / 1000), m = Math.floor(t / 60), s = t % 60;
  const base = `${m}:${String(s).padStart(2, "0")}`;
  return tenths ? `${base}.${Math.floor(ms % 1000 / 100)}` : base;
}

function fitPpx() { return state.durMs / Math.max(width() - 2 * PAD, 1); }
function isFit() { return state.ppx && Math.abs(state.ppx - fitPpx()) < 1e-6 && state.viewStart < 1e-6; }
function xAt(ms) { return PAD + (ms - state.viewStart) / state.ppx; }
function msAt(x) { return state.viewStart + (x - PAD) * state.ppx; }
function width() { return canvas.clientWidth; }
function height() { return canvas.clientHeight; }

function resize() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width() * dpr; canvas.height = height() * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (state.durMs && isFit()) state.ppx = fitPpx();
  draw();
  requestPeaks();
}

function setFit() { state.viewStart = 0; state.ppx = fitPpx(); draw(); requestPeaks(); }

function clampView() {
  const span = (width() - 2 * PAD) * state.ppx;
  state.viewStart = Math.max(0, Math.min(state.viewStart, Math.max(0, state.durMs - span)));
}

function zoomAt(anchorMs, factor) {
  const old = state.ppx || fitPpx();
  const next = Math.min(Math.max(old * factor, MIN_PPX), state.durMs / 20);
  state.viewStart = Math.max(0, anchorMs - ((anchorMs - state.viewStart) / old) * next);
  state.ppx = next;
  clampView();
  draw(); requestPeaks();
}

// ---- peaks (computed client-side from the decoded buffer) --------------------

function computePeaks(startMs, endMs, buckets) {
  const b = state.buffer, out = [];
  const sr = b.sampleRate, ch = b.numberOfChannels;
  const s0 = Math.max(0, Math.floor(startMs / 1000 * sr));
  const s1 = Math.min(b.length, Math.ceil(endMs / 1000 * sr) + 1);
  if (s1 <= s0) return out;
  for (let i = 0; i < buckets; i++) {
    const a = s0 + Math.floor((s1 - s0) * i / buckets);
    const z = s0 + Math.ceil((s1 - s0) * (i + 1) / buckets);
    let mn = 0, mx = 0;
    for (let c = 0; c < ch; c++) {
      const d = b.getChannelData(c);
      for (let j = a; j < z; j++) { const v = d[j]; if (v < mn) mn = v; if (v > mx) mx = v; }
    }
    out.push([mn, mx]);
  }
  return out;
}

function requestPeaks() {
  if (!state.buffer) return;
  let start = 0, end = state.durMs;
  if (!isFit()) {
    start = Math.max(0, Math.floor(state.viewStart));
    end = Math.min(state.durMs, Math.ceil(state.viewStart + (width() - 2 * PAD) * state.ppx));
  }
  const key = `${start}:${end}`;
  if (state.peaksKey === key) return;
  clearTimeout(requestPeaks.timer);
  requestPeaks.timer = setTimeout(() => {
    const buckets = Math.max(64, Math.round(width() * 0.5));
    state.peaks = computePeaks(start, end, buckets);
    state.peaksStart = start; state.peaksEnd = end; state.peaksKey = key;
    draw();
  }, 120);
}

// ---- drawing -----------------------------------------------------------------

function draw() {
  const w = width(), h = height();
  ctx.clearRect(0, 0, w, h);
  if (!state.durMs) { drawEmpty(); return; }
  const mid = h / 2, amp = h / 4 - 8;
  const step = rulerStep();
  const first = Math.floor(state.viewStart / step) * step;
  ctx.strokeStyle = "rgba(255,255,255,0.09)";
  ctx.fillStyle = "#8a91a3";
  ctx.font = "8pt Consolas";
  ctx.lineWidth = 1;
  for (let t = first, x = xAt(t); x <= w && t <= state.durMs; t += step, x += step / state.ppx) {
    ctx.beginPath(); ctx.moveTo(Math.round(x) + .5, 0); ctx.lineTo(Math.round(x) + .5, h - 17); ctx.stroke();
    ctx.fillText(fmt(t, false), Math.round(x) - 30, h - 5);
  }
  const [a, b] = state.sel;
  if (b > a) {
    const ax = xAt(a), bx = xAt(b);
    ctx.fillStyle = "rgba(44,58,68,0.55)";
    ctx.fillRect(ax, 0, bx - ax, h - 17);
    ctx.strokeStyle = "#5dd6b0";
    ctx.beginPath();
    ctx.moveTo(Math.round(ax) + .5, 4); ctx.lineTo(Math.round(ax) + .5, h - 17);
    ctx.moveTo(Math.round(bx) + .5, 4); ctx.lineTo(Math.round(bx) + .5, h - 17);
    ctx.stroke();
  }
  paintPeaks(mid, amp, w, h);
  if (b > a) { paintHandle(xAt(a), "l"); paintHandle(xAt(b), "r"); }
  const px = xAt(state.pos);
  if (px >= 0 && px <= w) {
    ctx.strokeStyle = (state.pos > a && state.pos < b) ? "#5dd6b0" : "#ffffff";
    ctx.beginPath(); ctx.moveTo(Math.round(px) + .5, 14); ctx.lineTo(Math.round(px) + .5, h - 17); ctx.stroke();
    ctx.fillStyle = "#ffb347";
    ctx.beginPath();
    ctx.moveTo(px - 5, 2); ctx.lineTo(px + 5, 2); ctx.lineTo(px, 14);
    ctx.fill();
  }
}

function drawEmpty() {
  const w = width(), h = height();
  ctx.fillStyle = "#8a91a3";
  ctx.font = "13px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("Open an audio file or drop it here", w / 2, h / 2);
  ctx.textAlign = "left";
}

function rulerStep() {
  const steps = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 30000, 60000, 120000, 300000, 600000];
  const target = 90 * (state.ppx || fitPpx());
  for (const s of steps) if (s >= target) return s;
  return 600000;
}

function paintPeaks(mid, amp, w, h) {
  if (!state.peaks.length) return;
  const span = state.peaksEnd - state.peaksStart;
  if (span <= 0) return;
  const n = state.peaks.length;
  const loI = Math.max(0, Math.floor(((state.viewStart - state.peaksStart) / span) * n));
  const hiI = Math.min(n, Math.ceil(((state.viewStart + (w - 2 * PAD) * state.ppx - state.peaksStart) / span) * n) + 1);
  const [a, b] = state.sel;
  for (let i = loI; i < hiI; i++) {
    const t0 = state.peaksStart + (i / n) * span;
    const t1 = state.peaksStart + ((i + 1) / n) * span;
    const x0 = xAt(t0), x1 = xAt(t1);
    if (x1 < -2 || x0 > w + 2) continue;
    const bw = Math.max(1.5, x1 - x0);
    const [mn, mx] = state.peaks[i];
    const top = mid - Math.max(mx, -mn) * amp;
    const bot = mid + Math.max(mx, -mn) * amp;
    const inside = t1 > a && t0 < b;
    ctx.fillStyle = inside ? "rgba(93,214,176,0.9)" : "rgba(255,179,71,0.75)";
    ctx.fillRect(x0, top, bw, Math.max(1, bot - top));
  }
}

function paintHandle(x, side) {
  ctx.fillStyle = "#5dd6b0";
  roundRect(x - HANDLE_W / 2, 8, HANDLE_W, 46, 3);
  ctx.fill();
  ctx.fillStyle = "#101216";
  const cy = 8 + 23, th = 6;
  ctx.beginPath();
  if (side === "l") {
    const tip = x - HANDLE_W / 2 + 2.5;
    ctx.moveTo(tip, cy - th / 2); ctx.lineTo(tip, cy + th / 2); ctx.lineTo(tip + th, cy);
  } else {
    const tip = x + HANDLE_W / 2 - 2.5;
    ctx.moveTo(tip, cy - th / 2); ctx.lineTo(tip, cy + th / 2); ctx.lineTo(tip - th, cy);
  }
  ctx.fill();
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// ---- interaction ---------------------------------------------------------------

function hitTest(x) {
  const px = xAt(state.pos);
  if (state.durMs && px >= -2 && px <= width() + 2 && Math.abs(x - px) <= 9) return "pos";
  const [a, b] = state.sel;
  if (b > a) {
    const ax = xAt(a), bx = xAt(b);
    if (Math.abs(x - ax) <= 9) return "sel-l";
    if (Math.abs(x - bx) <= 9) return "sel-r";
    if (x > ax && x < bx) return "move";
  }
  return "seek";
}

canvas.addEventListener("mousedown", (e) => {
  if (!state.durMs) return;
  const x = e.offsetX;
  const mode = hitTest(x);
  state.pressX = x;
  if (mode === "pos") { state.drag = "pos"; canvas.style.cursor = "ew-resize"; return; }
  if (mode === "sel-l" || mode === "sel-r") { state.drag = mode; canvas.style.cursor = "ew-resize"; return; }
  if (mode === "move") {
    state.drag = "move";
    state.moveSelOrigin = [state.sel[0], msAt(x), state.viewStart];
    canvas.style.cursor = "move";
    return;
  }
  if (!isFit()) {
    state.drag = "pan?"; state.dragOrigin = x; state.panStart = state.viewStart;
    canvas.style.cursor = "grabbing";
  }
});

window.addEventListener("mousemove", (e) => {
  const x = e.clientX - canvas.getBoundingClientRect().left;
  if (!state.drag) {
    if (state.durMs) {
      const mode = hitTest(x);
      canvas.style.cursor =
        mode === "sel-l" || mode === "sel-r" || mode === "pos" ? "ew-resize" :
        mode === "move" ? "move" :
        isFit() ? "pointer" : "grab";
    }
    return;
  }
  if (state.drag === "pos") {
    state.pos = Math.max(0, Math.min(Math.round(msAt(x)), state.durMs));
    const now = performance.now();
    if (state.playing && state.buffer && (now - (state.lastSeek || 0)) > 50) {
      state.lastSeek = now;
      seekPlay(state.pos);
    }
    updateTime(); draw();
  } else if (state.drag === "sel-l" || state.drag === "sel-r") {
    let ms = Math.max(0, Math.min(Math.round(msAt(x)), state.durMs));
    const [a, b] = state.sel;
    state.sel = state.drag === "sel-l" ? [Math.min(ms, b - 1), b] : [a, Math.max(ms, a + 1)];
    updateTime(); draw();
  } else if (state.drag === "move" && state.moveSelOrigin) {
    const [origA, anchorMs, viewAtPress] = state.moveSelOrigin;
    if (isFit()) {
      const wlen = state.sel[1] - state.sel[0];
      const na = Math.max(0, Math.min(origA + Math.round(msAt(x)) - anchorMs, state.durMs - wlen));
      state.sel = [na, na + wlen]; updateTime(); draw();
    } else {
      // rigid grab: track + selection stay glued to the cursor
      state.viewStart = Math.max(0, Math.min(anchorMs - (x - PAD) * state.ppx, Math.max(0, state.durMs - (width() - 2 * PAD) * state.ppx)));
      draw(); requestPeaks();
    }
  } else if (state.drag === "pan" || state.drag === "pan?") {
    if (state.drag === "pan?" && Math.abs(x - state.dragOrigin) <= 5) return;
    state.drag = "pan";
    state.viewStart = Math.max(0, Math.min(state.panStart - (x - state.dragOrigin) * state.ppx, state.durMs - (width() - 2 * PAD) * state.ppx));
    draw(); requestPeaks();
  }
  if (state.drag === "sel-l" || state.drag === "sel-r" || state.drag === "move" || state.drag === "pos") edgePan(x);
});

window.addEventListener("mouseup", () => {
  if (state.drag === "pos" && state.playing && state.buffer) seekPlay(state.pos);
  state.drag = null; state.moveSelOrigin = null;
  canvas.style.cursor = "default";
});

canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  if (!state.durMs || e.deltaY === 0) return;
  const raw = e.deltaMode === 1 ? e.deltaY * 20 : e.deltaY;
  const f = Math.pow(1.5, raw / 100);
  zoomAt(msAt(e.offsetX), f);
}, { passive: false });

canvas.addEventListener("dblclick", (e) => {
  if (!state.durMs) return;
  state.sel = [0, state.durMs]; updateTime(); setFit();
});

function edgePan(x) {
  if (isFit()) return;
  const w = width(), edge = 26;
  let n = 0;
  if (x < edge) n = -(1 - x / edge) * 24;
  else if (x > w - edge) n = (1 - (w - x) / edge) * 24;
  if (n) {
    state.viewStart = Math.max(0, Math.min(state.viewStart + n * state.ppx, state.durMs - (w - 2 * PAD) * state.ppx));
    draw(); requestPeaks();
  }
}

// ---- open / playback ------------------------------------------------------------

function ensureAudio() {
  if (!state.ctx_) state.ctx_ = new (window.AudioContext || window.webkitAudioContext)();
  if (state.ctx_.state === "suspended") state.ctx_.resume();
  return state.ctx_;
}

$("openBtn").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (f) await loadFile(f);
  e.target.value = "";
});

async function loadFile(file) {
  stopPlayback();
  showStatus(`Loading ${file.name} …`);
  try {
    const data = await file.arrayBuffer();
    const ac = ensureAudio();
    const buf = await ac.decodeAudioData(data);
    state.buffer = buf;
    state.file = file;
    state.fileName = file.name;
    state.durMs = buf.duration * 1000;
    state.sel = [Math.floor(state.durMs / 3), Math.floor(state.durMs / 3 + state.durMs * 0.2)];
    state.pos = 0; state.peaks = []; state.peaksKey = "";
    $("fileLabel").textContent = `${file.name}   ·   ${(state.durMs / 1000).toFixed(1)}s`;
    setFit();
    updateTime();
    showStatus(`Loaded ${file.name}`);
  } catch (err) {
    showStatus(`Could not load ${file.name}: ${err}`);
  }
}

function seekPlay(ms) {
  if (!state.buffer) return;
  const ac = ensureAudio();
  stopNode();
  const t = ac.currentTime + 0.02;
  const src = ac.createBufferSource();
  src.buffer = state.buffer;
  const g = ac.createGain();
  g.gain.value = ($("volume").value / 100) * 0.9;
  src.connect(g).connect(ac.destination);
  src.start(t, ms / 1000);
  state.srcNode = src; state.gain = g;
  state.playing = true; state.playStartCtx = t; state.playStartMs = ms;
  updateTime(); draw();
}

function stopNode() {
  if (state.srcNode) { try { state.srcNode.stop(); } catch (_) {} state.srcNode.disconnect(); state.srcNode = null; }
  if (state.gain) { state.gain.disconnect(); state.gain = null; }
}

function pausePlayback() {
  if (!state.playing) return;
  state.playing = false;
  const pos = state.pos; stopNode(); state.pos = pos;
}

function stopPlayback() {
  stopNode();
  state.playing = false;
  state.pos = state.playStartMs = state.playStartCtx = 0;
}

$("btnPlay").addEventListener("click", () => {
  if (!state.buffer) return;
  if (state.playing) { pausePlayback(); } else { seekPlay(state.pos); }
});
$("btnPause").addEventListener("click", pausePlayback);
$("btnStop").addEventListener("click", stopPlayback);
$("btnJump").addEventListener("click", () => {
  if (!state.buffer) return;
  const a = state.sel[0];
  state.pos = a;
  if (state.playing) seekPlay(a); else updateTime();
  draw();
});
$("volume").addEventListener("input", () => {
  if (state.gain) state.gain.gain.value = ($("volume").value / 100) * 0.9;
});

// ---- export ----------------------------------------------------------------------

$("export").addEventListener("click", async () => {
  if (!state.buffer) return;
  const [a, b] = state.sel;
  if (b - a < 50) { showStatus("Selection is too short to export."); return; }
  const btn = $("export");
  btn.disabled = true; showStatus(`Exporting ${fmt(a)} – ${fmt(b)} to MP3 (${$("bitrate").value})…`);
  try {
    const fd = new FormData();
    fd.append("file", state.file, state.fileName);
    fd.append("start", String(a));
    fd.append("end", String(b));
    fd.append("bitrate", $("bitrate").value);
    const r = await fetch("/api/export-upload", { method: "POST", body: fd }).then((x) => x.json());
    showStatus(r.ok ? `Saved: ${r.file} (${r.path})` : `Export failed: ${r.error || ""}`);
  } finally { btn.disabled = false; }
});

// ---- settings ----------------------------------------------------------------------

$("gear").addEventListener("click", async () => {
  const r = await fetch("/api/settings").then((x) => x.json());
  $("cfgSource").value = r.source || ""; $("cfgOutput").value = r.output || "";
  $("overlay").classList.remove("hidden");
});
$("closeX").addEventListener("click", () => $("overlay").classList.add("hidden"));
for (const key of ["setSource", "setOutput"]) {
  $(key).addEventListener("click", async () => {
    const field = key === "setSource" ? "source" : "output";
    const val = $(field === "source" ? "cfgSource" : "cfgOutput").value.trim();
    if (!val) return;
    const r = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: val }),
    }).then((x) => x.json());
    showStatus(r.ok ? "Settings saved" : `Settings error: ${r.error || ""}`);
  });
}

// ---- misc --------------------------------------------------------------------------

$("zoomIn").onclick = () => state.durMs && zoomAt(msAt(width() / 2), 1 / 2.2);
$("zoomOut").onclick = () => state.durMs && zoomAt(msAt(width() / 2), 2.2);
$("fit").onclick = () => state.durMs && setFit();

$("btnCenterPos").onclick = () => {
  if (!state.durMs) return;
  state.pos = Math.max(0, Math.min(Math.round(msAt(width() / 2)), state.durMs));
  if (state.playing && state.buffer) seekPlay(state.pos);
  updateTime(); draw();
};
$("btnCenterSel").onclick = () => {
  if (!state.durMs) return;
  const c = msAt(width() / 2);
  const half = 75 * state.ppx;
  const a = Math.max(0, Math.round(c - half));
  const b = Math.max(a + 1, Math.min(state.durMs, Math.round(c + half)));
  state.sel = [a, b];
  updateTime(); draw();
};

window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && state.buffer) {
    e.preventDefault();
    if (state.playing) pausePlayback(); else seekPlay(state.pos);
  }
  if (e.code === "ArrowLeft") { e.preventDefault(); state.pos = Math.max(0, state.pos - 100); if (state.playing) seekPlay(state.pos); updateTime(); draw(); }
  if (e.code === "ArrowRight") { e.preventDefault(); state.pos = Math.min(state.durMs, state.pos + 100); if (state.playing) seekPlay(state.pos); updateTime(); draw(); }
  if (e.code === "Digit0" && e.ctrlKey) { e.preventDefault(); state.durMs && setFit(); }
});

function showStatus(msg) { $("status").textContent = msg; }

function loop() {
  requestAnimationFrame(loop);
  if (!state.playing) { updateTime(); return; }
  const ac = state.ctx_;
  if (!ac) return;
  state.pos = state.playStartMs + (ac.currentTime - state.playStartCtx) * 1000;
  if (state.pos >= state.durMs) { stopPlayback(); }
  updateTime(); draw();
}

function updateTime() {
  const [a, b] = state.sel;
  $("time").textContent = `${fmt(state.pos)} / ${fmt(state.durMs, false)}`;
  $("selTime").textContent = `Selection: ${fmt(a)} – ${fmt(b)}  ·  ${fmt(b - a)}`;
}

window.addEventListener("resize", () => { requestAnimationFrame(resize); });
resize();
loop();