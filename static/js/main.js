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
const dataPreviewSection = document.getElementById('dataPreviewSection');

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
    btns.forEach(btn => btn.disabled = !enabled);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function showResults(html) {
    resultsSection.innerHTML = html;
    resultsSection.classList.add('visible');
}

function clearResults() {
    resultsSection.innerHTML = '';
    resultsSection.classList.remove('visible');
}


function showDataPreview(data, isTemplate) {
    const previewDiv = document.getElementById('dataPreview');
    if (!previewDiv) return;
    
    const title = isTemplate ? '模板数据预览' : '上传数据预览';
    const stats = data.stats;
    
    let html = `
        <div class="data-preview-header">
            <h3>${title}</h3>
            <div class="data-stats">
                <span class="stat-item">钻孔数: ${stats.total_holes}</span>
                <span class="stat-item">测斜点数: ${stats.total_survey_points}</span>
                <span class="stat-item">岩性段数: ${stats.total_lithology_segments}</span>
            </div>
        </div>
    `;
    
    // 岩性统计
    if (stats.lithology_stats) {
        html += `<div class="lithology-stats">`;
        html += `<h4>岩性分布</h4>`;
        html += `<div class="lithology-tags">`;
        for (const [lith, count] of Object.entries(stats.lithology_stats)) {
            const color = stats.color_map ? Object.keys(stats.color_map).find(k => stats.color_map[k].includes(lith)) : null;
            const colorStyle = color ? `style="background-color:${color};color:${isLightColor(color) ? '#000' : '#fff'}"` : '';
            html += `<span class="lithology-tag" ${colorStyle}>${lith} (${count})</span>`;
        }
        html += `</div></div>`;
    }
    
    // 颜色映射
    if (stats.color_map) {
        html += `<div class="color-map">`;
        html += `<h4>颜色映射</h4>`;
        html += `<div class="color-map-items">`;
        for (const [color, name] of Object.entries(stats.color_map)) {
            html += `<div class="color-map-item">
                <span class="color-swatch" style="background-color:${color};"></span>
                <span>${color} → ${name}</span>
            </div>`;
        }
        html += `</div></div>`;
    }
    
    // 数据表格 - 三个表格
    html += `<div class="data-tables">`;
    
    // 1. 定位表
    html += `<div class="data-table-wrap">`;
    html += `<h4>定位表 (前${Math.min(data.location.length, 5)}行)</h4>`;
    html += `<table class="data-table">`;
    if (data.location && data.location.length > 0) {
        const headers = Object.keys(data.location[0]);
        html += `<thead><tr>`;
        for (const h of headers) {
            html += `<th>${h}</th>`;
        }
        html += `</tr></thead><tbody>`;
        for (let i = 0; i < Math.min(data.location.length, 5); i++) {
            html += `<tr>`;
            for (const h of headers) {
                html += `<td>${data.location[i][h] ?? ''}</td>`;
            }
            html += `</tr>`;
        }
        html += `</tbody>`;
    } else {
        html += `<tbody><tr><td colspan="5" style="text-align:center;color:#999;">暂无数据</td></tr></tbody>`;
    }
    html += `</table></div>`;
    
    // 2. 测斜表
    html += `<div class="data-table-wrap">`;
    html += `<h4>测斜表 (前${Math.min(data.survey.length, 5)}行)</h4>`;
    html += `<table class="data-table">`;
    if (data.survey && data.survey.length > 0) {
        const headers = Object.keys(data.survey[0]);
        html += `<thead><tr>`;
        for (const h of headers) {
            html += `<th>${h}</th>`;
        }
        html += `</tr></thead><tbody>`;
        for (let i = 0; i < Math.min(data.survey.length, 5); i++) {
            html += `<tr>`;
            for (const h of headers) {
                html += `<td>${data.survey[i][h] ?? ''}</td>`;
            }
            html += `</tr>`;
        }
        html += `</tbody>`;
    } else {
        html += `<tbody><tr><td colspan="4" style="text-align:center;color:#999;">暂无数据</td></tr></tbody>`;
    }
    html += `</table></div>`;
    
    // 3. 岩性表
    html += `<div class="data-table-wrap">`;
    html += `<h4>岩性表 (前${Math.min(data.lithology.length, 5)}行)</h4>`;
    html += `<table class="data-table">`;
    if (data.lithology && data.lithology.length > 0) {
        const headers = Object.keys(data.lithology[0]);
        html += `<thead><tr>`;
        for (const h of headers) {
            html += `<th>${h}</th>`;
        }
        html += `</tr></thead><tbody>`;
        for (let i = 0; i < Math.min(data.lithology.length, 5); i++) {
            html += `<tr>`;
            for (const h of headers) {
                const val = data.lithology[i][h] ?? '';
                if (h === '建模颜色' && val) {
                    html += `<td><span class="color-swatch-inline" style="background-color:${val};"></span> ${val}</td>`;
                } else {
                    html += `<td>${val}</td>`;
                }
            }
            html += `</tr>`;
        }
        html += `</tbody>`;
    } else {
        html += `<tbody><tr><td colspan="5" style="text-align:center;color:#999;">暂无数据</td></tr></tbody>`;
    }
    html += `</table></div>`;
    
    html += `</div>`; // 结束 data-tables
    
    previewDiv.innerHTML = html;
    previewDiv.style.display = 'block';
}


// ==================== 加载模板数据 ====================
async function loadTemplateData() {
    try {
        const response = await fetch('/api/template_info');
        const result = await response.json();
        if (result.success) {
            updatePreviewData(result.data, true);
            currentData = result.data;
            setStatus('==> 模板数据加载成功，可点击「数据预览」查看', 'success');
        } else {
            setStatus('!!! 加载模板数据失败: ' + (result.error || '未知错误'), 'error');
        }
    } catch (error) {
        setStatus('!!! 加载模板数据失败: ' + error.message, 'error');
    }
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
    clearResults();
    // 恢复显示模板数据
    if (currentData) {
        showDataPreview(currentData, true);
        isTemplateData = true;
    }
    setStatus('等待上传文件...', 'info');
});

async function handleFile(file) {
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
        const response = await fetch('/api/upload', { method: 'POST', body: formData });
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

        // 关键：加载文件数据并更新预览
        await loadFileData(filePath);

        setButtonsEnabled(true);
        setStatus('==> 文件上传成功: ' + data.filename, 'success');
        clearResults();
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

        // 首先检查响应是否成功
        if (!response.ok) {
            // 获取错误文本（可能是 HTML）
            const text = await response.text();
            console.error('服务器返回错误:', text);
            setStatus('!!! 服务器错误: ' + response.status, 'error');
            return;
        }

        // 尝试解析 JSON
        let result;
        try {
            result = await response.json();
        } catch (jsonError) {
            // 如果 JSON 解析失败，获取原始文本并显示
            const text = await response.text();
            console.error('JSON 解析失败，原始响应:', text);
            setStatus('!!! 响应格式错误，请检查后端日志', 'error');
            return;
        }

        console.log('loadFileData 返回:', result);

        if (result.success) {
            updatePreviewData(result.data, false);
            if (currentTab === 'map' && previewMap) {
                updateMapMarkers();
            }
            // 更新标题（如果弹窗已打开）
            if (previewModal.classList.contains('active')) {
                modalTitle.textContent = '📊 预览数据（上传数据）';
            }
        } else {
            setStatus('!!! 读取文件数据失败: ' + (result.error || '未知错误'), 'error');
            console.error('后端错误:', result.error);
        }
    } catch (error) {
        console.error('loadFileData 捕获错误:', error);
        setStatus('!!! 加载数据失败: ' + error.message, 'error');
    }
}

// ==================== 浙江天地图地图 ====================
// 主地图
let mainMap = null;
let mainMarkerGroup = [];   // 存储标记对象
let mainMapInitialized = false;

// 预览地图
let previewMap = null;
let previewMarkerGroup = [];
let previewMapInitialized = false;

const zj_key = window.ZJ_TIANDITU_KEY || '';

function initMainMap() {
    if (!zj_key) {
        alert('天地图密钥未配置，无法加载地图');
        return;
    }
    const container = document.getElementById('mainMap');

    if (!container) return;
    if (mainMap) {
        mainMap.resize();
        return;
    }
    // 创建地图
    mainMap = new T.Map('mainMap');
    // 浙江省中心点
    var center = new T.LngLat(120.2, 30.3);
    mainMap.centerAndZoom(center, 8);
    // 添加控件
    mainMap.addControl(new T.Control.Zoom());
    mainMap.addControl(new T.Control.Scale());
    mainMapInitialized = true;
    document.getElementById('mainMapContainer').style.display = 'block';
    console.log('✅ 浙江天地图初始化完成');
    
}

function showPointsOnMainMap() {
    try {
        if (!zj_key) {
            alert('天地图密钥未配置');
            return;
        }
        if (!mainMapInitialized) {
            initMainMap();
            if (!mainMap) return;
        }
        if (!mainMap) return;

        // 清除旧标记
        mainMarkerGroup.forEach(marker => mainMap.removeOverLay(marker));
        mainMarkerGroup = [];

        const points = previewData.points || [];
        if (!points.length) {
            alert('暂无钻孔数据');
            return;
        }

        const bounds = new T.LngLatBounds();

        points.forEach(p => {
            console.log(p)
            const lngLat = new T.LngLat(p.lat, p.lon);
            const marker = new T.Marker(lngLat);

            // 1. 创建信息窗口的内容 (HTML字符串)
            const contentHtml = `
                <div style="padding:4px 8px;font-size:13px;line-height:1.6;">
                    <div style="font-weight:bold;font-size:15px;color:#1a73e8;border-bottom:1px solid #eee;margin-bottom:4px;">
                        🔹 ${p.钻孔编号}
                    </div>
                    <div>开孔坐标E: ${p.lat || '--'}</div>
                    <div>开孔坐标N: ${p.lon || '--'}</div>
                    <div>开孔高程R: ${p.开孔高程R || '--'} m</div>
                    <div>钻孔长度: ${p.钻孔长度 || '--'} m</div>
                </div>
            `;
            // 2. 将HTML字符串转换为DOM元素
            const contentDiv = document.createElement('div');
            contentDiv.innerHTML = contentHtml;

            // 3. 创建信息窗口，传入DOM元素
            const infoWin = new T.InfoWindow(contentDiv, { offset: new T.Point(0, -30) });

            // 4. 绑定点击事件
            marker.addEventListener("click", function(e) {
                const point = e.lnglat;
                const content = `
                    <div style="padding:6px 12px;font-size:13px;line-height:1.7;">
                        <div style="font-weight:bold;font-size:15px;color:#1a73e8;border-bottom:1px solid #eee;margin-bottom:6px;">
                            🔹 ${p.钻孔编号}
                        </div>
                        <div>经度 (lon): ${p.lon ? p.lon.toFixed(6) : '--'}</div>
                        <div>纬度 (lat): ${p.lat ? p.lat.toFixed(6) : '--'}</div>
                        <div>开孔坐标E: ${p.开孔坐标E || '--'} m</div>
                        <div>开孔坐标N: ${p.开孔坐标N || '--'} m</div>
                        <div>开孔高程R: ${p.开孔高程R || '--'} m</div>
                        <div>钻孔长度: ${p.钻孔长度 || '--'} m</div>
                    </div>
                `;
                const infoWin = new T.InfoWindow();
                infoWin.setContent(content);
                mainMap.closeInfoWindow();
                mainMap.openInfoWindow(infoWin, point);
            });

            mainMap.addOverLay(marker);
            mainMarkerGroup.push(marker);
            bounds.extend(lngLat);
        });

        if (mainMarkerGroup.length) {
            if (mainMap.fitBounds) {
                mainMap.fitBounds(bounds, { padding: 40 });
            } else {
                const center = bounds.getCenter();
                mainMap.centerAndZoom(center, 10);
            }
        }
        setStatus(`==> 已叠加 ${mainMarkerGroup.length} 个钻孔点位`, 'success');
    } catch (e) {
        console.error('地图操作异常:', e);
        setStatus('!!! 地图操作异常，请刷新页面重试', 'error');
    }
}

// ==================== 生成钻孔示意图 ====================
btnDrillViews.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    startLogPolling(sessionId); // 启动日志轮询
    setStatus('正在生成钻孔示意图...', 'loading');
    btnDrillViews.disabled = true;

    try {
        const response = await fetch('/api/generate_drill_views', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, path: filePath })
        });
        const data = await response.json();

        stopLogPolling(); // 停止日志轮询

        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            btnDrillViews.disabled = false;
            return;
        }

        currentViews = data.views;
        currentSlideIndex = 0;
        renderCarousel(currentViews, '钻孔示意图');
        setStatus('==> 生成完成，共 ' + currentViews.length + ' 张图', 'success');
        btnDrillViews.disabled = false;

    } catch (error) {
        setStatus('!!! 生成失败: ' + error.message, 'error');
        btnDrillViews.disabled = false;
    }
});


// ==================== 生成建模示意图 ====================
btnModelViews.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    // ========== 1. 立即隐藏钻孔模型容器，清空结果区 ==========
    const drillContainer = document.getElementById('drillModelContainer');
    if (drillContainer) {
        drillContainer.style.display = 'none';  // 隐藏，不占位
    }
    const resultsSection = document.getElementById('resultsSection');
    if (resultsSection) {
        resultsSection.innerHTML = '';           // 清空旧轮播
        resultsSection.classList.remove('visible');
    }
    // 可选：显示一个“加载中”提示
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'modelLoading';
    loadingDiv.style.cssText = 'text-align:center;padding:40px;font-size:16px;color:#666;';
    loadingDiv.innerHTML = '⏳ 正在生成建模示意图，请稍候...';
    resultsSection.appendChild(loadingDiv);
    resultsSection.classList.add('visible');

    // 启动日志轮询
    startLogPolling(sessionId);
    setStatus('正在生成建模示意图...', 'loading');
    btnModelViews.disabled = true;

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
            btnModelViews.disabled = false;
            // 出错时恢复钻孔模型显示
            if (drillContainer) drillContainer.style.display = 'flex';
            return;
        }

        modelData = data;

        // ========== 2. 移除加载提示，渲染结果 ==========
        const loadingEl = document.getElementById('modelLoading');
        if (loadingEl) loadingEl.remove();

        // 重新填充结果
        resultsSection.innerHTML = '';
        resultsSection.classList.add('visible');

        // 标注图轮播
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

        // 无标注图轮播
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

        // 启用AI建模
        if (data.color_map && Object.keys(data.color_map).length > 0) {
            btnAIModeling.disabled = false;
        } else {
            btnAIModeling.disabled = true;
        }

        // ========== 3. 恢复钻孔模型显示（但放在结果下方，如果需要） ==========
        // 如果希望保留钻孔模型在底部，可取消注释；当前需求是隐藏，则不恢复
        // if (drillContainer) drillContainer.style.display = 'flex';

        setStatus('==> 多视角建模示意图生成完成', 'success');
        btnModelViews.disabled = false;

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        btnModelViews.disabled = false;
        // 出错时恢复钻孔模型
        if (drillContainer) drillContainer.style.display = 'flex';
    }
});

// ==================== AI建模 ====================
btnAIModeling.addEventListener('click', async () => {
    // 检查是否有模型数据
    if (!modelData || !modelData.color_map || Object.keys(modelData.color_map).length === 0) {
        setStatus('!!! 请先生成建模示意图', 'error');
        return;
    }

    startLogPolling(sessionId); // 启动日志轮询
    setStatus('正在进行AI建模，请稍候...（生成4张图）', 'loading');
    btnAIModeling.disabled = true;

    try {
        const response = await fetch('/api/ai_modeling', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                color_map: modelData.color_map
            })
        });
        const data = await response.json();

        stopLogPolling(); // 停止日志轮询
        
        if (data.error) {
            setStatus('!!! ' + data.error, 'error');
            btnAIModeling.disabled = false;
            return;
        }

        let aiViews = data.image_urls.map((url, idx) => ({
            url: url,
            label: `AI建模图 ${idx+1}`
        }));
        
        renderCarousel(aiViews, 'AI 建模结果');

        setStatus('==> AI建模完成，生成 ' + data.count + ' 张图', 'success');
        btnAIModeling.disabled = false;

    } catch (error) {
        setStatus('!!! AI建模失败: ' + error.message, 'error');
        btnAIModeling.disabled = false;
    }
});

// ==================== 批量下载AI图片 ====================
function downloadAllAIImages() {
    if (!window._aiImageUrls || window._aiImageUrls.length === 0) {
        alert('没有AI图片可下载');
        return;
    }
    downloadAllAsZip(window._aiImageUrls, 'ai_model_images.zip');
}

// 全局暴露批量下载函数
window.downloadAllAIImages = downloadAllAIImages;

// ==================== 交互式3D模型 ====================
btnInteractive.addEventListener('click', async () => {
    if (!sessionId || !filePath) {
        setStatus('!!! 请先上传文件', 'error');
        return;
    }

    // 如果已经生成，滚动到模型位置
    if (interactiveModelLoaded) {
        const container = document.getElementById('interactiveModelContainer');
        if (container) {
            container.scrollIntoView({ behavior: 'smooth' });
        } else {
            // 如果容器不存在，重置状态并重新生成
            interactiveModelLoaded = false;
        }
        setStatus('==> 交互式模型已存在', 'success');
        return;
    }

    startLogPolling(sessionId);
    setStatus('正在生成交互式模型，请稍候...', 'loading');
    btnInteractive.disabled = true;

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
            btnInteractive.disabled = false;
            return;
        }

        // 确保 resultsSection 存在
        const resultsSection = document.getElementById('resultsSection');
        if (!resultsSection) {
            setStatus('!!! 结果区域未找到', 'error');
            btnInteractive.disabled = false;
            return;
        }

        // 创建或获取容器
        let container = document.getElementById('interactiveModelContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'interactiveModelContainer';
            container.style.cssText = 'margin-top:20px;border-top:2px solid #e8eaf6;padding-top:20px;';
            resultsSection.appendChild(container);
        }

        // 清空并填充内容
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
        // 滚动到容器
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });

        setStatus('==> 交互式模型生成完成', 'success');
        btnInteractive.disabled = false;

    } catch (error) {
        stopLogPolling();
        setStatus('!!! 生成失败: ' + error.message, 'error');
        btnInteractive.disabled = false;
    }
});

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

// 一次性下载带标注的地质体建模图
function downloadAllModelViews() {
    if (!modelData.labeled_views || modelData.labeled_views.length === 0) {
        alert('没有标注图可下载');
        return;
    }
    const urls = modelData.labeled_views.map(v => v.url);
    downloadAllAsZip(urls, 'model_labeled_views.zip');
}

// 一次性下载无标注的地质体建模图
function downloadAllUnlabeledViews() {
    if (!modelData.unlabeled_views || modelData.unlabeled_views.length === 0) {
        alert('没有无标注图可下载');
        return;
    }
    const urls = modelData.unlabeled_views.map(v => v.url);
    downloadAllAsZip(urls, 'model_unlabeled_views.zip');
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

// ==================== 初始化 ====================
setStatus('请上传钻孔数据文件', 'info');


// ==================== 初始化 ====================
// 页面加载时自动加载模板数据
document.addEventListener('DOMContentLoaded', function() {
    loadTemplateData();
    setStatus('已加载模板数据，可查看下方预览', 'info');
    // 绑定“显示点位”按钮
    // const btnShowPoints = document.getElementById('btnShowPoints');
    // if (btnShowPoints) {
    //     btnShowPoints.addEventListener('click', function() {
    //        if (!zj_key) {
    //             alert('天地图密钥未配置，无法加载地图');
    //             return;
    //         }
    //         if (!previewData.points || previewData.points.length === 0) {
    //             setStatus('!!! 暂无钻孔数据，请先上传文件', 'error');
    //             return;
    //         }
    //         showPointsOnMainMap(); 
    //     });
    // } else {
    //     console.warn('按钮 #btnShowPoints 未找到');
    // }

    if (document.getElementById('mainMap')) {
        initMainMap();
    }
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
let mapMarkerGroup = null;

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
        const lngLat = new T.LngLat(p.lat, p.lon);
        const marker = new T.Marker(lngLat);

        marker.addEventListener("click", function(e) {
            const point = e.lnglat || lngLat;
            const content = `
                <div style="padding:6px 12px;font-size:13px;line-height:1.7;">
                    <div style="font-weight:bold;font-size:15px;color:#1a73e8;border-bottom:1px solid #eee;margin-bottom:6px;">
                        🔹 ${p.钻孔编号}
                    </div>
                    <div>经度 (lon): ${p.lon ? p.lon.toFixed(6) : '--'}</div>
                    <div>纬度 (lat): ${p.lat ? p.lat.toFixed(6) : '--'}</div>
                    <div>开孔坐标E: ${p.开孔坐标E || '--'} m</div>
                    <div>开孔坐标N: ${p.开孔坐标N || '--'} m</div>
                    <div>开孔高程R: ${p.开孔高程R || '--'} m</div>
                    <div>钻孔长度: ${p.钻孔长度 || '--'} m</div>
                </div>
            `;
            const infoWin = new T.InfoWindow();
            infoWin.setContent(content);
            previewMap.closeInfoWindow();
            previewMap.openInfoWindow(infoWin, point);
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
// 在页面加载时加载模板数据并更新预览
async function loadTemplateData() {
    setStatus('加载模板数据...', 'loading');
    try {
        const response = await fetch('/api/template_info');
        const data = await response.json();
        if (data.success) {
            isTemplateData = true;
            currentData = data.data;
            // 更新预览数据
            updatePreviewData(data.data, true);
            // 原有的预览显示（保留兼容）
            showDataPreview(data.data, true);
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
    
    // ====== 关键修复：在 try 外部定义 formData ======
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
        // 更新界面信息
        fileInfo.style.display = 'flex';
        uploadArea.style.display = 'none';
        fileName.textContent = data.filename;
        fileSize.textContent = formatFileSize(file.size);
        // 加载数据并更新预览
        await loadFileData(filePath);
        setButtonsEnabled(true);
        setStatus('==> 文件上传成功: ' + data.filename, 'success');
        clearResults();
    } catch (error) {
        setStatus('!!! 上传失败: ' + error.message, 'error');
    }
}

async function loadFileData(path) {
    console.log('loadFileData 被调用，路径:', path);
    try {
        const response = await fetch('/api/file_info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const result = await response.json();
        console.log('loadFileData 返回结果:', result);
        if (result.success) {
            updatePreviewData(result.data, false);
            if (currentTab === 'map' && previewMap) {
                updatePreviewMapMarkers();
            }
        } else {
            console.error('后端返回错误:', result.error);
            setStatus('!!! ' + result.error, 'error');
        }
    } catch (error) {
        console.error('loadFileData 异常:', error);
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
    clearResults();
    // 恢复模板数据
    if (currentData) {
        updatePreviewData(currentData, true);
        isTemplateData = true;
        modalTitle.textContent = '📊 数据预览（模板数据）';
    }
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