# app.py
# 主应用入口

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os
from io import BytesIO
import uuid
import json
from datetime import datetime
import shutil
import threading
import time
import webbrowser
import pandas as pd
import numpy as np
import geopandas as gpd
import zipfile
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
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

def clean_dataframe(df):
    """删除全为空值的列和行"""
    df = df.dropna(axis=1, how='all')  # 删除全为空值的列
    df = df.dropna(axis=0, how='all')  # 删除全为空值的行
    return df

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

# 清理日志（可选，在会话完成后调用）
def clear_logs(session_id):
    if session_id in log_storage:
        del log_storage[session_id]

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


# app.py

@app.route('/api/generate_model', methods=['POST'])
def generate_model_api():
    """生成3D建模示意图（多视角）"""
    data = request.json
    session_id = data.get('session_id')
    file_path = data.get('path')
    
    if not session_id or not file_path:
        return jsonify({'error': '缺少必要参数'}), 400
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 400
    
    try:
        # 读取数据
        loc_df = pd.read_excel(file_path, sheet_name='定位表')
        survey_df = pd.read_excel(file_path, sheet_name='测斜表')
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')
        
        base_name = f'model_{datetime.now().strftime("%y%m%d%H%M")}'
        output_dir = OUTPUT_FOLDER
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建地质体（仅一次）
        log_and_print(session_id, "正在构建地质体模型...")
        bodies, volume_data = build_geological_bodies_with_volume_v2(
            loc_df, litho_df, survey_df, n_layers=N_LAYERS
        )
        
        if not bodies or not volume_data:
            return jsonify({'error': '未生成任何地质体，请检查数据'}), 500
        
        # 从 config 中读取视角配置
        view_configs = VIEW_CONFIGS
        
        results = {'labeled': [], 'unlabeled': []}
        
        # for view in view_configs:
        for view in sorted(VIEW_CONFIGS, key=lambda v: v.get('order', 0)):
            log_and_print(session_id, f"生成 {view['label']}...")
            
            # 标注图
            labeled_path = draw_single_model_view(
                volume_data, loc_df, survey_df, litho_df,
                view, output_dir, base_name, labeled=True
            )
            results['labeled'].append({
                'name': view['name'],
                'label': view['label'],
                'user_tip': view.get('user_tip', ''),
                'path': labeled_path,
                'url': f'/outputs/{os.path.basename(labeled_path)}'
            })
            log_and_print(session_id, f"  ==> 标注图已保存")
            
            # 无标注图
            unlabeled_path = draw_single_model_view(
                volume_data, loc_df, survey_df, litho_df,
                view, output_dir, base_name, labeled=False
            )
            results['unlabeled'].append({
                'name': view['name'],
                'label': view['label'],
                'user_tip': view.get('user_tip', ''),
                'path': unlabeled_path,
                'url': f'/outputs/{os.path.basename(unlabeled_path)}'
            })
            log_and_print(session_id, f"  ==> 无标注图已保存")
        
        # 颜色映射
        color_map = get_color_map_from_dataframe(litho_df)
        
        return jsonify({
            'success': True,
            'labeled_views': results['labeled'],
            'unlabeled_views': results['unlabeled'],
            'session_id': session_id,
            'color_map': color_map
        })
        
    except Exception as e:
        log_and_print(session_id, f"!!! 生成模型失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai_modeling', methods=['POST'])
def ai_modeling_api():
    """AI建模 - 使用侧视图和前视图生成4张AI建模图"""
    data = request.json
    session_id = data.get('session_id')
    color_map = data.get('color_map', {})
    
    if not session_id:
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        # 只使用侧视图和前视图
        target_views = ['side_view', 'front_view']
        image_paths = []
        
        for view_name in target_views:
            pattern = f'unlabeled_{view_name}'
            found = False
            for filename in os.listdir(OUTPUT_FOLDER):
                if pattern in filename and filename.endswith('.png'):
                    path = os.path.join(OUTPUT_FOLDER, filename)
                    image_paths.append(path)
                    found = True
                    log_and_print(session_id, f"==> 找到参考图: {filename}")
                    break
            if not found:
                log_and_print(session_id, f"!!! 未找到 {view_name} 对应的图片")
        
        if len(image_paths) < 2:
            return jsonify({'error': f'未找到足够的参考图（需要侧视图和前视图），当前找到 {len(image_paths)} 张'}), 400
        
        log_and_print(session_id, f"==> 使用参考图: {[os.path.basename(p) for p in image_paths]}")
        log_and_print(session_id, f"==> 颜色映射: {color_map}")
        
        # 调用Qwen API（返回4张图片URL列表）
        image_urls, error = call_qwen_api_for_modeling(image_paths, color_map)
        
        if error:
            return jsonify({'error': error}), 500
        
        # 下载所有图片到本地
        import requests
        saved_paths = []
        for idx, img_url in enumerate(image_urls, 1):
            local_filename = f'ai_model_result_{datetime.now().strftime("%y%m%d%H%M")}_{idx}.png'
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
                    log_and_print(session_id, f"==> AI模型图 {idx} 已保存: {local_path}")
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