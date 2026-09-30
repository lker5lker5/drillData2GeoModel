// main.js
let sessionId = null;
let filePath = null;
let currentViews = [];
let currentSlideIndex = 0;
let currentData = null;
let isTemplateData = true;
let interactiveModelLoaded = false;
let modelData = {};


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

// ==================== 工具函数 ====================
function setStatus(message, type = 'info') {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message';
    if (type) statusMessage.classList.add(type);
}

function setButtonsEnabled(enabled) {
    const btns = [btnDrillViews, btnModelViews, btnAIModeling, btnInteractive];
    const btnMultiviewAI = document.getElementById('btnMultiviewAI');
    if (btnMultiviewAI) btns.push(btnMultiviewAI);
    btns.forEach(btn => {
        if (btn) btn.disabled = !enabled;
    });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
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
    fileInput.value = '';
    fileInfo.style.display = 'none';
    uploadArea.style.display = 'block';
    sessionId = null;
    filePath = null;
    setButtonsEnabled(false);
    if (currentData) {
        updatePreviewData(currentData, true);
        isTemplateData = true;
    }
    setStatus('等待上传文件...', 'info');
});

// ==================== 按钮"计算中"状态管理 ====================
/**
 * 启动按钮的"计算中"状态
 * @param {HTMLElement} btn - 目标按钮
 * @param {string} label - 提示文字，如"钻孔绘制中"
 * @returns {Object} - 返回一个控制器，用于更新计时器文字
 */
function startButtonTimer(btn, label) {
    if (!btn) return null;

    // 1. 按钮变灰
    btn.classList.add('loading');
    btn.disabled = true;

    // 2. 查找或创建提示行（在按钮后面）
    let timerEl = btn.nextElementSibling;
    if (!timerEl || !timerEl.classList.contains('btn-timer')) {
        timerEl = document.createElement('div');
        timerEl.className = 'btn-timer';
        btn.parentNode.insertBefore(timerEl, btn.nextSibling);
    }
    timerEl.classList.remove('hidden');

    // 3. 计时器逻辑
    const startTime = Date.now();
    let timerId = null;

    function formatTime(seconds) {
        if (seconds < 60) {
            return `${seconds}s`;
        }
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}分${s}秒`;
    }

    function updateText() {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        timerEl.innerHTML = `${label}（已用时 ${formatTime(elapsed)}）`;
    }

    updateText();  // 立即显示 0s
    timerId = setInterval(updateText, 1000);

    // 4. 返回控制器
    return {
        stop: function () {
            if (timerId) {
                clearInterval(timerId);
                timerId = null;
            }
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
btnDrillViews.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
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
        renderCarousel(currentViews, '钻孔示意图');
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

        if (data.labeled_views && data.labeled_views.length > 0) {
            const labeledViews = data.labeled_views.map(v => ({
                url: v.url,
                label: '标注-' + v.label,
                user_tip: v.user_tip || ''
            }));
            const div = document.createElement('div');
            div.id = 'labeled-carousel';
            resultsSection.appendChild(div);
            renderCarouselToElement(div, labeledViews, '三维建模示意图（标注版）');
        }

        if (data.unlabeled_views && data.unlabeled_views.length > 0) {
            const unlabeledViews = data.unlabeled_views.map(v => ({
                url: v.url,
                label: '无标注-' + v.label,
                user_tip: v.user_tip || ''
            }));
            const div = document.createElement('div');
            div.id = 'unlabeled-carousel';
            resultsSection.appendChild(div);
            renderCarouselToElement(div, unlabeledViews, '三维建模示意图（无标注版）');
        }

        if (data.color_map && Object.keys(data.color_map).length > 0) {
            btnAIModeling.disabled = false;
        } else {
            btnAIModeling.disabled = true;
        }

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
    html += '<div class="ai-candidates-grid">';

    for (const c of data.candidates) {
        const isBest = (c.index === data.best_index);
        const scoreText = (c.scores && c.scores.total_score !== undefined)
            ? '综合评分: ' + (c.scores.total_score * 100).toFixed(1)
            : '';
        const ssimText = (c.scores && c.scores.ssim !== undefined)
            ? '几何相似度: ' + (c.scores.ssim * 100).toFixed(1)
            : '';

        html += `
            <div class="ai-candidate-card ${isBest ? 'best' : ''}" data-index="${c.index}">
                ${isBest ? '<div class="best-badge">✨ 推荐</div>' : ''}
                <img src="${c.url}" alt="AI 候选 ${c.index}">
                <div class="candidate-info">
                    <div>候选 ${c.index}</div>
                    <div class="score">${scoreText}</div>
                    <div class="score-sub">${ssimText}</div>
                </div>
                <button class="btn-select" data-index="${c.index}">使用这张</button>
            </div>
        `;
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
    document.querySelectorAll('.ai-candidate-card').forEach(card => {
        card.classList.remove('selected');
        if (parseInt(card.dataset.index) === index) {
            card.classList.add('selected');
        }
    });

    setStatus('==> 已选择候选 ' + index, 'success');
}

// ==================== 交互式3D模型 ====================
btnInteractive.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    // 如果已生成，滚动到位置
    if (interactiveModelLoaded) {
        const container = document.getElementById('interactiveModelContainer');
        if (container) {
            container.scrollIntoView({ behavior: 'smooth' });
        } else {
            interactiveModelLoaded = false;
        }
        setStatus('==> 交互式模型已存在', 'success');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在生成交互式模型，请稍候...', 'loading');

    const timer = startButtonTimer(btnInteractive, '交互式模型生成中');

    try {
        const response = await fetch('/api/interactive_model', {
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

        const resultsSection = document.getElementById('resultsSection');
        if (!resultsSection) {
            setStatus('!!! 结果区域未找到', 'error');
            if (timer) timer.stop();
            return;
        }

        let container = document.getElementById('interactiveModelContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'interactiveModelContainer';
            container.style.cssText = 'margin-top:20px;border-top:2px solid #e8eaf6;padding-top:20px;';
            resultsSection.appendChild(container);
        }

        container.innerHTML = `
            <h3>交互式3D地质体模型</h3>
            <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;">
                <iframe src="${data.html_url}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:none;"></iframe>
            </div>
            <div style="text-align:center;margin-top:8px;font-size:13px;color:#666;">
                鼠标拖拽旋转 · 滚轮缩放 · 右键平移
                <a href="${data.html_url}" target="_blank" style="margin-left:16px;color:#1565C0;">在新窗口打开</a>
            </div>
        `;

        interactiveModelLoaded = true;
        resultsSection.classList.add('visible');
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });

        setStatus('==> 交互式模型生成完成', 'success');
        if (timer) timer.stop();

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        if (timer) timer.stop();
    }
});

// ==================== 多视角 AI 生成 ====================
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
            setStatus('==> 纹理升级完成（成功 ' + data.success_count + '/' + data.total_count + '）', 'success');
            if (timer) timer.stop();

        } catch (error) {
            stopLogPolling();
            setStatus('!!! 生成失败: ' + error.message, 'error');
            if (timer) timer.stop();
        }
    });
}

function renderMultiviewResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.innerHTML = '';
    resultsSection.classList.add('visible');

    let html = '<h2>多视角纹理升级结果（用于混元 3D）</h2>';
    html += '<p style="color:#666;font-size:13px;margin-bottom:12px;">成功生成 ' + data.success_count + '/' + data.total_count + ' 张，几何形态与 Python 模型完全一致，可直接下载用于混元 3D 建模。</p>';

    html += '<div class="multiview-grid">';
    for (const img of data.images) {
        html += `
            <div class="multiview-card">
                <div class="view-label">${img.view_label}</div>
                <div style="position:relative;">
                    <img src="${img.url}" alt="${img.view_label}">
                    <button class="btn-zoom" onclick="openFullscreen('${img.url}')" title="放大查看">🔍</button>
                </div>
                <div class="card-actions">
                    <a href="${img.url}" download class="btn-download">下载</a>
                </div>
            </div>
        `;
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

    let html = '';
    for (const [key, meta] of Object.entries(currentParamsMeta)) {
        const value = currentParams[key] !== undefined ? currentParams[key] : meta.default;
        html += renderParamItem(key, meta, value);
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

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    loadTemplateData();
    initParamsPanel();
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
        await loadFileData(filePath);
        setButtonsEnabled(true);
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
    fileInput.value = '';
    fileInfo.style.display = 'none';
    uploadArea.style.display = 'block';
    sessionId = null;
    filePath = null;
    setButtonsEnabled(false);
    // clearResults();
    // 恢复模板数据
    if (currentData) {
        updatePreviewData(currentData, true);
        isTemplateData = true;
        modalTitle.textContent = '📊 数据预览（模板数据）';
    }

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

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeFullscreen();
});