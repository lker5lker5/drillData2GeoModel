"""
测试 Flask 路由 — 上传、文件、会话管理
"""
import os
import json
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock, ANY


# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    import matplotlib
    matplotlib.use('Agg')
    # 清理 sessions 状态
    from handlers.app_utils import session_last_active, log_storage
    session_last_active.clear()
    log_storage.clear()
    pass


# ==================== 基本路由 ====================

class TestIndexRoute:
    """测试首页路由"""

    def test_get_index(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        # 页面应包含基本的 HTML 结构
        assert len(resp.data) > 100
        # 页面编码为 UTF-8，可用文本检查
        text = resp.data.decode('utf-8', errors='replace')
        assert '地质' in text or '建模' in text or 'drill' in text.lower()

    def test_static_file(self, client):
        """能被 Flask 正常响应即可"""
        resp = client.get('/static/js/main.js')
        assert resp.status_code in (200, 302, 404)


class TestUploadRoute:
    """测试文件上传"""

    def test_no_file_returns_error(self, client):
        resp = client.post('/api/upload')
        data = resp.get_json()
        assert resp.status_code == 400
        assert 'error' in data or '文件' in str(data)

    def test_empty_filename_returns_error(self, client):
        resp = client.post('/api/upload', data={
            'file': (BytesIO(b''), '')
        })
        data = resp.get_json()
        assert resp.status_code == 400

    def test_wrong_format_returns_error(self, client):
        resp = client.post('/api/upload', data={
            'file': (BytesIO(b'some content'), 'test.txt')
        })
        data = resp.get_json()
        assert resp.status_code == 400
        assert '格式' in str(data) or 'format' in str(data).lower()

    def test_valid_upload_returns_session(self, client, create_sample_excel):
        with open(create_sample_excel, 'rb') as f:
            resp = client.post('/api/upload', data={
                'file': (f, 'test.xlsx')
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'session_id' in data
        assert 'path' in data
        assert 'filename' in data
        assert len(data['session_id']) == 8

    def test_upload_old_session_cleanup(self, client, create_sample_excel):
        """上传时传递 old_session 参数应触发清理"""
        from handlers.app_utils import session_last_active
        # 先上传第一个文件获取 session_id
        with open(create_sample_excel, 'rb') as f:
            resp1 = client.post('/api/upload', data={
                'file': (f, 'test.xlsx')
            })
        old_session = resp1.get_json()['session_id']
        # 标记为活跃
        session_last_active[old_session] = 1.0

        # 第二次上传，传 old_session
        with open(create_sample_excel, 'rb') as f:
            resp2 = client.post('/api/upload', data={
                'file': (f, 'test2.xlsx'),
                'old_session': old_session
            })
        assert resp2.status_code == 200
        # 旧的 session 应已被清理
        assert old_session not in session_last_active


class TestTemplateRoute:
    """测试模板下载"""

    def test_download_template(self, client):
        resp = client.get('/api/template')
        assert resp.status_code in (200, 302)
        # 检查是否是文件下载响应
        if resp.status_code == 200:
            assert len(resp.data) > 0


# ==================== 文件信息路由 ====================

class TestFileInfoRoute:
    """测试文件信息"""

    def test_missing_params(self, client):
        resp = client.post('/api/file_info', json={})
        assert resp.status_code == 400

    def test_nonexistent_file(self, client):
        resp = client.post('/api/file_info', json={
            'session_id': 'test123',
            'path': '/nonexistent/file.xlsx'
        })
        assert resp.status_code in (200, 400)
        data = resp.get_json()
        if resp.status_code == 200:
            assert 'error' in data  # should contain error info

    def test_valid_file(self, client, create_sample_excel):
        resp = client.post('/api/file_info', json={
            'session_id': 'test123',
            'path': create_sample_excel
        })
        assert resp.status_code == 200
        data = resp.get_json()
        # 应返回文件信息（钻孔数量、岩性数量等）
        assert isinstance(data, dict)


# ==================== 会话管理路由 ====================

class TestSessionParamsRoutes:
    """测试会话参数路由"""

    def test_get_params_no_session(self, client):
        resp = client.get('/api/session_params')
        data = resp.get_json()
        assert 'params' in data
        assert 'meta' in data

    def test_get_params_with_session(self, client):
        resp = client.get('/api/session_params?session_id=test_session')
        data = resp.get_json()
        assert 'params' in data
        assert 'meta' in data

    def test_save_params_missing_session(self, client):
        resp = client.post('/api/save_params', json={
            'params': {'DRILL_RADIUS': 1.0}
        })
        assert resp.status_code == 400

    def test_save_and_get_params(self, client):
        # 保存参数
        save_resp = client.post('/api/save_params', json={
            'session_id': 'test_save_params',
            'params': {'DRILL_RADIUS': 5.0}
        })
        assert save_resp.status_code == 200
        save_data = save_resp.get_json()
        assert save_data.get('success') is True

        # 读取参数
        get_resp = client.get('/api/session_params?session_id=test_save_params')
        get_data = get_resp.get_json()
        assert get_data['params']['DRILL_RADIUS'] == 5.0

    def test_save_invalid_params(self, client):
        resp = client.post('/api/save_params', json={
            'session_id': 'test_invalid',
            'params': {'DRILL_RADIUS': -1.0}
        })
        data = resp.get_json()
        # 应返回错误
        assert 'success' not in data or data.get('success') is False

    def test_save_empty_params(self, client):
        resp = client.post('/api/save_params', json={
            'session_id': 'test_empty',
            'params': {}
        })
        data = resp.get_json()
        assert data.get('success') is True


class TestCleanupRoutes:
    """测试会话清理路由"""

    def test_cleanup_session_missing_id(self, client):
        resp = client.post('/api/cleanup_session', json={})
        assert resp.status_code == 400

    def test_cleanup_session(self, client, override_config):
        resp = client.post('/api/cleanup_session', json={
            'session_id': 'nonexistent_test'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_cleanup_all_sessions(self, client, override_config):
        resp = client.post('/api/cleanup_all_sessions', json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True


# ==================== 日志路由 ====================

class TestLogRoutes:
    """测试日志路由"""

    def test_get_logs_existing(self, client):
        from handlers.app_utils import add_log
        add_log('test_log_session', 'test message')
        resp = client.get('/api/logs/test_log_session')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'logs' in data

    def test_get_logs_nonexistent(self, client):
        resp = client.get('/api/logs/nonexistent_session')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('logs') == []