"""
数据处理路由：上传、分析、参数管理、导出、清理。
使用 register_routes(app) 模式注册所有路由。
"""
from flask import request, jsonify, render_template, send_file, send_from_directory
from flask import Response, abort
import os
import shutil
import uuid
import time
import gzip
import mimetypes
import pandas as pd
import numpy as np
import zipfile
from datetime import datetime
from io import BytesIO
from werkzeug.utils import safe_join
from werkzeug.http import http_date
from .app_utils import *
from config import *
from .processors import *


# ==================== 生成文件服务：gzip + 缓存 ====================
# 生成页里内嵌的 plotly.js 有 3.6 MB，gzip 后 1.1 MB，是页面最大的载荷。
# 这里对可压缩的文本资源在客户端支持时返回 gzip，并把压缩结果按
# (路径, 修改时间, 大小) 缓存在进程内——每个文件只付一次压缩 CPU；
# 同时返回 ETag / Last-Modified，浏览器再次打开同一页面时命中 304，
# 一个字节都不用重传（本地访问时这一项比压缩本身更值钱）。
_COMPRESSIBLE_EXT = {'.html', '.htm', '.js', '.css', '.json', '.svg', '.txt', '.xml', '.csv'}
_GZIP_MIN_SIZE = 1024      # 再小压缩后反而更大
_GZIP_LEVEL = 6            # 实测 6 与 9 的压缩率相同（都是 73%），但快约 20%
_GZIP_CACHE_LIMIT = 8      # 每项约 1 MB，常驻内存上限约 9 MB
_gzip_cache = {}


def _gzip_cached(path):
    """返回 path 的 gzip 字节；命中进程内缓存则不再重复压缩。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime_ns, st.st_size)
    hit = _gzip_cache.get(key)
    if hit is not None:
        return hit
    try:
        with open(path, 'rb') as fh:
            packed = gzip.compress(fh.read(), _GZIP_LEVEL)
    except OSError:
        return None
    if len(_gzip_cache) >= _GZIP_CACHE_LIMIT:
        _gzip_cache.pop(next(iter(_gzip_cache)))   # 简单 FIFO，够用
    _gzip_cache[key] = packed
    return packed


def serve_file_with_gzip(directory, filename, max_age=300):
    """
    带 gzip 与缓存头的文件服务（/outputs 与 /static 共用）。

    max_age: 强缓存秒数。生成物（名字带时间戳、内容不再变化）给 300 秒，
             静态源文件给 None（每次都带 ETag 回来校验，保证改了立刻生效）。
    """
    full = safe_join(directory, filename)
    if not full or not os.path.isfile(full):
        abort(404)

    st = os.stat(full)
    ext = os.path.splitext(full)[1].lower()
    want_gzip = (ext in _COMPRESSIBLE_EXT and st.st_size >= _GZIP_MIN_SIZE
                 and 'gzip' in (request.headers.get('Accept-Encoding') or ''))
    # gzip 与非 gzip 是同一文件的不同表示，ETag 必须区分开，
    # 否则先取到 gzip 的浏览器再发不带 gzip 的请求时会误命中 304。
    etag = '"%x-%x%s"' % (int(st.st_mtime), st.st_size, '-gz' if want_gzip else '')

    if request.headers.get('If-None-Match') == etag:
        resp = Response(status=304)
    else:
        packed = _gzip_cached(full) if want_gzip else None
        if packed is not None:
            resp = Response(packed, mimetype=mimetypes.guess_type(full)[0]
                            or 'application/octet-stream')
            resp.headers['Content-Encoding'] = 'gzip'
        else:
            resp = send_file(full, conditional=False)

    resp.headers['ETag'] = etag
    resp.headers['Last-Modified'] = http_date(st.st_mtime)
    resp.headers['Cache-Control'] = ('no-cache' if max_age is None
                                     else 'private, max-age=%d' % max_age)
    resp.headers['Vary'] = 'Accept-Encoding'
    return resp


def register_routes(app):
    # ==================== 路由 ====================
    @app.route('/api/logs/<session_id>')
    def get_logs(session_id):
        """获取指定会话的日志（返回 JSON）"""
        since = request.args.get('since', type=float, default=0)
        logs = log_storage.get(session_id, [])
        # 返回 since 之后的新日志
        new_logs = [log for log in logs if log['time'] > since]
        return jsonify({
            'logs': new_logs,
            'latest': logs[-1]['time'] if logs else 0
        })
    
    
    @app.route('/')
    def index():
        # 静态文件版本号（基于文件修改时间），用于缓存破坏
        static_ver = 1
        try:
            css_path = os.path.join(app.root_path, 'static', 'css', 'style.css')
            js_path = os.path.join(app.root_path, 'static', 'js', 'main.js')
            css_mtime = int(os.path.getmtime(css_path))
            js_mtime = int(os.path.getmtime(js_path))
            static_ver = max(css_mtime, js_mtime)
        except Exception:
            pass
        return render_template('index.html',
                               zj_key=ZJ_TIANDITU_KEY,
                               zj_host=ZJ_TIANDITU_HOST,
                               static_ver=static_ver)    
    
    
    @app.route('/api/template_info', methods=['GET'])
    def get_template_info():
        """获取模板数据信息"""
        template_path = TEMPLATE_FILE
        
        if not os.path.exists(template_path):
            generate_template()
        
        try:
            loc_df = pd.read_excel(template_path, sheet_name='定位表')
            survey_df = pd.read_excel(template_path, sheet_name='测斜表')
            litho_df = pd.read_excel(template_path, sheet_name='岩性表')
    
            points = add_points_to_data(loc_df)
            
            return jsonify({
                'success': True,
                'is_template': True,
                'data': {
                    'location': loc_df.to_dict('records'),
                    'survey': survey_df.to_dict('records'),
                    'lithology': litho_df.to_dict('records'),
                    'points': points,
                    'stats': {
                        'total_holes': len(loc_df['钻孔编号'].unique()),
                        'total_survey_points': len(survey_df),
                        'total_lithology_segments': len(litho_df)
                    }
                }
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    
    
    @app.route('/api/file_info', methods=['POST'])
    def get_file_info():
        try:
            data = request.json
            file_path = data.get('path')
            if not file_path or not os.path.exists(file_path):
                return jsonify({'error': '文件不存在'}), 400
    
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            # 打印列名以检查是否匹配
            print("定位表列:", loc_df.columns.tolist())
            print("测斜表列:", survey_df.columns.tolist())
            print("岩性表列:", litho_df.columns.tolist())
    
            # 清理空列
            loc_df = loc_df.dropna(axis=1, how='all')
            survey_df = survey_df.dropna(axis=1, how='all')
            litho_df = litho_df.dropna(axis=1, how='all')
    
            # 转换 NaN 为 None
            loc_df = loc_df.where(pd.notnull(loc_df), None)
            survey_df = survey_df.where(pd.notnull(survey_df), None)
            litho_df = litho_df.where(pd.notnull(litho_df), None)
    
            points = add_points_to_data(loc_df)
            color_map = get_color_map_from_dataframe(litho_df)
            lithology_stats = litho_df['岩性描述'].value_counts().to_dict()
    
            return jsonify({
                'success': True,
                'data': {
                    'location': loc_df.to_dict('records'),
                    'survey': survey_df.to_dict('records'),
                    'lithology': litho_df.to_dict('records'),
                    'points': points,
                    'stats': {
                        'total_holes': len(loc_df['钻孔编号'].unique()),
                        'total_survey_points': len(survey_df),
                        'total_lithology_segments': len(litho_df),
                        'lithology_stats': lithology_stats,
                        'color_map': color_map
                    }
                }
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """静态文件服务"""
        return send_from_directory(STATIC_FOLDER, filename)
    
    
    
    @app.route('/outputs/<path:filename>')
    def output_files(filename):
        """输出文件服务（支持 gzip 与缓存校验）"""
        return serve_file_with_gzip(OUTPUT_FOLDER, filename)

    @app.route(PLOTLYJS_URL)
    def shared_plotlyjs():
        """
        共享 plotly.js（生成页共用的那一份，3.60 MB）。

        这条显式路由没有参数，比 Flask 内置的 /static/<path:filename> 更具体，
        因此优先匹配——只为这一个占页面 85% 的资源开 gzip 与缓存校验，
        /static/ 下其它文件仍走 Flask 原有行为，不受影响。
        max_age=None：每次都带 ETag 回来校验，文件换了立刻生效（只花一次 304）。
        """
        return serve_file_with_gzip(STATIC_FOLDER, PLOTLYJS_REL_PATH, max_age=None)

    # 生成页引用的两个面板脚本（第 12 项抽成的独立文件）走同一条通道：
    # 与共享 plotly.js 一样是无参数路由，优先于 Flask 内置的 /static/<path:filename>。
    # 体积虽小（3.7 KB / 22.5 KB），但它们是每个生成页都要下载的公共资源，
    # 开 gzip 后可再省约 3/4；缓存策略与 plotly.js 保持一致，改了立刻生效。
    @app.route(LAYER_PANEL_JS_URL)
    def shared_layer_panel_js():
        """分层观察 / 岩性显隐 / 钻孔显隐面板脚本。"""
        return serve_file_with_gzip(STATIC_FOLDER, LAYER_PANEL_JS_REL_PATH, max_age=None)

    @app.route(VOLUME_PANEL_JS_URL)
    def shared_volume_panel_js():
        """体积估算面板脚本。"""
        return serve_file_with_gzip(STATIC_FOLDER, VOLUME_PANEL_JS_REL_PATH, max_age=None)
    
    
    
    @app.route('/api/layers_list', methods=['POST'])
    def layers_list_api():
        """获取上传文件中的岩性列表"""
        data = request.json
        file_path = data.get('path')
    
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        try:
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
            layers = sorted(litho_df['岩性描述'].dropna().unique().tolist())
            return jsonify({
                'success': True,
                'layers': layers
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    
    
    @app.route('/api/upload', methods=['POST'])
    def upload_file():
        """上传Excel文件"""
        if 'file' not in request.files:
            return jsonify({'error': '没有文件被上传'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
    
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '只支持 .xlsx 和 .xls 格式'}), 400
    
        # ========== 清理旧 session（如果有） ==========
        old_session_id = request.form.get('old_session')
        if old_session_id:
            cleanup_session(old_session_id)
        # ============================================
    
        # 生成唯一会话ID
        session_id = str(uuid.uuid4())[:8]
        session_dir = os.path.join(UPLOAD_FOLDER, session_id)
        os.makedirs(session_dir, exist_ok=True)
    
        # 保存文件
        file_path = os.path.join(session_dir, file.filename)
        file.save(file_path)
    
        # ========== 清除该 session 的缓存 ==========
        from .cache_manager import clear_cache
        clear_cache(session_id)
        # =========================================
    
        update_session_activity(session_id)
    
        return jsonify({
            'session_id': session_id,
            'filename': file.filename,
            'path': file_path
        })
    
    
    
    @app.route('/api/session_params', methods=['GET'])
    def get_session_params():
        """
        获取当前会话的参数和参数元信息。
        """
        session_id = request.args.get('session_id')
    
        from .params_manager import load_session_params, get_frontend_meta, compute_params_hash
    
        params = load_session_params(session_id) if session_id else {}
        meta = get_frontend_meta()
        params_hash = compute_params_hash(params)
    
        return jsonify({
            'success': True,
            'params': params,
            'meta': meta,
            'params_hash': params_hash
        })
    
    
    
    @app.route('/api/save_params', methods=['POST'])
    def save_params_api():
        """
        保存当前会话的参数。
        如果参数与旧参数不同，清除模型缓存。
        """
        data = request.json
        session_id = data.get('session_id')
        params = data.get('params', {})
    
        if not session_id:
            return jsonify({'error': '缺少 session_id'}), 400
    
        from .params_manager import (
            load_session_params, save_session_params,
            compute_params_hash
        )
        from .cache_manager import clear_cache_by_params_change
    
        # 读取旧参数
        old_params = load_session_params(session_id)
        old_hash = compute_params_hash(old_params)
    
        # 保存新参数
        ok, err = save_session_params(session_id, params)
        if not ok:
            return jsonify({'error': err}), 400
    
        # 计算新哈希
        new_params = load_session_params(session_id)
        new_hash = compute_params_hash(new_params)
    
        # 如果参数变化，清除缓存
        if old_hash != new_hash:
            clear_cache_by_params_change(session_id)
            log_and_print(session_id, f"==> 参数已变更，模型缓存已清除")

        # 同步更新分析数据中的参数（确保数据说明 tab 始终展示最新参数）
        try:
            from .analysis_manager import load_analysis_data, save_analysis_data
            analysis_data = load_analysis_data(session_id)
            updated = False

            # RBF 参数映射: param_key → analysis_data_key
            rbf_key_map = {
                'RBF_FUNCTION': 'rbf_function',
                'RBF_SMOOTH': 'rbf_smooth',
                'GRID_RESOLUTION': 'grid_resolution',
                'N_LAYERS': 'n_layers'
            }
            if 'rbf' in analysis_data:
                p = dict(analysis_data['rbf']['params'])
                for pk, ak in rbf_key_map.items():
                    if pk in params:
                        p[ak] = params[pk]
                analysis_data['rbf']['params'] = p
                updated = True

            # 克里金参数映射
            kriging_key_map = {'KRIGING_VARIOGRAM': 'variogram_model'}
            if 'kriging' in analysis_data:
                p = dict(analysis_data['kriging']['params'])
                for pk, ak in kriging_key_map.items():
                    if pk in params:
                        p[ak] = params[pk]
                analysis_data['kriging']['params'] = p
                updated = True

            if updated:
                save_analysis_data(session_id, analysis_data)
                log_and_print(session_id, f"==> 分析数据参数已同步更新")
        except Exception as e:
            print(f"!!! 同步分析数据参数失败: {e}")
    
        return jsonify({
            'success': True,
            'params': new_params,
            'params_hash': new_hash
        })
    
    
    
    @app.route('/api/template', methods=['GET'])
    def download_template():
        """下载Excel模板"""
        template_path = generate_template()
        return send_file(template_path, as_attachment=True,
                         download_name='钻孔数据模板.xlsx')
    
    
    
    @app.route('/api/cleanup_session', methods=['POST'])
    def cleanup_session_api():
        """清理指定 session 的所有临时数据"""
        data = request.json
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': '缺少 session_id'}), 400
        cleanup_session(session_id)
        return jsonify({'success': True})
    
    
    
    @app.route('/api/cleanup_all_sessions', methods=['POST'])
    def cleanup_all_sessions_api():
        """清理所有 session 的临时数据"""
        import shutil
        # 清理所有 outputs/ 下的 session 子目录
        if os.path.exists(OUTPUT_FOLDER):
            for item in os.listdir(OUTPUT_FOLDER):
                item_path = os.path.join(OUTPUT_FOLDER, item)
                if os.path.isdir(item_path) and len(item) == 8:
                    cleanup_session(item)
        # 清理所有 uploads/ 下的 session 子目录
        if os.path.exists(UPLOAD_FOLDER):
            for item in os.listdir(UPLOAD_FOLDER):
                item_path = os.path.join(UPLOAD_FOLDER, item)
                if os.path.isdir(item_path) and len(item) == 8:
                    shutil.rmtree(item_path, ignore_errors=True)
        session_last_active.clear()
        log_storage.clear()
        return jsonify({'success': True})

    @app.route('/api/clear_uploads', methods=['POST'])
    def clear_uploads_api():
        """清空 uploads/ 文件夹所有内容"""
        import shutil
        cleaned = 0
        if os.path.exists(UPLOAD_FOLDER):
            for item in os.listdir(UPLOAD_FOLDER):
                item_path = os.path.join(UPLOAD_FOLDER, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    cleaned += 1
                except Exception:
                    pass
        return jsonify({'success': True, 'cleaned': cleaned})

    @app.route('/api/clear_outputs', methods=['POST'])
    def clear_outputs_api():
        """清空 outputs/ 文件夹所有内容"""
        import shutil
        cleaned = 0
        if os.path.exists(OUTPUT_FOLDER):
            for item in os.listdir(OUTPUT_FOLDER):
                item_path = os.path.join(OUTPUT_FOLDER, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    cleaned += 1
                except Exception:
                    pass
        session_last_active.clear()
        log_storage.clear()
        return jsonify({'success': True, 'cleaned': cleaned})
    
    
    
    @app.route('/api/analyze_kriging_params', methods=['POST'])
    def analyze_kriging_params_api():
        """
        克里金参数分析：遍历变异函数模型，输出最优参数。
        请求: { session_id, path, target_layer? }
        """
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
        target_layer = data.get('target_layer', 'all')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        try:
            from config import (
                CACHE_ENABLED, KRIGING_ANALYSIS_CACHE_TYPE, KRIGING_RMSE_STANDARDS,
                KRIGING_NUGGET_RATIO_STANDARDS, KRIGING_R2_STANDARDS, RBF_COMPOSITE_STANDARDS
            )
            from .cache_manager import (
                compute_file_hash, get_cached_result, save_cached_result
            )
            from .params_manager import load_session_params, compute_params_hash
            from .processors import optimize_kriging_params
    
            # 读取用户参数
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            # 缓存键
            cache_extra = f'_{target_layer}' if target_layer != 'all' else ''
    
            # 缓存查询
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(
                    session_id, KRIGING_ANALYSIS_CACHE_TYPE,
                    input_hash + cache_extra, params_hash
                )
                if cached:
                    log_and_print(session_id, "==> 命中克里金参数分析缓存")
                    # 缓存命中时，也要确保分析数据中记录的是最佳参数
                    try:
                        from .analysis_manager import save_best_params
                        cached_data = cached['result']
                        best_key = target_layer
                        cr = cached_data.get('analysis', {}).get(best_key, {})
                        if cr.get('best'):
                            b = cr['best']
                            save_best_params(session_id, 'kriging', {
                                'variogram_model': b.get('variogram_model'),
                                'nlags': b.get('nlags'),
                                'weight': b.get('weight')
                            })
                    except Exception:
                        pass
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **cached['result']
                    })
    
            # 读取数据
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            # 提取控制点（与 RBF 分析相同的逻辑）
            hole_coords = {}
            for _, row in loc_df.iterrows():
                hid = row['钻孔编号']
                hole_coords[hid] = (row['开孔坐标E'], row['开孔坐标N'], row['开孔高程R'])
    
            traj_cache = {}
            for hid in loc_df['钻孔编号']:
                surv = survey_df[survey_df['钻孔编号'] == hid]
                if len(surv) > 0:
                    lengths, xs, ys, zs = compute_trajectory(surv)
                    traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
            litho_groups = {}
            for _, seg in litho_df.iterrows():
                hid = seg['钻孔编号']
                d_top = seg['上层位长度起始刻度']
                d_bot = seg['下层位长度起始刻度']
                lith = seg['岩性描述']
    
                if hid not in hole_coords or hid not in traj_cache:
                    continue
    
                e0, n0, z0 = hole_coords[hid]
                traj = traj_cache[hid]
    
                x_top, y_top, z_top = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
                x_bot, y_bot, z_bot = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
    
                x_top, y_top = x_top[0] + e0, y_top[0] + n0
                x_bot, y_bot = x_bot[0] + e0, y_bot[0] + n0
                z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
    
                if lith not in litho_groups:
                    litho_groups[lith] = {'top': [], 'bottom': []}
                litho_groups[lith]['top'].append((x_top, y_top, z_top))
                litho_groups[lith]['bottom'].append((x_bot, y_bot, z_bot))
    
            # ========== 执行参数寻优 ==========
            analysis_results = {}
    
            if target_layer == 'all':
                all_pts = []
                for lith, group_data in litho_groups.items():
                    all_pts.extend(group_data['top'])
    
                all_pts_arr = np.array(all_pts)
                log_and_print(session_id, f"==> 分析整个数据集（{len(all_pts_arr)} 个控制点）")
    
                def progress_cb(current, total, info):
                    log_and_print(session_id, f"  [{current}/{total}] {info}", 'info')
    
                result = optimize_kriging_params(
                    x=all_pts_arr[:, 0],
                    y=all_pts_arr[:, 1],
                    z=all_pts_arr[:, 2],
                    progress_callback=progress_cb
                )
                analysis_results['all'] = result
                if result.get('best'):
                    b = result['best']
                    cs = b.get('composite_score')
                    cs_str = f'{cs:.4f}' if cs is not None else 'N/A'
                    log_and_print(session_id, f"==> 克里金推荐: {b['variogram_model']} | 综合评分={cs_str} | RMSE={b['rmse']:.2f} MAE={b['mae']:.2f} max_err={b['max_error']:.2f}")
            else:
                if target_layer not in litho_groups:
                    return jsonify({'error': f'未找到岩性: {target_layer}'}), 400
    
                top_pts = np.array(litho_groups[target_layer]['top'])
                log_and_print(session_id, f"==> 分析岩性: {target_layer}（{len(top_pts)} 个控制点）")
    
                def progress_cb(current, total, info):
                    log_and_print(session_id, f"  [{current}/{total}] {info}", 'info')
    
                result = optimize_kriging_params(
                    x=top_pts[:, 0],
                    y=top_pts[:, 1],
                    z=top_pts[:, 2],
                    progress_callback=progress_cb
                )
                analysis_results[target_layer] = result
                if result.get('best'):
                    b = result['best']
                    cs = b.get('composite_score')
                    cs_str = f'{cs:.4f}' if cs is not None else 'N/A'
                    log_and_print(session_id, f"==> 克里金推荐: {b['variogram_model']} | 综合评分={cs_str} | RMSE={b['rmse']:.2f} MAE={b['mae']:.2f} max_err={b['max_error']:.2f}")
    
            # ========== 组织返回数据 ==========
            # 记录最佳参数到分析数据，确保数据说明 tab 显示推荐参数
            try:
                from .analysis_manager import save_best_params
                best_key = target_layer
                best_result = analysis_results.get(best_key)
                if best_result and best_result.get('best'):
                    b = best_result['best']
                    save_best_params(session_id, 'kriging', {
                        'variogram_model': b.get('variogram_model'),
                        'nlags': b.get('nlags'),
                        'weight': b.get('weight')
                    })
            except Exception as e:
                print(f"!!! 保存克里金最佳参数到分析数据失败: {e}")

            result_data = {
                'target_layer': target_layer,
                'analysis': analysis_results,
                'standards': KRIGING_RMSE_STANDARDS,
                'composite_standards': RBF_COMPOSITE_STANDARDS,
                'nugget_ratio_standards': KRIGING_NUGGET_RATIO_STANDARDS,
                'r2_standards': KRIGING_R2_STANDARDS,
                'layers_available': list(litho_groups.keys())
            }
    
            # 缓存
            if CACHE_ENABLED and input_hash:
                save_cached_result(
                    session_id, KRIGING_ANALYSIS_CACHE_TYPE,
                    input_hash + cache_extra, result_data, OUTPUT_FOLDER, params_hash
                )
                log_and_print(session_id, "==> 克里金参数分析结果已缓存")
    
            log_and_print(session_id, f"==> 克里金参数分析完成")
    
            return jsonify({
                'success': True,
                'from_cache': False,
                **result_data
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! 克里金参数分析失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    
    @app.route('/api/analyze_rbf_params', methods=['POST'])
    def analyze_rbf_params_api():
        """
        RBF 参数分析：遍历核函数和 smooth 组合，输出最优参数。
        请求: { session_id, path, target_layer? }
        """
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
        target_layer = data.get('target_layer', 'all')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        try:
            from config import (
                CACHE_ENABLED, RBF_ANALYSIS_CACHE_TYPE, RBF_RMSE_STANDARDS, RBF_COMPOSITE_STANDARDS
            )
            from .cache_manager import (
                compute_file_hash, get_cached_result, save_cached_result
            )
            from .params_manager import load_session_params, compute_params_hash
            from .processors import optimize_rbf_params
    
            # 读取用户参数
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            # 缓存键：文件哈希 + target_layer
            cache_extra = f'_{target_layer}' if target_layer != 'all' else ''
    
            # 缓存查询
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(
                    session_id, RBF_ANALYSIS_CACHE_TYPE,
                    input_hash + cache_extra, params_hash
                )
                if cached:
                    log_and_print(session_id, "==> 命中 RBF 参数分析缓存")
                    # 缓存命中时，也要确保分析数据中记录的是最佳参数
                    try:
                        from .analysis_manager import save_best_params
                        cached_data = cached['result']
                        best_key = target_layer if target_layer != 'all' else 'all'
                        cr = cached_data.get('analysis', {}).get(best_key, {})
                        if cr.get('best'):
                            b = cr['best']
                            save_best_params(session_id, 'rbf', {
                                'rbf_function': b.get('rbf_function'),
                                'rbf_smooth': b.get('smooth'),
                                'grid_resolution': '分析推荐',
                                'n_layers': 'auto',
                                'epsilon': b.get('epsilon')
                            })
                    except Exception:
                        pass
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **cached['result']
                    })
    
            # 读取数据
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            # 提取控制点
            hole_coords = {}
            for _, row in loc_df.iterrows():
                hid = row['钻孔编号']
                hole_coords[hid] = (row['开孔坐标E'], row['开孔坐标N'], row['开孔高程R'])
    
            traj_cache = {}
            for hid in loc_df['钻孔编号']:
                surv = survey_df[survey_df['钻孔编号'] == hid]
                if len(surv) > 0:
                    lengths, xs, ys, zs = compute_trajectory(surv)
                    traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
            litho_groups = {}
            for _, seg in litho_df.iterrows():
                hid = seg['钻孔编号']
                d_top = seg['上层位长度起始刻度']
                d_bot = seg['下层位长度起始刻度']
                lith = seg['岩性描述']
    
                if hid not in hole_coords or hid not in traj_cache:
                    continue
    
                e0, n0, z0 = hole_coords[hid]
                traj = traj_cache[hid]
    
                x_top, y_top, z_top = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
                x_bot, y_bot, z_bot = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
    
                x_top, y_top = x_top[0] + e0, y_top[0] + n0
                x_bot, y_bot = x_bot[0] + e0, y_bot[0] + n0
                z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
    
                if lith not in litho_groups:
                    litho_groups[lith] = {'top': [], 'bottom': []}
                litho_groups[lith]['top'].append((x_top, y_top, z_top))
                litho_groups[lith]['bottom'].append((x_bot, y_bot, z_bot))
    
            # ========== 执行参数寻优 ==========
            analysis_results = {}
    
            if target_layer == 'all':
                # 分析整个数据集：合并所有岩性层的顶面控制点
                all_pts = []
                for lith, group_data in litho_groups.items():
                    all_pts.extend(group_data['top'])
    
                all_pts_arr = np.array(all_pts)
                log_and_print(session_id, f"==> 分析整个数据集（{len(all_pts_arr)} 个控制点）")
    
                def progress_cb(current, total, info):
                    log_and_print(session_id, f"  [{current}/{total}] {info}", 'info')
    
                result = optimize_rbf_params(
                    x=all_pts_arr[:, 0],
                    y=all_pts_arr[:, 1],
                    z=all_pts_arr[:, 2],
                    progress_callback=progress_cb
                )
                analysis_results['all'] = result
                if result.get('best'):
                    b = result['best']
                    cs = b.get('composite_score')
                    cs_str = f'{cs:.4f}' if cs is not None else 'N/A'
                    log_and_print(session_id, f"==> RBF 推荐: {b['rbf_function']}/smooth={b['smooth']} | 综合评分={cs_str} | RMSE={b['rmse']:.2f} MAE={b['mae']:.2f} max_err={b['max_error']:.2f}")
            else:
                if target_layer not in litho_groups:
                    return jsonify({'error': f'未找到岩性: {target_layer}'}), 400
    
                top_pts = np.array(litho_groups[target_layer]['top'])
                log_and_print(session_id, f"==> 分析岩性: {target_layer}（{len(top_pts)} 个控制点）")
    
                def progress_cb2(current, total, info):
                    log_and_print(session_id, f"  [{current}/{total}] {info}", 'info')
    
                result = optimize_rbf_params(
                    x=top_pts[:, 0],
                    y=top_pts[:, 1],
                    z=top_pts[:, 2],
                    progress_callback=progress_cb2
                )
                analysis_results[target_layer] = result
                if result.get('best'):
                    b = result['best']
                    cs = b.get('composite_score')
                    cs_str = f'{cs:.4f}' if cs is not None else 'N/A'
                    log_and_print(session_id, f"==> RBF 推荐: {b['rbf_function']}/smooth={b['smooth']} | 综合评分={cs_str} | RMSE={b['rmse']:.2f} MAE={b['mae']:.2f} max_err={b['max_error']:.2f}")
    
            # ========== 组织返回数据 ==========
            # 记录最佳参数到分析数据，确保数据说明 tab 显示推荐参数
            try:
                from .analysis_manager import save_best_params
                best_key = target_layer if target_layer != 'all' else 'all'
                best_result = analysis_results.get(best_key)
                if best_result and best_result.get('best'):
                    b = best_result['best']
                    save_best_params(session_id, 'rbf', {
                        'rbf_function': b.get('rbf_function'),
                        'rbf_smooth': b.get('smooth'),
                        'grid_resolution': '分析推荐',
                        'n_layers': 'auto',
                        'epsilon': b.get('epsilon')
                    })
            except Exception as e:
                print(f"!!! 保存 RBF 最佳参数到分析数据失败: {e}")

            result_data = {
                'target_layer': target_layer,
                'analysis': analysis_results,
                'standards': RBF_RMSE_STANDARDS,
                'composite_standards': RBF_COMPOSITE_STANDARDS,
                'layers_available': list(litho_groups.keys())
            }
    
            # 缓存
            if CACHE_ENABLED and input_hash:
                save_cached_result(
                    session_id, RBF_ANALYSIS_CACHE_TYPE,
                    input_hash + cache_extra, result_data, OUTPUT_FOLDER, params_hash
                )
                log_and_print(session_id, "==> RBF 参数分析结果已缓存")
    
            log_and_print(session_id, "==> RBF 参数分析完成")
    
            return jsonify({
                'success': True,
                'from_cache': False,
                **result_data
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! RBF 参数分析失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    
    @app.route('/api/kriging_analysis', methods=['POST'])
    def kriging_analysis_api():
        """克里金插值分析 - 生成与 RBF 对比的 2x2 并排图"""
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        try:
            from .params_manager import load_session_params, compute_params_hash
            from .cache_manager import compute_file_hash, get_cached_result, save_cached_result
            from config import CACHE_ENABLED
    
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            rbf_function = user_params.get('RBF_FUNCTION', RBF_FUNCTION)
            rbf_smooth = user_params.get('RBF_SMOOTH', RBF_SMOOTH)
            grid_resolution = user_params.get('GRID_RESOLUTION', GRID_RESOLUTION)
            n_layers = user_params.get('N_LAYERS', N_LAYERS)
            variogram_model = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            log_and_print(session_id, f"==> 克里金参数: 变异函数={variogram_model}, RBF={rbf_function}, 网格={grid_resolution}, 层数={n_layers}")
    
            # ========== 缓存查询 ==========
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(session_id, 'kriging', input_hash, params_hash)
                if cached:
                    log_and_print(session_id, "==> 命中缓存，直接返回克里金结果")
                    result = cached['result']
                    for cp in result.get('comparison_paths', []):
                        if 'url' in cp and cp['url'].startswith('/outputs/'):
                            fname = cp['url'][len('/outputs/'):]
                            # 兼容新旧缓存：新缓存不含 session_id，旧缓存已含
                            if not fname.startswith(session_id + '/'):
                                cp['url'] = f'/outputs/{session_id}/{fname}'
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **result
                    })
            # =============================
    
            output_dir = get_session_output_dir(session_id)
    
            # ========== 1. 读取数据 ==========
            log_and_print(session_id, "正在读取数据...")
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            log_and_print(session_id, f"定位表: {len(loc_df)} 行, 测斜表: {len(survey_df)} 行, 岩性表: {len(litho_df)} 行")
    
            # ========== 2. 执行克里金分析 ==========
            log_and_print(session_id, "正在执行克里金插值分析（含 RBF 对比）...")
            result = perform_kriging_analysis(
                loc_df, litho_df, survey_df,
                n_layers=n_layers,
                rbf_function=rbf_function,
                rbf_smooth=rbf_smooth,
                grid_resolution=grid_resolution,
                variogram_model=variogram_model,
                output_dir=output_dir
            )
    
            if result['layer_count'] == 0:
                log_and_print(session_id, "!!! 未生成任何岩性的克里金插值结果")
                # 即使未生成图片，也返回分析报告文本
                return jsonify({
                    'success': True,
                    'comparison_paths': [],
                    'layer_count': 0,
                    'analysis_text': result['analysis_text'],
                    'point_counts': {}
                })
    
            log_and_print(session_id, f"==> 成功分析 {result['layer_count']} 个岩性层")
    
            # ========== 3. 保存缓存（使用不含 session_id 的原始 URL）==========
            raw_comparison_paths = result['comparison_paths']
            result_data = {
                'comparison_paths': raw_comparison_paths,
                'analysis_text': result['analysis_text'],
                'layer_count': result['layer_count'],
                'point_counts': result['point_counts']
            }
    
            if CACHE_ENABLED and input_hash:
                save_cached_result(session_id, 'kriging', input_hash, result_data, output_dir, params_hash)
                log_and_print(session_id, "==> 已保存克里金结果到缓存")
    
            # 修正 comparison_paths 中的 URL（加上 session_id，仅用于本次响应）
            comparison_paths = []
            for cp in raw_comparison_paths:
                cp_copy = dict(cp)
                if 'url' in cp_copy and cp_copy['url'].startswith('/outputs/'):
                    fname = cp_copy['url'][len('/outputs/'):]
                    cp_copy['url'] = f'/outputs/{session_id}/{fname}'
                comparison_paths.append(cp_copy)
    
            return jsonify({
                'success': True,
                'from_cache': False,
                'comparison_paths': comparison_paths,
                'analysis_text': result_data['analysis_text'],
                'layer_count': result_data['layer_count'],
                'point_counts': result_data['point_counts']
            })
    
        except ImportError as e:
            log_and_print(session_id, f"!!! 缺少依赖: {str(e)}，请执行 pip install pykrige")
            return jsonify({'error': f'缺少依赖包: {str(e)}，请在终端执行 pip install pykrige'}), 500
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print("=" * 70)
            print("!!! kriging_analysis_api 异常:")
            print(error_detail)
            print("=" * 70)
            log_and_print(session_id, f"!!! 克里金分析失败: {str(e)}")
            return jsonify({
                'error': str(e),
                'detail': error_detail
            }), 500
    
    
    # ==================== 克里金曲面数值分析（新的独立分析） ====================
    
    
    @app.route('/api/kriging_surface_analysis', methods=['POST'])
    def kriging_surface_analysis_api():
        """克里金曲面数值分析 - 顶面和底面分别分析，与 RBF 对照"""
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
        variogram_model = data.get('variogram_model', None)
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        try:
            from .params_manager import load_session_params, compute_params_hash
            from .cache_manager import compute_file_hash, get_cached_result, save_cached_result
            from config import (CACHE_ENABLED, KRIGING_SURFACE_CACHE_TYPE,
                                KRIGING_DEFAULT_VARIOGRAM, KRIGING_VARIOGRAM_MODEL,
                                OUTPUT_FOLDER)
            from .processors import (generate_kriging_analysis_for_layer,
                                    compute_trajectory, get_interpolated_coords)
    
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            if not variogram_model:
                variogram_model = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            log_and_print(session_id, f"==> 克里金曲面分析参数: 变异函数={variogram_model}")
    
            # ========== 缓存查询 ==========
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(session_id, KRIGING_SURFACE_CACHE_TYPE, input_hash, params_hash)
                if cached:
                    log_and_print(session_id, "==> 命中缓存，直接返回克里金曲面分析结果")
                    result = cached['result']
                    for layer in result.get('layers', []):
                        for key in ['top_url', 'bot_url']:
                            val = layer.get(key)
                            if val and val.startswith('/outputs/'):
                                fname = val[len('/outputs/'):]
                                # 兼容新旧缓存：新缓存不含 session_id，旧缓存已含
                                if not fname.startswith(session_id + '/'):
                                    layer[key] = f'/outputs/{session_id}/{fname}'
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **result
                    })
            # =============================
    
            # ========== 读取数据 ==========
            log_and_print(session_id, "正在读取数据...")
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            log_and_print(session_id, f"定位表: {len(loc_df)} 行, 测斜表: {len(survey_df)} 行, 岩性表: {len(litho_df)} 行")
    
            # ========== 提取各岩性的控制点（原始坐标） ==========
            log_and_print(session_id, "==> 正在提取各岩性的控制点")
    
            hole_coords = {}
            for _, row in loc_df.iterrows():
                hid = row['钻孔编号']
                hole_coords[hid] = (row['开孔坐标E'], row['开孔坐标N'], row['开孔高程R'])
    
            traj_cache = {}
            for hid in loc_df['钻孔编号']:
                surv = survey_df[survey_df['钻孔编号'] == hid]
                if len(surv) > 0:
                    lengths, xs, ys, zs = compute_trajectory(surv)
                    traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
            litho_groups = {}
            for _, seg in litho_df.iterrows():
                hid = seg['钻孔编号']
                d_top = seg['上层位长度起始刻度']
                d_bot = seg['下层位长度起始刻度']
                lith = seg['岩性描述']
    
                if hid not in hole_coords or hid not in traj_cache:
                    continue
    
                e0, n0, z0 = hole_coords[hid]
                traj = traj_cache[hid]
    
                x_top, y_top, z_top = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
                x_bot, y_bot, z_bot = get_interpolated_coords(
                    traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
    
                x_top, y_top = x_top[0] + e0, y_top[0] + n0
                x_bot, y_bot = x_bot[0] + e0, y_bot[0] + n0
                z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
    
                if lith not in litho_groups:
                    litho_groups[lith] = {'top': [], 'bottom': []}
                litho_groups[lith]['top'].append((x_top, y_top, z_top))
                litho_groups[lith]['bottom'].append((x_bot, y_bot, z_bot))
    
            log_and_print(session_id, f"==> 提取到 {len(litho_groups)} 个岩性组")
    
            # ========== 逐层分析 ==========
            base_name = f'kriging_{datetime.now().strftime("%y%m%d%H%M")}'
            output_dir = get_session_output_dir(session_id)
    
            rbf_function = user_params.get('RBF_FUNCTION', None)
            rbf_smooth = user_params.get('RBF_SMOOTH', None)
    
            results = []
            all_warnings = []
    
            for lith, data in litho_groups.items():
                top_pts = np.array(data['top'])
                bot_pts = np.array(data['bottom'])
    
                log_and_print(session_id, f"==> 分析岩性: {lith}（顶{len(top_pts)}点/底{len(bot_pts)}点）")
    
                r = generate_kriging_analysis_for_layer(
                    lith, top_pts, bot_pts,
                    output_dir, base_name,
                    variogram_model=variogram_model,
                    rbf_function=rbf_function,
                    rbf_smooth=rbf_smooth
                )
                results.append(r)
                all_warnings.extend(r['warnings'])
    
            # ========== 记录克里金分析数据 ==========
            try:
                from .analysis_manager import record_kriging_data
    
                layers_info = []
                for r in results:
                    if r.get('top_path'):
                        layers_info.append({
                            'layer_name': r['layer_name'],
                            'part_name': '顶面',
                            'control_points': r.get('top_control_points', []),
                            'grid_x': r.get('top_grid_x', []),
                            'grid_y': r.get('top_grid_y', []),
                            'z_kriging': r.get('top_z_kriging', []),
                            'z_variance': r.get('top_z_variance', []),
                            'stats': r.get('top_stats', {})
                        })
                    if r.get('bot_path'):
                        layers_info.append({
                            'layer_name': r['layer_name'],
                            'part_name': '底面',
                            'control_points': r.get('bot_control_points', []),
                            'grid_x': r.get('bot_grid_x', []),
                            'grid_y': r.get('bot_grid_y', []),
                            'z_kriging': r.get('bot_z_kriging', []),
                            'z_variance': r.get('bot_z_variance', []),
                            'stats': r.get('bot_stats', {})
                        })
    
                kriging_params = {'variogram_model': variogram_model}
                record_kriging_data(session_id, kriging_params, layers_info)
            except Exception as e:
                log_and_print(session_id, f"!!! 记录克里金数据失败: {e}")
    
            # ========== 构建不含 session_id 的原始 URL（用于缓存）==========
            raw_layers = []
            for r in results:
                layer_info = {
                    'layer_name': r['layer_name'],
                    'top_url': f'/outputs/{os.path.basename(r["top_path"])}' if r['top_path'] else None,
                    'bot_url': f'/outputs/{os.path.basename(r["bot_path"])}' if r['bot_path'] else None,
                    'top_stats': r['top_stats'],
                    'bot_stats': r['bot_stats']
                }
                raw_layers.append(layer_info)
    
            raw_result_data = {
                'layers': raw_layers,
                'warnings': all_warnings,
                'variogram_model': variogram_model,
                'analysis_count': len([r for r in results if r['top_path'] or r['bot_path']])
            }
    
            # ========== 保存缓存 ==========
            if CACHE_ENABLED and input_hash:
                save_cached_result(session_id, KRIGING_SURFACE_CACHE_TYPE, input_hash, raw_result_data, output_dir, params_hash)
                log_and_print(session_id, "==> 曲面分析结果已缓存")
    
            log_and_print(session_id, f"==> 克里金曲面分析完成，共 {raw_result_data['analysis_count']} 个图层")
    
            # 构建含 session_id 的响应数据
            response_layers = []
            for layer in raw_layers:
                layer_copy = dict(layer)
                for key in ['top_url', 'bot_url']:
                    val = layer_copy.get(key)
                    if val and val.startswith('/outputs/'):
                        fname = val[len('/outputs/'):]
                        layer_copy[key] = f'/outputs/{session_id}/{fname}'
                response_layers.append(layer_copy)
    
            return jsonify({
                'success': True,
                'from_cache': False,
                'layers': response_layers,
                'warnings': raw_result_data['warnings'],
                'variogram_model': raw_result_data['variogram_model'],
                'analysis_count': raw_result_data['analysis_count']
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! 克里金曲面分析失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    
    # ==================== 模型质量评估 ====================
    
    @app.route('/api/evaluate_quality', methods=['POST'])
    def evaluate_quality_api():
        """
        模型质量评估接口。
        接收 session_id 和 path，返回各检查项结果和综合评分。
        """
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        if not ENABLE_QUALITY_CHECK:
            return jsonify({'error': '模型质量评估功能未启用'}), 400
    
        try:
            from .cache_manager import compute_file_hash, get_cached_result, save_cached_result
            from .params_manager import load_session_params, compute_params_hash
    
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            log_and_print(session_id, "==> 开始模型质量评估...")
    
            # ========== 缓存查询 ==========
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(session_id, QUALITY_CHECK_CACHE_TYPE, input_hash, params_hash)
                if cached:
                    log_and_print(session_id, "==> 命中缓存，直接返回质量评估结果")
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **cached['result']
                    })
    
            # ========== 执行评估 ==========
            # 首先需要获取地质体 bodies
            # 读取三个 sheet 并构建地质体
            log_and_print(session_id, "正在读取数据...")
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
            log_and_print(session_id, f"定位表: {len(loc_df)} 行, 测斜表: {len(survey_df)} 行, 岩性表: {len(litho_df)} 行")
    
            from .processors import build_geological_bodies_with_volume_v2
    
            grid_resolution = user_params.get('GRID_RESOLUTION', GRID_RESOLUTION)
            rbf_function = user_params.get('RBF_FUNCTION', RBF_FUNCTION)
            rbf_smooth = user_params.get('RBF_SMOOTH', RBF_SMOOTH)
            interpolation_method = user_params.get('INTERPOLATION_METHOD', INTERPOLATION_METHOD)
            kriging_variogram = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            bodies, volume_data = build_geological_bodies_with_volume_v2(
                loc_df, litho_df, survey_df,
                n_layers=user_params.get('N_LAYERS', N_LAYERS),
                rbf_function=rbf_function,
                rbf_smooth=rbf_smooth,
                grid_resolution=grid_resolution,
                session_id=session_id,
                method=interpolation_method,
                kriging_variogram=kriging_variogram
            )
            if not bodies or not volume_data:
                return jsonify({'error': '地质体构建失败，无法进行评估'}), 400
    
            log_and_print(session_id, f"成功构建 {len(volume_data)} 个地质体，开始质量评估...")
    
            # 执行综合评估
            result = evaluate_model_quality(bodies, litho_df)
    
            # ========== 保存缓存 ==========
            if CACHE_ENABLED and input_hash:
                save_cached_result(
                    session_id, QUALITY_CHECK_CACHE_TYPE,
                    input_hash, result, OUTPUT_FOLDER, params_hash=params_hash
                )
    
            log_and_print(session_id, f"==> 模型质量评估完成，综合评分: {result['overall_score']} 分，评级: {result['overall_grade']}")
    
            return jsonify({
                'success': True,
                'from_cache': False,
                **result
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! 模型质量评估失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    
    # ==================== 分析数据查询 ====================
    
    @app.route('/api/analysis_data', methods=['GET'])
    def get_analysis_data_api():
        """获取当前会话的分析数据（RBF + 克里金）"""
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({'error': '缺少 session_id'}), 400
    
        from .analysis_manager import load_analysis_data
        data = load_analysis_data(session_id)
    
        has_rbf = 'rbf' in data and data['rbf'].get('params') and len(data['rbf'].get('params', {})) > 0
        has_kriging = 'kriging' in data and data['kriging'].get('params') and len(data['kriging'].get('params', {})) > 0
    
        if not has_rbf and not has_kriging:
            return jsonify({
                'success': False,
                'error': '暂无分析数据，请先生成建模图或执行克里金分析'
            })
    
        return jsonify({
            'success': True,
            'has_rbf': has_rbf,
            'has_kriging': has_kriging,
            'data': data
        })
    
    
    
    # ==================== 分析数据导出 ====================
    
    @app.route('/api/export_analysis', methods=['POST'])
    def export_analysis_api():
        """导出分析数据为 ZIP 包"""
        import zipfile
        from io import BytesIO
    
        data = request.json
        session_id = data.get('session_id')
        formats = data.get('formats', ['csv', 'excel'])
    
        if not session_id:
            return jsonify({'error': '缺少 session_id'}), 400
    
        from .analysis_manager import load_analysis_data
    
        analysis_data = load_analysis_data(session_id)
        if not analysis_data:
            return jsonify({'error': '暂无分析数据'}), 400
    
        try:
            zip_buffer = BytesIO()
            timestamp = datetime.now().strftime('%y%m%d%H%M')
    
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. 统计汇总表
                summary_rows = []
    
                if 'rbf' in analysis_data:
                    for layer in analysis_data['rbf']['layers']:
                        s = layer['stats']
                        summary_rows.append({
                            '方法': 'RBF',
                            '岩性': layer['layer_name'],
                            '层位': layer['part_name'],
                            '控制点数': s.get('n_points'),
                            '最小值(m)': s.get('min'),
                            '最大值(m)': s.get('max'),
                            '均值(m)': s.get('mean'),
                            '标准差(m)': s.get('std'),
                            '平均方差': ''
                        })
    
                if 'kriging' in analysis_data:
                    for layer in analysis_data['kriging']['layers']:
                        s = layer['stats']
                        summary_rows.append({
                            '方法': '克里金',
                            '岩性': layer['layer_name'],
                            '层位': layer['part_name'],
                            '控制点数': s.get('n_points'),
                            '最小值(m)': s.get('kriging_min'),
                            '最大值(m)': s.get('kriging_max'),
                            '均值(m)': s.get('kriging_mean'),
                            '标准差(m)': s.get('kriging_std'),
                            '平均方差': s.get('variance_mean')
                        })
    
                if 'csv' in formats and summary_rows:
                    df = pd.DataFrame(summary_rows)
                    csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
                    zf.writestr(f'00_统计汇总_{timestamp}.csv', csv_bytes)
    
                if 'excel' in formats and summary_rows:
                    excel_buffer = BytesIO()
                    df = pd.DataFrame(summary_rows)
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, sheet_name='统计汇总', index=False)
                    zf.writestr(f'00_统计汇总_{timestamp}.xlsx', excel_buffer.getvalue())
    
                # 2. 按岩性导出各层数据
                all_layers = set()
                if 'rbf' in analysis_data:
                    for layer in analysis_data['rbf']['layers']:
                        all_layers.add(layer['layer_name'])
                if 'kriging' in analysis_data:
                    for layer in analysis_data['kriging']['layers']:
                        all_layers.add(layer['layer_name'])
    
                for idx, lith in enumerate(sorted(all_layers), 1):
                    folder = f'{idx:02d}_{lith}/'
    
                    # RBF 数据
                    if 'rbf' in analysis_data:
                        for layer in analysis_data['rbf']['layers']:
                            if layer['layer_name'] != lith:
                                continue
                            part = layer['part_name']
    
                            if layer.get('control_points'):
                                cp_df = pd.DataFrame(layer['control_points'],
                                                      columns=['X', 'Y', 'Z'])
                                csv_bytes = cp_df.to_csv(index=False).encode('utf-8-sig')
                                zf.writestr(f'{folder}RBF_{part}_控制点.csv', csv_bytes)
    
                            if layer.get('z_pred') and layer.get('grid_x'):
                                grid_x = layer['grid_x']
                                grid_y = layer['grid_y']
                                z_pred = layer['z_pred']
                                gx, gy = np.meshgrid(grid_x, grid_y)
                                grid_df = pd.DataFrame({
                                    'X': gx.ravel(),
                                    'Y': gy.ravel(),
                                    'Z_RBF': z_pred
                                })
                                csv_bytes = grid_df.to_csv(index=False).encode('utf-8-sig')
                                zf.writestr(f'{folder}RBF_{part}_网格.csv', csv_bytes)
    
                    # 克里金数据
                    if 'kriging' in analysis_data:
                        for layer in analysis_data['kriging']['layers']:
                            if layer['layer_name'] != lith:
                                continue
                            part = layer['part_name']
    
                            if layer.get('control_points'):
                                cp_df = pd.DataFrame(layer['control_points'],
                                                      columns=['X', 'Y', 'Z'])
                                csv_bytes = cp_df.to_csv(index=False).encode('utf-8-sig')
                                zf.writestr(f'{folder}克里金_{part}_控制点.csv', csv_bytes)
    
                            if layer.get('z_kriging') and layer.get('grid_x'):
                                grid_x = layer['grid_x']
                                grid_y = layer['grid_y']
                                z_kriging = layer['z_kriging']
                                z_var = layer.get('z_variance', [])
                                gx, gy = np.meshgrid(grid_x, grid_y)
                                grid_df = pd.DataFrame({
                                    'X': gx.ravel(),
                                    'Y': gy.ravel(),
                                    'Z_Kriging': z_kriging,
                                    'Variance': z_var if z_var else [None] * len(z_kriging)
                                })
                                csv_bytes = grid_df.to_csv(index=False).encode('utf-8-sig')
                                zf.writestr(f'{folder}克里金_{part}_网格.csv', csv_bytes)
    
            zip_buffer.seek(0)
    
            return send_file(
                zip_buffer,
                as_attachment=True,
                download_name=f'analysis_data_{timestamp}.zip',
                mimetype='application/zip'
            )
    
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    
    @app.route('/api/download_zip', methods=['POST'])
    def download_zip():
        data = request.json
        urls = data.get('urls', [])
        zip_name = data.get('zip_name', 'images.zip')
        if not urls:
            return jsonify({'error': '没有图片可下载'}), 400
    
        try:
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for url in urls:
                    # 从 URL 中提取相对路径（去掉 /outputs/ 前缀）
                    if url.startswith('/outputs/'):
                        relative_path = url[len('/outputs/'):]
                    else:
                        relative_path = url.lstrip('/')
                    local_path = os.path.join(OUTPUT_FOLDER, relative_path)
                    if os.path.exists(local_path):
                        # 保留目录结构，确保子文件夹中的文件能正确打包
                        zf.write(local_path, relative_path)
                        print(f"Added: {relative_path}")
                    else:
                        print(f"File not found: {local_path}")
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                as_attachment=True,
                download_name=zip_name,
                mimetype='application/zip'
            )
        except Exception as e:
            print(f"Error creating zip: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    pass  # register_routes ends here
