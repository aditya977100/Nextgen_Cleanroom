// Cleanroom dashboard - plain JavaScript, no build step, no framework.
// Reads data/naive.json, data/cleanroom.json, data/slip.json (relative paths, GitHub Pages ready).

var LINKS = { repo: "", video: "" };   // paste your GitHub repo and demo video links here
var MODES = [
  ["naive", "A: Naive shared sandbox", "Naive"],
  ["cleanroom", "B: Cleanroom", "Cleanroom"],
  ["slip", "C: Slip-up mid-run", "Slip-up"]
];
var MODE_META = {
  naive:     { label: "Run A - Naive shared sandbox", short: "Naive" },
  cleanroom: { label: "Run B - Cleanroom",            short: "Cleanroom" },
  slip:      { label: "Run C - Slip-up mid-run",       short: "Slip-up" }
};
var DIARY_LIMIT = 60;      // rows shown at the top; the last 20 are always shown as well
var DIARY_TAIL = 20;

var cache = {}, cur = null, work = null, backup = null, mode = "cleanroom";

function $(i) { return document.getElementById(i); }
function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
function reduceMotion() { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
async function sha(s) {
  var b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(b)).map(function (x) { return x.toString(16).padStart(2, "0"); }).join("");
}

/* ---------------------------------------------------------------- icons */
function svg(inner) {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + inner + "</svg>";
}
var ICON = {
  shield: svg('<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9.5 4.6-1.1 8-4.5 8-9.5V6Z"/><path d="m9 12 2 2 4-4"/>'),
  alert: svg('<path d="M10.3 3.9 2.5 17.4A2 2 0 0 0 4.2 20.4h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 16.5h.01"/>'),
  file: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/>'),
  log: svg('<path d="M4 17l6-6-6-6"/><path d="M12 19h8"/>'),
  lock: svg('<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>'),
  net: svg('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="8.5" y="14" width="7" height="7" rx="1.5"/><path d="M6.5 10v2h11v-2M12 12v2"/>'),
  user: svg('<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>'),
  clock: svg('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
  key: svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 8-8 2 2-1.5 1.5L21 9l-2 2-2-2-1.5 1.5"/>'),
  copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>'),
  link: svg('<path d="M10 13a4 4 0 0 0 5.7.3l2.6-2.6A4 4 0 0 0 12.6 5l-1.5 1.5"/><path d="M14 11a4 4 0 0 0-5.7-.3L5.7 13.3A4 4 0 0 0 11.4 19l1.5-1.5"/>'),
  github: svg('<path d="M9 19c-4 1.3-4-2-6-2.5m12 5v-3.4a3 3 0 0 0-.8-2.3c2.7-.3 5.5-1.3 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.6 11.6 0 0 0-6 0C6.7 3 5.7 3.3 5.7 3.3a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.3 9.8c0 4.6 2.8 5.6 5.5 6a3 3 0 0 0-.8 2.2V22"/>'),
  play: svg('<circle cx="12" cy="12" r="9"/><path d="m10 8.5 6 3.5-6 3.5Z"/>')
};
function channelIcon(name) {
  var n = String(name).toLowerCase();
  if (n.indexOf("file") >= 0) return ICON.file;
  if (n.indexOf("log") >= 0) return ICON.log;
  if (n.indexOf("diary") >= 0) return ICON.lock;
  if (n.indexOf("direct") >= 0) return ICON.net;
  if (n.indexOf("imperson") >= 0) return ICON.user;
  if (n.indexOf("cache") >= 0) return ICON.clock;
  return ICON.shield;
}
function shortMove(name) {
  var n = String(name).toLowerCase();
  if (n.indexOf("shared file") >= 0) return "Shared files";
  if (n.indexOf("logs") >= 0) return "Logs";
  if (n.indexOf("directly to blue") >= 0) return "Direct to blue";
  if (n.indexOf("directly to the model") >= 0) return "Direct to model";
  if (n.indexOf("pretend") >= 0) return "Impersonate";
  if (n.indexOf("diary") >= 0) return "Read diary";
  if (n.indexOf("cache") >= 0) return "Cache timing";
  return String(name).split(" ")[0] + "…";
}

/* ---------------------------------------------------------------- theme */
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
function initTheme() {
  var p = new URLSearchParams(location.search).get("theme");
  if (p === "light" || p === "dark") { applyTheme(p); return; }
  var saved = null;
  try { saved = localStorage.getItem("cleanroom-theme"); } catch (e) { saved = null; }
  if (saved === "light" || saved === "dark") applyTheme(saved);
}
function currentTheme() {
  var a = document.documentElement.getAttribute("data-theme");
  if (a) return a;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}
function toggleTheme() {
  var next = currentTheme() === "light" ? "dark" : "light";
  applyTheme(next);
  try { localStorage.setItem("cleanroom-theme", next); } catch (e) { /* private mode */ }
  $("theme").setAttribute("aria-label", next === "light" ? "Switch to the dark theme" : "Switch to the light theme");
}

/* ---------------------------------------------------------------- data */
async function load(which) {
  if (!cache[which]) {
    var r = await fetch("data/" + which + ".json");
    if (!r.ok) throw new Error("HTTP " + r.status);
    cache[which] = await r.json();
  }
  return cache[which];
}

/* ---------------------------------------------------------------- floor plan */
function planSVG(which) {
  var s = '<svg viewBox="0 0 620 300" role="img" aria-label="Floor plan of the test rooms">';
  s += '<rect x="8" y="8" width="604" height="284" rx="18" fill="none" stroke="var(--line)" stroke-width="1"/>';

  if (which === "naive") {
    s += '<rect class="plan-open" x="24" y="34" width="572" height="238" rx="16"/>';
    s += '<text class="plan-sub" x="40" y="56">one shared sandbox: shared files, shared logs, one model cache</text>';
    s += '<rect class="plan-room red" x="52" y="110" width="140" height="86" rx="12"/>';
    s += '<text class="plan-label" x="122" y="150" text-anchor="middle">Red</text>';
    s += '<text class="plan-sub" x="122" y="168" text-anchor="middle">attack payloads</text>';
    s += '<rect class="plan-room blue" x="240" y="110" width="140" height="86" rx="12"/>';
    s += '<text class="plan-label" x="310" y="150" text-anchor="middle">Blue</text>';
    s += '<text class="plan-sub" x="310" y="168" text-anchor="middle">defense rules</text>';
    s += '<rect class="plan-room" x="428" y="110" width="140" height="86" rx="12"/>';
    s += '<text class="plan-label" x="498" y="150" text-anchor="middle">Model</text>';
    s += '<text class="plan-sub" x="498" y="168" text-anchor="middle">one shared cache</text>';
    s += '<path class="plan-leak" d="M192 138H240M192 168H240"/>';
    s += '<path class="plan-leak" d="M380 138H428M380 168H428"/>';
    s += '<path class="plan-leak" d="M192 196Q310 262 428 196"/>';
    s += '<text class="plan-txt" x="310" y="256" text-anchor="middle" fill="var(--bad)">leaks everywhere</text>';
  } else {
    s += '<rect class="plan-room red" x="24" y="104" width="168" height="96" rx="12"/>';
    s += '<text class="plan-label" x="108" y="146" text-anchor="middle">Red room</text>';
    s += '<text class="plan-sub" x="108" y="164" text-anchor="middle">own files, own logs</text>';
    s += '<rect class="plan-room blue" x="428" y="104" width="168" height="96" rx="12"/>';
    s += '<text class="plan-label" x="512" y="146" text-anchor="middle">Blue room</text>';
    s += '<text class="plan-sub" x="512" y="164" text-anchor="middle">own files, own logs</text>';
    s += '<rect class="plan-room gw" x="250" y="108" width="120" height="88" rx="12"/>';
    s += '<text class="plan-label" x="310" y="146" text-anchor="middle">Gateway</text>';
    s += '<text class="plan-sub" x="310" y="164" text-anchor="middle">the only door</text>';
    s += '<rect class="plan-room" x="250" y="232" width="120" height="52" rx="12"/>';
    s += '<text class="plan-label" x="310" y="256" text-anchor="middle">Model</text>';
    s += '<text class="plan-sub" x="310" y="272" text-anchor="middle">cache per team</text>';
    s += '<path class="plan-link" d="M192 152h58M370 152h58M310 196v36"/>';
    s += '<path class="plan-block" d="M186 58h248" stroke-dasharray="5 5" opacity=".55"/>';
    s += '<circle cx="310" cy="58" r="11" fill="var(--surface)" stroke="var(--bad)" stroke-width="1.4"/>';
    s += '<path d="M305 53l10 10M315 53l-10 10" stroke="var(--bad)" stroke-width="1.6" stroke-linecap="round"/>';
    s += '<text class="plan-sub" x="310" y="40" text-anchor="middle">no route: red never reaches blue</text>';
    if (which === "slip") {
      s += '<path class="plan-vol" d="M192 186Q310 222 428 186"/>';
      s += '<text class="plan-txt" x="310" y="220" text-anchor="middle" fill="var(--bad)">shared volume mounted at finding 5</text>';
    }
  }
  s += "</svg>";
  return s;
}
function planLegend(which) {
  var h = '<span><i></i>leak path</span>';
  if (which !== "naive") h += '<span><i class="acc"></i>allowed path</span><span><i class="solid"></i>sealed wall</span><span><i class="cross"></i>no route</span>';
  return h;
}
function drawPlan(which) {
  $("rooms").innerHTML = planSVG(which) + '<div class="plan-legend">' + planLegend(which) + "</div>";
  var note = $("roomnote");
  if (which === "naive") note.textContent = "One shared sandbox: shared files, shared logs, one model cache, plaintext logs.";
  else if (which === "slip") note.textContent = "Cleanroom until finding 5, then somebody mounts one shared volume into red and blue. The network is still sealed - only the files leak.";
  else note.textContent = "Three internal networks. The gateway is the only door, it identifies callers by their IP address, and the diary stores hashes, never the message text.";
}

/* ---------------------------------------------------------------- diary ledger */
function diary() {
  var t = $("diary"), e = work;
  if (!e.length) {
    t.innerHTML = '<div class="ledger-empty">A naive sandbox keeps no signed diary.</div>';
    $("diarycount").textContent = "no entries";
    return;
  }
  var show = e, note = "";
  if (e.length > DIARY_LIMIT) {
    show = e.slice(0, DIARY_LIMIT).concat(e.slice(-DIARY_TAIL));
    note = '<tr class="ledger-note"><td colspan="6">Showing the first ' + DIARY_LIMIT + " and the last " + DIARY_TAIL +
           " of " + e.length + " entries. Verify still checks every one of them.</td></tr>";
  }
  var rows = show.map(function (x) {
    return '<tr id="r' + x.i + '">' +
      '<td class="c-idx">' + x.i + "</td>" +
      '<td class="c-actor">' + esc(x.actor) + "</td>" +
      "<td>" + esc(x.event) + "</td>" +
      '<td class="c-data">' + esc(x.data) + "</td>" +
      '<td class="c-hash"><span class="hashchip" title="hash ' + esc(x.hash) + '">' + esc(x.hash.slice(0, 10)) + "</span></td>" +
      '<td class="c-prev"><span class="prevcell" title="previous hash ' + esc(x.prev) + '">' + ICON.link + '<span class="hashchip">' + esc(x.prev.slice(0, 10)) + "</span></span></td>" +
      "</tr>";
  }).join("");
  t.innerHTML = "<table><thead><tr><th>#</th><th>Who</th><th>Event</th><th>Details</th><th>Hash</th><th>Previous</th></tr></thead><tbody>" + rows + note + "</tbody></table>";
  $("diarycount").textContent = e.length + " signed entries";
}

/* ---------------------------------------------------------------- count up */
function countUp(el, to, decimals) {
  var text = el.textContent;
  if (reduceMotion()) { el.textContent = decimals ? to.toFixed(decimals) : String(to); return; }
  var from = 0, start = null, dur = 750;
  function step(ts) {
    if (start === null) start = ts;
    var p = Math.min(1, (ts - start) / dur);
    var eased = 1 - Math.pow(1 - p, 3);
    var v = from + (to - from) * eased;
    el.textContent = decimals ? v.toFixed(decimals) : String(Math.round(v));
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
  return text;
}

/* ---------------------------------------------------------------- leak meter */
function logPct(v) {
  if (!v || v <= 0) return 0;
  var t = (Math.log10(v) + 2) / 2;
  return Math.max(0, Math.min(1, t));
}
function keySentence(m) {
  if (m.key_seconds === null || m.key_seconds === undefined) return "no signal: nothing to steal through this channel";
  var s = m.key_seconds;
  var t = s < 90 ? s.toFixed(s < 10 ? 1 : 0) + " seconds" : s < 5400 ? (s / 60).toFixed(1) + " minutes" : (s / 3600).toFixed(1) + " hours";
  return "a 32-character key could be stolen in " + t;
}
function drawMeter(meter) {
  $("meter").innerHTML = meter.map(function (m) {
    var pct = logPct(m.bits_per_use);
    var zero = !m.bits_per_use;
    return '<div class="meter-row">' +
      '<div class="meter-head"><span class="meter-name">' + esc(m.channel) +
        '<span class="meter-tag ' + (m.real ? "real" : "sim") + '">' + (m.real ? "real" : "simulated") + "</span></span>" +
        '<span class="meter-val">' + m.bits_per_use + " bit/use &middot; " + m.bits_per_s + " bit/s</span></div>" +
      '<div class="meter-track"><div class="meter-fill' + (zero ? " zero" : "") + '" data-w="' + (pct * 100).toFixed(1) + '"></div></div>' +
      '<div class="meter-axis"><span>0.01</span><span>0.1</span><span>1 bit / use</span></div>' +
      '<div class="meter-note"><b>' + esc(keySentence(m)) + "</b></div>" +
      "</div>";
  }).join("");
  requestAnimationFrame(function () {
    Array.prototype.forEach.call(document.querySelectorAll(".meter-fill"), function (f) {
      f.style.width = f.dataset.w + "%";
    });
  });
}

/* ---------------------------------------------------------------- findings */
function drawFindings(d) {
  var firstBad = -1;
  d.findings.forEach(function (f, i) { if (f.status === "TAINTED" && firstBad < 0) firstBad = i; });
  var cut = firstBad < 0 ? 100 : (firstBad / d.findings.length) * 100;
  var nodes = d.findings.map(function (f, i) {
    var tainted = f.status === "TAINTED";
    var mark = (i === firstBad) ? '<span class="tl-mark"><span class="mk-full">leak starts here</span><span class="mk-short">leak</span></span>' : "";
    var receipt = f.receipt
      ? '<button class="tl-receipt" type="button" data-copy="' + esc(f.receipt) + '" title="Copy receipt ' + esc(f.receipt) + '">' + ICON.copy + "<span>" + esc(f.receipt) + "</span></button>"
      : '<span class="tl-receipt" title="No receipt: this run keeps no signed diary">no receipt</span>';
    return '<div class="tl-node' + (tainted ? " tainted" : "") + '">' + mark +
      '<span class="tl-dot"></span><div class="tl-card">' +
      '<div class="tl-id">' + esc(f.id) + "</div>" +
      '<div class="tl-text">' + esc(f.text) + "</div>" +
      '<div class="tl-status ' + (tainted ? "t" : "v") + '">' + esc(f.status) + "</div>" +
      receipt + "</div></div>";
  }).join("");
  $("finds").innerHTML = '<div class="tl-rail" style="--cut:' + cut.toFixed(2) + '%"></div>' + nodes;
  var n = d.findings.length, valid = 0;
  d.findings.forEach(function (f) { if (f.status === "VALID") valid++; });
  var fs = $("fsum");
  fs.className = "tl-summary " + (valid === n ? "good" : "bad");
  fs.textContent = valid === n
    ? "All " + n + " findings are trustworthy. Each has a receipt tied to the sealed diary."
    : valid === 0
      ? "All " + n + " findings are tainted. Nothing can be trusted; re-run all " + n + "."
      : valid + " of " + n + " findings are still valid. Re-run only the " + (n - valid) + " tainted ones, not all " + n + ".";
}

/* ---------------------------------------------------------------- mole + channels */
function drawMole(mole) {
  $("molesum").className = "tl-summary " + (mole.landed ? "bad" : "good");
  $("molesum").textContent = "The Mole landed " + mole.landed + " of " + mole.tried + " escape moves.";
  $("moles").innerHTML = mole.moves.map(function (m) {
    return '<div class="chip' + (m.landed ? " landed" : "") + '" title="' + esc(m.name + " - " + m.note) + '">' +
      '<span class="cdot"></span><span class="cname">' + esc(shortMove(m.name)) + "</span>" +
      '<span class="cnote">' + esc(m.note) + "</span></div>";
  }).join("");
}
function drawChannels(channels) {
  $("chans").innerHTML = channels.map(function (c) {
    return '<div class="ch' + (c.leaked ? " leak" : "") + '">' +
      '<span class="ch-ico">' + (c.leaked ? ICON.alert : ICON.shield) + "</span>" +
      "<span><span class=\"ch-name\">" + esc(c.name) + '</span> <span class="ch-state">' + (c.leaked ? "leak" : "clean") + "</span>" +
      '<div class="ch-detail">' + esc(c.detail) + "</div></span></div>";
  }).join("");
}

/* ---------------------------------------------------------------- verdict */
function verdictText(d) {
  var n = d.findings.length, valid = 0, firstBad = -1;
  d.findings.forEach(function (f, i) {
    if (f.status === "VALID") valid++;
    else if (firstBad < 0) firstBad = i;
  });
  if (!d.channels.some(function (c) { return c.leaked; }) && valid === n) {
    return 'The room was clean. <span class="ok">All ' + n + " findings hold.</span>";
  }
  if (valid === 0) {
    return 'Nothing here can be trusted. <span class="bad">All ' + n + " findings are tainted.</span>";
  }
  var a = "F" + (firstBad + 1), b = "F" + n;
  return '<span class="bad">' + a + " to " + b + ' can\'t be trusted.</span> <span class="ok">F1 to F' + firstBad + " still hold.</span>";
}

function fmtStarted(s) {
  var m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return String(s || "");
  var mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return Number(m[3]) + " " + mon + " " + m[1] + ", " + m[4] + ":" + m[5] + " UTC";
}

/* ---------------------------------------------------------------- render a run */
function render(which, d) {
  cur = d; mode = which;
  var meta = MODE_META[which];
  $("runlabel").textContent = meta.label;
  var real = d.engine === "docker";
  $("enginebadge").className = "badge " + (real ? "real" : "sim");
  $("enginetext").textContent = real ? "real Docker containers" : "simulation - rooms are Python objects";
  $("verdict").innerHTML = verdictText(d);
  $("cert").innerHTML = '<div class="hero-cert' + (d.channels.some(function (c) { return c.leaked; }) ? " bad" : "") + '">' +
    '<span class="dot"></span><span>' + esc(d.certificate) + "</span></div>";
  $("meta").innerHTML =
    '<div class="mrow"><dt>Started</dt><dd>' + esc(fmtStarted(d.started)) + "</dd></div>" +
    '<div class="mrow"><dt>First leak</dt><dd>' + (d.first_leak_at === null || d.first_leak_at === undefined ? "none" : "finding F" + d.first_leak_at) + "</dd></div>" +
    '<div class="mrow"><dt>Sealed diary</dt><dd>' + (d.diary && d.diary.entries ? d.diary.entries.length : 0) + " signed entries</dd></div>" +
    '<div class="mrow"><dt>Verifier</dt><dd>' + esc(d.verify && d.verify.reason ? d.verify.reason : "n/a") + "</dd></div>";

  drawPlan(which);
  drawFindings(d);
  drawMeter(d.meter);
  drawMole(d.mole);
  drawChannels(d.channels);
  $("labels").innerHTML =
    '<div class="label-col real"><div class="label-head"><span class="ldot"></span>Real</div><ul>' +
    d.labels.real.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>" +
    '<div class="label-col sim"><div class="label-head"><span class="ldot"></span>Simulated or assumed</div><ul>' +
    d.labels.simulated.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>";

  work = JSON.parse(JSON.stringify(d.diary.entries || []));
  backup = null;
  diary();
  $("vres").className = "verdict idle";
  $("vres").innerHTML = "";
  $("bT").disabled = work.length < 2;
  $("bV").disabled = !work.length;
  $("bU").disabled = true;

  var leaks = d.channels.filter(function (c) { return c.leaked; }).length;
  var valid = d.findings.filter(function (f) { return f.status === "VALID"; }).length;
  var files = d.meter.filter(function (m) { return m.channel.indexOf("Shared files") >= 0; })[0] || d.meter[0];
  countUp($("s-leaks"), leaks, 0);
  $("s-leaks").className = "stat-value num " + (leaks ? "bad" : "good");
  $("s-leaks-sub").textContent = "of " + d.channels.length + " channels checked";
  countUp($("s-valid"), valid, 0);
  $("s-valid").className = "stat-value num " + (valid === d.findings.length ? "good" : "warn");
  $("s-valid-sub").textContent = "of " + d.findings.length + " findings";
  countUp($("s-mole"), d.mole.landed, 0);
  $("s-mole").className = "stat-value num " + (d.mole.landed ? "bad" : "good");
  $("s-mole-sub").textContent = "of " + d.mole.tried + " escape moves";
  countUp($("s-bps"), files ? files.bits_per_s : 0, 1);
  $("s-bps").className = "stat-value num " + (files && files.bits_per_s ? "bad" : "good");
  $("s-bps-sub").textContent = "shared files channel" + (files && !files.real ? " (simulated)" : "");

  Array.prototype.forEach.call($("tabs").children, function (b) {
    b.setAttribute("aria-pressed", b.dataset.mode === which ? "true" : "false");
  });
  if (history.replaceState) history.replaceState(null, "", "#" + which);
}


async function verify() {
  var prev = "0".repeat(64);
  var bar = $("progress"), fill = bar.firstElementChild;
  bar.classList.add("on");
  fill.style.width = "0%";
  $("vres").className = "verdict idle";
  $("vres").innerHTML = "Verifying " + work.length + " entries…";
  for (var i = 0; i < work.length; i++) {
    var e = work[i], h = await sha(e.i + "|" + e.t + "|" + e.actor + "|" + e.event + "|" + e.data + "|" + e.prev);
    if (i % 20 === 0) fill.style.width = ((i / work.length) * 100).toFixed(1) + "%";
    if (e.prev !== prev || h !== e.hash) {
      var row = $("r" + i); if (row) row.className = "broken";
      fill.style.width = "100%";
      bar.classList.remove("on");
      $("vres").className = "verdict bad";
      $("vres").innerHTML = ICON.alert + "<span>TAMPERED at entry " + i + ": the chain is broken, so the record can't be trusted.</span>";
      return;
    }
    prev = e.hash;
  }
  fill.style.width = "100%";
  bar.classList.remove("on");
  $("vres").className = "verdict ok";
  $("vres").innerHTML = ICON.shield + "<span>VALID: " + work.length + " entries, every fingerprint matches.</span>";
}

/* ---------------------------------------------------------------- run switch */
function replay() {
  var items = document.querySelectorAll("#board .reveal");
  Array.prototype.forEach.call(items, function (el) { el.classList.remove("reveal"); });
  void document.body.offsetWidth;
  Array.prototype.forEach.call(items, function (el) { el.classList.add("reveal"); });
}
async function show(which) {
  $("skeleton").hidden = false;
  $("error").hidden = true;
  $("board").hidden = true;
  try {
    var d = await load(which);
    render(which, d);
    $("skeleton").hidden = true;
    $("board").hidden = false;
    replay();
  } catch (err) {
    $("skeleton").hidden = true;
    $("board").hidden = true;
    $("error").hidden = false;
    $("errmsg").innerHTML = 'The file <code>data/' + esc(which) + ".json</code> could not be loaded (" +
      esc(err && err.message ? err.message : "unknown error") + "). Run <code>python -m tester.run_test</code> first, then reload.";
  }
}

/* ---------------------------------------------------------------- wiring */
MODES.forEach(function (m) {
  var b = document.createElement("button");
  b.className = "seg-btn";
  b.type = "button";
  b.dataset.mode = m[0];
  b.setAttribute("aria-pressed", "false");
  b.innerHTML = '<span class="k">' + m[1].split(":")[0] + '</span>' +
    '<span class="lbl-full">' + esc(m[1].split(":").slice(1).join(":").trim()) + "</span>" +
    '<span class="lbl-short">' + esc(m[2]) + "</span>";
  b.onclick = function () { show(m[0]); };
  $("tabs").appendChild(b);
});

$("bT").onclick = function () {
  if (!work || work.length < 2) return;
  backup = work[1].data;
  work[1].data = backup + " (edited)";
  diary();
  $("bU").disabled = false;
  $("vres").className = "verdict idle";
  $("vres").innerHTML = "Entry 1 was edited by hand. Now press Verify diary.";
};
$("bV").onclick = verify;
$("bU").onclick = function () {
  if (backup !== null) { work[1].data = backup; backup = null; }
  diary();
  $("bU").disabled = true;
  $("vres").className = "verdict idle";
  $("vres").innerHTML = "Entry 1 restored. Press Verify diary.";
};
$("theme").onclick = toggleTheme;
$("retry").onclick = function () { cache = {}; show(mode); };

document.addEventListener("click", function (e) {
  var chip = e.target.closest ? e.target.closest(".tl-receipt[data-copy]") : null;
  if (!chip) return;
  var value = chip.dataset.copy;
  var label = chip.querySelector("span");
  var original = label ? label.textContent : "";
  function flash(text, cls) {
    if (label) label.textContent = text;
    chip.classList.add(cls);
    setTimeout(function () {
      if (label) label.textContent = original;
      chip.classList.remove(cls);
    }, 1200);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(function () {
      flash("copied", "copied");
    }).catch(function () {
      flash("blocked", "failed");
    });
  } else {
    flash("blocked", "failed");
  }
});

(function links() {
  var l = [];
  if (LINKS.repo) l.push('<a href="' + esc(LINKS.repo) + '" target="_blank" rel="noopener">' + ICON.github + "GitHub repo</a>");
  if (LINKS.video) l.push('<a href="' + esc(LINKS.video) + '" target="_blank" rel="noopener">' + ICON.play + "Demo video</a>");
  l.push('<a href="simulation.html">' + ICON.play + "Interactive browser model</a>");
  $("links").innerHTML = l.join("");
})();

initTheme();
var startMode = new URLSearchParams(location.search).get("run") || (location.hash || "").replace("#", "");
if (!MODE_META[startMode]) startMode = "cleanroom";
show(startMode);

window.addEventListener("hashchange", function () {
  var m = (location.hash || "").replace("#", "");
  if (MODE_META[m] && m !== mode) show(m);
});
