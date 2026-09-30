"""
AI 生成图的自动评分模块。
使用 SSIM（结构相似度）+ 颜色直方图余弦相似度 综合评分。
"""
import numpy as np
from PIL import Image

from config import SCORE_WEIGHT_SSIM, SCORE_WEIGHT_COLOR, SCORE_DIFF_THRESHOLD
from config import SCORE_RECOMMEND_THRESHOLD


def load_image_as_array(image_path, target_size=(512, 512)):
    """加载图片为数组"""
    img = Image.open(image_path).convert('RGB')
    img = img.resize(target_size)
    return np.array(img)


def compute_ssim(img1, img2):
    """
    计算两张图片的 SSIM（结构相似度）。
    """
    try:
        from skimage.metrics import structural_similarity as ssim
    except ImportError:
        print("!!! 未安装 scikit-image，无法计算 SSIM")
        return 0.5

    if len(img1.shape) == 3:
        img1_gray = np.mean(img1, axis=2)
    else:
        img1_gray = img1
    if len(img2.shape) == 3:
        img2_gray = np.mean(img2, axis=2)
    else:
        img2_gray = img2

    try:
        score, _ = ssim(img1_gray, img2_gray, full=True, data_range=255)
    except Exception as e:
        print(f"!!! SSIM 计算失败: {e}")
        return 0.5

    return float(max(0.0, min(1.0, score)))


def compute_color_similarity(img1, img2):
    """
    计算两张图片的色调相似度（颜色直方图余弦相似度）。
    """
    def color_hist(img):
        hist = []
        for c in range(3):
            h, _ = np.histogram(img[:, :, c], bins=32, range=(0, 256), density=True)
            hist.extend(h)
        hist = np.array(hist)
        norm = np.linalg.norm(hist)
        return hist / norm if norm > 0 else hist

    h1 = color_hist(img1)
    h2 = color_hist(img2)
    similarity = float(np.dot(h1, h2))
    return max(0.0, min(1.0, similarity))


def evaluate_ai_image(ai_image_path, ref_image_path):
    """
    评估单张 AI 图。

    返回:
        {'ssim': float, 'color_similarity': float, 'total_score': float}
    """
    try:
        ai = load_image_as_array(ai_image_path)
        ref = load_image_as_array(ref_image_path)
    except Exception as e:
        print(f"!!! 图片加载失败: {e}")
        return {'ssim': 0.0, 'color_similarity': 0.0, 'total_score': 0.0}

    ssim_score = compute_ssim(ai, ref)
    color_score = compute_color_similarity(ai, ref)
    total = SCORE_WEIGHT_SSIM * ssim_score + SCORE_WEIGHT_COLOR * color_score

    return {
        'ssim': float(round(ssim_score, 4)),
        'color_similarity': float(round(color_score, 4)),
        'total_score': float(round(total, 4))
    }


def rank_ai_candidates(candidates, ref_image_path):
    """
    对多张 AI 候选图进行排序。

    参数:
        candidates: [{'path': ..., 'index': 1, 'url': ...}, ...]
        ref_image_path: 参考图路径（Python 无标注图）

    返回:
        {
            'ranked': [...],
            'best_index': int,
            'is_close': bool
        }
    """
    scored = []
    for c in candidates:
        scores = evaluate_ai_image(c['path'], ref_image_path)
        scored.append({
            'path': c['path'],
            'url': c.get('url', ''),
            'index': c['index'],
            'scores': scores
        })

    scored.sort(key=lambda x: x['scores']['total_score'], reverse=True)

    is_close = False
    if len(scored) >= 2:
        diff = scored[0]['scores']['total_score'] - scored[1]['scores']['total_score']
        is_close = bool(diff < SCORE_DIFF_THRESHOLD)

    return {
        'ranked': scored,
        'best_index': int(scored[0]['index']) if scored else None,
        'is_close': bool(is_close)
    }