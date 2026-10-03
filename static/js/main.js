// main.js
let sessionId = null;
let filePath = null;
let currentViews = [];
let currentSlideIndex = 0;
let currentData = null;
let isTemplateData = true;
let interactiveModelLoaded = false;
let modelData = {};
var analysisData = null;
var currentAnalysisMode = 'all'; // 'rbf' | 'kriging' | 'all'
var drillViewsCache = null; // 缓存钻孔示意图结果，避免重复请求
let hasClickedModeling = false; // 用户是否点击过建模示意图


// DOM 元素
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFileBtn = document.getElementById('removeFile');
const statusMessage = document.getElementById('statusMessage');
const resultsSection = document.getElementById('resultsSection');
const btnDrillViews = document.getElementById('btnDrillViews');
const btnModelViews = document.getElementById('btnModelViews');
const btnAIModeling = document.getElementById('btnAIModeling');
const btnInteractive = document.getElementById('btnInteractive');

const fullscreenModal = document.getElementById('fullscreenModal');
const fullscreenImage = document.getElementById('fullscreenImage');
const fullscreenClose = document.getElementById('fullscreenClose');

const interactiveModal = document.getElementById('interactiveModal');
const interactiveClose = document.getElementById('interactiveClose');

// ==================== 工具函数 ====================
function setStatus(message, type = 'info') {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message';
    if (type) statusMessage.classList.add(type);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function updateButtonStates() {
    var hasFile = !!sessionId;
    var hasModelViews = modelData && modelData.color_map && Object.keys(modelData.color_map).length > 0;
    var hasAISelected = modelData && modelData.ai && modelData.ai.selected_index !== undefined;
    var btnMultiviewAI = document.getElementById('btnMultiviewAI');
    var krigAnalysis = document.getElementById('btnKrigingAnalysis');
    var btnAnalyzeRBF = document.getElementById('btnAnalyzeRBF');

    btnDrillViews.disabled = !hasFile;
    btnModelViews.disabled = !hasFile;
    btnInteractive.disabled = !hasFile;
    btnAIModeling.disabled = !hasModelViews;
    btnKriging.disabled = !hasFile;
    if (krigAnalysis) krigAnalysis.disabled = !hasFile;
    if (btnMultiviewAI) btnMultiviewAI.disabled = !hasAISelected;
    if (btnAnalyzeRBF) btnAnalyzeRBF.disabled = !hasFile;
}

// ==================== 统一卡片渲染 ====================
function renderUniformCard(imgSrc, label, onZoom) {
    var card = document.createElement('div');
    card.className = 'uniform-card';
    var wrapper = document.createElement('div');
    wrapper.className = 'card-img-wrapper';
    var img = document.createElement('img');
    img.src = imgSrc;
    img.alt = label || '';
    img.onerror = function() { this.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect fill='%23f0f0f0' width='400' height='300'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23999' font-size='16'%3E图片加载失败%3C/text%3E%3C/svg%3E"; };
    wrapper.appendChild(img);
    var zoomBtn = document.createElement('button');
    zoomBtn.className = 'uniform-zoom-btn';
    zoomBtn.innerHTML = '🔍';
    zoomBtn.title = '放大查看';
    zoomBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        openFullscreen(imgSrc);
    });
    wrapper.appendChild(zoomBtn);
    card.appendChild(wrapper);
    if (label) {
        var title = document.createElement('div');
        title.className = 'card-title';
        title.textContent = label;
        card.appendChild(title);
    }
    return card;
}

function renderUniformCarousel(container, views, title) {
    container.innerHTML = '';
    var uid = 'uc-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6);
    var currentIdx = 0;

    var viewport = document.createElement('div');
    viewport.className = 'uniform-card';
    viewport.id = uid + '-viewport';

    var wrapper = document.createElement('div');
    wrapper.className = 'card-img-wrapper';
    wrapper.style.position = 'relative';

    var img = document.createElement('img');
    img.id = uid + '-img';
    img.src = views[0].url;
    img.alt = views[0].label || '';
    img.style.cssText = 'width:100%;max-height:500px;object-fit:contain;background:#f8f9fc;display:block;';
    img.onerror = function() { this.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect fill='%23f0f0f0' width='400' height='300'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23999' font-size='16'%3E图片加载失败%3C/text%3E%3C/svg%3E"; };

    var zoomBtn = document.createElement('button');
    zoomBtn.className = 'uniform-zoom-btn';
    zoomBtn.innerHTML = '🔍';
    zoomBtn.title = '放大查看';
    zoomBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        openFullscreen(views[currentIdx].url);
    });
    wrapper.appendChild(img);
    wrapper.appendChild(zoomBtn);
    viewport.appendChild(wrapper);

    var label = document.createElement('div');
    label.className = 'card-title';
    label.id = uid + '-label';
    label.textContent = views[0].label || '';
    viewport.appendChild(label);
    container.appendChild(viewport);

    // Controls
    var ctrl = document.createElement('div');
    ctrl.style.cssText = 'display:flex;justify-content:center;align-items:center;gap:16px;margin-top:12px;';

    var prevBtn = document.createElement('button');
    prevBtn.textContent = '‹';
    prevBtn.style.cssText = 'width:36px;height:36px;border-radius:50%;border:1px solid #ddd;background:#fff;font-size:18px;cursor:pointer;';
    prevBtn.addEventListener('click', function() {
        currentIdx = (currentIdx - 1 + views.length) % views.length;
        updateView();
    });

    var dotsDiv = document.createElement('div');
    dotsDiv.style.cssText = 'display:flex;gap:6px;';
    var dots = [];
    for (var i = 0; i < views.length; i++) {
        var dot = document.createElement('button');
        dot.style.cssText = 'width:10px;height:10px;border-radius:50%;background:' + (i === 0 ? '#1565C0' : '#ddd') + ';border:none;cursor:pointer;';
        dot.addEventListener('click', (function(idx) { return function() { currentIdx = idx; updateView(); }; })(i));
        dotsDiv.appendChild(dot);
        dots.push(dot);
    }

    var nextBtn = document.createElement('button');
    nextBtn.textContent = '›';
    nextBtn.style.cssText = 'width:36px;height:36px;border-radius:50%;border:1px solid #ddd;background:#fff;font-size:18px;cursor:pointer;';
    nextBtn.addEventListener('click', function() {
        currentIdx = (currentIdx + 1) % views.length;
        updateView();
    });

    ctrl.appendChild(prevBtn);
    ctrl.appendChild(dotsDiv);
    ctrl.appendChild(nextBtn);
    container.appendChild(ctrl);

    function updateView() {
        var v = views[currentIdx];
        document.getElementById(uid + '-img').src = v.url;
        document.getElementById(uid + '-label').textContent = v.label || '';
        for (var i = 0; i < dots.length; i++) {
            dots[i].style.background = i === currentIdx ? '#1565C0' : '#ddd';
        }
    }

    // Return navigation helpers for linked carousel
    return {
        goTo: function(idx) { currentIdx = idx; updateView(); },
        getIndex: function() { return currentIdx; },
        length: views.length
    };
}

function renderLinkedCarousel(container, leftViews, rightViews, leftLabel, rightLabel) {
    container.innerHTML = '';
    container.className = 'linked-carousel';

    var leftPane = document.createElement('div');
    leftPane.className = 'linked-pane';
    var leftCard = renderUniformCard(leftViews[0].url, (leftLabel || '') + ' - ' + (leftViews[0].label || ''), null);
    leftPane.appendChild(leftCard);

    var rightPane = document.createElement('div');
    rightPane.className = 'linked-pane';
    var rightCard = renderUniformCard(rightViews[0].url, (rightLabel || '') + ' - ' + (rightViews[0].label || ''), null);
    rightPane.appendChild(rightCard);

    container.appendChild(leftPane);
    container.appendChild(rightPane);

    var n = Math.max(leftViews.length, rightViews.length);
    var currentIdx = 0;

    var ctrl = document.createElement('div');
    ctrl.className = 'linked-controls';

    var prevBtn = document.createElement('button');
    prevBtn.className = 'lc-btn';
    prevBtn.textContent = '‹';
    prevBtn.addEventListener('click', function() {
        currentIdx = (currentIdx - 1 + n) % n;
        syncView();
    });

    var labelSpan = document.createElement('span');
    labelSpan.className = 'lc-label';

    var dotsDiv = document.createElement('div');
    dotsDiv.className = 'lc-dots';
    var dots = [];
    for (var i = 0; i < n; i++) {
        var dot = document.createElement('button');
        dot.className = 'lc-dot' + (i === 0 ? ' active' : '');
        dot.addEventListener('click', (function(idx) { return function() { currentIdx = idx; syncView(); }; })(i));
        dotsDiv.appendChild(dot);
        dots.push(dot);
    }

    var nextBtn = document.createElement('button');
    nextBtn.className = 'lc-btn';
    nextBtn.textContent = '›';
    nextBtn.addEventListener('click', function() {
        currentIdx = (currentIdx + 1) % n;
        syncView();
    });

    ctrl.appendChild(prevBtn);
    ctrl.appendChild(dotsDiv);
    ctrl.appendChild(nextBtn);
    container.appendChild(ctrl);

    function syncView() {
        // Update left
        var li = Math.min(currentIdx, leftViews.length - 1);
        leftCard.querySelector('img').src = leftViews[li].url;
        var lt = leftCard.querySelector('.card-title');
        if (lt) lt.textContent = (leftLabel || '') + ' - ' + (leftViews[li].label || '');

        // Update right
        var ri = Math.min(currentIdx, rightViews.length - 1);
        rightCard.querySelector('img').src = rightViews[ri].url;
        var rt = rightCard.querySelector('.card-title');
        if (rt) rt.textContent = (rightLabel || '') + ' - ' + (rightViews[ri].label || '');

        // Update label
        var idxLabel = (currentIdx + 1) + ' / ' + n;
        labelSpan.textContent = idxLabel;

        // Update dots
        for (var i = 0; i < dots.length; i++) {
            dots[i].className = 'lc-dot' + (i === currentIdx ? ' active' : '');
        }
    }
    syncView();
}

// ==================== 文件上传 ====================
uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
        handleFile(fileInput.files[0]);
    }
});

removeFileBtn.addEventListener('click', () => {
    drillViewsCache = null;
    fileInput.value = '';
    fileInfo.style.display = 'none';
    uploadArea.style.display = 'block';
    sessionId = null;
    filePath = null;
    updateButtonStates();
    if (currentData) {
        updatePreviewData(currentData, true);
        isTemplateData = true;
    }
    // 重置结果区域：恢复钻孔计算器
    var resultsSection = document.getElementById('resultsSection');
    if (resultsSection) {
        resultsSection.classList.remove('visible');
        resultsSection.innerHTML = '<div id="drillModelContainer" style="flex:1;width:100%;min-height:0;border-radius:8px;overflow:hidden;background:#f0f0f0;">' +
            '<iframe src="/static/drillAngleExplain.HTML" style="width:100%;height:100%;border:none;" allowfullscreen></iframe>' +
            '</div><div id="resultsContent"></div>';
        resultsSection.style.display = '';
    }
    hideResultTabs();
    setStatus('等待上传文件...', 'info');
});

// ==================== 按钮"计算中"状态管理 ====================
/**
 * 按钮→所属 timer 容器的映射
 */
const BTN_TIMER_MAP = {
    btnDrillViews: 'visTimer',
    btnModelViews: 'visTimer',
    btnInteractive: 'visTimer',
    btnAIModeling: 'visTimer',
    btnMultiviewAI: 'visTimer',
    btnKriging: 'interpTimer',
    btnKrigingAnalysis: 'interpTimer',
    btnAnalyzeRBF: 'interpTimer'
};

/** 每个容器内当前活跃的 timer 控制器 */
const _timerInstances = {};

/**
 * 启动按钮的"计算中"状态
 * 提示文字显示在分组下方的固定容器中，不干扰按钮布局
 * @param {HTMLElement} btn - 目标按钮
 * @param {string} label - 提示文字，如"钻孔绘制中"
 * @returns {Object} - 返回一个控制器，用于更新计时器文字
 */
function startButtonTimer(btn, label) {
    if (!btn) return null;

    // 1. 按钮变灰
    btn.classList.add('loading');
    btn.disabled = true;

    // 2. 找到所属的固定 timer 容器
    var containerId = BTN_TIMER_MAP[btn.id];
    var container = containerId ? document.getElementById(containerId) : null;
    if (!container) {
        // 容错：没有映射或找不到容器时，退回到原来的行内模式
        return _fallbackTimer(btn, label);
    }

    // 停止同组之前的 timer
    if (_timerInstances[containerId]) {
        _timerInstances[containerId].stop();
    }

    // 3. 创建/复用容器内的 timer 元素
    var timerEl = container.querySelector('.btn-timer');
    if (!timerEl) {
        timerEl = document.createElement('div');
        timerEl.className = 'btn-timer';
        container.appendChild(timerEl);
    }
    timerEl.classList.remove('hidden');

    // 4. 计时器逻辑
    const startTime = Date.now();
    let timerId = null;

    function formatTime(seconds) {
        if (seconds < 60) {
            return seconds + 's';
        }
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        return m + '分' + s + '秒';
    }

    function updateText() {
        var elapsed = Math.floor((Date.now() - startTime) / 1000);
        timerEl.innerHTML = label + '（已用时 ' + formatTime(elapsed) + '）';
    }

    updateText();
    timerId = setInterval(updateText, 1000);

    // 5. 返回控制器
    var ctrl = {
        stop: function () {
            if (timerId) {
                clearInterval(timerId);
                timerId = null;
            }
            btn.classList.remove('loading');
            btn.disabled = false;
            timerEl.classList.add('hidden');
            delete _timerInstances[containerId];
        }
    };
    _timerInstances[containerId] = ctrl;
    return ctrl;
}

/** 行内模式 fallback — 当固定容器不可用时 */
function _fallbackTimer(btn, label) {
    if (!btn) return null;
    btn.classList.add('loading');
    btn.disabled = true;
    let timerEl = btn.nextElementSibling;
    if (!timerEl || !timerEl.classList.contains('btn-timer')) {
        timerEl = document.createElement('div');
        timerEl.className = 'btn-timer';
        btn.parentNode.insertBefore(timerEl, btn.nextSibling);
    }
    timerEl.classList.remove('hidden');
    const startTime = Date.now();
    let timerId = null;
    function formatTime(s) { return s < 60 ? s + 's' : Math.floor(s / 60) + '分' + (s % 60) + '秒'; }
    function updateText() { timerEl.innerHTML = label + '（已用时 ' + formatTime(Math.floor((Date.now() - startTime) / 1000)) + '）'; }
    updateText();
    timerId = setInterval(updateText, 1000);
    return {
        stop: function () {
            if (timerId) { clearInterval(timerId); timerId = null; }
            btn.classList.remove('loading');
            btn.disabled = false;
            timerEl.classList.add('hidden');
        }
    };
}

// ==================== 预览地图（用于数据弹窗中的地图Tab）====================
let previewMap = null;
let previewMarkerGroup = [];
let previewMapInitialized = false;

const zj_key = window.ZJ_TIANDITU_KEY || '';

// ==================== 生成钻孔示意图 ====================
/** 在右侧显示钻孔示意图（从数据渲染） */
function renderDrillViews(views) {
    var drillContainer = document.getElementById('drillModelContainer');
    if (drillContainer) drillContainer.style.display = 'none';
    var resultsSection = document.getElementById('resultsSection');
    if (resultsSection) {
        resultsSection.innerHTML = '';
        resultsSection.classList.add('visible', 'carousel-fill');
    }
    var viewItems = views.map(function(v) { return { url: v.url, label: v.label || '', user_tip: v.user_tip || '' }; });
    var div = document.createElement('div');
    if (resultsSection) resultsSection.appendChild(div);
    renderUniformCarousel(div, viewItems, '');
    hideResultTabs();
}

btnDrillViews.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    // 有缓存 → 直接显示，不请求 API
    if (drillViewsCache) {
        currentViews = drillViewsCache;
        currentSlideIndex = 0;
        renderDrillViews(drillViewsCache);
        setStatus('==> 使用缓存结果，共 ' + drillViewsCache.length + ' 张图', 'success');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在生成钻孔示意图...', 'loading');

    const timer = startButtonTimer(btnDrillViews, '钻孔绘制中');

    try {
        const response = await fetch('/api/generate_drill_views', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, path: filePath })
        });
        const data = await response.json();
        stopLogPolling();

        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            if (timer) timer.stop();
            return;
        }

        currentViews = data.views;
        currentSlideIndex = 0;
        // 存入缓存
        drillViewsCache = data.views;
        renderDrillViews(data.views);
        setStatus('==> 生成完成，共 ' + currentViews.length + ' 张图', 'success');
        if (timer) timer.stop();

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        if (timer) timer.stop();
    }
});

// ==================== 生成建模示意图 ====================
btnModelViews.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    hasClickedModeling = true;
    currentAnalysisMode = 'rbf';

    // 隐藏钻孔模型容器
    const drillContainer = document.getElementById('drillModelContainer');
    if (drillContainer) {
        drillContainer.style.display = 'none';
    }
    const resultsSection = document.getElementById('resultsSection');
    if (resultsSection) {
        resultsSection.innerHTML = '';
        resultsSection.classList.remove('visible');
    }
    // 显示加载提示
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'modelLoading';
    loadingDiv.style.cssText = 'text-align:center;padding:40px;font-size:16px;color:#666;';
    loadingDiv.innerHTML = '⏳ 正在生成建模示意图，请稍候...';
    if (resultsSection) {
        resultsSection.appendChild(loadingDiv);
        resultsSection.classList.add('visible');
    }

    startLogPolling(sessionId);
    setStatus('正在生成建模示意图...', 'loading');

    const timer = startButtonTimer(btnModelViews, '建模绘制中');

    try {
        const response = await fetch('/api/generate_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, path: filePath })
        });
        const data = await response.json();
        stopLogPolling();

        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            if (timer) timer.stop();
            if (drillContainer) drillContainer.style.display = 'flex';
            return;
        }

        modelData = data;

        // 移除加载提示
        const loadingEl = document.getElementById('modelLoading');
        if (loadingEl) loadingEl.remove();

        // 渲染结果（保持你原有的逻辑）
        if (resultsSection) {
            resultsSection.innerHTML = '';
            resultsSection.classList.add('visible');
        }

        if (data.labeled_views && data.labeled_views.length > 0 &&
            data.unlabeled_views && data.unlabeled_views.length > 0) {
            // 标注版和无标注版联动轮播
            var cont = document.createElement('div');
            resultsSection.appendChild(cont);
            var labeledViews = data.labeled_views.map(function(v) { return { url: v.url, label: v.label || '' }; });
            var unlabeledViews = data.unlabeled_views.map(function(v) { return { url: v.url, label: v.label || '' }; });
            renderLinkedCarousel(cont, labeledViews, unlabeledViews, '标注版', '无标注版');
        } else {
            // 只有其中一种时，用统一轮播
            if (data.labeled_views && data.labeled_views.length > 0) {
                var labeledViews = data.labeled_views.map(function(v) { return { url: v.url, label: '标注-' + (v.label || ''), user_tip: v.user_tip || '' }; });
                var div = document.createElement('div');
                div.style.marginBottom = '16px';
                resultsSection.appendChild(div);
                renderUniformCarousel(div, labeledViews, '');
            }

            if (data.unlabeled_views && data.unlabeled_views.length > 0) {
                var unlabeledViews = data.unlabeled_views.map(function(v) { return { url: v.url, label: '无标注-' + (v.label || ''), user_tip: v.user_tip || '' }; });
                var div = document.createElement('div');
                div.style.marginBottom = '16px';
                resultsSection.appendChild(div);
                renderUniformCarousel(div, unlabeledViews, '');
            }
        }

        if (data.color_map && Object.keys(data.color_map).length > 0) {
            modelData.color_map = data.color_map;
        }

        updateButtonStates();
        // 建模示意图有数据报告，显示 tabs
        showResultTabs();

        if (data.from_cache) {
            setStatus('==> 使用缓存结果（来自上次计算）', 'success');
        } else {
            setStatus('==> 多视角建模示意图生成完成', 'success');
        }
        if (timer) timer.stop();

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        if (timer) timer.stop();
    }
});

// ==================== AI建模 ====================
btnAIModeling.addEventListener('click', async () => {
    if (!modelData || !modelData.color_map || Object.keys(modelData.color_map).length === 0) {
        setStatus('!!! 请先生成建模示意图', 'error');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在进行AI建模，请稍候...', 'loading');

    const timer = startButtonTimer(btnAIModeling, 'AI 建模中');

    try {
        const response = await fetch('/api/ai_modeling', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                color_map: modelData.color_map,
                file_path: filePath
            })
        });
        const data = await response.json();
        stopLogPolling();

        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            if (timer) timer.stop();
            return;
        }

        // 阶段 2：渲染候选图
        renderAICandidates(data);
        updateButtonStates();
        showResultTabs();

        if (data.is_close) {
            setStatus('==> AI建模完成，两张候选评分接近，请人工对比选择', 'success');
        } else if (data.from_cache) {
            setStatus('==> 使用缓存结果（来自上次计算）', 'success');
        } else {
            setStatus('==> AI建模完成，推荐候选 ' + data.best_index, 'success');
        }
        if (timer) timer.stop();

    } catch (error) {
        stopLogPolling();
        setStatus('!!! AI建模失败: ' + error.message, 'error');
        if (timer) timer.stop();
    }
});

// ==================== AI 候选图展示 ====================
function renderAICandidates(data) {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    let html = '<h2>AI 建模结果（候选图）</h2>';
    html += '<div class="uniform-grid">';

    for (const c of data.candidates) {
        const isBest = (c.index === data.best_index);
        const scoreText = (c.scores && c.scores.total_score !== undefined)
            ? '综合评分: ' + (c.scores.total_score * 100).toFixed(1)
            : '';
        const ssimText = (c.scores && c.scores.ssim !== undefined)
            ? '几何相似度: ' + (c.scores.ssim * 100).toFixed(1)
            : '';

        html += '<div class="uniform-card" data-index="' + c.index + '" style="' + (isBest ? 'border:2px solid #2E7D32;' : '') + '">';
        if (isBest) {
            html += '<div style="position:absolute;top:12px;right:12px;background:#2E7D32;color:white;padding:4px 10px;border-radius:4px;font-size:12px;font-weight:bold;z-index:10;">推荐</div>';
        }
        html += '<div class="card-img-wrapper" style="cursor:default;">';
        html += '<img src="' + c.url + '" alt="AI 候选 ' + c.index + '" style="width:100%;max-height:400px;object-fit:contain;background:#f8f9fc;display:block;">';
        html += '</div>';
        html += '<div class="card-title">候选 ' + c.index;
        if (scoreText) html += ' | ' + scoreText;
        if (ssimText) html += ' | ' + ssimText;
        html += '</div>';
        html += '<div style="padding:8px 16px 12px;text-align:center;">';
        html += '<button class="btn-select" data-index="' + c.index + '" style="width:100%;">使用这张</button>';
        html += '</div>';
        html += '</div>';
    }

    html += '</div>';

    if (data.is_close) {
        html += '<p class="close-hint">💡 两张图评分接近，建议人工对比选择。</p>';
    }

    resultsSection.innerHTML = html;

    // 绑定选择按钮
    document.querySelectorAll('.btn-select').forEach(btn => {
        btn.addEventListener('click', function() {
            const selectedIndex = parseInt(this.dataset.index);
            selectAICandidate(selectedIndex, data);
        });
    });
}

function selectAICandidate(index, data) {
    // 保存用户选择到 modelData
    if (!modelData.ai) modelData.ai = {};
    modelData.ai.selected_index = index;

    // 找到选中候选的路径
    const selected = data.candidates.find(c => c.index === index);
    if (selected) {
        modelData.ai.best_image_path = selected.path;
        modelData.ai.best_image_url = selected.url;
    }

    // 高亮选中的卡片
    document.querySelectorAll('.uniform-card').forEach(card => {
        card.style.border = '';
        if (parseInt(card.dataset.index) === index) {
            card.style.border = '2px solid #1565C0';
        }
    });

    setStatus('==> 已选择候选 ' + index, 'success');
    updateButtonStates();
}

// ==================== 交互式3D模型（弹窗展示 - Tab版） ====================
btnInteractive.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在生成交互式模型，请稍候...', 'loading');

    const timer = startButtonTimer(btnInteractive, '交互式模型生成中');

    try {
        // 1. 生成钻孔专用模型（仅钻孔，不含地质体）
        var drillResp = await fetch('/api/interactive_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                path: filePath,
                mode: 'drill_only'
            })
        });
        var drillData = await drillResp.json();

        if (drillData.error) {
            setStatus('!!! 钻孔模型生成失败: ' + drillData.error, 'error');
            if (timer) timer.stop();
            return;
        }

        var drillHtmlUrl = drillData.html_url;
        var content = document.getElementById('interactiveContent');
        if (!content) {
            setStatus('!!! 弹窗容器未找到', 'error');
            if (timer) timer.stop();
            return;
        }

        // 2. 构建Tab页面
        var html = '';

        // Tab 栏
        html += '<div class="interactive-tab-bar">';
        html += '<button class="interactive-tab active" data-tab="drill">🔬 钻孔3D模型</button>';
        if (hasClickedModeling) {
            html += '<button class="interactive-tab" data-tab="geology">🏔️ 地质体模型</button>';
        }
        html += '</div>';

        // Tab 内容区域
        html += '<div class="interactive-tab-contents">';
        html += '<div class="interactive-tab-content active" id="tab-drill">';
        html += '<div class="interactive-frame-content">';
        html += '<iframe src="' + drillHtmlUrl + '"></iframe>';
        html += '</div>';
        html += '</div>';
        if (hasClickedModeling) {
            html += '<div class="interactive-tab-content" id="tab-geology">';
            html += '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;">';
            html += '<p style="color:#999;font-size:16px;">💡 点击地质体模型选项卡后加载</p>';
            html += '</div>';
            html += '</div>';
        }
        html += '</div>';

        content.innerHTML = html;

        // 3. 绑定 Tab 切换事件
        document.querySelectorAll('.interactive-tab').forEach(tab => {
            tab.addEventListener('click', async function() {
                var tabName = this.dataset.tab;

                // 切换 Tab 高亮
                document.querySelectorAll('.interactive-tab').forEach(t => t.classList.remove('active'));
                this.classList.add('active');

                // 切换内容
                document.querySelectorAll('.interactive-tab-content').forEach(tc => tc.classList.remove('active'));
                var targetContent = document.getElementById('tab-' + tabName);
                if (targetContent) targetContent.classList.add('active');

                // 如果是地质体tab，懒加载地质体模型
                if (tabName === 'geology') {
                    var geologyContent = document.getElementById('tab-geology');
                    // 检查是否已经加载了地质体模型（是否有 iframe）
                    if (geologyContent && !geologyContent.querySelector('iframe')) {
                        geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;">';
                        geologyContent.innerHTML += '<p style="color:#666;font-size:16px;">⏳ 正在加载地质体模型...</p>';
                        geologyContent.innerHTML += '</div>';

                        try {
                            var fullResp = await fetch('/api/interactive_model', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    session_id: sessionId,
                                    path: filePath,
                                    mode: 'full'
                                })
                            });
                            var fullData = await fullResp.json();

                            if (!fullData.error && fullData.html_url) {
                                geologyContent.innerHTML = '<div class="interactive-frame-content">';
                                geologyContent.innerHTML += '<iframe src="' + fullData.html_url + '"></iframe>';
                                geologyContent.innerHTML += '</div>';
                            } else {
                                geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;">';
                                geologyContent.innerHTML += '<p style="color:#e74c3c;font-size:16px;">地质体模型生成失败</p>';
                                geologyContent.innerHTML += '</div>';
                            }
                        } catch(e) {
                            geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;">';
                            geologyContent.innerHTML += '<p style="color:#e74c3c;font-size:16px;">加载失败: ' + e.message + '</p>';
                            geologyContent.innerHTML += '</div>';
                        }
                    }
                }
            });
        });

        // 4. 打开弹窗
        var modal = document.getElementById('interactiveModal');
        if (modal) modal.classList.add('active');

        setStatus('==> 交互式3D模型已加载', 'success');
        if (timer) timer.stop();

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        if (timer) timer.stop();
    }
});

// ==================== 多视角 AI 生成 ====================
const btnKriging = document.getElementById('btnKriging');
const btnMultiviewAI = document.getElementById('btnMultiviewAI');
if (btnMultiviewAI) {
    btnMultiviewAI.addEventListener('click', async () => {
        if (!sessionId) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }

        if (!modelData || !modelData.color_map || Object.keys(modelData.color_map).length === 0) {
            setStatus('!!! 请先生成建模图', 'error');
            return;
        }

        const viewCountStr = prompt('生成几张视角？（1~4）', '3');
        if (!viewCountStr) return;

        const count = parseInt(viewCountStr);
        if (isNaN(count) || count < 1 || count > 4) {
            setStatus('!!! 请输入 1~4 之间的数字', 'error');
            return;
        }

        startLogPolling(sessionId);
        setStatus('正在进行多视角纹理升级...', 'loading');
        const timer = startButtonTimer(btnMultiviewAI, '纹理升级中');

        try {
            const response = await fetch('/api/multiview_texture_upgrade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    view_count: count,
                    color_map: modelData.color_map,
                    file_path: filePath
                })
            });
            const data = await response.json();
            stopLogPolling();

            if (data.error) {
                setStatus('!!! ' + data.error, 'error');
                if (timer) timer.stop();
                return;
            }

            renderMultiviewResults(data);
            updateButtonStates();
            showResultTabs();
            setStatus('==> 纹理升级完成（成功 ' + data.success_count + '/' + data.total_count + '）', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            setStatus('!!! 生成失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

// ==================== 克里金分析 ====================
if (btnKriging) {
    btnKriging.addEventListener('click', async () => {
        if (!sessionId || !filePath) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }

        currentAnalysisMode = 'kriging';

        // 隐藏钻孔模型容器
        const drillContainer = document.getElementById('drillModelContainer');
        if (drillContainer) {
            drillContainer.style.display = 'none';
        }
        const resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.innerHTML = '';
            resultsSection.classList.remove('visible');
        }

        // 显示加载提示
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'krigingLoading';
        loadingDiv.style.cssText = 'text-align:center;padding:40px;font-size:16px;color:#666;';
        loadingDiv.innerHTML = '⏳ 正在执行克里金插值分析（含 RBF 对比），请稍候...';
        if (resultsSection) {
            resultsSection.appendChild(loadingDiv);
            resultsSection.classList.add('visible');
        }

        startLogPolling(sessionId);
        setStatus('正在执行克里金插值分析...', 'loading');

        const timer = startButtonTimer(btnKriging, '克里金分析中');

        try {
            const response = await fetch('/api/kriging_analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, path: filePath })
            });
            const data = await response.json();
            stopLogPolling();

            if (data.error) {
                setStatus('!!! ' + data.error, 'error');
                if (timer) timer.stop();
                if (drillContainer) drillContainer.style.display = 'flex';
                return;
            }

            // 移除加载提示
            const loadingEl = document.getElementById('krigingLoading');
            if (loadingEl) loadingEl.remove();

            renderKrigingResults(data);
            updateButtonStates();
            showResultTabs();
            if (data.from_cache) {
                setStatus('==> 使用缓存结果（来自上次计算）', 'success');
            } else {
                setStatus('==> 克里金分析完成，共分析 ' + data.layer_count + ' 个岩性层', 'success');
            }
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            setStatus('!!! 克里金分析失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

function renderKrigingResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    // 即使没有图片，也尝试显示报告
    var hasImages = data && data.comparison_paths && data.comparison_paths.length > 0;
    var reportText = (data && data.analysis_text) || '暂无分析报告数据';
    var layerCount = (data && data.layer_count) || 0;

    var html = '<h2>📊 克里金 vs RBF 对比分析</h2>';

    if (hasImages) {
        html += '<p style="color:#666;font-size:13px;margin-bottom:12px;">';
        html += '分析完成，共 ' + layerCount + ' 个岩性层。';
        html += '每张图为 2×2 并排布局（左上:克里金 / 右上:RBF / 左下:预测标准差 / 右下:差值）。';
        html += '</p>';

        if (data.comparison_paths.length > 1) {
            html += '<div class="kriging-layer-selector" id="krigingLayerSelector">';
            for (var i = 0; i < data.comparison_paths.length; i++) {
                var activeClass = i === 0 ? 'active' : '';
                html += '<button class="kriging-layer-btn ' + activeClass + '" data-index="' + i + '">' + data.comparison_paths[i].lith + '</button>';
            }
            html += '</div>';
        }

        html += '<div class="uniform-card" style="margin-bottom:16px;">';
        html += '<div id="krigingComparisonDisplay">';
        html += '<div class="card-img-wrapper" style="cursor:pointer;" onclick="openFullscreen(\'' + data.comparison_paths[0].url + '\')">';
        html += '<img src="' + data.comparison_paths[0].url + '?t=' + Date.now() + '" alt="克里金对比分析图" style="width:100%;max-height:600px;object-fit:contain;background:#f8f9fc;display:block;">';
        html += '</div>';
        html += '</div>';
        html += '</div>';
    }

    // ===== 分析报告（可折叠，默认展开） =====
    html += '<div class="kriging-analysis-report">';
    html += '<div class="kriging-report-header" id="krigingReportToggle">';
    html += '<span class="kriging-report-title">📋 数值分析报告</span>';
    html += '<span style="display:flex;align-items:center;gap:8px;">';
    html += '<button class="btn-report-download" id="btnReportDownload" title="下载报告">⬇ 导出</button>';
    html += '<span class="kriging-report-toggle open" id="krigingReportArrow">▶</span>';
    html += '</span>';
    html += '</div>';
    html += '<div class="kriging-report-body" id="krigingReportBody">';
    // 用 textContent 安全地设置报告文本，防止特殊字符破坏 HTML
    html += '<pre id="krigingReportPre"></pre>';
    html += '</div>';
    html += '</div>';

    resultsSection.innerHTML = html;

    // 安全地设置报告文本（避免 innerHTML 对特殊字符的解析问题）
    var preEl = document.getElementById('krigingReportPre');
    if (preEl) {
        preEl.textContent = reportText;
    }

    // 绑定层选择事件
    var selector = document.getElementById('krigingLayerSelector');
    if (selector) {
        selector.addEventListener('click', function(e) {
            var btn = e.target.closest('.kriging-layer-btn');
            if (!btn) return;

            selector.querySelectorAll('.kriging-layer-btn').forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');

            var index = parseInt(btn.dataset.index);
            var path = data.comparison_paths[index].url;
            var display = document.getElementById('krigingComparisonDisplay');
            display.innerHTML = '<div class="card-img-wrapper" style="cursor:pointer;" onclick="openFullscreen(\'' + path + '\')">' +
                '<img src="' + path + '?t=' + Date.now() + '" alt="克里金对比分析图" style="width:100%;max-height:600px;object-fit:contain;background:#f8f9fc;display:block;"></div>';
        });
    }

    // 绑定报告折叠事件
    var reportHeader = document.getElementById('krigingReportToggle');
    var reportBody = document.getElementById('krigingReportBody');
    var reportArrow = document.getElementById('krigingReportArrow');
    if (reportHeader && reportBody && reportArrow) {
        reportHeader.addEventListener('click', function(e) {
            if (e.target.closest('#btnReportDownload')) return;
            reportBody.classList.toggle('collapsed');
            reportArrow.classList.toggle('open');
        });
    }

    // 绑定报告下载事件
    var downloadBtn = document.getElementById('btnReportDownload');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var text = reportText;
            var now = new Date();
            var dateStr = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');
            var filename = '克里金分析报告_' + dateStr + '.txt';
            var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            setStatus('==> 分析报告已导出: ' + filename, 'success');
        });
    }
}

function renderMultiviewResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    let html = '<h2>多视角纹理升级结果</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:12px;">成功生成 ' + data.success_count + '/' + data.total_count + ' 张。</p>';

    html += '<div class="uniform-grid">';
    for (const img of data.images) {
        html += '<div class="uniform-card">';
        html += '<div class="card-title" style="border-top:none;background:#f5f5f5;font-weight:700;color:#333;">' + img.view_label + '</div>';
        html += '<div class="card-img-wrapper" style="cursor:default;">';
        html += '<img src="' + img.url + '" alt="' + img.view_label + '" style="width:100%;max-height:350px;object-fit:contain;background:#f8f9fc;display:block;">';
        html += '</div>';
        html += '<div style="padding:8px 16px;text-align:center;">';
        html += '<a href="' + img.url + '" download class="btn-download" style="display:inline-block;padding:6px 16px;background:#1565C0;color:white;border-radius:4px;text-decoration:none;font-size:13px;">下载</a>';
        html += '</div>';
        html += '</div>';
    }
    html += '</div>';

    resultsSection.innerHTML = html;
}

// ==================== 轮播及功能 ====================
function renderCarousel(views, title) {
    const container = document.getElementById('resultsSection');
    container.innerHTML = ''; // 清空，用于单轮播（钻孔、AI）
    container.classList.add('visible');
    renderCarouselToElement(container, views, title);
}

function renderCarouselToElement(container, views, title) {
    if (!container) return;
    if (!views || views.length === 0) {
        container.innerHTML = '<p>没有可显示的图片</p>';
        return;
    }

    const uid = 'carousel-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6);
    let html = `<h2>${title}</h2>`;
    html += `<div class="carousel-container" id="${uid}">`;
    html += '<div class="carousel-viewport">';
    html += '<div class="carousel-track" id="track-' + uid + '">';
    for (let i = 0; i < views.length; i++) {
        const view = views[i];
        html += `
            <div class="carousel-slide">
                <img src="${view.url}" alt="${view.label}" 
                     onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22800%22 height=%22600%22%3E%3Crect fill=%22%23f0f0f0%22 width=%22800%22 height=%22600%22/%3E%3Ctext x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22 font-size=%2220%22%3E图片加载失败%3C/text%3E%3C/svg%3E'">
                <button class="btn-zoom" onclick="openFullscreen('${view.url}')" title="放大查看">🔍</button>
            </div>
        `;
    }
    html += '</div></div>';
    html += '<div class="carousel-controls">';
    html += `<button class="carousel-btn" data-action="prev" data-uid="${uid}">‹</button>`;
    html += `<span class="carousel-label" id="label-${uid}" title="${views[0].user_tip || ''}">${views[0].label} <span style="cursor:help;color:#1565C0;font-size:12px;">ℹ️</span></span>`;
    html += '<div class="carousel-indicators" id="indicators-' + uid + '">';
    for (let i = 0; i < views.length; i++) {
        html += `<button class="carousel-dot ${i === 0 ? 'active' : ''}" data-index="${i}" data-uid="${uid}"></button>`;
    }
    html += '</div>';
    html += `<button class="carousel-btn" data-action="next" data-uid="${uid}">›</button>`;
    html += '</div>';
    // 下载按钮
    html += `<div style="display:flex; justify-content:center; gap:12px; margin-top:12px; flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="downloadCurrentView('${uid}')">📥 下载当前图</button>
        <button class="btn btn-primary" onclick="downloadAllViews('${uid}')">📥 下载全部</button>
    </div>`;
    html += '</div>';

    container.innerHTML += html; // 追加（用于多个轮播）

    // 初始化状态
    const state = { views: views, currentIndex: 0, uid: uid };
    const containerEl = document.getElementById(uid);
    containerEl._carouselState = state;

    // 绑定事件
    containerEl.querySelector('[data-action="prev"]').addEventListener('click', function() {
        const st = containerEl._carouselState;
        st.currentIndex = (st.currentIndex - 1 + st.views.length) % st.views.length;
        updateCarousel(containerEl);
    });
    containerEl.querySelector('[data-action="next"]').addEventListener('click', function() {
        const st = containerEl._carouselState;
        st.currentIndex = (st.currentIndex + 1) % st.views.length;
        updateCarousel(containerEl);
    });
    containerEl.querySelectorAll('.carousel-dot').forEach(dot => {
        dot.addEventListener('click', function() {
            const idx = parseInt(this.dataset.index);
            const st = containerEl._carouselState;
            st.currentIndex = idx;
            updateCarousel(containerEl);
        });
    });
    updateCarousel(containerEl);
}

function updateCarousel(container) {
    const state = container._carouselState;
    if (!state) return;
    const track = container.querySelector('.carousel-track');
    const label = container.querySelector('.carousel-label');
    const dots = container.querySelectorAll('.carousel-dot');
    if (!track || !label) return;
    
    const currentView = state.views[state.currentIndex];
    track.style.transform = `translateX(-${state.currentIndex * 100}%)`;
    
    // 更新标签文本和悬浮提示
    if (currentView) {
        label.innerHTML = `${currentView.label} <span style="cursor:help;color:#1565C0;font-size:12px;">ℹ️</span>`;
        label.setAttribute('title', currentView.user_tip || '');
    } else {
        label.textContent = '';
        label.removeAttribute('title');
    }
    
    dots.forEach((dot, i) => {
        dot.classList.toggle('active', i === state.currentIndex);
    });
}

function downloadCurrentView(uid) {
    const container = document.getElementById(uid);
    if (!container) return;
    const state = container._carouselState;
    if (!state) return;
    const view = state.views[state.currentIndex];
    if (view) downloadImage(view.url);
}

// 一次性下载带标注的钻孔图
function downloadAllViews(uid) {
    const container = document.getElementById(uid);
    if (!container) return;
    const state = container._carouselState;
    if (!state) return;
    const urls = state.views.map(v => v.url);
    downloadAllAsZip(urls, 'drill_views.zip');
}

function downloadImage(url) {
    const link = document.createElement('a');
    link.href = url;
    link.download = url.split('/').pop();  // 从 URL 提取文件名
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// 以ZIP打包方式一次性下载相关图片
async function downloadAllAsZip(urls, zipName) {
    if (!urls || urls.length === 0) {
        alert('没有可下载的图片');
        return;
    }
    try {
        const response = await fetch('/api/download_zip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: urls, zip_name: zipName })
        });
        if (!response.ok) {
            const err = await response.json();
            alert('下载失败: ' + (err.error || '未知错误'));
            return;
        }
        const blob = await response.blob();
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = zipName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    } catch (e) {
        alert('下载失败: ' + e.message);
    }
}


// 全局暴露函数
window.downloadCurrentView = downloadCurrentView;
window.downloadAllViews = downloadAllViews;

// ==================== 高级参数管理 ====================
let currentParams = {};
let currentParamsMeta = {};
let savedParamsHash = '';

// 加载参数元信息和当前值
async function loadSessionParams() {
    if (!sessionId) return;

    try {
        const response = await fetch(`/api/session_params?session_id=${sessionId}`);
        const data = await response.json();

        if (data.success) {
            currentParamsMeta = data.meta || {};
            savedParamsHash = data.params_hash || '';

            // 先从 localStorage 读取（优先级更高）
            const localSaved = localStorage.getItem(`params_${sessionId}`);
            let params = data.params || {};

            if (localSaved) {
                try {
                    const parsed = JSON.parse(localSaved);
                    params = { ...params, ...parsed };
                } catch (e) {}
            }

            currentParams = params;
            renderParamsUI();
        }
    } catch (error) {
        console.error('加载参数失败:', error);
    }
}

// 渲染参数 UI
function renderParamsUI() {
    const container = document.getElementById('paramsContent');
    const loading = document.getElementById('paramsLoading');
    const applyBtn = document.getElementById('btnApplyParams');
    if (!container || !loading) return;

    loading.style.display = 'none';
    container.style.display = 'block';
    if (applyBtn) applyBtn.style.display = 'block';

    // 按 group 分组
    const groups = {};
    const groupOrder = ['RBF 插值参数', '克里金参数', '建模参数', '钻孔显示参数'];
    for (const [key, meta] of Object.entries(currentParamsMeta)) {
        const g = meta.group || '';
        if (!groups[g]) groups[g] = [];
        groups[g].push({ key, meta });
    }

    let html = '';
    // 先渲染有 group 的（按 groupOrder 排序），再渲染无 group 的
    const renderedGroups = new Set();
    for (const groupName of groupOrder) {
        if (!groups[groupName]) continue;
        renderedGroups.add(groupName);
        html += `<div class="param-group-title">${groupName}</div>`;
        for (const { key, meta } of groups[groupName]) {
            const value = currentParams[key] !== undefined ? currentParams[key] : meta.default;
            html += renderParamItem(key, meta, value);
        }
    }
    // 剩余无 group 或未在 groupOrder 中的
    for (const [groupName, items] of Object.entries(groups)) {
        if (renderedGroups.has(groupName)) continue;
        if (groupName) {
            html += `<div class="param-group-title">${groupName}</div>`;
        }
        for (const { key, meta } of items) {
            const value = currentParams[key] !== undefined ? currentParams[key] : meta.default;
            html += renderParamItem(key, meta, value);
        }
    }
    container.innerHTML = html;

    // 绑定事件
    for (const key of Object.keys(currentParamsMeta)) {
        const meta = currentParamsMeta[key];
        if (meta.type === 'number') {
            const slider = document.getElementById(`param_${key}_slider`);
            const input = document.getElementById(`param_${key}_input`);
            if (slider && input) {
                slider.addEventListener('input', () => {
                    input.value = slider.value;
                });
                input.addEventListener('input', () => {
                    slider.value = input.value;
                });
            }
        } else if (meta.type === 'number_or_auto') {
            const slider = document.getElementById(`param_${key}_slider`);
            const input = document.getElementById(`param_${key}_input`);
            const autoCheck = document.getElementById(`param_${key}_auto`);
            if (slider && input && autoCheck) {
                autoCheck.addEventListener('change', () => {
                    const isAuto = autoCheck.checked;
                    slider.disabled = isAuto;
                    input.disabled = isAuto;
                });
                // 初始化
                if (value === null || value === undefined) {
                    autoCheck.checked = true;
                    slider.disabled = true;
                    input.disabled = true;
                }
            }
        }
    }
}

// 渲染单个参数项
function renderParamItem(key, meta, value) {
    let html = `<div class="param-item">`;
    html += `<label class="param-label" title="${meta.description || ''}">${meta.label}</label>`;

    if (meta.type === 'enum') {
        html += `<select id="param_${key}" class="param-select">`;
        for (const opt of meta.options) {
            const selected = (opt === value) ? 'selected' : '';
            html += `<option value="${opt}" ${selected}>${opt}</option>`;
        }
        html += `</select>`;
    } else if (meta.type === 'number') {
        html += `<div class="param-number-row">`;
        html += `<input type="range" id="param_${key}_slider"
                 min="${meta.min}" max="${meta.max}" step="${meta.step}" value="${value}"
                 class="param-slider">`;
        html += `<input type="number" id="param_${key}_input"
                 min="${meta.min}" max="${meta.max}" step="${meta.step}" value="${value}"
                 class="param-input">`;
        html += `</div>`;
    } else if (meta.type === 'number_or_auto') {
        html += `<div class="param-auto-row">`;
        html += `<label class="param-auto-label"><input type="checkbox" id="param_${key}_auto"> 自动</label>`;
        html += `</div>`;
        html += `<div class="param-number-row">`;
        html += `<input type="range" id="param_${key}_slider"
                 min="${meta.min}" max="${meta.max}" step="${meta.step}" value="${value || meta.min}"
                 class="param-slider">`;
        html += `<input type="number" id="param_${key}_input"
                 min="${meta.min}" max="${meta.max}" step="${meta.step}" value="${value || meta.min}"
                 class="param-input">`;
        html += `</div>`;
    }

    if (meta.description) {
        html += `<div class="param-description">${meta.description}</div>`;
    }

    html += `</div>`;
    return html;
}

// 收集用户当前调整的参数
function collectParamsFromUI() {
    const params = {};
    for (const [key, meta] of Object.entries(currentParamsMeta)) {
        if (meta.type === 'enum') {
            const el = document.getElementById(`param_${key}`);
            if (el) params[key] = el.value;
        } else if (meta.type === 'number') {
            const el = document.getElementById(`param_${key}_input`);
            if (el) params[key] = parseFloat(el.value);
        } else if (meta.type === 'number_or_auto') {
            const autoCheck = document.getElementById(`param_${key}_auto`);
            if (autoCheck && autoCheck.checked) {
                params[key] = null;  // 自动模式
            } else {
                const el = document.getElementById(`param_${key}_input`);
                if (el) params[key] = parseInt(el.value);
            }
        }
    }
    return params;
}

// 应用参数
async function applyParams() {
    if (!sessionId) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    const params = collectParamsFromUI();
    const hint = document.getElementById('paramsHint');

    try {
        const response = await fetch('/api/save_params', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, params: params })
        });
        const data = await response.json();

        if (data.error) {
            setStatus('!!! 参数保存失败: ' + data.error, 'error');
            if (hint) hint.textContent = '保存失败: ' + data.error;
            return;
        }

        currentParams = data.params;
        savedParamsHash = data.params_hash;

        // 保存到 localStorage
        localStorage.setItem(`params_${sessionId}`, JSON.stringify(params));

        setStatus('==> 参数已应用，下次生成时生效', 'success');
        if (hint) {
            hint.textContent = '参数已应用，下次生成时生效';
            hint.style.color = '#2E7D32';
        }

        // 收起面板
        setTimeout(() => {
            document.getElementById('paramsBody').style.display = 'none';
            document.getElementById('paramsToggle').textContent = '▶';
        }, 800);

    } catch (error) {
        setStatus('!!! 参数保存失败: ' + error.message, 'error');
    }
}

// 绑定折叠面板事件
function initParamsPanel() {
    const header = document.getElementById('paramsHeader');
    const body = document.getElementById('paramsBody');
    const toggle = document.getElementById('paramsToggle');
    const applyBtn = document.getElementById('btnApplyParams');

    if (!header || !body || !toggle) return;

    header.addEventListener('click', () => {
        const isHidden = body.style.display === 'none';
        body.style.display = isHidden ? 'block' : 'none';
        toggle.textContent = isHidden ? '▼' : '▶';

        // 首次展开时加载参数
        if (isHidden && Object.keys(currentParamsMeta).length === 0 && sessionId) {
            loadSessionParams();
        }
    });

    if (applyBtn) {
        applyBtn.addEventListener('click', applyParams);
    }
}

// ==================== 克里金曲面数值分析 ====================
const btnKrigingAnalysis = document.getElementById('btnKrigingAnalysis');
if (btnKrigingAnalysis) {
    btnKrigingAnalysis.addEventListener('click', async function() {
        if (!sessionId || !filePath) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }

        currentAnalysisMode = 'kriging';

        // 隐藏钻孔模型容器
        var drillContainer = document.getElementById('drillModelContainer');
        if (drillContainer) drillContainer.style.display = 'none';

        var resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.innerHTML = '';
            resultsSection.classList.remove('visible');
        }

        var loadingDiv = document.createElement('div');
        loadingDiv.id = 'krigingSurfaceLoading';
        loadingDiv.style.cssText = 'text-align:center;padding:40px;font-size:16px;color:#666;';
        loadingDiv.textContent = '⏳ 正在进行插值数值分析（含 RBF 对比），请稍候...';
        if (resultsSection) {
            resultsSection.appendChild(loadingDiv);
            resultsSection.classList.add('visible');
        }

        startLogPolling(sessionId);
        setStatus('正在进行插值数值分析...', 'loading');
        var timer = startButtonTimer(btnKrigingAnalysis, '插值分析中');

        try {
            var response = await fetch('/api/kriging_surface_analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    path: filePath
                })
            });
            var data = await response.json();
            stopLogPolling();

            if (data.error) {
                setStatus('!!! ' + data.error, 'error');
                if (timer) timer.stop();
                if (drillContainer) drillContainer.style.display = 'flex';
                return;
            }

            var loadingEl = document.getElementById('krigingSurfaceLoading');
            if (loadingEl) loadingEl.remove();

            renderKrigingSurfaceResults(data);
            updateButtonStates();
            showResultTabs();
            setStatus('==> 插值曲面分析完成，共 ' + data.analysis_count + ' 个图层', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            setStatus('!!! 分析失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

// ==================== RBF 参数分析 ====================
const btnAnalyzeRBF = document.getElementById('btnAnalyzeRBF');
if (btnAnalyzeRBF) {
    btnAnalyzeRBF.addEventListener('click', async function() {
        if (!sessionId || !filePath) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }

        // 1. 获取岩性列表
        var layers = [];
        try {
            const layerResp = await fetch('/api/layers_list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath })
            });
            const layerData = await layerResp.json();
            if (layerData.success) {
                layers = layerData.layers;
            }
        } catch (e) {
            console.warn('获取岩性列表失败:', e);
        }

        // 2. 弹窗让用户选择分析对象
        var options = ['整体（所有岩性层合并）'];
        for (var li = 0; li < layers.length; li++) {
            options.push(layers[li]);
        }
        var targetLayer = await showLayerSelectModal(options);
        if (!targetLayer) return; // 用户取消

        // 隐藏钻孔模型容器
        var drillContainer = document.getElementById('drillModelContainer');
        if (drillContainer) drillContainer.style.display = 'none';

        var resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.innerHTML = '';
            resultsSection.classList.remove('visible');
        }

        // 3. 开始分析
        startLogPolling(sessionId);
        setStatus('正在进行 RBF 参数分析...', 'loading');
        var timer = startButtonTimer(btnAnalyzeRBF, '参数分析中');

        // 4. 显示进度条
        if (resultsSection) {
            resultsSection.innerHTML = [
                '<div class="analysis-progress">',
                '   <h3>🔬 RBF 参数分析进行中</h3>',
                '   <div class="progress-bar-wrap">',
                '       <div class="progress-bar-fill" id="rbfProgressFill" style="width: 0%;"></div>',
                '   </div>',
                '   <p id="rbfProgressText">准备中...</p>',
                '</div>'
            ].join('');
            resultsSection.classList.add('visible');
        }

        // 5. 假进度（后端同步阻塞，无法获取真实进度）
        var fakeProgress = 0;
        var progressInterval = setInterval(function() {
            fakeProgress += 3;
            if (fakeProgress > 90) fakeProgress = 90;
            var fill = document.getElementById('rbfProgressFill');
            var text = document.getElementById('rbfProgressText');
            if (fill) fill.style.width = fakeProgress + '%';
            if (text) text.textContent = '正在计算...（约 ' + fakeProgress + '%）';
        }, 1000);

        try {
            var response = await fetch('/api/analyze_rbf_params', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    path: filePath,
                    target_layer: targetLayer
                })
            });
            var data = await response.json();
            stopLogPolling();

            clearInterval(progressInterval);

            if (data.error) {
                setStatus('!!! ' + data.error, 'error');
                if (timer) timer.stop();
                if (resultsSection) {
                    resultsSection.innerHTML = '<p style="color:#c62828;text-align:center;padding:40px;">分析失败: ' + data.error + '</p>';
                }
                if (drillContainer) drillContainer.style.display = 'flex';
                return;
            }

            // 进度条到 100%
            var fill = document.getElementById('rbfProgressFill');
            if (fill) fill.style.width = '100%';

            // 渲染结果
            renderRBFAnalysisResults(data);
            updateButtonStates();
            showResultTabs();
            setStatus('==> RBF 参数分析完成', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            clearInterval(progressInterval);
            setStatus('!!! 分析失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

/**
 * 打开图层选择弹窗，返回 Promise
 * @param {string[]} options - 选项列表（第一项为"整体"）
 * @returns {Promise<string|null>} - 选中项，取消返回 null
 */
function showLayerSelectModal(options) {
    return new Promise(function(resolve) {
        var modal = document.getElementById('layerSelectModal');
        var container = document.getElementById('layerSelectOptions');
        var closeBtn = document.getElementById('layerSelectClose');
        var cancelBtn = document.getElementById('layerSelectCancel');
        var confirmBtn = document.getElementById('layerSelectConfirm');

        if (!modal || !container) {
            // 容错：模态框不存在，回退到 prompt
            var userChoice = prompt(
                '请选择分析范围（输入序号）：\n' +
                options.map(function(opt, i) { return (i + 1) + '. ' + opt; }).join('\n'),
                '1'
            );
            if (!userChoice) { resolve(null); return; }
            var idx = parseInt(userChoice) - 1;
            if (isNaN(idx) || idx < 0 || idx >= options.length) { resolve(null); return; }
            resolve(options[idx]);
            return;
        }

        // 构建单选列表
        var html = '';
        for (var i = 0; i < options.length; i++) {
            var checked = i === 0 ? 'checked' : '';
            html += '<label style="display:flex;align-items:center;padding:8px 12px;' +
                    'border:1px solid #e0e0e0;border-radius:6px;margin-bottom:6px;' +
                    'cursor:pointer;transition:background 0.2s;' +
                    '" onmouseover="this.style.background=\'#f5f5f5\'" ' +
                    'onmouseout="this.style.background=\'\'">';
            html += '  <input type="radio" name="layerSelect" value="' + i + '" ' + checked + ' ' +
                    'style="margin-right:10px;width:16px;height:16px;accent-color:#1565C0;">';
            html += '  <span style="font-size:14px;color:#333;">' + options[i] + '</span>';
            html += '</label>';
        }
        container.innerHTML = html;

        // 显示弹窗
        modal.style.display = 'flex';

        // 清理函数
        function cleanup() {
            modal.style.display = 'none';
            container.innerHTML = '';
            closeBtn.removeEventListener('click', onCancel);
            cancelBtn.removeEventListener('click', onCancel);
            confirmBtn.removeEventListener('click', onConfirm);
            modal.removeEventListener('click', onOverlayClick);
        }

        function onCancel() {
            cleanup();
            resolve(null);
        }

        function onOverlayClick(e) {
            if (e.target === modal) {
                cleanup();
                resolve(null);
            }
        }

        function onConfirm() {
            var selected = container.querySelector('input[name="layerSelect"]:checked');
            if (!selected) {
                cleanup();
                resolve(null);
                return;
            }
            var idx = parseInt(selected.value);
            var result = options[idx];
            cleanup();
            // 第一项 "整体" → 传 'all'
            resolve(idx === 0 ? 'all' : result);
        }

        closeBtn.addEventListener('click', onCancel);
        cancelBtn.addEventListener('click', onCancel);
        confirmBtn.addEventListener('click', onConfirm);
        modal.addEventListener('click', onOverlayClick);
    });
}

function renderKrigingSurfaceResults(data) {
    var resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    var html = '<h2>📊 克里金曲面数值分析结果</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:8px;">';
    html += '变异函数模型: <b>' + data.variogram_model + '</b> ｜ ';
    html += '分析图层数: <b>' + data.analysis_count + '</b>';
    html += '</p>';

    if (data.warnings && data.warnings.length > 0) {
        html += '<div class="kriging-warnings">';
        html += '<h4>⚠️ 注意事项</h4><ul>';
        for (var i = 0; i < data.warnings.length; i++) {
            html += '<li>' + data.warnings[i] + '</li>';
        }
        html += '</ul></div>';
    }

    for (var i = 0; i < data.layers.length; i++) {
        var layer = data.layers[i];
        html += '<div class="kriging-layer">';
        html += '<h3>' + layer.layer_name + '</h3>';

        if (layer.top_stats || layer.bot_stats) {
            html += '<div class="kriging-stats">';
            if (layer.top_stats) {
                html += '<div class="stat-block"><b>顶面</b>：控制点 ' + layer.top_stats.n_points + ' 个，平均方差 ' + layer.top_stats.variance_mean.toFixed(2) + '</div>';
            }
            if (layer.bot_stats) {
                html += '<div class="stat-block"><b>底面</b>：控制点 ' + layer.bot_stats.n_points + ' 个，平均方差 ' + layer.bot_stats.variance_mean.toFixed(2) + '</div>';
            }
            html += '</div>';
        }

        html += '<div class="uniform-grid">';
        if (layer.top_url) {
            html += '<div class="uniform-card">';
            html += '<div class="card-img-wrapper" style="cursor:pointer;" onclick="openFullscreen(\'' + layer.top_url + '\')">';
            html += '<img src="' + layer.top_url + '?t=' + Date.now() + '" alt="' + layer.layer_name + ' 顶面" style="width:100%;max-height:400px;object-fit:contain;background:#f8f9fc;display:block;">';
            html += '</div>';
            html += '<div class="card-title">顶面分析</div>';
            html += '</div>';
        }
        if (layer.bot_url) {
            html += '<div class="uniform-card">';
            html += '<div class="card-img-wrapper" style="cursor:pointer;" onclick="openFullscreen(\'' + layer.bot_url + '\')">';
            html += '<img src="' + layer.bot_url + '?t=' + Date.now() + '" alt="' + layer.layer_name + ' 底面" style="width:100%;max-height:400px;object-fit:contain;background:#f8f9fc;display:block;">';
            html += '</div>';
            html += '<div class="card-title">底面分析</div>';
            html += '</div>';
        }
        html += '</div></div>';
    }

    resultsSection.innerHTML = html;
}

function initResultTabs() {
    var tabVisual = document.getElementById('tabVisual');
    var tabReport = document.getElementById('tabReport');
    var resultsSection = document.getElementById('resultsSection');
    var reportSection = document.getElementById('reportSection');
    var resultTabs = document.getElementById('resultTabs');

    if (!tabVisual || !tabReport) return;

    // tabs 默认由 HTML 的 style="display:none" 隐藏
    // 只有分析结果页面才通过 showResultTabs() 显示

    tabVisual.addEventListener('click', function() {
        tabVisual.classList.add('active');
        tabReport.classList.remove('active');
        // 使用 '' 重置内联样式，让 CSS 的 flex 生效，避免 display:block 破坏布局
        if (resultsSection) resultsSection.style.display = '';
        if (reportSection) reportSection.style.display = 'none';
    });

    tabReport.addEventListener('click', function() {
        tabReport.classList.add('active');
        tabVisual.classList.remove('active');
        if (resultsSection) resultsSection.style.display = 'none';
        if (reportSection) reportSection.style.display = ''; // 重置，让 CSS flex 生效
        loadAnalysisReport();
    });
}

/** 显示结果区的「可视化结果/数据说明」tabs */
function showResultTabs() {
    var tabs = document.getElementById('resultTabs');
    if (tabs) tabs.style.display = 'flex';
    // 确保可视化结果 tab 激活
    var tabVisual = document.getElementById('tabVisual');
    var tabReport = document.getElementById('tabReport');
    if (tabVisual) tabVisual.classList.add('active');
    if (tabReport) tabReport.classList.remove('active');
    var resultsSection = document.getElementById('resultsSection');
    var reportSection = document.getElementById('reportSection');
    if (resultsSection) resultsSection.style.display = '';
    if (reportSection) reportSection.style.display = 'none';
}

// ==================== RBF 参数分析结果渲染 ====================
function renderRBFAnalysisResults(data) {
    var resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    var analysisKeys = Object.keys(data.analysis || {});
    if (analysisKeys.length === 0) {
        resultsSection.innerHTML = '<div class="rbf-results-wrapper"><p style="text-align:center;padding:40px;color:#666;">无分析结果</p></div>';
        return;
    }

    var key = analysisKeys[0];
    var result = data.analysis[key];

    if (!result.success) {
        resultsSection.innerHTML = '<div class="rbf-results-wrapper"><p style="color:#c62828;text-align:center;padding:40px;">分析失败: ' + (result.error || '未知错误') + '</p></div>';
        return;
    }

    var best = result.best;
    var allResults = result.all_results;
    var standards = data.standards;

    if (!best || !allResults || allResults.length === 0) {
        resultsSection.innerHTML = '<div class="rbf-results-wrapper"><p style="text-align:center;padding:40px;color:#666;">无有效的参数组合结果</p></div>';
        return;
    }

    // 判断最优 RMSE 属于哪个标准
    var currentStd = standards[standards.length - 1];
    for (var si = 0; si < standards.length; si++) {
        if (best.rmse < standards[si].max) {
            currentStd = standards[si];
            break;
        }
    }

    var targetLabel = key === 'all' ? '整体数据集' : key;

    // ========== 全部内容放在一个容器中，避免 CSS > div:not(.linked-carousel) 的 flex 影响 ==========
    var html = '<div class="rbf-results-wrapper">';

    html += '<h2 style="margin-bottom:8px;">🔬 RBF 参数分析结果</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:16px;">分析范围: <b>' + targetLabel + '</b></p>';

    // ========== 推荐参数卡片 ==========
    html += '<div class="best-param-card">';
    html += '   <div class="best-badge">✨ 推荐参数</div>';
    html += '   <div class="best-param-content">';
    html += '       <div class="best-param-row"><span class="label">核函数：</span><span class="value">' + best.rbf_function + '</span></div>';
    html += '       <div class="best-param-row"><span class="label">平滑度：</span><span class="value">' + best.smooth + '</span></div>';
    if (best.epsilon !== null && best.epsilon !== undefined) {
        html += '   <div class="best-param-row"><span class="label">epsilon：</span><span class="value">' + best.epsilon + '</span></div>';
    }
    html += '       <div class="best-param-row">';
    html += '           <span class="label">预期误差 (RMSE)：</span>';
    html += '           <span class="value" style="color:' + currentStd.color + ';font-size:18px;">';
    html += best.rmse.toFixed(2) + ' m';
    html += '               <span class="rmse-tag" style="background:' + currentStd.color + '">' + currentStd.label + '</span>';
    html += '           </span>';
    html += '       </div>';
    html += '       <div class="best-param-row"><span class="label">建议：</span><span class="value">' + currentStd.suggestion + '</span></div>';
    html += '   </div>';
    html += '   <div class="best-param-actions">';
    html += '       <button class="btn btn-primary" id="btnApplyBestParams">✅ 应用此参数到当前会话</button>';
    html += '       <button class="btn" id="btnCopyBestParams">📋 复制参数</button>';
    html += '   </div>';
    html += '</div>';

    // ========== RMSE 热力图（固定高度容器） ==========
    html += '<div class="analysis-block">';
    html += '   <h3>📊 RMSE 热力图（核函数 × 平滑度）</h3>';
    html += '   <div id="rmseHeatmap" class="rbf-heatmap-container"></div>';
    html += '</div>';

    // ========== 参数表格 ==========
    var sorted = allResults.slice().sort(function(a, b) { return a.rmse - b.rmse; });
    var topN = sorted.slice(0, 30);

    html += '<div class="analysis-block">';
    html += '   <h3>📋 参数组合明细（按 RMSE 升序，前 30 项）</h3>';
    html += '   <table class="report-table"><thead><tr>';
    html += '       <th>排名</th><th>核函数</th><th>平滑度</th><th>epsilon</th>';
    html += '       <th>RMSE(m)</th><th>MAE(m)</th><th>最大误差(m)</th><th>评价</th>';
    html += '   </tr></thead><tbody>';

    for (var ri = 0; ri < topN.length; ri++) {
        var r = topN[ri];
        var std = standards[standards.length - 1];
        for (var sj = 0; sj < standards.length; sj++) {
            if (r.rmse < standards[sj].max) { std = standards[sj]; break; }
        }
        var epsDisplay = (r.epsilon !== null && r.epsilon !== undefined) ? r.epsilon : '-';
        html += '<tr>';
        html += '   <td>' + (ri + 1) + '</td>';
        html += '   <td>' + r.rbf_function + '</td>';
        html += '   <td>' + r.smooth + '</td>';
        html += '   <td>' + epsDisplay + '</td>';
        html += '   <td><b>' + r.rmse.toFixed(2) + '</b></td>';
        html += '   <td>' + r.mae.toFixed(2) + '</td>';
        html += '   <td>' + r.max_error.toFixed(2) + '</td>';
        html += '   <td style="color:' + std.color + '">' + std.label + '</td>';
        html += '</tr>';
    }

    html += '</tbody></table></div>';

    // ========== 参考标准表 ==========
    html += '<div class="analysis-block">';
    html += '   <h3>📖 RMSE 参考标准</h3>';
    html += '   <table class="report-table standards-table"><thead><tr>';
    html += '       <th>RMSE 范围</th><th>评价</th><th>建议</th>';
    html += '   </tr></thead><tbody>';

    for (var si2 = 0; si2 < standards.length; si2++) {
        var st = standards[si2];
        var isCurrent = (st === currentStd);
        var rangeText = st.max >= 99999
            ? '> ' + standards[standards.length - 2].max + ' m'
            : '< ' + st.max + ' m';
        var rowStyle = isCurrent ? 'background:' + st.color + '22;font-weight:bold;' : '';
        html += '<tr class="' + (isCurrent ? 'current-standard' : '') + '" style="' + rowStyle + '">';
        html += '   <td>' + rangeText + '</td>';
        html += '   <td style="color:' + st.color + '">' + st.label + '</td>';
        html += '   <td>' + st.suggestion + (isCurrent ? ' ← 当前结果' : '') + '</td>';
        html += '</tr>';
    }

    html += '</tbody></table></div>';

    html += '</div>'; // rbf-results-wrapper

    resultsSection.innerHTML = html;

    // 渲染热力图（延迟一小段时间确保 DOM 已渲染）
    setTimeout(function() {
        drawRMSEHeatmap(allResults);
    }, 100);

    // 绑定按钮事件
    var btnApply = document.getElementById('btnApplyBestParams');
    if (btnApply) {
        btnApply.addEventListener('click', function() { applyBestParams(best); });
    }

    var btnCopy = document.getElementById('btnCopyBestParams');
    if (btnCopy) {
        btnCopy.addEventListener('click', function() { copyBestParams(best); });
    }
}

/**
 * 绘制 RMSE 热力图（Plotly）
 * 横轴为平滑度，纵轴为核函数，颜色深度表示 RMSE 大小
 */
function drawRMSEHeatmap(allResults) {
    var functions = [];
    var funcMap = {};
    for (var fi = 0; fi < allResults.length; fi++) {
        var fname = allResults[fi].rbf_function;
        if (!funcMap[fname]) {
            funcMap[fname] = true;
            functions.push(fname);
        }
    }

    var smoothSet = {};
    for (var si = 0; si < allResults.length; si++) {
        smoothSet[allResults[si].smooth] = true;
    }
    var smooths = Object.keys(smoothSet).map(Number).sort(function(a, b) { return a - b; });

    // 构建 RMSE 矩阵（每个 func × smooth 取最优 epsilon 的 RMSE）
    // 使用 NaN 代替 null，Plotly 对 NaN 处理更稳定
    var rmseMatrix = [];
    var hoverTexts = [];

    // 找出全局最小/最大 RMSE 用于 colorscale 固定范围
    var allRmses = allResults.map(function(r) { return r.rmse; }).filter(function(v) { return isFinite(v); });
    var globalMin = allRmses.length > 0 ? Math.min.apply(null, allRmses) : 0;
    var globalMax = allRmses.length > 0 ? Math.max.apply(null, allRmses) : 1;
    if (globalMax <= globalMin) globalMax = globalMin + 1;

    for (var fi2 = 0; fi2 < functions.length; fi2++) {
        var func = functions[fi2];
        var row = [];
        var hRow = [];
        for (var si2 = 0; si2 < smooths.length; si2++) {
            var sm = smooths[si2];
            var candidates = allResults.filter(function(r) {
                return r.rbf_function === func && r.smooth === sm;
            });
            if (candidates.length > 0) {
                var minRmse = Math.min.apply(null, candidates.map(function(c) { return c.rmse; }));
                row.push(parseFloat(minRmse.toFixed(2)));
                var bestCand = candidates.reduce(function(a, b) { return a.rmse < b.rmse ? a : b; });
                var txt = '核函数: ' + func + '<br>smooth: ' + sm;
                if (bestCand.epsilon !== null && bestCand.epsilon !== undefined) {
                    txt += '<br>最优 epsilon: ' + bestCand.epsilon;
                }
                txt += '<br>RMSE: ' + bestCand.rmse.toFixed(2) + ' m';
                hRow.push(txt);
            } else {
                row.push(NaN);
                hRow.push('无数据');
            }
        }
        rmseMatrix.push(row);
        hoverTexts.push(hRow);
    }

    var trace = {
        z: rmseMatrix,
        x: smooths.map(String),
        y: functions,
        type: 'heatmap',
        colorscale: 'RdYlGn_r',
        showscale: true,
        zmin: globalMin,
        zmax: globalMax,
        colorbar: { title: 'RMSE (m)' },
        text: hoverTexts,
        hoverinfo: 'text',
        connectgaps: false
    };

    var layout = {
        xaxis: { title: '平滑度 (smooth)', type: 'category' },
        yaxis: { title: '核函数', type: 'category' },
        margin: { l: 140, r: 40, t: 20, b: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
    };

    var heatmapDiv = document.getElementById('rmseHeatmap');
    if (heatmapDiv && typeof Plotly !== 'undefined') {
        Plotly.newPlot(heatmapDiv, [trace], layout, { responsive: true });
    }
}

/**
 * 应用推荐参数到当前会话
 */
function applyBestParams(best) {
    if (!best) return;

    // 更新前端 currentParams
    if (typeof currentParams !== 'object') {
        currentParams = {};
    }
    currentParams.RBF_FUNCTION = best.rbf_function;
    currentParams.RBF_SMOOTH = best.smooth;

    // 如果参数面板已渲染，同步更新输入框
    var funcEl = document.getElementById('param_RBF_FUNCTION');
    if (funcEl) funcEl.value = best.rbf_function;

    var smoothEl = document.getElementById('param_RBF_SMOOTH_input');
    if (smoothEl) smoothEl.value = best.smooth;

    var smoothSlider = document.getElementById('param_RBF_SMOOTH_slider');
    if (smoothSlider) smoothSlider.value = best.smooth;

    setStatus('==> 推荐参数已应用到当前会话（下次生成时生效）', 'success');

    setTimeout(function() {
        var hint = document.getElementById('paramsHint');
        if (hint) {
            hint.textContent = '已从参数分析结果应用 RBF 参数';
            hint.style.color = '#2E7D32';
        }
    }, 300);
}

/**
 * 复制推荐参数到剪贴板
 */
function copyBestParams(best) {
    var text = '核函数: ' + best.rbf_function +
               '\n平滑度: ' + best.smooth +
               (best.epsilon ? '\nepsilon: ' + best.epsilon : '') +
               '\n预期误差: ' + best.rmse.toFixed(2) + ' m';

    navigator.clipboard.writeText(text).then(function() {
        setStatus('==> 参数已复制到剪贴板', 'success');
    }).catch(function() {
        prompt('请手动复制：', text);
    });
}

/** 隐藏结果区的 tabs（仅展示钻孔计算器等内容时） */
function hideResultTabs() {
    var tabs = document.getElementById('resultTabs');
    if (tabs) tabs.style.display = 'none';
    var reportSection = document.getElementById('reportSection');
    if (reportSection) reportSection.style.display = 'none';
    var resultsSection = document.getElementById('resultsSection');
    if (resultsSection) resultsSection.style.display = '';
}

// ==================== 数据说明页面 ====================
async function loadAnalysisReport() {
    var reportSection = document.getElementById('reportSection');
    if (!reportSection) return;

    if (!sessionId) {
        reportSection.innerHTML = '<p style="text-align:center;padding:40px;color:#999;">请先上传文件</p>';
        return;
    }

    reportSection.innerHTML = '<p style="text-align:center;padding:40px;color:#666;">正在加载分析数据...</p>';

    try {
        var response = await fetch('/api/analysis_data?session_id=' + sessionId);
        var data = await response.json();

        if (!data.success) {
            reportSection.innerHTML = '<p style="text-align:center;padding:40px;color:#999;">' + (data.error || '暂无分析数据') + '</p>';
            return;
        }

        analysisData = data;
        renderAnalysisReport(data);

    } catch (error) {
        reportSection.innerHTML = '<p style="text-align:center;padding:40px;color:#c62828;">加载失败: ' + error.message + '</p>';
    }
}

function renderAnalysisReport(data) {
    var reportSection = document.getElementById('reportSection');
    var html = '';

    html += '<div class="report-header">';
    html += '<h2>📈 数据说明</h2>';
    html += '<button class="btn btn-primary" id="btnExportAnalysis">📥 导出分析数据（ZIP）</button>';
    html += '</div>';

    // 模式提示
    var modeLabel = '';
    if (currentAnalysisMode === 'rbf') {
        modeLabel = '<p style="color:#1565C0;font-size:13px;margin-bottom:12px;">📌 当前显示 RBF 插值相关数据</p>';
    } else if (currentAnalysisMode === 'kriging') {
        modeLabel = '<p style="color:#1565C0;font-size:13px;margin-bottom:12px;">📌 当前显示克里金插值相关数据</p>';
    }
    if (modeLabel) {
        html += modeLabel;
    }

    // 参数信息
    html += '<div class="report-block"><h3>🔧 分析参数</h3><div class="param-grid">';

    if (data.has_rbf && data.data.rbf && currentAnalysisMode !== 'kriging') {
        var p = data.data.rbf.params || {};
        html += '<div class="param-card">';
        html += '<h4>RBF 建模参数</h4>';
        html += '<div>核函数: ' + (p.rbf_function || '-') + '</div>';
        html += '<div>平滑度: ' + (p.rbf_smooth !== undefined ? p.rbf_smooth : '-') + '</div>';
        html += '<div>网格分辨率: ' + (p.grid_resolution || '-') + '</div>';
        html += '<div>体渲染层数: ' + (p.n_layers || '自动') + '</div>';
        html += '</div>';
    }

    if (data.has_kriging && data.data.kriging && currentAnalysisMode !== 'rbf') {
        var p = data.data.kriging.params || {};
        html += '<div class="param-card">';
        html += '<h4>克里金参数</h4>';
        html += '<div>变异函数: ' + (p.variogram_model || '-') + '</div>';
        html += '</div>';
    }

    html += '</div></div>';

    // 统计汇总表
    html += '<div class="report-block"><h3>📊 各层统计汇总</h3>';
    html += '<table class="report-table"><thead><tr>';
    html += '<th>方法</th><th>岩性</th><th>层位</th><th>控制点数</th>';
    html += '<th>最小值(m)</th><th>最大值(m)</th><th>均值(m)</th>';
    html += '<th>标准差(m)</th><th>平均方差</th>';
    html += '</tr></thead><tbody>';

    if (data.has_rbf && data.data.rbf && currentAnalysisMode !== 'kriging') {
        for (var i = 0; i < data.data.rbf.layers.length; i++) {
            var layer = data.data.rbf.layers[i];
            var s = layer.stats || {};
            html += '<tr>';
            html += '<td>RBF</td><td>' + (layer.layer_name || '-') + '</td><td>' + (layer.part_name || '-') + '</td>';
            html += '<td>' + (s.n_points !== undefined ? s.n_points : '-') + '</td>';
            html += '<td>' + (s.min !== null && s.min !== undefined ? s.min.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.max !== null && s.max !== undefined ? s.max.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.mean !== null && s.mean !== undefined ? s.mean.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.std !== null && s.std !== undefined ? s.std.toFixed(2) : '-') + '</td>';
            html += '<td>-</td>';
            html += '</tr>';
        }
    }

    if (data.has_kriging && data.data.kriging && currentAnalysisMode !== 'rbf') {
        for (var i = 0; i < data.data.kriging.layers.length; i++) {
            var layer = data.data.kriging.layers[i];
            var s = layer.stats || {};
            html += '<tr>';
            html += '<td>克里金</td><td>' + (layer.layer_name || '-') + '</td><td>' + (layer.part_name || '-') + '</td>';
            html += '<td>' + (s.n_points !== undefined ? s.n_points : '-') + '</td>';
            html += '<td>' + (s.kriging_min !== undefined ? s.kriging_min.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.kriging_max !== undefined ? s.kriging_max.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.kriging_mean !== undefined ? s.kriging_mean.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.kriging_std !== undefined ? s.kriging_std.toFixed(2) : '-') + '</td>';
            html += '<td>' + (s.variance_mean !== undefined ? s.variance_mean.toFixed(2) : '-') + '</td>';
            html += '</tr>';
        }
    }

    html += '</tbody></table></div>';

    // 图表
    html += '<div class="report-block"><h3>📈 图表分析</h3><div id="reportCharts"></div></div>';

    reportSection.innerHTML = html;

    var exportBtn = document.getElementById('btnExportAnalysis');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportAnalysisData);
    }

    renderReportCharts(data);
}

function renderReportCharts(data) {
    if (!data.has_rbf && !data.has_kriging) return;

    var chartsDiv = document.getElementById('reportCharts');
    if (!chartsDiv) return;

    var html = '';

    // 对比图：仅在未过滤模式（'all'）且两种数据都存在时显示
    if (data.has_rbf && data.has_kriging && currentAnalysisMode === 'all') {
        html += '<div class="chart-card">';
        html += '<h4>散点图：RBF vs Kriging 插值值对比</h4>';
        html += '<div id="scatterChart" style="height:500px;"></div>';
        html += '</div>';
        html += '<div class="chart-card">';
        html += '<h4>直方图：克里金与 RBF 的差异分布</h4>';
        html += '<div id="diffHistogram" style="height:400px;"></div>';
        html += '</div>';
    }

    // 方差图：在克里金模式或全模式下显示
    if (data.has_kriging && currentAnalysisMode !== 'rbf') {
        html += '<div class="chart-card">';
        html += '<h4>直方图：克里金预测方差分布</h4>';
        html += '<div id="varianceHistogram" style="height:400px;"></div>';
        html += '</div>';
    }

    chartsDiv.innerHTML = html;

    if (data.has_rbf && data.has_kriging && currentAnalysisMode === 'all') {
        drawScatterChart(data);
        drawDiffHistogram(data);
    }
    if (data.has_kriging && currentAnalysisMode !== 'rbf') {
        drawVarianceHistogram(data);
    }
}

function drawScatterChart(data) {
    var rbfLayer = null;
    var krigingLayer = null;
    if (data.data.rbf && data.data.rbf.layers) {
        for (var i = 0; i < data.data.rbf.layers.length; i++) {
            if (data.data.rbf.layers[i].part_name === '顶面') {
                rbfLayer = data.data.rbf.layers[i];
                break;
            }
        }
    }
    if (data.data.kriging && data.data.kriging.layers) {
        for (var i = 0; i < data.data.kriging.layers.length; i++) {
            if (data.data.kriging.layers[i].part_name === '顶面') {
                krigingLayer = data.data.kriging.layers[i];
                break;
            }
        }
    }
    if (!rbfLayer || !krigingLayer) return;

    var rbfZ = rbfLayer.z_pred ? rbfLayer.z_pred.filter(function(v) { return v !== null; }) : [];
    var krigingZ = krigingLayer.z_kriging ? krigingLayer.z_kriging.filter(function(v) { return v !== null; }) : [];
    var n = Math.min(rbfZ.length, krigingZ.length, 500);

    var trace1 = {
        x: rbfZ.slice(0, n),
        y: krigingZ.slice(0, n),
        mode: 'markers',
        type: 'scatter',
        marker: { color: '#1565C0', size: 4, opacity: 0.6 },
        name: '样本'
    };

    var allValues = rbfZ.slice(0, n).concat(krigingZ.slice(0, n));
    var minV = Math.min.apply(null, allValues);
    var maxV = Math.max.apply(null, allValues);
    var trace2 = {
        x: [minV, maxV],
        y: [minV, maxV],
        mode: 'lines',
        type: 'scatter',
        line: { color: '#c62828', dash: 'dash', width: 2 },
        name: '理想对角线'
    };

    var layout = {
        xaxis: { title: 'RBF 插值值 (m)' },
        yaxis: { title: '克里金插值值 (m)' },
        margin: { l: 60, r: 20, t: 20, b: 60 }
    };

    Plotly.newPlot('scatterChart', [trace1, trace2], layout, { responsive: true });
}

function drawDiffHistogram(data) {
    var rbfLayer = null;
    var krigingLayer = null;
    if (data.data.rbf && data.data.rbf.layers) {
        for (var i = 0; i < data.data.rbf.layers.length; i++) {
            if (data.data.rbf.layers[i].part_name === '顶面') {
                rbfLayer = data.data.rbf.layers[i];
                break;
            }
        }
    }
    if (data.data.kriging && data.data.kriging.layers) {
        for (var i = 0; i < data.data.kriging.layers.length; i++) {
            if (data.data.kriging.layers[i].part_name === '顶面') {
                krigingLayer = data.data.kriging.layers[i];
                break;
            }
        }
    }
    if (!rbfLayer || !krigingLayer) return;

    var diff = [];
    var rbfZ = rbfLayer.z_pred || [];
    var krigingZ = krigingLayer.z_kriging || [];
    var n = Math.min(rbfZ.length, krigingZ.length);

    for (var i = 0; i < n; i++) {
        if (rbfZ[i] !== null && krigingZ[i] !== null) {
            diff.push(krigingZ[i] - rbfZ[i]);
        }
    }

    var trace = {
        x: diff,
        type: 'histogram',
        marker: { color: '#F57C00' },
        name: '差异'
    };

    var layout = {
        xaxis: { title: '克里金 - RBF (m)' },
        yaxis: { title: '频次' },
        margin: { l: 60, r: 20, t: 20, b: 60 }
    };

    Plotly.newPlot('diffHistogram', [trace], layout, { responsive: true });
}

function drawVarianceHistogram(data) {
    var krigingLayer = null;
    if (data.data.kriging && data.data.kriging.layers) {
        for (var i = 0; i < data.data.kriging.layers.length; i++) {
            if (data.data.kriging.layers[i].part_name === '顶面') {
                krigingLayer = data.data.kriging.layers[i];
                break;
            }
        }
    }
    if (!krigingLayer || !krigingLayer.z_variance) return;

    var variance = krigingLayer.z_variance.filter(function(v) { return v !== null; });

    var trace = {
        x: variance,
        type: 'histogram',
        marker: { color: '#2E7D32' },
        name: '方差'
    };

    var layout = {
        xaxis: { title: '预测方差' },
        yaxis: { title: '频次' },
        margin: { l: 60, r: 20, t: 20, b: 60 }
    };

    Plotly.newPlot('varianceHistogram', [trace], layout, { responsive: true });
}

async function exportAnalysisData() {
    if (!sessionId) {
        alert('请先上传文件');
        return;
    }

    setStatus('正在导出数据...', 'loading');

    try {
        var response = await fetch('/api/export_analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, formats: ['csv', 'excel'] })
        });

        if (!response.ok) {
            var err = await response.json();
            setStatus('!!! 导出失败: ' + (err.error || '未知错误'), 'error');
            return;
        }

        var blob = await response.blob();
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'analysis_data_' + Date.now() + '.zip';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);

        setStatus('==> 数据已导出', 'success');
    } catch (error) {
        setStatus('!!! 导出失败: ' + error.message, 'error');
    }
}

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    loadTemplateData();
    initParamsPanel();
    initResultTabs();
    setStatus('已加载模板数据，可查看下方预览', 'info');
});


// ==================== 数据预览弹窗 ====================
let previewData = {
    location: [],
    survey: [],
    lithology: [],
    points: []
};
let currentTab = 'location';
let currentPage = 1;
let pageSize = 20;
let previewDataSource = '模板数据';

// DOM 元素（弹窗相关）
const previewModal = document.getElementById('previewModal');
const modalClose = document.getElementById('modalClose');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const btnPreviewData = document.getElementById('btnPreviewData');
const tabBtns = document.querySelectorAll('.tab-btn');
const pageSizeSelect = document.getElementById('pageSizeSelect');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const pageInfo = document.getElementById('pageInfo');
const totalRowsSpan = document.getElementById('totalRows');
const tableHead = document.getElementById('tableHead');
const tableBody = document.getElementById('tableBody');
const dataSourceSpan = document.getElementById('dataSource');
const modalTitle = document.getElementById('modalTitle');

// ==================== 打开/关闭弹窗 ====================
function openPreviewModal() {
    previewModal.classList.add('active');
    document.body.style.overflow = 'hidden';
    // 根据数据源设置标题
    const title = isTemplateData ? '📊 数据预览（模板数据）' : '📊 预览数据（上传数据）';
    modalTitle.textContent = title;
    loadPreviewData();
}

function closePreviewModal() {
    previewModal.classList.remove('active');
    document.body.style.overflow = '';
}

// 关闭事件
modalClose.addEventListener('click', closePreviewModal);
modalCloseBtn.addEventListener('click', closePreviewModal);
previewModal.addEventListener('click', (e) => {
    if (e.target === previewModal) closePreviewModal();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePreviewModal();
});

// ==================== 打开预览按钮 ====================
btnPreviewData.addEventListener('click', openPreviewModal);

// ==================== Tab 切换 ====================
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTab = btn.dataset.tab;
        currentPage = 1;
        loadPreviewData();
    });
});

// ==================== 每页行数切换 ====================
pageSizeSelect.addEventListener('change', () => {
    currentPage = 1;
    loadPreviewData();
});

// ==================== 分页按钮 ====================
prevPageBtn.addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        loadPreviewData();
    }
});

nextPageBtn.addEventListener('click', () => {
    const totalPages = getTotalPages();
    if (currentPage < totalPages) {
        currentPage++;
        loadPreviewData();
    }
});

// ==================== 数据加载 ====================
function getTotalPages() {
    const data = getTabData(currentTab);
    const size = parseInt(pageSizeSelect.value) || 20;
    return Math.max(1, Math.ceil(data.length / size));
}

function getTabData(tabName) {
    switch (tabName) {
        case 'location':
            return previewData.location || [];
        case 'survey':
            return previewData.survey || [];
        case 'lithology':
            return previewData.lithology || [];
        case 'map':
            return [];
        default:
            return [];
    }
}

function loadPreviewData() {
    const tableWrapper = document.getElementById('tableWrapper');
    const mapContainer = document.getElementById('mapContainer');
    const modalControls = document.getElementById('modalControls');
    const pagination = document.getElementById('pagination');

    if (!tableWrapper || !mapContainer) {
        console.warn('tableWrapper or mapContainer not found');
        return;
    }

    // 地图 Tab
    if (currentTab === 'map') {
        tableWrapper.style.display = 'none';
        mapContainer.style.display = 'block';
        modalControls.style.display = 'none';
        pagination.style.display = 'none';
        // 延迟初始化，确保容器已渲染
        setTimeout(() => {
            if (!previewMapInitialized) initPreviewMap();
            updatePreviewMapMarkers();
        }, 100);
        return;
    }

    // 表格 Tab
    tableWrapper.style.display = 'block';
    mapContainer.style.display = 'none';
    if (modalControls) modalControls.style.display = 'flex';
    if (pagination) pagination.style.display = 'flex';

    // 获取当前 Tab 数据
    const allData = getTabData(currentTab);
    console.log(`当前 Tab: ${currentTab}, 数据条数: ${allData.length}`);

    const total = allData.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;

    const start = (currentPage - 1) * pageSize;
    const end = Math.min(start + pageSize, total);
    const pageData = allData.slice(start, end);

    // 更新控件
    document.getElementById('totalRows').textContent = total;
    document.getElementById('pageInfo').textContent = `第 ${currentPage} / ${totalPages} 页`;
    document.getElementById('prevPage').disabled = (currentPage <= 1);
    document.getElementById('nextPage').disabled = (currentPage >= totalPages);

    const sourceLabel = isTemplateData ? '模板数据' : '上传数据';
    document.getElementById('dataSource').innerHTML = `数据来源：<span class="source-highlight">${sourceLabel}</span>`;

    renderTable(pageData, currentTab);
}

function renderTable(data, tabName) {
    if (!data || data.length === 0) {
        tableHead.innerHTML = '';
        tableBody.innerHTML = `
            <tr>
                <td colspan="10" style="text-align:center;padding:40px;color:#999;">
                    <div class="empty-state">
                        <span class="icon">📭</span>
                        暂无数据
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    // 获取表头（使用第一行数据的键）
    const headers = Object.keys(data[0]);

    // 渲染表头
    let headHtml = '<tr>';
    for (const h of headers) {
        headHtml += `<th>${h}</th>`;
    }
    headHtml += '</tr>';
    tableHead.innerHTML = headHtml;

    // 渲染表体
    let bodyHtml = '';
    for (const row of data) {
        bodyHtml += '<tr>';
        for (const h of headers) {
            let val = row[h] !== undefined && row[h] !== null ? row[h] : '';
            if (h === '建模颜色' && val && String(val).startsWith('#')) {
                bodyHtml += `<td><span class="color-swatch-inline" style="background-color:${val};"></span> ${val}</td>`;
            } else {
                bodyHtml += `<td>${String(val)}</td>`;
            }
        }
        bodyHtml += '</tr>';
    }
    tableBody.innerHTML = bodyHtml;
}

// ==================== 更新预览数据 ====================
function updatePreviewData(data, isTemplate = true) {
    console.log('updatePreviewData 接收 data:', data);
    if (!data) {
        console.warn('data 为空');
        return;
    }
    previewData = {
        location: Array.isArray(data.location) ? data.location : [],
        survey: Array.isArray(data.survey) ? data.survey : [],
        lithology: Array.isArray(data.lithology) ? data.lithology : [],
        points: Array.isArray(data.points) ? data.points : []
    };
    isTemplateData = isTemplate;
    previewDataSource = isTemplate ? '模板数据' : '上传数据';
    console.log('更新后 previewData:', previewData);
    console.log('isTemplateData:', isTemplateData);
    // 如果弹窗已打开，刷新显示
    if (previewModal.classList.contains('active')) {
        loadPreviewData();
        modalTitle.textContent = isTemplate ? '📊 数据预览（模板数据）' : '📊 预览数据（上传数据）';
    }
}

// 在页面加载时加载模板数据并更新预览
async function loadTemplateData() {
    setStatus('加载模板数据...', 'loading');
    try {
        const response = await fetch('/api/template_info');
        const data = await response.json();
        if (data.success) {
            isTemplateData = true;
            currentData = data.data;
            updatePreviewData(data.data, true);
            setStatus('==> 模板数据加载成功，可点击「数据预览」查看', 'success');
        } else {
            setStatus('!!! 加载模板数据失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (error) {
        setStatus('!!! 加载模板数据失败: ' + error.message, 'error');
    }
}

// 在上传文件成功后，更新预览数据
async function handleFile(file) {
    // 验证文件类型
    const validTypes = ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                        'application/vnd.ms-excel'];
    if (!validTypes.includes(file.type) && !file.name.match(/\.(xlsx|xls)$/)) {
        setStatus('!!! 请上传 .xlsx 或 .xls 格式的文件', 'error');
        return;
    }

    setStatus('正在上传文件...', 'loading');

    const formData = new FormData();
    formData.append('file', file);
    // 通知后端清理旧 session 的临时文件
    if (sessionId) {
        formData.append('old_session', sessionId);
    }

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            return;
        }
        sessionId = data.session_id;
        filePath = data.path;
        fileInfo.style.display = 'flex';
        uploadArea.style.display = 'none';
        fileName.textContent = data.filename;
        fileSize.textContent = formatFileSize(file.size);
        // 清空数据说明区域
        var reportSection = document.getElementById('reportSection');
        if (reportSection) reportSection.innerHTML = '';
        window.analysisData = null;

        await loadFileData(filePath);
        updateButtonStates();
        // 加载该 session 的参数
        await loadSessionParams();
        setStatus('==> 文件上传成功: ' + data.filename, 'success');
    } catch (error) {
        setStatus('!!! 上传失败: ' + error.message, 'error');
    }
}

async function loadFileData(path) {
    try {
        const response = await fetch('/api/file_info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const result = await response.json();
        if (result.success) {
            updatePreviewData(result.data, false);
            if (currentTab === 'map' && previewMap) {
                updatePreviewMapMarkers();
            }
        } else {
            setStatus('!!! ' + result.error, 'error');
        }
    } catch (error) {
        setStatus('!!! 加载数据失败: ' + error.message, 'error');
    }
}

// 移除文件后恢复模板数据预览
removeFileBtn.addEventListener('click', () => {
    drillViewsCache = null;
    fileInput.value = '';
    fileInfo.style.display = 'none';
    uploadArea.style.display = 'block';
    sessionId = null;
    filePath = null;
    updateButtonStates();
    // clearResults();
    // 恢复模板数据
    if (currentData) {
        updatePreviewData(currentData, true);
        isTemplateData = true;
        modalTitle.textContent = '📊 数据预览（模板数据）';
    }

    // 清空数据说明区域
    var reportSection = document.getElementById('reportSection');
    if (reportSection) reportSection.innerHTML = '';
    // 重置结果区显示，隐藏 tabs（如果第一个 handler 没来得及执行）
    hideResultTabs();
    window.analysisData = null;

    // 清除参数相关的状态
    currentParams = {};
    currentParamsMeta = {};
    savedParamsHash = '';
    const paramsContent = document.getElementById('paramsContent');
    if (paramsContent) paramsContent.innerHTML = '';
    const paramsLoading = document.getElementById('paramsLoading');
    if (paramsLoading) {
        paramsLoading.style.display = 'block';
        paramsLoading.textContent = '请先上传文件，展开后加载参数...';
    }
    const applyBtn = document.getElementById('btnApplyParams');
    if (applyBtn) applyBtn.style.display = 'none';

    setStatus('等待上传文件...', 'info');
});

//日志轮询相关变量
let logInterval = null;
let lastLogTime = 0;
let isProcessing = false;

function startLogPolling(sessionId) {
    // 停止之前的轮询（如果存在）
    if (logInterval) {
        clearInterval(logInterval);
        logInterval = null;
    }

    // ===== 清空状态栏，并设置为日志容器 =====
    const statusDiv = document.getElementById('statusMessage');
    statusDiv.innerHTML = '';
    statusDiv.className = 'status-message log-container';

    lastLogTime = 0;
    isProcessing = true;

    logInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/logs/${sessionId}?since=${lastLogTime}`);
            const data = await response.json();
            if (data.logs && data.logs.length > 0) {
                for (const log of data.logs) {
                    appendLogMessage(log.msg, log.type);
                }
                if (data.latest) {
                    lastLogTime = data.latest;
                }
            }
        } catch (e) {
            // 静默失败，继续轮询
        }
    }, 800);
}

function stopLogPolling() {
    if (logInterval) {
        clearInterval(logInterval);
        logInterval = null;
    }
    isProcessing = false;
    // 保留最后一条消息作为摘要
    const statusDiv = document.getElementById('statusMessage');
    const lastMsg = statusDiv.lastChild ? statusDiv.lastChild.textContent : '处理完成';
    statusDiv.innerHTML = lastMsg;
    statusDiv.className = 'status-message success';
}

function appendLogMessage(msg, type) {
    const statusDiv = document.getElementById('statusMessage');
    const line = document.createElement('div');
    line.textContent = msg;
    line.className = 'log-line';
    if (type === 'error') line.style.color = '#c62828';
    else if (type === 'success') line.style.color = '#2E7D32';
    else if (type === 'warning') line.style.color = '#f57f17';
    else line.style.color = '#333';
    statusDiv.appendChild(line);
    // 自动滚动到底部
    const container = statusDiv.parentElement;
    container.scrollTop = container.scrollHeight;
}

// 地图初始化函数
function initPreviewMap() {
    if (!zj_key) {
        alert('天地图密钥未配置');
        return;
    }
    const container = document.getElementById('previewMap');
    if (!container) return;
    if (previewMap) {
        previewMap.resize();
        return;
    }
    // 确保容器可见且有尺寸
    if (container.offsetWidth === 0 || container.offsetHeight === 0) {
        console.warn('容器尺寸为0，延迟初始化');
        setTimeout(initPreviewMap, 200);
        return;
    }
    previewMap = new T.Map('previewMap');
    if (!previewMap) {
        console.error('预览地图创建失败');
        return;
    }
    previewMap.centerAndZoom(new T.LngLat(120.2, 30.3), 8);
    previewMap.addControl(new T.Control.Zoom());
    previewMap.addControl(new T.Control.Scale());
    previewMapInitialized = true;
    console.log('✅ 预览地图初始化成功');
}

function updatePreviewMapMarkers() {
    if (!previewMapInitialized) {
        initPreviewMap();
        if (!previewMap) return;
    }
    previewMarkerGroup.forEach(m => previewMap.removeOverLay(m));
    previewMarkerGroup = [];
    const points = previewData.points || [];
    if (!points.length) {
        const infoWin = new T.InfoWindow('暂无钻孔数据');
        previewMap.openInfoWindow(infoWin, new T.LngLat(120.2, 30.3));
        return;
    }
    const bounds = new T.LngLatBounds();
    points.forEach(p => {
        console.log(p)
        const lngLat = new T.LngLat(p.lat, p.lon);
        const marker = new T.Marker(lngLat);

        // 1. 创建信息窗口的内容 (HTML字符串)
        const contentHtml = `
            <div style="padding:6px 12px;">
                <div style="font-weight:bold;font-size:14px;color:#1a73e8;border-bottom:1px solid #eee;margin-bottom:6px;">
                    🔹 ${p.钻孔编号}
                </div>
                <div style="font-size:13px;color:#333;line-height:1.7;">
                    <div>开孔坐标E: ${p.开孔坐标E || '--'}</div>
                    <div>开孔坐标N: ${p.开孔坐标N || '--'}</div>
                    <div>开孔高程R: ${p.开孔高程R || '--'} m</div>
                    <div>钻孔长度: ${p.钻孔长度 || '--'} m</div>
                </div>
            </div>
        `;
        // 2. 将HTML字符串转换为DOM元素
        const contentDiv = document.createElement('div');
        contentDiv.innerHTML = contentHtml;

        // 3. 创建信息窗口，传入DOM元素
        const infoWin = new T.InfoWindow(contentDiv, { offset: new T.Point(0, -30) });

        // 4. 绑定点击事件
        marker.addEventListener("click", function() {
            previewMap.openInfoWindow(infoWin, lngLat);
        });

        previewMap.addOverLay(marker);
        previewMarkerGroup.push(marker);
        bounds.extend(lngLat);
    });
    if (previewMarkerGroup.length) {
        if (previewMap.fitBounds) {
            previewMap.fitBounds(bounds, { padding: 40 });
        } else {
            const center = bounds.getCenter();
            previewMap.centerAndZoom(center, 10);
        }
    }
}
// ==================== 全屏放大功能 ====================
function openFullscreen(imageUrl) {
    fullscreenImage.src = imageUrl;
    fullscreenModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeFullscreen() {
    fullscreenModal.classList.remove('active');
    document.body.style.overflow = '';
}

fullscreenClose.addEventListener('click', closeFullscreen);
fullscreenModal.addEventListener('click', (e) => {
    if (e.target === fullscreenModal) closeFullscreen();
});

// ==================== 交互式3D弹窗 ====================
function closeInteractive() {
    interactiveModal.classList.remove('active');
    document.body.style.overflow = '';
    // 清理 iframe 防止继续播放/占用
    var content = document.getElementById('interactiveContent');
    if (content) content.innerHTML = '';
}

interactiveClose.addEventListener('click', closeInteractive);
interactiveModal.addEventListener('click', (e) => {
    if (e.target === interactiveModal) closeInteractive();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeFullscreen();
});

// ==================== 新建会话 ====================
const btnNewSession = document.getElementById('btnNewSession');
if (btnNewSession) {
    btnNewSession.addEventListener('click', async () => {
        if (!sessionId) {
            // 如果没有活跃 session，直接重置页面
            resetToInitialState();
            setStatus('==> 已重置，请上传数据文件', 'success');
            return;
        }

        const sidToClean = sessionId;
        // 先清理前端状态
        resetToInitialState();

        try {
            const resp = await fetch('/api/cleanup_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sidToClean })
            });
            const data = await resp.json();
            if (data.success) {
                setStatus('==> 已清理当前会话数据，请上传新的数据文件', 'success');
            } else {
                setStatus('==> 已重置前端，后台清理完成', 'success');
            }
        } catch (e) {
            setStatus('==> 已重置前端', 'success');
        }
    });
}

function resetToInitialState() {
    drillViewsCache = null;
    sessionId = null;
    filePath = null;
    fileInput.value = '';
    fileInfo.style.display = 'none';
    uploadArea.style.display = 'block';
    currentData = null;
    isTemplateData = true;
    window.analysisData = null;

    // 重置结果区域
    var resultsSection = document.getElementById('resultsSection');
    if (resultsSection) {
        resultsSection.classList.remove('visible');
        resultsSection.innerHTML =
            '<div id="drillModelContainer" style="flex:1;width:100%;min-height:0;border-radius:8px;overflow:hidden;background:#f0f0f0;">' +
            '<iframe src="/static/drillAngleExplain.HTML" style="width:100%;height:100%;border:none;" allowfullscreen></iframe>' +
            '</div><div id="resultsContent"></div>';
        resultsSection.style.display = '';
    }

    // 重置参数面板
    var paramsBody = document.getElementById('paramsBody');
    var paramsContent = document.getElementById('paramsContent');
    var paramsLoading = document.getElementById('paramsLoading');
    var btnApplyParams = document.getElementById('btnApplyParams');
    var paramsHint = document.getElementById('paramsHint');
    if (paramsBody) paramsBody.style.display = 'none';
    if (paramsContent) paramsContent.style.display = 'none';
    if (paramsLoading) paramsLoading.style.display = 'block';
    if (btnApplyParams) btnApplyParams.style.display = 'none';
    if (paramsHint) paramsHint.textContent = '';

    // 隐藏结果 tab
    var resultTabs = document.getElementById('resultTabs');
    if (resultTabs) resultTabs.style.display = 'none';

    // 关闭所有弹窗
    var previewModal = document.getElementById('previewModal');
    if (previewModal) previewModal.classList.remove('active');
    var interactiveModal = document.getElementById('interactiveModal');
    if (interactiveModal) interactiveModal.style.display = 'none';
    var fullscreenModal = document.getElementById('fullscreenModal');
    if (fullscreenModal) fullscreenModal.classList.remove('active');

    // 更新按钮状态
    updateButtonStates();

    // 恢复模板数据预览
    if (typeof loadTemplateData === 'function') {
        loadTemplateData();
    }
}