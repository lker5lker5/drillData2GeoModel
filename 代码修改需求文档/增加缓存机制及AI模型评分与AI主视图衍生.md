# 需求实施文档：缓存 + AI图自动评分 + 多视角AI生成

> **文档版本**: v1.0  
> **创建日期**: 2026-09-29  
> **用途**: 供 Claude CLI 阅读，指导代码实施  
> **前置条件**: 已有可运行的钻孔三维建模工程（含 app.py、processors.py、config.py、main.js、style.css、index.html）  
> **实施方式**: 分 3 个阶段，每阶段独立可验证

---

## 零、项目现状说明

### 现有文件结构
```
project_root/
├── app.py                    # Flask 主应用，路由定义
├── config.py                 # 全局配置
├── processors.py             # 核心处理函数（建模、绘图、AI调用）
├── index.html                # 主页面（根目录）
├── static/
│   ├── css/style.css         # 全局样式
│   ├── js/main.js            # 前端交互逻辑
│   └── drillAngleExplain.HTML
├── uploads/{session_id}/     # 用户上传文件
└── outputs/{session_id}/     # 生成结果
```

### 现有主要函数
- `processors.compute_trajectory` — 计算钻孔轨迹
- `processors.build_geological_bodies_with_volume_v2` — 构建地质体
- `processors.draw_single_model_view` — 绘制单视角图
- `processors.generate_interactive_model` — 交互式3D模型
- `processors.call_qwen_api_for_modeling` — 调用 Qwen API
- `processors.get_color_map_from_dataframe` — 颜色映射

### 现有主要路由
- `/api/upload` — 上传文件
- `/api/template_info` — 模板数据
- `/api/file_info` — 上传文件信息
- `/api/generate_drill_views` — 钻孔示意图
- `/api/generate_model` — 建模示意图
- `/api/ai_modeling` — AI 建模
- `/api/interactive_model` — 交互式模型
- `/api/download_zip` — ZIP 下载
- `/api/logs/<session_id>` — 日志轮询

### 现有辅助函数
- `app.log_and_print(session_id, msg, msg_type)` — 打印+记录日志
- `app.clean_dataframe(df)` — 清理空列

---

## 一、阶段 1：建模图缓存

### 1.1 目标

同一个 `session_id` 内，用户点击"建模示意图"或"AI 建模"时：
- 如果已有缓存结果，直接返回，不重新计算
- 缓存失效条件：换文件 / 删文件 / 超时 24 小时
- 缓存范围：建模示意图（model）+ AI 建模图（ai_model）

### 1.2 修改 `config.py`

在文件末尾追加：

```python
# ==================== 缓存配置 ====================
# 缓存有效期（小时）
CACHE_TTL_HOURS = 24

# 后台清理线程的扫描间隔（秒）
CACHE_CLEANUP_INTERVAL = 3600

# 缓存存储目录名（位于 outputs/{session_id}/ 下）
CACHE_DIR_NAME = '_cache'

# 是否启用缓存
CACHE_ENABLED = True
```

### 1.3 新建文件 `cache_manager.py`

```python
"""
缓存管理器：管理建模图和 AI 图的缓存。
"""
import os
import json
import hashlib
from datetime import datetime, timedelta

from config import OUTPUT_FOLDER, CACHE_TTL_HOURS, CACHE_DIR_NAME


def compute_file_hash(file_path):
    """计算文件的 MD5 哈希"""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cache_dir(session_id):
    """获取会话的缓存目录"""
    cache_dir = os.path.join(OUTPUT_FOLDER, session_id, CACHE_DIR_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_cache_meta_path(session_id):
    """获取缓存的元信息文件路径"""
    return os.path.join(get_cache_dir(session_id), 'cache_meta.json')


def load_cache_meta(session_id):
    """加载缓存元信息"""
    meta_path = get_cache_meta_path(session_id)
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache_meta(session_id, meta):
    """保存缓存元信息"""
    meta_path = get_cache_meta_path(session_id)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def get_cached_result(session_id, task_type, input_hash):
    """
    查询缓存。
    
    参数:
        session_id: 会话 ID
        task_type: 'model' 或 'ai_model'
        input_hash: 输入文件的哈希值
    
    返回:
        命中: {'result': {...}, 'created_at': '...'} 
        未命中: None
    """
    meta = load_cache_meta(session_id)
    entry = meta.get(task_type)
    if not entry:
        return None
    
    if entry.get('input_hash') != input_hash:
        return None
    
    created_at = datetime.fromisoformat(entry['created_at'])
    if datetime.now() - created_at > timedelta(hours=CACHE_TTL_HOURS):
        return None
    
    result_dir = entry.get('result_dir')
    if not result_dir or not os.path.exists(result_dir):
        return None
    
    return {
        'result': entry.get('result', {}),
        'created_at': entry['created_at']
    }


def save_cached_result(session_id, task_type, input_hash, result, result_dir):
    """
    保存缓存。
    
    参数:
        session_id: 会话 ID
        task_type: 'model' 或 'ai_model'
        input_hash: 输入文件的哈希值
        result: 结果字典
        result_dir: 结果文件所在目录
    """
    meta = load_cache_meta(session_id)
    meta[task_type] = {
        'input_hash': input_hash,
        'created_at': datetime.now().isoformat(),
        'result': result,
        'result_dir': result_dir
    }
    save_cache_meta(session_id, meta)


def clear_cache(session_id, task_type=None):
    """
    清除缓存。
    
    参数:
        session_id: 会话 ID
        task_type: 指定清除的类型，None 表示清除所有
    """
    meta = load_cache_meta(session_id)
    if task_type:
        meta.pop(task_type, None)
    else:
        meta = {}
    save_cache_meta(session_id, meta)


def cleanup_expired_cache():
    """后台线程调用：清理超过 TTL 的缓存"""
    if not os.path.exists(OUTPUT_FOLDER):
        return
    
    for session_id in os.listdir(OUTPUT_FOLDER):
        session_dir = os.path.join(OUTPUT_FOLDER, session_id)
        if not os.path.isdir(session_dir):
            continue
        
        meta = load_cache_meta(session_id)
        changed = False
        
        for task_type in list(meta.keys()):
            entry = meta[task_type]
            try:
                created_at = datetime.fromisoformat(entry['created_at'])
                if datetime.now() - created_at > timedelta(hours=CACHE_TTL_HOURS):
                    print(f"==> 清理过期缓存: {session_id}/{task_type}")
                    del meta[task_type]
                    changed = True
            except Exception:
                del meta[task_type]
                changed = True
        
        if changed:
            save_cache_meta(session_id, meta)
```

### 1.4 修改 `app.py` 的 `generate_model_api`

**在函数最开始**（读取数据之前）插入缓存查询：

```python
    try:
        # ========== 缓存查询 ==========
        from cache_manager import compute_file_hash, get_cached_result, save_cached_result
        from config import CACHE_ENABLED
        
        input_hash = None
        if CACHE_ENABLED:
            input_hash = compute_file_hash(file_path)
            cached = get_cached_result(session_id, 'model', input_hash)
            if cached:
                log_and_print(session_id, "==> 命中缓存，直接返回建模结果")
                return jsonify({
                    'success': True,
                    'from_cache': True,
                    **cached['result']
                })
        # =============================
        
        # ... 原有的读取数据、构建地质体、生成图片的逻辑 ...
```

**在函数返回前**（构造 jsonify 之前）插入缓存保存：

```python
        # ========== 保存缓存 ==========
        result_data = {
            'labeled_views': results['labeled'],
            'unlabeled_views': results['unlabeled'],
            'color_map': color_map
        }
        
        if CACHE_ENABLED and input_hash:
            save_cached_result(session_id, 'model', input_hash, result_data, output_dir)
            log_and_print(session_id, "==> 已保存建模结果到缓存")
        # =============================
        
        return jsonify({
            'success': True,
            'from_cache': False,
            **result_data
        })
```

### 1.5 修改 `app.py` 的 `ai_modeling_api`

**同样在开头插入缓存查询**：

```python
    try:
        # ========== 缓存查询 ==========
        from cache_manager import compute_file_hash, get_cached_result, save_cached_result
        from config import CACHE_ENABLED
        
        # 用文件路径作为哈希（AI 建模的输入是文件+color_map）
        input_hash = None
        if CACHE_ENABLED and file_path:
            input_hash = compute_file_hash(file_path)
            cached = get_cached_result(session_id, 'ai_model', input_hash)
            if cached:
                log_and_print(session_id, "==> 命中缓存，直接返回 AI 建模结果")
                return jsonify({
                    'success': True,
                    'from_cache': True,
                    **cached['result']
                })
        # =============================
        
        # ... 原有 AI 生成逻辑 ...
```

**在返回前保存缓存**：

```python
        result_data = {
            'image_urls': [p['url'] for p in saved_paths],
            'reference_images': [os.path.basename(p) for p in image_paths],
            'count': len(saved_paths)
        }
        
        if CACHE_ENABLED and input_hash:
            save_cached_result(session_id, 'ai_model', input_hash, result_data, OUTPUT_FOLDER)
        
        return jsonify({
            'success': True,
            'from_cache': False,
            **result_data
        })
```

> **注意**：AI 建模的 `file_path` 变量需要从 request 中获取。如果当前的 `ai_modeling_api` 没有 file_path，请同时修改前端 main.js 传入该参数，以及路由接收该参数。

### 1.6 修改 `app.py` 的 `/api/upload` 路由

在保存文件之后，清除该 session 的所有缓存：

```python
    # 保存文件
    file_path = os.path.join(session_dir, file.filename)
    file.save(file_path)
    
    # ========== 清除该 session 的缓存 ==========
    from cache_manager import clear_cache
    clear_cache(session_id)
    # =========================================
    
    return jsonify({...})
```

### 1.7 修改 `app.py` 的 `if __name__ == '__main__':`

添加后台清理线程：

```python
def cache_cleanup_daemon():
    """后台线程：定期清理过期缓存"""
    import time
    from cache_manager import cleanup_expired_cache
    from config import CACHE_CLEANUP_INTERVAL
    while True:
        try:
            cleanup_expired_cache()
        except Exception as e:
            print(f"!!! 缓存清理异常: {e}")
        time.sleep(CACHE_CLEANUP_INTERVAL)


if __name__ == '__main__':
    # ... 原有输出 ...
    
    # 启动缓存清理线程
    threading.Thread(target=cache_cleanup_daemon, daemon=True).start()
    print('==> 缓存清理线程已启动')
    
    # ... 原有的 open_browser 线程和 app.run() ...
```

### 1.8 修改 `main.js`

在 `btnModelViews` 和 `btnAIModeling` 的响应处理中，判断 `from_cache`：

```javascript
if (data.from_cache) {
    setStatus('==> 使用缓存结果（来自上次计算）', 'success');
} else {
    setStatus('==> 生成完成', 'success');
}
```

### 1.9 验收标准

- [ ] 上传文件 → 点击"建模示意图" → 生成
- [ ] 点击"钻孔示意图"切换 → 再点"建模示意图"
- [ ] **第二次瞬间返回，状态栏显示"使用缓存结果"**
- [ ] 上传新文件 → 缓存清除 → 重新生成

---

## 二、阶段 2：AI 图自动评分

### 2.1 目标

调用 AI 生成 2 张候选图后，自动判定哪张更优；两张都保留，前端展示时高亮推荐。

### 2.2 修改 `config.py`

追加：

```python
# ==================== AI 图评分配置 ====================
# 评分权重
SCORE_WEIGHT_SSIM = 0.6      # 结构相似度权重
SCORE_WEIGHT_COLOR = 0.4     # 色调相似度权重

# 分数差距阈值（低于此值视为"接近"，两张都保留并提示）
SCORE_DIFF_THRESHOLD = 0.05

# 推荐标记阈值（高于此值才标记为"推荐"）
SCORE_RECOMMEND_THRESHOLD = 0.7
```

### 2.3 新建文件 `scoring.py`

```python
"""
AI 生成图的自动评分模块。
使用 SSIM（结构相似度）+ 颜色直方图余弦相似度 综合评分。
"""
import numpy as np
from PIL import Image

from config import SCORE_WEIGHT_SSIM, SCORE_WEIGHT_COLOR, SCORE_DIFF_THRESHOLD


def load_image_as_array(image_path, target_size=(512, 512)):
    """加载图片为数组"""
    img = Image.open(image_path).convert('RGB')
    img = img.resize(target_size)
    return np.array(img)


def compute_ssim(img1, img2):
    """
    计算两张图片的 SSIM（结构相似度）。
    """
    try:
        from skimage.metrics import structural_similarity as ssim
    except ImportError:
        print("!!! 未安装 scikit-image，无法计算 SSIM")
        return 0.5
    
    if len(img1.shape) == 3:
        img1_gray = np.mean(img1, axis=2)
    else:
        img1_gray = img1
    if len(img2.shape) == 3:
        img2_gray = np.mean(img2, axis=2)
    else:
        img2_gray = img2
    
    try:
        score, _ = ssim(img1_gray, img2_gray, full=True, data_range=255)
    except Exception as e:
        print(f"!!! SSIM 计算失败: {e}")
        return 0.5
    
    return max(0.0, min(1.0, score))


def compute_color_similarity(img1, img2):
    """
    计算两张图片的色调相似度（颜色直方图余弦相似度）。
    """
    def color_hist(img):
        hist = []
        for c in range(3):
            h, _ = np.histogram(img[:, :, c], bins=32, range=(0, 256), density=True)
            hist.extend(h)
        hist = np.array(hist)
        norm = np.linalg.norm(hist)
        return hist / norm if norm > 0 else hist
    
    h1 = color_hist(img1)
    h2 = color_hist(img2)
    similarity = float(np.dot(h1, h2))
    return max(0.0, min(1.0, similarity))


def evaluate_ai_image(ai_image_path, ref_image_path):
    """
    评估单张 AI 图。
    
    返回:
        {'ssim': float, 'color_similarity': float, 'total_score': float}
    """
    try:
        ai = load_image_as_array(ai_image_path)
        ref = load_image_as_array(ref_image_path)
    except Exception as e:
        print(f"!!! 图片加载失败: {e}")
        return {'ssim': 0.0, 'color_similarity': 0.0, 'total_score': 0.0}
    
    ssim_score = compute_ssim(ai, ref)
    color_score = compute_color_similarity(ai, ref)
    total = SCORE_WEIGHT_SSIM * ssim_score + SCORE_WEIGHT_COLOR * color_score
    
    return {
        'ssim': round(ssim_score, 4),
        'color_similarity': round(color_score, 4),
        'total_score': round(total, 4)
    }


def rank_ai_candidates(candidates, ref_image_path):
    """
    对多张 AI 候选图进行排序。
    
    参数:
        candidates: [{'path': ..., 'index': 1, 'url': ...}, ...]
        ref_image_path: 参考图路径（Python 无标注图）
    
    返回:
        {
            'ranked': [...],
            'best_index': int,
            'is_close': bool
        }
    """
    scored = []
    for c in candidates:
        scores = evaluate_ai_image(c['path'], ref_image_path)
        scored.append({
            'path': c['path'],
            'url': c.get('url', ''),
            'index': c['index'],
            'scores': scores
        })
    
    scored.sort(key=lambda x: x['scores']['total_score'], reverse=True)
    
    is_close = False
    if len(scored) >= 2:
        diff = scored[0]['scores']['total_score'] - scored[1]['scores']['total_score']
        is_close = diff < SCORE_DIFF_THRESHOLD
    
    return {
        'ranked': scored,
        'best_index': scored[0]['index'] if scored else None,
        'is_close': is_close
    }
```

### 2.4 安装依赖

在终端执行：
```bash
pip install scikit-image
```

### 2.5 修改 `app.py` 的 `ai_modeling_api`

在 AI 生成、下载图片完成后，调用评分函数。**替换原有的返回逻辑**为：

```python
        # 下载所有图片到本地（原有逻辑保留）
        saved_paths = []
        for idx, img_url in enumerate(image_urls, 1):
            local_filename = f'ai_model_result_{datetime.now().strftime("%y%m%d%H%M%S")}_{idx}.png'
            local_path = os.path.join(OUTPUT_FOLDER, local_filename)
            try:
                import requests
                resp = requests.get(img_url, timeout=30)
                if resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                    saved_paths.append({
                        'local_path': local_path,
                        'path': local_path,
                        'url': f'/outputs/{local_filename}',
                        'index': idx
                    })
                    log_and_print(session_id, f"==> AI模型图 {idx} 已保存")
            except Exception as e:
                log_and_print(session_id, f"!!! 下载AI模型图 {idx} 失败: {e}")
        
        if not saved_paths:
            return jsonify({'error': '所有AI模型图下载失败'}), 500
        
        # ========== 自动评分 ==========
        from scoring import rank_ai_candidates
        
        # 找参考图：Python 的图1 无标注图
        ref_image_path = None
        for f in sorted(os.listdir(OUTPUT_FOLDER)):
            if 'unlabeled_01_main_view' in f and f.endswith('.png'):
                ref_image_path = os.path.join(OUTPUT_FOLDER, f)
                break
        
        if ref_image_path and len(saved_paths) >= 2:
            ranking = rank_ai_candidates(saved_paths, ref_image_path)
            log_and_print(session_id, f"==> AI 图评分完成，最优候选: 第{ranking['best_index']}张")
            
            result_data = {
                'candidates': ranking['ranked'],
                'best_index': ranking['best_index'],
                'is_close': ranking['is_close'],
                'reference_images': [os.path.basename(p) for p in image_paths],
                'count': len(saved_paths)
            }
        else:
            # 无法评分，返回原始列表
            result_data = {
                'candidates': [
                    {'path': p['path'], 'url': p['url'], 'index': p['index'], 'scores': {}}
                    for p in saved_paths
                ],
                'best_index': 1,
                'is_close': False,
                'reference_images': [os.path.basename(p) for p in image_paths],
                'count': len(saved_paths)
            }
        # =============================
        
        # 保存缓存（阶段 1 的逻辑，保留）
        if CACHE_ENABLED and input_hash:
            save_cached_result(session_id, 'ai_model', input_hash, result_data, OUTPUT_FOLDER)
        
        return jsonify({
            'success': True,
            'from_cache': False,
            **result_data
        })
```

### 2.6 修改 `main.js` 的 `btnAIModeling` 响应

**替换原有的 renderCarousel 逻辑**，改为调用新的候选图渲染函数：

```javascript
        // 阶段 2：改为渲染候选图
        renderAICandidates(data);
        
        if (data.is_close) {
            setStatus(`==> AI建模完成，两张候选评分接近，请人工对比选择`, 'success');
        } else {
            setStatus(`==> AI建模完成，推荐候选 ${data.best_index}`, 'success');
        }
        if (timer) timer.stop();
```

**在 main.js 中新增** `renderAICandidates` 和 `selectAICandidate` 函数：

```javascript
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
            ? `综合评分: ${(c.scores.total_score * 100).toFixed(1)}`
            : '';
        const ssimText = (c.scores && c.scores.ssim !== undefined)
            ? `几何相似度: ${(c.scores.ssim * 100).toFixed(1)}`
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
    
    setStatus(`==> 已选择候选 ${index}`, 'success');
}
```

### 2.7 修改 `style.css`

追加：

```css
/* ==================== AI 候选图展示 ==================== */
.ai-candidates-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-top: 16px;
}

.ai-candidate-card {
    background: #fafafa;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px;
    position: relative;
    transition: border-color 0.3s, box-shadow 0.3s;
}

.ai-candidate-card.best {
    border-color: #2E7D32;
    background: #f1f8e9;
}

.ai-candidate-card.selected {
    border-color: #1565C0;
    box-shadow: 0 0 0 3px rgba(21, 101, 192, 0.2);
}

.best-badge {
    position: absolute;
    top: 12px;
    right: 12px;
    background: #2E7D32;
    color: white;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    z-index: 10;
}

.ai-candidate-card img {
    width: 100%;
    border-radius: 6px;
    display: block;
}

.candidate-info {
    text-align: center;
    margin-top: 10px;
    font-size: 13px;
    color: #666;
}

.candidate-info .score {
    font-weight: bold;
    color: #1a237e;
}

.candidate-info .score-sub {
    font-size: 11px;
    color: #888;
}

.btn-select {
    width: 100%;
    margin-top: 8px;
    padding: 8px;
    background: #1565C0;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
}

.btn-select:hover {
    background: #0D47A1;
}

.close-hint {
    text-align: center;
    color: #f57f17;
    font-size: 13px;
    margin-top: 12px;
}
```

### 2.8 验收标准

- [ ] 点击 AI 建模 → 显示 2 张候选图
- [ ] 高分那张有"✨ 推荐"标记
- [ ] 每张图下方显示综合评分和几何相似度
- [ ] 可点击"使用这张"切换选择
- [ ] 如果两张接近，显示提示文字

---

## 三、阶段 3：多视角 AI 生成

### 3.1 目标

基于最优 AI 图（主锚），生成图1、图3、图5 的多视角 AI 图，用于混元 3D 建模。
- 输出两套：纯净版（给混元 3D）+ 带标注版（给报告）
- 用户可选生成 1~4 张
- 如果全部失败，终止流程，提示用户重试

### 3.2 修改 `config.py`

追加：

```python
# ==================== 多视角 AI 生成配置 ====================
# 可选的生成数量
MULTIVIEW_COUNT_OPTIONS = [1, 2, 3, 4]
MULTIVIEW_DEFAULT_COUNT = 3

# 用于多视角生成的 Python 参考图顺序（order 值）
MULTIVIEW_VIEW_ORDERS = [1, 3, 5]   # 图1、图3、图5
```

### 3.3 在 `processors.py` 中新增函数

**函数 1：`color_map_to_text`**

```python
def color_map_to_text(color_map):
    """把 color_map 转为文本描述"""
    lines = []
    for color, names in color_map.items():
        lines.append(f'- {color}: {names}')
    return '\n'.join(lines)
```

**函数 2：`call_qwen_api_for_multiview`**

```python
def call_qwen_api_for_multiview(anchor_image, target_image, color_map, 
                                  api_key=None, api_url=None, model=None):
    """
    以最优 AI 图为主锚，生成目标视角的 AI 图。
    
    参数:
        anchor_image: 主锚图路径（最优 AI 图）
        target_image: 目标视角的 Python 无标注图路径
        color_map: 颜色映射 dict
        api_key / api_url / model: 可选覆盖
    
    返回:
        (image_urls, error)
    """
    import base64
    import requests
    from config import QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL
    
    api_key = api_key or QWEN_API_KEY
    api_url = api_url or QWEN_API_URL
    model = model or QWEN_MODEL
    
    if not api_key:
        return None, "!!! API密钥未配置"
    
    # 构建提示词
    color_text = color_map_to_text(color_map)
    prompt = f"""
请生成一张三维地质体渲染图。

【参考图说明】
- 图1：已生成的高质量 AI 纹理图（主锚图）—— 参考它的岩石纹理、光影风格、色调。
- 图2：目标视角的几何约束图 —— 参考它的几何结构、层位分布、视角。

【任务】
生成一张新图，满足：
1. 几何结构：严格遵循图2的层位分布、层间厚度、视角
2. 岩石纹理：参考图1的纹理风格，保持视觉一致
3. 颜色规范：严格遵循下方的颜色-岩性对应
4. 背景纯白，无文字标注
5. 不同岩性应呈现符合地质学常识的岩石质感（透明矿物晶莹剔透、金属矿物金属光泽、结晶岩有结晶结构等）

【颜色-岩性对应关系】
{color_text}
"""
    
    # 构建 content
    content_list = []
    for img_path in [anchor_image, target_image]:
        if not os.path.exists(img_path):
            return None, f"!!! 图片不存在: {img_path}"
        with open(img_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
            content_list.append({"image": f"data:image/png;base64,{b64}"})
    content_list.append({"text": prompt})
    
    payload = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": content_list}]
        },
        "parameters": {
            "n": 1,
            "size": "1024*1024",
            "watermark": False,
            "prompt_extend": True
        }
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=180)
        if response.status_code != 200:
            return None, f"!!! API调用失败 ({response.status_code}): {response.text}"
        
        result = response.json()
        output = result.get('output', {})
        choices = output.get('choices', [])
        if not choices:
            return None, f"!!! API返回格式异常: {result}"
        
        content = choices[0].get('message', {}).get('content', [])
        image_urls = []
        for item in content:
            if isinstance(item, dict) and 'image' in item:
                image_urls.append(item['image'])
        
        if not image_urls:
            return None, f"!!! 未找到图片: {result}"
        
        return image_urls, None
    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"
```

**函数 3：`add_annotations_to_ai_image`**

```python
def add_annotations_to_ai_image(ai_image_path, output_path, z_min, z_max):
    """
    在 AI 图上叠加深度标尺（带标注版）。
    
    参数:
        ai_image_path: AI 生成图路径
        output_path: 输出路径
        z_min, z_max: 高程范围（米）
    """
    from PIL import Image, ImageDraw, ImageFont
    
    try:
        img = Image.open(ai_image_path).convert('RGB')
    except Exception as e:
        print(f"!!! 打开 AI 图失败: {e}")
        return None
    
    w, h = img.size
    
    # 扩展画布（右侧留 120px 给标尺）
    new_img = Image.new('RGB', (w + 120, h), 'white')
    new_img.paste(img, (0, 0))
    
    draw = ImageDraw.Draw(new_img)
    ruler_x = w + 30
    ruler_top = 80
    ruler_bottom = h - 80
    ruler_width = 20
    
    # 灰度渐变条（浅→深）
    for i in range(ruler_bottom - ruler_top):
        gray = int(255 * (1 - i / (ruler_bottom - ruler_top)))
        draw.rectangle(
            [ruler_x, ruler_top + i, ruler_x + ruler_width, ruler_top + i + 1],
            fill=(gray, gray, gray)
        )
    
    # 刻度
    n_ticks = 6
    for i in range(n_ticks + 1):
        y = ruler_top + int((ruler_bottom - ruler_top) * i / n_ticks)
        z_val = z_max - (z_max - z_min) * i / n_ticks
        draw.line([ruler_x + ruler_width, y, ruler_x + ruler_width + 8, y],
                  fill='black', width=2)
        draw.text((ruler_x + ruler_width + 12, y - 8), f'{int(z_val)}m', fill='black')
    
    # 标题
    draw.text((ruler_x, ruler_top - 30), '深度标尺', fill='black')
    
    new_img.save(output_path)
    return output_path
```

### 3.4 修改 `app.py`，新增路由 `/api/multiview_ai`

```python
@app.route('/api/multiview_ai', methods=['POST'])
def multiview_ai_api():
    """
    基于最优 AI 图，生成多视角 AI 图。
    """
    data = request.json
    session_id = data.get('session_id')
    best_ai_path = data.get('best_ai_path')
    view_count = data.get('view_count', MULTIVIEW_DEFAULT_COUNT)
    color_map = data.get('color_map', {})
    
    if not session_id or not best_ai_path:
        return jsonify({'error': '缺少必要参数'}), 400
    
    if view_count < 1 or view_count > 4:
        return jsonify({'error': 'view_count 必须在 1~4 之间'}), 400
    
    if not os.path.exists(best_ai_path):
        return jsonify({'error': f'主锚图不存在: {best_ai_path}'}), 400
    
    try:
        from config import MULTIVIEW_VIEW_ORDERS, VIEW_CONFIGS
        from processors import call_qwen_api_for_multiview, add_annotations_to_ai_image
        
        # 选取要生成的视角
        target_orders = MULTIVIEW_VIEW_ORDERS[:view_count]
        
        images = []
        success_count = 0
        
        for order in target_orders:
            view = next((v for v in VIEW_CONFIGS if v.get('order') == order), None)
            if not view:
                continue
            
            # 查找对应的 Python 无标注图（带序号前缀）
            py_image_path = None
            pattern = f'unlabeled_{order:02d}_{view["name"]}'
            for f in sorted(os.listdir(OUTPUT_FOLDER)):
                if pattern in f and f.endswith('.png') and 'ai_' not in f and 'multiview' not in f:
                    py_image_path = os.path.join(OUTPUT_FOLDER, f)
                    break
            
            if not py_image_path:
                log_and_print(session_id, f"!!! 未找到 图{order} 的 Python 图")
                continue
            
            # 调用 API 生成
            log_and_print(session_id, f"==> 正在生成 图{order} ({view['label']})")
            try:
                ai_urls, error = call_qwen_api_for_multiview(
                    anchor_image=best_ai_path,
                    target_image=py_image_path,
                    color_map=color_map
                )
                
                if error or not ai_urls:
                    log_and_print(session_id, f"!!! 图{order} 生成失败: {error}")
                    images.append({
                        'view_name': view['name'],
                        'view_label': view['label'],
                        'order': order,
                        'url': f'/outputs/{os.path.basename(py_image_path)}',
                        'has_ai': False
                    })
                    continue
                
                # 下载 AI 图
                ai_url = ai_urls[0]
                local_filename = f'multiview_ai_{order:02d}_{view["name"]}.png'
                local_path = os.path.join(OUTPUT_FOLDER, local_filename)
                
                import requests
                resp = requests.get(ai_url, timeout=60)
                if resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                    
                    images.append({
                        'view_name': view['name'],
                        'view_label': view['label'],
                        'order': order,
                        'url': f'/outputs/{local_filename}',
                        'path': local_path,
                        'has_ai': True
                    })
                    success_count += 1
                    log_and_print(session_id, f"==> 图{order} 生成成功")
                else:
                    log_and_print(session_id, f"!!! 图{order} 下载失败")
                    images.append({
                        'view_name': view['name'],
                        'view_label': view['label'],
                        'order': order,
                        'url': f'/outputs/{os.path.basename(py_image_path)}',
                        'has_ai': False
                    })
            except Exception as e:
                log_and_print(session_id, f"!!! 图{order} 异常: {e}")
                images.append({
                    'view_name': view['name'],
                    'view_label': view['label'],
                    'order': order,
                    'url': f'/outputs/{os.path.basename(py_image_path)}',
                    'has_ai': False
                })
        
        # ========== 全部失败时终止 ==========
        if success_count == 0:
            return jsonify({
                'error': '所有视角的 AI 生成均失败，请重试',
                'images': images
            }), 500
        # =====================================
        
        # ========== 生成带标注版 ==========
        # 从缓存获取 Z 轴范围，若无则用默认值
        from cache_manager import get_cached_result
        z_min, z_max = -300, 400  # 默认值
        try:
            cached = get_cached_result(session_id, 'model', None)
        except Exception:
            pass
        
        annotated_images = []
        for img in images:
            if img['has_ai']:
                annotated_filename = f'annotated_{os.path.basename(img["url"])}'
                annotated_path = os.path.join(OUTPUT_FOLDER, annotated_filename)
                result_path = add_annotations_to_ai_image(
                    img['path'], annotated_path, z_min, z_max
                )
                annotated_images.append({
                    **img,
                    'annotated_url': f'/outputs/{annotated_filename}' if result_path else img['url']
                })
            else:
                annotated_images.append({
                    **img,
                    'annotated_url': img['url']
                })
        # ==================================
        
        return jsonify({
            'success': True,
            'images': images,
            'annotated_images': annotated_images,
            'success_count': success_count,
            'total_count': len(images)
        })
    
    except Exception as e:
        log_and_print(session_id, f"!!! 多视角生成失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
```

### 3.5 修改 `index.html`，在按钮组中新增按钮

在 `action-group` 中，`btnInteractive` 之后添加：

```html
<button class="btn btn-warning" id="btnMultiviewAI" disabled>
    <span class="icon">🎨</span> 多视角 AI 生成
</button>
```

### 3.6 修改 `main.js`

**在 `setButtonsEnabled` 函数中，将新按钮加入禁用控制**：

```javascript
function setButtonsEnabled(enabled) {
    const btns = [btnDrillViews, btnModelViews, btnAIModeling, btnInteractive];
    const btnMultiviewAI = document.getElementById('btnMultiviewAI');
    if (btnMultiviewAI) btns.push(btnMultiviewAI);
    btns.forEach(btn => {
        if (btn) btn.disabled = !enabled;
    });
}
```

**新增按钮事件**：

```javascript
// ==================== 多视角 AI 生成 ====================
const btnMultiviewAI = document.getElementById('btnMultiviewAI');
if (btnMultiviewAI) {
    btnMultiviewAI.addEventListener('click', async () => {
        if (!sessionId) {
            setStatus('!!! 请先上传文件', 'error');
            return;
        }
        
        if (!modelData.ai || !modelData.ai.best_image_path) {
            setStatus('!!! 请先生成 AI 建模图并选定最优候选', 'error');
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
        setStatus('正在生成多视角 AI 图...', 'loading');
        const timer = startButtonTimer(btnMultiviewAI, '多视角 AI 生成中');
        
        try {
            const response = await fetch('/api/multiview_ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    best_ai_path: modelData.ai.best_image_path,
                    view_count: count,
                    color_map: modelData.color_map || {}
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
            setStatus(`==> 多视角生成完成（成功 ${data.success_count}/${data.total_count}）`, 'success');
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
    
    let html = '<h2>多视角 AI 图（用于混元 3D）</h2>';
    html += `<p style="color:#666;font-size:13px;margin-bottom:12px;">
        成功生成 ${data.success_count}/${data.total_count} 张，可直接下载用于混元 3D 建模。
    </p>`;
    
    // 纯净版（给混元 3D）
    html += '<h3 style="margin-top:16px;">🎨 纯净版（给混元 3D）</h3>';
    html += '<div class="multiview-grid">';
    for (const img of data.images) {
        html += `
            <div class="multiview-card ${img.has_ai ? '' : 'fallback'}">
                <div class="view-label">${img.view_label}</div>
                <img src="${img.url}" alt="${img.view_label}">
                <div class="card-actions">
                    <a href="${img.url}" download class="btn-download">下载</a>
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    // 带标注版（给报告）
    html += '<h3 style="margin-top:24px;">📊 带标注版（给报告）</h3>';
    html += '<div class="multiview-grid">';
    for (const img of data.annotated_images) {
        html += `
            <div class="multiview-card">
                <div class="view-label">${img.view_label}</div>
                <img src="${img.annotated_url}" alt="${img.view_label}">
                <div class="card-actions">
                    <a href="${img.annotated_url}" download class="btn-download">下载</a>
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    resultsSection.innerHTML = html;
}
```

### 3.7 修改 `style.css`

追加：

```css
/* ==================== 多视角 AI 图展示 ==================== */
.multiview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-top: 12px;
}

.multiview-card {
    background: #fafafa;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px;
}

.multiview-card.fallback {
    border-color: #f57f17;
    background: #fff8e1;
}

.multiview-card .view-label {
    font-size: 14px;
    font-weight: bold;
    color: #1a237e;
    margin-bottom: 8px;
}

.multiview-card img {
    width: 100%;
    border-radius: 6px;
    display: block;
}

.multiview-card .card-actions {
    text-align: center;
    margin-top: 8px;
}

.btn-download {
    display: inline-block;
    padding: 6px 16px;
    background: #1565C0;
    color: white;
    border-radius: 4px;
    text-decoration: none;
    font-size: 13px;
}

.btn-download:hover {
    background: #0D47A1;
}

/* 按钮样式补充 */
.btn-warning {
    background: #F57C00;
    color: white;
}

.btn-warning:hover:not(:disabled) {
    background: #E65100;
}
```

### 3.8 验收标准

- [ ] 点击"多视角 AI 生成" → 输入 1~4
- [ ] 生成所有视角的 AI 图
- [ ] 展示两套：纯净版 + 带标注版
- [ ] 每张图可单独下载
- [ ] 全部失败时，返回错误提示

---

## 四、执行顺序与约束

### 4.1 执行顺序

```
【阶段 1：缓存】
1. 修改 config.py（新增缓存配置）
2. 创建 cache_manager.py
3. 修改 app.py 的 generate_model_api、ai_modeling_api（缓存查询+保存）
4. 修改 app.py 的 /api/upload（清缓存）
5. 修改 app.py 的 __main__（启动后台线程）
6. 修改 main.js（处理 from_cache）
7. 测试并验证

【阶段 2：自动评分】
1. 修改 config.py（新增评分配置）
2. 创建 scoring.py
3. 执行 pip install scikit-image
4. 修改 app.py 的 ai_modeling_api（评分+排序）
5. 修改 main.js（renderAICandidates + selectAICandidate）
6. 修改 style.css（候选图样式）
7. 测试并验证

【阶段 3：多视角 AI 生成】
1. 修改 config.py（新增多视角配置）
2. 在 processors.py 新增 3 个函数
3. 修改 app.py（新增 /api/multiview_ai 路由）
4. 修改 index.html（新增按钮）
5. 修改 main.js（按钮事件 + 渲染函数）
6. 修改 style.css（多视角样式）
7. 测试并验证
```

### 4.2 约束

- 保持所有现有功能不变
- 保持函数签名不变（除非文档明确要求）
- 保持坐标约定（X=东、Y=北、Z=高程）
- 所有新增函数必须有中文注释
- 关键步骤用 `log_and_print(session_id, msg, type)` 输出日志
- 每个阶段独立实施、独立验证
- 出错时降级到 Python 原图（阶段 3 全部失败除外）

### 4.3 汇报要求

每完成一个阶段，向用户汇报：

1. 修改了哪些文件
2. 新增了哪些文件
3. 关键改动点
4. 测试结果（截图或文字描述）
5. 是否遇到问题

---

## 五、注意事项

1. **阶段 1 的 `ai_modeling_api` 需要 file_path**：如果当前 `ai_modeling_api` 没有接收 file_path，需要同步修改前端传入和路由接收。

2. **阶段 2 的 SSIM 依赖**：必须安装 scikit-image，否则 `scoring.py` 会降级到默认 0.5 分。

3. **阶段 3 的 Z 轴范围**：`add_annotations_to_ai_image` 需要 z_min/z_max，当前代码里用了默认值 -300/400。如果要从缓存中读取准确的 Z 轴范围，需要在阶段 1 保存缓存时把 z_min/z_max 一起保存。

4. **阶段 3 的颜色映射**：从 `modelData.color_map` 传入，如果为空则提示用户先生成建模图。

5. **缓存与阶段 2/3 的交互**：
   - 阶段 2 的候选图结果应保存到缓存（`task_type='ai_model'`）
   - 阶段 3 生成的多视角图，也建议加入缓存（可选，看用户需求）

---

**文档结束**

如遇到问题，请向用户汇报，等待进一步指示。
