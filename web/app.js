(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    datasets: [],
    selectedId: null,
    selectedVersion: null,
    schema: [],
    pageOffset: 0,
    pageLimit: 25,
    totalRows: 0,
    statusTimer: null,
    searchTimer: null,
    filterTimer: null
  };

  const els = {
    appTitle: $("appTitle"), datasetSelect: $("datasetSelect"), kindBadge: $("kindBadge"), datasetStatusBadge: $("datasetStatusBadge"),
    sourceText: $("sourceText"), rowsStat: $("rowsStat"), columnsStat: $("columnsStat"), versionStat: $("versionStat"), refreshStat: $("refreshStat"),
    statusMessage: $("statusMessage"), refreshCurrentBtn: $("refreshCurrentBtn"), refreshAllBtn: $("refreshAllBtn"), downloadBtn: $("downloadBtn"),
    xSelect: $("xSelect"), ySelect: $("ySelect"), aggSelect: $("aggSelect"), chartTypeSelect: $("chartTypeSelect"), sortSelect: $("sortSelect"), groupLimitSelect: $("groupLimitSelect"),
    filterColumn1: $("filterColumn1"), filterValue1: $("filterValue1"), filterColumn2: $("filterColumn2"), filterValue2: $("filterValue2"), clearFiltersBtn: $("clearFiltersBtn"),
    chartTitle: $("chartTitle"), chartMeta: $("chartMeta"), chartWrap: $("chartWrap"), chartError: $("chartError"),
    datasetCount: $("datasetCount"), datasetList: $("datasetList"), storageText: $("storageText"), discoveryText: $("discoveryText"),
    searchInput: $("searchInput"), pageSizeSelect: $("pageSizeSelect"), tableMeta: $("tableMeta"), tableHead: $("tableHead"), tableBody: $("tableBody"),
    prevBtn: $("prevBtn"), nextBtn: $("nextBtn"), pageText: $("pageText"), footerTimestamp: $("footerTimestamp")
  };

  function formatNumber(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value ?? "—");
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(n);
  }

  function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[ch]));
  }

  async function getJSON(url, options) {
    const response = await fetch(url, options);
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* no-op */ }
    if (!response.ok) throw new Error(payload?.error || payload?.message || `Request failed (${response.status})`);
    return payload;
  }

  function selectedDataset() {
    return state.datasets.find((item) => item.id === state.selectedId) || null;
  }

  function filterPayload() {
    const filters = [];
    const pairs = [
      [els.filterColumn1.value, els.filterValue1.value],
      [els.filterColumn2.value, els.filterValue2.value]
    ];
    for (const [column, value] of pairs) {
      if (column && value.trim()) filters.push({ column, value: value.trim() });
    }
    return filters;
  }

  function filtersQuery() {
    const filters = filterPayload();
    return filters.length ? `&filters=${encodeURIComponent(JSON.stringify(filters))}` : "";
  }

  function setBadge(el, text, status) {
    el.textContent = text;
    el.className = `badge ${status || ""}`;
  }

  function renderDatasetSelector() {
    const current = state.selectedId;
    els.datasetSelect.innerHTML = state.datasets.map((ds) => `<option value="${escapeHTML(ds.id)}">${escapeHTML(ds.name)}</option>`).join("");
    if (current && state.datasets.some((ds) => ds.id === current)) els.datasetSelect.value = current;
  }

  function renderDatasetRegistry() {
    els.datasetCount.textContent = String(state.datasets.length);
    els.datasetList.innerHTML = state.datasets.map((ds) => {
      const selected = ds.id === state.selectedId ? " selected" : "";
      return `<button type="button" class="dataset-item${selected}" data-id="${escapeHTML(ds.id)}">
        <span class="dataset-item-main"><strong>${escapeHTML(ds.name)}</strong><small>${escapeHTML(ds.kind)}</small></span>
        <span class="dataset-item-side"><span class="mini-status ${escapeHTML(ds.status)}">${escapeHTML(ds.status)}</span><small>${formatNumber(ds.rows)} rows</small></span>
      </button>`;
    }).join("");
    els.datasetList.querySelectorAll(".dataset-item").forEach((button) => {
      button.addEventListener("click", () => selectDataset(button.dataset.id));
    });
  }

  function applySelectedStatus() {
    const ds = selectedDataset();
    if (!ds) return;
    els.rowsStat.textContent = formatNumber(ds.rows);
    els.columnsStat.textContent = formatNumber(ds.columns);
    els.versionStat.textContent = formatNumber(ds.version);
    els.refreshStat.textContent = formatDate(ds.lastRefreshUtc);
    els.sourceText.textContent = ds.source || "—";
    els.statusMessage.textContent = ds.message || "";
    setBadge(els.kindBadge, String(ds.kind || "dataset").toUpperCase(), "kind");
    setBadge(els.datasetStatusBadge, String(ds.status || "unknown").toUpperCase(), ds.status);
    els.refreshCurrentBtn.disabled = !ds.refreshable;
    els.refreshCurrentBtn.title = ds.refreshable ? "Force a refresh of this SBDF" : "Derived/demo datasets refresh when their source datasets change";
    els.downloadBtn.href = ds.downloadUrl || `/download/${encodeURIComponent(ds.id)}.csv`;
  }

  async function loadGlobalStatus({ preserveSelection = true } = {}) {
    const payload = await getJSON(`/api/status?_=${Date.now()}`);
    state.datasets = payload.datasets || [];
    document.title = payload.appTitle || "SBDF Multi-Data Explorer";
    els.appTitle.textContent = payload.appTitle || "SBDF Multi-Data Explorer";
    els.storageText.textContent = payload.storage || "DuckDB + Parquet";
    els.discoveryText.textContent = `Discovery: ${payload.discoveryFolder || "—"}`;
    els.footerTimestamp.textContent = `Checked ${new Date().toLocaleTimeString()}`;

    const previous = preserveSelection ? state.selectedId : null;
    if (!previous || !state.datasets.some((ds) => ds.id === previous)) {
      const preferred = state.datasets.find((ds) => ds.status === "ok" && ds.kind === "append") || state.datasets.find((ds) => ds.status === "ok") || state.datasets[0];
      state.selectedId = preferred?.id || null;
    }
    renderDatasetSelector();
    renderDatasetRegistry();
    applySelectedStatus();
    return payload;
  }

  function fillSelect(select, columns, { numericOnly = false, includeNone = false } = {}) {
    const previous = select.value;
    const candidates = numericOnly ? columns.filter((c) => c.numeric) : columns;
    const items = [];
    if (includeNone) items.push(`<option value="">None</option>`);
    for (const col of candidates) items.push(`<option value="${escapeHTML(col.name)}">${escapeHTML(col.name)}</option>`);
    select.innerHTML = items.join("");
    if (previous && candidates.some((c) => c.name === previous)) select.value = previous;
  }

  async function loadSchema() {
    if (!state.selectedId) return;
    const payload = await getJSON(`/api/datasets/${encodeURIComponent(state.selectedId)}/schema?_=${Date.now()}`);
    state.schema = payload.columns || [];
    fillSelect(els.xSelect, state.schema);
    fillSelect(els.ySelect, state.schema, { numericOnly: true, includeNone: true });
    fillSelect(els.filterColumn1, state.schema, { includeNone: true });
    fillSelect(els.filterColumn2, state.schema, { includeNone: true });

    if (!els.xSelect.value && state.schema.length) els.xSelect.value = state.schema[0].name;
    if (!els.ySelect.value) {
      const numeric = state.schema.find((c) => c.numeric);
      if (numeric) els.ySelect.value = numeric.name;
    }
  }

  function renderEmptyChart(message) {
    els.chartWrap.innerHTML = `<div class="empty-state">${escapeHTML(message)}</div>`;
  }

  function renderBarChart(points) {
    if (!points.length) return renderEmptyChart("No chart data for the current selection.");
    const width = 980, height = 390, left = 76, right = 24, top = 24, bottom = 92;
    const plotW = width - left - right, plotH = height - top - bottom;
    const values = points.map((p) => Number(p.value) || 0);
    const max = Math.max(...values, 0) || 1;
    const gap = Math.max(4, plotW * 0.012);
    const barW = Math.max(3, (plotW - gap * (points.length - 1)) / points.length);
    const yTicks = 4;
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Bar chart">`;
    for (let i = 0; i <= yTicks; i++) {
      const y = top + plotH - (i / yTicks) * plotH;
      const val = (i / yTicks) * max;
      svg += `<line x1="${left}" x2="${width-right}" y1="${y}" y2="${y}" class="grid-line"/><text x="${left-10}" y="${y+4}" text-anchor="end" class="axis-text">${escapeHTML(formatNumber(val))}</text>`;
    }
    points.forEach((p, i) => {
      const v = Number(p.value) || 0;
      const h = (v / max) * plotH;
      const x = left + i * (barW + gap);
      const y = top + plotH - h;
      svg += `<rect x="${x}" y="${y}" width="${barW}" height="${Math.max(1,h)}" rx="3" class="bar"><title>${escapeHTML(p.label)}: ${escapeHTML(formatNumber(v))}</title></rect>`;
      const label = String(p.label).length > 14 ? String(p.label).slice(0, 12) + "…" : String(p.label);
      svg += `<text x="${x + barW/2}" y="${top+plotH+18}" text-anchor="end" transform="rotate(-38 ${x + barW/2} ${top+plotH+18})" class="axis-text">${escapeHTML(label)}</text>`;
    });
    svg += `</svg>`;
    els.chartWrap.innerHTML = svg;
  }

  function renderLineChart(points) {
    if (!points.length) return renderEmptyChart("No chart data for the current selection.");
    const width = 980, height = 390, left = 76, right = 24, top = 24, bottom = 92;
    const plotW = width - left - right, plotH = height - top - bottom;
    const values = points.map((p) => Number(p.value) || 0);
    const max = Math.max(...values, 0) || 1;
    const yTicks = 4;
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart">`;
    for (let i = 0; i <= yTicks; i++) {
      const y = top + plotH - (i / yTicks) * plotH;
      const val = (i / yTicks) * max;
      svg += `<line x1="${left}" x2="${width-right}" y1="${y}" y2="${y}" class="grid-line"/><text x="${left-10}" y="${y+4}" text-anchor="end" class="axis-text">${escapeHTML(formatNumber(val))}</text>`;
    }
    const coords = points.map((p, i) => {
      const x = points.length === 1 ? left + plotW / 2 : left + (i / (points.length - 1)) * plotW;
      const y = top + plotH - ((Number(p.value) || 0) / max) * plotH;
      return [x, y];
    });
    svg += `<polyline points="${coords.map((c) => c.join(",")).join(" ")}" class="line-path"/>`;
    coords.forEach(([x, y], i) => {
      const p = points[i];
      svg += `<circle cx="${x}" cy="${y}" r="4.5" class="line-dot"><title>${escapeHTML(p.label)}: ${escapeHTML(formatNumber(p.value))}</title></circle>`;
      const label = String(p.label).length > 14 ? String(p.label).slice(0, 12) + "…" : String(p.label);
      svg += `<text x="${x}" y="${top+plotH+18}" text-anchor="end" transform="rotate(-38 ${x} ${top+plotH+18})" class="axis-text">${escapeHTML(label)}</text>`;
    });
    svg += `</svg>`;
    els.chartWrap.innerHTML = svg;
  }

  async function loadChart() {
    if (!state.selectedId || !els.xSelect.value) return renderEmptyChart("Select a dataset and X/category column.");
    els.chartError.textContent = "";
    const params = new URLSearchParams({
      x: els.xSelect.value,
      y: els.ySelect.value || "",
      agg: els.aggSelect.value,
      sort: els.sortSelect.value,
      limit: els.groupLimitSelect.value
    });
    const filters = filterPayload();
    if (filters.length) params.set("filters", JSON.stringify(filters));
    try {
      const payload = await getJSON(`/api/datasets/${encodeURIComponent(state.selectedId)}/chart?${params.toString()}`);
      els.chartTitle.textContent = `${payload.metricLabel} by ${payload.x}`;
      els.chartMeta.textContent = `${selectedDataset()?.name || state.selectedId} • ${payload.groupsReturned} groups${filters.length ? ` • ${filters.length} filter(s)` : ""}`;
      if (els.chartTypeSelect.value === "line") renderLineChart(payload.points || []);
      else renderBarChart(payload.points || []);
    } catch (error) {
      els.chartError.textContent = error.message;
      renderEmptyChart("Chart unavailable.");
    }
  }

  async function loadRows() {
    if (!state.selectedId) return;
    const params = new URLSearchParams({ offset: String(state.pageOffset), limit: String(state.pageLimit), search: els.searchInput.value.trim() });
    const filters = filterPayload();
    if (filters.length) params.set("filters", JSON.stringify(filters));
    try {
      const payload = await getJSON(`/api/datasets/${encodeURIComponent(state.selectedId)}/rows?${params.toString()}`);
      state.totalRows = payload.total || 0;
      els.tableHead.innerHTML = (payload.columns || []).map((col) => `<th>${escapeHTML(col)}</th>`).join("");
      if (!payload.rows?.length) {
        els.tableBody.innerHTML = `<tr><td colspan="${Math.max(1, payload.columns?.length || 1)}" class="empty-cell">No matching rows.</td></tr>`;
      } else {
        els.tableBody.innerHTML = payload.rows.map((row) => `<tr>${payload.columns.map((col) => `<td title="${escapeHTML(row[col] ?? "")}">${escapeHTML(row[col] ?? "")}</td>`).join("")}</tr>`).join("");
      }
      const start = state.totalRows ? state.pageOffset + 1 : 0;
      const end = Math.min(state.pageOffset + state.pageLimit, state.totalRows);
      els.tableMeta.textContent = `${formatNumber(state.totalRows)} matching rows${payload.searchTruncated ? ` • search limited to first ${formatNumber(payload.searchedRows)}` : ""}`;
      els.pageText.textContent = `${formatNumber(start)}–${formatNumber(end)} of ${formatNumber(state.totalRows)}`;
      els.prevBtn.disabled = state.pageOffset <= 0;
      els.nextBtn.disabled = state.pageOffset + state.pageLimit >= state.totalRows;
    } catch (error) {
      els.tableMeta.textContent = error.message;
      els.tableHead.innerHTML = "";
      els.tableBody.innerHTML = "";
    }
  }

  async function loadSelectedDataset() {
    applySelectedStatus();
    state.pageOffset = 0;
    state.selectedVersion = selectedDataset()?.version ?? null;
    els.searchInput.value = "";
    els.filterValue1.value = "";
    els.filterValue2.value = "";
    try {
      await loadSchema();
      await Promise.all([loadChart(), loadRows()]);
    } catch (error) {
      els.chartError.textContent = error.message;
      renderEmptyChart("Dataset is not ready yet.");
      els.tableMeta.textContent = error.message;
    }
    renderDatasetRegistry();
  }

  async function selectDataset(id) {
    if (!id || id === state.selectedId) return;
    state.selectedId = id;
    els.datasetSelect.value = id;
    await loadSelectedDataset();
  }

  async function refreshCurrent() {
    const ds = selectedDataset();
    if (!ds?.refreshable) return;
    els.refreshCurrentBtn.disabled = true;
    const original = els.refreshCurrentBtn.textContent;
    els.refreshCurrentBtn.textContent = "Refreshing…";
    try {
      await getJSON(`/api/datasets/${encodeURIComponent(ds.id)}/refresh`, { method: "POST" });
      await loadGlobalStatus();
      await loadSelectedDataset();
    } catch (error) {
      els.statusMessage.textContent = error.message;
    } finally {
      els.refreshCurrentBtn.textContent = original;
      applySelectedStatus();
    }
  }

  async function refreshAll() {
    els.refreshAllBtn.disabled = true;
    const original = els.refreshAllBtn.textContent;
    els.refreshAllBtn.textContent = "Started…";
    try {
      await getJSON(`/api/refresh-all`, { method: "POST" });
      setTimeout(async () => { await pollStatus(); }, 1200);
    } catch (error) {
      els.statusMessage.textContent = error.message;
    } finally {
      setTimeout(() => { els.refreshAllBtn.disabled = false; els.refreshAllBtn.textContent = original; }, 1600);
    }
  }

  async function pollStatus() {
    const oldVersion = selectedDataset()?.version ?? null;
    try {
      await loadGlobalStatus();
      const now = selectedDataset();
      if (now && now.version !== oldVersion) {
        state.selectedVersion = now.version;
        await loadSchema();
        await Promise.all([loadChart(), loadRows()]);
      }
    } catch (_) { /* keep current UI while server is temporarily unavailable */ }
  }

  function scheduleFilterRefresh() {
    clearTimeout(state.filterTimer);
    state.filterTimer = setTimeout(() => {
      state.pageOffset = 0;
      loadChart();
      loadRows();
    }, 300);
  }

  els.datasetSelect.addEventListener("change", () => selectDataset(els.datasetSelect.value));
  els.refreshCurrentBtn.addEventListener("click", refreshCurrent);
  els.refreshAllBtn.addEventListener("click", refreshAll);
  [els.xSelect, els.ySelect, els.aggSelect, els.chartTypeSelect, els.sortSelect, els.groupLimitSelect].forEach((el) => el.addEventListener("change", loadChart));
  [els.filterColumn1, els.filterColumn2].forEach((el) => el.addEventListener("change", scheduleFilterRefresh));
  [els.filterValue1, els.filterValue2].forEach((el) => el.addEventListener("input", scheduleFilterRefresh));
  els.clearFiltersBtn.addEventListener("click", () => {
    els.filterColumn1.value = ""; els.filterValue1.value = ""; els.filterColumn2.value = ""; els.filterValue2.value = "";
    state.pageOffset = 0; loadChart(); loadRows();
  });
  els.searchInput.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => { state.pageOffset = 0; loadRows(); }, 300);
  });
  els.pageSizeSelect.addEventListener("change", () => { state.pageLimit = Number(els.pageSizeSelect.value) || 25; state.pageOffset = 0; loadRows(); });
  els.prevBtn.addEventListener("click", () => { state.pageOffset = Math.max(0, state.pageOffset - state.pageLimit); loadRows(); });
  els.nextBtn.addEventListener("click", () => { if (state.pageOffset + state.pageLimit < state.totalRows) { state.pageOffset += state.pageLimit; loadRows(); } });

  async function init() {
    try {
      await loadGlobalStatus({ preserveSelection: false });
      if (state.selectedId) await loadSelectedDataset();
      else renderEmptyChart("No datasets available. Configure a folder or SBDF source in config.json.");
    } catch (error) {
      els.statusMessage.textContent = error.message;
      renderEmptyChart("Could not connect to the backend.");
    }
    state.statusTimer = setInterval(pollStatus, 15000);
  }

  init();
})();
