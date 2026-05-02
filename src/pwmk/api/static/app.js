const state = {
  selectedConditionId: null,
  markets: [],
  apiToken: localStorage.getItem("pwmkApiToken") || "",
};

const fmtUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const fmtNum = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return fmtUsd.format(Number(value));
}

function shortId(value) {
  if (!value) return "-";
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

async function getJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.apiToken) headers.set("X-API-Key", state.apiToken);
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function setStatus(text) {
  document.getElementById("snapshot-status").textContent = text;
}

async function loadSummary() {
  const summary = await getJson("/api/summary");
  document.getElementById("metric-volume-24h").textContent = money(summary.active_volume_24h);
  document.getElementById("metric-volume-total").textContent = money(summary.active_volume_total);
  document.getElementById("metric-liquidity").textContent = money(summary.active_liquidity);
  document.getElementById("metric-markets").textContent = fmtNum.format(summary.active_markets || 0);
  document.getElementById("metric-events").textContent = fmtNum.format(summary.events_total || 0);
  document.getElementById("metric-alerts").textContent = fmtNum.format(summary.pending_alerts || 0);
  const lastRun = summary.last_run ? `${summary.last_run.mode}: ${summary.last_run.status}` : "idle";
  setStatus(`Snapshot ${summary.latest_snapshot_at || "-"} | ${lastRun}`);
}

async function loadOps() {
  const [scheduler, momentum, alerts] = await Promise.all([
    getJson("/api/scheduler"),
    getJson("/api/momentum?limit=5"),
    getJson("/api/alerts?limit=5"),
  ]);
  renderScheduler(scheduler);
  renderMomentum(momentum);
  renderAlerts(alerts);
}

async function loadMarkets() {
  const search = document.getElementById("search").value.trim();
  const sort = document.getElementById("sort").value;
  const params = new URLSearchParams({ limit: "100", sort });
  if (search) params.set("search", search);
  state.markets = await getJson(`/api/markets?${params}`);
  renderMarkets();
  if (!state.selectedConditionId && state.markets.length) {
    await selectMarket(state.markets[0].condition_id);
  }
}

function renderMarkets() {
  const body = document.getElementById("markets-body");
  body.innerHTML = "";
  for (const market of state.markets) {
    const tr = document.createElement("tr");
    tr.dataset.conditionId = market.condition_id;
    if (market.condition_id === state.selectedConditionId) tr.classList.add("selected");
    tr.innerHTML = `
      <td>
        <span class="market-title">${escapeHtml(market.question || "-")}</span>
        <span class="market-subtitle">${escapeHtml(market.event_title || market.slug || "")}</span>
      </td>
      <td class="number">${money(market.volume_24h)}</td>
      <td class="number">${money(market.volume_total)}</td>
      <td class="number">${money(market.liquidity)}</td>
    `;
    tr.addEventListener("click", () => selectMarket(market.condition_id));
    body.appendChild(tr);
  }
}

async function selectMarket(conditionId) {
  state.selectedConditionId = conditionId;
  renderMarkets();
  const [detail, series] = await Promise.all([
    getJson(`/api/markets/${conditionId}`),
    getJson(`/api/markets/${conditionId}/aggregates?bucket_size=hour&hours=168`),
  ]);
  renderDetail(detail);
  drawChart(series);
}

function renderScheduler(scheduler) {
  const target = document.getElementById("scheduler-status");
  const tasks = scheduler.tasks && scheduler.tasks.length ? scheduler.tasks.join(", ") : "none";
  target.innerHTML = `
    <div><strong>${scheduler.enabled ? "enabled" : "manual"}</strong></div>
    <div>tasks: ${escapeHtml(tasks)}</div>
    <div>poll: ${scheduler.poll_limit} every ${scheduler.poll_interval_seconds}s</div>
    <div>stream: ${scheduler.stream_enabled ? "enabled" : "disabled"}</div>
  `;
}

function renderMomentum(rows) {
  const target = document.getElementById("momentum-list");
  if (!rows.length) {
    target.innerHTML = "Need at least two snapshots for momentum.";
    return;
  }
  target.innerHTML = rows
    .map(
      (row) => `
        <div class="ops-item">
          <div>
            <strong>${escapeHtml(row.question || "-")}</strong>
            <span>${money(row.previous_volume_24h)} to ${money(row.volume_24h)}</span>
          </div>
          <div class="number">${money(row.volume_24h_change)}</div>
        </div>
      `
    )
    .join("");
}

function renderAlerts(alerts) {
  const target = document.getElementById("alerts-list");
  if (!alerts.length) {
    target.innerHTML = "No alerts.";
    return;
  }
  target.innerHTML = alerts
    .map(
      (alert) => `
        <div class="ops-item">
          <div>
            <strong>${escapeHtml(alert.title || alert.alert_type)}</strong>
            <span>${escapeHtml(alert.message)}</span>
          </div>
          <div>${escapeHtml(alert.severity)}</div>
        </div>
      `
    )
    .join("");
}

function renderDetail(market) {
  const target = document.getElementById("market-detail");
  const tokens = (market.tokens || [])
    .map(
      (token) => `
      <div class="token">
        <span>${escapeHtml(token.outcome || shortId(token.token_id))}</span>
        <strong>${formatProbability(token.outcome_price)}</strong>
      </div>
    `
    )
    .join("");
  target.className = "detail-market";
  target.innerHTML = `
    <h2>${escapeHtml(market.question || "-")}</h2>
    <div class="detail-meta">
      <span class="pill">${escapeHtml(market.event_title || "No event")}</span>
      <span class="pill">${shortId(market.condition_id)}</span>
      <span class="pill">${market.accepting_orders ? "Accepting orders" : "Not accepting orders"}</span>
    </div>
    <div class="token-grid">${tokens || '<div class="detail-empty">No tokens</div>'}</div>
  `;
  renderTrades(market.recent_trades || []);
}

function renderTrades(trades) {
  const target = document.getElementById("trades-list");
  if (!trades.length) {
    target.innerHTML = '<div class="detail-empty">No observed trades</div>';
    return;
  }
  target.innerHTML = trades
    .map((trade) => {
      const sideClass = trade.side === "BUY" ? "side-buy" : "side-sell";
      return `
        <div class="trade-row">
          <div>
            <strong class="${sideClass}">${escapeHtml(trade.side || "-")}</strong>
            <span>${escapeHtml(trade.trade_ts || "")}</span>
          </div>
          <div class="number">${money(trade.notional)} @ ${fmtNum.format(trade.price || 0)}</div>
        </div>
      `;
    })
    .join("");
}

function drawChart(series) {
  const canvas = document.getElementById("volume-chart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  if (!series.length) {
    ctx.fillStyle = "#64748b";
    ctx.font = "14px system-ui";
    ctx.fillText("No series data", 24, 36);
    return;
  }

  const values = series.map((point) =>
    Number(point.volume_24h_last ?? point.volume_24h ?? point.volume_total_delta ?? 0)
  );
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 28;
  const chartWidth = width - pad * 2;
  const chartHeight = height - pad * 2;

  ctx.strokeStyle = "#d8dee8";
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = pad + (chartHeight / 3) * i;
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - pad, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#2f5f9f";
  ctx.lineWidth = 3;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = pad + (chartWidth * index) / Math.max(values.length - 1, 1);
    const y = height - pad - ((value - min) / span) * chartHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#1f2933";
  ctx.font = "12px system-ui";
  ctx.fillText(`24h volume ${money(values.at(-1))}`, pad, 18);
}

function formatProbability(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadMarkets(), loadOps()]);
}

function setupApiToken() {
  const input = document.getElementById("api-token");
  input.value = state.apiToken;
  input.addEventListener("change", () => {
    state.apiToken = input.value.trim();
    if (state.apiToken) localStorage.setItem("pwmkApiToken", state.apiToken);
    else localStorage.removeItem("pwmkApiToken");
    refreshAll().catch((error) => {
      console.error(error);
      setStatus("Dashboard error");
    });
  });
}

document.getElementById("refresh-button").addEventListener("click", async () => {
  await refreshAll();
});

document.getElementById("ingest-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  setStatus("Ingesting");
  try {
    await getJson("/api/ingest/poll?limit=100", { method: "POST" });
    await refreshAll();
  } finally {
    button.disabled = false;
  }
});

document.getElementById("search").addEventListener("input", debounce(loadMarkets, 250));
document.getElementById("sort").addEventListener("change", loadMarkets);
setupApiToken();

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

refreshAll().catch((error) => {
  console.error(error);
  setStatus("Dashboard error");
});
