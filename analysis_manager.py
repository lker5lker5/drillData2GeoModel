"""
分析数据管理器：保存 RBF 和克里金的分析数据，用于数据说明页面。
"""
import os
import json
import numpy as np
from datetime import datetime

from config import OUTPUT_FOLDER, CACHE_DIR_NAME


def get_analysis_data_path(session_id):
    """获取分析数据文件路径"""
    cache_dir = os.path.join(OUTPUT_FOLDER, session_id, CACHE_DIR_NAME)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, 'analysis_data.json')


def load_analysis_data(session_id):
    """加载分析数据"""
    path = get_analysis_data_path(session_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"!!! 读取分析数据失败: {e}")
        return {}


def save_analysis_data(session_id, data):
    """保存分析数据"""
    path = get_analysis_data_path(session_id)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"!!! 保存分析数据失败: {e}")
        return False


def _numpy_to_list(arr):
    """把 numpy 数组转为可 JSON 序列化的列表"""
    if arr is None:
        return None
    if isinstance(arr, np.ndarray):
        return [None if np.isnan(v) else float(v) for v in arr.ravel()]
    elif isinstance(arr, (list, tuple)):
        return [None if isinstance(v, float) and np.isnan(v) else v for v in arr]
    return arr


def record_rbf_data(session_id, params, layers_info):
    """记录 RBF 建模的分析数据"""
    data = load_analysis_data(session_id)

    if 'rbf' not in data:
        data['rbf'] = {'params': params, 'layers': [], 'created_at': None}

    data['rbf']['params'] = params
    data['rbf']['created_at'] = datetime.now().isoformat()
    data['rbf']['layers'] = layers_info

    save_analysis_data(session_id, data)
    print(f"==> RBF 分析数据已记录（{len(layers_info)} 个图层）")


def record_kriging_data(session_id, params, layers_info):
    """记录克里金分析数据"""
    data = load_analysis_data(session_id)

    if 'kriging' not in data:
        data['kriging'] = {'params': params, 'layers': [], 'created_at': None}

    data['kriging']['params'] = params
    data['kriging']['created_at'] = datetime.now().isoformat()
    data['kriging']['layers'] = layers_info

    save_analysis_data(session_id, data)
    print(f"==> 克里金分析数据已记录（{len(layers_info)} 个图层）")