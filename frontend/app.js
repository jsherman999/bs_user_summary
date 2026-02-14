const form = document.getElementById("analyze-form");
const statusCard = document.getElementById("status-card");
const statusText = document.getElementById("status-text");
const statusProgressFill = document.getElementById("status-progress-fill");
const statusProgressMeta = document.getElementById("status-progress-meta");
const statusDetailsList = document.getElementById("status-details-list");
const summaryCard = document.getElementById("summary-card");
const summaryText = document.getElementById("summary-text");
const metricsGrid = document.getElementById("metrics-grid");
const topicsList = document.getElementById("topics-list");
const termsList = document.getElementById("terms-list");
const claimsList = document.getElementById("claims-list");
const llmStatus = document.getElementById("llm-status");
const llmAlignmentsList = document.getElementById("llm-alignments-list");
const takesList = document.getElementById("takes-list");
const comparisonList = document.getElementById("comparison-list");
const uncertaintyList = document.getElementById("uncertainty-list");
const honestyList = document.getElementById("honesty-list");
const evidenceList = document.getElementById("evidence-list");
const exportJson = document.getElementById("export-json");
const exportMd = document.getElementById("export-md");
const llmProviderSelect = document.getElementById("llm_provider");
const llmModelSelect = document.getElementById("llm_model");
const llmModelNote = document.getElementById("llm-model-note");
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
  statusProgressFill.style.width = "0%";
  statusProgressMeta.textContent = "0%";
  statusDetailsList.innerHTML = "";
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

function renderList(listEl, entries, formatter, emptyText = "No strong signal from sampled data.") {
  listEl.innerHTML = "";
  for (const entry of entries) {
    const item = document.createElement("li");
    item.textContent = formatter(entry);
    listEl.appendChild(item);
  }
  if (!entries.length && emptyText) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    listEl.appendChild(item);
  }
}

function renderEvidence(evidenceItems) {
  evidenceList.innerHTML = "";
  const maxEvidence = 24;
  for (const entry of evidenceItems.slice(0, maxEvidence)) {
    const node = document.createElement("article");
    node.className = "evidence-card";
    const meta = `${entry.id} | ${entry.created_at || "unknown time"} | ${entry.is_reply ? "reply" : "post"}`;
    node.innerHTML = `
      <div class="evidence-meta">${meta}</div>
      <div>${entry.text || "(no text)"}</div>
    `;
    evidenceList.appendChild(node);
  }

  if (!evidenceItems.length) {
    evidenceList.textContent = "No evidence items were retrieved for this run.";
  }
}

function renderComparison(comparison) {
  if (!comparison) {
    renderList(comparisonList, [], (entry) => entry, "Not enough timestamped data for comparison.");
    return;
  }

  const recent = comparison.recent_window || {};
  const prior = comparison.prior_window || {};
  const delta = comparison.delta || {};

  const lines = [
    `Window days: ${comparison.window_days}`,
    `Recent window items: ${recent.items ?? 0}`,
    `Prior window items: ${prior.items ?? 0}`,
    `Item delta: ${delta.items ?? 0}`,
    `Activity direction: ${delta.activity_direction || "flat"}`,
    `Reply ratio delta: ${delta.reply_ratio ?? 0}`,
  ];

  renderList(comparisonList, lines, (line) => line, "Not enough timestamped data for comparison.");
}

function renderLlmAssessment(assessment) {
  if (!assessment) {
    llmStatus.textContent = "No LLM assessment data in summary.";
    renderList(llmAlignmentsList, [], (line) => line, "No LLM alignments available.");
    return;
  }

  const source = assessment.source || "unknown";
  const status = assessment.status || "unknown";
  const provider = assessment.provider || "n/a";
  const model = assessment.model || "default";
  const usage = assessment.usage || {};

  llmStatus.textContent = `Source: ${source} | Status: ${status} | Provider: ${provider} | Model: ${model} | Tokens in/out: ${usage.input_tokens || 0}/${usage.output_tokens || 0}`;
  renderList(
    llmAlignmentsList,
    assessment.topic_alignments || [],
    (row) =>
      `${row.topic}: ${row.alignment} (confidence ${row.confidence}, mentions ${row.mention_count}; evidence: ${(row.evidence_ids || []).join(", ")})`,
    "No LLM alignments available."
  );
}

function updateStatusProgress(job) {
  const progress = job.progress || {};
  const stage = progress.stage || job.status;
  const message = progress.message || `Job ${job.id}: ${job.status}`;
  const percent = Number(progress.percent || 0);
  const current = Number(progress.current || 0);
  const total = Number(progress.total || 0);
  const meta = progress.meta || {};

  const stageText = stage ? `[${stage}] ` : "";
  const countText = total > 0 ? ` (${current}/${total})` : "";
  statusText.textContent = `${stageText}${message}${countText}`;

  statusProgressFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  statusProgressMeta.textContent = `${percent.toFixed(1)}%`;

  const detailLines = [];
  if (meta.fetched_posts !== undefined || meta.requested_posts !== undefined) {
    detailLines.push(`Fetched: ${meta.fetched_posts ?? 0}/${meta.requested_posts ?? 0} posts`);
  }
  if (meta.posts_analyzed !== undefined || meta.posts_total !== undefined) {
    detailLines.push(`Analyzed: ${meta.posts_analyzed ?? 0}/${meta.posts_total ?? 0} posts`);
  }
  if (meta.chunks_analyzed !== undefined || meta.chunks_total !== undefined) {
    detailLines.push(`LLM chunks: ${meta.chunks_analyzed ?? 0}/${meta.chunks_total ?? 0}`);
  }
  if (meta.provider || meta.model) {
    detailLines.push(`LLM: ${(meta.provider || "n/a")}:${(meta.model || "default")}`);
  }

  renderList(statusDetailsList, detailLines, (line) => line, "");
}

function setModelOptions(models, defaultModel, priorSelection) {
  llmModelSelect.innerHTML = "";

  const autoOption = document.createElement("option");
  autoOption.value = "";
  autoOption.textContent = defaultModel ? `default (${defaultModel})` : "default";
  llmModelSelect.appendChild(autoOption);

  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.free ? `${model.id} (free)` : model.id;
    llmModelSelect.appendChild(option);
  }

  if (priorSelection && [...llmModelSelect.options].some((row) => row.value === priorSelection)) {
    llmModelSelect.value = priorSelection;
  } else {
    llmModelSelect.value = "";
  }
}

async function loadModelOptions() {
  const provider = llmProviderSelect.value;
  const prior = llmModelSelect.value;
  llmModelSelect.innerHTML = "<option value=''>Loading model list...</option>";

  try {
    const freeOnly = provider === "openrouter" ? "true" : "false";
    const payload = await getJson(`/api/llm/models?provider=${encodeURIComponent(provider)}&free_only=${freeOnly}`);
    const models = payload.models || [];
    setModelOptions(models, payload.default_model || "", prior);

    if (payload.error) {
      llmModelNote.textContent = `Model list note: ${payload.error}`;
    } else if (!models.length) {
      llmModelNote.textContent = "No models returned. The selected provider may not be configured.";
    } else {
      llmModelNote.textContent = `Loaded ${models.length} model options from ${payload.provider}.`;
    }
  } catch (error) {
    llmModelSelect.innerHTML = "<option value=''>default</option>";
    llmModelNote.textContent = `Could not load models: ${error.message}`;
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
    updateStatusProgress(job);

    if (job.status === "failed") {
      throw new Error(job.error || "Analysis failed");
    }

    if (job.status === "completed") {
      const summary = await getJson(`/api/summary/${jobId}`);
      return summary;
    }

    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetView();

  const button = form.querySelector("button");
  button.disabled = true;

  const handle = document.getElementById("handle").value.trim();
  const maxItems = Number(document.getElementById("max_items").value || 200);
  const comparisonWindowDays = Number(document.getElementById("comparison_window_days").value || 30);
  const useCache = document.getElementById("use_cache").checked;
  const enableLlm = document.getElementById("enable_llm").checked;
  const llmProvider = document.getElementById("llm_provider").value;
  const llmModel = document.getElementById("llm_model").value.trim();
  const llmMaxPosts = Number(document.getElementById("llm_max_posts").value || 500);

  try {
    const start = await getJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        handle,
        max_items: maxItems,
        comparison_window_days: comparisonWindowDays,
        use_cache: useCache,
        enable_llm: enableLlm,
        llm_provider: llmProvider,
        llm_model: llmModel,
        llm_max_posts: llmMaxPosts,
      }),
    });
    currentJobId = start.job_id;

    const summary = await pollJob(currentJobId);
    setHidden(summaryCard, false);

    exportJson.href = `/api/export/${currentJobId}.json`;
    exportMd.href = `/api/export/${currentJobId}.md`;

    summaryText.textContent = summary.summary_text || "No narrative summary available.";
    renderMetrics(summary.metrics || {});
    renderComparison(summary.comparison || null);

    renderList(topicsList, summary.top_topics || [], (topic) => `${topic.topic}: ${topic.count}`);
    renderList(termsList, summary.top_terms || [], (term) => `${term.term}: ${term.count}`);
    renderList(
      claimsList,
      summary.claims || [],
      (claim) => `${claim.text} (confidence ${claim.confidence}; evidence: ${(claim.evidence_ids || []).join(", ")})`,
      "No grounded claims available."
    );
    renderLlmAssessment(summary.llm_assessment || null);
    renderList(
      takesList,
      summary.takes || [],
      (take) => `${take.statement} (confidence ${take.confidence}; mentions ${take.signal_count})`,
      "No topic takes available from sampled content."
    );
    renderList(
      uncertaintyList,
      summary.uncertainty_notes || [],
      (entry) => entry,
      "No additional uncertainty notes."
    );
    renderList(honestyList, summary.honesty_notes || [], (entry) => entry, "");
    renderEvidence(summary.evidence || []);
  } catch (error) {
    showError(error.message || "Unexpected error.");
  } finally {
    button.disabled = false;
  }
});

llmProviderSelect.addEventListener("change", () => {
  loadModelOptions();
});

loadModelOptions();
