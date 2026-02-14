const form = document.getElementById("analyze-form");
const statusCard = document.getElementById("status-card");
const statusText = document.getElementById("status-text");
const summaryCard = document.getElementById("summary-card");
const summaryText = document.getElementById("summary-text");
const metricsGrid = document.getElementById("metrics-grid");
const topicsList = document.getElementById("topics-list");
const termsList = document.getElementById("terms-list");
const errorCard = document.getElementById("error-card");
const errorText = document.getElementById("error-text");

let currentJobId = null;

function setHidden(el, hidden) {
  if (hidden) {
    el.classList.add("hidden");
  } else {
    el.classList.remove("hidden");
  }
}

function resetView() {
  setHidden(errorCard, true);
  setHidden(summaryCard, true);
  setHidden(statusCard, false);
  statusText.textContent = "Queued...";
}

function showError(message) {
  setHidden(errorCard, false);
  errorText.textContent = message;
}

function formatPct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function renderMetrics(metrics) {
  metricsGrid.innerHTML = "";
  const rows = [
    ["Sample Size", metrics.sample_size],
    ["Posts", metrics.total_posts],
    ["Replies", metrics.total_replies],
    ["Reply Ratio", formatPct(metrics.reply_ratio || 0)],
    ["Active Days", metrics.active_days],
    ["Avg Items/Day", metrics.avg_items_per_day],
    ["Visible Reactions", metrics.total_visible_reactions],
  ];

  for (const [label, value] of rows) {
    const box = document.createElement("div");
    box.className = "metric";
    box.innerHTML = `<div class="label">${label}</div><div class="value">${value ?? "-"}</div>`;
    metricsGrid.appendChild(box);
  }
}

function renderList(listEl, entries, formatter) {
  listEl.innerHTML = "";
  for (const entry of entries) {
    const item = document.createElement("li");
    item.textContent = formatter(entry);
    listEl.appendChild(item);
  }
  if (!entries.length) {
    const item = document.createElement("li");
    item.textContent = "No strong signal from sampled data.";
    listEl.appendChild(item);
  }
}

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload;
}

async function pollJob(jobId) {
  while (true) {
    const job = await getJson(`/api/jobs/${jobId}`);
    statusText.textContent = `Job ${job.id}: ${job.status}`;

    if (job.status === "failed") {
      throw new Error(job.error || "Analysis failed");
    }

    if (job.status === "completed") {
      const summary = await getJson(`/api/summary/${jobId}`);
      return summary;
    }

    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetView();

  const button = form.querySelector("button");
  button.disabled = true;

  const handle = document.getElementById("handle").value.trim();
  const maxItems = Number(document.getElementById("max_items").value || 200);
  const useCache = document.getElementById("use_cache").checked;

  try {
    const start = await getJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        handle,
        max_items: maxItems,
        use_cache: useCache,
      }),
    });
    currentJobId = start.job_id;

    const summary = await pollJob(currentJobId);
    setHidden(summaryCard, false);
    setHidden(statusCard, true);

    summaryText.textContent = summary.summary_text || "No narrative summary available.";
    renderMetrics(summary.metrics || {});
    renderList(topicsList, summary.top_topics || [], (topic) => `${topic.topic}: ${topic.count}`);
    renderList(termsList, summary.top_terms || [], (term) => `${term.term}: ${term.count}`);
  } catch (error) {
    showError(error.message || "Unexpected error.");
  } finally {
    button.disabled = false;
  }
});
