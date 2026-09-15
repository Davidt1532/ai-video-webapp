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
const FALLBACK_VOICES = [
  { name: "", label: "Auto — smart voice (recommended)" },
  { name: "en-US-ChristopherNeural", label: "Christopher — Deep & dramatic" },
  { name: "en-US-MichelleNeural", label: "Michelle — Bright & lively" },
  { name: "en-GB-RyanNeural", label: "Ryan — British gentleman" },
  { name: "en-GB-SoniaNeural", label: "Sonia — Warm & storytelling" },
  { name: "en-IN-PrabhatNeural", label: "Prabhat — Calm & clear" },
];

async function loadVoices() {
  const sel = $("#voice-select");
  if (!sel) return;
  try {
    const data = await api("/api/voices");
    const list = (data && data.voices && data.voices.length) ? data.voices : FALLBACK_VOICES;
    sel.innerHTML = "";
    for (const v of list) {
      const opt = el("option", "", v.label);
      opt.value = v.name || "";
      sel.appendChild(opt);
    }
  } catch (e) {
    sel.innerHTML = "";
    for (const v of FALLBACK_VOICES) {
      const opt = el("option", "", v.label);
      opt.value = v.name || "";
      sel.appendChild(opt);
    }
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

function _genResetStages() {
  const orb = $("#progress-card");
  orb && orb.classList.remove("orb-done", "orb-fail");
  for (let i = 0; i < 4; i++) {
    const st = $(`#stage-${i}`);
    if (st) { st.classList.remove("done", "active"); st.classList.add("pending"); }
  }
}

function _genSetStage(i, state) {
  const st = $(`#stage-${i}`);
  if (!st) return;
  st.classList.remove("done", "active", "pending");
  st.classList.add(state);
}

function _genRenderStages(job) {
  // state: 0 pending, 1 active, 2 done
  const total = job.scenes_total || 0;
  const done = job.scenes_done || 0;
  const p = total > 0 ? done / total : 0;

  if (job.status === "completed") {
    for (let i = 0; i < 4; i++) _genSetStage(i, "done");
    return;
  }
  if (job.status === "queued") { _genResetStages(); return; }
  if (job.status !== "running") return;

  _genSetStage(0, total > 0 ? "done" : "active");                 // reading story
  _genSetStage(1, total > 0 && p >= 1 ? "done" : "active");       // casting clips
  _genSetStage(2, p >= 1 ? "done" : (p >= 0.6 ? "active" : "pending")); // weaving voice
  _genSetStage(3, p >= 1 ? "active" : "pending");                 // binding film
}

function _genRender(job) {
  const stBadge = $("#status-badge");
  const stText = $("#status-text");
  const bar = $("#progress-bar");
  if (!stBadge) return;

  stBadge.textContent = job.status;
  stBadge.className = "badge " + (STATUS_COLORS[job.status] || "badge-grey");
  const orb = $("#progress-card");

  if (job.status === "running" || job.status === "queued") {
    stText.textContent = job.current_scene || "Waiting for the magic to begin…";
    if (job.scenes_total > 0) {
      bar.style.width = Math.round((job.scenes_done / job.scenes_total) * 100) + "%";
    }
    _genRenderScenes(job.scenes_detail);
    _genRenderStages(job);
    $("#error-box") && $("#error-box").classList.add("hidden");
  } else if (job.status === "failed") {
    stText.textContent = "The spell broke";
    const eb = $("#error-box");
    eb.textContent = job.error || "Generation failed.";
    eb.classList.remove("hidden");
    orb && orb.classList.add("orb-fail");
  } else if (job.status === "completed") {
    bar.style.width = "100%";
    orb && orb.classList.add("orb-done");
    $(".magic-title").textContent = "The spell is complete ✨";
    stText.textContent = "Done";
    _genRenderStages(job);
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

  let refFile = null;
  let refToken = null;

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

  // Character reference image upload
  const refDrop = $("#ref-drop");
  const refInput = $("#ref-file");
  const refPreview = $("#ref-preview");
  const refPlaceholder = $("#ref-placeholder");
  const refRemove = $("#ref-remove");

  function showRefPreview(file) {
    refPreview.src = URL.createObjectURL(file);
    refPreview.classList.remove("hidden");
    refPlaceholder.classList.add("hidden");
    refRemove.classList.remove("hidden");
  }
  function clearRefPreview() {
    refFile = null;
    refToken = null;
    refPreview.src = "";
    refPreview.classList.add("hidden");
    refPlaceholder.classList.remove("hidden");
    refRemove.classList.add("hidden");
  }
  refDrop.onclick = () => refInput.click();
  refInput.onchange = () => {
    const file = refInput.files && refInput.files[0];
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) {
      formError.textContent = "Please choose a PNG, JPG or WebP image.";
      formError.classList.remove("hidden");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      formError.textContent = "Image too large (max 10 MB).";
      formError.classList.remove("hidden");
      return;
    }
    refFile = file;
    showRefPreview(file);
  };
  refRemove.onclick = (e) => { e.stopPropagation(); clearRefPreview(); };

  async function uploadRef(file) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/refs", { method: "POST", body: fd });
    if (!res.ok) {
      let msg = res.statusText;
      try { const j = await res.json(); msg = j.detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    const data = await res.json();
    return data.ref;
  }

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
    $("#status-text").textContent = "Waiting for the magic to begin…";
    $(".magic-title").textContent = "Casting your story into video…";
    _genResetStages();

    const duration = parseInt($("#duration-input").value, 10) || 4;
    const payload = {
      mode: story ? "story" : "clip",
      duration,
      aspect_ratio: $("#ratio-select").value,
      voice: $("#voice-select").value,
      prompt: story ? $("#story-text").value.trim() : $("#prompt-clip").value.trim(),
    };

    if (story) {
      payload.voice_instructions = $("#voice-instructions").value.trim();
      payload.smart_voiceover = $("#smart-voice").checked;
    }

    if (!payload.prompt) {
      formError.textContent = "Please enter a prompt or story.";
      formError.classList.remove("hidden");
      return;
    }

    generateBtn.disabled = true;
    try {
      if (refFile) {
        refToken = await uploadRef(refFile);
        payload.ref_image = refToken;
      }
      const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
      startPolling(job.id);
    } catch (e) {
      formError.textContent = e.message;
      formError.classList.remove("hidden");
    } finally {
      generateBtn.disabled = false;
    }
  };

  $("#rerun-btn").onclick = async () => {
    if (!_genJobId) return;
    await api(`/api/jobs/${_genJobId}/rerun`, { method: "POST" });
    $("#result-card").classList.add("hidden");
    $("#progress-card").classList.remove("hidden");
    $(".magic-title").textContent = "Casting your story into video…";
    _genResetStages();
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