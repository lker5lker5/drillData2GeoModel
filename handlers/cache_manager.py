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
    cache_dir = os.path.join(OUTPUT_FOLDER, session_id, CACHE_DIR_NAME) if session_id else os.path.join(OUTPUT_FOLDER, CACHE_DIR_NAME)
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


def get_cached_result(session_id, task_type, input_hash, params_hash=None):
    """
    查询缓存。

    参数:
        session_id: 会话 ID
        task_type: 'model' 或 'ai_model'
        input_hash: 输入文件的哈希值
        params_hash: 参数哈希（可选）

    返回:
        命中: {'result': {...}, 'created_at': '...'}
        未命中: None
    """
    meta = load_cache_meta(session_id)
    entry = meta.get(task_type)
    if not entry:
        return None

    # 检查输入文件哈希
    if entry.get('input_hash') != input_hash:
        return None

    # 检查参数哈希（如果提供）
    if params_hash is not None:
        if entry.get('params_hash') != params_hash:
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


def save_cached_result(session_id, task_type, input_hash, result, result_dir, params_hash=None):
    """
    保存缓存。

    参数:
        session_id: 会话 ID
        task_type: 'model' 或 'ai_model'
        input_hash: 输入文件的哈希值
        result: 结果字典
        result_dir: 结果文件所在目录
        params_hash: 参数哈希（可选）
    """
    meta = load_cache_meta(session_id)
    meta[task_type] = {
        'input_hash': input_hash,
        'params_hash': params_hash,
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


def clear_cache_by_params_change(session_id):
    """
    当参数变化时，清除该 session 的模型、AI 模型和克里金缓存，
    同时清除分析数据以免数据报告显示过期参数。
    """
    meta = load_cache_meta(session_id)
    for key in ['model', 'ai_model', 'kriging', 'kriging_surface',
            'rbf_analysis', 'kriging_analysis', 'quality_check',
            'drill_views', 'interactive_model_drill_only', 'interactive_model_full', 'multiview_tex']:
        meta.pop(key, None)
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
            if not isinstance(entry, dict):
                continue
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