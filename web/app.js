/* 지능형 기동지원 군사상황 정보판단 프로그램 — 웹 화면 */
"use strict";

let API = (window.API_BASE || "").replace(/\/$/, "");  // resolveApi()가 정함

// ------------------------------------------------------------------ Supabase (공개 읽기 전용)
const SB = () => (window.SUPABASE_URL && window.SUPABASE_ANON_KEY)
  ? { url: window.SUPABASE_URL.replace(/\/$/, ""), key: window.SUPABASE_ANON_KEY } : null;
async function sbGet(path) {
  const s = SB();
  const headers = { apikey: s.key };
  if (!s.key.startsWith("sb_")) headers.Authorization = `Bearer ${s.key}`;  // 예전 JWT 형식 키
  const r = await fetch(`${s.url}/rest/v1/${path}`, { headers });
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}

// 분석 서버(노트북) 찾기: 같은 주소 → Supabase에 적힌 공개 주소 순서
async function resolveApi() {
  if (API) return { ok: true, how: "고정 주소" };
  try {
    const r = await fetch("/api/config", { cache: "no-store" });
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) return { ok: true, how: "같은 주소" };
  } catch (e) { /* 정적 호스팅(Vercel)이면 여기로 */ }
  if (!SB()) return { ok: false, why: "분석 서버 주소를 찾을 수 없습니다 (Supabase 설정 없음)" };
  try {
    const [s] = await sbGet("server_status?id=eq.1&select=*");
    const fresh = s && s.updated_at && Date.now() - Date.parse(s.updated_at) < 3 * 60 * 1000;
    if (s && s.online && s.api_base && fresh) {
      API = s.api_base.replace(/\/$/, "");
      const r = await fetch(API + "/api/config", { cache: "no-store" });
      if (r.ok) return { ok: true, how: "노트북 공개 주소" };
    }
    return { ok: false, why: "분석 서버(노트북)가 꺼져 있습니다", last: s && s.updated_at };
  } catch (e) {
    return { ok: false, why: "분석 서버 상태를 확인하지 못했습니다 (" + e.message + ")" };
  }
}
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const r1 = (x) => Math.round(x * 10) / 10;

const MOB = { 0: ["미확인", "#9e9e9e"], 1: ["기동 가능 (Go)", "#2e7d32"], 2: ["제한적 기동 (Slow-Go)", "#f9a825"], 3: ["기동 불가 (No-Go)", "#c62828"] };
const TRAF = { 0: ["미확인", "#9e9e9e"], 1: ["원활", "#2e7d32"], 2: ["서행", "#f9a825"], 3: ["정체", "#e65100"], 4: ["돌발 의심", "#c62828"] };
const THREAT = ["없음", "주의", "경계", "위험"];
const THREAT_COLOR = ["#2e7d32", "#f9a825", "#e65100", "#c62828"];
const T_ICON = { 0: "⚪", 1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴" };
const M_ICON = { 0: "⚪", 1: "🟢", 2: "🟡", 3: "🔴" };
const TH_ICON = { 0: "⚪", 1: "🟡", 2: "🟠", 3: "🔴" };
const OSM = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const ESRI_IMG = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_LBL = "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;

const S = {
  cfg: null,
  demo: true, seconds: 10, maxc: 6, buffer: 0.3,
  route: { data: null, isr: [], result: null, resultKey: null, fitKey: null },
  area: { cctvs: [], isr: [], result: null, resultKey: null },
};

// ------------------------------------------------------------------ 서버 호출
// 관리자 비밀번호: 이 브라우저 탭에서만 기억 (탭을 닫으면 사라짐)
const adminPass = () => { try { return sessionStorage.getItem("adminPass") || ""; } catch (e) { return ""; } };
const withAdmin = (h = {}) => (adminPass() ? { ...h, "X-Admin-Pass": adminPass() } : h);

async function api(path, body) {
  const opt = body === undefined ? { headers: withAdmin() }
    : { method: "POST", headers: withAdmin({ "Content-Type": "application/json" }), body: JSON.stringify(body) };
  const r = await fetch(API + path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

async function upload(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(API + "/api/upload", { method: "POST", body: fd, headers: withAdmin() });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

function poll(jobId, box, onDone, onErr) {
  const bar = box.querySelector(".bar"), msg = box.querySelector(".msg");
  box.classList.remove("hidden");
  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${jobId}`);
      bar.style.width = `${Math.round((j.progress || 0) * 100)}%`;
      msg.textContent = j.message || "";
      if (j.status === "done") return onDone(j.result);
      if (j.status === "error") return onErr(new Error(j.error));
      setTimeout(tick, 1000);
    } catch (e) { onErr(e); }
  };
  tick();
}

const debounce = (fn, ms = 400) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const media = (u) => (u ? API + u : "");

// ------------------------------------------------------------------ 지도
function makeMap(id) {
  // 페이지를 스크롤할 때 지도가 확대·축소되지 않도록, 지도를 클릭한 뒤에만 휠 확대 허용
  const map = L.map(id, { scrollWheelZoom: false }).setView([37.3, 127.1], 9);
  map.on("click focus", () => map.scrollWheelZoom.enable());
  map.on("mouseout blur", () => map.scrollWheelZoom.disable());
  const m = { map, base: null, overlay: L.layerGroup().addTo(map) };
  setBase(m, "osm");
  return m;
}

function setBase(m, style) {
  if (m.base) m.map.removeLayer(m.base);
  m.map.getContainer().classList.toggle("dark-tiles", style === "dark");
  m.base = style === "sat"
    ? L.layerGroup([
        L.tileLayer(ESRI_IMG, { maxZoom: 19, attribution: "Tiles © Esri — Esri, Maxar, Earthstar Geographics" }),
        L.tileLayer(ESRI_LBL, { maxZoom: 19 }),
      ])
    : L.tileLayer(OSM, { maxZoom: 19, attribution: "© OpenStreetMap contributors" });
  m.base.addTo(m.map);
}

function styleRadios(el, m) {
  const opts = [["osm", "🗺️ 일반 지도"], ["sat", "🛰️ 위성 지도"], ["dark", "🌙 상황판 지도"]];
  el.innerHTML = opts.map(([v, t], i) =>
    `<label><input type="radio" name="st-${el.dataset.map}" value="${v}" ${i === 0 ? "checked" : ""}> ${t}</label>`).join("");
  el.addEventListener("change", (e) => setBase(m, e.target.value));
}

const pin = (color, emoji, size = 28) => L.divIcon({
  className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2],
  html: `<div class="mk" style="background:${color};width:${size}px;height:${size}px">${emoji}</div>`,
});

// ------------------------------------------------------------------ 지리 계산 (서버와 같은 근사식)
function offsetPoint(lat, lon, brg, km) {
  const b = brg * Math.PI / 180;
  return [lat + km * Math.cos(b) / 110.57, lon + km * Math.sin(b) / (111.32 * Math.cos(lat * Math.PI / 180))];
}
function bearingDist(lat1, lon1, lat2, lon2) {
  const dx = (lon2 - lon1) * 111.32 * Math.cos(lat1 * Math.PI / 180), dy = (lat2 - lat1) * 110.57;
  return [((Math.atan2(dx, dy) * 180 / Math.PI) + 360) % 360, Math.hypot(dx, dy)];
}

// ------------------------------------------------------------------ 공통 화면 조각
const kpis = (items) => items.map(([lbl, val, color]) =>
  `<div class="kpi" ${color ? `style="border-left-color:${color}"` : ""}><div class="lbl">${esc(lbl)}</div><div class="val">${val}</div></div>`).join("");

const badge = (text, color, dark) => `<span class="badge" style="background:${color};color:${dark ? "#111" : "#fff"}">${esc(text)}</span>`;

function verdictBox(text, color, mob, when) {
  return `<div class="verdict" style="background:${color};color:${mob === 2 ? "#111" : "#fff"}">
    <span>종합 판단 · ${esc(text)}</span><span class="when">분석 ${esc(when)}</span></div>`;
}

function stepsHtml(cur) {
  return ["① 기동로 설정", "② CCTV·ISR 영상 분석", "③ 상황 판단·보고"].map((n, i) => {
    const k = i + 1, cls = k < cur ? "done" : k === cur ? "active" : "";
    return `<div class="step ${cls}">${n}${k < cur ? " ✓" : ""}</div>`;
  }).join("");
}

function table(head, rows) {
  return `<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => (typeof c === "object" && c && c.html !== undefined ? `<td${c.cls ? ` class="${c.cls}"` : ""}${c.attr || ""}>${c.html}</td>` : `<td>${esc(c)}</td>`)).join("")}</tr>`).join("")}</tbody>`;
}

function itemsTable(items) {
  if (!items || !items.length) return `<p class="hint">탐지된 위협 후보 없음</p>`;
  const keys = Object.keys(items[0]);
  return `<table class="tbl">${table(keys, items.map((i) => keys.map((k) => i[k])))}</table>`;
}

function reportBlock(text, filename) {
  const id = "rep-" + Math.random().toString(36).slice(2, 8);
  setTimeout(() => {
    const dl = document.getElementById(id + "-dl"), cp = document.getElementById(id + "-cp");
    dl && (dl.onclick = () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      a.download = filename; a.click();
    });
    cp && (cp.onclick = () => navigator.clipboard.writeText(text).then(() => (cp.textContent = "✅ 복사됨")));
  });
  return `<pre class="report">${esc(text)}</pre>
    <button class="btn" id="${id}-dl">📥 보고서 내려받기 (.txt)</button> <button class="btn" id="${id}-cp">📋 복사</button>`;
}

function isrRow(t, where) {
  return `<div class="isr-row">
    <div>${t.image ? `<img src="${media(t.image)}" alt="ISR 분석 결과">` : `<p class="hint">이미지 없음</p>`}</div>
    <div><div class="cap" style="font-size:1rem">${badge("위협 " + t.level_name, THREAT_COLOR[t.level], t.level === 1)} <b>${esc(where)}</b> ${esc(t.name)}</div>
      ${itemsTable(t.items)}
      <p class="hint">상자 색: 빨강 위험 / 주황 경계 / 노랑 주의 / 회색 민간. 종류는 AI 추정이며 최종 식별은 사람이 확인합니다.</p></div>
  </div>`;
}

function cctvFigure(c, extra = "") {
  if (!c.image) return `<figure><div class="error">${esc(c.name)}: ${esc(c.error || "영상 수신 실패")}</div></figure>`;
  const lv = c.level ?? 0;
  return `<figure><img src="${media(c.image)}" alt="CCTV 분석 결과">
    <figcaption class="cap">${badge(TRAF[lv][0], TRAF[lv][1], lv === 2)} ${extra}${esc(c.name)} · 차량 ${c.traffic ? c.traffic["평균 차량 수(화면당)"] : "-"}대${c.weather && c.weather !== "시야 양호" ? " · ⚠️ " + esc(c.weather) : ""}</figcaption></figure>`;
}

function showTab(group, name) {
  document.querySelectorAll(`nav[data-group="${group}"] .tab`).forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  const nav = document.querySelector(`nav[data-group="${group}"]`);
  nav.querySelectorAll(".tab").forEach((b) => $("#tab-" + b.dataset.tab).classList.toggle("hidden", b.dataset.tab !== name));
  // 숨겨져 있던 지도는 크기가 0이라 범위 맞춤이 틀어지므로, 탭을 열 때 크기를 다시 재고 범위를 다시 맞춤
  if (group === "main" && name === "history") return loadHistory();
  if (group === "main") setTimeout(() => {
    (name === "route" ? RM : AM).map.invalidateSize();
    if (name === "area") renderArea(true);
    else { S.route.fitKey = null; renderRoute(); }
  }, 50);
}

// ------------------------------------------------------------------ 설정(사이드바)
function readSettings() {
  S.demo = $("#demo").checked;
  S.seconds = +$("#seconds").value; S.maxc = +$("#maxc").value; S.buffer = +$("#buffer").value;
  $("#seconds-v").textContent = S.seconds; $("#maxc-v").textContent = S.maxc; $("#buffer-v").textContent = S.buffer;
  $("#seconds-hint").textContent = S.seconds < 10 ? "⚠️ 10초 미만이면 돌발상황(8초 이상 정차)을 판단할 수 없습니다." : "";
  $("#live-warn").classList.toggle("hidden", S.demo);
  const b = $("#banner");
  if (S.replay) {  // 녹화 시연 배너 유지
    b.className = "cls-banner";
    b.style.cssText = "background:var(--info-bg);color:var(--info-fg);border-color:var(--info-line)";
    b.textContent = `녹화된 시연 · ${S.replayAt} 실제 분석 결과 재생 (분석 서버 없이 동작)`;
    return;
  }
  b.className = "cls-banner" + (S.demo ? " demo" : "");
  b.textContent = S.demo ? "시연 모드 · 실제 CCTV 일부 + 공개 샘플 영상 · 훈련·교육용" : "실시간 · 공개 도로 CCTV(국가교통정보센터) 기반 · 훈련·교육용";
}

function renderSidebar(usage) {
  const c = S.cfg;
  $("#api-usage").innerHTML = c.has_key
    ? `📊 이번 달 ITS API 호출: <b>${(usage ?? c.api_usage).toLocaleString()} / ${c.api_limit.toLocaleString()}건</b>`
    : "ITS 인증키 없음 (시연 모드만 사용)";
  const oldest = c.saved_real.map((s) => s.saved_at).sort()[0] || "-";
  $("#saved-info").textContent = `💾 시연용 실제 CCTV ${c.saved_real.length}개 저장됨 (가장 오래된 저장: ${oldest})`;
}

// ================================================================== 기동로 분석
let RM;
// 출발·도착점: 목록의 지명 또는 직접 입력한 좌표 (위도·경도 칸이 기준)
const CUSTOM_PT = "__custom";
const ptOf = (k) => [+$(`#${k}-lat`).value, +$(`#${k}-lon`).value];
const startPt = () => ptOf("start");
const endPt = () => ptOf("end");
const ptName = (k) => $(`#${k}`).value === CUSTOM_PT ? `지정 지점(${ptOf(k).map((v) => v.toFixed(3)).join(", ")})` : $(`#${k}`).value;
// 목록에서 지명을 고르면 좌표 칸을 채움
function setRoutePlace(k, name) {
  const p = S.cfg.places[name];
  $(`#${k}`).value = p ? name : CUSTOM_PT;
  if (p) { $(`#${k}-lat`).value = p[0]; $(`#${k}-lon`).value = p[1]; }
}
// 입력한 출발·도착점이 아직 반영되지 않았음을 단추에 표시
function routePending(on) {
  $("#route-apply").classList.toggle("primary", on);
  $("#route-apply-hint").textContent = on ? "⚠️ 입력한 출발·도착점이 아직 반영되지 않았습니다. 단추나 Enter를 누르세요."
    : "목록에서 고르거나 위도·경도를 직접 입력한 뒤 이 단추나 Enter를 누르세요.";
}
async function applyRoute() {
  if (S.replay) return;
  const bad = ["start", "end"].find((k) => { const [la, lo] = ptOf(k); return !(la >= 33 && la <= 39 && lo >= 124 && lo <= 132); });
  if (bad) return alert(`${bad === "start" ? "출발점" : "도착점"} 좌표를 위도 33~39, 경도 124~132 범위(대한민국)로 입력하세요.`);
  const b = $("#route-apply"); b.disabled = true; b.textContent = "⏳ 경로·CCTV 찾는 중…";
  try { await loadRoute(); } finally { b.disabled = false; b.textContent = "🧭 기동로 반영 (경로·CCTV 다시 찾기)"; }
}

function routeReq(extra = {}) {
  return Object.assign({
    start: startPt(), end: endPt(), start_name: ptName("start"), end_name: ptName("end"),
    buffer_km: S.buffer, max_cctvs: S.maxc, seconds: S.seconds, demo: S.demo, isr: S.route.isr,
  }, extra);
}
const routeKey = () => JSON.stringify([startPt(), endPt(), S.buffer, S.maxc, S.demo, S.route.isr.map((i) => i.id)]);

async function loadRoute() {
  if (S.replay) return;  // 녹화 시연: 서버 호출 없음
  $("#route-error").classList.add("hidden");
  routePending(false);
  if (JSON.stringify(startPt()) === JSON.stringify(endPt())) {
    $("#route-error").textContent = "출발점과 도착점이 같습니다."; $("#route-error").classList.remove("hidden"); return;
  }
  try {
    const d = await api("/api/route", routeReq());
    S.route.data = d;
    if (d.error) { $("#route-error").textContent = "CCTV 조회 실패: " + d.error + " — 왼쪽에서 시연 모드를 켜면 API 없이 볼 수 있습니다."; $("#route-error").classList.remove("hidden"); }
    renderSidebar(d.api_usage);
    const km = $("#route-isr-km");
    km.max = Math.ceil(d.route.total_km);
    if (+km.value === 0 || +km.value > +km.max) km.value = Math.round(d.route.total_km / 2);
    $("#route-isr-km-v").textContent = km.value;
  } catch (e) {
    $("#route-error").textContent = "경로 조회 실패: " + e.message; $("#route-error").classList.remove("hidden");
  }
  renderRoute();
}

function routeIsrPos() {
  const d = S.route.data;
  if (!d) return [];
  const total = d.route.total_km;
  return S.route.isr.map((it) => ({ ...it, km: it.ratio != null ? total * it.ratio : Math.min(it.km ?? 0, total) }))
    .sort((a, b) => a.km - b.km);
}

function pointAt(coords, km) {
  // 경로 좌표를 따라 km 지점 (지도 표시용 근사)
  let acc = 0;
  for (let i = 1; i < coords.length; i++) {
    const [a, b] = [coords[i - 1], coords[i]];
    const seg = Math.hypot((b[1] - a[1]) * 111.32 * Math.cos(a[0] * Math.PI / 180), (b[0] - a[0]) * 110.57);
    if (acc + seg >= km) { const f = seg ? (km - acc) / seg : 0; return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]; }
    acc += seg;
  }
  return coords[coords.length - 1];
}

function renderRoute() {
  const d = S.route.data;
  const res = S.route.resultKey === routeKey() ? S.route.result : null;
  const isrs = routeIsrPos();
  $("#route-isr-count").textContent = isrs.length;
  $("#route-isr-table").innerHTML = isrs.length
    ? table(["위치(km)", "ISR 영상", "형식", ""], isrs.map((i) => [r1(i.km), { html: isrThumb(i.source) + esc(i.name) }, IMAGE_EXT.test(i.source) ? "사진" : "동영상",
        { html: "✕", cls: "x", attr: ` data-del="${esc(i.id)}" title="삭제"` }]))
    : `<tbody><tr><td class="hint">ISR·UAV 영상이 없습니다. 오른쪽에서 사진·영상을 올리고 기동로 위 위치를 지정하세요.</td></tr></tbody>`;
  if (!d) return;

  const picks = d.cctvs.filter((c) => c.picked);
  const segs = res ? res.segments : null;
  const camRes = {}, thrRes = {};
  (segs || []).forEach((s) => { if (s.cctv) camRes[s.cctv.id] = s.cctv; s.threats.forEach((t) => (thrRes[t.id] = t)); });

  $("#route-steps").innerHTML = stepsHtml(res ? 3 : picks.length || isrs.length ? 2 : 1);
  const maxThreat = res ? Math.max(0, ...Object.values(thrRes).map((t) => t.level)) : 0;
  const nogo = segs ? segs.filter((s) => s.mobility === 3).length : null;
  $("#route-kpis").innerHTML = kpis([
    ["기동로 거리", `${r1(d.route.distance_km)} <small>km</small>`],
    ["평시 예상 시간", d.route.duration_min ? `${Math.round(d.route.duration_min)} <small>분</small>` : "-"],
    ["분석 CCTV", `${picks.length} <small>/ ${d.cctvs.length}개</small>`],
    ["ISR 위협", res ? `${THREAT[maxThreat]} <small>${isrs.length}건</small>` : `${isrs.length} <small>건 대기</small>`, res ? THREAT_COLOR[maxThreat] : null],
    ["기동 불가 구간", res ? `${nogo} <small>개</small>` : "<small>분석 전</small>", res ? res.verdict.color : "#455a64"],
  ]);
  $("#route-verdict").innerHTML = res ? verdictBox(res.verdict.text, res.verdict.color, res.verdict.mobility, res.time) : "";
  $("#route-detour").innerHTML = res && res.detour
    ? `<div class="verdict detour" style="font-size:1rem"><span>↪ 우회로 건의 · ${Math.round(res.detour.distance_km)}km, 예상 ${Math.round(res.detour.duration_min)}분${res.detour.delta_min != null ? ` (현 경로 대비 ${res.detour.delta_min >= 0 ? "+" : ""}${Math.round(res.detour.delta_min)}분)` : ""} · 위협 지점 2km 이상 회피 · 지도에 보라색 점선</span></div>` : "";

  // 구간 띠
  const total = Math.max(d.route.total_km, 0.1), pct = (k) => Math.min(Math.max(k / total * 100, 0), 100).toFixed(2);
  const parts = segs
    ? segs.map((s) => `<div class="seg" title="${r1(s.from_km)}~${r1(s.to_km)}km ${esc(s.mobility_label)}" style="width:${((s.to_km - s.from_km) / total * 100).toFixed(2)}%;background:${s.mobility_color}"></div>`).join("")
    : `<div class="seg" style="width:100%;background:#37474f"></div>`;
  const cams = picks.map((c) => `<div class="cam" style="left:${pct(c.along_km)}%">📹</div>`).join("");
  const isrMk = isrs.map((i) => { const t = thrRes[i.id]; return `<div class="isr" style="left:${pct(i.km)}%">${t && t.level >= 2 ? "⚠️" : "🛰️"}</div>`; }).join("");
  $("#route-strip").innerHTML = `<div class="strip-wrap"><div class="strip-title">기동로 구간별 기동 가능성 (출발 → 도착 · 📹 CCTV · 🛰️/⚠️ ISR 위협 지점)</div>
    <div class="strip">${parts}${cams}${isrMk}</div>
    <div class="strip-axis"><span>▶ ${esc(ptName("start"))} 0km</span><span>${Math.round(total * .25)}km</span><span>${Math.round(total * .5)}km</span><span>${Math.round(total * .75)}km</span><span>${esc(ptName("end"))} ${Math.round(total)}km ⚑</span></div>
    <div class="legend">${Object.values(MOB).map(([n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join("")}</div></div>`;

  // 지도
  const ov = RM.overlay; ov.clearLayers();
  if (res && res.detour) L.polyline(res.detour.coords, { color: "#7e57c2", weight: 6, opacity: .95, dashArray: "10,8" })
    .bindTooltip(`우회로 ${Math.round(res.detour.distance_km)}km / ${Math.round(res.detour.duration_min)}분`).addTo(ov);
  if (segs) segs.forEach((s) => L.polyline(s.coords, { color: s.mobility_color, weight: 8, opacity: .9 })
    .bindTooltip(`${r1(s.from_km)}~${r1(s.to_km)}km ${s.mobility_label}`).addTo(ov));
  else L.polyline(d.route.coords, { color: "#4a90d9", weight: 6, opacity: .85 }).bindTooltip("기동로").addTo(ov);
  d.cctvs.filter((c) => !c.picked).forEach((c) => L.circleMarker([c.lat, c.lon], { radius: 3, color: "#78909c" }).bindTooltip(c.name).addTo(ov));
  picks.forEach((c) => {
    const r = camRes[c.id], lv = r ? r.level ?? 0 : null;
    L.marker([c.lat, c.lon], { icon: pin(lv != null ? TRAF[lv][1] : "#1e88e5", "📹") })
      .bindTooltip(`📹 ${c.name} (${r1(c.along_km)}km)${r ? " · 교통 " + TRAF[lv][0] : ""}`).addTo(ov);
  });
  isrs.forEach((i) => {
    const t = thrRes[i.id], p = t ? [t.lat, t.lon] : pointAt(d.route.coords, i.km);
    L.marker(p, { icon: pin(t ? THREAT_COLOR[t.level] : "#5f9ea0", t && t.level >= 2 ? "⚠️" : "🛰️") })
      .bindTooltip(`🛰️ ${i.name} (${r1(i.km)}km)${t ? ` · 위협 ${t.level_name}: ${t.summary}` : " · 분석 전"}`).addTo(ov);
    if (t && t.level >= 3) L.circle(p, { radius: 2000, color: "#c62828", fillOpacity: .12 }).bindTooltip("위협 지점 반경 2km").addTo(ov);
  });
  L.marker(d.route.coords[0], { icon: pin("#111", "▶") }).bindTooltip("출발: " + ptName("start")).addTo(ov);
  L.marker(d.route.coords[d.route.coords.length - 1], { icon: pin("#111", "⚑") }).bindTooltip("도착: " + ptName("end")).addTo(ov);
  const fitKey = JSON.stringify([startPt(), endPt(), !!(res && res.detour)]);
  if (S.route.fitKey !== fitKey) {
    RM.map.fitBounds(L.latLngBounds(d.route.coords.concat(res && res.detour ? res.detour.coords : [])), { padding: [20, 20] });
    S.route.fitKey = fitKey;
  }

  // 분석 대상 표
  const rows = picks.map((c) => { const r = camRes[c.id]; return [r1(c.along_km), "📹 CCTV", c.name, r ? `${T_ICON[r.level ?? 0]} ${TRAF[r.level ?? 0][0]}` : "⏳ 대기"]; })
    .concat(isrs.map((i) => { const t = thrRes[i.id]; return [r1(i.km), "🛰️ ISR", i.name, t ? `${TH_ICON[t.level]} ${t.level_name}` : "⏳ 대기"]; }))
    .sort((a, b) => a[0] - b[0]);
  $("#route-targets").innerHTML = table(["위치(km)", "구분", "이름", "결과"], rows);
  $("#route-run").textContent = `▶ 분석 시작 (CCTV ${picks.length} · ISR ${isrs.length})`;
  $("#route-run").disabled = !(picks.length || isrs.length);
  if (S.replay) { $("#route-run").disabled = true; $("#route-run").textContent = "녹화된 시연 (새 분석은 분석 서버 필요)"; }
  $("#route-save-demo").classList.toggle("hidden", S.demo || !picks.length);

  // 결과
  $("#route-results").classList.toggle("hidden", !res);
  if (!res) return;
  const threats = segs.flatMap((s) => s.threats).sort((a, b) => a.along_km - b.along_km);
  $("#tab-r-isr").innerHTML = threats.length ? threats.map((t) => isrRow(t, `${Math.round(t.along_km)}km`)).join("") : `<p class="hint">분석한 ISR·UAV 영상이 없습니다.</p>`;
  $("#tab-r-cam").innerHTML = `<div class="gallery">${segs.filter((s) => s.cctv).map((s) => cctvFigure(s.cctv, `<b>${Math.round(s.from_km)}~${Math.round(s.to_km)}km</b> `)).join("")}</div>`;
  $("#tab-r-seg").innerHTML = `<table class="tbl">${table(["구간(km)", "기동 가능성", "교통", "ISR 위협", "CCTV", "기상·시야"],
    segs.map((s) => [`${Math.round(s.from_km)}~${Math.round(s.to_km)}`, `${M_ICON[s.mobility]} ${s.mobility_label}`,
      `${T_ICON[s.traffic_level]} ${s.traffic_label}`, s.threats.length ? s.threats.map((t) => `${t.level_name}(${t.summary})`).join(", ") : "-",
      s.cctv ? s.cctv.name : "-", s.cctv ? s.cctv.weather || "-" : "-"]))}</table>
    <p class="hint">기동 불가(No-Go): 돌발상황 또는 위협 '위험' / 제한적 기동(Slow-Go): 서행·정체 또는 위협 주의·경계 / 기동 가능(Go): 원활하고 위협 없음</p>`;
  $("#tab-r-rep").innerHTML = reportBlock(res.report, `기동로_군사상황보고_${res.time.replace(/[-: ]/g, "").slice(0, 12)}.txt`);
}

function runRoute() {
  if (S.replay) return;
  const btn = $("#route-run"), key = routeKey();
  btn.disabled = true;
  api("/api/jobs/route", routeReq()).then(({ job_id }) => poll(job_id, $("#route-progress"), (res) => {
    S.route.result = res; S.route.resultKey = key; btn.disabled = false;
    $("#route-progress").classList.add("hidden"); $("#route-isr-panel").open = false;
    renderRoute(); refreshUsage();
  }, (e) => { btn.disabled = false; $("#route-progress .msg").textContent = "분석 실패: " + e.message; }))
    .catch((e) => { btn.disabled = false; alert("분석 시작 실패: " + e.message); });
}

// ================================================================== 지점 주변 분석
let AM;
const areaPt = () => [+$("#area-lat").value, +$("#area-lon").value];
const areaRadius = () => +$("#area-radius").value;
const areaKey = () => JSON.stringify([areaPt().map((v) => v.toFixed(4)), areaRadius(), S.demo, areaIsrPos().map((i) => i.id), S.area.cctvs.map((c) => c.id)]);

function areaIsrPos() {
  const [lat, lon] = areaPt();
  return S.area.isr.map((it) => {
    const p = it.lat != null ? [it.lat, it.lon] : offsetPoint(lat, lon, it.bearing, it.dist_km);
    const [brg, dist] = bearingDist(lat, lon, p[0], p[1]);
    return { ...it, plat: p[0], plon: p[1], brg, dist };
  }).filter((i) => i.dist <= areaRadius()).sort((a, b) => a.dist - b.dist);
}

// 지점 입력이 아직 반영되지 않았음을 단추에 표시
function areaPending(on) {
  $("#area-apply").classList.toggle("primary", on);
  $("#area-apply-hint").textContent = on ? "⚠️ 입력한 지점이 아직 반영되지 않았습니다. 단추나 Enter를 누르세요." : "위도·경도를 고친 뒤 이 단추나 Enter를 누르세요.";
}

async function applyArea() {
  if (S.replay) return;
  const lat = +$("#area-lat").value, lon = +$("#area-lon").value;
  if (!(lat >= 33 && lat <= 39 && lon >= 124 && lon <= 132)) return alert("위도 33~39, 경도 124~132 범위(대한민국)로 입력하세요.");
  const b = $("#area-apply"); b.disabled = true; b.textContent = "⏳ 주변 CCTV 찾는 중…";
  try { await loadArea(); } finally { b.disabled = false; b.textContent = "📍 지점 반영 (주변 CCTV 다시 찾기)"; }
}

async function loadArea() {
  if (S.replay) return;
  areaPending(false);
  $("#area-error").classList.add("hidden");
  const [lat, lon] = areaPt();
  try {
    const d = await api("/api/nearby", { lat, lon, radius: areaRadius(), demo: S.demo });
    S.area.cctvs = d.cctvs;
    if (d.error) { $("#area-error").textContent = "CCTV 조회 실패: " + d.error; $("#area-error").classList.remove("hidden"); }
    renderSidebar(d.api_usage);
  } catch (e) {
    $("#area-error").textContent = "CCTV 조회 실패: " + e.message; $("#area-error").classList.remove("hidden");
  }
  renderArea(true);
}

function renderArea(refit = false) {
  const [lat, lon] = areaPt(), radius = areaRadius();
  const res = S.area.resultKey === areaKey() ? S.area.result : null;
  const isrs = areaIsrPos(), cctvs = S.area.cctvs;
  const camRes = {}, thrRes = {};
  if (res) { res.cctvs.forEach((c) => (camRes[c.id] = c)); res.isr.forEach((t) => (thrRes[t.id] = t)); }
  const a = res ? res.assessment : null;

  $("#area-isr-count").textContent = isrs.length;
  $("#area-isr-table").innerHTML = isrs.length
    ? table(["방위(°)", "거리(km)", "ISR 영상", ""], isrs.map((i) => [String(Math.round(i.brg)).padStart(3, "0"), r1(i.dist), { html: isrThumb(i.source) + esc(i.name) },
        { html: "✕", cls: "x", attr: ` data-del="${esc(i.id)}" title="삭제"` }]))
    : `<tbody><tr><td class="hint">반경 안에 ISR·UAV 영상이 없습니다. 오른쪽에서 올리고 방위·거리를 지정하세요.</td></tr></tbody>`;

  const place = $("#area-place").value === "__custom" ? "지정 지점" : $("#area-place").value;
  $("#area-kpis").innerHTML = kpis([
    ["기준 지점", esc(place)],
    ["반경 안 CCTV", `${cctvs.length} <small>개</small>`],
    ["반경 안 ISR", `${isrs.length} <small>건</small>`],
    ["교통 (최악)", a ? TRAF[a.traffic][0] : "<small>분석 전</small>", a ? TRAF[a.traffic][1] : null],
    ["ISR 위협 (최고)", a ? THREAT[a.threat] : "<small>분석 전</small>", a ? THREAT_COLOR[a.threat] : null],
  ]);
  $("#area-verdict").innerHTML = a ? verdictBox(a.text, a.color, a.mobility, res.time) : "";

  const ov = AM.overlay; ov.clearLayers();
  L.circle([lat, lon], { radius: radius * 1000, color: a ? a.color : "#4a90d9", weight: 3, fillOpacity: .08 }).bindTooltip(`분석 반경 ${radius}km`).addTo(ov);
  L.marker([lat, lon], { icon: pin("#111", "⌖") }).bindTooltip("기준 지점: " + place).addTo(ov);
  cctvs.forEach((c) => {
    const r = camRes[c.id], lv = r && r.level != null ? r.level : null;
    L.marker([c.lat, c.lon], { icon: pin(lv != null ? TRAF[lv][1] : "#1e88e5", "📹") })
      .bindTooltip(`📹 ${c.name} (${r1(c.distance_km)}km)${lv != null ? " · 교통 " + TRAF[lv][0] : ""}`).addTo(ov);
  });
  isrs.forEach((i) => {
    const t = thrRes[i.id];
    L.marker([i.plat, i.plon], { icon: pin(t ? THREAT_COLOR[t.level] : "#5f9ea0", t && t.level >= 2 ? "⚠️" : "🛰️") })
      .bindTooltip(`🛰️ ${i.name} · 방위 ${String(Math.round(i.brg)).padStart(3, "0")}° ${r1(i.dist)}km${t ? ` · 위협 ${t.level_name}: ${t.summary}` : " · 분석 전"}`).addTo(ov);
    if (t && t.level >= 2) L.polyline([[lat, lon], [i.plat, i.plon]], { color: THREAT_COLOR[t.level], weight: 2, dashArray: "6,6" }).addTo(ov);
    if (t && t.level >= 3) L.circle([i.plat, i.plon], { radius: 500, color: "#c62828", fillOpacity: .15 }).bindTooltip("위협 지점 반경 500m").addTo(ov);
  });
  if (refit) AM.map.fitBounds(L.latLng(lat, lon).toBounds(radius * 2200));

  const rows = cctvs.map((c) => { const r = camRes[c.id]; const [b] = bearingDist(lat, lon, c.lat, c.lon);
    return ["📹 CCTV", `${String(Math.round(b)).padStart(3, "0")}° ${r1(c.distance_km)}km`, c.name, r ? (r.level != null ? `${T_ICON[r.level]} ${TRAF[r.level][0]}` : "❌ 실패") : "⏳ 대기"]; })
    .concat(isrs.map((i) => { const t = thrRes[i.id];
      return ["🛰️ ISR", `${String(Math.round(i.brg)).padStart(3, "0")}° ${r1(i.dist)}km`, i.name, t ? `${TH_ICON[t.level]} ${t.level_name}` : "⏳ 대기"]; }));
  $("#area-targets").innerHTML = rows.length ? table(["구분", "방위·거리", "이름", "결과"], rows)
    : `<tbody><tr><td class="hint">반경 안에 CCTV와 ISR 영상이 없습니다. 반경을 넓히거나 ISR 영상을 추가하세요.</td></tr></tbody>`;
  $("#area-run").textContent = `▶ 주변 융합 분석 (CCTV ${cctvs.length} · ISR ${isrs.length})`;
  $("#area-run").disabled = !rows.length;
  if (S.replay) { $("#area-run").disabled = true; $("#area-run").textContent = "녹화된 시연 (새 분석은 분석 서버 필요)"; }

  $("#area-results").classList.toggle("hidden", !res);
  if (!res) return;
  $("#tab-a-isr").innerHTML = res.isr.length
    ? res.isr.slice().sort((x, y) => x.dist_km - y.dist_km).map((t) => isrRow(t, `방위 ${String(Math.round(t.bearing)).padStart(3, "0")}° ${r1(t.dist_km)}km`)).join("")
    : `<p class="hint">분석한 ISR·UAV 영상이 없습니다.</p>`;
  $("#tab-a-cam").innerHTML = `<div class="gallery">${res.cctvs.slice().sort((x, y) => x.distance_km - y.distance_km).map((c) => cctvFigure(c, `(${r1(c.distance_km)}km) `)).join("")}</div>`;
  $("#tab-a-rep").innerHTML = reportBlock(res.report, `지점주변_군사상황보고_${res.time.replace(/[-: ]/g, "").slice(0, 12)}.txt`);
}

function runArea() {
  if (S.replay) return;
  const btn = $("#area-run"), key = areaKey();
  const [lat, lon] = areaPt();
  const place = $("#area-place").value === "__custom" ? "지정 지점" : $("#area-place").value;
  btn.disabled = true;
  api("/api/jobs/area", { lat, lon, radius: areaRadius(), place, seconds: S.seconds, demo: S.demo, isr: S.area.isr })
    .then(({ job_id }) => poll(job_id, $("#area-progress"), (res) => {
      S.area.result = res; S.area.resultKey = key; btn.disabled = false;
      $("#area-progress").classList.add("hidden"); $("#area-isr-panel").open = false;
      renderArea(); refreshUsage();
    }, (e) => { btn.disabled = false; $("#area-progress .msg").textContent = "분석 실패: " + e.message; }))
    .catch((e) => { btn.disabled = false; alert("분석 시작 실패: " + e.message); });
}

// ================================================================== 분석 기록 (Supabase)
async function fetchHistory() {
  // Supabase를 직접 읽음 (노트북 서버가 꺼져 있어도 기록은 보임). 설정이 없으면 서버를 통해 읽음.
  if (SB()) {
    const items = await sbGet("analyses?select=id,created_at,kind,title,verdict_text,mobility,threat_level,demo&order=created_at.desc&limit=30");
    return { enabled: true, items };
  }
  return api("/api/history");
}

async function fetchHistoryItem(id) {
  if (SB()) {
    const [row] = await sbGet(`analyses?id=eq.${encodeURIComponent(id)}&select=*`);
    if (!row) throw new Error("기록을 찾을 수 없습니다");
    return row;
  }
  return api(`/api/history/${id}`);
}

async function loadHistory() {
  const box = $("#history-list");
  $("#history-detail").innerHTML = "";
  box.innerHTML = `<p class="hint">불러오는 중...</p>`;
  try {
    const d = await fetchHistory();
    if (!d.enabled) { box.innerHTML = `<div class="warn">분석 기록 저장소(Supabase)가 연결돼 있지 않습니다. 분석 서버에 SUPABASE_URL, SUPABASE_SERVICE_KEY를 설정하면 기록이 쌓입니다.</div>`; return; }
    if (d.error) { box.innerHTML = `<div class="error">${esc(d.error)}</div>`; return; }
    if (!d.items.length) { box.innerHTML = `<p class="hint">아직 저장된 분석 기록이 없습니다. 분석을 한 번 돌려 보세요.</p>`; return; }
    box.innerHTML = `<table class="tbl" id="history-table">${table(["시각", "구분", "대상", "기동 가능성", "위협", "종합 판단", "모드"],
      d.items.map((h) => [new Date(h.created_at).toLocaleString("ko-KR"), h.kind === "route" ? "🛣️ 기동로" : "📍 지점",
        { html: `<a href="#" data-hid="${h.id}">${esc(h.title)}</a>` }, `${M_ICON[h.mobility ?? 0]} ${MOB[h.mobility ?? 0][0]}`,
        THREAT[h.threat_level ?? 0], h.verdict_text, h.demo ? "시연" : "실시간"]))}</table>`;
  } catch (e) { box.innerHTML = `<div class="error">기록을 불러오지 못했습니다: ${esc(e.message)}</div>`; }
}

async function showHistory(id) {
  const box = $("#history-detail");
  box.innerHTML = `<p class="hint">불러오는 중...</p>`;
  try {
    const h = await fetchHistoryItem(id);
    box.innerHTML = `<h4>${esc(h.title)} · ${new Date(h.created_at).toLocaleString("ko-KR")}</h4>` +
      reportBlock(h.report || "", `분석기록_${h.id}.txt`);
  } catch (e) { box.innerHTML = `<div class="error">${esc(e.message)}</div>`; }
}

async function refreshUsage() {
  try { S.cfg = await api("/api/config"); renderSidebar(); } catch (e) { /* 무시 */ }
}

// ================================================================== 시작
// ------------------------------------------------------------------ 실시간 모드 비밀번호 (공개 사이트)
function applyAccess() {
  const c = S.cfg;
  // 공개 사이트라도 비밀번호로 열 수 있으면 스위치는 켜 둠 (끌 때 비밀번호를 물음)
  $("#demo").disabled = !c.has_key || (c.live_locked && !c.admin_available);
  const daily = c.live_daily_limit ? ` 실시간 호출은 하루 ${c.live_daily_limit}건까지(오늘 ${c.api_today ?? 0}건).` : "";
  $("#demo-hint").textContent = c.live_locked
    ? (c.admin_available
      ? "공개 사이트: 스위치를 끄면 비밀번호를 확인한 뒤 실시간 모드(ITS API)로 바뀝니다." + daily
      : "공개 사이트: 실시간 모드(ITS API)는 잠겨 있습니다. 저장된 실제 CCTV와 공개 샘플 영상으로 시연합니다.")
    : "켜짐: ITS API를 부르지 않고 저장된 실제 CCTV + 공개 샘플 영상 + 시연용 ISR로 동작합니다. 끄면 실시간 모드(ITS API 호출, 월 5,000건 한도)." + (c.public_demo ? daily : "");
  $("#admin-box").classList.toggle("hidden", !c.admin);
  $("#admin-on").classList.toggle("hidden", !c.admin);
}

async function unlockLive() {
  // 비밀번호 확인 → 이 탭에 기억 → 서버 설정 다시 읽기. 성공하면 true
  const pass = prompt("실시간 모드 비밀번호를 입력하세요");
  if (!pass) return false;
  try {
    await api("/api/admin/login", { passcode: pass });
    try { sessionStorage.setItem("adminPass", pass.trim()); } catch (e) { /* 저장 불가 브라우저 */ }
    S.cfg = await api("/api/config");
    applyAccess(); renderSidebar();
    return !S.cfg.live_locked;
  } catch (e) { alert("비밀번호 확인 실패: " + e.message); return false; }
}

async function adminLogout() {
  try { sessionStorage.removeItem("adminPass"); } catch (e) { /* 무시 */ }
  S.cfg = await api("/api/config");
  $("#demo").checked = true;
  readSettings(); applyAccess(); renderSidebar(); loadRoute(); loadArea();
}

function offlineMode(info) {
  // 노트북 분석 서버가 꺼져 있을 때: 지난 분석 기록만 보여줌
  const when = info.last ? ` (마지막 신호: ${new Date(info.last).toLocaleString("ko-KR")})` : "";
  $("#banner").className = "cls-banner";
  $("#banner").style.cssText = "background:var(--err-bg);color:var(--err-fg);border-color:var(--nogo)";
  $("#banner").textContent = "분석 서버 꺼짐 · 지난 분석 기록만 볼 수 있습니다";
  document.querySelector("main").insertAdjacentHTML("afterbegin",
    `<div class="warn" style="font-size:.95rem">⚠️ ${esc(info.why)}${esc(when)}.<br>
     새로 분석하려면 노트북에서 분석 서버(run_public.bat)가 켜져 있어야 합니다. 아래 <b>🗂️ 분석 기록</b>에서 지난 분석 결과와 보고서를 볼 수 있습니다.</div>`);
  document.querySelectorAll('nav[data-group="main"] .tab').forEach((b) => { if (b.dataset.tab !== "history") b.disabled = true; b.style.opacity = b.dataset.tab === "history" ? 1 : .4; });
  $("#sidebar").style.opacity = .5;
  $("#sidebar").style.pointerEvents = "none";
  bindCommon();
  showTab("main", "history");
  // 녹화된 시연이 있으면 바로 볼 수 있게 버튼 제공
  fetch("replay/replay.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((b) => {
    if (!b) return;
    document.querySelector("main > .warn").insertAdjacentHTML("beforeend",
      `<div style="margin-top:10px"><button class="btn primary" id="replay-btn">▶ 녹화된 시연 보기 (${esc(b.recorded_at)} 실제 분석 결과)</button>
       <span class="hint" style="margin-left:8px">서버 없이 기동로·지점 주변 분석 화면 전체를 그대로 볼 수 있습니다.</span></div>`);
    $("#replay-btn").addEventListener("click", () => startReplay(b));
  }).catch(() => { /* 녹화 시연 없음 */ });
}

// 탭·분석 기록 버튼 (한 번만 연결)
function bindCommon() {
  if (S.commonBound) return;
  S.commonBound = true;
  document.querySelectorAll("nav.tabs").forEach((nav) => nav.addEventListener("click", (e) => {
    const b = e.target.closest(".tab"); if (b && !b.disabled) showTab(nav.dataset.group, b.dataset.tab);
  }));
  $("#history-refresh").addEventListener("click", loadHistory);
  $("#history-list").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-hid]"); if (!a) return;
    e.preventDefault(); showHistory(a.dataset.hid);
  });
}

// ------------------------------------------------------------------ 녹화된 시연 (서버 없이 실제 분석 결과 재생)
function startReplay(b) {
  S.replay = true;
  S.replayAt = b.recorded_at;
  API = "";  // 사진은 이 사이트의 replay/ 폴더에서 읽음
  S.cfg = b.config;
  document.querySelector("main > .warn")?.remove();
  document.querySelectorAll('nav[data-group="main"] .tab').forEach((t) => { t.disabled = false; t.style.opacity = 1; });
  $("#sidebar").style.opacity = 1; $("#sidebar").style.pointerEvents = "";
  $("#banner").style.cssText = "background:var(--info-bg);color:var(--info-fg);border-color:var(--info-line)";
  $("#banner").textContent = `녹화된 시연 · ${b.recorded_at} 실제 분석 결과 재생 (분석 서버 없이 동작)`;
  document.querySelector("header.hdr").insertAdjacentHTML("afterend",
    `<div class="warn" style="background:var(--info-bg);color:var(--info-text);border-color:var(--info-line);font-size:.92rem">🎬 <b>녹화된 시연</b>입니다.
     ${esc(b.recorded_at)}에 실제로 분석한 결과(공개 도로 CCTV·시연용 ISR 영상)를 그대로 보여줍니다. 지도·결과 탭·보고서를 눌러 보세요.
     설정을 바꿔 새로 분석하려면 분석 서버(노트북)가 켜져 있어야 합니다.
     <a href="./" style="color:var(--info-fg);margin-left:6px">실시간 분석 화면으로 →</a></div>`);

  setupUI();
  // 기동로
  setRoutePlace("start", b.route.start); setRoutePlace("end", b.route.end);
  $("#buffer").value = b.route.buffer_km; $("#maxc").value = b.route.max_cctvs; $("#demo").checked = true;
  readSettings();
  S.route.isr = b.route.isr.map((x) => ({ ...x }));
  S.route.data = b.route.info;
  S.route.result = b.route.result; S.route.resultKey = routeKey();
  $("#route-isr-panel").open = false;
  renderRoute();
  // 지점 주변
  $("#area-place").value = b.area.place;
  $("#area-lat").value = b.area.lat; $("#area-lon").value = b.area.lon;
  $("#area-radius").value = b.area.radius; $("#area-radius-v").textContent = b.area.radius;
  S.area.isr = b.area.isr.map((x) => ({ ...x }));
  S.area.cctvs = b.area.cctvs;
  S.area.result = b.area.result; S.area.resultKey = areaKey();
  $("#area-isr-panel").open = false;
  // 설정·입력은 잠금 (지도 바탕 선택·결과 탭은 그대로 사용)
  document.querySelectorAll('#sidebar input, #sidebar button, #tab-route select, #tab-route input:not([name^="st-"]), #tab-area select, #tab-area input:not([name^="st-"]), #route-isr-add, #route-isr-clear, #area-isr-add, #area-isr-clear, #area-apply, #route-apply')
    .forEach((e) => (e.disabled = true));
  ["#route-run", "#area-run"].forEach((s) => { $(s).disabled = true; $(s).textContent = "녹화된 시연 (새 분석은 분석 서버 필요)"; });
  showTab("main", "route");
}

// 색상 시안: 주소에 ?theme=a~d 를 붙여 미리 보기
(function applyTheme() {
  const t = new URLSearchParams(location.search).get("theme");
  if (t && /^[a-z]$/.test(t)) document.documentElement.dataset.theme = t;
})();

async function init() {
  if (new URLSearchParams(location.search).has("replay")) {  // ?replay 로 바로 녹화 시연 보기
    try { return startReplay(await (await fetch("replay/replay.json", { cache: "no-store" })).json()); } catch (e) { /* 없으면 평소대로 */ }
  }
  const conn = await resolveApi();
  if (!conn.ok) return offlineMode(conn);
  try {
    S.cfg = await api("/api/config");
  } catch (e) {
    return offlineMode({ why: "분석 서버에 연결하지 못했습니다 (" + e.message + ")" });
  }
  setupUI();
  // 서버가 켜져 있어도 녹화 시연을 볼 수 있게 링크 제공
  fetch("replay/replay.json", { method: "HEAD", cache: "no-store" }).then((r) => {
    if (r.ok) document.querySelector(".hdr-sub").insertAdjacentHTML("beforeend",
      ` <a href="?replay" style="color:var(--info-fg);white-space:nowrap">🎬 녹화된 시연 보기</a>`);
  }).catch(() => {});
  await loadRoute();
  await loadArea();
}

// 화면 준비 (선택 목록·지도·버튼 연결). 실시간·녹화 시연 공용
// ISR 사진 썸네일 (web/isr/ 에 축소본이 있는 시연용 사진만)
function isrThumb(src) {
  return /^isr\/[\w.-]+\.(jpe?g|png|webp)$/i.test(src || "") ? `<img class="isr-th" src="${esc(src)}" alt="" loading="lazy">` : "";
}

// 시연용 ISR 사진 갤러리: 사진을 눌러 고르면 아래 '추가' 버튼으로 넣음
function isrGallery(k, list) {
  const sel = $(`#${k}-isr-extra`);
  sel.closest("label").insertAdjacentHTML("afterend", `<div class="isr-gallery" id="${k}-isr-gallery">` +
    list.map((e, i) => `<figure data-i="${i}" title="${esc(e.name)}">${isrThumb(e.source)}<figcaption>${esc(e.name.replace(/^\[시연용 ISR\]\s*/, ""))}</figcaption></figure>`).join("") + `</div>`);
  const gal = $(`#${k}-isr-gallery`);
  const mark = () => gal.querySelectorAll("figure").forEach((f) => f.classList.toggle("sel", f.dataset.i === sel.value));
  gal.addEventListener("click", (e) => {
    const f = e.target.closest("figure"); if (!f || S.replay) return;
    sel.value = sel.value === f.dataset.i ? "" : f.dataset.i; mark();
  });
  sel.addEventListener("change", mark);
  S.isrMark = S.isrMark || {}; S.isrMark[k] = mark;
}

function setupUI() {
  const c = S.cfg;
  applyAccess();
  $("#admin-logout").addEventListener("click", (e) => { e.preventDefault(); adminLogout(); });
  renderSidebar();
  readSettings();

  const names = Object.keys(c.places);
  const opts = names.map((n) => `<option>${esc(n)}</option>`).join("");
  const ptOpts = opts + `<option value="${CUSTOM_PT}">직접 지정 (위도·경도)</option>`;
  $("#start").innerHTML = ptOpts; $("#end").innerHTML = ptOpts;
  setRoutePlace("start", names[0]);
  setRoutePlace("end", names.includes("천안") ? "천안" : names[1]);
  $("#area-place").innerHTML = `<option value="__custom">직접 지정 (지도 클릭·좌표)</option>` + opts;
  const extra = `<option value="">선택 안 함</option>` + c.demo_isr.extra.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join("");
  $("#route-isr-extra").innerHTML = extra; $("#area-isr-extra").innerHTML = extra;
  ["route", "area"].forEach((k) => isrGallery(k, c.demo_isr.extra));

  S.route.isr = c.demo_isr.items.map((x) => ({ ...x }));
  S.area.isr = (c.demo_isr.near || []).map((x) => ({ ...x }));

  RM = makeMap("route-map"); AM = makeMap("area-map");
  styleRadios(document.querySelector('.map-styles[data-map="route"]'), RM);
  styleRadios(document.querySelector('.map-styles[data-map="area"]'), AM);
  AM.map.on("click", (e) => {
    if (S.replay) return;
    $("#area-lat").value = e.latlng.lat.toFixed(5); $("#area-lon").value = e.latlng.lng.toFixed(5);
    $("#area-place").value = "__custom"; loadArea();
  });

  // 탭·분석 기록
  bindCommon();

  // 설정 변경
  const onSettings = debounce(() => { readSettings(); loadRoute(); loadArea(); }, 300);
  ["#seconds", "#maxc", "#buffer"].forEach((s) => $(s).addEventListener("input", () => { readSettings(); }));
  ["#maxc", "#buffer"].forEach((s) => $(s).addEventListener("change", onSettings));
  $("#demo").addEventListener("change", async () => {
    if (!$("#demo").checked) {
      // 공개 사이트에서는 실시간 모드로 바꿀 때 비밀번호 확인
      if (S.cfg.live_locked && !(await unlockLive())) { $("#demo").checked = true; return; }
      if (!confirm("실시간 모드로 바꾸면 국가교통정보센터 ITS API를 호출합니다 (월 5,000건 한도). 계속할까요?")) { $("#demo").checked = true; return; }
    }
    readSettings(); loadRoute(); loadArea();
  });
  $("#check-saved").addEventListener("click", async () => {
    $("#check-out").textContent = "확인 중...";
    try {
      const r = await api("/api/check_saved");
      $("#check-out").innerHTML = r.map((s) => `${s.ok ? "✅" : "❌"} ${esc(s.name)}${s.ok ? "" : " — 만료됨, 실시간 모드에서 다시 받아 저장 필요"}`).join("<br>");
    } catch (e) { $("#check-out").textContent = "확인 실패: " + e.message; }
  });

  // 기동로
  // 출발·도착점: 목록 선택은 바로 반영, 좌표 입력은 '기동로 반영' 단추(또는 Enter)로 반영
  ["start", "end"].forEach((k) => {
    $(`#${k}`).addEventListener("change", () => {
      if ($(`#${k}`).value === CUSTOM_PT) { $(`#${k}-lat`).focus(); return routePending(true); }
      setRoutePlace(k, $(`#${k}`).value); loadRoute();
    });
    [`#${k}-lat`, `#${k}-lon`].forEach((s) => {
      $(s).addEventListener("input", () => { $(`#${k}`).value = CUSTOM_PT; routePending(true); });
      $(s).addEventListener("keydown", (e) => { if (e.key === "Enter") applyRoute(); });
    });
  });
  $("#route-apply").addEventListener("click", applyRoute);
  $("#route-run").addEventListener("click", runRoute);
  $("#route-isr-km").addEventListener("input", () => ($("#route-isr-km-v").textContent = $("#route-isr-km").value));
  $("#route-isr-table").addEventListener("click", (e) => {
    if (S.replay) return;
    const id = e.target.dataset && e.target.dataset.del; if (!id) return;
    S.route.isr = S.route.isr.filter((i) => i.id !== id); renderRoute();
  });
  $("#route-isr-clear").addEventListener("click", () => { S.route.isr = []; renderRoute(); });
  $("#route-isr-add").addEventListener("click", async () => {
    const km = +$("#route-isr-km").value, f = $("#route-isr-file").files[0], ex = $("#route-isr-extra").value;
    try {
      if (f) { const u = await upload(f); S.route.isr.push({ id: u.id, name: u.name, source: u.source, km }); $("#route-isr-file").value = ""; }
      else if (ex !== "") { const e2 = c.demo_isr.extra[+ex]; S.route.isr.push({ id: Math.random().toString(36).slice(2, 10), name: e2.name, source: e2.source, km }); }
      else return alert("사진·영상 파일을 고르거나 시연용 ISR 사진을 선택하세요.");
      renderRoute();
    } catch (e) { alert("추가 실패: " + e.message); }
  });
  $("#route-save-demo").addEventListener("click", async () => {
    try { const r = await api("/api/save_demo", routeReq()); alert(`시연 목록에 실제 CCTV를 저장했습니다 (총 ${r.saved_total}개). 시연 모드에서 API 호출 없이 씁니다.`); refreshUsage(); }
    catch (e) { alert("저장 실패: " + e.message); }
  });

  // 지점 주변
  $("#area-place").addEventListener("change", () => {
    const p = c.places[$("#area-place").value];
    if (p) { $("#area-lat").value = p[0]; $("#area-lon").value = p[1]; loadArea(); }
  });
  // 위도·경도는 입력 중 자동 조회하지 않고 '지점 반영' 단추(또는 Enter)로 반영
  ["#area-lat", "#area-lon"].forEach((s) => {
    $(s).addEventListener("input", () => { $("#area-place").value = "__custom"; areaPending(true); });
    $(s).addEventListener("keydown", (e) => { if (e.key === "Enter") applyArea(); });
  });
  $("#area-apply").addEventListener("click", applyArea);
  $("#area-radius").addEventListener("input", () => ($("#area-radius-v").textContent = $("#area-radius").value));
  $("#area-radius").addEventListener("change", loadArea);
  $("#area-run").addEventListener("click", runArea);
  $("#area-isr-table").addEventListener("click", (e) => {
    if (S.replay) return;
    const id = e.target.dataset && e.target.dataset.del; if (!id) return;
    S.area.isr = S.area.isr.filter((i) => i.id !== id); renderArea();
  });
  $("#area-isr-clear").addEventListener("click", () => { S.area.isr = []; renderArea(); });
  $("#area-isr-add").addEventListener("click", async () => {
    const [lat, lon] = areaPt();
    const [plat, plon] = offsetPoint(lat, lon, +$("#area-isr-brg").value, +$("#area-isr-dist").value);
    const f = $("#area-isr-file").files[0], ex = $("#area-isr-extra").value;
    try {
      if (f) { const u = await upload(f); S.area.isr.push({ id: u.id, name: u.name, source: u.source, lat: plat, lon: plon }); $("#area-isr-file").value = ""; }
      else if (ex !== "") { const e2 = c.demo_isr.extra[+ex]; S.area.isr.push({ id: Math.random().toString(36).slice(2, 10), name: e2.name, source: e2.source, lat: plat, lon: plon }); }
      else return alert("사진·영상 파일을 고르거나 시연용 ISR 사진을 선택하세요.");
      renderArea();
    } catch (e) { alert("추가 실패: " + e.message); }
  });

}

init();
