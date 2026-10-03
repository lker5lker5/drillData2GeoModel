"""
测试 analysis_manager.py — 分析数据管理
"""
import os
import json
import pytest
import numpy as np

# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    pass


@pytest.fixture
def analysis_mgr():
    import analysis_manager as am
    return am


# ==================== 测试 ====================

class TestGetAnalysisDataPath:
    """测试分析数据路径"""

    def test_returns_path(self, analysis_mgr, sample_session_id):
        path = analysis_mgr.get_analysis_data_path(sample_session_id)
        assert '_cache' in path
        assert 'analysis_data.json' in path
        assert sample_session_id in path

    def test_creates_directory(self, analysis_mgr, sample_session_id):
        path = analysis_mgr.get_analysis_data_path(sample_session_id)
        assert os.path.exists(os.path.dirname(path))


class TestLoadAnalysisData:
    """测试加载分析数据"""

    def test_no_file_returns_empty(self, analysis_mgr, sample_session_id):
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert data == {}

    def test_after_save_returns_saved(self, analysis_mgr, sample_session_id):
        test_data = {'rbf': {'params': {'func': 'multiquadric'}}}
        analysis_mgr.save_analysis_data(sample_session_id, test_data)
        loaded = analysis_mgr.load_analysis_data(sample_session_id)
        assert loaded == test_data

    def test_corrupted_file_returns_empty(self, analysis_mgr, sample_session_id):
        path = analysis_mgr.get_analysis_data_path(sample_session_id)
        with open(path, 'w') as f:
            f.write('not json {{{')
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert data == {}


class TestSaveAnalysisData:
    """测试保存分析数据"""

    def test_save_success(self, analysis_mgr, sample_session_id):
        result = analysis_mgr.save_analysis_data(sample_session_id, {'test': 'data'})
        assert result is True

    def test_save_persists_to_disk(self, analysis_mgr, sample_session_id):
        analysis_mgr.save_analysis_data(sample_session_id, {'key': 'value'})
        path = analysis_mgr.get_analysis_data_path(sample_session_id)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data['key'] == 'value'

    def test_overwrite_works(self, analysis_mgr, sample_session_id):
        analysis_mgr.save_analysis_data(sample_session_id, {'v': 1})
        analysis_mgr.save_analysis_data(sample_session_id, {'v': 2})
        loaded = analysis_mgr.load_analysis_data(sample_session_id)
        assert loaded['v'] == 2

    def test_save_empty_dict(self, analysis_mgr, sample_session_id):
        assert analysis_mgr.save_analysis_data(sample_session_id, {}) is True
        assert analysis_mgr.load_analysis_data(sample_session_id) == {}


class TestNumpyToList:
    """测试 numpy 数组转 JSON 可序列化"""

    def test_none(self, analysis_mgr):
        assert analysis_mgr._numpy_to_list(None) is None

    def test_1d_array(self, analysis_mgr):
        arr = np.array([1.0, 2.5, np.nan, 4.0])
        result = analysis_mgr._numpy_to_list(arr)
        assert isinstance(result, list)
        assert len(result) == 4
        assert result[0] == 1.0
        assert result[1] == 2.5
        assert result[2] is None  # NaN -> None
        assert result[3] == 4.0

    def test_2d_array_raveled(self, analysis_mgr):
        arr = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = analysis_mgr._numpy_to_list(arr)
        # ravel() flatten to 1D
        assert len(result) == 4

    def test_regular_list(self, analysis_mgr):
        result = analysis_mgr._numpy_to_list([1, 2, None])
        assert result == [1, 2, None]

    def test_list_with_nan(self, analysis_mgr):
        result = analysis_mgr._numpy_to_list([1.0, float('nan'), 3.0])
        assert result[1] is None


class TestRecordRbfData:
    """测试记录 RBF 分析数据"""

    def test_record_creates_entry(self, analysis_mgr, sample_session_id):
        params = {'func': 'multiquadric', 'smooth': 0.1}
        layers = [{'name': '矿化带', 'points': 100}, {'name': '第四系', 'points': 50}]
        analysis_mgr.record_rbf_data(sample_session_id, params, layers)
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert 'rbf' in data
        assert data['rbf']['params'] == params
        assert len(data['rbf']['layers']) == 2

    def test_record_overwrites_previous(self, analysis_mgr, sample_session_id):
        analysis_mgr.record_rbf_data(sample_session_id, {'func': 'linear'}, [{'name': 'A'}])
        analysis_mgr.record_rbf_data(sample_session_id, {'func': 'thin_plate'}, [{'name': 'B'}])
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert data['rbf']['params']['func'] == 'thin_plate'
        assert data['rbf']['layers'][0]['name'] == 'B'

    def test_record_empty_layers(self, analysis_mgr, sample_session_id):
        analysis_mgr.record_rbf_data(sample_session_id, {}, [])
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert data['rbf']['layers'] == []

    def test_record_has_created_at(self, analysis_mgr, sample_session_id):
        analysis_mgr.record_rbf_data(sample_session_id, {}, [])
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert 'created_at' in data['rbf']
        assert data['rbf']['created_at'] is not None


class TestRecordKrigingData:
    """测试记录克里金分析数据"""

    def test_record_creates_entry(self, analysis_mgr, sample_session_id):
        params = {'variogram': 'spherical'}
        layers = [{'name': '矿化带', 'rmse': 0.5}]
        analysis_mgr.record_kriging_data(sample_session_id, params, layers)
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert 'kriging' in data
        assert data['kriging']['params'] == params

    def test_rbf_and_kriging_coexist(self, analysis_mgr, sample_session_id):
        analysis_mgr.record_rbf_data(sample_session_id, {'func': 'm'}, [])
        analysis_mgr.record_kriging_data(sample_session_id, {'variogram': 's'}, [])
        data = analysis_mgr.load_analysis_data(sample_session_id)
        assert 'rbf' in data
        assert 'kriging' in data