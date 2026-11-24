// ReelerCoaster Web Application Logic

let currentSourceTab = 'url';
let currentMode = 'irl';
let currentStrategy = 'highlights';
let currentCamMode = 'visual'; // 'visual' or 'preset'
let camBoxCoords = { x: 0.72, y: 0.04, w: 0.25, h: 0.34 }; // normalized 0.0 - 1.0
let selectedFile = null;
let currentJobId = null;
let pollInterval = null;

// Source tab switching (URL vs File)
function switchSourceTab(tab) {
  currentSourceTab = tab;
  const tabUrlBtn = document.getElementById('tabUrlBtn');
  const tabFileBtn = document.getElementById('tabFileBtn');
  const urlContainer = document.getElementById('urlInputContainer');
  const fileContainer = document.getElementById('fileInputContainer');

  if (tab === 'url') {
    tabUrlBtn.classList.add('active');
    tabFileBtn.classList.remove('active');
    urlContainer.classList.remove('hidden');
    fileContainer.classList.add('hidden');
  } else {
    tabFileBtn.classList.add('active');
    tabUrlBtn.classList.remove('active');
    fileContainer.classList.remove('hidden');
    urlContainer.classList.add('hidden');
  }
}

// Strategy selection (Highlights vs Full Series Split)
function selectStrategy(strategy) {
  currentStrategy = strategy;
  const stratHl = document.getElementById('stratHighlights');
  const stratSplit = document.getElementById('stratFullSplit');
  const hlConfig = document.getElementById('highlightsConfig');
  const splitConfig = document.getElementById('fullSplitConfig');

  if (strategy === 'highlights') {
    stratHl.classList.add('active');
    stratSplit.classList.remove('active');
    hlConfig.classList.remove('hidden');
    splitConfig.classList.add('hidden');
  } else {
    stratSplit.classList.add('active');
    stratHl.classList.remove('active');
    splitConfig.classList.remove('hidden');
    hlConfig.classList.add('hidden');
  }
}

function onPartPresetChange(val) {
  const customBox = document.getElementById('customDurationContainer');
  const targetInput = document.getElementById('targetPartDuration');
  if (val === 'custom') {
    customBox.classList.remove('hidden');
  } else {
    customBox.classList.add('hidden');
    targetInput.value = val;
  }
}

// Content Mode (IRL vs Gaming)
function selectMode(mode) {
  currentMode = mode;
  const irlCard = document.getElementById('modeIrl');
  const gamingCard = document.getElementById('modeGaming');
  const gamingOptions = document.getElementById('gamingOptions');

  if (mode === 'irl') {
    irlCard.classList.add('active');
    gamingCard.classList.remove('active');
    gamingOptions.classList.add('hidden');
  } else {
    gamingCard.classList.add('active');
    irlCard.classList.remove('active');
    gamingOptions.classList.remove('hidden');
    // Ensure interactive box is rendered
    setTimeout(updateCamCoordsReadout, 50);
  }
}

// Webcam selection mode (Visual Canvas vs Preset Dropdown)
function switchCamMode(mode) {
  currentCamMode = mode;
  const tabVisual = document.getElementById('tabCamVisual');
  const tabPreset = document.getElementById('tabCamPreset');
  const visualContainer = document.getElementById('camVisualContainer');
  const presetContainer = document.getElementById('camPresetContainer');

  if (mode === 'visual') {
    tabVisual.classList.add('active');
    tabPreset.classList.remove('active');
    visualContainer.classList.remove('hidden');
    presetContainer.classList.add('hidden');
  } else {
    tabPreset.classList.add('active');
    tabVisual.classList.remove('active');
    presetContainer.classList.remove('hidden');
    visualContainer.classList.add('hidden');
  }
}

function onWebcamPresetSelect(val) {
  if (val === 'top_right') setCamBoxPreset(72, 4, 25, 34);
  else if (val === 'top_left') setCamBoxPreset(3, 4, 25, 34);
  else if (val === 'bottom_right') setCamBoxPreset(72, 62, 25, 34);
  else if (val === 'bottom_left') setCamBoxPreset(3, 62, 25, 34);
}

function setCamBoxPreset(xPct, yPct, wPct, hPct) {
  camBoxCoords = {
    x: xPct / 100.0,
    y: yPct / 100.0,
    w: wPct / 100.0,
    h: hPct / 100.0
  };
  const box = document.getElementById('camBox');
  if (box) {
    box.style.left = xPct + '%';
    box.style.top = yPct + '%';
    box.style.width = wPct + '%';
    box.style.height = hPct + '%';
  }
  updateCamCoordsReadout();
}

function updateCamCoordsReadout() {
  const readout = document.getElementById('camCoords');
  if (readout) {
    const x = Math.round(camBoxCoords.x * 100);
    const y = Math.round(camBoxCoords.y * 100);
    const w = Math.round(camBoxCoords.w * 100);
    const h = Math.round(camBoxCoords.h * 100);
    readout.textContent = `📍 X: ${x}% | Y: ${y}% | Размер: ${w}% × ${h}%`;
  }
}

// Draggable & Resizable Webcam Box
function initCamBoxInteractivity() {
  const stage = document.getElementById('camStage');
  const box = document.getElementById('camBox');
  if (!stage || !box) return;

  let isDragging = false;
  let isResizing = false;
  let startX = 0, startY = 0;
  let initBoxX = 0, initBoxY = 0;
  let initBoxW = 0, initBoxH = 0;

  box.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const stageRect = stage.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();

    if (e.target.classList.contains('handle-br')) {
      isResizing = true;
    } else {
      isDragging = true;
    }

    startX = e.clientX;
    startY = e.clientY;
    initBoxX = boxRect.left - stageRect.left;
    initBoxY = boxRect.top - stageRect.top;
    initBoxW = boxRect.width;
    initBoxH = boxRect.height;
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging && !isResizing) return;
    const stageRect = stage.getBoundingClientRect();
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    if (isDragging) {
      let newX = initBoxX + dx;
      let newY = initBoxY + dy;
      newX = Math.max(0, Math.min(stageRect.width - initBoxW, newX));
      newY = Math.max(0, Math.min(stageRect.height - initBoxH, newY));

      const xPct = (newX / stageRect.width) * 100;
      const yPct = (newY / stageRect.height) * 100;

      box.style.left = xPct.toFixed(1) + '%';
      box.style.top = yPct.toFixed(1) + '%';

      camBoxCoords.x = Math.max(0.0, Math.min(1.0, newX / stageRect.width));
      camBoxCoords.y = Math.max(0.0, Math.min(1.0, newY / stageRect.height));
      updateCamCoordsReadout();
    } else if (isResizing) {
      let newW = initBoxW + dx;
      let newH = initBoxH + dy;
      newW = Math.max(30, Math.min(stageRect.width - initBoxX, newW));
      newH = Math.max(30, Math.min(stageRect.height - initBoxY, newH));

      const wPct = (newW / stageRect.width) * 100;
      const hPct = (newH / stageRect.height) * 100;

      box.style.width = wPct.toFixed(1) + '%';
      box.style.height = hPct.toFixed(1) + '%';

      camBoxCoords.w = Math.max(0.05, Math.min(1.0, newW / stageRect.width));
      camBoxCoords.h = Math.max(0.05, Math.min(1.0, newH / stageRect.height));
      updateCamCoordsReadout();
    }
  });

  window.addEventListener('mouseup', () => {
    isDragging = false;
    isResizing = false;
  });
}

// Extract preview frame from video file directly in the browser
function updatePreviewFrameFromFile(file) {
  try {
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.src = URL.createObjectURL(file);
    video.currentTime = 5.0; // Seek 5s in
    video.onseeked = () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 360;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imgUrl = canvas.toDataURL('image/jpeg');
      const stageBg = document.getElementById('camStageBg');
      if (stageBg) {
        stageBg.src = imgUrl;
        stageBg.classList.remove('hidden');
        document.getElementById('camStageMockup').classList.add('hidden');
      }
    };
  } catch (err) {
    console.warn('Frame preview extraction failed', err);
  }
}

// Extract preview frame for URL
async function updatePreviewFrameFromUrl(url) {
  if (!url) return;
  try {
    const formData = new FormData();
    formData.append('url', url);
    const res = await fetch('/api/video/preview-frame', { method: 'POST', body: formData });
    if (res.ok) {
      const data = await res.json();
      if (data.thumbnail_url) {
        const stageBg = document.getElementById('camStageBg');
        if (stageBg) {
          stageBg.src = data.thumbnail_url;
          stageBg.classList.remove('hidden');
          document.getElementById('camStageMockup').classList.add('hidden');
        }
      }
    }
  } catch (e) {
    // Non-fatal
  }
}

function toggleSubtitleStyle(checked) {
  const opts = document.getElementById('subtitleOptions');
  if (checked) {
    opts.classList.remove('hidden');
  } else {
    opts.classList.add('hidden');
  }
}

function handleFileSelected(event) {
  const file = event.target.files[0];
  if (file) {
    selectedFile = file;
    document.getElementById('fileLabel').textContent = `Выбран файл: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} МБ)`;
    updatePreviewFrameFromFile(file);
  }
}

// Drag & drop handlers
const dropzone = document.getElementById('dropzone');
if (dropzone) {
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = '#00f3ff';
  });
  dropzone.addEventListener('dragleave', () => {
    dropzone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
  });
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      selectedFile = e.dataTransfer.files[0];
      document.getElementById('videoFile').files = e.dataTransfer.files;
      document.getElementById('fileLabel').textContent = `Выбран: ${selectedFile.name} (${(selectedFile.size / (1024 * 1024)).toFixed(1)} МБ)`;
      updatePreviewFrameFromFile(selectedFile);
    }
  });
}

// URL input listener for thumbnail preview
const urlInput = document.getElementById('videoUrl');
if (urlInput) {
  urlInput.addEventListener('change', () => {
    const val = urlInput.value.trim();
    if (val) updatePreviewFrameFromUrl(val);
  });
}

async function startGeneration() {
  const startBtn = document.getElementById('startBtn');
  const urlVal = document.getElementById('videoUrl').value.trim();

  if (currentSourceTab === 'url' && !urlVal) {
    alert('Пожалуйста, вставьте ссылку на YouTube или видео!');
    return;
  }
  if (currentSourceTab === 'file' && !selectedFile) {
    alert('Пожалуйста, выберите видео-файл!');
    return;
  }

  // Switch UI to Progress State
  document.getElementById('emptyState').classList.add('hidden');
  document.getElementById('resultsGrid').classList.add('hidden');
  document.getElementById('progressState').classList.remove('hidden');
  startBtn.disabled = true;

  updateProgress(5, 'Отправка задачи на сервер...');
  clearLogs();

  const formData = new FormData();
  formData.append('source_type', currentSourceTab);
  if (currentSourceTab === 'url') {
    formData.append('url', urlVal);
  } else {
    formData.append('file', selectedFile);
  }

  formData.append('mode', currentMode);
  formData.append('split_strategy', currentStrategy);
  formData.append('target_part_duration', document.getElementById('targetPartDuration')?.value || 90);

  if (currentMode === 'gaming') {
    if (currentCamMode === 'visual') {
      formData.append('webcam_position', 'custom');
      formData.append('webcam_box', JSON.stringify(camBoxCoords));
    } else {
      formData.append('webcam_position', document.getElementById('webcamPosition').value);
    }
  } else {
    formData.append('webcam_position', 'none');
  }

  formData.append('enable_subtitles', document.getElementById('enableSubtitles').checked);
  formData.append('subtitle_style', document.getElementById('subtitleStyle').value);
  formData.append('whisper_model', document.getElementById('whisperModel').value);
  formData.append('target_clips', document.getElementById('targetClips').value);
  formData.append('clip_duration', document.getElementById('clipDuration').value);
  formData.append('cleanup_source', document.getElementById('cleanupSource')?.checked ?? true);

  try {
    const res = await fetch('/api/jobs/create', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Ошибка запуска задачи');
    }

    const data = await res.json();
    currentJobId = data.job_id;
    addLog(`Задание зарегистрировано: ID #${currentJobId}`);

    // Poll for status
    pollInterval = setInterval(checkJobStatus, 2000);
  } catch (err) {
    alert('Ошибка: ' + err.message);
    resetToInitial();
  }
}

async function checkJobStatus() {
  if (!currentJobId) return;

  try {
    const res = await fetch(`/api/jobs/${currentJobId}`);
    if (!res.ok) return;

    const data = await res.json();
    updateProgress(data.progress || 0, data.message || 'Обработка...');

    if (data.message) {
      addLog(data.message);
    }

    if (data.status === 'completed') {
      clearInterval(pollInterval);
      showResults(data.result);
      document.getElementById('startBtn').disabled = false;
    } else if (data.status === 'failed') {
      clearInterval(pollInterval);
      alert('Ошибка при обработке: ' + (data.error || 'Неизвестная ошибка'));
      resetToInitial();
    }
  } catch (err) {
    console.error('Polling error', err);
  }
}

function updateProgress(pct, msg) {
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('progressPct').textContent = pct + '%';
  document.getElementById('progressTitle').textContent = msg;
}

function addLog(msg) {
  const logs = document.getElementById('stepsLog');
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${msg}`;
  logs.appendChild(entry);
  logs.scrollTop = logs.scrollHeight;
}

function clearLogs() {
  const logs = document.getElementById('stepsLog');
  logs.innerHTML = '';
}

function showResults(result) {
  document.getElementById('progressState').classList.add('hidden');
  const grid = document.getElementById('resultsGrid');
  grid.innerHTML = '';
  grid.classList.remove('hidden');

  if (!result || !result.clips || result.clips.length === 0) {
    grid.innerHTML = '<div class="empty-desc">Не удалось сформировать клипы. Попробуйте другое видео.</div>';
    return;
  }

  result.clips.forEach(clip => {
    const card = document.createElement('div');
    card.className = 'reel-card';
    card.innerHTML = `
      <video class="reel-player" controls preload="metadata" playsinline>
        <source src="${clip.video_url}" type="video/mp4">
        Ваш браузер не поддерживает видео HTML5.
      </video>
      <div class="reel-info">
        <div>
          <div class="reel-title">${clip.title}</div>
          <div class="reel-duration">⏱ Длительность: ${clip.duration} сек</div>
        </div>
        <a href="${clip.video_url}" download="${clip.filename}" class="btn-download">
          <span>⬇ Скачать Reel (9:16)</span>
        </a>
      </div>
    `;
    grid.appendChild(card);
  });
}

function resetToInitial() {
  document.getElementById('startBtn').disabled = false;
  document.getElementById('progressState').classList.add('hidden');
  document.getElementById('emptyState').classList.remove('hidden');
}

// Initialize on DOM load
window.addEventListener('DOMContentLoaded', () => {
  initCamBoxInteractivity();
  updateCamCoordsReadout();
});
