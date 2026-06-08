"use strict";

const COLS = [
  { key: "name", label: "Firma", cls: "name" },
  { key: "wkn", label: "WKN", cls: "wkn" },
  { key: "ticker", label: "Ticker", cls: "ticker" },
  { key: "presented_date", label: "Vorgestellt", cls: "" },
  { key: "entry", label: "Kurs Vorst.", cls: "num" },
  { key: "now", label: "Kurs heute", cls: "num" },
  { key: "currency", label: "Whg.", cls: "" },
  { key: "abs_delta", label: "Δ abs.", cls: "num" },
  { key: "pct_delta", label: "Δ %", cls: "num" },
  { key: "days_held", label: "Tage", cls: "num" },
];

const state = {
  data: null,
  view: "all",
  sortKey: "pct_delta",
  sortDir: "desc",
  q: "",
  year: "",
  ccy: "",
  onlyResolved: true,
};

const $ = (s) => document.querySelector(s);

function rows() {
  return state.view === "first" ? state.data.first : state.data.all;
}
function agg() {
  return state.view === "first"
    ? state.data.aggregates_first
    : state.data.aggregates_all;
}

function fmtNum(v) {
  if (v === null || v === undefined) return "–";
  return v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v) {
  if (v === null || v === undefined) return null;
  const s = v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (v > 0 ? "+" : "") + s + " %";
}
function fmtDate(iso) {
  if (!iso) return "–";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderCards() {
  const a = agg();
  const card = (label, value, sub, cls) => `
    <div class="card${label === "Gleichgewichtetes Depot" ? " span2" : ""}">
      <p class="label">${label}</p>
      <p class="value ${cls || ""}">${value}</p>
      ${sub ? `<p class="sub">${sub}</p>` : ""}
    </div>`;
  const best = a.best ? `${fmtPct(a.best.pct)}` : "–";
  const worst = a.worst ? `${fmtPct(a.worst.pct)}` : "–";
  $("#cards").innerHTML = [
    card("Größter Gewinner", best, a.best ? esc(a.best.name) : "", a.best && a.best.pct >= 0 ? "pos" : "neg"),
    card("Größter Verlierer", worst, a.worst ? esc(a.worst.name) : "", a.worst && a.worst.pct < 0 ? "neg" : "pos"),
    card("Trefferquote", a.winner_share !== null ? a.winner_share.toLocaleString("de-DE") + " %" : "–",
      a.count_resolved ? `${a.winners} Gewinner · ${a.losers} Verlierer` : ""),
    card("Median Δ %", a.median_pct !== null ? fmtPct(a.median_pct) : "–", "über alle auflösbaren",
      a.median_pct >= 0 ? "pos" : "neg"),
    card("Gleichgewichtetes Depot", a.equal_weight_pct !== null ? fmtPct(a.equal_weight_pct) : "–",
      `Ø-Rendite, hätte man jede Vorstellung gekauft · ${a.count_resolved} Positionen`,
      a.equal_weight_pct >= 0 ? "pos" : "neg"),
  ].join("");
}

function renderHead() {
  $("#head-row").innerHTML = COLS.map((c) => {
    const sorted = state.sortKey === c.key;
    const arrow = sorted ? (state.sortDir === "asc" ? "▲" : "▼") : "▼";
    const aria = sorted ? ` aria-sort="${state.sortDir === "asc" ? "ascending" : "descending"}"` : "";
    return `<th class="${c.cls}" data-key="${c.key}"${aria}>${c.label}<span class="arrow">${arrow}</span></th>`;
  }).join("");
  $("#head-row").querySelectorAll("th").forEach((th) =>
    th.addEventListener("click", () => onSort(th.dataset.key)));
}

function filtered() {
  let r = rows().slice();
  if (state.onlyResolved) r = r.filter((x) => x.resolved);
  if (state.q) {
    const q = state.q.toLowerCase();
    r = r.filter((x) => (x.name || "").toLowerCase().includes(q));
  }
  if (state.year) r = r.filter((x) => (x.presented_date || "").startsWith(state.year));
  if (state.ccy) r = r.filter((x) => x.currency === state.ccy);
  return r;
}

function sortRows(r) {
  const k = state.sortKey;
  const dir = state.sortDir === "asc" ? 1 : -1;
  const numeric = ["entry", "now", "abs_delta", "pct_delta", "days_held"].includes(k);
  return r.sort((a, b) => {
    let av = a[k], bv = b[k];
    // Nullwerte immer ans Ende
    const an = av === null || av === undefined, bn = bv === null || bv === undefined;
    if (an && bn) return 0;
    if (an) return 1;
    if (bn) return -1;
    if (numeric) return (av - bv) * dir;
    return String(av).localeCompare(String(bv), "de") * dir;
  });
}

function renderRows() {
  const r = sortRows(filtered());
  const tb = $("#rows");
  if (!r.length) {
    tb.innerHTML = "";
    $("#empty").hidden = false;
    $("#rowcount").textContent = "";
    return;
  }
  $("#empty").hidden = true;
  tb.innerHTML = r.map((x) => {
    const pctCell = x.pct_delta === null
      ? `<span class="na">n/a</span>`
      : `<span class="pill ${x.pct_delta >= 0 ? "pos" : "neg"}">${fmtPct(x.pct_delta)}</span>`;
    return `<tr>
      <td class="name">${esc(x.name)}<span class="ep" title="${esc(x.ep_title)}">${esc(x.ep_title)}</span></td>
      <td class="wkn">${esc(x.wkn)}</td>
      <td class="ticker">${x.ticker ? esc(x.ticker) : '<span class="na">–</span>'}</td>
      <td>${fmtDate(x.presented_date)}</td>
      <td class="num">${x.entry === null ? '<span class="na">–</span>' : fmtNum(x.entry)}</td>
      <td class="num">${x.now === null ? '<span class="na">–</span>' : fmtNum(x.now)}</td>
      <td>${x.currency || '<span class="na">–</span>'}</td>
      <td class="num">${x.abs_delta === null ? '<span class="na">–</span>' : fmtNum(x.abs_delta)}</td>
      <td class="num">${pctCell}</td>
      <td class="num">${x.days_held}</td>
    </tr>`;
  }).join("");
  $("#rowcount").textContent = `${r.length} Zeile${r.length === 1 ? "" : "n"} angezeigt`;
}

function onSort(key) {
  if (state.sortKey === key) {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = key;
    state.sortDir = ["name", "wkn", "ticker", "currency", "presented_date"].includes(key) ? "asc" : "desc";
  }
  renderHead();
  renderRows();
}

function render() {
  renderCards();
  renderHead();
  renderRows();
}

function initFilters() {
  const years = new Set();
  const ccys = new Set();
  for (const x of state.data.all) {
    if (x.presented_date) years.add(x.presented_date.slice(0, 4));
    if (x.currency) ccys.add(x.currency);
  }
  $("#f-year").insertAdjacentHTML("beforeend",
    [...years].sort().reverse().map((y) => `<option value="${y}">${y}</option>`).join(""));
  $("#f-ccy").insertAdjacentHTML("beforeend",
    [...ccys].sort().map((c) => `<option value="${c}">${c}</option>`).join(""));

  $("#f-q").addEventListener("input", (e) => { state.q = e.target.value.trim(); renderRows(); });
  $("#f-year").addEventListener("change", (e) => { state.year = e.target.value; renderRows(); });
  $("#f-ccy").addEventListener("change", (e) => { state.ccy = e.target.value; renderRows(); });
  $("#f-resolved").addEventListener("change", (e) => { state.onlyResolved = e.target.checked; renderRows(); });

  document.querySelectorAll(".seg-btn").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(".seg-btn").forEach((x) => x.classList.remove("is-active"));
      b.classList.add("is-active");
      state.view = b.dataset.view;
      render();
    }));
}

async function main() {
  try {
    const res = await fetch("data.json", { cache: "no-store" });
    state.data = await res.json();
  } catch (e) {
    $("#asof").textContent = "Fehler beim Laden von data.json";
    return;
  }
  const d = new Date(state.data.as_of);
  $("#asof").textContent = "Stand " + d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  try {
    const meta = await (await fetch("meta.json", { cache: "no-store" })).json();
    $("#meta-line").textContent =
      `${meta.presentations} Vorstellungen · ${meta.unique_wkns} Aktien · ${meta.episodes} Folgen · ${meta.unresolved_count} ungelöste WKNs · Stand ${d.toLocaleString("de-DE")}`;
  } catch (e) { /* meta optional */ }
  initFilters();
  render();
}

main();
