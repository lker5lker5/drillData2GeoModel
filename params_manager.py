"""
用户参数管理：管理每个会话的建模参数。
参数与 session_id 绑定，保存在 uploads/{session_id}/user_params.json 中。
"""
import os
import json
import hashlib

from config import UPLOAD_FOLDER, SESSION_PARAMS_FILENAME, USER_ADJUSTABLE_PARAMS


def get_default_params():
    """获取所有可调参数的默认值"""
    defaults = {}
    for key, meta in USER_ADJUSTABLE_PARAMS.items():
        defaults[key] = meta['default']
    return defaults


def get_params_path(session_id):
    """获取参数文件路径"""
    return os.path.join(UPLOAD_FOLDER, session_id, SESSION_PARAMS_FILENAME)


def load_session_params(session_id):
    """
    加载会话参数。
    如果参数文件不存在，返回默认参数。
    """
    if not session_id:
        return get_default_params()

    params_path = get_params_path(session_id)
    if not os.path.exists(params_path):
        return get_default_params()

    try:
        with open(params_path, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        # 与默认值合并，确保新增的参数有默认值
        defaults = get_default_params()
        defaults.update(saved)
        return defaults
    except Exception as e:
        print(f"!!! 读取参数失败: {e}")
        return get_default_params()


def save_session_params(session_id, params):
    """
    保存会话参数。只保存可调参数，其他键忽略。
    """
    if not session_id:
        return False, "缺少 session_id"

    # 过滤：只保留可调参数
    filtered = {}
    for key in USER_ADJUSTABLE_PARAMS.keys():
        if key in params:
            filtered[key] = params[key]

    # 校验
    ok, err = validate_params(filtered)
    if not ok:
        return False, err

    # 保存
    params_path = get_params_path(session_id)
    os.makedirs(os.path.dirname(params_path), exist_ok=True)

    try:
        with open(params_path, 'w', encoding='utf-8') as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_params(params):
    """
    校验参数范围。
    返回: (是否合法, 错误信息)
    """
    for key, value in params.items():
        if key not in USER_ADJUSTABLE_PARAMS:
            continue
        meta = USER_ADJUSTABLE_PARAMS[key]
        ptype = meta['type']

        # 枚举校验
        if ptype == 'enum':
            if value not in meta['options']:
                return False, f"{key} 的值 '{value}' 不在允许的选项中: {meta['options']}"

        # 数值校验
        elif ptype == 'number':
            try:
                v = float(value)
            except (TypeError, ValueError):
                return False, f"{key} 必须是数字"
            if v < meta['min'] or v > meta['max']:
                return False, f"{key} 的值 {v} 超出范围 [{meta['min']}, {meta['max']}]"

        # 数值或自动校验
        elif ptype == 'number_or_auto':
            if value is None:
                continue
            try:
                v = int(value)
            except (TypeError, ValueError):
                return False, f"{key} 必须是整数或 null"
            if v < meta['min'] or v > meta['max']:
                return False, f"{key} 的值 {v} 超出范围 [{meta['min']}, {meta['max']}]"

    return True, None


def compute_params_hash(params):
    """
    计算参数哈希，用于缓存判断。
    """
    filtered = {}
    for key in sorted(USER_ADJUSTABLE_PARAMS.keys()):
        if key in params:
            filtered[key] = params[key]
    # 转为 JSON 字符串后哈希
    s = json.dumps(filtered, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def get_frontend_meta():
    """
    返回给前端的参数元信息（用于渲染 UI）。
    """
    meta = {}
    for key, info in USER_ADJUSTABLE_PARAMS.items():
        meta[key] = {
            'label': info['label'],
            'type': info['type'],
            'default': info['default'],
            'description': info.get('description', '')
        }
        if 'options' in info:
            meta[key]['options'] = info['options']
        if 'min' in info:
            meta[key]['min'] = info['min']
        if 'max' in info:
            meta[key]['max'] = info['max']
        if 'step' in info:
            meta[key]['step'] = info['step']
    return meta