"""
共享工具函数：日志存储、Session 管理。
从 main.py 和 handlers/ 引用，避免循环导入。
"""
import os
import shutil
import time
from collections import defaultdict
from config import OUTPUT_FOLDER, UPLOAD_FOLDER, SESSION_TIMEOUT_MINUTES


# ==================== 日志存储 ====================
log_storage = defaultdict(list)
MAX_LOG_ENTRIES = 1000


def add_log(session_id, msg, msg_type='info'):
    """添加日志到会话存储"""
    if session_id:
        log_storage[session_id].append({
            'time': time.time(),
            'msg': msg,
            'type': msg_type
        })
        if len(log_storage[session_id]) > MAX_LOG_ENTRIES:
            log_storage[session_id] = log_storage[session_id][-MAX_LOG_ENTRIES:]


def log_and_print(session_id, msg, msg_type='info'):
    """同时打印到终端并记录到日志存储"""
    print(msg)
    add_log(session_id, msg, msg_type)


# ==================== Session 管理 ====================
SESSION_TIMEOUT = SESSION_TIMEOUT_MINUTES * 60  # 转换为秒
session_last_active = {}  # session_id -> last_active_timestamp


def update_session_activity(session_id):
    """更新 session 的最后活跃时间"""
    if session_id:
        session_last_active[session_id] = time.time()


def get_session_output_dir(session_id):
    """返回 session 对应的输出目录"""
    session_dir = os.path.join(OUTPUT_FOLDER, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def get_session_output_url(session_id, filename):
    """返回 session 输出文件的 URL"""
    return f'/outputs/{session_id}/{filename}'


def cleanup_session(session_id):
    """清理 session 的所有临时数据"""
    if not session_id:
        return
    log_and_print(session_id, f"==> 正在清理 session: {session_id}")
    session_output_dir = os.path.join(OUTPUT_FOLDER, session_id)
    if os.path.exists(session_output_dir):
        shutil.rmtree(session_output_dir, ignore_errors=True)
        log_and_print(session_id, f"==> 已清理输出目录: {session_id}")
    session_upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
    if os.path.exists(session_upload_dir):
        shutil.rmtree(session_upload_dir, ignore_errors=True)
        log_and_print(session_id, f"==> 已清理上传目录: {session_id}")
    if session_id in log_storage:
        del log_storage[session_id]
    if session_id in session_last_active:
        del session_last_active[session_id]
    log_and_print(session_id, f"==> Session {session_id} 清理完成")


def cleanup_expired_sessions():
    """清理所有过期 session 的数据"""
    now = time.time()
    expired = [
        sid for sid, last_active in session_last_active.items()
        if (now - last_active) > SESSION_TIMEOUT
    ]
    for sid in expired:
        print(f"==> Session {sid} 已过期（超过 {SESSION_TIMEOUT_MINUTES} 分钟无活动），正在清理...")
        cleanup_session(sid)
    return expired