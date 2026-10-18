"""
导出（或校验）共享的 plotly.js 到 static/js/plotly.min.js。

背景：生成的交互式页面原本每页内嵌一份 plotly.js（3.60 MB），而各页内嵌的是
完全相同的同一份文件。改为引用 static/js/plotly.min.js 后，浏览器只需下载一次，
生成页体积直接少 3.60 MB。

本脚本把「当前安装的 plotly 会内嵌的那份 plotly.js」原样写到 static/js/plotly.min.js，
因此共享文件的字节与原先内嵌的完全一致（不改动任何绘图行为）。

用法：
    python tools/export_plotlyjs.py            # 缺失则导出，已存在则校验
    python tools/export_plotlyjs.py --force    # 强制重新导出（plotly 升级后用）
    python tools/export_plotlyjs.py --check    # 只校验，不写入（不一致时返回 1）
"""
import argparse
import hashlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def bundled_plotlyjs():
    """返回 plotly 会内嵌进 HTML 的那份 plotly.js 源码。"""
    from plotly.offline.offline import get_plotlyjs
    return get_plotlyjs()


def plotly_version():
    try:
        import plotly
        if hasattr(plotly, '__version__'):
            return plotly.__version__
    except Exception:
        pass
    try:
        from plotly.offline.offline import _plotlyjs_version
        return _plotlyjs_version
    except Exception:
        return '未知'


def main():
    ap = argparse.ArgumentParser(description='导出/校验共享的 plotly.js')
    ap.add_argument('--force', action='store_true', help='已存在时也强制重新导出')
    ap.add_argument('--check', action='store_true', help='只校验，不写入')
    args = ap.parse_args()

    from config import STATIC_FOLDER
    target = os.path.join(STATIC_FOLDER, 'js', 'plotly.min.js')
    source = bundled_plotlyjs()
    src_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()

    print('plotly 版本 : %s' % plotly_version())
    print('目标文件   : %s' % target)
    print('内嵌源码   : %s 字节  sha256 %s' % (format(len(source), ','), src_hash[:16]))

    if os.path.isfile(target):
        with open(target, 'r', encoding='utf-8') as fh:
            current = fh.read()
        cur_hash = hashlib.sha256(current.encode('utf-8')).hexdigest()
        same = (cur_hash == src_hash)
        print('现有文件   : %s 字节  sha256 %s  %s'
              % (format(len(current), ','), cur_hash[:16], '一致 ✓' if same else '不一致 ✗'))
        if same:
            print('无需改动。')
            return 0
        if args.check:
            print('共享文件与当前 plotly 不一致：plotly 升级后请执行 --force 重新导出。')
            return 1
        if not args.force:
            print('提示：加 --force 才会覆盖。')
            return 1
    elif args.check:
        print('共享文件不存在 ✗（生成页会退回内嵌，功能不受影响但体积大 3.60 MB）')
        return 1

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as fh:
        fh.write(source)
    print('已写出 %s 字节 → %s' % (format(len(source), ','), target))
    return 0


if __name__ == '__main__':
    sys.exit(main())