# app.py
# 主应用入口

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os
from io import BytesIO
import uuid
from datetime import datetime
import threading
import time
import webbrowser
import pandas as pd
import zipfile
from config import *
from processors import *
from collections import defaultdict


app = Flask(__name__, template_folder='.')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


# 日志存储
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
        # 限制大小
        if len(log_storage[session_id]) > MAX_LOG_ENTRIES:
            log_storage[session_id] = log_storage[session_id][-MAX_LOG_ENTRIES:]

def log_and_print(session_id, msg, msg_type='info'):
    """同时打印到终端并记录到日志存储"""
    print(msg)
    add_log(session_id, msg, msg_type)

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
    return render_template('index.html',
                           zj_key=ZJ_TIANDITU_KEY,
                           zj_host=ZJ_TIANDITU_HOST)    

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
    """输出文件服务"""
    return send_from_directory(OUTPUT_FOLDER, filename)


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
    
    # 生成唯一会话ID
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_FOLDER, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # 保存文件
    file_path = os.path.join(session_dir, file.filename)
    file.save(file_path)
    
    return jsonify({
        'session_id': session_id,
        'filename': file.filename,
        'path': file_path
    })


@app.route('/api/template', methods=['GET'])
def download_template():
    """下载Excel模板"""
    template_path = generate_template()
    return send_file(template_path, as_attachment=True, 
                     download_name='钻孔数据模板.xlsx')


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
    
    try:
        loc_df = pd.read_excel(file_path, sheet_name='定位表')
        survey_df = pd.read_excel(file_path, sheet_name='测斜表')
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')
        
        # 直接使用 OUTPUT_FOLDER，不创建 session_id 子目录
        base_name = f'drill_views_{datetime.now().strftime("%y%m%d%H%M")}'
        output_dir = OUTPUT_FOLDER  # 直接使用输出根目录
        os.makedirs(output_dir, exist_ok=True)
        
        views = generate_drill_views(loc_df, survey_df, litho_df, output_dir, base_name)
        
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

    try:
        # ========== 1. 读取数据 ==========
        log_and_print(session_id, "正在读取数据...")
        loc_df = pd.read_excel(file_path, sheet_name='定位表')
        survey_df = pd.read_excel(file_path, sheet_name='测斜表')
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')

        log_and_print(session_id, f"定位表: {len(loc_df)} 行, 测斜表: {len(survey_df)} 行, 岩性表: {len(litho_df)} 行")

        # ========== 2. 构建地质体（仅一次，坐标归一化 + 过滤） ==========
        log_and_print(session_id, "正在构建地质体模型...")
        bodies, volume_data = build_geological_bodies_with_volume_v2(
            loc_df, litho_df, survey_df, n_layers=N_LAYERS
        )

        if not bodies or not volume_data:
            log_and_print(session_id, "!!! 未生成任何地质体，请检查数据")
            return jsonify({'error': '未生成任何地质体，请检查数据'}), 500

        log_and_print(session_id, f"==> 成功构建 {len(volume_data)} 个地质体")

        # ========== 3. 按 order 排序视角，确保与提示词编号一致 ==========
        view_configs = sorted(VIEW_CONFIGS, key=lambda v: v.get('order', 0))

        # ========== 4. 输出目录 ==========
        base_name = f'model_{datetime.now().strftime("%y%m%d%H%M")}'
        output_dir = OUTPUT_FOLDER
        os.makedirs(output_dir, exist_ok=True)

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
                    view, output_dir, base_name, labeled=True
                )
                results['labeled'].append({
                    'order': order,
                    'name': view['name'],
                    'label': view_label,
                    'user_tip': view.get('user_tip', ''),
                    'path': labeled_path,
                    'url': f'/outputs/{os.path.basename(labeled_path)}'
                })
                log_and_print(session_id, f"  ==> 标注图已保存: {os.path.basename(labeled_path)}")
            except Exception as e:
                log_and_print(session_id, f"!!! 图{order} 标注图生成失败: {str(e)}")
                import traceback
                traceback.print_exc()

            # ----- 无标注图 -----
            try:
                unlabeled_path = draw_single_model_view(
                    volume_data, loc_df, survey_df, litho_df,
                    view, output_dir, base_name, labeled=False
                )
                results['unlabeled'].append({
                    'order': order,
                    'name': view['name'],
                    'label': view_label,
                    'user_tip': view.get('user_tip', ''),
                    'path': unlabeled_path,
                    'url': f'/outputs/{os.path.basename(unlabeled_path)}'
                })
                log_and_print(session_id, f"  ==> 无标注图已保存: {os.path.basename(unlabeled_path)}")
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
        log_and_print(session_id, "==> 建模示意图生成完成")

        # ========== 8. 返回结果 ==========
        return jsonify({
            'success': True,
            'labeled_views': results['labeled'],
            'unlabeled_views': results['unlabeled'],
            'session_id': session_id,
            'color_map': color_map
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
    
    if not session_id:
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        # ========== 按 AI_REFERENCE_ORDERS 选取参考图 ==========
        image_paths = []
        for order in AI_REFERENCE_IMGS:
            # 找到对应 order 的视图
            view = next((v for v in VIEW_CONFIGS if v.get('order') == order), None)
            if not view:
                log_and_print(session_id, f"!!! 未找到 order={order} 的视图配置")
                continue
            
            order_prefix = f'{order:02d}_'
            pattern_suffix = f'unlabeled_{order_prefix}{view["name"]}.png'
            
            found = False
            # 搜索 outputs 目录下所有可能的位置
            for root, dirs, files in os.walk(OUTPUT_FOLDER):
                for filename in files:
                    if filename.endswith(pattern_suffix):
                        full_path = os.path.join(root, filename)
                        image_paths.append(full_path)
                        log_and_print(session_id, f"==> 图{order} ({view['label']}): {filename}")
                        found = True
                        break
                if found:
                    break
            
            if not found:
                log_and_print(session_id, f"!!! 未找到 图{order} 对应的图片: {pattern_suffix}")
        
        if len(image_paths) < 3:
            return jsonify({
                'error': f'需要3张参考图，当前只找到 {len(image_paths)} 张。请先生成建模示意图。'
            }), 400
        
        log_and_print(session_id, f"==> 使用参考图: {[os.path.basename(p) for p in image_paths]}")
        log_and_print(session_id, f"==> 颜色映射: {color_map}")
        
        # 调用Qwen API
        image_urls, error = call_qwen_api_for_modeling(image_paths, color_map)
        
        if error:
            return jsonify({'error': error}), 500
        
        # 下载所有图片到本地
        import requests
        saved_paths = []
        for idx, img_url in enumerate(image_urls, 1):
            local_filename = f'ai_model_result_{datetime.now().strftime("%y%m%d%H%M%S")}_{idx}.png'
            local_path = os.path.join(OUTPUT_FOLDER, local_filename)
            try:
                resp = requests.get(img_url, timeout=30)
                if resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(resp.content)
                    saved_paths.append({
                        'local_path': local_path,
                        'url': f'/outputs/{local_filename}',
                        'index': idx
                    })
                    log_and_print(session_id, f"==> AI模型图 {idx} 已保存")
                else:
                    log_and_print(session_id, f"!!! 下载AI模型图 {idx} 失败: HTTP {resp.status_code}")
            except Exception as e:
                log_and_print(session_id, f"!!! 下载AI模型图 {idx} 失败: {e}")
        
        if not saved_paths:
            return jsonify({'error': '所有AI模型图下载失败'}), 500
        
        return jsonify({
            'success': True,
            'image_urls': [p['url'] for p in saved_paths],
            'reference_images': [os.path.basename(p) for p in image_paths],
            'count': len(saved_paths)
        })
        
    except Exception as e:
        log_and_print(session_id, f"!!! AI建模失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/interactive_model', methods=['POST'])
def interactive_model_api():
    """生成交互式3D模型"""
    data = request.json
    session_id = data.get('session_id')
    file_path = data.get('path')
    
    if not session_id or not file_path:
        return jsonify({'error': '缺少必要参数'}), 400
    
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 400
    
    try:
        loc_df = pd.read_excel(file_path, sheet_name='定位表')
        survey_df = pd.read_excel(file_path, sheet_name='测斜表')
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')
        
        base_name = f'interactive_{datetime.now().strftime("%y%m%d%H%M")}'
        output_dir = OUTPUT_FOLDER  # 直接使用输出根目录
        os.makedirs(output_dir, exist_ok=True)
        
        html_path = generate_interactive_model(
            loc_df, survey_df, litho_df, output_dir, base_name)
        
        if not html_path:
            log_and_print(session_id, '!!! 无法生成交互式模型')
            return jsonify({'error': '无法生成交互式模型'}), 500
        
        return jsonify({
            'success': True,
            'html_url': f'/outputs/{os.path.basename(html_path)}',
            'session_id': session_id
        })
        
    except Exception as e:
        log_and_print(session_id, f"!!! 生成交互式模型失败: {str(e)}")
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

# ==================== 启动 ====================
def open_browser():
    """自动打开浏览器"""
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{PORT}')


if __name__ == '__main__':
    print('======================================================================')
    print('  地质体建模 Web 应用')
    print('======================================================================')
    print(f'  服务地址: http://127.0.0.1:{PORT}')
    print(f'  上传目录: {UPLOAD_FOLDER}')
    print(f'  输出目录: {OUTPUT_FOLDER}')
    print('======================================================================')
    
    # 自动打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()
    
    app.run(host=HOST, port=PORT, debug=DEBUG)