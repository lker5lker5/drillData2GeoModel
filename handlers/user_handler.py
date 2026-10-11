"""
用户操作路由：建模示意图、AI建模、多视角纹理升级。
使用 register_routes(app) 模式注册所有路由。
"""
from flask import request, jsonify
from datetime import datetime
from .app_utils import *
from config import *
from .processors import *

def register_routes(app):
    @app.route('/api/generate_drill_views', methods=['POST'])
    def generate_drill_views_api():
        """生成钻孔示意图"""
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        try:
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            base_name = f'drill_views_{datetime.now().strftime("%y%m%d%H%M")}'
            output_dir = get_session_output_dir(session_id)
    
            views = generate_drill_views(loc_df, survey_df, litho_df, output_dir, base_name)
    
            # 修正 URL 为 session 子目录路径
            for v in views:
                if 'url' in v and v['url'].startswith('/outputs/'):
                    fname = v['url'][len('/outputs/'):]
                    v['url'] = f'/outputs/{session_id}/{fname}'
    
            return jsonify({
                'success': True,
                'views': views,
                'base_name': base_name,
                'session_id': session_id
            })
    
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    
    @app.route('/api/generate_model', methods=['POST'])
    def generate_model_api():
        """生成3D建模示意图（多视角，标注版 + 无标注版）"""
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        try:
            # ========== 读取用户参数 ==========
            from .params_manager import load_session_params, compute_params_hash
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
    
            rbf_function = user_params.get('RBF_FUNCTION', RBF_FUNCTION)
            rbf_smooth = user_params.get('RBF_SMOOTH', RBF_SMOOTH)
            grid_resolution = user_params.get('GRID_RESOLUTION', GRID_RESOLUTION)
            n_layers = user_params.get('N_LAYERS', N_LAYERS)
            drill_style = user_params.get('DRILL_STYLE', DRILL_STYLE)
            drill_radius = user_params.get('DRILL_RADIUS', DRILL_RADIUS)
            # 读取插值方法
            interpolation_method = user_params.get('INTERPOLATION_METHOD', INTERPOLATION_METHOD)
            kriging_variogram = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            log_and_print(session_id, f"==> 用户参数: 方法={interpolation_method}, RBF={rbf_function}, 平滑度={rbf_smooth}, 克里金变异函数={kriging_variogram}, 网格={grid_resolution}, 层数={n_layers}, 钻孔样式={drill_style}, 半径={drill_radius}")
            # =============================
    
            # ========== 缓存查询 ==========
            from .cache_manager import compute_file_hash, get_cached_result, save_cached_result
            from config import CACHE_ENABLED
    
            input_hash = None
            if CACHE_ENABLED:
                input_hash = compute_file_hash(file_path)
                # 缓存键包含 method 标识，确保不同插值方法的缓存不冲突
                cache_model_key = 'model' + (f'_{interpolation_method}' if interpolation_method != 'rbf' else '')
                cached = get_cached_result(session_id, cache_model_key, input_hash, params_hash)
                if cached:
                    log_and_print(session_id, "==> 命中缓存，直接返回建模结果")
                    # 修正缓存的 URL 路径（替换旧 session_id 为新 session_id）
                    result = cached['result']
                    for key in ['labeled_views', 'unlabeled_views']:
                        for item in result.get(key, []):
                            if 'url' in item and item['url'].startswith('/outputs/'):
                                # URL 格式: /outputs/{old_session_id}/filename.png
                                # 提取 filename 部分并替换 session_id
                                parts = item['url'].split('/')
                                if len(parts) >= 4:
                                    parts[2] = session_id  # 替换旧 session_id
                                    item['url'] = '/'.join(parts)
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **result
                    })
            # =============================
    
            # ========== 1. 读取数据 ==========
            log_and_print(session_id, "正在读取数据...")
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            log_and_print(session_id, f"定位表: {len(loc_df)} 行, 测斜表: {len(survey_df)} 行, 岩性表: {len(litho_df)} 行")
    
            # ========== 2. 构建地质体（仅一次，坐标归一化 + 过滤） ==========
            log_and_print(session_id, "正在构建地质体模型...")
            bodies, volume_data = build_geological_bodies_with_volume_v2(
                loc_df, litho_df, survey_df,
                n_layers=n_layers,
                rbf_function=rbf_function,
                rbf_smooth=rbf_smooth,
                grid_resolution=grid_resolution,
                session_id=session_id,
                method=interpolation_method,
                kriging_variogram=kriging_variogram
            )
    
            if not bodies or not volume_data:
                log_and_print(session_id, "!!! 未生成任何地质体，请检查数据")
                return jsonify({'error': '未生成任何地质体，请检查数据'}), 500
    
            log_and_print(session_id, f"==> 成功构建 {len(volume_data)} 个地质体")
    
            # ========== 3. 按 order 排序视角，确保与提示词编号一致 ==========
            view_configs = sorted(VIEW_CONFIGS, key=lambda v: v.get('order', 0))
    
            # ========== 4. 输出目录 ==========
            base_name = f'model_{datetime.now().strftime("%y%m%d%H%M")}'
            output_dir = get_session_output_dir(session_id)
    
            # ========== 5. 循环生成每个视角的标注图和无标注图 ==========
            results = {'labeled': [], 'unlabeled': []}
    
            for view in view_configs:
                order = view.get('order', 0)
                view_label = view.get('label', '')
                log_and_print(session_id, f"生成 图{order} - {view_label}...")
    
                # ----- 标注图 -----
                try:
                    labeled_path = draw_single_model_view(
                        volume_data, loc_df, survey_df, litho_df,
                        view, output_dir, base_name, labeled=True,
                        drill_style=drill_style, drill_radius=drill_radius
                    )
                    results['labeled'].append({
                        'order': order,
                        'name': view['name'],
                        'label': view_label,
                        'user_tip': view.get('user_tip', ''),
                        'path': labeled_path,
                        'url': f'/outputs/{session_id}/{os.path.basename(labeled_path)}'
                    })
                    log_and_print(session_id, f"  ==> 标注图已保存: {labeled_path} -> {f'/outputs/{session_id}/{os.path.basename(labeled_path)}'}")
                except Exception as e:
                    log_and_print(session_id, f"!!! 图{order} 标注图生成失败: {str(e)}")
                    import traceback
                    traceback.print_exc()
    
                # ----- 无标注图 -----
                try:
                    unlabeled_path = draw_single_model_view(
                        volume_data, loc_df, survey_df, litho_df,
                        view, output_dir, base_name, labeled=False,
                        drill_style=drill_style, drill_radius=drill_radius
                    )
                    results['unlabeled'].append({
                        'order': order,
                        'name': view['name'],
                        'label': view_label,
                        'user_tip': view.get('user_tip', ''),
                        'path': unlabeled_path,
                        'url': f'/outputs/{session_id}/{os.path.basename(unlabeled_path)}'
                    })
                    log_and_print(session_id, f"  ==> 无标注图已保存: {unlabeled_path} -> {f'/outputs/{session_id}/{os.path.basename(unlabeled_path)}'}")
                except Exception as e:
                    log_and_print(session_id, f"!!! 图{order} 无标注图生成失败: {str(e)}")
                    import traceback
                    traceback.print_exc()
    
            # ========== 6. 检查是否有任何图片生成成功 ==========
            if not results['labeled'] and not results['unlabeled']:
                log_and_print(session_id, "!!! 所有视角均生成失败")
                return jsonify({'error': '所有视角生成失败，请检查数据'}), 500
    
            # ========== 7. 获取颜色映射（用于后续 AI 建模） ==========
            try:
                color_map = get_color_map_from_dataframe(litho_df)
            except Exception as e:
                log_and_print(session_id, f"!!! 颜色映射提取失败: {str(e)}")
                color_map = {}
    
            # 过滤无效颜色映射
            filtered_color_map = {}
            for color, names in color_map.items():
                if color and names and color.lower() not in ['nan', 'none', '']:
                    filtered_color_map[color] = names
            color_map = filtered_color_map
    
            log_and_print(session_id, f"==> 最终颜色映射: {len(color_map)} 项")
            # 验证文件确实存在
            for item in results['labeled'] + results['unlabeled']:
                if os.path.exists(item['path']):
                    log_and_print(session_id, f"  ✓ 文件存在: {item['path']}")
                else:
                    log_and_print(session_id, f"  ✗ 文件不存在: {item['path']}")
            log_and_print(session_id, "==> 建模示意图生成完成")
    
            # ========== 8. 保存缓存 ==========
            result_data = {
                'labeled_views': results['labeled'],
                'unlabeled_views': results['unlabeled'],
                'color_map': color_map,
                'default_selected_views': AI_DEFAULT_REFERENCE_VIEWS
            }
    
            if CACHE_ENABLED and input_hash:
                save_cached_result(session_id, cache_model_key, input_hash, result_data, output_dir, params_hash)
                log_and_print(session_id, "==> 已保存建模结果到缓存")
            # =============================
    
            # ========== 9. 返回结果 ==========
            return jsonify({
                'success': True,
                'from_cache': False,
                **result_data
            })
    
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            # 打印完整堆栈到终端
            print("=" * 70)
            print("!!! generate_model_api 异常:")
            print(error_detail)
            print("=" * 70)
            # 记录到日志系统
            try:
                log_and_print(session_id, f"!!! 生成模型失败: {str(e)}")
            except:
                pass
            # 返回错误信息（开发阶段返回 detail，生产环境可移除）
            return jsonify({
                'error': str(e),
                'detail': error_detail
            }), 500
    
    
    
    @app.route('/api/ai_modeling', methods=['POST'])
    def ai_modeling_api():
        """AI建模 - 使用3张参考图生成AI建模图"""
        data = request.json
        session_id = data.get('session_id')
        color_map = data.get('color_map', {})
        file_path = data.get('file_path')  # 用于缓存的文件路径
        selected_views = data.get('selected_views')  # 用户选择的视图 name 列表
    
        if not session_id:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not selected_views or len(selected_views) != 3:
            return jsonify({'error': '需要恰好选择3个视角作为参考图'}), 400
    
        update_session_activity(session_id)
    
        try:
            # ========== 读取用户参数 ==========
            from .params_manager import load_session_params, compute_params_hash
            user_params = load_session_params(session_id)
            params_hash = compute_params_hash(user_params)
            # =============================
    
            # ========== 缓存查询 ==========
            from .cache_manager import compute_file_hash, get_cached_result, save_cached_result
            from config import CACHE_ENABLED
    
            input_hash = None
            if CACHE_ENABLED and file_path:
                input_hash = compute_file_hash(file_path)
                cached = get_cached_result(session_id, 'ai_model', input_hash, params_hash)
                if cached:
                    log_and_print(session_id, "==> 命中缓存，直接返回 AI 建模结果")
                    return jsonify({
                        'success': True,
                        'from_cache': True,
                        **cached['result']
                    })
            # =============================
    
            output_dir = get_session_output_dir(session_id)
    
            # ========== 按 selected_views 选取参考图 ==========
            image_paths = []
            view_metas = []
            for view_name in selected_views:
                # 找到对应 name 的视图配置
                view = next((v for v in VIEW_CONFIGS if v.get('name') == view_name), None)
                if not view:
                    log_and_print(session_id, f"!!! 未找到 view_name={view_name} 的视图配置")
                    continue
    
                # 搜索 unlabeled 图（不再依赖 order 前缀）
                pattern_suffix = f'unlabeled_'
                found = False
                # 搜索 session 输出目录：同时匹配 view name 和 pattern
                if os.path.exists(output_dir):
                    for filename in sorted(os.listdir(output_dir)):
                        if view['name'] in filename and 'unlabeled' in filename and filename.endswith('.png'):
                            full_path = os.path.join(output_dir, filename)
                            image_paths.append(full_path)
                            view_metas.append({
                                'name': view['name'],
                                'label': view['label'],
                                'user_tip': view.get('user_tip', '')
                            })
                            log_and_print(session_id, f"==> {view['label']} ({view['name']}): {filename}")
                            found = True
                            break
                if not found:
                    log_and_print(session_id, f"!!! 未找到 {view['label']} 对应的 unlabeled 图片")
    
            if len(image_paths) < 3:
                return jsonify({
                    'error': f'需要3张参考图，当前只找到 {len(image_paths)} 张。请先生成建模示意图。'
                }), 400
    
            log_and_print(session_id, f"==> 使用参考图: {[os.path.basename(p) for p in image_paths]}")
            log_and_print(session_id, f"==> 颜色映射: {color_map}")
    
            # 调用Qwen API（传入 view_metas 用于构建动态 prompt）
            image_urls, error = call_qwen_api_for_modeling(image_paths, view_metas, color_map)
    
            if error:
                return jsonify({'error': error}), 500
    
            # 下载所有图片到本地
            import requests
            saved_paths = []
            for idx, img_url in enumerate(image_urls, 1):
                local_filename = f'ai_model_result_{datetime.now().strftime("%y%m%d%H%M%S")}_{idx}.png'
                local_path = os.path.join(output_dir, local_filename)
                try:
                    resp = requests.get(img_url, timeout=30)
                    if resp.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
                        saved_paths.append({
                            'local_path': local_path,
                            'path': local_path,
                            'url': f'/outputs/{session_id}/{local_filename}',
                            'index': idx
                        })
                        log_and_print(session_id, f"==> AI模型图 {idx} 已保存")
                    else:
                        log_and_print(session_id, f"!!! 下载AI模型图 {idx} 失败: HTTP {resp.status_code}")
                except Exception as e:
                    log_and_print(session_id, f"!!! 下载AI模型图 {idx} 失败: {e}")
    
            if not saved_paths:
                return jsonify({'error': '所有AI模型图下载失败'}), 500
    
            # ========== 自动评分 ==========
            from .scoring import rank_ai_candidates
    
            # 找参考图：selected_views 中的第一个视图的 unlabeled 图
            ref_image_path = None
            first_view_name = selected_views[0] if selected_views else 'main_view'
            if os.path.exists(output_dir):
                for f in sorted(os.listdir(output_dir)):
                    if 'unlabeled' in f and first_view_name in f and f.endswith('.png'):
                        ref_image_path = os.path.join(output_dir, f)
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
    
            # ========== 保存缓存 ==========
            if CACHE_ENABLED and input_hash:
                save_cached_result(session_id, 'ai_model', input_hash, result_data, output_dir, params_hash)
            # =============================
    
            return jsonify({
                'success': True,
                'from_cache': False,
                **result_data
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! AI建模失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    
    @app.route('/api/interactive_model', methods=['POST'])
    def interactive_model_api():
        """生成交互式3D模型（mode=drill_only: 仅钻孔; mode=full: 钻孔+地质体）"""
        data = request.json
        session_id = data.get('session_id')
        file_path = data.get('path')
        mode = data.get('mode', 'drill_only')  # drill_only 或 full
    
        if not session_id or not file_path:
            return jsonify({'error': '缺少必要参数'}), 400
    
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 400
    
        update_session_activity(session_id)
    
        try:
            from .params_manager import load_session_params
    
            user_params = load_session_params(session_id)
            n_layers = user_params.get('N_LAYERS', N_LAYERS)
            rbf_function = user_params.get('RBF_FUNCTION', RBF_FUNCTION)
            rbf_smooth = user_params.get('RBF_SMOOTH', RBF_SMOOTH)
            grid_resolution = user_params.get('GRID_RESOLUTION', GRID_RESOLUTION)
            drill_style = user_params.get('DRILL_STYLE', DRILL_STYLE)
            drill_radius = user_params.get('DRILL_RADIUS', DRILL_RADIUS)
            interpolation_method = user_params.get('INTERPOLATION_METHOD', INTERPOLATION_METHOD)
            kriging_variogram = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            base_name = f'interactive_{datetime.now().strftime("%y%m%d%H%M")}'
            output_dir = get_session_output_dir(session_id)
    
            if mode == 'drill_only':
                # 钻孔专用模式：快速生成，不含地质体
                html_path = generate_drill_model_only(
                    loc_df, survey_df, litho_df, output_dir, base_name,
                    drill_style=drill_style, drill_radius=drill_radius
                )
                log_and_print(session_id, "==> 生成钻孔专用3D模型（不含地质体）")
            else:
                # 完整模式：包含钻孔和地质体（与之前相同）
                html_path = generate_interactive_model(
                    loc_df, survey_df, litho_df, output_dir, base_name,
                    drill_style=drill_style, drill_radius=drill_radius,
                    n_layers=n_layers, rbf_function=rbf_function,
                    rbf_smooth=rbf_smooth, grid_resolution=grid_resolution,
                    method=interpolation_method,
                    kriging_variogram=kriging_variogram
                )
                log_and_print(session_id, "==> 生成完整3D模型（钻孔+地质体）")
    
            if not html_path:
                log_and_print(session_id, '!!! 无法生成交互式模型')
                return jsonify({'error': '无法生成交互式模型'}), 500
    
            return jsonify({
                'success': True,
                'html_url': f'/outputs/{session_id}/{os.path.basename(html_path)}',
                'mode': mode,
                'session_id': session_id
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! 生成交互式模型失败: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    
    
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
    
        update_session_activity(session_id)
    
        try:
            from config import MULTIVIEW_VIEW_ORDERS, VIEW_CONFIGS
            from .processors import call_qwen_api_for_multiview, add_annotations_to_ai_image
    
            output_dir = get_session_output_dir(session_id)
    
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
                if os.path.exists(output_dir):
                    for f in sorted(os.listdir(output_dir)):
                        if pattern in f and f.endswith('.png') and 'ai_' not in f and 'multiview' not in f:
                            py_image_path = os.path.join(output_dir, f)
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
                            'url': f'/outputs/{session_id}/{os.path.basename(py_image_path)}',
                            'has_ai': False
                        })
                        continue
    
                    # 下载 AI 图
                    ai_url = ai_urls[0]
                    local_filename = f'multiview_ai_{order:02d}_{view["name"]}.png'
                    local_path = os.path.join(output_dir, local_filename)
    
                    import requests
                    resp = requests.get(ai_url, timeout=60)
                    if resp.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
    
                        images.append({
                            'view_name': view['name'],
                            'view_label': view['label'],
                            'order': order,
                            'url': f'/outputs/{session_id}/{local_filename}',
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
                            'url': f'/outputs/{session_id}/{os.path.basename(py_image_path)}',
                            'has_ai': False
                        })
                except Exception as e:
                    log_and_print(session_id, f"!!! 图{order} 异常: {e}")
                    images.append({
                        'view_name': view['name'],
                        'view_label': view['label'],
                        'order': order,
                        'url': f'/outputs/{session_id}/{os.path.basename(py_image_path)}',
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
            # 默认 Z 轴范围
            z_min, z_max = -300, 400
            # 尝试从缓存获取更精确的 Z 轴范围
            try:
                from .cache_manager import get_cached_result
                cached = get_cached_result(session_id, 'model', None)
            except Exception:
                pass
    
            annotated_images = []
            for img in images:
                if img.get('has_ai'):
                    annotated_filename = f'annotated_{os.path.basename(img["url"])}'
                    annotated_path = os.path.join(output_dir, annotated_filename)
                    result_path = add_annotations_to_ai_image(
                        img['path'], annotated_path, z_min, z_max
                    )
                    annotated_images.append({
                        **img,
                        'annotated_url': f'/outputs/{session_id}/{annotated_filename}' if result_path else img['url']
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
    
    
    
    @app.route('/api/multiview_texture_upgrade', methods=['POST'])
    def multiview_texture_upgrade_api():
        """
        多视角纹理升级：
        1. Python 生成 3 张带黑色描边的几何图
        2. 每张独立调用 AI 升级纹理
        3. 遮罩合成（几何由 Python 100% 控制，AI 只贡献纹理）
        4. 色调统一
        """
        data = request.json
        session_id = data.get('session_id')
        view_count = data.get('view_count', 3)
        color_map = data.get('color_map', {})
        file_path = data.get('file_path')  # 用于读取原始数据重建 volume_data
    
        if not session_id:
            return jsonify({'error': '缺少 session_id'}), 400
    
        if not color_map:
            return jsonify({'error': '缺少颜色映射，请先生成建模图'}), 400
    
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': '数据文件不存在，请先上传'}), 400
    
        try:
            update_session_activity(session_id)
            output_dir = get_session_output_dir(session_id)
            from config import MULTIVIEW_VIEW_ORDERS, VIEW_CONFIGS
            from .processors import (
                plot_geometry_with_black_edges,
                generate_ai_texture_for_single_view,
                composite_ai_texture_with_geometry,
                unify_multiview_color_tones
            )
    
            # ========== 读取数据并构建地质体 ==========
            log_and_print(session_id, "正在读取数据并构建地质体模型...")
            loc_df = pd.read_excel(file_path, sheet_name='定位表')
            survey_df = pd.read_excel(file_path, sheet_name='测斜表')
            litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    
            from .params_manager import load_session_params
            user_params = load_session_params(session_id)
            n_layers = user_params.get('N_LAYERS', N_LAYERS)
            rbf_function = user_params.get('RBF_FUNCTION', RBF_FUNCTION)
            rbf_smooth = user_params.get('RBF_SMOOTH', RBF_SMOOTH)
            grid_resolution = user_params.get('GRID_RESOLUTION', GRID_RESOLUTION)
            drill_style = user_params.get('DRILL_STYLE', DRILL_STYLE)
            drill_radius = user_params.get('DRILL_RADIUS', DRILL_RADIUS)
            interpolation_method = user_params.get('INTERPOLATION_METHOD', INTERPOLATION_METHOD)
            kriging_variogram = user_params.get('KRIGING_VARIOGRAM', KRIGING_VARIOGRAM_MODEL)
    
            bodies, volume_data = build_geological_bodies_with_volume_v2(
                loc_df, litho_df, survey_df,
                n_layers=n_layers,
                rbf_function=rbf_function,
                rbf_smooth=rbf_smooth,
                grid_resolution=grid_resolution,
                session_id=session_id,
                method=interpolation_method,
                kriging_variogram=kriging_variogram
            )
    
            if not volume_data:
                return jsonify({'error': '未生成地质体数据'}), 500
    
            log_and_print(session_id, f"==> 成功构建 {len(volume_data)} 个地质体")
    
            # ========== Step 1: 生成几何图（带黑色描边） ==========
            log_and_print(session_id, "==> 生成几何约束图（带黑色描边）...")
            geometry_paths = []  # (order, view, geo_path)
            for order in MULTIVIEW_VIEW_ORDERS[:view_count]:
                view = next((v for v in VIEW_CONFIGS if v.get('order') == order), None)
                if not view:
                    log_and_print(session_id, f"!!! 未找到 order={order} 的视角配置")
                    continue
    
                geo_path = plot_geometry_with_black_edges(
                    volume_data, view, output_dir, f'multiview_tex_{session_id}'
                )
                geometry_paths.append((order, view, geo_path))
                log_and_print(session_id, f"==> 几何图 图{order} 已生成")
    
            if not geometry_paths:
                return jsonify({'error': '所有几何图生成失败'}), 500
    
            # ========== Step 2: 每张独立调用 AI 升级纹理 ==========
            log_and_print(session_id, "==> 开始 AI 纹理升级...")
            import requests as http_requests
            ai_paths = []  # (order, view, geo_path, ai_path)
            success_count = 0
    
            for order, view, geo_path in geometry_paths:
                log_and_print(session_id, f"==> 正在生成 图{order} ({view['label']}) 的 AI 纹理")
    
                ai_url, error = generate_ai_texture_for_single_view(geo_path, color_map)
    
                if error or not ai_url:
                    log_and_print(session_id, f"!!! 图{order} AI 生成失败: {error}")
                    continue
    
                # 下载 AI 图
                local_filename = f'multiview_ai_raw_{order:02d}_{view["name"]}.png'
                local_path = os.path.join(output_dir, local_filename)
    
                resp = http_requests.get(ai_url, timeout=60)
                if resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                    ai_paths.append((order, view, geo_path, local_path))
                    success_count += 1
                    log_and_print(session_id, f"==> 图{order} AI 纹理生成成功")
                else:
                    log_and_print(session_id, f"!!! 图{order} 下载失败: HTTP {resp.status_code}")
    
            if success_count == 0:
                return jsonify({'error': '所有视角 AI 纹理升级均失败，请重试'}), 500
    
            # ========== Step 3: 遮罩合成 ==========
            log_and_print(session_id, "==> 正在进行遮罩合成...")
            composite_paths = []
            for order, view, geo_path, ai_path in ai_paths:
                out_filename = f'multiview_composite_{order:02d}_{view["name"]}.png'
                out_path = os.path.join(output_dir, out_filename)
                composite_ai_texture_with_geometry(geo_path, ai_path, out_path)
                composite_paths.append(out_path)
    
            # ========== Step 4: 色调统一 ==========
            log_and_print(session_id, "==> 正在进行色调统一...")
            unified_paths = unify_multiview_color_tones(composite_paths)
    
            # ========== 组织返回数据 ==========
            images = []
            import time as _time
            _cache_buster = str(int(_time.time()))
            for i, (order, view, _, _) in enumerate(ai_paths):
                unified_path = unified_paths[i]
                if os.path.exists(unified_path) and os.path.getsize(unified_path) > 0:
                    filename = os.path.basename(unified_path)
                    url = f'/outputs/{session_id}/{filename}?t={_cache_buster}'
                    images.append({
                        'view_name': view['name'],
                        'view_label': view['label'],
                        'order': order,
                        'url': url,
                        'has_ai': True
                    })
                    log_and_print(session_id, f"  ✅ [{i}] {filename} ({os.path.getsize(unified_path)} bytes) → {url}")
                else:
                    log_and_print(session_id, f"  ❌ [{i}] 文件不存在或为空: {unified_path}")
    
            log_and_print(session_id, f"==> 多视角纹理升级完成（成功 {success_count}/{len(geometry_paths)}）")
            return jsonify({
                'success': True,
                'images': images,
                'success_count': success_count,
                'total_count': len(geometry_paths)
            })
    
        except Exception as e:
            log_and_print(session_id, f"!!! 多视角纹理升级失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
    
    pass  # register_routes ends here
