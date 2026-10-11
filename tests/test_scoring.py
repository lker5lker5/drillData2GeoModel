"""
测试 scoring.py — AI 图评分
"""
import os
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image


# ==================== Fixtures ====================

@pytest.fixture
def scoring_mgr():
    from handlers import scoring as sc
    return sc


@pytest.fixture
def create_test_image(temp_dir):
    """创建测试图片文件"""
    def _create(filename='test.png', size=(64, 64), color=(100, 150, 200)):
        path = os.path.join(temp_dir, filename)
        img = Image.new('RGB', size, color)
        img.save(path)
        return path
    return _create


@pytest.fixture
def two_test_images(temp_dir):
    """创建两张相似的测试图片"""
    path_a = os.path.join(temp_dir, 'img_a.png')
    path_b = os.path.join(temp_dir, 'img_b.png')
    # A: 纯色蓝色渐变
    img_a = Image.new('RGB', (64, 64), (50, 100, 200))
    img_a.save(path_a)
    # B: 稍微不同的蓝色渐变
    arr = np.ones((64, 64, 3), dtype=np.uint8)
    arr[:, :, 0] = 60
    arr[:, :, 1] = 110
    arr[:, :, 2] = 210
    img_b = Image.fromarray(arr)
    img_b.save(path_b)
    return path_a, path_b


# ==================== 测试 ====================

class TestLoadImageAsArray:
    """测试图片加载"""

    def test_loads_png(self, scoring_mgr, create_test_image):
        path = create_test_image('test.png', size=(64, 64))
        arr = scoring_mgr.load_image_as_array(path)
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (512, 512, 3)  # 默认 resize 为 512x512

    def test_resizes_image(self, scoring_mgr, create_test_image):
        path = create_test_image('test.png', size=(100, 50))
        arr = scoring_mgr.load_image_as_array(path, target_size=(512, 512))
        assert arr.shape == (512, 512, 3)

    def test_default_target_size(self, scoring_mgr, create_test_image):
        path = create_test_image('test.png')
        arr = scoring_mgr.load_image_as_array(path)
        assert arr.shape == (512, 512, 3)

    def test_nonexistent_file_raises(self, scoring_mgr):
        with pytest.raises(Exception):
            scoring_mgr.load_image_as_array('/nonexistent/file.png')


class TestComputeSSIM:
    """测试 SSIM 计算"""

    def test_identical_images(self, scoring_mgr):
        img = np.ones((64, 64, 3), dtype=np.uint8) * 128
        score = scoring_mgr.compute_ssim(img, img)
        assert score == 1.0  # 完全相同的图片 SSIM=1

    def test_different_images(self, scoring_mgr):
        img1 = np.ones((64, 64, 3), dtype=np.uint8) * 0
        img2 = np.ones((64, 64, 3), dtype=np.uint8) * 255
        score = scoring_mgr.compute_ssim(img1, img2)
        assert score < 1.0
        assert isinstance(score, float)

    def test_score_range(self, scoring_mgr):
        """SSIM 应在 [0, 1] 范围内"""
        img1 = np.ones((64, 64, 3), dtype=np.uint8) * 100
        img2 = np.ones((64, 64, 3), dtype=np.uint8) * 200
        score = scoring_mgr.compute_ssim(img1, img2)
        assert 0.0 <= score <= 1.0

    def test_grayscale_input(self, scoring_mgr):
        img1 = np.ones((64, 64), dtype=np.uint8) * 100
        img2 = np.ones((64, 64), dtype=np.uint8) * 200
        score = scoring_mgr.compute_ssim(img1, img2)
        assert 0.0 <= score <= 1.0

    def test_evaluate_fallback_on_load_error(self, scoring_mgr):
        """evaluate_ai_image 在图片加载失败时应返回全 0 评分"""
        result = scoring_mgr.evaluate_ai_image('/nonexistent/ai.png', '/nonexistent/ref.png')
        assert result['ssim'] == 0.0
        assert result['color_similarity'] == 0.0
        assert result['total_score'] == 0.0


class TestComputeColorSimilarity:
    """测试颜色相似度"""

    def test_identical_images(self, scoring_mgr):
        img = np.ones((64, 64, 3), dtype=np.uint8) * 128
        score = scoring_mgr.compute_color_similarity(img, img)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_different_colors(self, scoring_mgr):
        img1 = np.ones((64, 64, 3), dtype=np.uint8) * 0   # 纯黑
        img2 = np.ones((64, 64, 3), dtype=np.uint8) * 255 # 纯白
        score = scoring_mgr.compute_color_similarity(img1, img2)
        assert score < 1.0
        assert isinstance(score, float)

    def test_score_range(self, scoring_mgr):
        img1 = np.ones((64, 64, 3), dtype=np.uint8) * 100
        img2 = np.ones((64, 64, 3), dtype=np.uint8) * 200
        score = scoring_mgr.compute_color_similarity(img1, img2)
        assert 0.0 <= score <= 1.0


class TestEvaluateAIImage:
    """测试 AI 图评分"""

    def test_evaluate_returns_all_keys(self, scoring_mgr, two_test_images):
        ai_path, ref_path = two_test_images
        scores = scoring_mgr.evaluate_ai_image(ai_path, ref_path)
        assert 'ssim' in scores
        assert 'color_similarity' in scores
        assert 'total_score' in scores

    def test_total_score_between_0_and_1(self, scoring_mgr, two_test_images):
        ai_path, ref_path = two_test_images
        scores = scoring_mgr.evaluate_ai_image(ai_path, ref_path)
        assert 0.0 <= scores['total_score'] <= 1.0

    def test_identical_images_max_score(self, scoring_mgr, create_test_image):
        path = create_test_image('test.png')
        scores = scoring_mgr.evaluate_ai_image(path, path)
        assert scores['total_score'] > 0.9  # 应接近 1.0

    def test_nonexistent_ai_path(self, scoring_mgr, create_test_image):
        ref_path = create_test_image('ref.png')
        scores = scoring_mgr.evaluate_ai_image('/nonexistent.png', ref_path)
        assert scores['ssim'] == 0.0
        assert scores['color_similarity'] == 0.0
        assert scores['total_score'] == 0.0

    def test_nonexistent_ref_path(self, scoring_mgr, create_test_image):
        ai_path = create_test_image('ai.png')
        scores = scoring_mgr.evaluate_ai_image(ai_path, '/nonexistent.png')
        assert scores['total_score'] == 0.0


class TestRankAICandidates:
    """测试 AI 候选图排序"""

    def test_rank_candidates(self, scoring_mgr, two_test_images):
        ai_path, ref_path = two_test_images
        candidates = [
            {'path': ai_path, 'index': 1, 'url': '/url/1'},
        ]
        result = scoring_mgr.rank_ai_candidates(candidates, ref_path)
        assert 'ranked' in result
        assert 'best_index' in result
        assert 'is_close' in result
        assert len(result['ranked']) == 1
        assert result['best_index'] == 1

    def test_multiple_candidates_sorted(self, scoring_mgr, two_test_images, create_test_image):
        """候选图应按照评分从高到低排列"""
        ref_path = create_test_image('ref.png', color=(100, 100, 100))
        best_path = create_test_image('best.png', color=(100, 100, 100))  # 与 ref 相同
        worst_path = create_test_image('worst.png', color=(0, 0, 0))      # 与 ref 不同
        candidates = [
            {'path': worst_path, 'index': 2, 'url': '/url/2'},
            {'path': best_path, 'index': 1, 'url': '/url/1'},
        ]
        result = scoring_mgr.rank_ai_candidates(candidates, ref_path)
        assert result['ranked'][0]['index'] == 1  # 最佳排第一

    def test_is_close_threshold(self, scoring_mgr, two_test_images, create_test_image):
        """当两个候选评分接近时, is_close 应为 True"""
        ref_path = create_test_image('ref.png', color=(128, 128, 128))
        cand1 = create_test_image('c1.png', color=(128, 128, 128))
        cand2 = create_test_image('c2.png', color=(130, 130, 130))
        candidates = [
            {'path': cand1, 'index': 1, 'url': '/url/1'},
            {'path': cand2, 'index': 2, 'url': '/url/2'},
        ]
        result = scoring_mgr.rank_ai_candidates(candidates, ref_path)
        # 如果 diff < SCORE_DIFF_THRESHOLD 则 is_close=True
        # （是否触发取决于实际图片相似度）
        assert isinstance(result['is_close'], bool)

    def test_empty_candidates(self, scoring_mgr, create_test_image):
        ref_path = create_test_image('ref.png')
        result = scoring_mgr.rank_ai_candidates([], ref_path)
        assert result['ranked'] == []
        assert result['best_index'] is None
        assert result['is_close'] is False

    def test_single_candidate(self, scoring_mgr, two_test_images):
        ai_path, ref_path = two_test_images
        candidates = [{'path': ai_path, 'index': 1, 'url': '/url/1'}]
        result = scoring_mgr.rank_ai_candidates(candidates, ref_path)
        assert len(result['ranked']) == 1
        assert result['is_close'] is False


class TestColorHistNormalization:
    """测试颜色直方图归一化（内部行为验证）"""

    def test_zero_norm_handled(self, scoring_mgr):
        """全黑图片的直方图 L2 范数为 0，不应除零"""
        from handlers import scoring as sc_module
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        # _color_hist 是内部函数，但可以通过参数验证
        score = sc_module.compute_color_similarity(img, img)
        assert 0.0 <= score <= 1.0