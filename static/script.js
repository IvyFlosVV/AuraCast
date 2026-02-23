/**
 * AuraCast frontend: upload, dynamic states, playback, script display.
 * State updates driven by API response (Phase 1 mock; Phase 5 will use SSE or polling).
 */

(function () {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const submitBtn = document.getElementById("submit-btn");
  const stateStrip = document.getElementById("state-strip");
  const stateMessage = document.getElementById("state-message");
  const errorPanel = document.getElementById("error-panel");
  const errorMessage = document.getElementById("error-message");
  const dismissErrorBtn = document.getElementById("dismiss-error");
  const resultPanel = document.getElementById("result-panel");
  const audioPlayer = document.getElementById("audio-player");
  const scriptContent = document.getElementById("script-content");

  const STATES = [
    "uploading",
    "parsing",
    "generating_script",
    "synthesizing",
    "ready",
  ];

  function setState(state, message) {
    stateStrip.removeAttribute("hidden");
    stateStrip.setAttribute("data-state", state);
    stateMessage.textContent = message || "";
    stateStrip.querySelectorAll(".state-step").forEach((el) => {
      const step = el.getAttribute("data-step");
      el.classList.remove("active", "done");
      const idx = STATES.indexOf(state);
      const stepIdx = STATES.indexOf(step);
      if (stepIdx < idx) el.classList.add("done");
      else if (step === state) el.classList.add("active");
    });
  }

  function showError(msg) {
    setState("error", "");
    errorMessage.textContent = msg;
    errorPanel.removeAttribute("hidden");
    resultPanel.setAttribute("hidden", "");
  }

  function hideError() {
    errorPanel.setAttribute("hidden", "");
  }

  function showResult(script, audioUrl) {
    stateStrip.setAttribute("hidden", "");
    errorPanel.setAttribute("hidden", "");
    resultPanel.removeAttribute("hidden");

    scriptContent.innerHTML = "";
    script.forEach((line) => {
      const div = document.createElement("div");
      div.className =
        "script-line " +
        (line.speaker === "Host A" ? "script-line--host-a" : "script-line--host-b");
      div.innerHTML =
        '<span class="script-line__speaker">' +
        escapeHtml(line.speaker) +
        "</span><p class=\"script-line__text\">" +
        escapeHtml(line.text) +
        "</p>";
      scriptContent.appendChild(div);
    });

    if (audioUrl) {
      audioPlayer.src = audioUrl;
      audioPlayer.removeAttribute("hidden");
    } else {
      audioPlayer.removeAttribute("src");
      audioPlayer.setAttribute("hidden", "");
    }
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function validateFile() {
    const file = fileInput.files[0];
    if (!file) return "Please select a file.";
    const ext = file.name.split(".").pop().toLowerCase();
    if (ext !== "pdf" && ext !== "epub") return "Only PDF and EPUB files are allowed.";
    const maxMb = 50;
    if (file.size > maxMb * 1024 * 1024) return "File is too large (max " + maxMb + " MB).";
    return null;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = validateFile();
    if (err) {
      showError(err);
      return;
    }

    hideError();
    submitBtn.disabled = true;
    setState("uploading", "Uploading your file…");

    const formData = new FormData(form);
    try {
      const res = await fetch("/api/generate-podcast", {
        method: "POST",
        body: formData,
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        showError(data.error || "Something went wrong.");
        submitBtn.disabled = false;
        return;
      }

      if (data.state === "ready") {
        showResult(data.script || [], data.audio_url || null);
      } else {
        setState(data.state || "ready", data.message || "");
        if (data.script && data.audio_url !== undefined) {
          showResult(data.script, data.audio_url);
        }
      }
    } catch (e) {
      showError("Network error. Please try again.");
    } finally {
      submitBtn.disabled = false;
    }
  });

  dismissErrorBtn.addEventListener("click", hideError);
})();
