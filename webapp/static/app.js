"use strict";

const POLL_MS = 2000;

// ---------- Helpers ----------
function $(sel) { return document.querySelector(sel); }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}
const STATUS_COLORS = {
  queued: "badge-grey", running: "badge-blue", completed: "badge-green", failed: "badge-red"
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

// ---------- Voices ----------
async function loadVoices() {
  const sel = $("#voice-select");
  if (!sel) return;
  try {
    const data = await api("/api/voices");
    sel.innerHTML = "<option value=''>Default voice</option>";
    const groups = data.groups || {};
    for (const lang of Object.keys(groups).sort()) {
      const og = el("optgroup");
      og.label = lang.toUpperCase();
      for (const v of groups[lang]) {
        if (v.name.startsWith("en-") || v.name.startsWith("zh-")) {
          const opt = el("option", "", v.label);
          opt.value = v.name;
          og.appendChild(opt);
        }
      }
      if (og.children.length) sel.appendChild(og);
    }
  } catch (e) {
    sel.innerHTML = "<option value=''>Default voice</option>";
    console.error("voices:", e);
  }
}

// =====================================================================
// Generator page
// =====================================================================
let _genPollTimer = null;
let _genJobId = null;

async function _genPoll() {
  if (!_genJobId) return;
  const job = await api(`/api/jobs/${_genJobId}`);
  _genRender(job);
  if (job.status === "completed" || job.status === "failed") {
    clearInterval(_genPollTimer);
    _genPollTimer = null;
  }
}

function _genRender(job) {
  const stBadge = $("#status-badge");
  const stText = $("#status-text");
  const bar = $("#progress-bar");
  if (!stBadge) return;

  stBadge.textContent = job.status;
  stBadge.className = "badge " + (STATUS_COLORS[job.status] || "badge-grey");

  if (job.status === "running" || job.status === "queued") {
    stText.textContent = job.current_scene || "Waiting…";
    if (job.scenes_total > 0) {
      bar.style.width = Math.round((job.scenes_done / job.scenes_total) * 100) + "%";
    }
    _genRenderScenes(job.scenes_detail);
    $("#error-box") && $("#error-box").classList.add("hidden");
  } else if (job.status === "failed") {
    stText.textContent = "Failed";
    const eb = $("#error-box");
    eb.textContent = job.error || "Generation failed.";
    eb.classList.remove("hidden");
  } else if (job.status === "completed") {
    bar.style.width = "100%";
    stText.textContent = "Done";
    _genShowResult(job);
  }
}

function _genRenderScenes(detail) {
  const list = $("#scene-list");
  if (!list) return;
  list.innerHTML = "";
  for (const sc of detail) {
    const li = el("li", "scene-item");
    const dot = el("span", "scene-dot " + (sc.status === "done" ? "dot-done"
      : sc.status === "processing" ? "dot-proc" : "dot-pend"));
    const txt = el("span", "", sc.title || ("Scene " + sc.number));
    li.append(dot, txt);
    list.appendChild(li);
  }
}

function _genShowResult(job) {
  if (!$("#result-card")) return;
  $("#progress-card").classList.add("hidden");
  $("#result-card").classList.remove("hidden");
  const player = $("#video-player");
  player.src = job.video_url;
  $("#download-btn").href = job.video_url;
  if (job.clip_urls && job.clip_urls.length) {
    $("#clip-links").innerHTML =
      "Individual clips: " +
      job.clip_urls.map((u, i) => `<a href="${u}" download>clip ${i + 1}</a>`).join(" · ");
  }
}

function startPolling(jobId) {
  _genJobId = jobId;
  if (_genPollTimer) clearInterval(_genPollTimer);
  _genPollTimer = setInterval(_genPoll, POLL_MS);
  _genPoll();
}

function initGenerator() {
  if (!$("#prompt-clip")) return;
  const btnClip = $("#mode-clip");
  const btnStory = $("#mode-story");
  const formError = $("#form-error");
  const generateBtn = $("#generate-btn");

  function setMode(story) {
    btnClip.classList.toggle("active", !story);
    btnStory.classList.toggle("active", story);
    $("#panel-clip").classList.toggle("hidden", story);
    $("#panel-story").classList.toggle("hidden", !story);
  }
  btnClip.onclick = () => setMode(false);
  btnStory.onclick = () => setMode(true);

  const fileInput = $("#story-file");
  $("#upload-btn").onclick = () => fileInput.click();
  fileInput.onchange = async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    $("#file-name").textContent = file.name;
    $("#story-text").value = await file.text();
  };

  generateBtn.onclick = async () => {
    const story = btnStory.classList.contains("active");
    formError.classList.add("hidden");
    $("#error-box").classList.add("hidden");
    $("#progress-card").classList.remove("hidden");
    $("#result-card").classList.add("hidden");
    $("#progress-bar").style.width = "0%";
    $("#scene-list").innerHTML = "";
    $("#status-badge").className = "badge badge-grey";
    $("#status-badge").textContent = "queued";
    $("#status-text").textContent = "Submitting…";

    const duration = parseInt($("#duration-input").value, 10) || 4;
    const payload = {
      mode: story ? "story" : "clip",
      duration,
      aspect_ratio: $("#ratio-select").value,
      voice: $("#voice-select").value,
      prompt: story ? $("#story-text").value.trim() : $("#prompt-clip").value.trim(),
    };
    if (!payload.prompt) {
      formError.textContent = "Please enter a prompt or story.";
      formError.classList.remove("hidden");
      return;
    }
    try {
      const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
      startPolling(job.id);
    } catch (e) {
      formError.textContent = e.message;
      formError.classList.remove("hidden");
    }
  };

  $("#rerun-btn").onclick = async () => {
    if (!_genJobId) return;
    await api(`/api/jobs/${_genJobId}/rerun`, { method: "POST" });
    $("#result-card").classList.add("hidden");
    $("#progress-card").classList.remove("hidden");
    startPolling(_genJobId);
  };

  // ?live=JOBID support
  const params = new URLSearchParams(window.location.search);
  const liveId = params.get("live");
  if (liveId) {
    api(`/api/jobs/${liveId}`).then((job) => {
      setMode(job.mode === "story");
      startPolling(liveId);
    }).catch(() => {});
  }
}

// =====================================================================
// History page
// =====================================================================
async function initHistory() {
  const tbody = document.querySelector("#history-table tbody");
  if (!tbody) return;

  async function render() {
    const jobs = await api("/api/jobs");
    tbody.innerHTML = "";
    const empty = $("#history-empty");
    if (!jobs.length) { empty.classList.remove("hidden"); return; }
    empty.classList.add("hidden");

    for (const job of jobs) {
      const row = el("tr");
      const preview = job.status === "completed" && job.video_url;

      const tdId = el("td", "mono", job.id.slice(0, 8));
      const tdMode = el("td", "", job.mode === "story" ? "Story" : "Clip");
      const tdPrompt = el("td", "cell-prompt", (job.prompt || "").split("\n")[0].slice(0, 60));
      const tdStatus = el("td", "", "");
      const badge = el("span", "badge " + (STATUS_COLORS[job.status] || "badge-grey"), job.status);
      tdStatus.appendChild(badge);
      const tdScenes = el("td", "", `${job.scenes_done}/${job.scenes_total}`);
      const tdCreated = el("td", "", fmtTime(job.created_at));

      const tdActions = el("td", "");
      if (preview) {
        const play = el("button", "act-btn", "▶");
        play.title = "Preview";
        play.onclick = () => openModal(job);
        tdActions.appendChild(play);
        const dl = el("a", "act-btn act-link", "⬇");
        dl.href = job.video_url;
        dl.download = `story_${job.id}.mp4`;
        tdActions.appendChild(dl);
      } else if (job.status === "running" || job.status === "queued") {
        const live = el("a", "act-btn act-link", "👁");
        live.href = "/?live=" + job.id;
        tdActions.appendChild(live);
      }
      const rerun = el("button", "act-btn", "↻");
      rerun.title = "Re-run";
      rerun.onclick = async () => { await api(`/api/jobs/${job.id}/rerun`, { method: "POST" }); render(); };
      tdActions.appendChild(rerun);

      const del = el("button", "act-btn", "✕");
      del.title = "Delete";
      del.onclick = async () => { await api(`/api/jobs/${job.id}`, { method: "DELETE" }); render(); };
      tdActions.appendChild(del);

      row.append(tdId, tdMode, tdPrompt, tdStatus, tdScenes, tdCreated, tdActions);
      tbody.appendChild(row);
    }
  }

  const modal = $("#player-modal");
  const mVideo = $("#modal-video");
  $("#modal-close").onclick = () => { modal.classList.add("hidden"); mVideo.pause(); };
  modal.onclick = (e) => { if (e.target === modal) { modal.classList.add("hidden"); mVideo.pause(); } };

  function openModal(job) {
    $("#modal-title").textContent = (job.prompt || "").split("\n")[0].slice(0, 40) || "Preview";
    mVideo.src = job.video_url;
    $("#modal-download").href = job.video_url;
    modal.classList.remove("hidden");
  }

  render();
}

// ---------- Boot ----------
loadVoices();
initGenerator();
initHistory();