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
let hasRunParamAnalysis = false; // RBF参数分析是否已完成（启用建模示意图的前提）
let selectedAIViews = [];  // 用户勾选的 AI 建模参考视图 name 列表


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
const btnModelParams = document.getElementById('btnModelParams');
const btnQualityCheck = document.getElementById('btnQualityCheck');
const fullscreenImage = document.getElementById('fullscreenImage');
const fullscreenClose = document.getElementById('fullscreenClose');

const interactiveModal = document.getElementById('interactiveModal');
const interactiveClose = document.getElementById('interactiveClose');

// ==================== 工具函数 ====================
function setStatus(message, type = 'info') {
    var el = document.getElementById('statusCurrent');
    if (!el) el = statusMessage; // fallback
    el.textContent = message;
    el.className = 'status-current';
    if (type) el.classList.add(type);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 坐标/高程列的列名（开孔坐标E、开孔坐标N、开孔高程R 等）
function isCoordColumn(name) {
    return /坐标|高程/.test(String(name));
}

// 坐标类数值统一显示为「保留两位小数的普通数字」(如 3232138.97)，
// 既不用 3.1825M / 523.55K 这类缩写，也不显示浮点原始全精度。
// 无法转成数字时返回 null，由调用方决定回退显示。
function formatCoord2(val) {
    if (val === undefined || val === null || val === '') return null;
    const n = Number(val);
    return Number.isFinite(n) ? n.toFixed(2) : null;
}

function updateButtonStates() {
    var hasFile = !!sessionId;
    var hasModelViews = modelData && modelData.color_map && Object.keys(modelData.color_map).length > 0;
    var hasAISelected = modelData && modelData.ai && modelData.ai.selected_index !== undefined;
    var btnMultiviewAI = document.getElementById('btnMultiviewAI');
    var krigAnalysis = document.getElementById('btnKrigingAnalysis');
    var btnAnalyzeRBF = document.getElementById('btnAnalyzeRBF');
    var btnAnalyzeKriging = document.getElementById('btnAnalyzeKriging');

    btnDrillViews.disabled = !hasFile;
    btnModelViews.disabled = !hasFile || !hasRunParamAnalysis;
    btnInteractive.disabled = !hasFile;
    btnAIModeling.disabled = !hasModelViews;
    btnKriging.disabled = !hasFile;
    if (krigAnalysis) krigAnalysis.disabled = !hasFile;
    if (btnMultiviewAI) btnMultiviewAI.disabled = !hasAISelected;
    if (btnAnalyzeRBF) btnAnalyzeRBF.disabled = !hasFile;
    if (btnAnalyzeKriging) btnAnalyzeKriging.disabled = !hasFile;
    if (btnModelParams) btnModelParams.disabled = !hasFile;
    if (btnQualityCheck) btnQualityCheck.disabled = !hasFile;
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
    btnAnalyzeRBF: 'rbfTimer',
    btnAnalyzeKriging: 'krigingParamTimer',
    btnQualityCheck: 'krigingParamTimer'
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
        console.log('Generate model response URLs:',
            (data.labeled_views || []).map(function(v) { return v.url; }),
            (data.unlabeled_views || []).map(function(v) { return v.url; }));

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
            // 标注版和无标注版联动轮播 — 包裹在统一容器中
            var wrapper = document.createElement('div');
            wrapper.className = 'model-views-wrapper';
            resultsSection.appendChild(wrapper);

            var cont = document.createElement('div');
            wrapper.appendChild(cont);
            var labeledViews = data.labeled_views.map(function(v) { return { url: v.url, label: v.label || '' }; });
            var unlabeledViews = data.unlabeled_views.map(function(v) { return { url: v.url, label: v.label || '' }; });
            renderLinkedCarousel(cont, labeledViews, unlabeledViews, '标注版', '无标注版');
            // 在轮播下方增加 AI 建模参考图选择区域
            renderViewSelectionCheckboxes(data, wrapper);
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

// ==================== AI 建模参考图选择区域 ====================
function renderViewSelectionCheckboxes(data, parentContainer) {
	var container = parentContainer || document.getElementById('resultsSection');
	if (!container || !data.unlabeled_views || data.unlabeled_views.length === 0) return;

	// 移除旧的选择区域
	var oldSel = document.getElementById('viewSelectionArea');
	if (oldSel) oldSel.remove();

	// 初始默认勾选
	var defaultViews = data.default_selected_views || ['main_view', 'east_west_section', 'north_south_section'];
	selectedAIViews = defaultViews.slice(0, 3);

	var area = document.createElement('div');
	area.id = 'viewSelectionArea';
	area.className = 'view-selection';

	var title = document.createElement('div');
	title.className = 'view-selection-title';
	title.textContent = '🤖 AI 建模参考图选择（请勾选恰好 3 张）：';
	area.appendChild(title);

	var grid = document.createElement('div');
	grid.className = 'view-selection-grid';

	// 按 order 排序
	var views = data.unlabeled_views.slice().sort(function(a, b) { return (a.order || 0) - (b.order || 0); });

	views.forEach(function(v) {
		var isChecked = selectedAIViews.indexOf(v.name) !== -1;
		var item = document.createElement('div');
		item.className = 'view-selection-item' + (isChecked ? ' selected' : '');
		item.dataset.viewName = v.name;

		var checkbox = document.createElement('input');
		checkbox.type = 'checkbox';
		checkbox.checked = isChecked;
		checkbox.className = 'view-checkbox';
		checkbox.addEventListener('change', function() {
			updateViewSelection(v.name, this.checked);
		});

		var thumb = document.createElement('img');
		thumb.src = v.url;
		thumb.alt = v.label || v.name;
		thumb.addEventListener('click', function(e) {
			checkbox.checked = !checkbox.checked;
			updateViewSelection(v.name, checkbox.checked);
		});

		var label = document.createElement('span');
		label.className = 'view-name';
		label.textContent = v.label || v.name;

		var topRow = document.createElement('div');
		topRow.style.cssText = 'display:flex;align-items:center;gap:4px;width:100%;';
		topRow.appendChild(checkbox);
		topRow.appendChild(label);

		item.appendChild(topRow);
		item.appendChild(thumb);
		grid.appendChild(item);
	});

	area.appendChild(grid);

	var status = document.createElement('div');
	status.className = 'view-selection-status';
	status.id = 'viewSelectionStatus';
	status.textContent = '已选择 ' + selectedAIViews.length + '/3';
	area.appendChild(status);

	container.appendChild(area);
}

function updateViewSelection(viewName, checked) {
	if (checked) {
		if (selectedAIViews.indexOf(viewName) === -1) {
			if (selectedAIViews.length >= 3) {
				var removed = selectedAIViews.shift();
				var oldItem = document.querySelector('.view-selection-item[data-view-name="' + removed + '"]');
				if (oldItem) {
					oldItem.classList.remove('selected');
					var oldCb = oldItem.querySelector('.view-checkbox');
					if (oldCb) oldCb.checked = false;
				}
			}
			selectedAIViews.push(viewName);
		}
	} else {
		var idx = selectedAIViews.indexOf(viewName);
		if (idx !== -1) selectedAIViews.splice(idx, 1);
	}

	var item = document.querySelector('.view-selection-item[data-view-name="' + viewName + '"]');
	if (item) {
		if (checked) {
			item.classList.add('selected');
		} else {
			item.classList.remove('selected');
		}
	}

	var status = document.getElementById('viewSelectionStatus');
	if (status) {
		status.textContent = '已选择 ' + selectedAIViews.length + '/3';
	}
}

// ==================== AI建模 ====================
btnAIModeling.addEventListener('click', async () => {
    if (!modelData || !modelData.color_map || Object.keys(modelData.color_map).length === 0) {
        setStatus('!!! 请先生成建模示意图', 'error');
        return;
    }

    // 验证恰好选中3个视角
    if (!selectedAIViews || selectedAIViews.length !== 3) {
        setStatus('!!! 请勾选恰好3个视角作为AI建模参考图', 'error');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在进行AI建模，请稍候...', 'loading');

    const timer = startButtonTimer(btnAIModeling, 'AI 建模中');

    // 设置 300s 超时，防止连接静默断开
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000);

    try {
        const response = await fetch('/api/ai_modeling', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                color_map: modelData.color_map,
                file_path: filePath,
                selected_views: selectedAIViews
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
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
    // 两张候选左右平放
    html += '<div class="linked-carousel">';

    for (const c of data.candidates) {
        const isBest = (c.index === data.best_index);
        const scoreText = (c.scores && c.scores.total_score !== undefined)
            ? '综合评分: ' + (c.scores.total_score * 100).toFixed(1)
            : '';
        const ssimText = (c.scores && c.scores.ssim !== undefined)
            ? '几何相似度: ' + (c.scores.ssim * 100).toFixed(1)
            : '';

        html += '<div class="linked-pane">';
        html += '<div class="uniform-card" data-index="' + c.index + '" style="' + (isBest ? 'border:2px solid #2E7D32;' : '') + '">';
        if (isBest) {
            html += '<div style="position:absolute;top:12px;right:12px;background:#2E7D32;color:white;padding:4px 10px;border-radius:4px;font-size:12px;font-weight:bold;z-index:10;">推荐</div>';
        }
        // 图片容器：包含 hover 显示的放大和下载按钮
        html += '<div class="card-img-wrapper">';
        html += '<img src="' + c.url + '" alt="AI 候选 ' + c.index + '" style="width:100%;max-height:400px;object-fit:contain;background:#f8f9fc;display:block;">';
        // 放大镜按钮
        html += '<button class="uniform-zoom-btn zoom-btn" data-url="' + c.url + '" title="放大预览">🔍</button>';
        // 下载按钮
        html += '<button class="uniform-zoom-btn download-btn" data-url="' + c.url + '" data-index="' + c.index + '" title="下载保存" style="right:62px;">⬇</button>';
        html += '</div>';
        html += '<div class="card-title">候选 ' + c.index;
        if (scoreText) html += ' | ' + scoreText;
        if (ssimText) html += ' | ' + ssimText;
        html += '</div>';
        html += '<div style="padding:8px 16px 12px;text-align:center;">';
        html += '<button class="btn-select" data-index="' + c.index + '" style="width:100%;">使用这张</button>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
    }

    html += '</div>';

    if (data.is_close) {
        html += '<p class="close-hint">💡 两张图评分接近，建议人工对比选择。</p>';
    }

    resultsSection.innerHTML = html;

    // 绑定放大镜按钮
    document.querySelectorAll('.uniform-zoom-btn.zoom-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            openFullscreen(this.dataset.url);
        });
    });

    // 绑定下载按钮
    document.querySelectorAll('.uniform-zoom-btn.download-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var imgUrl = this.dataset.url;
            var index = this.dataset.index;
            var link = document.createElement('a');
            link.href = imgUrl;
            link.download = 'AI建模_候选' + index + '.png';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    });

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
        html += '<button class="interactive-tab" data-tab="geology">🏔️ 地质体模型</button>';
        html += '</div>';

        // Tab 内容区域
        html += '<div class="interactive-tab-contents">';
        html += '<div class="interactive-tab-content active" id="tab-drill">';
        html += '<div class="interactive-frame-content">';
        html += '<iframe src="' + drillHtmlUrl + '"></iframe>';
        html += '</div>';
        html += '</div>';
        // 地质体模型标签（懒加载）
        html += '<div class="interactive-tab-content" id="tab-geology">';
            html += '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;">';
            html += '<p style="color:#999;font-size:16px;">💡 点击地质体模型选项卡后加载</p>';
            html += '</div>';
            html += '</div>';
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
                        geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;"><p style="color:#666;font-size:16px;">⏳ 正在加载地质体模型...</p></div>';

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
                                geologyContent.innerHTML = '<div class="interactive-frame-content"><iframe src="' + fullData.html_url + '"></iframe></div>';
                            } else {
                                geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;"><p style="color:#e74c3c;font-size:16px;">地质体模型生成失败</p></div>';
                            }
                        } catch(e) {
                            geologyContent.innerHTML = '<div class="interactive-frame-content" style="display:flex;align-items:center;justify-content:center;"><p style="color:#e74c3c;font-size:16px;">加载失败: ' + e.message + '</p></div>';
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

        startLogPolling(sessionId);
        setStatus('正在进行多视角纹理升级（全部6个视角）...', 'loading');
        const timer = startButtonTimer(btnMultiviewAI, '纹理升级中');

        try {
            const response = await fetch('/api/multiview_texture_upgrade', {
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
            hideResultTabs();
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

    // 用包装容器隔离，避免 CSS > div:not(.linked-carousel) 的 flex 链影响
    var html = '<div class="kriging-results-wrapper">';

    html += '<h2>📊 克里金 vs RBF 对比分析</h2>';

    if (hasImages) {
        html += '<p style="color:#666;font-size:13px;margin-bottom:12px;">';
        html += '分析完成，共 ' + layerCount + ' 个岩性层。';
        html += '每张图为 2×2 并排布局（左上:克里金 / 右上:RBF / 左下:预测标准差 / 右下:差值）。';
        html += '</p>';
    }

    // ===== Tab 切换 =====
    html += '<div class="kriging-tabs">';
    html += '  <button class="kriging-tab active" data-tab="chart">📊 对比图</button>';
    html += '  <button class="kriging-tab" data-tab="report">📋 数值分析报告</button>';
    html += '</div>';

    // ===== Tab 内容：对比图 =====
    html += '<div class="kriging-tab-content active" id="krigingTabChart">';
    if (hasImages) {
        if (data.comparison_paths.length > 1) {
            html += '<div class="kriging-layer-selector" id="krigingLayerSelector">';
            for (var i = 0; i < data.comparison_paths.length; i++) {
                var activeClass = i === 0 ? 'active' : '';
                html += '<button class="kriging-layer-btn ' + activeClass + '" data-index="' + i + '">' + data.comparison_paths[i].lith + '</button>';
            }
            html += '</div>';
        }

        html += '<div id="krigingComparisonDisplay">';
        html += '<img src="' + data.comparison_paths[0].url + '?t=' + Date.now() + '" alt="克里金对比分析图" class="kriging-comparison-img" onclick="openFullscreen(\'' + data.comparison_paths[0].url + '\')" style="cursor:pointer;">';
        html += '</div>';
    } else {
        html += '<p style="color:#999;text-align:center;padding:40px;">暂无对比图</p>';
    }
    html += '</div>'; // krigingTabChart

    // ===== Tab 内容：数值分析报告 =====
    html += '<div class="kriging-tab-content" id="krigingTabReport">';
    html += '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">';
    html += '  <button class="btn-report-download" id="btnReportDownload" title="下载报告">⬇ 导出报告</button>';
    html += '</div>';
    html += '<pre id="krigingReportPre" style="white-space:pre-wrap;font-size:13px;line-height:1.6;color:#333;"></pre>';
    html += '</div>'; // krigingTabReport

    html += '</div>'; // kriging-results-wrapper

    resultsSection.innerHTML = html;

    // 安全地设置报告文本
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
            display.innerHTML = '<img src="' + path + '?t=' + Date.now() + '" alt="克里金对比分析图" class="kriging-comparison-img" onclick="openFullscreen(\'' + path + '\')" style="cursor:pointer;">';
        });
    }

    // 绑定 Tab 切换事件
    var tabContainer = document.querySelector('.kriging-tabs');
    if (tabContainer) {
        tabContainer.addEventListener('click', function(e) {
            var tab = e.target.closest('.kriging-tab');
            if (!tab) return;

            // 切换 tab 高亮
            tabContainer.querySelectorAll('.kriging-tab').forEach(function(t) { t.classList.remove('active'); });
            tab.classList.add('active');

            // 切换内容
            var target = tab.dataset.tab;
            document.querySelectorAll('.kriging-tab-content').forEach(function(c) { c.classList.remove('active'); });
            var contentEl = document.getElementById('krigingTab' + target.charAt(0).toUpperCase() + target.slice(1));
            if (contentEl) contentEl.classList.add('active');
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

    if (!data.images || data.images.length === 0) {
        resultsSection.innerHTML = '<p>没有可显示的图片</p>';
        return;
    }

    const uid = 'multiview-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6);
    let html = '<h2>多视角纹理升级结果</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:12px;">成功生成 ' + data.success_count + '/' + data.total_count + ' 张。</p>';

    // 翻页式轮播容器
    html += '<div class="carousel-container" id="' + uid + '">';
    html += '<div class="carousel-viewport">';
    html += '<div class="carousel-track" id="track-' + uid + '">';
    for (let i = 0; i < data.images.length; i++) {
        const img = data.images[i];
        html += '<div class="carousel-slide">';
        // 标题
        html += '<div class="card-title" style="border-top:none;background:#f5f5f5;font-weight:700;color:#333;padding:8px 16px;text-align:center;">' + img.view_label + '</div>';
        // 图片 + 操作按钮
        html += '<div class="card-img-wrapper" style="position:relative;">';
        html += '<img src="' + img.url + '" alt="' + img.view_label + '" style="width:100%;max-height:560px;object-fit:contain;background:#f8f9fc;display:block;" onerror="this.style.display=\'none\';this.insertAdjacentHTML(\'afterend\',\'<div style=background:#fff3cd;color:#856404;padding:40px;text-align:center;border-radius:4px>⚠️ 图片加载失败<br><small>\' + this.src.split(\'?t=\')[0].split(\'/\').pop() + \'</small></div>\')">';
        // 放大镜按钮
        html += '<button class="zoom-btn" data-url="' + img.url + '" title="放大预览">🔍</button>';
        html += '</div>';
        html += '</div>';
    }
    html += '</div></div>';

    // 控制栏
    html += '<div class="carousel-controls">';
    html += '<button class="carousel-btn" data-action="prev" data-uid="' + uid + '">‹</button>';
    html += '<span class="carousel-label" id="label-' + uid + '">' + data.images[0].view_label + '</span>';
    html += '<div class="carousel-indicators" id="indicators-' + uid + '">';
    for (let i = 0; i < data.images.length; i++) {
        html += '<button class="carousel-dot ' + (i === 0 ? 'active' : '') + '" data-index="' + i + '" data-uid="' + uid + '"></button>';
    }
    html += '</div>';
    html += '<button class="carousel-btn" data-action="next" data-uid="' + uid + '">›</button>';
    html += '</div>';

    // 下载按钮组
    html += '<div style="display:flex; justify-content:center; gap:12px; margin-top:12px; flex-wrap:wrap;">';
    html += '<button class="btn btn-primary" onclick="downloadCurrentMultiview(\'' + uid + '\')">📥 下载当前图</button>';
    html += '<button class="btn btn-primary" onclick="downloadAllMultiview(\'' + uid + '\')">📥 下载全部</button>';
    html += '</div>';
    html += '</div>';

    resultsSection.innerHTML = html;

    // 初始化轮播状态
    const state = { views: data.images, currentIndex: 0, uid: uid };
    const containerEl = document.getElementById(uid);
    containerEl._carouselState = state;

    // 绑定翻页事件
    containerEl.querySelector('[data-action="prev"]').addEventListener('click', function() {
        const st = containerEl._carouselState;
        st.currentIndex = (st.currentIndex - 1 + st.views.length) % st.views.length;
        updateMultiviewCarousel(containerEl);
    });
    containerEl.querySelector('[data-action="next"]').addEventListener('click', function() {
        const st = containerEl._carouselState;
        st.currentIndex = (st.currentIndex + 1) % st.views.length;
        updateMultiviewCarousel(containerEl);
    });
    containerEl.querySelectorAll('.carousel-dot').forEach(dot => {
        dot.addEventListener('click', function() {
            const idx = parseInt(this.dataset.index);
            const st = containerEl._carouselState;
            st.currentIndex = idx;
            updateMultiviewCarousel(containerEl);
        });
    });

    // 绑定放大镜按钮（直接使用 openFullscreen）
    containerEl.querySelectorAll('.zoom-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            openFullscreen(this.dataset.url);
        });
    });
}

function updateMultiviewCarousel(containerEl) {
    const state = containerEl._carouselState;
    const track = containerEl.querySelector('.carousel-track');
    const label = containerEl.querySelector('.carousel-label');
    const dots = containerEl.querySelectorAll('.carousel-dot');

    if (track) {
        track.style.transform = 'translateX(-' + (state.currentIndex * 100) + '%)';
    }
    if (label && state.views[state.currentIndex]) {
        label.textContent = state.views[state.currentIndex].view_label;
    }
    dots.forEach((dot, i) => {
        dot.classList.toggle('active', i === state.currentIndex);
    });
}

function downloadCurrentMultiview(uid) {
    const container = document.getElementById(uid);
    if (!container) return;
    const state = container._carouselState;
    if (!state) return;
    const view = state.views[state.currentIndex];
    if (view) {
        const link = document.createElement('a');
        link.href = view.url;
        link.download = (view.view_label || 'multiview') + '.png';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

function downloadAllMultiview(uid) {
    const container = document.getElementById(uid);
    if (!container) return;
    const state = container._carouselState;
    if (!state) return;
    const urls = state.views.map(v => v.url);
    downloadAllAsZip(urls, 'multiview_texture_upgrade.zip');
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
            // 渲染由 btnModelParams 点击触发，此处只保存数据
        }
    } catch (error) {
        console.error('加载参数失败:', error);
    }
}

// 在右侧结果区域渲染建模参数页面
function renderModelParamsPage() {
    const resultsSection = document.getElementById('resultsSection');
    if (!resultsSection) return;

    // 隐藏钻孔模型容器
    var drillContainer = document.getElementById('drillModelContainer');
    if (drillContainer) drillContainer.style.display = 'none';

    // 检查是否有参数元数据
    if (!currentParamsMeta || Object.keys(currentParamsMeta).length === 0) {
        resultsSection.innerHTML = `
            <div class="model-params-page">
                <h2>⚙️ 建模参数</h2>
                <p style="color:#999;text-align:center;padding:40px 0;">请先上传数据文件</p>
            </div>
        `;
        return;
    }

    // 按 group 分组
    const groups = {};
    const groupOrder = ['建模参数', '钻孔显示参数'];
    for (const [key, meta] of Object.entries(currentParamsMeta)) {
        const g = meta.group || '';
        if (!groups[g]) groups[g] = [];
        groups[g].push({ key, meta });
    }

    let html = `<div class="model-params-page"><h2>⚙️ 建模参数</h2>`;
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
    // 应用按钮 + 提示
    html += `<button class="btn btn-primary params-apply-btn" id="btnApplyParamsRight">应用参数</button>`;
    html += `<div class="params-hint" id="paramsHintRight"></div>`;
    html += `</div>`;

    resultsSection.innerHTML = html;
    resultsSection.classList.add('visible');

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
                const currentVal = currentParams[key] !== undefined ? currentParams[key] : meta.default;
                if (currentVal === null || currentVal === undefined) {
                    autoCheck.checked = true;
                    slider.disabled = true;
                    input.disabled = true;
                }
            }
        }
    }

    // 绑定应用按钮
    const applyBtn = document.getElementById('btnApplyParamsRight');
    if (applyBtn) {
        applyBtn.addEventListener('click', applyParamsRight);
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

// 应用参数（旧版，保留用于兼容）
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
    } catch (error) {
        setStatus('!!! 参数保存失败: ' + error.message, 'error');
    }
}

// 右侧参数页面的应用按钮
async function applyParamsRight() {
    if (!sessionId) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    const params = collectParamsFromUI();
    const hint = document.getElementById('paramsHintRight');

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
            hint.textContent = '✓ 参数已应用，下次生成时生效';
            hint.style.color = '#2E7D32';
        }
    } catch (error) {
        setStatus('!!! 参数保存失败: ' + error.message, 'error');
    }
}

// 建模参数按钮 — 在右侧结果区域展示参数页面
function initModelParamsButton() {
    if (btnModelParams) {
        btnModelParams.addEventListener('click', function() {
            if (!sessionId) {
                setStatus('!!! 请先上传文件', 'error');
                return;
            }
            currentAnalysisMode = null;
            renderModelParamsPage();
            setStatus('==> 建模参数页面已打开', 'info');
        });
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

            // 自动应用推荐参数，并启用建模示意图
            var analysisKeys = Object.keys(data.analysis || {});
            if (analysisKeys.length > 0) {
                var analysisResult = data.analysis[analysisKeys[0]];
                if (analysisResult && analysisResult.best && analysisResult.best.rbf_function) {
                    applyBestParams(analysisResult.best);
                }
            }
            hasRunParamAnalysis = true;
            updateButtonStates();
            hideResultTabs();
            setStatus('==> RBF 参数分析完成，已自动应用推荐参数，可点击建模示意图', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            clearInterval(progressInterval);
            setStatus('!!! 分析失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

// ==================== 克里金参数分析 ====================
const btnAnalyzeKriging = document.getElementById('btnAnalyzeKriging');
if (btnAnalyzeKriging) {
    btnAnalyzeKriging.addEventListener('click', async function() {
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
        if (!targetLayer) return;

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
        setStatus('正在进行克里金参数分析...', 'loading');
        var timer = startButtonTimer(btnAnalyzeKriging, '参数分析中');

        // 4. 显示进度条
        if (resultsSection) {
            resultsSection.innerHTML = [
                '<div class="analysis-progress">',
                '   <h3>📊 克里金参数分析进行中</h3>',
                '   <div class="progress-bar-wrap">',
                '       <div class="progress-bar-fill" id="krigingParamProgressFill" style="width: 0%;"></div>',
                '   </div>',
                '   <p id="krigingParamProgressText">准备中...</p>',
                '</div>'
            ].join('');
            resultsSection.classList.add('visible');
        }

        // 5. 假进度
        var fakeProgress = 0;
        var progressInterval = setInterval(function() {
            fakeProgress += 10;
            if (fakeProgress > 90) fakeProgress = 90;
            var fill = document.getElementById('krigingParamProgressFill');
            var text = document.getElementById('krigingParamProgressText');
            if (fill) fill.style.width = fakeProgress + '%';
            if (text) text.textContent = '正在计算...（约 ' + fakeProgress + '%）';
        }, 800);

        try {
            var response = await fetch('/api/analyze_kriging_params', {
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

            var fill = document.getElementById('krigingParamProgressFill');
            if (fill) fill.style.width = '100%';

            renderKrigingParamResults(data);
            updateButtonStates();
            hideResultTabs();
            setStatus('==> 克里金参数分析完成', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            clearInterval(progressInterval);
            setStatus('!!! 分析失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

// ==================== 模型质量评估 ====================
if (btnQualityCheck) {
    btnQualityCheck.addEventListener('click', async function() {
        if (!sessionId || !filePath) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }

        // 隐藏钻孔模型容器
        var drillContainer = document.getElementById('drillModelContainer');
        if (drillContainer) drillContainer.style.display = 'none';

        var resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.innerHTML = '';
            resultsSection.classList.remove('visible');
        }

        // 开始评估
        startLogPolling(sessionId);
        setStatus('正在进行模型质量评估...', 'loading');
        var timer = startButtonTimer(btnQualityCheck, '质量评估中');

        // 显示进度条
        if (resultsSection) {
            resultsSection.innerHTML = [
                '<div class="analysis-progress">',
                '   <h3>✅ 模型质量评估进行中</h3>',
                '   <div class="progress-bar-wrap">',
                '       <div class="progress-bar-fill" id="qualityProgressFill" style="width: 0%;"></div>',
                '   </div>',
                '   <p id="qualityProgressText">准备中...</p>',
                '</div>'
            ].join('');
            resultsSection.classList.add('visible');
        }

        // 假进度
        var fakeProgress = 0;
        var progressInterval = setInterval(function() {
            fakeProgress += 15;
            if (fakeProgress > 90) fakeProgress = 90;
            var fill = document.getElementById('qualityProgressFill');
            var text = document.getElementById('qualityProgressText');
            if (fill) fill.style.width = fakeProgress + '%';
            if (text) text.textContent = '正在评估...（约 ' + fakeProgress + '%）';
        }, 500);

        try {
            var response = await fetch('/api/evaluate_quality', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    path: filePath
                })
            });
            var data = await response.json();
            stopLogPolling();

            clearInterval(progressInterval);

            if (data.error) {
                setStatus('!!! ' + data.error, 'error');
                if (timer) timer.stop();
                if (resultsSection) {
                    resultsSection.innerHTML = '<p style="color:#c62828;text-align:center;padding:40px;">评估失败: ' + data.error + '</p>';
                }
                if (drillContainer) drillContainer.style.display = 'flex';
                return;
            }

            var fill = document.getElementById('qualityProgressFill');
            if (fill) fill.style.width = '100%';

            renderQualityReport(data);
            updateButtonStates();
            hideResultTabs();
            setStatus('==> 模型质量评估完成', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            clearInterval(progressInterval);
            setStatus('!!! 评估失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

// ==================== 质量评估渲染函数 ====================

function renderQualityReport(data) {
    var html = buildQualityReportHTML(data);
    var section = document.getElementById('resultsSection');
    if (!section) return;
    section.innerHTML = html;
    section.classList.add('visible');

    // 初始化 Tab 切换
    initQualityTabs();

    // 填充各 Tab 内容
    renderIntersectionTab(data.layer_intersection);
    renderThicknessTab(data.thickness_variation);
    renderPinchoutTab(data.pinch_out);
    renderSummaryTab(data);

    // 默认选中第一个 Tab
    activateQualityTab('tab-intersection');
}

function buildQualityReportHTML(data) {
    return [
        '<div class="quality-report">',
        '  <h2 class="quality-report-title">✅ 模型质量评估报告</h2>',
        '  <div class="quality-score-card">',
        '    <div class="quality-score-circle" style="border-color: ' + data.grade_color + '">',
        '      <span class="quality-score-value" style="color: ' + data.grade_color + '">' + data.overall_score + '</span>',
        '      <span class="quality-score-label" style="color: ' + data.grade_color + '">' + data.overall_grade + '</span>',
        '    </div>',
        '    <div class="quality-score-detail">',
        '      <p class="quality-score-title">综合评分</p>',
        '      <p class="quality-score-sub">满分 100 分</p>',
        '    </div>',
        '  </div>',
        '  <div class="quality-tabs">',
        '    <button class="quality-tab active" data-tab="tab-intersection">层间关系检查</button>',
        '    <button class="quality-tab" data-tab="tab-thickness">厚度变化检查</button>',
        '    <button class="quality-tab" data-tab="tab-pinchout">尖灭识别</button>',
        '    <button class="quality-tab" data-tab="tab-summary">综合质量报告</button>',
        '  </div>',
        '  <div class="quality-tab-content" id="tab-intersection"></div>',
        '  <div class="quality-tab-content" id="tab-thickness" style="display:none"></div>',
        '  <div class="quality-tab-content" id="tab-pinchout" style="display:none"></div>',
        '  <div class="quality-tab-content" id="tab-summary" style="display:none"></div>',
        '</div>'
    ].join('');
}

function initQualityTabs() {
    var tabs = document.querySelectorAll('.quality-tab');
    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            var target = this.getAttribute('data-tab');
            activateQualityTab(target);
        });
    });
}

function activateQualityTab(tabId) {
    // Tab 按钮激活状态
    var tabs = document.querySelectorAll('.quality-tab');
    tabs.forEach(function(t) { t.classList.remove('active'); });
    var activeTab = document.querySelector('.quality-tab[data-tab="' + tabId + '"]');
    if (activeTab) activeTab.classList.add('active');

    // 内容切换
    var contents = document.querySelectorAll('.quality-tab-content');
    contents.forEach(function(c) { c.style.display = 'none'; });
    var targetContent = document.getElementById(tabId);
    if (targetContent) targetContent.style.display = 'block';
}

function renderIntersectionTab(data) {
    var container = document.getElementById('tab-intersection');
    if (!container) return;

    var statusIcon = data.has_intersection ? '❌' : '✅';
    var statusText = data.has_intersection ? '存在穿层' : '无穿层';
    var statusColor = data.has_intersection ? '#c62828' : '#2E7D32';

    var html = [
        '<div class="quality-block">',
        '  <h3>层间关系检查</h3>',
        '  <div class="metric-row">',
        '    <div class="metric-item">',
        '      <span class="metric-label">状态</span>',
        '      <span class="metric-value" style="color:' + statusColor + '">' + statusIcon + ' ' + statusText + '</span>',
        '    </div>',
        '    <div class="metric-item">',
        '      <span class="metric-label">穿层网格数</span>',
        '      <span class="metric-value">' + data.intersection_cells + ' / ' + data.total_cells + '</span>',
        '    </div>',
        '    <div class="metric-item">',
        '      <span class="metric-label">穿层比例</span>',
        '      <span class="metric-value">' + (data.intersection_ratio * 100).toFixed(2) + '%</span>',
        '    </div>',
        '  </div>',
        '  <div class="quality-hint">注意：穿层指同一位置顶面低于底面，通常由数据异常或插值失真引起。</div>',
        '</div>'
    ];

    if (data.details && data.details.length > 0) {
        html.push('<div class="quality-block"><h4>穿层位置详情（最多显示 5 处）</h4><ul class="quality-list">');
        data.details.forEach(function(d) {
            html.push('<li>岩性 <strong>' + d.layer + '</strong> 在 (' + Number(d.x).toFixed(2) + ', ' + Number(d.y).toFixed(2) + ') 处差值 ' + d.gap.toFixed(2) + ' m</li>');
        });
        html.push('</ul></div>');
    }

    container.innerHTML = html.join('');
}

function renderThicknessTab(data) {
    var container = document.getElementById('tab-thickness');
    if (!container) return;

    if (!data.layers || data.layers.length === 0) {
        container.innerHTML = '<div class="quality-block"><p>无厚度变化数据</p></div>';
        return;
    }

    var html = ['<div class="quality-block"><h3>厚度变化检查</h3>'];
    data.layers.forEach(function(layer) {
        var anomalyIcon = layer.has_anomaly ? '⚠️' : '✅';
        var anomalyColor = layer.has_anomaly ? '#F57C00' : '#2E7D32';
        html.push([
            '<div class="quality-layer-card">',
            '  <h4>' + anomalyIcon + ' 岩性: ' + layer.layer + '</h4>',
            '  <div class="metric-row">',
            '    <div class="metric-item"><span class="metric-label">最大厚度梯度</span><span class="metric-value">' + layer.max_gradient + ' m/m</span></div>',
            '    <div class="metric-item"><span class="metric-label">厚度范围</span><span class="metric-value">' + layer.thickness_min + ' ~ ' + layer.thickness_max + ' m</span></div>',
            '    <div class="metric-item"><span class="metric-label">平均厚度</span><span class="metric-value">' + layer.thickness_mean + ' m</span></div>',
            '    <div class="metric-item"><span class="metric-label">梯度异常网格</span><span class="metric-value" style="color:' + anomalyColor + '">' + layer.anomaly_count + '</span></div>',
            '  </div>',
            '</div>'
        ].join(''));
    });
    html.push('</div>');
    container.innerHTML = html.join('');
}

function renderPinchoutTab(data) {
    var container = document.getElementById('tab-pinchout');
    if (!container) return;

    if (!data.layers || data.layers.length === 0) {
        container.innerHTML = '<div class="quality-block"><p>无尖灭数据</p></div>';
        return;
    }

    var html = ['<div class="quality-block"><h3>尖灭识别</h3>'];
    data.layers.forEach(function(layer) {
        var icon = layer.is_reasonable ? '✅' : '⚠️';
        var color = layer.is_reasonable ? '#2E7D32' : '#F57C00';
        html.push([
            '<div class="quality-layer-card">',
            '  <h4>' + icon + ' 岩性: ' + layer.layer + '</h4>',
            '  <div class="metric-row">',
            '    <div class="metric-item"><span class="metric-label">尖灭比例</span><span class="metric-value">' + (layer.pinch_ratio * 100).toFixed(2) + '%</span></div>',
            '    <div class="metric-item"><span class="metric-label">尖灭网格数</span><span class="metric-value">' + layer.pinch_count + '</span></div>',
            '    <div class="metric-item"><span class="metric-label">判断</span><span class="metric-value" style="color:' + color + '">' + layer.comment + '</span></div>',
            '  </div>',
            '</div>'
        ].join(''));
    });
    html.push('</div>');
    container.innerHTML = html.join('');
}

function renderSummaryTab(data) {
    var container = document.getElementById('tab-summary');
    if (!container) return;

    var html = [
        '<div class="quality-block">',
        '  <h3>📋 综合质量报告</h3>',
        '  <div class="quality-summary-card">',
        '    <div class="quality-summary-header" style="border-left: 4px solid ' + data.grade_color + '">',
        '      <h4 style="color:' + data.grade_color + '">综合评级：' + data.overall_grade + '（' + data.overall_score + ' 分）</h4>',
        '    </div>'
    ];

    // 扣分项
    if (data.penalties && data.penalties.length > 0) {
        html.push('<div class="quality-penalties"><h4>扣分项</h4><ul class="quality-list">');
        data.penalties.forEach(function(p) {
            html.push('<li>' + p + '</li>');
        });
        html.push('</ul></div>');
    } else {
        html.push('<div class="quality-penalties"><p style="color:#2E7D32">✅ 无扣分项</p></div>');
    }

    // 已知局限
    if (data.limitations && data.limitations.length > 0) {
        html.push('<div class="quality-limitations"><h4>已知局限</h4><ul class="quality-list">');
        data.limitations.forEach(function(l) {
            html.push('<li>' + l + '</li>');
        });
        html.push('</ul></div>');
    }

    // 参数调整建议
    if (data.recommendations && data.recommendations.length > 0) {
        html.push('<div class="quality-recommendations"><h4>💡 参数调整建议</h4>');
        data.recommendations.forEach(function(r) {
            var bgColor = '#e3f2fd';
            var borderColor = '#1565C0';
            var icon = '💡';
            if (r.severity === 'warning') {
                bgColor = '#fff3e0';
                borderColor = '#F57C00';
                icon = '⚠️';
            } else if (r.severity === 'error') {
                bgColor = '#ffebee';
                borderColor = '#C62828';
                icon = '❌';
            }
            html.push([
                '<div class="recommendation-item" style="background:' + bgColor + ';border-left:3px solid ' + borderColor + '">',
                '  <span class="recommendation-text">' + icon + ' ' + r.text + '</span>',
                '</div>'
            ].join(''));
        });
        html.push('</div>');
    }

    html.push('  </div>');
    html.push('</div>');
    container.innerHTML = html.join('');
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

    var html = '<div class="surface-results-wrapper">';
    html += '<h2>📊 克里金曲面数值分析结果</h2>';
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

        html += '<div class="surface-grid">';
        if (layer.top_url) {
            html += '<div class="surface-card">';
            html += '<img src="' + layer.top_url + '?t=' + Date.now() + '" alt="' + layer.layer_name + ' 顶面" onclick="openFullscreen(\'' + layer.top_url + '\')" style="cursor:pointer;width:100%;max-height:420px;object-fit:contain;background:#f8f9fc;display:block;">';
            html += '<div class="surface-card-title">顶面分析</div>';
            html += '</div>';
        }
        if (layer.bot_url) {
            html += '<div class="surface-card">';
            html += '<img src="' + layer.bot_url + '?t=' + Date.now() + '" alt="' + layer.layer_name + ' 底面" onclick="openFullscreen(\'' + layer.bot_url + '\')" style="cursor:pointer;width:100%;max-height:420px;object-fit:contain;background:#f8f9fc;display:block;">';
            html += '<div class="surface-card-title">底面分析</div>';
            html += '</div>';
        }
        html += '</div></div>';
    }

    html += '</div>'; // surface-results-wrapper
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
    var compositeStandards = data.composite_standards || [];

    if (!best || !allResults || allResults.length === 0) {
        resultsSection.innerHTML = '<div class="rbf-results-wrapper"><p style="text-align:center;padding:40px;color:#666;">无有效的参数组合结果</p></div>';
        return;
    }

    // 用综合评分判断评级（优先），回退到 RMSE 标准
    var currentStd = standards[standards.length - 1];
    if (best.composite_score !== undefined && compositeStandards.length > 0) {
        for (var si = 0; si < compositeStandards.length; si++) {
            if (best.composite_score >= compositeStandards[si].min) {
                currentStd = compositeStandards[si];
                break;
            }
        }
    } else {
        for (var si = 0; si < standards.length; si++) {
            if (best.rmse < standards[si].max) {
                currentStd = standards[si];
                break;
            }
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
    html += '           </span>';
    html += '       </div>';
    html += '       <div class="best-param-row"><span class="label">MAE：</span><span class="value">' + best.mae.toFixed(2) + ' m</span></div>';
    html += '       <div class="best-param-row"><span class="label">最大误差：</span><span class="value">' + best.max_error.toFixed(2) + ' m</span></div>';
    if (best.composite_score !== undefined) {
        var compStdRBF = currentStd;
        if (compositeStandards.length > 0) {
            for (var si2 = 0; si2 < compositeStandards.length; si2++) {
                if (best.composite_score < compositeStandards[si2].max) { compStdRBF = compositeStandards[si2]; break; }
            }
        }
        html += '   <div class="best-param-row">';
        html += '       <span class="label">综合评分：</span>';
        html += '       <span class="value" style="color:' + compStdRBF.color + ';font-size:18px;">';
        html += best.composite_score.toFixed(4);
        html += '           <span class="rmse-tag" style="background:' + compStdRBF.color + '">' + compStdRBF.label + '</span>';
        html += '       </span>';
        html += '   </div>';
    }
    html += '       <div class="best-param-row"><span class="label">建议：</span><span class="value">' + currentStd.suggestion + '</span></div>';
    html += '   </div>';
    html += '   <div class="best-param-actions">';
    html += '       <span class="best-param-applied">✅ 已应用推荐参数</span>';
    html += '       <button class="btn" id="btnCopyBestParams">📋 复制参数</button>';
    html += '   </div>';
    html += '</div>';

    // ========== 综合评分热力图（固定高度容器） ==========
    html += '<div class="analysis-block">';
    html += '   <h3>📊 综合评分热力图（核函数 × 平滑度）</h3>';
    html += '   <p style="color:#888;font-size:12px;margin:0 0 8px;">颜色越绿越优（得分越高模型越好）。综合评分 = 1 − (0.5×norm(RMSE) + 0.3×norm(MAE) + 0.2×norm(max_error))</p>';
    html += '   <div id="rmseHeatmap" class="rbf-heatmap-container"></div>';
    html += '</div>';

    // ========== 参数表格 ==========
    var sorted = allResults.slice().sort(function(a, b) {
        return (b.composite_score || b.rmse) - (a.composite_score || a.rmse);
    });
    var topN = sorted.slice(0, 30);

    html += '<div class="analysis-block">';
    html += '   <h3>📋 参数组合明细（按综合评分降序，前 30 项）</h3>';
    html += '   <table class="report-table"><thead><tr>';
    html += '       <th>排名</th><th>核函数</th><th>平滑度</th><th>epsilon</th>';
    html += '       <th>综合评分</th><th>RMSE(m)</th><th>MAE(m)</th><th>最大误差(m)</th><th>评价</th>';
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
        html += '   <td>' + (r.composite_score !== undefined ? r.composite_score.toFixed(4) : '-') + '</td>';
        html += '   <td><b>' + r.rmse.toFixed(2) + '</b></td>';
        html += '   <td>' + r.mae.toFixed(2) + '</td>';
        html += '   <td>' + r.max_error.toFixed(2) + '</td>';
        html += '   <td style="color:' + std.color + '">' + std.label + '</td>';
        html += '</tr>';
    }

    html += '</tbody></table></div>';

    // ========== 参考标准表 ==========
    html += '<div class="analysis-block">';

    // ── 综合评分标准 ──
    if (compositeStandards.length > 0) {
        html += '   <h3>📖 综合评分参考标准</h3>';
        html += '   <p style="color:#888;font-size:12px;margin:0 0 8px;">综合评分 = 1 − (0.5×norm(RMSE) + 0.3×norm(MAE) + 0.2×norm(max_error))，1=最优，越高越好</p>';
        html += '   <table class="report-table standards-table"><thead><tr>';
        html += '       <th>综合评分范围</th><th>评价</th><th>建议</th>';
        html += '   </tr></thead><tbody>';
        var isCompositeCurrent = best.composite_score !== undefined;
        for (var ci = 0; ci < compositeStandards.length; ci++) {
            var cst = compositeStandards[ci];
            var cIsCur = isCompositeCurrent
                && best.composite_score >= cst.min
                && (ci === 0 || best.composite_score < compositeStandards[ci - 1].min);
            var cRange;
            if (ci === 0) {
                cRange = '≥ ' + cst.min.toFixed(2);
            } else if (ci === compositeStandards.length - 1) {
                cRange = '< ' + compositeStandards[ci - 1].min.toFixed(2);
            } else {
                cRange = cst.min.toFixed(2) + ' ~ ' + compositeStandards[ci - 1].min.toFixed(2);
            }
            var cRowStyle = cIsCur ? 'background:' + cst.color + '22;font-weight:bold;' : '';
            html += '<tr class="' + (cIsCur ? 'current-standard' : '') + '" style="' + cRowStyle + '">';
            html += '   <td>' + cRange + '</td>';
            html += '   <td style="color:' + cst.color + '">' + cst.label + '</td>';
            html += '   <td>' + cst.suggestion + (cIsCur ? ' ← 当前结果' : '') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
        html += '   <br>';
    }

    // ── RMSE 参考标准（传统） ──
    html += '   <h3>📖 RMSE 参考标准（绝对值）</h3>';
    html += '   <table class="report-table standards-table"><thead><tr>';
    html += '       <th>RMSE 范围</th><th>评价</th><th>建议</th>';
    html += '   </tr></thead><tbody>';

    var isRMSEOnly = best.composite_score === undefined;
    for (var si2 = 0; si2 < standards.length; si2++) {
        var st = standards[si2];
        var isCurrent = isRMSEOnly && (st === currentStd);
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
    var btnCopy = document.getElementById('btnCopyBestParams');
    if (btnCopy) {
        btnCopy.addEventListener('click', function() { copyBestParams(best); });
    }
}

/**
 * 绘制综合评分热力图（Plotly）
 * 横轴为平滑度，纵轴为 (核函数, epsilon) 组合，颜色深度表示综合评分大小
 * 综合评分 = 0.5×norm(RMSE) + 0.3×norm(MAE) + 0.2×norm(max_error)，0=最优
 * 每个单元格对应输出表格中的一行，不再聚合不同 epsilon
 */
function drawRMSEHeatmap(allResults) {
    // 收集所有 (函数, epsilon) 组合和所有 smooth 值
    var rowKeySet = {};  // key -> { func, eps, label }
    var rowKeys = [];
    for (var fi = 0; fi < allResults.length; fi++) {
        var r = allResults[fi];
        var eps = (r.epsilon !== null && r.epsilon !== undefined) ? r.epsilon : null;
        var key = r.rbf_function + '|' + eps;
        if (!rowKeySet[key]) {
            var label = r.rbf_function;
            if (eps !== null) label += ' (ε=' + eps + ')';
            rowKeySet[key] = { func: r.rbf_function, eps: eps, label: label };
            rowKeys.push(key);
        }
    }

    var smoothSet = {};
    for (var si = 0; si < allResults.length; si++) {
        smoothSet[allResults[si].smooth] = true;
    }
    var smooths = Object.keys(smoothSet).map(Number).sort(function(a, b) { return a - b; });

    // 构建综合评分矩阵 — 每行一个 (函数, epsilon)，每列一个 smooth
    var scoreMatrix = [];
    var hoverTexts = [];
    var yLabels = [];
    var cellScores = [];

    for (var ri = 0; ri < rowKeys.length; ri++) {
        var rk = rowKeySet[rowKeys[ri]];
        var row = [];
        var hRow = [];
        for (var si2 = 0; si2 < smooths.length; si2++) {
            var sm = smooths[si2];
            var found = null;
            for (var ai = 0; ai < allResults.length; ai++) {
                var ar = allResults[ai];
                var arEps = (ar.epsilon !== null && ar.epsilon !== undefined) ? ar.epsilon : null;
                if (ar.rbf_function === rk.func && arEps === rk.eps && ar.smooth === sm) {
                    found = ar;
                    break;
                }
            }
            if (found && typeof found.composite_score === 'number' && isFinite(found.composite_score)) {
                var val = parseFloat(found.composite_score.toFixed(4));
                row.push(val);
                cellScores.push(found.composite_score);
                var txt = '核函数: ' + rk.func + '<br>smooth: ' + sm;
                if (found.epsilon !== null && found.epsilon !== undefined) {
                    txt += '<br>epsilon: ' + found.epsilon;
                }
                txt += '<br>综合评分: ' + found.composite_score.toFixed(4);
                txt += '<br>RMSE: ' + found.rmse.toFixed(2) + ' m';
                txt += '<br>MAE: ' + found.mae.toFixed(2) + ' m';
                txt += '<br>最大误差: ' + found.max_error.toFixed(2) + ' m';
                hRow.push(txt);
            } else if (found && typeof found.rmse === 'number' && isFinite(found.rmse)) {
                // 回退：没有 composite_score 时用 RMSE（归一化近似）
                row.push(NaN);
                var txt2 = '核函数: ' + rk.func + '<br>smooth: ' + sm;
                if (found.epsilon !== null && found.epsilon !== undefined) {
                    txt2 += '<br>epsilon: ' + found.epsilon;
                }
                txt2 += '<br>RMSE: ' + found.rmse.toFixed(2) + ' m (无综合评分)';
                hRow.push(txt2);
            } else {
                row.push(NaN);
                hRow.push('无数据');
            }
        }
        scoreMatrix.push(row);
        hoverTexts.push(hRow);
        yLabels.push(rk.label);
    }

    // 综合评分（得分越高越好，1=最优）：取实际范围并做边界处理
    cellScores.sort(function(a, b) { return a - b; });
    var cellMin = cellScores.length > 0 ? cellScores[0] : 0;
    var cellMax = cellScores.length > 0 ? cellScores[cellScores.length - 1] : 1;
    var zmin = Math.max(0, Math.floor(cellMin * 100) / 100);
    var zmax = Math.min(1.0, Math.ceil(cellMax * 1.05 * 100) / 100);

    console.log('[RBF热力图] yLabels:', yLabels, '单元格数:', cellScores.length, 'cellMax:', cellMax, 'zmax:', zmax);

    var trace = {
        z: scoreMatrix,
        x: smooths.map(String),
        y: yLabels,
        type: 'heatmap',
        colorscale: [
                [0, '#d32f2f'],
                [0.5, '#ff9800'],
                [1, '#2e7d32']
            ],
        showscale: true,
        zauto: false,
        zmin: zmin,
        zmax: zmax,
        colorbar: { title: '综合评分' },
        text: hoverTexts,
        hoverinfo: 'text',
        connectgaps: false
    };

    var layout = {
        xaxis: { title: '平滑度 (smooth)', type: 'category' },
        yaxis: { title: '核函数 (epsilon)', type: 'category' },
        margin: { l: 220, r: 40, t: 20, b: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
    };

    var heatmapDiv = document.getElementById('rmseHeatmap');
    if (heatmapDiv && typeof Plotly !== 'undefined') {
        Plotly.newPlot(heatmapDiv, [trace], layout, { responsive: true });
        console.log('[RBF热力图] Plotly 已渲染，矩阵行数:', scoreMatrix.length, '列数:', scoreMatrix[0] ? scoreMatrix[0].length : 0);
    } else {
        console.warn('[RBF热力图] 无法渲染: heatmapDiv=' + !!heatmapDiv + ' Plotly=' + (typeof Plotly));
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

    // 保存到服务器，清除旧缓存，使下次生成使用新参数
    var params = { RBF_FUNCTION: best.rbf_function, RBF_SMOOTH: best.smooth };
    fetch('/api/save_params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, params: params })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (!data.error && data.params_hash) {
            savedParamsHash = data.params_hash;
            try { localStorage.setItem('params_' + sessionId, JSON.stringify(data.params)); } catch(e) {}
        }
    }).catch(function(e) { console.warn('保存参数失败:', e); });

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
               '\n综合评分: ' + (best.composite_score !== undefined ? best.composite_score.toFixed(4) : '-') +
               '\nRMSE: ' + best.rmse.toFixed(2) + ' m' +
               '\nMAE: ' + best.mae.toFixed(2) + ' m' +
               '\n最大误差: ' + best.max_error.toFixed(2) + ' m';

    navigator.clipboard.writeText(text).then(function() {
        setStatus('==> 参数已复制到剪贴板', 'success');
    }).catch(function() {
        prompt('请手动复制：', text);
    });
}

/** 隐藏结果区的 tabs（仅展示钻孔计算器等内容时） */
// ==================== 克里金参数分析结果渲染 ====================
function renderKrigingParamResults(data) {
    var resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    var analysisKeys = Object.keys(data.analysis || {});
    if (analysisKeys.length === 0) {
        resultsSection.innerHTML = '<div class="kriging-results-wrapper"><p style="text-align:center;padding:40px;color:#666;">无分析结果</p></div>';
        return;
    }

    var key = analysisKeys[0];
    var result = data.analysis[key];

    if (!result.success) {
        resultsSection.innerHTML = '<div class="kriging-results-wrapper"><p style="color:#c62828;text-align:center;padding:40px;">分析失败: ' + (result.error || '未知错误') + '</p></div>';
        return;
    }

    var best = result.best;
    var allResults = result.all_results;
    var standards = data.standards;
    var compositeStandards = data.composite_standards || [];
    var nrStandards = data.nugget_ratio_standards || [];
    var r2Standards = data.r2_standards || [];

    if (!best || !allResults || allResults.length === 0) {
        resultsSection.innerHTML = '<div class="kriging-results-wrapper"><p style="text-align:center;padding:40px;color:#666;">无有效的参数组合结果</p></div>';
        return;
    }

    // 用综合评分判断评级（优先），回退到 RMSE 标准
    var currentStd = standards[standards.length - 1];
    if (best.composite_score !== undefined && compositeStandards.length > 0) {
        for (var si = 0; si < compositeStandards.length; si++) {
            if (best.composite_score >= compositeStandards[si].min) {
                currentStd = compositeStandards[si];
                break;
            }
        }
    } else {
        for (var si = 0; si < standards.length; si++) {
            if (best.rmse < standards[si].max) {
                currentStd = standards[si];
                break;
            }
        }
    }

    // 判断最优 nugget_ratio 和 R² 标准
    var bestNrStd = null;
    if (best.nugget_ratio != null && nrStandards.length > 0) {
        bestNrStd = nrStandards[nrStandards.length - 1];
        for (var nri = 0; nri < nrStandards.length; nri++) {
            if (best.nugget_ratio <= nrStandards[nri].max) { bestNrStd = nrStandards[nri]; break; }
        }
    }
    var bestR2Std = null;
    if (best.r_squared != null && r2Standards.length > 0) {
        bestR2Std = r2Standards[r2Standards.length - 1];
        for (var r2i = 0; r2i < r2Standards.length; r2i++) {
            if (best.r_squared >= r2Standards[r2i].min) { bestR2Std = r2Standards[r2i]; break; }
        }
    }

    var targetLabel = key === 'all' ? '整体数据集' : key;

    var html = '<div class="kriging-results-wrapper">';
    html += '<h2 style="margin-bottom:8px;">📊 克里金参数分析结果</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:16px;">分析范围: <b>' + targetLabel + '</b></p>';

    // ========== 推荐参数卡片（含新参数） ==========
    html += '<div class="best-param-card">';
    html += '   <div class="best-badge">✨ 推荐参数</div>';
    html += '   <div class="best-param-content">';
    html += '       <div class="best-param-row"><span class="label">变异函数模型：</span><span class="value">' + best.variogram_model + '</span></div>';
    html += '       <div class="best-param-row">';
    html += '           <span class="label">预期误差 (RMSE)：</span>';
    html += '           <span class="value" style="color:' + currentStd.color + ';font-size:18px;">';
    html += best.rmse.toFixed(2) + ' m';
    html += '           </span>';
    html += '       </div>';
    html += '       <div class="best-param-row"><span class="label">MAE：</span><span class="value">' + best.mae.toFixed(2) + ' m</span></div>';
    html += '       <div class="best-param-row"><span class="label">最大误差：</span><span class="value">' + best.max_error.toFixed(2) + ' m</span></div>';
    if (best.composite_score !== undefined) {
        var compStdKrig = currentStd;
        if (compositeStandards.length > 0) {
            for (var si2 = 0; si2 < compositeStandards.length; si2++) {
                if (best.composite_score < compositeStandards[si2].max) { compStdKrig = compositeStandards[si2]; break; }
            }
        }
        html += '   <div class="best-param-row">';
        html += '       <span class="label">综合评分：</span>';
        html += '       <span class="value" style="color:' + compStdKrig.color + ';font-size:18px;">';
        html += best.composite_score.toFixed(4);
        html += '           <span class="rmse-tag" style="background:' + compStdKrig.color + '">' + compStdKrig.label + '</span>';
        html += '       </span>';
        html += '   </div>';
    }
    // 新增：块金值、基台值、块基比、变程、R²
    if (best.nugget != null) {
        html += '       <div class="best-param-row"><span class="label">块金值 (Nugget)：</span><span class="value">' + best.nugget.toFixed(2) + '</span></div>';
    }
    if (best.sill != null) {
        html += '       <div class="best-param-row"><span class="label">基台值 (Sill)：</span><span class="value">' + best.sill.toFixed(2) + '</span></div>';
    }
    if (best.nugget_ratio != null) {
        var nrColor = bestNrStd ? bestNrStd.color : '#333';
        html += '       <div class="best-param-row"><span class="label">块基比 (C₀/(C₀+C))：</span>';
        html += '           <span class="value" style="color:' + nrColor + ';">' + (best.nugget_ratio * 100).toFixed(1) + '%';
        if (bestNrStd) html += ' <span class="rmse-tag" style="background:' + nrColor + '">' + bestNrStd.label + '</span>';
        html += '           </span></div>';
    }
    if (best.range != null) {
        html += '       <div class="best-param-row"><span class="label">变程 (Range)：</span><span class="value">' + best.range.toFixed(2) + '</span></div>';
    }
    if (best.r_squared != null) {
        var r2Color = bestR2Std ? bestR2Std.color : '#333';
        html += '       <div class="best-param-row"><span class="label">R²：</span>';
        html += '           <span class="value" style="color:' + r2Color + ';">' + best.r_squared.toFixed(4);
        if (bestR2Std) html += ' <span class="rmse-tag" style="background:' + r2Color + '">' + bestR2Std.label + '</span>';
        html += '           </span></div>';
    }
    html += '       <div class="best-param-row"><span class="label">建议：</span><span class="value">' + currentStd.suggestion + '</span></div>';
    html += '   </div>';
    html += '   <div class="best-param-actions">';
    html += '       <span class="best-param-applied">✅ 已应用推荐参数</span>';
    html += '       <button class="btn" id="btnCopyKrigingBestParams">📋 复制参数</button>';
    html += '   </div>';
    html += '</div>';

    // ========== 关键参数对比图区 ==========
    html += '<div class="analysis-block">';
    html += '   <h3>📊 各变异函数关键参数对比</h3>';
    html += '   <div id="krigingParamChart" class="rbf-heatmap-container" style="height:300px;"></div>';
    html += '</div>';

    // 新增：块基比柱状图 + R² 柱状图
    html += '<div class="analysis-block chart-row">';
    html += '   <div class="chart-col">';
    html += '       <h4>🔵 块基比 (Nugget/Sill Ratio)</h4>';
    html += '       <div id="krigingNuggetRatioChart" class="rbf-heatmap-container" style="height:250px;"></div>';
    html += '   </div>';
    html += '   <div class="chart-col">';
    html += '       <h4>🟢 R² 对比</h4>';
    html += '       <div id="krigingR2Chart" class="rbf-heatmap-container" style="height:250px;"></div>';
    html += '   </div>';
    html += '</div>';

    // ========== 参数表格（含新列） ==========
    var sorted = allResults.slice().sort(function(a, b) {
        return (b.composite_score || b.rmse) - (a.composite_score || a.rmse);
    });

    html += '<div class="analysis-block">';
    html += '   <h3>📋 模型明细（按综合评分降序）</h3>';
    html += '   <div class="table-scrollable">';
    html += '   <table class="report-table"><thead><tr>';
    html += '       <th>排名</th><th>变异函数模型</th><th>综合评分</th><th>RMSE(m)</th><th>MAE(m)</th><th>最大误差(m)</th><th>块金值</th><th>基台值</th><th>块基比</th><th>变程</th><th>R²</th><th>评价</th>';
    html += '   </tr></thead><tbody>';

    for (var ri = 0; ri < sorted.length; ri++) {
        var r = sorted[ri];
        var std = standards[standards.length - 1];
        for (var sj = 0; sj < standards.length; sj++) {
            if (r.rmse < standards[sj].max) { std = standards[sj]; break; }
        }
        html += '<tr>';
        html += '   <td>' + (ri + 1) + '</td>';
        html += '   <td>' + r.variogram_model + '</td>';
        html += '   <td>' + (r.composite_score !== undefined ? r.composite_score.toFixed(4) : '-') + '</td>';
        html += '   <td><b>' + r.rmse.toFixed(2) + '</b></td>';
        html += '   <td>' + (r.mae !== undefined ? r.mae.toFixed(2) : '-') + '</td>';
        html += '   <td>' + (r.max_error !== undefined ? r.max_error.toFixed(2) : '-') + '</td>';
        html += '   <td>' + (r.nugget != null ? r.nugget.toFixed(2) : '-') + '</td>';
        html += '   <td>' + (r.sill != null ? r.sill.toFixed(2) : '-') + '</td>';
        html += '   <td>' + (r.nugget_ratio != null ? (r.nugget_ratio * 100).toFixed(1) + '%' : '-') + '</td>';
        html += '   <td>' + (r.range != null ? r.range.toFixed(2) : '-') + '</td>';
        html += '   <td>' + (r.r_squared != null ? r.r_squared.toFixed(4) : '-') + '</td>';
        html += '   <td style="color:' + std.color + '">' + std.label + '</td>';
        html += '</tr>';
    }
    html += '</tbody></table></div></div>';

    // ========== 关键参数参考标准 ==========
    html += '<div class="analysis-block">';
    html += '   <h3>📖 关键参数参考标准</h3>';

    // 综合评分标准（优先展示）
    if (compositeStandards.length > 0) {
        html += '   <h4 style="margin:12px 0 6px;font-size:14px;">⭐ 综合评分评价标准</h4>';
        html += '   <p style="color:#888;font-size:12px;margin:0 0 8px;">综合评分 = 1 − (0.5×norm(RMSE) + 0.3×norm(MAE) + 0.2×norm(max_error))，1=最优，越高越好</p>';
        html += '   <table class="report-table standards-table"><thead><tr>';
        html += '       <th>综合评分范围</th><th>评价</th><th>建议</th>';
        html += '   </tr></thead><tbody>';
        for (var csi = 0; csi < compositeStandards.length; csi++) {
            var cst = compositeStandards[csi];
            var isCsCurrent = (cst === currentStd);
            var csRangeText;
            if (csi === 0) {
                csRangeText = '≥ ' + cst.min.toFixed(2);
            } else if (csi === compositeStandards.length - 1) {
                csRangeText = '< ' + compositeStandards[csi - 1].min.toFixed(2);
            } else {
                csRangeText = cst.min.toFixed(2) + ' ~ ' + compositeStandards[csi - 1].min.toFixed(2);
            }
            var csRowStyle = isCsCurrent ? 'background:' + cst.color + '22;font-weight:bold;' : '';
            html += '<tr class="' + (isCsCurrent ? 'current-standard' : '') + '" style="' + csRowStyle + '">';
            html += '   <td>' + csRangeText + '</td>';
            html += '   <td style="color:' + cst.color + '">' + cst.label + '</td>';
            html += '   <td>' + cst.suggestion + (isCsCurrent ? ' ← 当前结果' : '') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
    }

    // RMSE 标准
    html += '   <h4 style="margin:12px 0 6px;font-size:14px;">📏 RMSE 评价标准</h4>';
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
    html += '</tbody></table>';

    // 块基比标准
    if (nrStandards.length > 0) {
        html += '   <h4 style="margin:12px 0 6px;font-size:14px;">🔵 块基比 (C₀/(C₀+C)) 评价标准</h4>';
        html += '   <table class="report-table standards-table"><thead><tr>';
        html += '       <th>块基比范围</th><th>评价</th><th>说明</th>';
        html += '   </tr></thead><tbody>';
        for (var nri2 = 0; nri2 < nrStandards.length; nri2++) {
            var nrst = nrStandards[nri2];
            var isNrCurrent = (nrst === bestNrStd);
            var nrRangeText = nrst.max >= 99999
                ? '> ' + (nrStandards[nrStandards.length - 2].max * 100).toFixed(0) + '%'
                : '< ' + (nrst.max * 100).toFixed(0) + '%';
            var nrRowStyle = isNrCurrent ? 'background:' + nrst.color + '22;font-weight:bold;' : '';
            html += '<tr style="' + nrRowStyle + '">';
            html += '   <td>' + nrRangeText + '</td>';
            html += '   <td style="color:' + nrst.color + '">' + nrst.label + '</td>';
            html += '   <td>' + nrst.description + (isNrCurrent ? ' ← 当前结果' : '') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
    }

    // R² 标准
    if (r2Standards.length > 0) {
        html += '   <h4 style="margin:12px 0 6px;font-size:14px;">🟢 R² 评价标准</h4>';
        html += '   <table class="report-table standards-table"><thead><tr>';
        html += '       <th>R² 范围</th><th>评价</th><th>说明</th>';
        html += '   </tr></thead><tbody>';
        for (var r2i2 = 0; r2i2 < r2Standards.length; r2i2++) {
            var r2st = r2Standards[r2i2];
            var isR2Current = (r2st === bestR2Std);
            // R² 越高越好，使用 min 阈值
            var r2RangeText = r2st.min <= -9999
                ? '< ' + r2Standards[r2Standards.length - 2].min.toFixed(1)
                : '≥ ' + r2st.min.toFixed(1);
            var r2RowStyle = isR2Current ? 'background:' + r2st.color + '22;font-weight:bold;' : '';
            html += '<tr style="' + r2RowStyle + '">';
            html += '   <td>' + r2RangeText + '</td>';
            html += '   <td style="color:' + r2st.color + '">' + r2st.label + '</td>';
            html += '   <td>' + r2st.description + (isR2Current ? ' ← 当前结果' : '') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
    }

    html += '</div>'; // analysis-block
    html += '</div>'; // kriging-results-wrapper

    resultsSection.innerHTML = html;

    // 渲染柱状图
    setTimeout(function() {
        drawKrigingParamChart(allResults);
        drawKrigingNuggetRatioChart(allResults);
        drawKrigingR2Chart(allResults);
    }, 100);

    var btnCopy = document.getElementById('btnCopyKrigingBestParams');
    if (btnCopy) {
        btnCopy.addEventListener('click', function() { copyKrigingBestParams(best); });
    }
}

/**
 * 绘制克里金参数分析的 RMSE 柱状图
 */
function drawKrigingParamChart(allResults) {
    var sorted = allResults.slice().sort(function(a, b) { return a.rmse - b.rmse; });
    var models = sorted.map(function(r) { return r.variogram_model; });
    var rmses = sorted.map(function(r) { return r.rmse; });

    var colors = [];
    for (var ci = 0; ci < sorted.length; ci++) {
        if (ci === 0) {
            colors.push('#2E7D32'); // best = green
        } else {
            colors.push('#1565C0');
        }
    }

    var trace = {
        x: models,
        y: rmses,
        type: 'bar',
        marker: { color: colors },
        text: rmses.map(function(v) { return v.toFixed(2) + ' m'; }),
        textposition: 'outside',
        hovertemplate: '模型: %{x}<br>RMSE: %{y:.2f} m<extra></extra>'
    };

    var bestVal = rmses[0];
    var worstVal = rmses[rmses.length - 1];
    var layout = {
        xaxis: { title: '变异函数模型' },
        yaxis: { title: 'RMSE (m)' },
        margin: { l: 60, r: 30, t: 10, b: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        shapes: bestVal < worstVal ? [{
            type: 'line',
            x0: -0.5, x1: models.length - 0.5,
            y0: bestVal, y1: bestVal,
            line: { color: '#2E7D32', width: 2, dash: 'dot' }
        }] : []
    };

    var chartDiv = document.getElementById('krigingParamChart');
    if (chartDiv && typeof Plotly !== 'undefined') {
        Plotly.newPlot(chartDiv, [trace], layout, { responsive: true });
    }
}

/**
 * 绘制块基比 (Nugget/Sill Ratio) 柱状图
 */
function drawKrigingNuggetRatioChart(allResults) {
    var sorted = allResults.slice().sort(function(a, b) {
        var ar = a.nugget_ratio !== undefined ? a.nugget_ratio : 0;
        var br = b.nugget_ratio !== undefined ? b.nugget_ratio : 0;
        return ar - br;
    });
    var models = sorted.map(function(r) { return r.variogram_model; });
    var ratios = sorted.map(function(r) {
        return r.nugget_ratio !== undefined ? r.nugget_ratio * 100 : null;
    });

    var colors = [];
    for (var ci = 0; ci < sorted.length; ci++) {
        var r = sorted[ci];
        if (r.nugget_ratio === undefined || r.nugget_ratio === null) {
            colors.push('#ccc');
        } else if (r.nugget_ratio <= 0.25) {
            colors.push('#2E7D32');
        } else if (r.nugget_ratio <= 0.75) {
            colors.push('#F57C00');
        } else {
            colors.push('#C62828');
        }
    }

    var trace = {
        x: models,
        y: ratios,
        type: 'bar',
        marker: { color: colors },
        text: ratios.map(function(v) { return v !== null ? v.toFixed(1) + '%' : 'N/A'; }),
        textposition: 'outside',
        hovertemplate: '模型: %{x}<br>块基比: %{y:.1f}%<extra></extra>'
    };

    var layout = {
        xaxis: { title: '变异函数模型' },
        yaxis: { title: '块基比 (%)', range: [0, 105] },
        margin: { l: 50, r: 20, t: 10, b: 50 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        shapes: [
            { type: 'line', x0: -0.5, x1: models.length - 0.5, y0: 25, y1: 25,
              line: { color: '#F57C00', width: 1.5, dash: 'dash' } },
            { type: 'line', x0: -0.5, x1: models.length - 0.5, y0: 75, y1: 75,
              line: { color: '#C62828', width: 1.5, dash: 'dash' } }
        ],
        annotations: [
            { x: models.length - 0.3, y: 25, text: '25% 中等', showarrow: false, font: { size: 10, color: '#F57C00' }, xanchor: 'left' },
            { x: models.length - 0.3, y: 75, text: '75% 弱', showarrow: false, font: { size: 10, color: '#C62828' }, xanchor: 'left' }
        ]
    };

    var chartDiv = document.getElementById('krigingNuggetRatioChart');
    if (chartDiv && typeof Plotly !== 'undefined') {
        Plotly.newPlot(chartDiv, [trace], layout, { responsive: true });
    }
}

/**
 * 绘制 R² 柱状图
 */
function drawKrigingR2Chart(allResults) {
    var sorted = allResults.slice().sort(function(a, b) {
        var ar = a.r_squared !== undefined ? a.r_squared : -1;
        var br = b.r_squared !== undefined ? b.r_squared : -1;
        return br - ar;
    });
    var models = sorted.map(function(r) { return r.variogram_model; });
    var r2s = sorted.map(function(r) {
        return r.r_squared !== undefined ? r.r_squared : null;
    });

    var colors = [];
    for (var ci = 0; ci < sorted.length; ci++) {
        var r = sorted[ci];
        if (r.r_squared === undefined || r.r_squared === null) {
            colors.push('#ccc');
        } else if (r.r_squared >= 0.9) {
            colors.push('#2E7D32');
        } else if (r.r_squared >= 0.7) {
            colors.push('#1565C0');
        } else if (r.r_squared >= 0.5) {
            colors.push('#F57C00');
        } else {
            colors.push('#C62828');
        }
    }

    var trace = {
        x: models,
        y: r2s,
        type: 'bar',
        marker: { color: colors },
        text: r2s.map(function(v) { return v !== null ? v.toFixed(4) : 'N/A'; }),
        textposition: 'outside',
        hovertemplate: '模型: %{x}<br>R²: %{y:.4f}<extra></extra>'
    };

    var layout = {
        xaxis: { title: '变异函数模型' },
        yaxis: { title: 'R²', range: [0, 1.1] },
        margin: { l: 50, r: 20, t: 10, b: 50 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        shapes: [
            { type: 'line', x0: -0.5, x1: models.length - 0.5, y0: 0.9, y1: 0.9,
              line: { color: '#2E7D32', width: 1.5, dash: 'dash' } },
            { type: 'line', x0: -0.5, x1: models.length - 0.5, y0: 0.7, y1: 0.7,
              line: { color: '#1565C0', width: 1.5, dash: 'dash' } },
            { type: 'line', x0: -0.5, x1: models.length - 0.5, y0: 0.5, y1: 0.5,
              line: { color: '#F57C00', width: 1.5, dash: 'dash' } }
        ]
    };

    var chartDiv = document.getElementById('krigingR2Chart');
    if (chartDiv && typeof Plotly !== 'undefined') {
        Plotly.newPlot(chartDiv, [trace], layout, { responsive: true });
    }
}

/**
 * 应用推荐参数到当前会话
 */
function applyKrigingBestParams(best) {
    if (!best) return;

    if (typeof currentParams !== 'object') {
        currentParams = {};
    }
    currentParams.KRIGING_VARIOGRAM = best.variogram_model;

    var el = document.getElementById('param_KRIGING_VARIOGRAM');
    if (el) el.value = best.variogram_model;

    // 保存到服务器，清除旧缓存，使下次生成使用新参数
    var params = { KRIGING_VARIOGRAM: best.variogram_model };
    fetch('/api/save_params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, params: params })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (!data.error && data.params_hash) {
            savedParamsHash = data.params_hash;
            try { localStorage.setItem('params_' + sessionId, JSON.stringify(data.params)); } catch(e) {}
        }
    }).catch(function(e) { console.warn('保存参数失败:', e); });

    setStatus('==> 推荐参数已应用到当前会话（下次生成时生效）', 'success');

    setTimeout(function() {
        var hint = document.getElementById('paramsHint');
        if (hint) {
            hint.textContent = '已从参数分析应用克里金变异函数模型: ' + best.variogram_model;
            hint.style.color = '#2E7D32';
        }
    }, 300);
}

/**
 * 复制推荐参数到剪贴板
 */
function copyKrigingBestParams(best) {
    var text = '变异函数模型: ' + best.variogram_model +
               '\n综合评分: ' + (best.composite_score !== undefined ? best.composite_score.toFixed(4) : '-') +
               '\nRMSE: ' + best.rmse.toFixed(2) + ' m' +
               '\nMAE: ' + best.mae.toFixed(2) + ' m' +
               '\n最大误差: ' + best.max_error.toFixed(2) + ' m';

    navigator.clipboard.writeText(text).then(function() {
        setStatus('==> 参数已复制到剪贴板', 'success');
    }).catch(function() {
        prompt('请手动复制：', text);
    });
}

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

    // 图表 — 仅在有分析数据时展示
    if (data.has_rbf || data.has_kriging) {
        html += '<div class="report-block"><h3>📈 图表分析</h3><div id="reportCharts"></div></div>';
    }

    reportSection.innerHTML = html;

    var exportBtn = document.getElementById('btnExportAnalysis');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportAnalysisData);
    }

    if (data.has_rbf || data.has_kriging) {
        renderReportCharts(data);
    }
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

    // 无可用图表时显示提示信息
    if (!html) {
        html = '<p style="text-align:center;padding:30px 20px;color:#888;font-size:14px;">'
             + '暂无图表数据。对比图表需要<strong>同时存在 RBF 和克里金</strong>两种分析结果才能生成。'
             + '请先在"克里金参数分析"中执行分析。'
             + '</p>';
        chartsDiv.innerHTML = html;
        return;
    }

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
    initModelParamsButton();
    initResultTabs();
    setStatus('已加载模板数据，可查看下方预览', 'info');

    // 页面加载/刷新时清空 uploads/ 文件夹
    fetch('/api/clear_uploads', { method: 'POST' }).catch(function() {});
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
            if (isCoordColumn(h)) {
                // 坐标列保留两位小数（如 3232138.97）
                const coord = formatCoord2(val);
                if (coord !== null) val = coord;
            }
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

    // ===== 在日志历史中添加分隔线 =====
    var historyEl = document.getElementById('statusHistory');
    if (historyEl && historyEl.children.length > 0) {
        var sep = document.createElement('div');
        sep.className = 'log-separator';
        historyEl.appendChild(sep);
    }

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
}

function appendLogMessage(msg, type) {
    var historyEl = document.getElementById('statusHistory');
    if (!historyEl) historyEl = document.getElementById('statusMessage');
    var line = document.createElement('div');
    line.textContent = msg;
    line.className = 'log-line';
    if (type === 'error') line.style.color = '#f44747';
    else if (type === 'success') line.style.color = '#6a9955';
    else if (type === 'warning') line.style.color = '#dcdcaa';
    else line.style.color = '#d4d4d4';
    historyEl.appendChild(line);
    // 自动滚动到底部 — 目标 #statusHistory（内容实际追加到的容器）
    historyEl.scrollTop = historyEl.scrollHeight;
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
                    <div>开孔坐标E: ${formatCoord2(p.开孔坐标E) || '--'}</div>
                    <div>开孔坐标N: ${formatCoord2(p.开孔坐标N) || '--'}</div>
                    <div>开孔高程R: ${formatCoord2(p.开孔高程R) || '--'} m</div>
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
        const sidToClean = sessionId;
        // 先清理前端状态
        resetToInitialState();

        // 清空 uploads/ 文件夹所有内容
        try {
            await fetch('/api/clear_uploads', { method: 'POST' });
        } catch (e) {}
        // 清理当前 session 的服务端数据
        if (sidToClean) {
            try {
                await fetch('/api/cleanup_session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sidToClean })
                });
            } catch (e) {}
        }
        setStatus('==> 已清理所有数据，请上传新的数据文件', 'success');
    });
}

// ==================== 清除历史记录 ====================
const btnClearHistory = document.getElementById('btnClearHistory');
if (btnClearHistory) {
    btnClearHistory.addEventListener('click', async () => {
        if (!confirm('确定要清空所有历史输出吗？此操作不可撤销。')) return;
        try {
            const resp = await fetch('/api/clear_outputs', { method: 'POST' });
            const data = await resp.json();
            // 同步重置前端状态
            resetToInitialState();
            setStatus('==> 已清空所有历史输出（' + (data.cleaned || 0) + ' 项）', 'success');
        } catch (e) {
            setStatus('!!! 清空历史记录失败', 'error');
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
    hasRunParamAnalysis = false;
    hasClickedModeling = false;

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