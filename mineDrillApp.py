# main.py
# 地质体建模 Web 应用入口

from flask import Flask
import os
import shutil
import threading
import time
import webbrowser
from config import *

app = Flask(__name__, template_folder='templates')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 注册所有路由
from handlers.user_handler import register_routes as register_user_routes
from handlers.data_handler import register_routes as register_data_routes
register_user_routes(app)
register_data_routes(app)


# ==================== 启动 ====================
def open_browser():
    """自动打开浏览器"""
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{PORT}')


def cache_cleanup_daemon():
    """后台线程：定期清理过期缓存和过期 session"""
    import time
    from handlers.cache_manager import cleanup_expired_cache
    from config import CACHE_CLEANUP_INTERVAL
    from handlers.app_utils import cleanup_expired_sessions
    while True:
        try:
            cleanup_expired_cache()
        except Exception as e:
            print(f"!!! 缓存清理异常: {e}")
        try:
            expired = cleanup_expired_sessions()
            if expired:
                print(f"==> 清理了 {len(expired)} 个过期 session")
        except Exception as e:
            print(f"!!! 会话清理异常: {e}")
        time.sleep(CACHE_CLEANUP_INTERVAL)


if __name__ == '__main__':
    print('======================================================================')
    print('  地质体建模 Web 应用')
    print('======================================================================')
    print(f'  服务地址: http://127.0.0.1:{PORT}')
    print(f'  上传目录: {UPLOAD_FOLDER}')
    print(f'  输出目录: {OUTPUT_FOLDER}')
    print('======================================================================')

    # 启动时清理历史遗留数据
    try:
        cleaned_count = 0
        for item in os.listdir(OUTPUT_FOLDER):
            item_path = os.path.join(OUTPUT_FOLDER, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
                cleaned_count += 1
            elif os.path.isdir(item_path) and len(item) != 8:
                shutil.rmtree(item_path, ignore_errors=True)
                cleaned_count += 1
        # 同步清空 uploads/ 文件夹
        for item in os.listdir(UPLOAD_FOLDER):
            item_path = os.path.join(UPLOAD_FOLDER, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
                cleaned_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
                cleaned_count += 1
        if cleaned_count > 0:
            print(f'==> 启动时清理了 {cleaned_count} 个遗留文件/目录')
    except Exception as e:
        print(f'!!! 启动清理异常: {e}')

    # 启动缓存清理线程
    threading.Thread(target=cache_cleanup_daemon, daemon=True).start()
    print('==> 缓存清理线程已启动')

    # 自动打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host=HOST, port=PORT, debug=DEBUG)