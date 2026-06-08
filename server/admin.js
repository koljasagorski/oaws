"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) { showLogin(); throw new Error("unauth"); }
  return r;
};
const jpost = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const msg = (el, text, good) => { const e = $(el); e.textContent = text; e.className = "msg " + (good ? "ok" : "bad"); setTimeout(() => { e.textContent = ""; }, 4000); };

function showLogin() { $("#login").classList.remove("hidden"); $("#dash").classList.add("hidden"); }
function showDash() { $("#login").classList.add("hidden"); $("#dash").classList.remove("hidden"); }

$("#login-btn").addEventListener("click", doLogin);
$("#login-pw").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
async function doLogin() {
  const fd = new FormData(); fd.append("password", $("#login-pw").value);
  const r = await fetch("/api/login", { method: "POST", body: fd, credentials: "same-origin" });
  if (r.ok) { $("#login-pw").value = ""; init(); }
  else { $("#login-msg").textContent = r.status === 401 ? "Falsches Passwort" : "Fehler"; }
}
$("#logout").addEventListener("click", async (e) => { e.preventDefault(); await jpost("/api/logout", {}); showLogin(); });

function fmtTs(s) { return s ? new Date(s).toLocaleString("de-DE") : "–"; }

async function loadStatus() {
  const r = await api("/api/status"); const d = await r.json();
  const m = d.meta || {}, lr = d.last_run || {};
  $("#stat").innerHTML = [
    ["Vorstellungen", m.presentations ?? "–"],
    ["Aktien", m.unique_wkns ?? "–"],
    ["Folgen", m.episodes ?? "–"],
    ["Ungelöste WKNs", d.unresolved_count ?? "–"],
    ["Letzter Lauf", `<span class="${lr.ok ? "ok" : "bad"}">${lr.ok ? "OK" : (lr.summary ? "Fehler" : "–")}</span>`],
    ["Stand", fmtTs(m.as_of)],
  ].map(([k, v]) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const badge = $("#run-badge");
  if (d.running) { badge.textContent = "läuft …"; badge.className = "badge run"; }
  else { badge.textContent = lr.finished ? "zuletzt " + fmtTs(lr.finished) : ""; badge.className = "badge"; }
  $("#refresh-btn").disabled = d.running;

  $("#key-state").textContent = d.has_openfigi_key ? "(gesetzt)" : "(nicht gesetzt)";
  const c = d.config || {};
  $("#entry-mode").value = c.entry_mode || "on_or_before";
  $("#scope").value = c.scope_days == null ? "null" : String(c.scope_days);
  $("#schedule").value = c.schedule || "08:00";

  $("#unr-count").textContent = `(${d.unresolved_count} gesamt, max 500 gezeigt)`;
  $("#unr-rows").innerHTML = (d.unresolved || []).map((u) =>
    `<tr data-wkn="${u.wkn}" data-name="${(u.figi_name || "").replace(/"/g, "&quot;")}" style="cursor:pointer">
       <td style="font-family:var(--mono)">${u.wkn}</td><td>${u.figi_name || "–"}</td></tr>`).join("");
  $("#unr-rows").querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => {
    $("#ov-wkn").value = tr.dataset.wkn; $("#ov-name").value = tr.dataset.name || ""; $("#ov-yahoo").focus();
  }));
  return d;
}

async function loadLog() {
  const r = await api("/api/run-log"); $("#log").textContent = await r.text();
  $("#log").scrollTop = $("#log").scrollHeight;
}

$("#refresh-btn").addEventListener("click", async () => {
  const r = await jpost("/api/refresh", {}); const d = await r.json();
  msg("#refresh-msg", d.msg || (d.ok ? "gestartet" : "Fehler"), d.ok);
  setTimeout(() => { loadStatus(); loadLog(); }, 1500);
});
$("#log-btn").addEventListener("click", loadLog);

$("#key-btn").addEventListener("click", async () => {
  const r = await jpost("/api/keys", { openfigi_api_key: $("#openfigi").value });
  msg("#key-msg", r.ok ? "gespeichert" : "Fehler", r.ok); $("#openfigi").value = ""; loadStatus();
});

$("#settings-btn").addEventListener("click", async () => {
  const body = { entry_mode: $("#entry-mode").value, scope_days: $("#scope").value, schedule: $("#schedule").value };
  const r = await jpost("/api/settings", body); const d = await r.json();
  msg("#settings-msg", d.msg || "gespeichert", r.ok);
});

$("#pw-btn").addEventListener("click", async () => {
  const np = $("#newpw").value;
  const r = await jpost("/api/password", { new_password: np });
  if (r.ok) { msg("#pw-msg", "Passwort geändert", true); $("#newpw").value = ""; }
  else { const e = await r.json().catch(() => ({})); msg("#pw-msg", e.detail || "Fehler", false); }
});

$("#ov-btn").addEventListener("click", async () => {
  const body = { wkn: $("#ov-wkn").value, yahoo: $("#ov-yahoo").value, currency: $("#ov-ccy").value, name: $("#ov-name").value };
  const r = await jpost("/api/override", body);
  if (r.ok) {
    msg("#ov-msg", "Override gesetzt — beim nächsten Lauf aktiv", true);
    ["ov-wkn", "ov-yahoo", "ov-ccy", "ov-name"].forEach((id) => { $("#" + id).value = ""; });
    loadStatus();
  } else { const e = await r.json().catch(() => ({})); msg("#ov-msg", e.detail || "Fehler", false); }
});

let pollTimer = null;
async function init() {
  try {
    showDash();
    await loadStatus();
    await loadLog();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(loadStatus, 5000);  // Live-Status während Läufen
  } catch (e) { /* showLogin already called on 401 */ }
}
init();
