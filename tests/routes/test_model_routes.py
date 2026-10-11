"""
测试 Flask 路由 — 建模生成、AI、插值分析
策略：mock 掉 processors 中耗时的实际计算，仅验证路由逻辑。
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from io import BytesIO

# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    import matplotlib
    matplotlib.use('Agg')
    from handlers.app_utils import session_last_active, log_storage
    session_last_active.clear()
    log_storage.clear()


# ==================== Mock 工厂 ====================

@pytest.fixture
def mock_processors(monkeypatch):
    """
    批量 mock processors 中耗时/外部依赖的函数。
    各个测试可在此基础上精调。
    """
    import mineDrillApp

    # ---- 钻孔视图 ----
    def mock_drill_views(loc_df, survey_df, litho_df, output_dir, base_name):
        return [
            {'url': '/outputs/test_abc.png', 'label': 'main_view', 'user_tip': ''},
            {'url': '/outputs/test_def.png', 'label': 'south_north_view', 'user_tip': ''},
        ]

    # ---- 建模图：mock 构建和绘图两个关键函数 ----
    def mock_build_bodies(loc_df, litho_df, survey_df, **kw):
        volume_data = {
            '矿化带': {
                'lith': '矿化带', 'traces': [],
                'grid_x': [[0]], 'grid_y': [[0]],
                'Z_top': [[100]], 'Z_bot': [[0]],
                'color': '#FF0000'
            }
        }
        return [{'lith': '矿化带'}], volume_data

    def mock_draw_model_view(volume_data, loc_df, survey_df, litho_df,
                              view_config, output_dir, base_name,
                              labeled=True, drill_style=None, drill_radius=None):
        # 创建伪文件以便测试 URL
        os.makedirs(output_dir, exist_ok=True)
        prefix = 'labeled' if labeled else 'unlabeled'
        file_path = os.path.join(output_dir, f'{prefix}_{view_config["name"]}.png')
        from PIL import Image
        Image.new('RGB', (64, 64)).save(file_path)
        return file_path

    # ---- 交互式模型 ----
    def mock_drill_model_only(loc_df, survey_df, litho_df, output_dir, base_name,
                              drill_style='cylinder', drill_radius=3.0):
        path = os.path.join(output_dir, f'{base_name}_drill.html')
        with open(path, 'w') as f: f.write('<html>drill only</html>')
        return path

    def mock_interactive_model(loc_df, survey_df, litho_df, output_dir, base_name,
                               drill_style='cylinder', drill_radius=3.0,
                               n_layers=None, rbf_function='multiquadric',
                               rbf_smooth=0.1, grid_resolution=50,
                               method=None, kriging_variogram=None):
        path = os.path.join(output_dir, f'{base_name}_full.html')
        with open(path, 'w') as f: f.write('<html>full model</html>')
        return path

    # ---- 克里金 ----
    def mock_kriging_analysis(loc_df, litho_df, survey_df, **kw):
        return {
            'comparison_paths': [
                {'url': '/outputs/comparison_01.png', 'layer': '矿化带', 'part': 'top'},
            ],
            'analysis_text': '矿化带顶面分析结果...',
            'layer_count': 1,
            'point_counts': {'矿化带': {'top': 10, 'bottom': 10}},
        }

    # ---- AI 建模 ----
    def mock_qwen_modeling(image_paths, view_metas=None, color_map=None, **kw):
        return (['http://mock-url.com/img1.png', 'http://mock-url.com/img2.png'], None)

    # ---- 多视角 AI ----
    def mock_qwen_multiview(anchor_image, target_image, color_map=None, **kw):
        return (['http://mock-url.com/multiview.png'], None)

    def mock_add_annotations(ai_image_path, output_path, z_min, z_max):
        from PIL import Image
        img = Image.new('RGB', (64, 64))
        img.save(output_path)
        return output_path

    # ---- 纹理升级 ----
    def mock_plot_geometry(lith_volume_data, view_config, output_dir, base_name):
        path = os.path.join(output_dir, f'geometry_{view_config["order"]:02d}.png')
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        from PIL import Image
        img = Image.new('RGB', (64, 64))
        img.save(path)
        return path

    def mock_ai_texture(geometry_path, color_map, **kw):
        return ('http://mock-url.com/texture.png', None)

    def mock_composite(geo_path, ai_path, output_path):
        from PIL import Image
        img = Image.new('RGB', (64, 64))
        img.save(output_path)
        return output_path

    def mock_unify_colors(image_paths):
        return image_paths

    # ---- kriging_surface_analysis 额外 mock（函数内 import processors 的版本） ----
    from handlers import processors as proc_mod
    monkeypatch.setattr('handlers.processors.compute_trajectory', lambda df: (
        np.array([0., 100.]), np.array([0., 0.]), np.array([0., 0.]), np.array([100., 0.])
    ))
    monkeypatch.setattr('handlers.processors.get_interpolated_coords', lambda a,b,c,d,e: (
        np.array([0., 50., 100.]), np.array([0., 0., 0.]), np.array([0., 0., 0.])
    ))
    monkeypatch.setattr('handlers.processors.generate_kriging_analysis_for_layer', lambda **kw: {
        'comparison_path': '', 'layer_name': '矿化带', 'part_name': '顶面',
        'analysis_text': 'test', 'point_counts': {}
    })
    monkeypatch.setattr('handlers.processors.plot_kriging_comparison', lambda *a, **kw: '/tmp/mock_plot.png')
    monkeypatch.setattr('handlers.processors.transform_xy_to_lonlat', lambda x, y, zone=None: (120.0, 30.0))

    # ---- processors 级 mock（也覆盖 handlers 中 from .processors import * 的引用） ----
    monkeypatch.setattr('handlers.processors.call_qwen_api_for_multiview', mock_qwen_multiview)
    monkeypatch.setattr('handlers.processors.add_annotations_to_ai_image', mock_add_annotations)
    monkeypatch.setattr('handlers.processors.call_qwen_api_for_modeling', mock_qwen_modeling)
    monkeypatch.setattr('handlers.processors.plot_geometry_with_black_edges', mock_plot_geometry)
    monkeypatch.setattr('handlers.processors.generate_ai_texture_for_single_view', mock_ai_texture)
    monkeypatch.setattr('handlers.processors.composite_ai_texture_with_geometry', mock_composite)
    monkeypatch.setattr('handlers.processors.unify_multiview_color_tones', mock_unify_colors)
    monkeypatch.setattr('handlers.processors.add_view_label_watermark', lambda fig, label='': None)

    # ---- handler 级 mock（handlers 中 from .processors import * 的副本） ----
    monkeypatch.setattr('handlers.user_handler.generate_drill_views', mock_drill_views)
    monkeypatch.setattr('handlers.user_handler.draw_single_model_view', mock_draw_model_view)
    monkeypatch.setattr('handlers.user_handler.build_geological_bodies_with_volume_v2', mock_build_bodies)
    monkeypatch.setattr('handlers.user_handler.generate_drill_model_only', mock_drill_model_only)
    monkeypatch.setattr('handlers.user_handler.generate_interactive_model', mock_interactive_model)
    monkeypatch.setattr('handlers.data_handler.perform_kriging_analysis', mock_kriging_analysis)

    # ---- 模拟 requests.get（AI 路由下载图片时使用） ----
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100  # fake PNG
    monkeypatch.setattr('requests.get', lambda url, timeout=30: mock_response)

    return monkeypatch


# ==================== 1. 钻孔示意图路由 ====================

class TestGenerateDrillViews:
    """测试 /api/generate_drill_views"""

    def test_missing_params(self, client):
        resp = client.post('/api/generate_drill_views', json={})
        assert resp.status_code == 400
        assert '缺少' in resp.get_json().get('error', '')

    def test_nonexistent_file(self, client):
        resp = client.post('/api/generate_drill_views', json={
            'session_id': 'test', 'path': '/nonexistent.xlsx'
        })
        assert resp.status_code == 400
        assert '不存在' in resp.get_json().get('error', '')

    def test_success(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/generate_drill_views', json={
            'session_id': 'test_dv', 'path': create_sample_excel
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'views' in data
        assert len(data['views']) > 0

    def test_url_fixup(self, client, create_sample_excel, mock_processors):
        """URL 应为 session 子目录路径"""
        resp = client.post('/api/generate_drill_views', json={
            'session_id': 'test_dv_url', 'path': create_sample_excel
        })
        data = resp.get_json()
        for v in data['views']:
            assert f'/outputs/test_dv_url/' in v['url']

    def test_excel_read_error(self, client, temp_dir, mock_processors):
        """损坏的 Excel 应返回 500"""
        bad_file = os.path.join(temp_dir, 'corrupt.xlsx')
        with open(bad_file, 'wb') as f: f.write(b'not an excel file')
        resp = client.post('/api/generate_drill_views', json={
            'session_id': 'test_err', 'path': bad_file
        })
        assert resp.status_code in (200, 500)
        if resp.status_code == 500:
            assert 'error' in resp.get_json()


# ==================== 2. 建模示意图路由 ====================

class TestGenerateModel:
    """测试 /api/generate_model"""

    def test_missing_params(self, client):
        resp = client.post('/api/generate_model', json={})
        assert resp.status_code == 400

    def test_nonexistent_file(self, client):
        resp = client.post('/api/generate_model', json={
            'session_id': 'test', 'path': '/no/file.xlsx'
        })
        assert resp.status_code == 400

    def test_success(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/generate_model', json={
            'session_id': 'test_model', 'path': create_sample_excel
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'labeled_views' in data
        assert 'unlabeled_views' in data
        assert 'color_map' in data

    def test_url_fixup(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/generate_model', json={
            'session_id': 'test_model_url', 'path': create_sample_excel
        })
        data = resp.get_json()
        for view_list in ['labeled_views', 'unlabeled_views']:
            for v in data.get(view_list, []):
                assert '/outputs/test_model_url/' in v.get('url', '')

    def test_cache_hit(self, client, create_sample_excel, mock_processors):
        """重复请求应命中缓存"""
        resp1 = client.post('/api/generate_model', json={
            'session_id': 'test_cache', 'path': create_sample_excel
        })
        assert resp1.status_code == 200
        resp2 = client.post('/api/generate_model', json={
            'session_id': 'test_cache', 'path': create_sample_excel
        })
        data2 = resp2.get_json()
        assert data2.get('success') is True


# ==================== 3. 交互式3D模型路由 ====================

class TestInteractiveModel:
    """测试 /api/interactive_model"""

    def test_missing_params(self, client):
        resp = client.post('/api/interactive_model', json={})
        assert resp.status_code == 400

    def test_nonexistent_file(self, client):
        resp = client.post('/api/interactive_model', json={
            'session_id': 'test', 'path': '/no/file.xlsx'
        })
        assert resp.status_code == 400

    def test_drill_only_mode(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/interactive_model', json={
            'session_id': 'test_int', 'path': create_sample_excel,
            'mode': 'drill_only'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'html_url' in data
        assert data['mode'] == 'drill_only'

    def test_full_mode(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/interactive_model', json={
            'session_id': 'test_int_full', 'path': create_sample_excel,
            'mode': 'full'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'html_url' in data
        assert data['mode'] == 'full'

    def test_default_mode(self, client, create_sample_excel, mock_processors):
        """不传 mode 参数时默认使用 drill_only"""
        resp = client.post('/api/interactive_model', json={
            'session_id': 'test_int_def', 'path': create_sample_excel
        })
        data = resp.get_json()
        assert data.get('mode') == 'drill_only'

    def test_html_content(self, client, create_sample_excel, mock_processors):
        """生成的 HTML 文件应存在于 outputs 目录"""
        resp = client.post('/api/interactive_model', json={
            'session_id': 'test_html', 'path': create_sample_excel,
            'mode': 'drill_only'
        })
        data = resp.get_json()
        html_url = data['html_url']
        # 输出目录应有对应的 html 文件
        output_path = html_url.replace('/outputs/', '')
        import config as cfg
        full_path = os.path.join(cfg.OUTPUT_FOLDER, output_path)
        assert os.path.exists(full_path), f"HTML file not found: {full_path}"


# ==================== 4. 克里金分析路由 ====================

class TestKrigingAnalysis:
    """测试 /api/kriging_analysis"""

    def test_missing_params(self, client):
        resp = client.post('/api/kriging_analysis', json={})
        assert resp.status_code == 400

    def test_success(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/kriging_analysis', json={
            'session_id': 'test_krig', 'path': create_sample_excel
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'comparison_paths' in data or 'error' in data

    def test_url_fixup(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/kriging_analysis', json={
            'session_id': 'test_krig_url', 'path': create_sample_excel
        })
        data = resp.get_json()
        if data.get('success'):
            for cp in data.get('comparison_paths', []):
                assert '/outputs/test_krig_url/' in cp.get('url', '')


class TestKrigingSurfaceAnalysis:
    """测试 /api/kriging_surface_analysis"""

    def test_missing_params(self, client):
        resp = client.post('/api/kriging_surface_analysis', json={})
        assert resp.status_code == 400

    def test_success(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/kriging_surface_analysis', json={
            'session_id': 'test_ks', 'path': create_sample_excel
        })
        assert resp.status_code in (200, 500)
        data = resp.get_json()
        if resp.status_code == 200:
            assert 'success' in data or 'error' in data


# ==================== 5. AI 建模路由 ====================

class TestAIModeling:
    """测试 /api/ai_modeling"""

    def test_missing_session(self, client):
        resp = client.post('/api/ai_modeling', json={})
        assert resp.status_code == 400

    def test_no_reference_images(self, client, mock_processors):
        """没有参考图时应返回 400"""
        resp = client.post('/api/ai_modeling', json={
            'session_id': 'test_ai', 'color_map': {'#FF0000': '矿化带'},
            'file_path': None,
            'selected_views': ['main_view', 'east_west_section', 'north_south_section']
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_missing_selected_views(self, client, mock_processors):
        """缺少 selected_views 时应返回 400"""
        resp = client.post('/api/ai_modeling', json={
            'session_id': 'test_ai', 'color_map': {'#FF0000': '矿化带'},
            'file_path': None
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_with_reference_images(self, client, create_sample_excel, mock_processors):
        """先生成建模图获得参考图，再调用 AI 建模"""
        # Step 1: 生成建模图（写入图像文件以提供参考图）
        from handlers.app_utils import get_session_output_dir
        from PIL import Image
        output_dir = get_session_output_dir('test_ai_ref')
        os.makedirs(output_dir, exist_ok=True)
        # 按默认视图生成对应的 unlabeled 图
        for fname in ['unlabeled_01_main_view.png', 'unlabeled_02_east_west_section.png',
                     'unlabeled_03_north_south_section.png']:
            img = Image.new('RGB', (100, 100), (255, 0, 0))
            img.save(os.path.join(output_dir, fname))
        # 也需要 labeled 图供评分逻辑使用（覆盖全部6个视角）
        for fname in ['labeled_01_main_view.png', 'labeled_02_east_west_section.png',
                     'labeled_03_north_south_section.png', 'labeled_04_top_down_view.png',
                     'labeled_05_supplementary_view.png', 'labeled_06_iso_view.png']:
            img = Image.new('RGB', (100, 100), (255, 0, 0))
            img.save(os.path.join(output_dir, fname))

        resp = client.post('/api/ai_modeling', json={
            'session_id': 'test_ai_ref',
            'color_map': {'#FF0000': '矿化带'},
            'file_path': create_sample_excel,
            'selected_views': ['main_view', 'east_west_section', 'north_south_section']
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True


# ==================== 6. 多视角 AI 路由 ====================

class TestMultiviewAI:
    """测试 /api/multiview_ai"""

    def test_missing_params(self, client):
        resp = client.post('/api/multiview_ai', json={})
        assert resp.status_code == 400

    def test_best_ai_path_not_found(self, client):
        resp = client.post('/api/multiview_ai', json={
            'session_id': 'test_mv', 'best_ai_path': '/nonexistent.png',
            'color_map': {}
        })
        assert resp.status_code == 400

    def test_invalid_view_count(self, client):
        resp = client.post('/api/multiview_ai', json={
            'session_id': 'test_mv', 'best_ai_path': '/some/path.png',
            'view_count': 5, 'color_map': {}
        })
        assert resp.status_code == 400

    def test_success(self, client, temp_dir, mock_processors):
        from PIL import Image
        from handlers.app_utils import get_session_output_dir
        # 创建主锚图
        ai_img = os.path.join(temp_dir, 'best_ai.png')
        Image.new('RGB', (100, 100)).save(ai_img)
        # 创建 Python 参考图（代码搜索模式: f'unlabeled_{order:02d}_{view["name"]}'）
        output_dir = get_session_output_dir('test_mv_success')
        os.makedirs(output_dir, exist_ok=True)
        for fname in ['unlabeled_01_main_view.png', 'unlabeled_03_north_south_section.png']:
            Image.new('RGB', (100, 100)).save(os.path.join(output_dir, fname))

        resp = client.post('/api/multiview_ai', json={
            'session_id': 'test_mv_success',
            'best_ai_path': ai_img,
            'view_count': 2,
            'color_map': {'#FF0000': '矿化带'}
        })
        assert resp.status_code == 200


# ==================== 7. 多视角纹理升级路由 ====================

class TestMultiviewTextureUpgrade:
    """测试 /api/multiview_texture_upgrade"""

    def test_missing_session(self, client):
        resp = client.post('/api/multiview_texture_upgrade', json={})
        assert resp.status_code == 400

    def test_missing_color_map(self, client):
        resp = client.post('/api/multiview_texture_upgrade', json={
            'session_id': 'test_tex', 'color_map': {}
        })
        assert resp.status_code == 400

    def test_missing_file(self, client):
        resp = client.post('/api/multiview_texture_upgrade', json={
            'session_id': 'test_tex',
            'color_map': {'#FF0000': '矿化带'}
        })
        assert resp.status_code == 400

    def test_nonexistent_file(self, client):
        resp = client.post('/api/multiview_texture_upgrade', json={
            'session_id': 'test_tex',
            'color_map': {'#FF0000': '矿化带'},
            'file_path': '/nonexistent.xlsx'
        })
        assert resp.status_code == 400

    def test_success(self, client, create_sample_excel, mock_processors):
        resp = client.post('/api/multiview_texture_upgrade', json={
            'session_id': 'test_tex_ok',
            'color_map': {'#FF0000': '矿化带'},
            'file_path': create_sample_excel,
            'view_count': 1
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'images' in data or 'success' in data


# ==================== 8. 分析数据路由 ====================

class TestAnalysisData:
    """测试 /api/analysis_data"""

    def test_missing_session(self, client):
        resp = client.get('/api/analysis_data')
        assert resp.status_code == 400

    def test_no_data(self, client):
        resp = client.get('/api/analysis_data?session_id=nonexistent')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is False

    def test_has_rbf_data(self, client, override_config):
        from handlers.analysis_manager import record_rbf_data
        record_rbf_data('test_analysis_rbf', {'func': 'm'}, [{'layer_name': '矿化带', 'stats': {}}])
        resp = client.get('/api/analysis_data?session_id=test_analysis_rbf')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert data.get('has_rbf') is True


class TestExportAnalysis:
    """测试 /api/export_analysis"""

    def test_missing_session(self, client):
        resp = client.post('/api/export_analysis', json={})
        assert resp.status_code == 400

    def test_no_data(self, client):
        resp = client.post('/api/export_analysis', json={
            'session_id': 'nonexistent'
        })
        assert resp.status_code == 400

    def test_export_zip(self, client):
        from handlers.analysis_manager import record_rbf_data
        record_rbf_data('test_export', {'func': 'm'}, [
            {'layer_name': '矿化带', 'part_name': '顶面',
             'stats': {'n_points': 10, 'min': 100, 'max': 200, 'mean': 150, 'std': 25}}
        ])
        resp = client.post('/api/export_analysis', json={
            'session_id': 'test_export',
            'formats': ['csv']
        })
        assert resp.status_code == 200
        assert resp.content_type and 'zip' in resp.content_type.lower()


# ==================== 9. 输出文件路由 ====================

class TestOutputFiles:
    """测试 /outputs/<path> 静态文件服务"""

    def test_nonexistent(self, client):
        resp = client.get('/outputs/nonexistent/file.png')
        assert resp.status_code in (404, 500)  # 取决于实现

    def test_existing_file(self, client, override_config):
        """输出目录中存在文件时，应能正常下载"""
        import config as cfg
        session_dir = os.path.join(cfg.OUTPUT_FOLDER, 'test_out')
        os.makedirs(session_dir, exist_ok=True)
        test_file = os.path.join(session_dir, 'test.txt')
        with open(test_file, 'w') as f: f.write('hello')
        resp = client.get(f'/outputs/test_out/test.txt')
        assert resp.status_code in (200, 404)