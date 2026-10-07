"""
测试 params_manager.py — 用户参数管理
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    """自动应用路径重定向，避免污染实际目录"""
    pass


@pytest.fixture
def params_mgr():
    """延迟导入 params_manager，确保路径 monkeypatch 已生效"""
    import params_manager as pm
    return pm


# ==================== 基本功能测试 ====================

class TestGetDefaultParams:
    """测试获取默认参数"""

    def test_returns_dict(self, params_mgr):
        result = params_mgr.get_default_params()
        assert isinstance(result, dict)
        assert 'GRID_RESOLUTION' in result
        assert 'N_LAYERS' in result
        assert 'DRILL_STYLE' in result
        assert 'DRILL_RADIUS' in result

    def test_default_values_match_config(self, params_mgr):
        from config import GRID_RESOLUTION, DRILL_STYLE, DRILL_RADIUS
        result = params_mgr.get_default_params()
        assert result['GRID_RESOLUTION'] == GRID_RESOLUTION
        assert result['DRILL_STYLE'] == DRILL_STYLE
        assert result['DRILL_RADIUS'] == DRILL_RADIUS

    def test_n_layers_is_none(self, params_mgr):
        from config import N_LAYERS
        result = params_mgr.get_default_params()
        assert result['N_LAYERS'] is N_LAYERS


class TestLoadSessionParams:
    """测试加载会话参数"""

    def test_no_session_id_returns_defaults(self, params_mgr):
        params = params_mgr.load_session_params(None)
        assert params['GRID_RESOLUTION'] == 50

    def test_empty_session_id_returns_defaults(self, params_mgr):
        params = params_mgr.load_session_params('')
        assert params['GRID_RESOLUTION'] == 50

    def test_no_file_returns_defaults(self, params_mgr, sample_session_id):
        params = params_mgr.load_session_params(sample_session_id)
        assert params['GRID_RESOLUTION'] == 50

    def test_load_saved_params(self, params_mgr, sample_session_id):
        params_mgr.save_session_params(sample_session_id, {'DRILL_RADIUS': 5.0})
        loaded = params_mgr.load_session_params(sample_session_id)
        assert loaded['DRILL_RADIUS'] == 5.0
        # 未保存的参数也应保留默认值
        assert loaded['GRID_RESOLUTION'] == 50

    def test_load_corrupted_file_returns_defaults(self, params_mgr, sample_session_id):
        import config as cfg
        params_path = os.path.join(cfg.UPLOAD_FOLDER, sample_session_id, cfg.SESSION_PARAMS_FILENAME)
        os.makedirs(os.path.dirname(params_path), exist_ok=True)
        with open(params_path, 'w') as f:
            f.write('不是有效的 JSON {{{')
        params = params_mgr.load_session_params(sample_session_id)
        assert params['GRID_RESOLUTION'] == 50


class TestSaveSessionParams:
    """测试保存会话参数"""

    def test_save_success(self, params_mgr, sample_session_id):
        ok, err = params_mgr.save_session_params(sample_session_id, {'GRID_RESOLUTION': 60})
        assert ok is True
        assert err is None

    def test_save_no_session_id(self, params_mgr):
        ok, err = params_mgr.save_session_params(None, {})
        assert ok is False
        assert 'session_id' in (err or '')

    def test_save_empty_session_id(self, params_mgr):
        ok, err = params_mgr.save_session_params('', {})
        assert ok is False
        assert 'session_id' in (err or '')

    def test_save_filters_unknown_keys(self, params_mgr, sample_session_id):
        params_mgr.save_session_params(sample_session_id, {'UNKNOWN_KEY': 999})
        loaded = params_mgr.load_session_params(sample_session_id)
        assert 'UNKNOWN_KEY' not in loaded

    def test_save_persists_to_disk(self, params_mgr, sample_session_id):
        params_mgr.save_session_params(sample_session_id, {'DRILL_RADIUS': 5.0})
        params_path = params_mgr.get_params_path(sample_session_id)
        assert os.path.exists(params_path)
        with open(params_path) as f:
            data = json.load(f)
        assert data['DRILL_RADIUS'] == 5.0

    def test_merges_with_defaults(self, params_mgr, sample_session_id):
        """保存部分参数后，加载应合并默认值"""
        params_mgr.save_session_params(sample_session_id, {'DRILL_RADIUS': 5.0})
        loaded = params_mgr.load_session_params(sample_session_id)
        assert loaded['DRILL_RADIUS'] == 5.0
        assert loaded['GRID_RESOLUTION'] == 50  # 默认值


class TestValidateParams:
    """测试参数校验"""

    def test_valid_params(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_STYLE': 'line'})
        assert ok is True
        assert err is None

    def test_invalid_enum_value(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_STYLE': 'invalid_style'})
        assert ok is False
        assert 'DRILL_STYLE' in (err or '')

    def test_number_out_of_range_high(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_RADIUS': 999.0})
        assert ok is False
        assert 'DRILL_RADIUS' in (err or '')

    def test_number_out_of_range_low(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_RADIUS': -1.0})
        assert ok is False
        assert 'DRILL_RADIUS' in (err or '')

    def test_number_at_boundary(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_RADIUS': 0.5})
        assert ok is True
        ok, err = params_mgr.validate_params({'DRILL_RADIUS': 20.0})
        assert ok is True

    def test_non_numeric_for_number(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_RADIUS': 'abc'})
        assert ok is False
        assert 'DRILL_RADIUS' in (err or '')

    def test_n_layers_none_is_valid(self, params_mgr):
        ok, err = params_mgr.validate_params({'N_LAYERS': None})
        assert ok is True

    def test_n_layers_valid_int(self, params_mgr):
        ok, err = params_mgr.validate_params({'N_LAYERS': 12})
        assert ok is True

    def test_n_layers_out_of_range(self, params_mgr):
        ok, err = params_mgr.validate_params({'N_LAYERS': 100})
        assert ok is False

    def test_invalid_drill_style(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_STYLE': 'cone'})
        assert ok is False

    def test_valid_drill_style(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_STYLE': 'line'})
        assert ok is True

    def test_invalid_variogram(self, params_mgr):
        ok, err = params_mgr.validate_params({'DRILL_STYLE': 'invalid'})
        assert ok is False
        assert 'DRILL_STYLE' in (err or '')

    def test_empty_params_dict(self, params_mgr):
        ok, err = params_mgr.validate_params({})
        assert ok is True
        assert err is None

    def test_unknown_keys_ignored(self, params_mgr):
        ok, err = params_mgr.validate_params({'SOME_RANDOM_KEY': 123})
        assert ok is True
        assert err is None


class TestComputeParamsHash:
    """测试参数哈希计算"""

    def test_consistent_hash(self, params_mgr):
        h1 = params_mgr.compute_params_hash({'DRILL_STYLE': 'cylinder', 'DRILL_RADIUS': 3.0})
        h2 = params_mgr.compute_params_hash({'DRILL_RADIUS': 3.0, 'DRILL_STYLE': 'cylinder'})
        assert h1 == h2  # 顺序无关

    def test_different_params_different_hash(self, params_mgr):
        h1 = params_mgr.compute_params_hash({'DRILL_STYLE': 'cylinder'})
        h2 = params_mgr.compute_params_hash({'DRILL_STYLE': 'line'})
        assert h1 != h2

    def test_unknown_keys_excluded(self, params_mgr):
        h1 = params_mgr.compute_params_hash({'DRILL_STYLE': 'cylinder'})
        h2 = params_mgr.compute_params_hash({'DRILL_STYLE': 'cylinder', 'UNKNOWN': 999})
        assert h1 == h2

    def test_none_vs_value(self, params_mgr):
        h1 = params_mgr.compute_params_hash({'N_LAYERS': None})
        h2 = params_mgr.compute_params_hash({'N_LAYERS': 12})
        assert h1 != h2

    def test_returns_hex_string(self, params_mgr):
        h = params_mgr.compute_params_hash({'RBF_FUNCTION': 'multiquadric'})
        assert isinstance(h, str)
        assert len(h) == 32  # MD5


class TestGetFrontendMeta:
    """测试前端参数元信息"""

    def test_returns_dict(self, params_mgr):
        meta = params_mgr.get_frontend_meta()
        assert isinstance(meta, dict)
        assert len(meta) > 0

    def test_contains_all_adjustable_params(self, params_mgr):
        from config import USER_ADJUSTABLE_PARAMS
        meta = params_mgr.get_frontend_meta()
        for key in USER_ADJUSTABLE_PARAMS:
            assert key in meta

    def test_has_required_keys(self, params_mgr):
        meta = params_mgr.get_frontend_meta()
        for key, info in meta.items():
            assert 'label' in info
            assert 'type' in info
            assert 'default' in info
            if info['type'] == 'enum':
                assert 'options' in info
            if info['type'] in ('number', 'number_or_auto'):
                assert 'min' in info
                assert 'max' in info