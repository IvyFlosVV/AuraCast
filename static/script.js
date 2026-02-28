/**
 * AuraCast V2 frontend: parse → episode list → generate episode → result. Theme, history, interrupt (Phase 4).
 */

(function () {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const labelText = document.getElementById("label-text");
  const selectedFileDisplay = document.getElementById("selected-file-display");
  const selectedFilename = document.getElementById("selected-filename");
  const submitBtn = document.getElementById("submit-btn");
  const progressSection = document.getElementById("progress-section");
  const progressBar = document.getElementById("progress-bar");
  const progressStatus = document.getElementById("progress-status");
  const errorPanel = document.getElementById("error-panel");
  const errorMessage = document.getElementById("error-message");
  const dismissErrorBtn = document.getElementById("dismiss-error");
  const resultPanel = document.getElementById("result-panel");
  const resultEpisodeTitle = document.getElementById("result-episode-title");
  const audioPlayer = document.getElementById("audio-player");
  const scriptContent = document.getElementById("script-content");
  const themeToggle = document.getElementById("theme-toggle");
  const historySidebar = document.getElementById("history-sidebar");
  const historyList = document.getElementById("history-list");
  const historyEmpty = document.getElementById("history-empty");
  const historyToggle = document.getElementById("history-toggle");
  const historyClose = document.getElementById("history-close");
  const episodeExplorer = document.getElementById("episode-explorer");
  const episodeList = document.getElementById("episode-list");
  const episodeSelectedBlock = document.getElementById("episode-selected-block");
  const episodePromptInput = document.getElementById("episode-prompt");
  const generateEpisodeBtn = document.getElementById("generate-episode-btn");
  const interruptBlock = document.getElementById("interrupt-block");
  const interruptBtn = document.getElementById("interrupt-btn");
  const interruptAskForm = document.getElementById("interrupt-ask-form");
  const interruptQuestionInput = document.getElementById("interrupt-question");
  const interruptAskSubmit = document.getElementById("interrupt-ask-submit");
  const tryDemoBtn = document.getElementById("try-demo-btn");

  let currentUploadId = null;
  let currentEpisodes = [];
  let selectedEpisodeId = null;
  let selectedEpisodeTitle = null;
  let currentEpisodeScript = null;
  let currentMainAudioUrl = null;
  let savedResumeTime = 0;
  let isPlayingInterruptReply = false;

  const HISTORY_KEY = "auracast-history";
  const MAX_FILENAME_LENGTH = 32;

  // Progress stops at 95% until API returns; 100% / "Ready!" only on success
  const STAGED_MESSAGES = [
    { width: 30, text: "Extracting text from eBook..." },
    { width: 70, text: "AI Hosts analyzing narrative and drafting script..." },
    { width: 95, text: "Synthesizing neural voices..." },
  ];
  const STAGED_DURATION_MS = 2400;
  const CHAT_STAGGER_MS = 800;
  const PROGRESS_TRANSITION_MS = 2000;

  let progressTimeouts = [];

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("auracast-theme", theme); } catch (e) {}
  }

  function showError(msg) {
    errorMessage.textContent = msg;
    errorPanel.removeAttribute("hidden");
    resultPanel.setAttribute("hidden", "");
    progressSection.setAttribute("hidden", "");
    submitBtn.removeAttribute("hidden");
    submitBtn.disabled = false;
    if (generateEpisodeBtn) generateEpisodeBtn.disabled = false;
    progressTimeouts.forEach(function (t) { clearTimeout(t); });
    progressTimeouts = [];
  }

  function hideError() {
    errorPanel.setAttribute("hidden", "");
  }

  function setProgress(percent, statusText) {
    progressBar.style.width = percent + "%";
    progressBar.setAttribute("aria-valuenow", percent);
    progressStatus.textContent = statusText;
  }

  function runStagedProgress(onComplete) {
    var stage = 0;
    function next() {
      if (stage >= STAGED_MESSAGES.length) {
        if (onComplete) onComplete();
        return;
      }
      var s = STAGED_MESSAGES[stage];
      setProgress(s.width, s.text);
      stage++;
      var t = setTimeout(next, STAGED_DURATION_MS);
      progressTimeouts.push(t);
    }
    next();
  }

  function showResult(script, audioUrl, episodeTitle) {
    progressTimeouts.forEach(function (t) { clearTimeout(t); });
    progressTimeouts = [];
    setProgress(100, "Ready!");
    progressStatus.textContent = "Ready!";
    currentEpisodeScript = script || [];
    currentMainAudioUrl = audioUrl || null;
    setTimeout(function () {
      progressSection.setAttribute("hidden", "");
      submitBtn.removeAttribute("hidden");
      submitBtn.disabled = false;
      if (generateEpisodeBtn) generateEpisodeBtn.disabled = false;
      errorPanel.setAttribute("hidden", "");
      resultPanel.removeAttribute("hidden");

      if (resultEpisodeTitle) {
        if (episodeTitle) {
          resultEpisodeTitle.textContent = "Episode: " + episodeTitle;
          resultEpisodeTitle.removeAttribute("hidden");
        } else {
          resultEpisodeTitle.setAttribute("hidden", "");
        }
      }

      scriptContent.innerHTML = "";
      if (audioUrl) {
        audioPlayer.src = audioUrl;
        audioPlayer.removeAttribute("hidden");
        if (interruptBlock && currentEpisodeScript && currentEpisodeScript.length) {
          interruptBlock.removeAttribute("hidden");
          if (interruptAskForm) interruptAskForm.setAttribute("hidden", "");
          if (interruptBtn) interruptBtn.removeAttribute("hidden");
        } else if (interruptBlock) {
          interruptBlock.setAttribute("hidden", "");
        }
      } else {
        audioPlayer.removeAttribute("src");
        audioPlayer.setAttribute("hidden", "");
        if (interruptBlock) interruptBlock.setAttribute("hidden", "");
      }
      savedResumeTime = 0;
      isPlayingInterruptReply = false;

      (script || []).forEach(function (line, i) {
        progressTimeouts.push(setTimeout(function () {
          var isHostA = line.speaker === "Host A";
          var row = document.createElement("div");
          row.className = "chat-row chat-row--" + (isHostA ? "host-a" : "host-b");
          var avatarEmoji = isHostA ? "👩‍💻" : "🕵️‍♂️";
          row.innerHTML =
            "<div class=\"chat-avatar chat-avatar--" + (isHostA ? "host-a" : "host-b") + "\" aria-hidden=\"true\">" + avatarEmoji + "</div>" +
            "<div class=\"chat-bubble\">" +
            "<span class=\"chat-bubble__speaker\">" + escapeHtml(line.speaker) + "</span>" +
            "<p class=\"chat-bubble__text\">" + escapeHtml(line.text) + "</p></div>";
          scriptContent.appendChild(row);
        }, i * CHAT_STAGGER_MS));
      });
    }, PROGRESS_TRANSITION_MS);
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function formatFileName(name) {
    if (!name || name.length <= MAX_FILENAME_LENGTH) return name;
    var ext = "";
    var i = name.lastIndexOf(".");
    if (i > 0) {
      ext = name.slice(i);
      name = name.slice(0, i);
    }
    var keep = MAX_FILENAME_LENGTH - ext.length - 3;
    return name.slice(0, Math.max(0, keep)) + "…" + ext;
  }

  function getHistory() {
    try {
      var raw = localStorage.getItem(HISTORY_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory(list) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
    } catch (e) {}
  }

  function removeFromHistory(id) {
    var list = getHistory().filter(function (item) { return item.id !== id; });
    saveHistory(list);
    renderHistory();
  }

  function renderHistory() {
    var list = getHistory();
    historyList.innerHTML = "";
    historyEmpty.style.display = list.length ? "none" : "block";
    list.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "history-list__item";
      li.dataset.historyId = String(item.id);
      li.innerHTML =
        "<div class=\"history-list__content\">" +
        "<span class=\"history-list__name\">" + escapeHtml(item.name || "Untitled") + "</span>" +
        "<span class=\"history-list__date\">" + escapeHtml(item.date || "") + "</span>" +
        "</div>" +
        "<button type=\"button\" class=\"history-list__delete\" aria-label=\"Remove from history\" title=\"Remove from history\">×</button>";
      historyList.appendChild(li);
    });
  }

  function addToHistory(filename) {
    var list = getHistory();
    var name = formatFileName(filename) || "Untitled";
    var date = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
    list.unshift({ id: Date.now(), name: name, fullName: filename, date: date });
    if (list.length > 50) list = list.slice(0, 50);
    saveHistory(list);
    renderHistory();
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

  function renderEpisodeList(episodes) {
    if (!episodeList) return;
    episodeList.innerHTML = "";
    episodes.forEach(function (ep) {
      var li = document.createElement("li");
      li.className = "episode-list__item";
      li.dataset.episodeId = String(ep.id);
      li.dataset.episodeTitle = String(ep.title || "Episode " + ep.id);
      li.textContent = ep.title || "Episode " + ep.id;
      li.setAttribute("role", "button");
      li.setAttribute("tabindex", "0");
      episodeList.appendChild(li);
    });
  }

  function onEpisodeSelected(episodeId, episodeTitle) {
    selectedEpisodeId = episodeId;
    selectedEpisodeTitle = episodeTitle;
    if (episodeSelectedBlock) {
      episodeSelectedBlock.removeAttribute("hidden");
      if (episodePromptInput) episodePromptInput.value = "";
    }
    var items = episodeList ? episodeList.querySelectorAll(".episode-list__item") : [];
    items.forEach(function (el) {
      el.classList.toggle("is-selected", String(el.dataset.episodeId) === String(episodeId));
    });
  }

  if (tryDemoBtn) {
    tryDemoBtn.addEventListener("click", function () {
      hideError();
      tryDemoBtn.disabled = true;
      progressSection.removeAttribute("hidden");
      setProgress(20, "Preparing demo...");
      fetch("/api/demo_episode", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; }); })
        .then(function (_) {
          var res = _.res;
          var data = _.data;
          tryDemoBtn.disabled = false;
          progressSection.setAttribute("hidden", "");
          if (!res.ok) {
            showError(data.error || "Demo failed. Check that ffmpeg is installed.");
            return;
          }
          var script = data.script || [];
          var audioUrl = data.audio_url != null ? data.audio_url : null;
          showResult(script, audioUrl, "Demo");
        })
        .catch(function () {
          showError("Network error. Please try again.");
          tryDemoBtn.disabled = false;
          progressSection.setAttribute("hidden", "");
        });
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var err = validateFile();
    if (err) {
      showError(err);
      return;
    }

    hideError();
    submitBtn.setAttribute("hidden", "");
    progressSection.removeAttribute("hidden");
    setProgress(20, "Extracting text from eBook...");

    var formData = new FormData(form);
    formData.append("language", document.getElementById("setting-language").value);
    formData.append("vibe", document.getElementById("setting-vibe").value);
    fetch("/api/parse", { method: "POST", body: formData })
      .then(function (res) { return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; }); })
      .then(function (_) {
        var res = _.res;
        var data = _.data;
        progressSection.setAttribute("hidden", "");
        submitBtn.removeAttribute("hidden");
        submitBtn.disabled = false;
        if (!res.ok) {
          showError(data.error || "Something went wrong.");
          return;
        }
        currentUploadId = data.upload_id || null;
        currentEpisodes = data.episodes || [];
        selectedEpisodeId = null;
        selectedEpisodeTitle = null;
        if (episodeSelectedBlock) episodeSelectedBlock.setAttribute("hidden", "");
        renderEpisodeList(currentEpisodes);
        if (episodeExplorer) episodeExplorer.removeAttribute("hidden");
        var file = fileInput.files && fileInput.files[0];
        if (file && file.name) addToHistory(file.name);
      })
      .catch(function () {
        showError("Network error. Please try again.");
        progressSection.setAttribute("hidden", "");
        submitBtn.removeAttribute("hidden");
        submitBtn.disabled = false;
      });
  });

  if (episodeList) {
    episodeList.addEventListener("click", function (e) {
      var item = e.target.closest(".episode-list__item");
      if (!item) return;
      onEpisodeSelected(item.dataset.episodeId, item.dataset.episodeTitle || "");
    });
    episodeList.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var item = e.target.closest(".episode-list__item");
      if (!item) return;
      e.preventDefault();
      onEpisodeSelected(item.dataset.episodeId, item.dataset.episodeTitle || "");
    });
  }

  if (generateEpisodeBtn) {
    generateEpisodeBtn.addEventListener("click", function () {
      if (!currentUploadId || selectedEpisodeId == null) {
        showError("Please select an episode first.");
        return;
      }
      hideError();
      generateEpisodeBtn.disabled = true;
      progressSection.removeAttribute("hidden");
      setProgress(30, "Generating episode...");

      var payload = {
        upload_id: currentUploadId,
        episode_id: parseInt(selectedEpisodeId, 10),
        user_prompt: (episodePromptInput && episodePromptInput.value) ? episodePromptInput.value.trim() : ""
      };
      fetch("/api/generate_episode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; }); })
        .then(function (_) {
          var res = _.res;
          var data = _.data;
          if (!res.ok) {
            showError(data.error || "Something went wrong.");
            generateEpisodeBtn.disabled = false;
            progressSection.setAttribute("hidden", "");
            return;
          }
          var script = data.script || [];
          var audioUrl = data.audio_url != null ? data.audio_url : null;
          showResult(script, audioUrl, selectedEpisodeTitle);
        })
        .catch(function () {
          showError("Network error. Please try again.");
          generateEpisodeBtn.disabled = false;
          progressSection.setAttribute("hidden", "");
        });
    });
  }

  dismissErrorBtn.addEventListener("click", hideError);

  themeToggle.addEventListener("click", function () {
    var root = document.documentElement;
    var next = root.getAttribute("data-theme") === "light" ? "" : "light";
    setTheme(next);
  });

  try {
    var saved = localStorage.getItem("auracast-theme");
    if (saved === "light") setTheme("light");
  } catch (e) {}

  fileInput.addEventListener("change", function () {
    var file = fileInput.files[0];
    if (file) {
      var sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      var label = formatFileName(file.name) + " · " + sizeMb + " MB";
      selectedFilename.textContent = label;
      selectedFileDisplay.classList.add("is-visible");
      labelText.textContent = "Change file";
    } else {
      selectedFilename.textContent = "";
      selectedFileDisplay.classList.remove("is-visible");
      labelText.textContent = "Choose PDF or EPUB";
    }
  });

  historyToggle.addEventListener("click", function () {
    historySidebar.classList.add("is-open");
  });
  historyClose.addEventListener("click", function () {
    historySidebar.classList.remove("is-open");
  });
  historyList.addEventListener("click", function (e) {
    var btn = e.target.closest(".history-list__delete");
    if (!btn) return;
    var li = btn.closest(".history-list__item");
    if (!li || !li.dataset.historyId) return;
    e.preventDefault();
    e.stopPropagation();
    removeFromHistory(Number(li.dataset.historyId));
  });
  renderHistory();

  function resumeMainAudio() {
    isPlayingInterruptReply = false;
    if (interruptAskForm) interruptAskForm.setAttribute("hidden", "");
    if (interruptBtn) interruptBtn.removeAttribute("hidden");
    if (interruptQuestionInput) interruptQuestionInput.value = "";
    if (currentMainAudioUrl && audioPlayer) {
      audioPlayer.src = currentMainAudioUrl;
      audioPlayer.currentTime = savedResumeTime;
      audioPlayer.play().catch(function () {});
    }
  }

  if (audioPlayer) {
    audioPlayer.addEventListener("ended", function () {
      if (isPlayingInterruptReply) resumeMainAudio();
    });
  }

  if (interruptBtn) {
    interruptBtn.addEventListener("click", function () {
      if (!audioPlayer || !currentEpisodeScript || !currentMainAudioUrl) return;
      audioPlayer.pause();
      savedResumeTime = audioPlayer.currentTime;
      if (interruptAskForm) interruptAskForm.removeAttribute("hidden");
      interruptBtn.setAttribute("hidden", "");
      if (interruptQuestionInput) interruptQuestionInput.focus();
    });
  }

  if (interruptAskSubmit && interruptQuestionInput) {
    interruptAskSubmit.addEventListener("click", function () {
      var question = interruptQuestionInput.value.trim();
      if (!question) return;
      if (!currentEpisodeScript || currentEpisodeScript.length === 0) {
        showError("No episode script available.");
        return;
      }
      interruptAskSubmit.disabled = true;
      fetch("/api/ask_hosts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, episode_script: currentEpisodeScript })
      })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; }); })
        .then(function (_) {
          interruptAskSubmit.disabled = false;
          if (!_.res.ok) {
            showError(_.data.error || "Something went wrong.");
            if (interruptBtn) interruptBtn.removeAttribute("hidden");
            if (interruptAskForm) interruptAskForm.setAttribute("hidden", "");
            return;
          }
          var audioUrl = _.data.audio_url;
          if (audioUrl && audioPlayer) {
            isPlayingInterruptReply = true;
            audioPlayer.src = audioUrl;
            audioPlayer.play().catch(function () {
              isPlayingInterruptReply = false;
              resumeMainAudio();
            });
          } else {
            if (interruptBtn) interruptBtn.removeAttribute("hidden");
            if (interruptAskForm) interruptAskForm.setAttribute("hidden", "");
          }
        })
        .catch(function () {
          interruptAskSubmit.disabled = false;
          showError("Network error. Please try again.");
          if (interruptBtn) interruptBtn.removeAttribute("hidden");
          if (interruptAskForm) interruptAskForm.setAttribute("hidden", "");
        });
    });
  }
})();
