"""
测试 cache_manager.py — 缓存管理
"""
import os
import json
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    pass


@pytest.fixture
def cache_mgr():
    """延迟导入 cache_manager"""
    import cache_manager as cm
    return cm


@pytest.fixture
def make_cache_entry(cache_mgr, sample_session_id, temp_dir):
    """在缓存中创建一个条目，并在 temp_dir 下创建真实的 result_dir"""
    def _make(task_type='model', extra_hours=0):
        input_hash = 'abc123def456'
        result = {'html_path': 'test.html', 'count': 5}
        result_dir = os.path.join(temp_dir, 'cache_results')
        os.makedirs(result_dir, exist_ok=True)
        params_hash = 'params_hash_001'
        if extra_hours > 0:
            # 手动写入过期时间
            meta = cache_mgr.load_cache_meta(sample_session_id)
            meta[task_type] = {
                'input_hash': input_hash,
                'params_hash': params_hash,
                'created_at': (datetime.now() - timedelta(hours=extra_hours)).isoformat(),
                'result': result,
                'result_dir': result_dir
            }
            cache_mgr.save_cache_meta(sample_session_id, meta)
        else:
            cache_mgr.save_cached_result(sample_session_id, task_type, input_hash, result, result_dir, params_hash)
        return input_hash, params_hash, result_dir
    return _make


# ==================== 测试 ====================

class TestComputeFileHash:
    """测试文件哈希计算"""

    def test_hash_consistent(self, cache_mgr, temp_dir):
        fpath = os.path.join(temp_dir, 'test.txt')
        with open(fpath, 'w') as f:
            f.write('hello world')
        h1 = cache_mgr.compute_file_hash(fpath)
        h2 = cache_mgr.compute_file_hash(fpath)
        assert h1 == h2

    def test_different_files_different_hash(self, cache_mgr, temp_dir):
        f1 = os.path.join(temp_dir, 'a.txt')
        f2 = os.path.join(temp_dir, 'b.txt')
        with open(f1, 'w') as f: f.write('content a')
        with open(f2, 'w') as f: f.write('content b')
        assert cache_mgr.compute_file_hash(f1) != cache_mgr.compute_file_hash(f2)

    def test_hash_type(self, cache_mgr, temp_dir):
        fpath = os.path.join(temp_dir, 'test.txt')
        with open(fpath, 'w') as f:
            f.write('data')
        h = cache_mgr.compute_file_hash(fpath)
        assert isinstance(h, str)
        assert len(h) == 32  # MD5


class TestCacheDir:
    """测试缓存目录"""

    def test_get_cache_dir_creates(self, cache_mgr, sample_session_id):
        cache_dir = cache_mgr.get_cache_dir(sample_session_id)
        assert os.path.exists(cache_dir)

    def test_get_cache_dir_no_session(self, cache_mgr):
        cache_dir = cache_mgr.get_cache_dir(None)
        assert os.path.exists(cache_dir)
        # 应该创建在 outputs/_cache/ 下
        assert cache_dir.endswith('_cache')

    def test_get_cache_meta_path(self, cache_mgr, sample_session_id):
        meta_path = cache_mgr.get_cache_meta_path(sample_session_id)
        assert meta_path.endswith('cache_meta.json')


class TestCacheMeta:
    """测试缓存元信息读写"""

    def test_load_nonexistent_returns_empty(self, cache_mgr, sample_session_id):
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert meta == {}

    def test_save_and_load(self, cache_mgr, sample_session_id):
        test_meta = {'model': {'input_hash': 'abc', 'created_at': '2024-01-01T00:00:00'}}
        cache_mgr.save_cache_meta(sample_session_id, test_meta)
        loaded = cache_mgr.load_cache_meta(sample_session_id)
        assert loaded == test_meta

    def test_corrupted_meta_returns_empty(self, cache_mgr, sample_session_id):
        meta_path = cache_mgr.get_cache_meta_path(sample_session_id)
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, 'w') as f:
            f.write('{corrupted json')
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert meta == {}


class TestGetCachedResult:
    """测试缓存查询"""

    def test_no_meta_returns_none(self, cache_mgr, sample_session_id):
        result = cache_mgr.get_cached_result(sample_session_id, 'model', 'any_hash')
        assert result is None

    def test_hit_without_params_hash(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, _, _ = make_cache_entry('model')
        result = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash)
        assert result is not None
        assert 'result' in result
        assert 'created_at' in result

    def test_hit_with_params_hash(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, params_hash, _ = make_cache_entry('model')
        result = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash, params_hash)
        assert result is not None

    def test_miss_wrong_input_hash(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model')
        result = cache_mgr.get_cached_result(sample_session_id, 'model', 'wrong_hash')
        assert result is None

    def test_miss_wrong_params_hash(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, _, _ = make_cache_entry('model')
        result = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash, 'wrong_params')
        assert result is None

    def test_miss_wrong_task_type(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, _, _ = make_cache_entry('model')
        result = cache_mgr.get_cached_result(sample_session_id, 'ai_model', input_hash)
        assert result is None

    def test_expired_cache_returns_none(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, _, _ = make_cache_entry('model', extra_hours=25)  # 超过默认的24h TTL
        result = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash)
        assert result is None

    def test_different_session_isolated(self, cache_mgr, make_cache_entry):
        input_hash, _, _ = make_cache_entry('model')
        # 不同 session 不应命中
        result = cache_mgr.get_cached_result('other_session', 'model', input_hash)
        assert result is None

    def test_ai_model_cache_type(self, cache_mgr, sample_session_id, make_cache_entry):
        input_hash, _, _ = make_cache_entry('ai_model')
        result = cache_mgr.get_cached_result(sample_session_id, 'ai_model', input_hash)
        assert result is not None


class TestSaveCachedResult:
    """测试缓存保存"""

    def test_save_and_retrieve(self, cache_mgr, sample_session_id, temp_dir):
        input_hash = 'def789'
        result_data = {'test_key': 'test_value', 'count': 42}
        result_dir = os.path.join(temp_dir, 'cache_results')
        os.makedirs(result_dir, exist_ok=True)
        params_hash = 'p_hash'
        cache_mgr.save_cached_result(sample_session_id, 'model', input_hash, result_data, result_dir, params_hash)
        cached = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash, params_hash)
        assert cached is not None
        assert cached['result']['test_key'] == 'test_value'

    def test_overwrite_existing(self, cache_mgr, sample_session_id, temp_dir):
        input_hash = 'same_hash'
        base = os.path.join(temp_dir, 'cache_results')
        d1 = os.path.join(base, 'd1')
        d2 = os.path.join(base, 'd2')
        os.makedirs(d1, exist_ok=True)
        os.makedirs(d2, exist_ok=True)
        cache_mgr.save_cached_result(sample_session_id, 'model', input_hash, {'v': 1}, d1, 'p1')
        cache_mgr.save_cached_result(sample_session_id, 'model', input_hash, {'v': 2}, d2, 'p2')
        # 应返回最新的
        cached = cache_mgr.get_cached_result(sample_session_id, 'model', input_hash, 'p2')
        assert cached['result']['v'] == 2


class TestClearCache:
    """测试缓存清除"""

    def test_clear_specific_type(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model')
        make_cache_entry('ai_model')
        cache_mgr.clear_cache(sample_session_id, 'model')
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert 'model' not in meta
        assert 'ai_model' in meta

    def test_clear_all(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model')
        make_cache_entry('ai_model')
        cache_mgr.clear_cache(sample_session_id)
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert meta == {}

    def test_clear_nonexistent_type(self, cache_mgr, sample_session_id):
        # 不报错即可
        cache_mgr.clear_cache(sample_session_id, 'nonexistent')


class TestClearCacheByParamsChange:
    """测试参数变更时清除相关缓存"""

    def test_clears_model_and_ai_and_kriging(self, cache_mgr, sample_session_id, make_cache_entry):
        for t in ['model', 'ai_model', 'kriging', 'kriging_surface']:
            make_cache_entry(t)
        cache_mgr.clear_cache_by_params_change(sample_session_id)
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert 'model' not in meta
        assert 'ai_model' not in meta
        assert 'kriging' not in meta
        assert 'kriging_surface' not in meta

    def test_preserves_other_types(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model')
        make_cache_entry('some_other_type')
        cache_mgr.clear_cache_by_params_change(sample_session_id)
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert 'model' not in meta
        assert 'some_other_type' in meta


class TestCleanupExpiredCache:
    """测试过期缓存清理"""

    def test_cleans_expired(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model', extra_hours=25)
        cache_mgr.cleanup_expired_cache()
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert 'model' not in meta

    def test_keeps_fresh(self, cache_mgr, sample_session_id, make_cache_entry):
        make_cache_entry('model')  # 0 extra hours = 当前时间
        cache_mgr.cleanup_expired_cache()
        meta = cache_mgr.load_cache_meta(sample_session_id)
        assert 'model' in meta

    def test_handles_corrupted_entries(self, cache_mgr, sample_session_id):
        """corrupted cache 的 cleanup_expired_cache 方法会跳过非 dict 条目"""
        meta_path = cache_mgr.get_cache_meta_path(sample_session_id)
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, 'w') as f:
            json.dump({'bad_entry': 'not_a_dict'}, f)
        cache_mgr.cleanup_expired_cache()
        meta = cache_mgr.load_cache_meta(sample_session_id)
        # 代码中遇到非 dict 条目使用 continue（跳过），所以条目仍存在
        assert 'bad_entry' in meta

    def test_no_output_folder(self, cache_mgr, temp_dir):
        import config as cfg
        cfg.OUTPUT_FOLDER = os.path.join(temp_dir, 'nonexistent_output')
        # 不应抛出异常
        cache_mgr.cleanup_expired_cache()