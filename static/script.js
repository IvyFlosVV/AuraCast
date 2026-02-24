/**
 * AuraCast frontend: theme toggle, upload, staged progress bar, chat bubbles with staggered animation.
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
  const audioPlayer = document.getElementById("audio-player");
  const scriptContent = document.getElementById("script-content");
  const themeToggle = document.getElementById("theme-toggle");
  const historySidebar = document.getElementById("history-sidebar");
  const historyList = document.getElementById("history-list");
  const historyEmpty = document.getElementById("history-empty");
  const historyToggle = document.getElementById("history-toggle");
  const historyClose = document.getElementById("history-close");

  const HISTORY_KEY = "auracast-history";
  const MAX_FILENAME_LENGTH = 32;

  const STAGED_MESSAGES = [
    { width: 30, text: "Extracting text from eBook..." },
    { width: 70, text: "AI Hosts analyzing narrative and drafting script..." },
    { width: 95, text: "Synthesizing neural voices..." },
    { width: 100, text: "Ready!" },
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

  function showResult(script, audioUrl) {
    progressTimeouts.forEach(function (t) { clearTimeout(t); });
    progressTimeouts = [];
    setProgress(100, "Ready!");
    progressStatus.textContent = "Ready!";
    setTimeout(function () {
      progressSection.setAttribute("hidden", "");
      submitBtn.removeAttribute("hidden");
      submitBtn.disabled = false;
      errorPanel.setAttribute("hidden", "");
      resultPanel.removeAttribute("hidden");

      scriptContent.innerHTML = "";
      if (audioUrl) {
        audioPlayer.src = audioUrl;
        audioPlayer.removeAttribute("hidden");
      } else {
        audioPlayer.removeAttribute("src");
        audioPlayer.setAttribute("hidden", "");
      }

      script.forEach(function (line, i) {
        progressTimeouts.push(setTimeout(function () {
          var isHostA = line.speaker === "Host A";
          var row = document.createElement("div");
          row.className = "chat-row chat-row--" + (isHostA ? "host-a" : "host-b");
          row.innerHTML =
            "<div class=\"chat-avatar chat-avatar--" + (isHostA ? "host-a" : "host-b") + "\" aria-hidden=\"true\"></div>" +
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

  function renderHistory() {
    var list = getHistory();
    historyList.innerHTML = "";
    historyEmpty.style.display = list.length ? "none" : "block";
    list.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "history-list__item";
      li.innerHTML =
        "<span class=\"history-list__name\">" + escapeHtml(item.name || "Untitled") + "</span>" +
        "<span class=\"history-list__date\">" + escapeHtml(item.date || "") + "</span>";
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
    setProgress(0, "Extracting text from eBook...");
    runStagedProgress();

    var formData = new FormData(form);
    formData.append("language", document.getElementById("setting-language").value);
    formData.append("vibe", document.getElementById("setting-vibe").value);
    fetch("/api/generate-podcast", { method: "POST", body: formData })
      .then(function (res) { return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; }); })
      .then(function (_) {
        var res = _.res;
        var data = _.data;
        if (!res.ok) {
          showError(data.error || "Something went wrong.");
          return;
        }
        var script = (data.state === "ready" ? data.script : data.script) || [];
        var audioUrl = data.audio_url != null ? data.audio_url : null;
        var file = fileInput.files && fileInput.files[0];
        if (file && file.name) addToHistory(file.name);
        showResult(script, audioUrl);
      })
      .catch(function () {
        showError("Network error. Please try again.");
      });
  });

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
  renderHistory();
})();
