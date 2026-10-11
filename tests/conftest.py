"""
共享 pytest fixtures 和辅助函数
"""
import os
import sys
import pytest
import tempfile
import shutil
import json

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ==================== 共享 Fixtures ====================

@pytest.fixture
def sample_session_id():
    """返回一个固定 session_id 用于测试"""
    return "test_session_001"


@pytest.fixture
def temp_dir():
    """创建并返回一个临时目录，测试结束后自动清理"""
    with tempfile.TemporaryDirectory(prefix="drill2model_test_") as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_params_dict():
    """返回一组样本参数"""
    return {
        'RBF_FUNCTION': 'multiquadric',
        'RBF_SMOOTH': 0.1,
        'GRID_RESOLUTION': 50,
        'N_LAYERS': None,
        'DRILL_STYLE': 'cylinder',
        'DRILL_RADIUS': 3.0,
        'KRIGING_VARIOGRAM': 'spherical'
    }


@pytest.fixture
def sample_litho_df():
    """返回一个简化的岩性 DataFrame，用于 processors 测试"""
    import pandas as pd
    return pd.DataFrame({
        '钻孔编号': ['ZK01', 'ZK01', 'ZK02', 'ZK02'],
        '孔口X': [500.0, 500.0, 600.0, 600.0],
        '孔口Y': [300.0, 300.0, 400.0, 400.0],
        '孔口Z': [100.0, 100.0, 120.0, 120.0],
        '岩性名称': ['矿化带', '第四系', '矿化带', '第四系'],
        '颜色': ['#FF0000', '#00FF00', '#FF0000', '#00FF00'],
        '层顶深': [0.0, 50.0, 0.0, 60.0],
        '层底深': [50.0, 100.0, 60.0, 150.0],
        '层顶Z': [100.0, 50.0, 120.0, 60.0],
        '层底Z': [50.0, 0.0, 60.0, -30.0],
    })


@pytest.fixture
def sample_loc_df():
    """返回一个简化的定位表 DataFrame"""
    import pandas as pd
    return pd.DataFrame({
        '钻孔编号': ['ZK01', 'ZK02'],
        '孔口X': [500.0, 600.0],
        '孔口Y': [300.0, 400.0],
        '孔口Z': [100.0, 120.0],
        '钻孔类型': ['垂直孔', '垂直孔'],
    })


@pytest.fixture
def sample_survey_df():
    """返回一个简化的测斜表 DataFrame"""
    import pandas as pd
    return pd.DataFrame({
        '钻孔编号': ['ZK01', 'ZK01', 'ZK02', 'ZK02'],
        '测深': [0.0, 100.0, 0.0, 150.0],
        '倾角': [-90.0, -90.0, -90.0, -90.0],
        '方位角': [0.0, 0.0, 0.0, 0.0],
    })


@pytest.fixture
def override_config(monkeypatch):
    """
    重写 config 中的路径常量，使测试不污染真实目录。
    同时修复 mineDrillApp 中通过 from config import * 导入的模块级副本。
    """
    import config as cfg
    tmpdir = tempfile.mkdtemp(prefix="drill2model_cfg_")
    # 更新 config 模块级变量
    cfg.UPLOAD_FOLDER = os.path.join(tmpdir, 'uploads')
    cfg.OUTPUT_FOLDER = os.path.join(tmpdir, 'outputs')
    cfg.TEMPLATE_FOLDER = os.path.join(tmpdir, 'templates')
    cfg.STATIC_FOLDER = os.path.join(tmpdir, 'static')
    for folder in [cfg.UPLOAD_FOLDER, cfg.OUTPUT_FOLDER, cfg.TEMPLATE_FOLDER]:
        os.makedirs(folder, exist_ok=True)
    # 确保 outputs 目录存在（cleanup_all_sessions 会 listdir）
    os.makedirs(cfg.OUTPUT_FOLDER, exist_ok=True)
    # 复制模板文件到临时路径（template 路由会 serve 它）
    import shutil as shutil_mod
    from config import TEMPLATE_FILE as ORIG_TEMPLATE
    if os.path.exists(ORIG_TEMPLATE):
        shutil_mod.copy2(ORIG_TEMPLATE, os.path.join(cfg.TEMPLATE_FOLDER, 'drill_data_template.xlsx'))

    # 缓存配置
    cfg.CACHE_ENABLED = True
    cfg.CACHE_TTL_HOURS = 24

    # 同步更新 mineDrillApp 的模块级副本（from config import * 导入的）
    try:
        import mineDrillApp
        mineDrillApp.UPLOAD_FOLDER = cfg.UPLOAD_FOLDER
        mineDrillApp.OUTPUT_FOLDER = cfg.OUTPUT_FOLDER
        mineDrillApp.TEMPLATE_FOLDER = cfg.TEMPLATE_FOLDER
        mineDrillApp.STATIC_FOLDER = cfg.STATIC_FOLDER
    except ImportError:
        pass  # mineDrillApp 可能尚未导入

    yield
    shutil.rmtree(tmpdir, ignore_errors=True)


# ==================== Flask App Fixtures ====================

@pytest.fixture
def app(override_config):
    """
    创建 Flask 测试应用实例。
    使用 override_config 确保路径指向临时目录。
    """
    from mineDrillApp import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['SERVER_NAME'] = 'localhost'
    # 禁用 CSR F / 调试覆盖
    flask_app.config['DEBUG'] = False
    return flask_app


@pytest.fixture
def client(app):
    """Flask 测试客户端"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Flask CLI 测试运行器"""
    return app.test_cli_runner()


# ==================== 测试数据相关 ====================

@pytest.fixture
def create_sample_excel(temp_dir):
    """
    创建一个符合代码约定的 Excel 测试文件。
    列名需匹配 processors.py / main.py 中的实际使用。
    """
    import pandas as pd
    loc = pd.DataFrame({
        '钻孔编号': ['ZK01', 'ZK02'],
        '开孔坐标E': [40504500, 40505500],
        '开孔坐标N': [3123456, 3124567],
        '开孔高程R': [100.0, 120.0],
        '钻孔类型': ['垂直孔', '垂直孔'],
        '钻孔长度': [100.0, 150.0],
    })
    survey = pd.DataFrame({
        '钻孔编号': ['ZK01', 'ZK01', 'ZK02', 'ZK02'],
        '各层位长度': [0.0, 100.0, 0.0, 150.0],
        '倾角': [-90.0, -90.0, -90.0, -90.0],
        '方位角': [0.0, 0.0, 0.0, 0.0],
    })
    litho = pd.DataFrame({
        '岩性描述': ['矿化带', '第四系', '矿化带', '第四系'],
        '建模颜色': ['#FF0000', '#00FF00', '#FF0000', '#00FF00'],
        '钻孔编号': ['ZK01', 'ZK01', 'ZK02', 'ZK02'],
        '孔口X': [500.0, 500.0, 600.0, 600.0],
        '孔口Y': [300.0, 300.0, 400.0, 400.0],
        '孔口Z': [100.0, 100.0, 120.0, 120.0],
        '层顶深': [0.0, 50.0, 0.0, 60.0],
        '层底深': [50.0, 100.0, 60.0, 150.0],
        '层顶Z': [100.0, 50.0, 120.0, 60.0],
        '层底Z': [50.0, 0.0, 60.0, -30.0],
    })
    filepath = os.path.join(temp_dir, 'test_drill_data.xlsx')
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        loc.to_excel(writer, sheet_name='定位表', index=False)
        survey.to_excel(writer, sheet_name='测斜表', index=False)
        litho.to_excel(writer, sheet_name='岩性表', index=False)
    return filepath


@pytest.fixture
def create_broken_excel(temp_dir):
    """
    创建一个只有定位表的残缺 Excel（缺少测斜表和岩性表）。
    """
    import pandas as pd
    loc = pd.DataFrame({
        '钻孔编号': ['ZK01'],
        '孔口X': [500.0],
        '孔口Y': [300.0],
        '孔口Z': [100.0],
    })
    filepath = os.path.join(temp_dir, 'broken_drill_data.xlsx')
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        loc.to_excel(writer, sheet_name='定位表', index=False)
    return filepath


@pytest.fixture
def mock_import(monkeypatch):
    """
    通用 mock 工厂：mock 掉可能产生副作用的导入或函数调用。
    后续各测试模块可自行扩展。
    """
    # 默认 mock matplotlib 后端，避免在无头环境报错
    import matplotlib
    monkeypatch.setattr(matplotlib, 'use', lambda *a, **kw: None, raising=False)
    return monkeypatch