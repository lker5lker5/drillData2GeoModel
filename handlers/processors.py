# processors.py
# 核心处理函数

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import Rbf
from scipy.interpolate import interp1d
from scipy.spatial import ConvexHull
from matplotlib.path import Path
from matplotlib.ticker import FormatStrFormatter
import plotly.graph_objects as go
import os
import json
import io
import requests
import base64
from pyproj import Transformer
from config import *

# ==================== 中文字体配置 ====================
def setup_chinese_font():
    """配置matplotlib中文字体"""
    import matplotlib.font_manager as fm
    
    # 尝试多个中文字体
    font_list = [
        'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 
        'SimHei', 'STHeiti', 'WenQuanYi Zen Hei',
        'Noto Sans CJK SC', 'Source Han Sans SC',
        'Arial Unicode MS', 'DejaVu Sans'
    ]
    
    for font_name in font_list:
        try:
            # 检查字体是否存在
            font_path = fm.findfont(font_name)
            if font_path and os.path.exists(font_path):
                plt.rcParams['font.sans-serif'] = [font_name]
                plt.rcParams['axes.unicode_minus'] = False
                print(f"==> 使用中文字体: {font_name}")
                return True
        except:
            continue
    
    # 如果都找不到，尝试从系统路径查找
    try:
        import matplotlib.font_manager as fm
        font_paths = fm.findSystemFonts()
        for font_path in font_paths:
            font_name = os.path.basename(font_path)
            if 'hei' in font_name.lower() or 'song' in font_name.lower() or 'yahei' in font_name.lower():
                try:
                    prop = fm.FontProperties(fname=font_path)
                    plt.rcParams['font.sans-serif'] = [prop.get_name()]
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"==> 使用中文字体: {prop.get_name()}")
                    return True
                except:
                    continue
    except:
        pass
    
    # 最后尝试使用默认字体
    try:
        plt.rcParams['font.sans-serif'] = ['sans-serif']
        print("!!! 未找到中文字体，使用默认字体（中文可能显示为方框）")
    except:
        pass
    
    return False

# 初始化中文字体
setup_chinese_font()

# ==================== COLOR_MAP 动态生成 ====================
def get_color_map_from_dataframe(litho_df):
    """
    从DataFrame中提取颜色映射
    返回: dict {颜色值: 岩性名称}
    处理空值和NaN
    """
    color_map = {}
    try:
        for _, row in litho_df.iterrows():
            color = str(row['建模颜色']).strip()
            lith_name = str(row['岩性描述']).strip()
            
            # 跳过空值、NaN、'nan'、'None'
            if not color or not lith_name:
                continue
            if color.lower() in ['nan', 'none', ''] or lith_name.lower() in ['nan', 'none', '']:
                continue
            
            if color in color_map:
                if lith_name not in color_map[color]:
                    color_map[color] = color_map[color] + '、' + lith_name
            else:
                color_map[color] = lith_name
        
        print(f"==> 从DataFrame提取到 {len(color_map)} 个颜色映射")
        return color_map
    except Exception as e:
        print(f"!!! 读取颜色映射失败: {e}")
        return {}

# ==================== 颜色解析 ====================
def parse_color(color_str, lith_name=None):
    """解析颜色字符串，返回 (r, g, b, alpha) 元组"""
    alpha = 1.0
    if lith_name:
        if '矿体' in lith_name:
            alpha = 1
        elif '矿化带' in lith_name:
            alpha = 0.6
        else:
            alpha = 0.4
    
    color_str = str(color_str).strip()
    
    if color_str.startswith('#'):
        hex_color = color_str.lstrip('#')
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            return (r, g, b, alpha)
    
    try:
        parts = color_str.split(',')
        if len(parts) == 3:
            r = int(parts[0].strip()) / 255.0
            g = int(parts[1].strip()) / 255.0
            b = int(parts[2].strip()) / 255.0
            return (r, g, b, alpha)
    except:
        pass
    
    return (0.5, 0.5, 0.5, alpha)


def hex_to_rgb_str(hex_color):
    """将十六进制颜色转换为RGB字符串"""
    if hex_color.startswith('#'):
        hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f'rgb({r},{g},{b})'
    return hex_color

def plot_cylinder_segment(ax, xs, ys, zs, color, radius=3.0, sides=8):
    """
    在钻孔轨迹上绘制圆柱曲面。
    
    参数:
        ax: matplotlib 3D 坐标轴
        xs, ys, zs: 钻孔轨迹点的坐标数组（沿钻孔方向）
        color: 圆柱颜色 (r, g, b) 或 (r, g, b, a)
        radius: 圆柱半径（米）
        sides: 圆周分段数
    
    原理:
        - 对每个轨迹点，生成一个垂直于钻孔方向的圆形截面
        - 将所有截面连接成圆柱曲面
    """
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    
    n_pts = len(xs)
    if n_pts < 2:
        return
    
    # 1. 计算每个轨迹点处的"切线方向"（即钻孔延伸方向）
    tangents = np.zeros((n_pts, 3))
    for i in range(n_pts):
        if i == 0:
            tangents[i] = [xs[1]-xs[0], ys[1]-ys[0], zs[1]-zs[0]]
        elif i == n_pts - 1:
            tangents[i] = [xs[-1]-xs[-2], ys[-1]-ys[-2], zs[-1]-zs[-2]]
        else:
            tangents[i] = [xs[i+1]-xs[i-1], ys[i+1]-ys[i-1], zs[i+1]-zs[i-1]]
        # 归一化
        norm = np.linalg.norm(tangents[i])
        if norm > 1e-9:
            tangents[i] /= norm
    
    # 2. 对每个轨迹点，构造垂直于切线的圆形截面
    #    用任意的"上"向量作为参考，避免与切线平行
    up = np.array([0, 0, 1])
    
    circle_angles = np.linspace(0, 2*np.pi, sides, endpoint=False)
    cos_a = np.cos(circle_angles)
    sin_a = np.sin(circle_angles)
    
    # 存储每个截面的顶点
    section_vertices = []
    for i in range(n_pts):
        t = tangents[i]
        # 构造局部坐标系的两个正交基向量
        if abs(np.dot(t, up)) > 0.99:
            up_ref = np.array([0, 1, 0])
        else:
            up_ref = up
        u = np.cross(t, up_ref)
        u_norm = np.linalg.norm(u)
        if u_norm < 1e-9:
            u = np.array([1, 0, 0])
        else:
            u /= u_norm
        v = np.cross(t, u)
        
        # 截面顶点
        verts = []
        for k in range(sides):
            point = np.array([xs[i], ys[i], zs[i]]) + radius * (cos_a[k] * u + sin_a[k] * v)
            verts.append(point)
        section_vertices.append(verts)
    
    # 3. 连接相邻截面，生成三角面片
    faces = []
    face_colors = []
    for i in range(n_pts - 1):
        for k in range(sides):
            k_next = (k + 1) % sides
            # 每个四边形拆分为两个三角形
            p1 = section_vertices[i][k]
            p2 = section_vertices[i][k_next]
            p3 = section_vertices[i+1][k_next]
            p4 = section_vertices[i+1][k]
            faces.append([p1, p2, p3])
            faces.append([p1, p3, p4])
            face_colors.append(color[:3])
    
    # 4. 用 Poly3DCollection 一次性绘制
    from matplotlib.colors import to_rgba
    if len(color) == 4:
        face_color = to_rgba(color[:3], alpha=color[3])
    else:
        face_color = to_rgba(color[:3], alpha=1.0)
    
    poly = Poly3DCollection(faces, facecolors=[face_color]*len(faces),
                            edgecolors='none', linewidths=0)
    ax.add_collection3d(poly)

def build_plotly_cylinder_mesh(xs, ys, zs, radius=3.0, sides=8):
    """
    为 Plotly 生成圆柱网格。
    
    返回:
        x, y, z: 顶点坐标数组（展平）
        i, j, k: 三角面索引
    """
    import numpy as np
    
    n_pts = len(xs)
    if n_pts < 2:
        return [], [], [], [], [], []
    
    # 计算切线方向
    tangents = np.zeros((n_pts, 3))
    for i in range(n_pts):
        if i == 0:
            tangents[i] = [xs[1]-xs[0], ys[1]-ys[0], zs[1]-zs[0]]
        elif i == n_pts - 1:
            tangents[i] = [xs[-1]-xs[-2], ys[-1]-ys[-2], zs[-1]-zs[-2]]
        else:
            tangents[i] = [xs[i+1]-xs[i-1], ys[i+1]-ys[i-1], zs[i+1]-zs[i-1]]
        norm = np.linalg.norm(tangents[i])
        if norm > 1e-9:
            tangents[i] /= norm
    
    up = np.array([0, 0, 1])
    angles = np.linspace(0, 2*np.pi, sides, endpoint=False)
    
    # 构建所有顶点
    vertices = []
    for i in range(n_pts):
        t = tangents[i]
        up_ref = np.array([0, 1, 0]) if abs(np.dot(t, up)) > 0.99 else up
        u = np.cross(t, up_ref)
        u_norm = np.linalg.norm(u)
        u = np.array([1, 0, 0]) if u_norm < 1e-9 else u / u_norm
        v = np.cross(t, u)
        
        center = np.array([xs[i], ys[i], zs[i]])
        for a in angles:
            p = center + radius * (np.cos(a) * u + np.sin(a) * v)
            vertices.append(p)
    
    vertices = np.array(vertices)
    
    # 构建三角面
    faces_i, faces_j, faces_k = [], [], []
    for i in range(n_pts - 1):
        for k in range(sides):
            k_next = (k + 1) % sides
            idx1 = i * sides + k
            idx2 = i * sides + k_next
            idx3 = (i+1) * sides + k_next
            idx4 = (i+1) * sides + k
            # 两个三角形
            faces_i.extend([idx1, idx1])
            faces_j.extend([idx2, idx3])
            faces_k.extend([idx3, idx4])
    
    return (vertices[:, 0].tolist(), vertices[:, 1].tolist(), vertices[:, 2].tolist(),
            faces_i, faces_j, faces_k)


def build_boundary_wall_mesh(X, Y, Z_top, Z_bot, color_str, max_vertices=80):
    """
    为地质体构建侧面墙体 Mesh3d trace。
    沿凸包边界连接顶面和底面，形成闭合的侧墙。

    参数:
        X, Y: shape=(grid_res, grid_res) 的 2D 网格坐标
        Z_top, Z_bot: shape=(grid_res, grid_res) 的顶/底面高程，NaN 表示无效区域
        color_str: 'rgb(r,g,b)' 颜色字符串
        max_vertices: 边界顶点数上限（降采样），默认 80

    返回:
        go.Mesh3d trace，或 None（有效点不足以构成边界时）
    """
    valid = ~np.isnan(Z_top)
    n_valid = int(np.sum(valid))
    if n_valid < 3:
        return None

    xv = X[valid]
    yv = Y[valid]
    zv_top = Z_top[valid]
    zv_bot = Z_bot[valid]

    points = np.column_stack([xv, yv])

    try:
        hull = ConvexHull(points)
    except Exception:
        return None

    hull_vertices = hull.vertices
    n_boundary = len(hull_vertices)

    if n_boundary < 3:
        return None

    # 降采样：最多 max_vertices 个边界顶点
    if n_boundary > max_vertices:
        step = max(1, n_boundary // max_vertices)
        hull_vertices = hull_vertices[::step]
        n_boundary = len(hull_vertices)
        if n_boundary < 3:
            return None

    bx = xv[hull_vertices]       # 边界 X 坐标
    by = yv[hull_vertices]       # 边界 Y 坐标
    bz_top = zv_top[hull_vertices]  # 边界顶面 Z
    bz_bot = zv_bot[hull_vertices]  # 边界底面 Z

    # 构建顶点数组：上环（0..N-1）+ 下环（N..2N-1）
    vx = np.concatenate([bx, bx])
    vy = np.concatenate([by, by])
    vz = np.concatenate([bz_top, bz_bot])

    # 构建三角面（quad strip，与 build_plotly_cylinder_mesh 模式一致）
    faces_i, faces_j, faces_k = [], [], []
    for i in range(n_boundary):
        i_next = (i + 1) % n_boundary
        # 顶环点 i, i_next，底环点 n_boundary+i_next, n_boundary+i
        # 三角 1: top_i, top_{i+1}, bot_{i+1}
        faces_i.append(i)
        faces_j.append(i_next)
        faces_k.append(n_boundary + i_next)
        # 三角 2: top_i, bot_{i+1}, bot_i
        faces_i.append(i)
        faces_j.append(n_boundary + i_next)
        faces_k.append(n_boundary + i)

    return go.Mesh3d(
        x=vx, y=vy, z=vz,
        i=faces_i, j=faces_j, k=faces_k,
        color=color_str,
        opacity=0.85,
        flatshading=True,
        showscale=False,
        showlegend=False,
        hoverinfo='skip',
        name=''
    )

# ==================== 轨迹计算 ====================
def compute_trajectory(df_survey):
    """
    根据测斜数据计算钻孔轨迹点（逐段使用对应测点的角度）
    
    坐标约定：
    - X 轴：东向（Easting）
    - Y 轴：北向（Northing）
    - Z 轴：高程（Elevation，向下为负）
    - 方位角：0° = 正北，顺时针增加
    
    返回: lengths (沿钻孔长度), xs (东向), ys (北向), zs (高程)
    """
    # 按长度升序排列
    df = df_survey.sort_values('各层位长度', ascending=True)
    
    # 去重：相同长度只保留第一条
    df = df.drop_duplicates(subset=['各层位长度'], keep='first')
    
    lengths = df['各层位长度'].values
    az = np.radians(df['方位角'].values)
    inc = np.radians(np.abs(df['倾角'].values))   # 取绝对值，兼容正负号
    
    # 起始点（孔口）
    xs = [0.0]
    ys = [0.0]
    zs = [0.0]
    
    for i in range(1, len(lengths)):
        delta = lengths[i] - lengths[i-1]
        # 垂向位移（用终点 i 的倾角）
        dz = -delta * np.sin(inc[i])
        # 水平位移
        horiz = delta * np.cos(inc[i])
        # 分解为东向和北向（用终点 i 的方位角）
        dx = horiz * np.sin(az[i])   # 东向 → X
        dy = horiz * np.cos(az[i])   # 北向 → Y
        xs.append(xs[-1] + dx)
        ys.append(ys[-1] + dy)
        zs.append(zs[-1] + dz)
    
    return lengths, np.array(xs), np.array(ys), np.array(zs)

def get_interpolated_coords(lengths, xs, ys, zs, target_lengths):
    """线性插值获得轨迹点"""
    interp_x = interp1d(lengths, xs, kind='linear', fill_value='extrapolate')
    interp_y = interp1d(lengths, ys, kind='linear', fill_value='extrapolate')
    interp_z = interp1d(lengths, zs, kind='linear', fill_value='extrapolate')
    return interp_x(target_lengths), interp_y(target_lengths), interp_z(target_lengths)


# 圆柱采样点抽稀容差（米）：轴线偏离原轨迹的上限。
# 远小于钻孔半径（默认 3.0 m）与坐标显示精度（0.01 m），肉眼不可分辨。
CYLINDER_SIMPLIFY_TOL = 0.05


def simplify_trajectory_points(xs, ys, zs, tol=CYLINDER_SIMPLIFY_TOL):
    """
    按曲率自适应抽稀钻孔轨迹采样点（Douglas-Peucker，三维垂距判据）。

    背景：圆柱按固定 0.5 m 间距布环，一个 50 m 的岩性段会采出约 100 个环。
    垂直孔的轨迹在数学上是一条直线，这 100 个环的圆心完全共线、截面平行，
    中间 98 个环对曲面毫无贡献，却让每个圆柱白白多出约 800 个顶点和 4700 个
    三角面索引——这是生成页面里最大的一块冗余。

    做法：以「点到首尾弦的垂距」为判据递归取拐点，首尾点必然保留
    （相邻岩性段的圆柱仍在原处无缝相接）。直线段只留两端点，弯曲段按曲率
    自动保留拐点，任何位置轴线偏移都不超过 tol。点数不足 3 点时原样返回。

    返回新的 (xs, ys, zs)，与入参同为 numpy 数组。
    """
    pts = np.column_stack([np.asarray(xs, dtype=float),
                           np.asarray(ys, dtype=float),
                           np.asarray(zs, dtype=float)])
    n = len(pts)
    if n <= 2 or tol <= 0:
        return xs, ys, zs

    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = pts[b] - pts[a]
        seg_len = np.linalg.norm(seg)
        if seg_len < 1e-12:
            # 首尾重合的退化段：退化为点到点的距离
            dist = np.linalg.norm(pts[a + 1:b] - pts[a], axis=1)
        else:
            dist = np.linalg.norm(np.cross(pts[a + 1:b] - pts[a], seg), axis=1) / seg_len
        m = int(np.argmax(dist))
        if dist[m] > tol:
            idx = a + 1 + m
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))

    return pts[keep, 0], pts[keep, 1], pts[keep, 2]


def plot_drill_holes_on_ax(ax, loc_df, survey_df, litho_df,
                            legend_labels=None, show_labels=True, show_legend=True,
                            drill_style=None, drill_radius=None):
    """
    在给定的 3D 坐标轴上绘制所有钻孔轨迹和岩性段。

    参数:
        ax: matplotlib 3D 坐标轴
        loc_df: 定位表 DataFrame
        survey_df: 测斜表 DataFrame
        litho_df: 岩性表 DataFrame
        legend_labels: 已存在的图例集合（set），用于去重。若为 None 则新建。
        show_labels: 是否显示钻孔编号
        show_legend: 是否收集图例信息（不创建3D代理线，由调用者通过2D Line2D构建图例）
        drill_style: 钻孔样式 ('cylinder'|'line')，None=使用config默认值
        drill_radius: 钻孔半径（米），None=使用config默认值
    返回:
        (legend_labels, legend_entries): legend_labels 为去重后的岩性名称集合，
            legend_entries 为 [(lith_name, color_rgb), ...] 列表（按首次出现顺序）
    """
    from config import (DRILL_STYLE as CFG_STYLE, DRILL_RADIUS as CFG_RADIUS,
                        DRILL_FORCE_LINE_THRESHOLD, DRILL_DEGRADE_THRESHOLD)

    if drill_style is None:
        drill_style = CFG_STYLE
    if drill_radius is None:
        drill_radius = CFG_RADIUS

    if legend_labels is None:
        legend_labels = set()

    legend_entries = []  # 按首次出现顺序收集 (lith_name, color_rgb)

    total_segments = len(litho_df)

    if drill_style == 'line' or total_segments > DRILL_FORCE_LINE_THRESHOLD:
        use_style = 'line'
        if total_segments > DRILL_FORCE_LINE_THRESHOLD:
            print(f"==> 钻孔段数 {total_segments} 超过强制阈值 {DRILL_FORCE_LINE_THRESHOLD}，使用极简线段模式")
    elif total_segments > DRILL_DEGRADE_THRESHOLD:
        use_style = 'line'
        print(f"==> 钻孔段数 {total_segments} 超过降级阈值 {DRILL_DEGRADE_THRESHOLD}，自动降级为线段模式")
    else:
        use_style = drill_style
        print(f"==> 钻孔绘制模式: {use_style}（共 {total_segments} 段）")

    hole_ids = loc_df['钻孔编号'].unique()

    for hid in hole_ids:
        row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
        x0 = row['开孔坐标N']
        y0 = row['开孔坐标E']
        z0 = row['开孔高程R']

        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) == 0:
            continue

        lengths, xs, ys, zs = compute_trajectory(surv)
        xs = xs + x0
        ys = ys + y0
        zs = zs + z0

        # 钻孔中心线（虚线）
        ax.plot(xs, ys, zs, color='gray', linewidth=1, alpha=0.3, linestyle='--')

        # 岩性段
        litho = litho_df[litho_df['钻孔编号'] == hid].sort_values(
            '上层位长度起始刻度', ascending=True)

        for idx, seg in litho.iterrows():
            d_top = seg['上层位长度起始刻度']
            d_bot = seg['下层位长度起始刻度']
            lith_name = seg['岩性描述']
            color = parse_color(seg['建模颜色'], lith_name)

            if d_top < lengths[0]:
                d_top = lengths[0]
            if d_bot > lengths[-1]:
                d_bot = lengths[-1]
            if d_top >= d_bot:
                continue

            d_sample = np.linspace(d_top, d_bot, max(3, int((d_bot - d_top) / 0.5)))
            x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)

            # 收集图例信息（不创建 3D 代理线，避免影响深度排序）
            if show_legend and (lith_name not in legend_labels):
                legend_labels.add(lith_name)
                legend_entries.append((lith_name, color[:3]))

            # 根据 use_style 选择绘制方式
            if use_style == 'cylinder':
                plot_cylinder_segment(ax, x, y, z, color,
                                    radius=drill_radius,
                                    sides=DRILL_CYLINDER_SIDES)
            else:
                # 线段模式（不带 label，避免生成 3D 代理线影响深度排序）
                ax.plot(x, y, z, color=color[:3], alpha=color[3], linewidth=6)

        # 钻孔编号
        if show_labels:
            ax.text(x0, y0, z0 + 3, hid, color='black', fontsize=12,
                    ha='center', va='bottom', weight='bold')

    return legend_labels, legend_entries

# 增加水印
def add_view_label_watermark(fig, label=''):
    """在 figure 左上角绘制视图名称水印"""
    if not label:
        return
    fig.text(
        0.02, 0.98, label,
        fontsize=16, fontweight='bold', color='#1a237e',
        ha='left', va='top',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='#1a237e', linewidth=2, alpha=0.95),
        zorder=10000
    )

def draw_single_model_view(volume_data, loc_df, survey_df, litho_df,
                            view_config, output_dir, base_name, labeled=True,
                            drill_style=None, drill_radius=None):
    """
    绘制单个视角的三维地质体模型图。

    参数:
        volume_data: build_geological_bodies_with_volume_v2 返回的体数据
        view_config: {'name': ..., 'label': ..., 'elev': ..., 'azim': ...}
        labeled: True → 带钻孔、图例、完整坐标轴；False → 仅地质体+Z轴
        drill_style: 钻孔样式，None=使用config默认值
        drill_radius: 钻孔半径，None=使用config默认值
    返回:
        保存的图片路径
    """
    fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax = fig.add_subplot(111, projection='3d')
    
    # 1. 绘制地质体（始终绘制）
    for lith, data in volume_data.items():
        color = data['color']
        color_rgb = color[:3]
        layers = data['layers']
        if not layers:
            continue
        for k, Z in enumerate(layers):
            opacity = 0.2 + 0.5 * (k / (len(layers) - 1)) if len(layers) > 1 else 0.5
            ax.plot_surface(
                data['X'], data['Y'], Z,
                color=color_rgb,
                alpha=opacity,
                edgecolor='none'
            )
    
    # 2. 绘制钻孔（仅标注版，无标注版不绘制钻孔）
    if labeled:
        legend_labels, legend_entries = plot_drill_holes_on_ax(
            ax, loc_df, survey_df, litho_df,
            legend_labels=set(),
            show_labels=True,
            show_legend=True,
            drill_style=drill_style,
            drill_radius=drill_radius
        )
        if legend_entries:
            from matplotlib.lines import Line2D
            legend_handles = [
                Line2D([0], [0], color=color, linewidth=6, label=name)
                for name, color in legend_entries
            ]
            ax.legend(handles=legend_handles, loc='upper right', fontsize=8)
    
    # 3. 坐标轴样式
    if labeled:
        # 标注版：完整坐标轴，透明背景 + 网格线
        # 注意方向：体数据按「X=N, Y=E」约定构建（见 build_geological_bodies_with_volume_v2
        # 的归一化注释），而 plot_surface 是 plot_surface(X, Y, Z)——即 X 轴画的是
        # 开孔坐标N、Y 轴画的是开孔坐标E。此处标题必须与之一致（原先两者写反了）。
        ax.set_xlabel('开孔坐标N (m)')
        ax.set_ylabel('开孔坐标E (m)')
        ax.set_zlabel('海拔高度 (m)')
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.grid(True, alpha=0.3)
    else:
        # ========== 无标注版：仅保留 Z 轴 + 深度标尺 ==========
        # 隐藏所有轴（仅保留 Z 轴线+刻度）
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlabel(''); ax.set_ylabel('')
        ax.tick_params(axis='x', which='both', length=0, labelbottom=False)
        ax.tick_params(axis='y', which='both', length=0, labelleft=False)
        ax.xaxis.line.set_visible(False)
        ax.yaxis.line.set_visible(False)
        ax.xaxis.pane.set_visible(False)
        ax.yaxis.pane.set_visible(False)
        ax.zaxis.pane.set_visible(False)

        # 保留 Z 轴（高程），刻度加大加粗，更清晰
        ax.set_zlabel('海拔高度 (m)', fontsize=12, fontweight='bold', labelpad=10)
        ax.tick_params(axis='z', labelsize=11, length=6, width=1.5, colors='#333')
        ax.zaxis.line.set_visible(True)

        # 让 Z 轴刻度自动生成清晰的刻度值
        ax.zaxis.set_tick_params(pad=5)

        # 关闭网格
        ax.grid(False)

    # 4. 计算范围（基于 volume_data 与钻孔数据）
        # 4. 范围（稳健计算，避免异常值污染刻度）
    all_x, all_y, all_z = [], [], []
    for data in volume_data.values():
        all_x.extend(data['X'].ravel())
        all_y.extend(data['Y'].ravel())
        for layer in data['layers']:
            valid = layer[~np.isnan(layer)]
            all_z.extend(valid.tolist())

    if all_x and all_y and all_z:
        # 过滤 NaN 后再转为数组
        all_z_arr = np.array(all_z)
        all_z_arr = all_z_arr[~np.isnan(all_z_arr)]

        # X 和 Y 用普通极值（它们的值都在合理范围内）
        margin = 20
        ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
        ax.set_ylim(min(all_y) - margin, max(all_y) + margin)

        # Z 用 1% 和 99% 分位数（稳健，避免极端外推值影响）
        if len(all_z_arr) > 10:
            z_min_v = np.percentile(all_z_arr, 1)
            z_max_v = np.percentile(all_z_arr, 99)
        else:
            z_min_v = all_z_arr.min()
            z_max_v = all_z_arr.max()

        # 加 10% 的上下余量
        z_margin = (z_max_v - z_min_v) * 0.1
        ax.set_zlim(z_min_v - z_margin, z_max_v + z_margin)

        # 关闭科学计数法/偏移量，并统一为「普通整数」（如 3123457）
        ax.ticklabel_format(style='plain', axis='x', useOffset=False)
        ax.ticklabel_format(style='plain', axis='y', useOffset=False)
        ax.ticklabel_format(style='plain', axis='z', useOffset=False)
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.0f'))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.0f'))
        ax.zaxis.set_major_formatter(FormatStrFormatter('%.0f'))

        # 旋转 X 轴刻度，避免密集时重叠
        ax.tick_params(axis='x', labelsize=8, rotation=15)
        ax.tick_params(axis='y', labelsize=8, rotation=-15)
        ax.tick_params(axis='z', labelsize=9)

    # 5. 视角与保存
    ax.view_init(elev=view_config['elev'], azim=view_config['azim'])

    # ========== 添加视角名称水印 ==========
    order = view_config.get('order', 0)
    view_label = view_config.get('label', '')
    if view_label:
        add_view_label_watermark(fig, view_label)

    # ========== 保存（文件名带序号前缀） ==========
    # tight_layout 在无标注版（隐藏 X/Y 轴）会报 'bboxes' cannot be empty
    try:
        plt.tight_layout(pad=0.5)
    except ValueError:
        pass  # 无标注版轴隐藏时无法计算 bbox，跳过
    
    suffix = '_labeled' if labeled else '_unlabeled'
    order_prefix = f'{order:02d}_' if order > 0 else ''
    fname = f'{base_name}{suffix}_{order_prefix}{view_config["name"]}.png'
    save_path = os.path.join(output_dir, fname)

    # ========== 在图片右侧绘制高程标尺条（仅无标注版） ==========
    # if not labeled and all_z:
    #     z_max_val = max(all_z)
    #     z_min_val = min(all_z)
    #     # 显示高度范围
    #     fig.text(
    #         0.90, 0.10,
    #         f'高程范围\n{z_min_val:.0f} ~ {z_max_val:.0f} m',
    #         fontsize=10, color='#333',
    #         ha='center', va='bottom',
    #         bbox=dict(boxstyle='round,pad=0.4',
    #                   facecolor='#f5f5f5', edgecolor='#999',
    #                   linewidth=1, alpha=0.9)
    #     )
         
    #     # 在 figure 右侧添加一个辅助坐标轴绘制标尺
    #     # [左, 下, 宽, 高] 归一化坐标
    #     cax = fig.add_axes([0.90, 0.25, 0.025, 0.5])
        
    #     # 生成一个渐变色条（从亮到暗，模拟深度）
    #     gradient = np.linspace(1, 0, 256).reshape(-1, 1)
    #     cax.imshow(gradient, aspect='auto', cmap='gray_r',
    #                extent=[0, 1, z_min_val, z_max_val])
        
    #     # 设置标尺的刻度和标签
    #     cax.set_xticks([])
    #     cax.set_yticks(np.linspace(z_min_val, z_max_val, 6))
    #     cax.set_yticklabels(
    #         [f'{v:.0f}' for v in np.linspace(z_min_val, z_max_val, 6)],
    #         fontsize=10
    #     )
    #     cax.yaxis.tick_right()
    #     cax.yaxis.set_label_position('right')
    #     cax.set_ylabel('Elevation (m)', fontsize=11, fontweight='bold',
    #                    rotation=270, labelpad=20)
    #     cax.tick_params(axis='y', length=4, width=1.2)
        
    #     # 边框
    #     for spine in cax.spines.values():
    #         spine.set_linewidth(1.2)
    #         spine.set_color('#333')

    plt.savefig(save_path, dpi=FIGURE_DPI, pad_inches=0, facecolor='white')
    plt.close()
    return save_path    

# ==================== 钻孔示意图生成 ====================
def generate_drill_views(loc_df, survey_df, litho_df, output_dir, base_name):
    """生成多角度钻孔示意图（仅钻孔，无地质体）"""
    views_configs = VIEW_CONFIGS
    
    results = []
    # 坐标一律使用钻孔表里的绝对值（与 generate_drill_model_only 同一套坐标系）。
    # 原先这里把 N/E 各减去最小值平移到相对坐标系，图上轴读数（0、100、200…）
    # 与钻孔表对不上；平移只是整体挪动，对图形形状、视角、比例毫无影响，
    # 因此取消平移不改变任何视觉要素，只让轴读数与钻孔表逐值对应。
    for config in views_configs:
        fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
        ax = fig.add_subplot(111, projection='3d')
        
        # 复用统一的钻孔绘制函数
        legend_labels, legend_entries = plot_drill_holes_on_ax(
            ax, loc_df, survey_df, litho_df,
            legend_labels=set(),
            show_labels=True,
            show_legend=True
        )

        ax.set_xlabel('北 (m)')
        ax.set_ylabel('东 (m)')
        ax.set_zlabel('海拔 (m)')
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.grid(True, alpha=0.3)
        ax.view_init(elev=config['elev'], azim=config['azim'])

        all_n = loc_df['开孔坐标N'].values
        all_e = loc_df['开孔坐标E'].values
        margin = 20
        ax.set_xlim(all_n.min() - margin, all_n.max() + margin)
        ax.set_ylim(all_e.min() - margin, all_e.max() + margin)

        # 坐标刻度统一为「普通整数」（如 3123457）：
        # 关掉科学计数法与 matplotlib 默认的大数偏移量（1e6），并去掉小数位。
        ax.ticklabel_format(style='plain', axis='x', useOffset=False)
        ax.ticklabel_format(style='plain', axis='y', useOffset=False)
        ax.ticklabel_format(style='plain', axis='z', useOffset=False)
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.0f'))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.0f'))
        ax.zaxis.set_major_formatter(FormatStrFormatter('%.0f'))

        if legend_entries:
            # 使用 2D Line2D 构建图例
            from matplotlib.lines import Line2D
            legend_handles = [
                Line2D([0], [0], color=color, linewidth=6, label=name)
                for name, color in legend_entries
            ]
            ax.legend(handles=legend_handles, loc='upper right', fontsize=8)
        
        plt.title(f'钻孔示意图 - {config["label"]}', fontsize=14)
        plt.tight_layout()
        
        fname = f'{base_name}_{config["name"]}.png'
        save_path = os.path.join(output_dir, fname)
        plt.savefig(save_path, dpi=FIGURE_DPI, bbox_inches='tight')
        plt.close()
        
        results.append({
            'name': config['name'],
            'label': config['label'],
            'path': save_path,
            'url': f'/outputs/{os.path.basename(save_path)}'
        })
    
    return results

# ==================== 页面体积优化：坐标圆整 ====================
def _round_nested_coords(value, ndigits=2):
    """递归圆整坐标数组（兼容 None 缺失值、NaN、以及一维/二维数组）。"""
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return np.round(value, ndigits)
    if isinstance(value, (list, tuple)):
        try:
            arr = np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            arr = None          # 含 None 等非数字项 → 逐项递归
        if arr is not None:
            return np.round(arr, ndigits).tolist()
        return [_round_nested_coords(v, ndigits) for v in value]
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if num != num:              # NaN 保持原样（序列化后即 null）
        return value
    return round(num, ndigits)


def round_figure_coords_for_html(fig, ndigits=2):
    """把即将写进 HTML 的图数据圆整到厘米级（保留两位小数）。

    只在序列化之前调用，用于压缩页面体积：模型页里的坐标数字约占整体的 88%，
    按全精度输出（如 3123456.7890123456）会让单个 HTML 膨胀数 MB。
    圆整精度 0.01 m 远小于网格间距和钻孔半径，视觉上无法分辨；
    体积估算、框图范围、分层观察取值都来自 geobody-grid-data 中的网格数据，
    而不是本图里的坐标副本，因此计算结果不受影响。
    """
    for trace in fig.data:
        for axis in ('x', 'y', 'z'):
            try:
                values = trace[axis]
            except (KeyError, AttributeError, ValueError):
                continue
            if values is None:
                continue
            trace[axis] = _round_nested_coords(values, ndigits)


# ==================== 页面体积优化：plotly.js 共享一份 ====================
# 每个生成页原本都内嵌一份 plotly.js（3.60 MB），而各页内嵌的是完全相同的
# 同一份文件；坐标圆整 + 圆柱抽稀之后 figure 数据只剩 0.64 MB，plotly.js
# 反而占了页面的 85%。改为引用 static/js/plotly.min.js：浏览器只下载一次、
# 之后每次打开只需一次 304 校验，生成页体积直接少 3.60 MB。
# 该文件由当前安装的 plotly 导出，内容与原先内嵌的逐字节相同（见
# tools/export_plotlyjs.py）；文件不存在时自动退回内嵌，功能不受影响。
PLOTLYJS_URL = '/static/js/plotly.min.js'
PLOTLYJS_REL_PATH = os.path.join('js', 'plotly.min.js')


def shared_plotlyjs_available():
    """共享 plotly.js 是否可用（不可用时调用方退回内嵌）。"""
    try:
        return os.path.isfile(os.path.join(STATIC_FOLDER, PLOTLYJS_REL_PATH))
    except Exception:
        return False


def _plotly_html_kwargs():
    """
    返回 write_html 的 include_plotlyjs 参数。

    可用时传共享文件的 URL：plotly 对「以 .js 结尾的字符串」有原生支持，
    会照原次序输出 window.PlotlyConfig（MathJaxConfig='local'）→
    <script src=共享文件> → Plotly.newPlot，除 plotly.js 的来源外与内嵌完全等价。
    共享文件不可用时传 True，退回内嵌，功能不受影响。
    """
    return {'include_plotlyjs': (PLOTLYJS_URL if shared_plotlyjs_available() else True)}


# ==================== 面板脚本抽成独立文件 ====================
# 「分层观察 / 岩性显隐 / 钻孔显隐」和「体积估算」这两段脚本原先由 processors.py 以
# f-string 逐页拼进 HTML：每生成一个页面就多内嵌一份完全相同的代码（约 23 KB），
# 而且 JS 的大括号在 f-string 里必须写成 {{ }}，极易出错。
# 现改为独立文件，页面只内联一个参数对象（几百字节）+ 一条 <script src>：
#   浏览器只需下载一次（之后各页命中缓存），JS 也能单独做语法检查。
LAYER_PANEL_JS_URL = '/static/js/layer_panel.js'
VOLUME_PANEL_JS_URL = '/static/js/volume_panel.js'
# 与 URL 对应的磁盘相对路径（data_handler 里用同一套 gzip + 缓存校验通道提供这两个文件）
LAYER_PANEL_JS_REL_PATH = os.path.join('js', 'layer_panel.js')
VOLUME_PANEL_JS_REL_PATH = os.path.join('js', 'volume_panel.js')


# ==================== 公共绘图片段（交互式页 / 钻孔专用页共用） ====================
# 两个模型页的「钻孔部分」逐行同源（已核对：除坐标原点、注释与空格之外完全一致），
# 抽成下面的两个函数，避免同一段逻辑维护两份。
def compute_drill_z_axis(loc_df, survey_df, hole_ids):
    """
    由所有钻孔轨迹点（含各孔开孔高程）计算数据驱动的 Z 轴范围。

    返回 (z_min_data, z_max_data, z_range_min, z_range_max)：前两个是钻点自身的
    Z 极值（交互式页还要用它给图例占位点定位），后两个是按既有规则给 Z 轴上下
    各留 10%（至少 5 m）余量后的轴范围。

    与抽公共代码前的两处实现逐位同源：仍按 hole_ids 的顺序遍历、仍以
    「开孔高程 + 轨迹点」的顺序累加，余量规则一字未改。
    """
    all_z_pts = list(loc_df['开孔高程R'].values)
    for hid in hole_ids:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            _, _, _, zs = compute_trajectory(surv)
            row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
            zs += row['开孔高程R']
            if len(zs) > 0:
                all_z_pts.extend(zs.tolist())

    all_z_arr = np.array(all_z_pts)
    z_min_data = np.min(all_z_arr)
    z_max_data = np.max(all_z_arr)
    z_margin = max((z_max_data - z_min_data) * 0.1, 5)
    return z_min_data, z_max_data, z_min_data - z_margin, z_max_data + z_margin


def add_drill_traces(fig, loc_df, survey_df, litho_df, hole_ids, use_style, drill_radius):
    """
    把钻孔轨迹追加到 fig：每孔一条灰色虚线轴线 + 若干分段岩性 + 孔口编号文字。

    坐标一律使用钻孔表里的绝对值（开孔坐标N / 开孔坐标E / 开孔高程R），不做任何
    原点平移——这样页面上的 X/Y 轴读数与钻孔表逐值对应。原先「钻孔专用页按
    (N.min(), E.min()) 平移」的做法已取消（平移对形状无影响，却使轴读数与钻孔表
    对不上），两种页面现在用同一个坐标系。

    不返回值：调用方需要的 trace 索引仍由 fig.data 的长度得出。
    """
    for hid in hole_ids:
        row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
        x0 = row['开孔坐标N']
        y0 = row['开孔坐标E']
        z0 = row['开孔高程R']

        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) == 0:
            continue

        lengths, xs, ys, zs = compute_trajectory(surv)
        xs += x0
        ys += y0
        zs += z0

        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode='lines',
            line=dict(color='gray', width=1, dash='dash'),
            showlegend=False,
            hoverinfo='skip'
        ))

        litho = litho_df[litho_df['钻孔编号'] == hid].sort_values(
            '上层位长度起始刻度', ascending=True)

        for _, seg in litho.iterrows():
            d_top = seg['上层位长度起始刻度']
            d_bot = seg['下层位长度起始刻度']
            lith_name = seg['岩性描述']
            color = parse_color(seg['建模颜色'], lith_name)

            if d_top < lengths[0]:
                d_top = lengths[0]
            if d_bot > lengths[-1]:
                d_bot = lengths[-1]
            if d_top >= d_bot:
                continue

            d_sample = np.linspace(d_top, d_bot, max(3, int((d_bot - d_top) / 0.5)))
            x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)
            # 按曲率抽稀采样点：直线段只留两端点，弯曲段保留拐点（轴线偏移 ≤0.05 m）
            x, y, z = simplify_trajectory_points(x, y, z)
            if len(x) == 0:
                continue

            alpha = color[3]
            color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'

            if use_style == 'cylinder':
                # 生成 Plotly 圆柱网格
                cyl_x, cyl_y, cyl_z, cyl_i, cyl_j, cyl_k = build_plotly_cylinder_mesh(
                    x, y, z, radius=drill_radius, sides=DRILL_CYLINDER_SIDES
                )
                fig.add_trace(go.Mesh3d(
                    x=cyl_x, y=cyl_y, z=cyl_z,
                    i=cyl_i, j=cyl_j, k=cyl_k,
                    color=color_str,
                    opacity=alpha,
                    flatshading=True,
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.2f}}m<extra></extra>'
                ))
            else:
                # 原有线段模式
                fig.add_trace(go.Scatter3d(
                    x=x, y=y, z=z,
                    mode='lines',
                    line=dict(color=f'rgba({int(color[0]*255)},{int(color[1]*255)},{int(color[2]*255)},{alpha})', width=6),
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.2f}}m<extra></extra>'
                ))

        fig.add_trace(go.Scatter3d(
            x=[x0], y=[y0], z=[z0 + 3],
            mode='text',
            text=[hid],
            textfont=dict(size=12, color='black', family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))


# ==================== 交互式模型生成（钻孔专用） ====================
def generate_drill_model_only(loc_df, survey_df, litho_df, output_dir, base_name,
                               drill_style=None, drill_radius=None):
    """
    生成仅展示钻孔轨迹（不含地质体）的交互式3D模型。
    参数含义同 generate_interactive_model。
    """
    from config import (DRILL_STYLE as CFG_STYLE, DRILL_RADIUS as CFG_RADIUS,
                        DRILL_FORCE_LINE_THRESHOLD, DRILL_DEGRADE_THRESHOLD)

    if drill_style is None:
        drill_style = CFG_STYLE
    if drill_radius is None:
        drill_radius = CFG_RADIUS

    hole_ids = loc_df['钻孔编号'].unique()

    # 收集所有钻点 Z 值，用于计算数据驱动的 Z 范围
    _, _, z_range_min, z_range_max = compute_drill_z_axis(loc_df, survey_df, hole_ids)

    total_segments = len(litho_df)

    if drill_style == 'line' or total_segments > DRILL_FORCE_LINE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly(钻孔专用): 使用线段模式（段数 {total_segments}）")
    elif total_segments > DRILL_DEGRADE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly(钻孔专用): 段数 {total_segments} 超降级阈值，使用线段模式")
    else:
        use_style = drill_style
        print(f"==> Plotly(钻孔专用): 使用 {use_style} 模式（段数 {total_segments}）")

    fig = go.Figure()

    # ==== 仅绘制钻孔（无地质体），使用钻孔表里的绝对坐标 ====
    add_drill_traces(fig, loc_df, survey_df, litho_df, hole_ids, use_style, drill_radius)

    margin = 20
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    fig.update_layout(
        scene=dict(
            # 坐标刻度统一用「普通整数」（如 3123457）：exponentformat='none' 关掉
            # Plotly 默认的 SI 缩写（3.1825M / 523.55K），tickformat='.0f' 去掉小数位。
            # hoverformat 仍是两位小数：悬停时用来看精确值（只有未定 hovertemplate 的
            # trace 才会用到；钻孔 trace 自带 hovertemplate，不受它影响）。
            xaxis=dict(title='北 (m)', range=[all_n.min() - margin, all_n.max() + margin],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            yaxis=dict(title='东 (m)', range=[all_e.min() - margin, all_e.max() + margin],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            zaxis=dict(title='海拔 (m)', range=[z_range_min, z_range_max],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            aspectmode='data',
            bgcolor='rgba(0,0,0,0)',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.0),
                center=dict(x=0, y=0, z=0)
            )
        ),
        autosize=True,
        title='交互式钻孔模型',
        legend=dict(
            x=1.02, y=1, xanchor='left', yanchor='top', font=dict(size=11)
        ),
        margin=dict(l=5, r=5, t=40, b=5),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )

    html_path = os.path.join(output_dir, f'{base_name}.html')
    # 写盘前把坐标圆整到厘米级，压缩页面体积（不影响任何计算与交互）
    round_figure_coords_for_html(fig)
    fig.write_html(html_path, config={
        'responsive': True,
        'scrollZoom': True,
        'displayModeBar': True
    }, **_plotly_html_kwargs())
    return html_path


# ==================== 网格数据序列化（体积估算用） ====================
def _serialize_grid_data(bodies):
    """
    将 bodies 网格数据序列化为紧凑 JSON，嵌入 Plotly HTML 供体积估算使用。

    参数:
        bodies: build_geological_bodies_with_volume_v2 返回的 bodies dict
               {lith: {X(2D), Y(2D), Z_top(2D), Z_bot(2D), color(r,g,b,a)}}
    返回:
        '<script id="geobody-grid-data" type="application/json">{...}</script>' 字符串
    """
    if not bodies:
        return ''

    import math

    first = next(iter(bodies.values()))
    X, Y = first['X'], first['Y']
    nx, ny = X.shape[1], X.shape[0]
    dx = float(X[0, 1] - X[0, 0]) if nx > 1 else 0
    dy = float(Y[1, 0] - Y[0, 0]) if ny > 1 else 0
    x_min = float(X[0, 0])
    x_max = float(X[0, -1])
    y_min = float(Y[0, 0])
    y_max = float(Y[-1, 0])

    z_data = {}
    colors = {}
    for lith, body in bodies.items():
        # 只存 Z_top 和 Z_bot，NaN 序列化为 null
        def _to_float_or_none(v):
            return None if math.isnan(v) else float(v)

        z_top_list = [[_to_float_or_none(v) for v in row] for row in body['Z_top']]
        z_bot_list = [[_to_float_or_none(v) for v in row] for row in body['Z_bot']]
        z_data[lith] = {
            'z_top': z_top_list,
            'z_bot': z_bot_list
        }
        r, g, b = body['color'][:3]
        colors[lith] = f'rgb({int(r*255)},{int(g*255)},{int(b*255)})'

    grid_dict = {
        'liths': list(bodies.keys()),
        'colors': colors,
        'x_range': [x_min, x_max],
        'y_range': [y_min, y_max],
        'nx': nx, 'ny': ny,
        'dx': dx, 'dy': dy,
        'z_data': z_data
    }
    grid_json = json.dumps(grid_dict, separators=(',', ':'))

    return f'<script id="geobody-grid-data" type="application/json">{grid_json}</script>'


# ==================== 交互式模型生成 ====================
def generate_interactive_model(loc_df, survey_df, litho_df, output_dir, base_name,
                                drill_style=None, drill_radius=None,
                                n_layers=None, rbf_function=None,
                                rbf_smooth=None, grid_resolution=None,
                                method=None, kriging_variogram=None):
    """
    生成可交互式3D模型。

    参数:
        drill_style / drill_radius: 钻孔样式参数，None=使用config默认值
        n_layers / rbf_function / rbf_smooth / grid_resolution: 插值参数，None=使用config默认值
        method: 'rbf' 或 'kriging'，None=使用config默认值
        kriging_variogram: 克里金变异函数模型，None=使用config默认值
    """
    from config import (DRILL_STYLE as CFG_STYLE, DRILL_RADIUS as CFG_RADIUS,
                        DRILL_FORCE_LINE_THRESHOLD, DRILL_DEGRADE_THRESHOLD)

    if drill_style is None:
        drill_style = CFG_STYLE
    if drill_radius is None:
        drill_radius = CFG_RADIUS

    bodies, volume_data = build_geological_bodies_with_volume_v2(
        loc_df, litho_df, survey_df,
        n_layers=n_layers,
        rbf_function=rbf_function,
        rbf_smooth=rbf_smooth,
        grid_resolution=grid_resolution,
        method=method,
        kriging_variogram=kriging_variogram
    )
    
    if not volume_data:
        return None
    
    hole_ids = loc_df['钻孔编号'].unique()
    
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values

    # 收集所有钻点 Z 值，用于计算数据驱动的 Z 范围（z_min_data 另用于给图例占位点定位）
    z_min_data, _, z_range_min, z_range_max = compute_drill_z_axis(loc_df, survey_df, hole_ids)

    total_segments = len(litho_df)

    if drill_style == 'line' or total_segments > DRILL_FORCE_LINE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly: 使用线段模式（段数 {total_segments}）")
    elif total_segments > DRILL_DEGRADE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly: 段数 {total_segments} 超降级阈值，使用线段模式")
    else:
        use_style = drill_style
        print(f"==> Plotly: 使用 {use_style} 模式（段数 {total_segments}）")

    fig = go.Figure()

    # ---- 记录地质体 trace 元信息（仅供分层观察滑块排序使用） ----
    # 格式: [{lith, type: 'surface'|'mesh', z}, ...]
    #  type='surface' → z 是 2D 数组；type='mesh' → z 是 1D 顶点数组
    # 注：坐标不再内嵌进 HTML（前端直接从 Plotly 的 gd.data 取），此处只保留排序需要的 z
    body_meta = []
    lith_layer_counts = {}     # {lith: n_layers}
    lith_trace_map = {}        # {lith: [trace_idx, ...]}  用于岩性显隐开关（不含图例标记）
    trace_idx = 0              # figure-level trace index

    # 绘制地质体：每个岩性 = 一个闭合实体（顶面 + 中间层 + 底面 + 侧面 + 图例标记）
    for lith, body_data in bodies.items():
        color = body_data['color']
        color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'
        vol_data = volume_data.get(lith)
        layers = vol_data['layers'] if vol_data else []
        n_layers_total = len(layers)
        lith_layer_counts[lith] = n_layers_total
        lith_trace_map[lith] = []  # 收集该岩性除图例标记外的所有 trace 索引

        import math

        # ---- 1) 顶面 Surface ----
        z_top = body_data['Z_top']
        show_legend = True
        opacity = 0.55
        fig.add_trace(go.Surface(
            x=body_data['X'], y=body_data['Y'], z=z_top,
            colorscale=[[0, color_str], [1, color_str]],
            opacity=opacity,
            showscale=False,
            showlegend=show_legend,
            name=lith,
            hoverinfo='skip'
        ))
        z_top_safe = [[None if math.isnan(v) else float(v) for v in row] for row in z_top]
        body_meta.append({'lith': lith, 'type': 'surface', 'z': z_top_safe})
        lith_trace_map[lith].append(trace_idx)
        trace_idx += 1
        show_legend = False

        # ---- 2) 中间层 Surface（保留体积感） ----
        for k, Z in enumerate(layers):
            if k == 0 or k == n_layers_total - 1:
                continue
            layer_opacity = 0.15 + 0.35 * (k / (n_layers_total - 1)) if n_layers_total > 1 else 0.3
            fig.add_trace(go.Surface(
                x=vol_data['X'], y=vol_data['Y'], z=Z,
                colorscale=[[0, color_str], [1, color_str]],
                opacity=layer_opacity,
                showscale=False,
                showlegend=False,
                name='',
                hoverinfo='skip'
            ))
            z_safe = [[None if math.isnan(v) else float(v) for v in row] for row in Z]
            body_meta.append({'lith': lith, 'type': 'surface', 'z': z_safe})
            lith_trace_map[lith].append(trace_idx)
            trace_idx += 1

        # ---- 3) 底面 Surface ----
        z_bot = body_data['Z_bot']
        fig.add_trace(go.Surface(
            x=body_data['X'], y=body_data['Y'], z=z_bot,
            colorscale=[[0, color_str], [1, color_str]],
            opacity=opacity,
            showscale=False,
            showlegend=False,
            name='',
            hoverinfo='skip'
        ))
        z_bot_safe = [[None if math.isnan(v) else float(v) for v in row] for row in z_bot]
        body_meta.append({'lith': lith, 'type': 'surface', 'z': z_bot_safe})
        lith_trace_map[lith].append(trace_idx)
        trace_idx += 1

        # ---- 4) 侧面墙体 Mesh3d ----
        wall = build_boundary_wall_mesh(
            body_data['X'], body_data['Y'], z_top, z_bot, color_str
        )
        if wall is not None:
            fig.add_trace(wall)
            z_wall_flat = [None if math.isnan(float(v)) else float(v) for v in wall.z]
            body_meta.append({'lith': lith, 'type': 'mesh', 'z': z_wall_flat})
            lith_trace_map[lith].append(trace_idx)
            trace_idx += 1

        # ---- 5) 图例标记（占位 trace，不参与显隐控制，保持图例始终完整） ----
        dummy_x = all_n.min() - 500
        dummy_y = all_e.min() - 500
        dummy_z = z_min_data - 500
        fig.add_trace(go.Scatter3d(
            x=[dummy_x], y=[dummy_y], z=[dummy_z],
            mode='markers',
            marker=dict(color=color_str, size=10),
            name=lith,
            showlegend=True,
            hoverinfo='skip'
        ))
        trace_idx += 1

    # 记录钻孔起始 trace 索引（用于钻孔显隐开关）
    drill_trace_start = trace_idx

    # 绘制钻孔（绝对坐标：原点偏移为 0）
    add_drill_traces(fig, loc_df, survey_df, litho_df, hole_ids, use_style, drill_radius)

    margin = 20
    x_min, x_max = all_n.min()-margin, all_n.max()+margin
    # 如有多个岩性，预扩 X 范围以容纳分层观察的水平展开
    if len(lith_layer_counts) >= 2:
        x_pad = (x_max - x_min) * 0.4
        x_min -= x_pad
        x_max += x_pad
    fig.update_layout(
        scene=dict(
            # 坐标刻度统一用「普通整数」（如 3123457）：exponentformat='none' 关掉
            # Plotly 默认的 SI 缩写（3.1825M / 523.55K），tickformat='.0f' 去掉小数位。
            # hoverformat 仍是两位小数：悬停时用来看精确值（只有未定 hovertemplate 的
            # trace 才会用到；钻孔 trace 自带 hovertemplate，不受它影响）。
            xaxis=dict(title='开孔坐标N (m)', range=[x_min, x_max],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            yaxis=dict(title='开孔坐标E (m)', range=[all_e.min()-margin, all_e.max()+margin],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            zaxis=dict(title='海拔高度 (m)', range=[z_range_min, z_range_max],
                       showgrid=True, zeroline=False, showbackground=False,
                       tickformat='.0f', hoverformat='.2f', exponentformat='none'),
            aspectmode='data',
            bgcolor='rgba(0,0,0,0)',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.0),
                center=dict(x=0, y=0, z=0)
            )
        ),
        autosize=True,
        title='交互式三维地质体模型',
        legend=dict(
            x=1.02,
            y=1,
            xanchor='left',
            yanchor='top',
            font=dict(size=11)
        ),
        margin=dict(l=5, r=5, t=40, b=5),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )

    html_path = os.path.join(output_dir, f'{base_name}.html')
    # 写盘前把坐标圆整到厘米级，压缩页面体积（不影响任何计算与交互）
    round_figure_coords_for_html(fig)
    fig.write_html(html_path, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': True},
                   div_id='layer-explode-model', **_plotly_html_kwargs())

    # ======== 注入控制面板（分层观察滑块 + 岩性/钻孔显隐，统一 div） ========
    # 读取 HTML 文件
    with open(html_path, 'r') as fh:
        html = fh.read()

    injection_parts = []

    # ---- 控制面板（单一面板，包含分层观察 + 岩性显隐 + 钻孔显隐） ----
    drill_trace_indices = list(range(drill_trace_start, len(fig.data)))
    has_explode = len(lith_layer_counts) >= 2
    has_drills = bool(drill_trace_indices)

    if has_explode or has_drills:
        import math

        # 岩性排序（分层观察和岩性开关共用）
        if has_explode:
            lith_median_z = {}
            for m in body_meta:
                if m['type'] == 'mesh':
                    vals = [v for v in m['z'] if v is not None]
                else:
                    vals = [v for row in m['z'] for v in row if v is not None]
                if vals:
                    lith_median_z.setdefault(m['lith'], []).extend(vals)
            lith_order = sorted(lith_median_z.keys(),
                                key=lambda l: sorted(lith_median_z[l])[len(lith_median_z[l])//2])
            x_range = all_n.max() - all_n.min()
            sep_per_lith = max(x_range * 0.35, 30.0)

        # ---- 构建面板各区块 ----

        # 分层观察滑块行 HTML
        explode_row_html = ''
        if has_explode:
            explode_row_html = (
                '<div class="panel-control-row">'
                '<span title="拖拽滑块将各地层左右展开为独立切片观察">📐 分层观察</span>'
                '<input type="range" id="layer-explode-slider" min="0" max="100" value="0" step="1">'
                '<span id="layer-explode-label">0%</span>'
                '<button id="layer-explode-reset">重置</button>'
                '<button id="vol-btn-activate" class="vol-btn-inline" title="点击激活体积估算工具">📐 体积估算</button>'
                '</div>'
            )

        # 岩性复选框 HTML
        lith_checkboxes_html = ''
        if has_explode:
            for lith in lith_order:
                c = bodies[lith]['color']
                color_css = f'rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})'
                lith_checkboxes_html += (
                    f'<label class="lith-cb-row">'
                    f'<input type="checkbox" class="lith-toggle-cb" value="{lith}" checked>'
                    f'<span class="lith-color-dot" style="background:{color_css}"></span>'
                    f'{lith}</label>'
                )

        # 钻孔开关 HTML
        drill_switch_html = ''
        if has_drills:
            lith_has = 'class="panel-sep"' if has_explode else ''
            drill_switch_html = (
                f'<span {lith_has}></span>'
                '<span style="white-space:nowrap">🔬 钻孔</span>'
                '<label class="drill-switch">'
                '<input type="checkbox" id="drill-toggle" checked>'
                '<span class="drill-slider"></span>'
                '</label>'
            )

        # 显隐开关行 HTML（仅在需要时显示）
        toggle_row_html = ''
        if has_explode or has_drills:
            toggle_row_html = (
                '<div class="panel-control-row panel-toggle-row">'
                f'{lith_checkboxes_html}'
                f'{drill_switch_html}'
                '</div>'
            )

        # ---- 面板脚本的参数 ----
        # 这些值原先直接写进逐页拼的 JS 字面量里；脚本抽成 static/js/layer_panel.js 后，
        # 改由这里的配置对象传入。仍旧按需给键：没有分层观察就不给 lithOrder/sep/lithTraces，
        # 没有钻孔就不给 drill，与原先「按需注入对应分支」的行为一一对应。
        layer_cfg = {}
        if has_explode:
            layer_cfg['lithOrder'] = lith_order
            layer_cfg['sep'] = round(float(sep_per_lith), 2)   # 原为 {sep_per_lith:.2f}
            layer_cfg['lithTraces'] = lith_trace_map
        if has_drills:
            layer_cfg['drill'] = drill_trace_indices

        # ---- 注入面板（样式 + HTML 内联，脚本引用共享文件） ----
        panel_js = f"""<style>
#layer-explode-panel{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(28,28,28,0.9);color:#e0e0e0;padding:6px 20px 8px;border-radius:8px;z-index:9999;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:13px;display:flex;flex-direction:column;gap:5px;box-shadow:0 2px 14px rgba(0,0,0,0.35)}}
.panel-control-row{{display:flex;gap:14px;align-items:center}}
.panel-toggle-row{{font-size:12px;gap:6px;flex-wrap:wrap;padding-top:2px;border-top:1px solid rgba(255,255,255,0.08)}}
.panel-sep{{width:1px;height:18px;background:rgba(255,255,255,0.15);margin:0 4px;flex-shrink:0}}
.lith-cb-row{{display:flex;gap:4px;align-items:center;cursor:pointer;padding:3px 8px;border-radius:4px;background:rgba(255,255,255,0.06);transition:background .15s;white-space:nowrap;user-select:none}}
.lith-cb-row:hover{{background:rgba(255,255,255,0.14)}}
.lith-cb-row input[type=checkbox]{{accent-color:#4fc3f7;margin:0;cursor:pointer}}
.lith-color-dot{{display:inline-block;width:10px;height:10px;border-radius:2px;flex-shrink:0}}
.drill-switch{{position:relative;display:inline-block;width:36px;height:20px;flex-shrink:0}}
.drill-switch input{{opacity:0;width:0;height:0}}
.drill-slider{{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:#555;transition:.3s;border-radius:20px}}
.drill-slider:before{{position:absolute;content:"";height:14px;width:14px;left:3px;bottom:3px;background-color:white;transition:.3s;border-radius:50%}}
input:checked+.drill-slider{{background-color:#4fc3f7}}
input:checked+.drill-slider:before{{transform:translateX(16px)}}
#layer-explode-slider{{width:240px;accent-color:#4fc3f7;cursor:pointer}}
#layer-explode-label{{min-width:44px;text-align:center;font-weight:600;color:#4fc3f7}}
#layer-explode-reset{{background:rgba(255,255,255,0.12);color:#ccc;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:4px 12px;cursor:pointer;font-size:12px;transition:background .15s}}
#layer-explode-reset:hover{{background:rgba(255,255,255,0.22)}}
</style>
<div id="layer-explode-panel">
  {explode_row_html}
  {toggle_row_html}
</div>

<script>window.LAYER_PANEL_CFG={json.dumps(layer_cfg)};</script>
<script charset="utf-8" src="{LAYER_PANEL_JS_URL}"></script>
"""
        injection_parts.append(panel_js)

    # ---- 体积估算面板 ----
    grid_data_tag = _serialize_grid_data(bodies)
    # 计算 Z 范围供滑块使用
    z_all = []
    for body in bodies.values():
        zt = body['Z_top'][~np.isnan(body['Z_top'])]
        zb = body['Z_bot'][~np.isnan(body['Z_bot'])]
        if len(zt) > 0:
            z_all.extend(zt.tolist())
        if len(zb) > 0:
            z_all.extend(zb.tolist())
    z_range_min = float(np.min(z_all)) if z_all else 0
    z_range_max = float(np.max(z_all)) if z_all else 100
    # 加 5% 余量
    z_pad = (z_range_max - z_range_min) * 0.05 if z_range_max > z_range_min else 10
    z_range_min -= z_pad
    z_range_max += z_pad

    # 面板脚本已抽成 static/js/volume_panel.js，原先写死在 JS 里的两个常量改由配置传入
    # （取值与原先内联的 {z_range_min:.2f} / {z_range_max:.2f} 一致，都是两位小数）
    vol_cfg = {'zMin': round(z_range_min, 2), 'zMax': round(z_range_max, 2)}

    volume_panel_js = f'''
<style>
#volume-estimate-panel{{
    position:absolute;bottom:60px;right:16px;background:rgba(28,28,28,0.9);color:#e0e0e0;
    border-radius:8px;z-index:9998;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    font-size:13px;box-shadow:0 2px 14px rgba(0,0,0,0.35);width:300px;overflow:hidden;display:none;
    user-select:none;-webkit-user-select:none;
}}
#volume-estimate-panel.visible{{display:block;}}
.vol-panel-header{{
    padding:8px 14px;display:flex;justify-content:space-between;align-items:center;
    border-bottom:1px solid rgba(255,255,255,0.1);cursor:pointer;
}}
.vol-panel-header span{{font-weight:600;color:#4fc3f7;}}
.vol-panel-header button{{
    background:none;border:none;color:#999;font-size:18px;cursor:pointer;padding:0 4px;line-height:1;
}}
.vol-panel-header button:hover{{color:#fff;}}
.vol-panel-body{{padding:10px 14px 12px;display:block;}}
.vol-panel-body.collapsed{{display:none;}}
.vol-slider-group{{margin-bottom:8px;position:relative;}}
.vol-slider-group input[type=range].vol-single-range{{
    position:static;top:auto;left:auto;width:100%;height:auto;margin:0;padding:0;
    -webkit-appearance:auto;appearance:auto;background:auto;pointer-events:auto;
    transform:none;accent-color:#4fc3f7;
}}
.vol-slider-group .vol-label{{
    display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;font-size:12px;
}}
.vol-slider-group .vol-label span:last-child{{color:#4fc3f7;font-weight:600;min-width:70px;text-align:right;}}
.vol-slider-group .vol-slider-track{{
    position:relative;height:22px;display:flex;align-items:center;
}}
.vol-slider-group input[type=range]{{
    position:absolute;top:0;left:0;width:100%;height:100%;margin:0;padding:0;
    -webkit-appearance:none;appearance:none;background:transparent;pointer-events:none;
}}
.vol-slider-group input[type=range]::-webkit-slider-runnable-track{{
    height:4px;background:rgba(255,255,255,0.15);border-radius:2px;border:none;
}}
.vol-slider-group input[type=range]::-webkit-slider-thumb{{
    -webkit-appearance:none;appearance:none;pointer-events:auto;
    width:12px;height:12px;border-radius:50%;background:#4fc3f7;
    border:2px solid #fff;cursor:pointer;margin-top:-4px;box-shadow:0 0 4px rgba(79,195,247,0.5);
}}
.vol-slider-group input[type=range]::-moz-range-track{{
    height:4px;background:rgba(255,255,255,0.15);border-radius:2px;border:none;
}}
.vol-slider-group input[type=range]::-moz-range-thumb{{
    pointer-events:auto;width:12px;height:12px;border-radius:50%;background:#4fc3f7;
    border:2px solid #fff;cursor:pointer;box-shadow:0 0 4px rgba(79,195,247,0.5);
}}
.vol-lith-checkboxes{{margin-bottom:10px;display:flex;flex-wrap:wrap;gap:6px;font-size:12px;}}
.vol-lith-checkboxes label{{cursor:pointer;display:flex;align-items:center;gap:3px;padding:3px 8px;border-radius:4px;background:rgba(255,255,255,0.06);transition:background .15s;}}
.vol-lith-checkboxes label:hover{{background:rgba(255,255,255,0.14);}}
.vol-lith-checkboxes input[type=checkbox]{{accent-color:#4fc3f7;margin:0;}}
.vol-result{{padding:10px 12px;background:rgba(79,195,247,0.08);border-radius:6px;text-align:center;}}
.vol-result .vol-total{{font-size:22px;font-weight:700;color:#4fc3f7;margin-bottom:2px;}}
.vol-result .vol-detail{{font-size:11px;color:#aaa;line-height:1.5;}}
.vol-result .vol-per-lith{{font-size:11px;color:#aaa;margin-top:4px;text-align:left;padding-left:12px;}}
.vol-actions{{display:flex;gap:8px;margin-top:10px;justify-content:flex-end;}}
.vol-btn{{
    padding:5px 14px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);cursor:pointer;
    font-size:12px;font-family:inherit;transition:background .15s;
}}
.vol-btn-confirm{{background:rgba(79,195,247,0.18);color:#4fc3f7;border-color:rgba(79,195,247,0.35);}}
.vol-btn-confirm:hover{{background:rgba(79,195,247,0.3);}}
.vol-btn-cancel{{background:rgba(255,255,255,0.08);color:#ccc;}}
.vol-btn-cancel:hover{{background:rgba(255,255,255,0.16);}}
.vol-btn-inline{{
    padding:4px 12px;border-radius:4px;border:1px solid rgba(79,195,247,0.4);cursor:pointer;
    background:rgba(255,255,255,0.08);color:#4fc3f7;font-size:12px;
    font-family:inherit;transition:background .15s;
}}
.vol-btn-inline:hover{{background:rgba(79,195,247,0.15);}}
.vol-btn-inline.active{{background:rgba(211,47,47,0.18);color:#ef9a9a;border-color:rgba(211,47,47,0.4);}}
</style>

{grid_data_tag}

<div id="volume-estimate-panel">
  <div class="vol-panel-header" id="vol-panel-header-btn">
    <span>📐 体积估算</span>
    <button id="vol-panel-toggle" title="收起/展开">−</button>
  </div>
  <div class="vol-panel-body" id="vol-panel-body">
    <div class="vol-slider-group">
      <div class="vol-label"><span>X (北) 范围</span><span id="vol-x-label">—</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-x-min" min="0" max="100" step="0.1" value="0">
        <input type="range" id="vol-x-max" min="0" max="100" step="0.1" value="100">
      </div>
    </div>
    <div class="vol-slider-group">
      <div class="vol-label"><span>Y (东) 范围</span><span id="vol-y-label">—</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-y-min" min="0" max="100" step="0.1" value="0">
        <input type="range" id="vol-y-max" min="0" max="100" step="0.1" value="100">
      </div>
    </div>
    <div class="vol-slider-group">
      <div class="vol-label"><span>Z (高程) 范围</span><span id="vol-z-label">—</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-z-min" min="0" max="100" step="0.1" value="0">
        <input type="range" id="vol-z-max" min="0" max="100" step="0.1" value="100">
      </div>
    </div>
    <div class="vol-slider-group">
      <div class="vol-label"><span>🔄 框体绕Z轴旋转</span><span id="vol-rot-label">0°</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-rot-angle" min="-90" max="90" value="0" step="1">
      </div>
    </div>
    <div class="vol-slider-group">
      <div class="vol-label"><span>🔄 框体绕X轴旋转</span><span id="vol-rot-x-label">0°</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-rot-x" min="-90" max="90" value="0" step="1">
      </div>
    </div>
    <div class="vol-slider-group">
      <div class="vol-label"><span>🔄 框体绕Y轴旋转</span><span id="vol-rot-y-label">0°</span></div>
      <div class="vol-slider-track">
        <input type="range" id="vol-rot-y" min="-90" max="90" value="0" step="1">
      </div>
    </div>
    <div class="vol-lith-checkboxes" id="vol-lith-checks"></div>
    <div class="vol-result" id="vol-result">
      <div class="vol-total">— m³</div>
      <div class="vol-detail">拖拽 X / Y / Z 滑块框选范围，查看体积估算结果</div>
    </div>
    <div class="vol-actions">
      <button class="vol-btn vol-btn-cancel" id="vol-btn-cancel">✕ 关闭</button>
      <button class="vol-btn vol-btn-confirm" id="vol-btn-confirm">✓ 确定</button>
    </div>
  </div>
</div>

<script>window.VOL_PANEL_CFG={json.dumps(vol_cfg)};</script>
<script charset="utf-8" src="{VOLUME_PANEL_JS_URL}"></script>
'''
    injection_parts.append(volume_panel_js)

    # 注入到 </body> 之前
    if injection_parts:
        html = html.replace('</body>', '\n'.join(injection_parts) + '\n</body>')
        with open(html_path, 'w') as fh:
            fh.write(html)

    return html_path

# ==================== AI建模 ====================
def call_qwen_api_for_modeling(image_paths, view_metas=None, color_map=None, api_key=QWEN_API_KEY, api_url=QWEN_API_URL, model=QWEN_MODEL):
    """
    调用 Token Plan API 生成 AI 建模图。
    使用 HTTP 直接请求，无需 dashscope SDK。

    参数:
        image_paths: 参考图文件路径列表（3张）
        view_metas: 每个视图的元信息列表，每个元素 {'name', 'label', 'user_tip'}
        color_map: 颜色映射 dict
    """
    if not api_key:
        return None, "!!! API密钥未配置，请设置 QWEN_KEY 环境变量"

    # ========== 1. 验证图片 ==========
    if not image_paths or len(image_paths) < 3:
        return None, f"!!! 需要3张参考图，当前只找到 {len(image_paths) if image_paths else 0} 张"

    print(f"==> 已选 {len(image_paths)} 张参考图")

    # ========== 2. 构建颜色描述 ==========
    if color_map and isinstance(color_map, dict):
        color_groups = {}
        for color, names in color_map.items():
            if color not in color_groups:
                color_groups[color] = set()
            for name in names.split('、'):
                color_groups[color].add(name.strip())
        color_lines = []
        for color, name_set in color_groups.items():
            color_lines.append(f'- {color}: {"/".join(sorted(name_set))}')
        color_relations = '\n'.join(color_lines)
    else:
        color_relations = '各岩性用对应颜色表达'

    # ========== 3. 动态构建视角描述（按视图名称分配角色） ==========
    def _get_view_role(vm):
        """根据视图名称/类型返回其在建模中的角色描述"""
        name = vm.get('name', '')
        label = vm.get('label', '')
        if 'main_view' in name or '全景' in label:
            return '作为几何形态的**主参考**，用于确定地质体的整体空间轮廓和三维形态'
        if 'east_west' in name or '东西向' in label:
            return '作为东西向剖面的**精确约束**。此图的每一条岩性分界线的高程位置，必须在生成结果中严格对应'
        if 'north_south' in name or '南北向' in label:
            return '作为南北向剖面的**精确约束**，与东西向剖面正交，共同约束三维形态'
        if 'top_down' in name or '俯视' in label:
            return '作为**平面展布参考**，用于确定矿体在平面上的分布范围和走向'
        if 'supplementary' in name or '补充' in label:
            return '作为**补充立体参考**，用于检查主视图背面被遮挡的结构和边界'
        if 'iso' in name or '等轴' in label:
            return '作为**标准化对比参考**，用于统一视角下的形态验证'
        return '用于多角度验证地质体的三维形态一致性'

    if view_metas and len(view_metas) >= 3:
        view_descriptions = []
        for i, vm in enumerate(view_metas):
            role = _get_view_role(vm)
            view_descriptions.append(f'- {vm["label"]} —— {vm.get("user_tip", "")}（{role}）')

        # 检测两个剖面视图是否正交
        profile_views = []
        for vm in view_metas:
            if '剖面' in vm.get('label', ''):
                profile_views.append(vm['label'])
        profile_line = ''
        if len(profile_views) >= 2:
            profile_line = f'- {profile_views[0]}和{profile_views[1]}是两个正交剖面，它们的**岩性分界线的深度位置必须严格对应**，这两个剖面的交点处（即钻孔位置附近）的层位深度应完全一致。\n'
    else:
        # fallback: 使用 view_metas 的第一条信息，或通用描述
        if view_metas:
            view_descriptions = [f'- {vm["label"]}: {vm.get("user_tip", "")}' for vm in view_metas]
        else:
            view_descriptions = ['- 第1张：整体三维形态参考', '- 第2张：垂向结构参考', '- 第3张：正交方向参考']
        profile_line = '- 后两张参考图如果是正交剖面，它们的**岩性分界线的深度位置必须严格对应**。\n'

    geomodel_prompt = f"""
请根据以下{len(view_descriptions)}张同一地质体的不同视角参考图，生成一张统一、逼真的三维地质结构模型渲染图。

【坐标约定】
本模型采用地质行业标准坐标：
- X 轴：东向（Easting）
- Y 轴：北向（Northing）
- Z 轴：高程（Elevation，向上为正）

【参考视角说明】
{chr(10).join(view_descriptions)}

【关键说明】
- 上述{len(view_descriptions)}张图是同一个地质体的不同视角，请综合理解其三维空间结构，不要将它们视为多个独立物体。
- 参考图左上角的文字是该视角的名称标识，请在生成结果中忽略这些标识文字，只关注地质体的形态和颜色。
{profile_line}
【参考图的性质说明】
上述参考图是**基于有限钻孔数据通过数学插值生成的初步模型**，具有以下特点：
- 其边界受钻孔控制点的空间分布范围限制，呈现为"被凸包裁剪"的形态，边缘生硬。
- 部分区域由于缺乏钻孔控制，会出现"凹陷""空洞"或"突然中断"。
- 这些不完整的边界**不代表真实地质体的实际边界**，仅代表"钻孔控制范围内的已知部分"。

【您的任务——科学化的地质填充】
请以参考图为骨架约束，运用地质学常识进行科学化的推断与填充，生成一个相对完整、符合地质规律的三维地质体：
1. **保持钻孔控制区的形态和深度不变**：
   - 参考图中由钻孔数据明确约束的**岩性分界线深度**必须严格保留。
   - 每一层的**顶板高程和底板高程**必须与剖面图中显示的数值一致。
   - 禁止将薄层"合并"或"抹掉"，每一条可见的岩性分界线都必须在结果中保留。
2. **填充缺失区域**：
   - 地层延续性：同一岩性在空间上应保持连续。
   - 厚度渐变：地层厚度变化应平滑过渡，不出现突然的增厚或减薄。
   - 倾角合理：保持在合理范围（0°~60°）。
   - 边界外延：地质体边缘应自然延伸至模型边界，而非突然中断。
3. **合理外推与尖灭**：
   - 延续性强的岩性（基岩、厚层）应稳定延伸至模型边界。
   - 透镜状、脉状矿体可合理"尖灭"，但应有渐变过渡。
4. **整体协调性**：
   - 填充后的地质体应像一个"完整的地质块体"，各岩性之间过渡自然。
   - 层位之间必须**层次分明**，从上到下按深度依次排列，不出现"层位穿插"或"上下颠倒"。

【岩性纹理逼真度要求——重要】
不同岩性应呈现**符合地质学常识的岩石质感**，避免所有岩性都是"一坨彩色黏土"。请根据岩性名称推断其应有的真实质感：
- **透明矿物（萤石、石英）**：晶莹剔透、半透明、玻璃光泽
- **金属矿物（黄铜矿、黄铁矿、铅锌矿）**：金属光泽、致密块状
- **结晶岩（花岗斑岩、片麻岩）**：斑状结构或片理构造
- **沉积岩（砂岩、泥岩、砾岩）**：颗粒感或层理清晰
- **覆盖层（第四系、浮土）**：松散、土状、无明显结晶
- **其他未列举的岩性**：根据名称推断其真实质感，避免"塑料感"

【颜色与岩性对应关系】
{color_relations}

【生成要求】
1. **岩石纹理逼真，各岩性呈现其独特的地质质感**
2. 各岩性严格使用上述对应颜色表达，颜色饱和度适中
3. 保持参考图的整体三维形态和剖面深度
4. 正交剖面图的岩性分界线在交点处深度必须一致
5. 地质体应呈现为完整连续的地质块体，边缘自然过渡
6. **层位必须严格按深度从上到下排列，禁止上下颠倒或穿插**
7. 光照自然，具有地质剖面的专业感，避免过度反光或卡通化
8. 背景为纯白色。在图像右侧显示Z轴（高程）标尺，仅此一个坐标轴，不要显示X轴和Y轴坐标，不要显示任何文字标注
9. 图像风格为科学分析 + 符合地质真实的图片
10. 输出为单张高质量的三维地质结构渲染图，分辨率不低于1024x1024
"""
    # ========== 3. 构建 content 数组（压缩参考图以减少传输量） ==========
    content_list = []
    from PIL import Image
    for path in image_paths:
        # 读取并压缩图片到 1024×1024，避免 JSON 负载过大导致连接超时
        img = Image.open(path)
        img.thumbnail((1024, 1024), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        content_list.append({"image": f"data:image/png;base64,{b64}"})
    content_list.append({"text": geomodel_prompt})

    # ========== 5. 构建请求体（注意：messages 在 input 下面） ==========
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content_list
                }
            ]
        },
        "parameters": {
            "n": 2,                    # 生成2张图
            "size": "1024*1024",
            "watermark": False,
            "prompt_extend": False    # 不允许 AI 重写结构化提示词
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # ========== 6. 发送请求 ==========
    print(f"==> 正在调用 {model} 生成地质模型...")
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=360)
        print(f"==> 响应状态码: {response.status_code}")

        if response.status_code != 200:
            return None, f"!!! API调用失败 (状态码{response.status_code}): {response.text}"

        result = response.json()

        # ========== 7. 解析返回结果 ==========
        # 典型结构：result['output']['choices'][0]['message']['content']
        # content 是列表：[{'image': 'url'}, ...]
        output = result.get('output', {})
        choices = output.get('choices', [])
        if not choices:
            return None, f"!!! API返回格式异常: {result}"

        content = choices[0].get('message', {}).get('content', [])
        image_urls = []
        for item in content:
            if isinstance(item, dict) and 'image' in item:
                image_urls.append(item['image'])

        if not image_urls:
            return None, f"!!! 未找到图片: {result}"

        print(f"==> 成功生成 {len(image_urls)} 张图")
        return image_urls, None

    except requests.exceptions.Timeout:
        return None, "!!! API请求超时（超过180秒）"
    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"


def color_map_to_text(color_map):
    """把 color_map dict 转为去重后的文本描述字符串（与 call_qwen_api_for_modeling 一致）"""
    color_groups = {}
    for color, names in color_map.items():
        if color not in color_groups:
            color_groups[color] = set()
        for name in names.split('、'):
            color_groups[color].add(name.strip())
    lines = []
    for color, name_set in color_groups.items():
        lines.append(f'- {color}: {"/".join(sorted(name_set))}')
    return '\n'.join(lines)


def call_qwen_api_for_multiview(anchor_image, target_image, color_map,
                                  anchor_view=None, target_view=None,
                                  api_key=None, api_url=None, model=None):
    """
    以最优 AI 图为主锚，生成目标视角的 AI 图。

    参数:
        anchor_image: 主锚图路径（最优 AI 图）
        target_image: 目标视角的 Python 无标注图路径
        color_map: 颜色映射 dict
        anchor_view: 主锚图对应的 VIEW_CONFIG 条目（含 name, label 等）
        target_view: 目标视角对应的 VIEW_CONFIG 条目
        api_key / api_url / model: 可选覆盖

    返回:
        (image_urls, error)
    """
    import base64
    import requests
    from config import QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL

    api_key = api_key or QWEN_API_KEY
    api_url = api_url or QWEN_API_URL
    model = model or QWEN_MODEL

    if not api_key:
        return None, "!!! API密钥未配置"

    # 构建提示词 — 使用视角名称而非序号，包含完整地质约束
    color_text = color_map_to_text(color_map)

    # 视角描述
    if target_view:
        target_desc = f'"{target_view.get("label", "目标视角")}"（{target_view.get("name", "")}）：{target_view.get("user_tip", "")}'
    else:
        target_desc = '目标视角'
    if anchor_view:
        anchor_desc = f'"{anchor_view.get("label", "主锚图")}"（{anchor_view.get("name", "")}）：{anchor_view.get("user_tip", "")}'
    else:
        anchor_desc = '主锚图（已生成的高质量 AI 纹理图）'

    prompt = f"""
你是一位地质建模专家。请根据以下两张参考图，生成一张目标视角的三维地质体渲染图。

【参考图说明】
- 主锚图（第一张图）：{anchor_desc}
  → 作用：参考它的岩石纹理风格、光影效果、色调一致性。
- 几何约束图（第二张图）：{target_desc}
  → 作用：严格遵循它的几何结构、层位分布、各岩性边界位置和视角。

【核心约束——必须严格遵守】
1. **几何结构必须与几何约束图一致**：
   - 每一层的顶板高程、底板高程、层间厚度必须与几何约束图对应
   - 岩性分界线的深度位置必须严格保留，禁止将薄层合并或抹掉
   - 层位必须按深度从上到下依次排列，禁止上下颠倒或穿插
2. **视角必须与几何约束图完全一致**：不要改变观察角度
3. **岩石纹理必须与主锚图风格一致**：纹理质感、光照方向、色调饱和度参考主锚图
4. **颜色必须严格遵守下方对应关系**：每一层的颜色基调不得大幅偏移
5. **背景必须为纯白色（255,255,255）**，无任何文字标注、水印、边框

【岩性纹理逼真度要求】
不同岩性必须呈现符合地质学常识的岩石质感，避免所有岩性都是"彩色黏土"：
- 透明矿物（萤石、石英、方解石）→ 晶莹剔透、玻璃光泽
- 金属矿物（黄铜矿、黄铁矿、铅锌矿）→ 金属光泽、致密块状
- 结晶岩（花岗斑岩、片麻岩）→ 斑状或粒状结构、矿物颗粒边界清晰
- 沉积岩（砂岩、泥岩、砾岩）→ 颗粒感或层理清晰
- 覆盖层（第四系、浮土）→ 松散土状、无明显结晶
- 其他未列举的岩性 → 根据名称推断真实地质质感，避免"塑料感"

【颜色-岩性对应关系】
{color_text}
"""
    # 移除公共前缀缩进（保持与原始一致的风格）
    prompt = prompt.strip()

    # 构建 content
    content_list = []
    for img_path in [anchor_image, target_image]:
        if not os.path.exists(img_path):
            return None, f"!!! 图片不存在: {img_path}"
        with open(img_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
            content_list.append({"image": f"data:image/png;base64,{b64}"})
    content_list.append({"text": prompt})

    payload = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": content_list}]
        },
        "parameters": {
            "n": 1,
            "size": "1024*1024",
            "watermark": False,
            "prompt_extend": False     # 不允许 AI 重写结构化提示词
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=360)
        if response.status_code != 200:
            return None, f"!!! API调用失败 ({response.status_code}): {response.text}"

        result = response.json()
        output = result.get('output', {})
        choices = output.get('choices', [])
        if not choices:
            return None, f"!!! API返回格式异常: {result}"

        content = choices[0].get('message', {}).get('content', [])
        image_urls = []
        for item in content:
            if isinstance(item, dict) and 'image' in item:
                image_urls.append(item['image'])

        if not image_urls:
            return None, f"!!! 未找到图片: {result}"

        return image_urls, None
    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"


def _get_pil_chinese_font(font_size=14):
    """获取 PIL 中文字体，多级后备"""
    from PIL import ImageFont
    import matplotlib.font_manager as fm

    # 与 matplotlib 使用相同的字体列表
    font_names = [
        'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
        'SimHei', 'STHeiti', 'WenQuanYi Zen Hei',
        'Noto Sans CJK SC', 'Source Han Sans SC',
        'Arial Unicode MS',
    ]
    for name in font_names:
        try:
            path = fm.findfont(name, fallback_to_default=False)
            if path and os.path.exists(path):
                return ImageFont.truetype(path, font_size)
        except Exception:
            continue

    # 系统文件扫描后备
    try:
        for fp in fm.findSystemFonts():
            bn = os.path.basename(fp).lower()
            if any(k in bn for k in ('hei', 'song', 'yahei', 'cjk', 'han')):
                return ImageFont.truetype(fp, font_size)
    except Exception:
        pass

    # 最终兜底：PIL 默认 bitmap 字体（中文将显示为方框）
    return ImageFont.load_default()


def add_annotations_to_ai_image(ai_image_path, output_path, z_min, z_max):
    """
    在 AI 图上叠加深度标尺（带标注版）。

    参数:
        ai_image_path: AI 生成图路径
        output_path: 输出路径
        z_min, z_max: 高程范围（米）
    """
    from PIL import Image, ImageDraw

    try:
        img = Image.open(ai_image_path).convert('RGB')
    except Exception as e:
        print(f"!!! 打开 AI 图失败: {e}")
        return None

    w, h = img.size

    # 扩展画布（右侧留 120px 给标尺）
    new_img = Image.new('RGB', (w + 120, h), 'white')
    new_img.paste(img, (0, 0))

    draw = ImageDraw.Draw(new_img)
    ruler_x = w + 30
    ruler_top = 80
    ruler_bottom = h - 80
    ruler_width = 20

    # 中文字体
    cn_font = _get_pil_chinese_font(font_size=12)
    cn_font_title = _get_pil_chinese_font(font_size=14)

    # 灰度渐变条（浅→深）
    for i in range(ruler_bottom - ruler_top):
        gray = int(255 * (1 - i / (ruler_bottom - ruler_top)))
        draw.rectangle(
            [ruler_x, ruler_top + i, ruler_x + ruler_width, ruler_top + i + 1],
            fill=(gray, gray, gray)
        )

    # 刻度
    n_ticks = 6
    for i in range(n_ticks + 1):
        y = ruler_top + int((ruler_bottom - ruler_top) * i / n_ticks)
        z_val = z_max - (z_max - z_min) * i / n_ticks
        draw.line([ruler_x + ruler_width, y, ruler_x + ruler_width + 8, y],
                  fill='black', width=2)
        # 高程标注保留两位小数（如 523.55m）：这是画在 AI 效果图上的深度标尺，
# 不是坐标轴，刻度值按 6 等分算出来通常不是整数，仍按两位小数显示。
        draw.text((ruler_x + ruler_width + 12, y - 8), f'{z_val:.2f}m',
                  fill='black', font=cn_font)

    # 标题（中文）
    draw.text((ruler_x, ruler_top - 30), '深度标尺', fill='black', font=cn_font_title)

    new_img.save(output_path)
    return output_path


# ==================== 多视角纹理升级相关函数 ====================
def plot_geometry_with_black_edges(volume_data, view_config, output_dir, base_name):
    """
    生成带黑色描边的几何图，用于 AI 纹理升级的输入。
    黑色描边帮助 AI 识别层位边界。

    参数:
        volume_data: 地质体数据
        view_config: 视角配置
        output_dir: 输出目录
        base_name: 文件名前缀

    返回:
        保存的图片路径
    """
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax = fig.add_subplot(111, projection='3d')

    # 绘制地质体（带黑色描边）
    for lith, data in volume_data.items():
        color_rgb = data['color'][:3]
        layers = data['layers']
        if not layers:
            continue
        for k, Z in enumerate(layers):
            opacity = 0.2 + 0.5 * (k / (len(layers) - 1)) if len(layers) > 1 else 0.5
            ax.plot_surface(
                data['X'], data['Y'], Z,
                color=color_rgb,
                alpha=opacity,
                edgecolor='black',           # 关键：黑色描边
                linewidth=GEOMETRY_EDGE_WIDTH
            )

    # 隐藏 X/Y 轴，保留 Z 轴
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.tick_params(axis='x', which='both', length=0, labelbottom=False)
    ax.tick_params(axis='y', which='both', length=0, labelleft=False)
    ax.xaxis.line.set_visible(False)
    ax.yaxis.line.set_visible(False)
    ax.xaxis.pane.set_visible(False)
    ax.yaxis.pane.set_visible(False)
    ax.zaxis.pane.set_visible(False)
    ax.set_zlabel('Elevation (m)', fontsize=10)
    ax.tick_params(axis='z', labelsize=8)
    ax.zaxis.line.set_visible(True)
    ax.grid(False)

    # 范围（从 volume_data 计算）
    all_x, all_y, all_z = [], [], []
    for data in volume_data.values():
        all_x.extend(data['X'].ravel())
        all_y.extend(data['Y'].ravel())
        for layer in data['layers']:
            valid = layer[~np.isnan(layer)]
            all_z.extend(valid.tolist())

    if all_x and all_y and all_z:
        margin = 20
        ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
        ax.set_ylim(min(all_y) - margin, max(all_y) + margin)
        ax.set_zlim(min(all_z) - 10, max(all_z) + 10)

    # 视角
    ax.view_init(elev=view_config['elev'], azim=view_config['azim'])

    # 保存
    order = view_config.get('order', 0)
    fname = f'{base_name}_geometry_{order:02d}_{view_config["name"]}.png'
    save_path = os.path.join(output_dir, fname)
    plt.savefig(save_path, dpi=FIGURE_DPI, pad_inches=0, facecolor='white')
    plt.close()

    return save_path


def generate_ai_texture_tile(lith_name, color_rgb, output_dir,
                              api_key=None, api_url=None, model=None):
    """
    调用 AI 为一种岩性生成无缝岩石纹理贴片。

    与 generate_ai_texture_for_single_view 的关键区别：
    - 输入：岩性名称 + RGB 颜色（无参考图，纯文本生成）
    - 输出：256×256 无缝纹理 tile
    - prompt_extend: False（不允许 AI 重写 prompt）
    - 职责：只生成纹理质感，不负责几何结构

    参数:
        lith_name: 岩性名称（如 "花岗斑岩"）
        color_rgb: (R, G, B) 基准颜色 tuple
        api_key / api_url / model: 可选覆盖

    返回:
        (tile_path_or_url, error) — tile_path 为保存的本地文件路径
    """
    import base64
    import requests
    from PIL import Image
    from io import BytesIO
    from config import (QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL,
                         TEXTURE_GENERATE_SIZE, TEXTURE_TILE_SIZE,
                         TEXTURE_PROMPT_EXTEND)

    api_key = api_key or QWEN_API_KEY
    api_url = api_url or QWEN_API_URL
    model = model or QWEN_MODEL

    if not api_key:
        return None, "!!! API密钥未配置"

    # 颜色格式兼容：hex 字符串 '#FF0000' → RGB tuple
    if isinstance(color_rgb, str):
        hex_color = color_rgb.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    else:
        r, g, b = color_rgb[:3]
        # 若为 0-1 范围则转为 0-255
        if isinstance(r, float) and r <= 1.0:
            r, g, b = int(r * 255), int(g * 255), int(b * 255)

    # 岩性类型推断（用于纹理描述细化）
    transparent_minerals = ['萤石', '石英', '方解石', '冰洲石', '水晶']
    metallic_minerals = ['黄铜矿', '黄铁矿', '铅锌矿', '磁铁矿', '赤铁矿',
                         '辉锑矿', '方铅矿', '闪锌矿', '斑铜矿', '辉铜矿']
    crystalline_rocks = ['花岗斑岩', '片麻岩', '花岗岩', '闪长岩', '辉长岩',
                         '玄武岩', '安山岩', '流纹岩', '大理岩', '片岩']
    sedimentary_rocks = ['砂岩', '泥岩', '砾岩', '页岩', '灰岩', '白云岩']
    overburden = ['第四系', '浮土', '残坡积', '冲积层', '覆盖层']

    # 构建岩性特征描述
    texture_desc = ''
    if any(m in lith_name for m in transparent_minerals):
        texture_desc = '透明-半透明矿物，玻璃光泽，晶体结构清晰，可见内部折射'
    elif any(m in lith_name for m in metallic_minerals):
        texture_desc = '金属矿物，金属光泽，致密块状构造，表面有不规则反光'
    elif any(m in lith_name for m in crystalline_rocks):
        texture_desc = '结晶岩，斑状或粒状结构，矿物颗粒边界清晰，略有风化痕迹'
    elif any(m in lith_name for m in sedimentary_rocks):
        texture_desc = '沉积岩，颗粒感或层理构造，可见碎屑颗粒，颜色略有不均'
    elif any(m in lith_name for m in overburden):
        texture_desc = '松散堆积物，土状质感，无明显结晶，颜色均匀偏暗'
    else:
        texture_desc = '天然岩石纹理，表面有自然颗粒感和微裂隙'

    prompt = f"""生成一张{lith_name}的岩石纹理贴图。

【岩性特征】
{lith_name}：{texture_desc}

【技术要求】
1. 纹理逼真，符合{lith_name}的地质学特征，细节丰富，微观颗粒、裂隙、结晶结构清晰可辨
2. 色彩基调为 RGB({r},{g},{b})，允许自然纹理变化但不得大幅偏移主色调
3. 无缝拼接（tileable/seamless），水平和垂直边界可自然衔接，无接缝
4. 无定向光源，光照均匀漫反射，避免明显的高光或阴影方向
5. 纯色或接近纯色的均匀背景，无文字、水印、边框
6. 分辨率 {TEXTURE_GENERATE_SIZE}×{TEXTURE_GENERATE_SIZE} 像素，满画幅填充，不要留白
7. 纹理内部应有自然的随机变化（颗粒大小、排列方向、色彩深浅），避免机械化的均匀重复

【重要】
这是一张纯纹理贴片（surface texture），不是地质结构图：
- 只包含岩石表面的微观纹理质感，不要出现任何几何结构、地层边界、黑色描边或深度信息
- 纹理的四个边必须能自然衔接（seamless tiling）
- 用于 3D 地质模型的表面纹理映射（材质贴图）
- 纹理应像真实岩心照片一样自然，不要有任何人工感"""

    payload = {
        "model": model,
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"text": prompt}
                ]
            }]
        },
        "parameters": {
            "n": 1,
            "size": f"{TEXTURE_GENERATE_SIZE}*{TEXTURE_GENERATE_SIZE}",
            "watermark": False,
            "prompt_extend": TEXTURE_PROMPT_EXTEND
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=360)
        if response.status_code != 200:
            return None, f"!!! API调用失败 ({response.status_code}): {response.text[:200]}"

        result = response.json()
        output = result.get('output', {})
        choices = output.get('choices', [])
        if not choices:
            return None, f"!!! API返回格式异常: {str(result)[:200]}"

        content = choices[0].get('message', {}).get('content', [])
        image_url = None
        for item in content:
            if isinstance(item, dict) and 'image' in item:
                image_url = item['image']
                break

        if not image_url:
            return None, f"!!! 未找到图片URL: {str(result)[:200]}"

        # 下载 AI 生成的纹理并下采样
        img_resp = requests.get(image_url, timeout=60)
        if img_resp.status_code != 200:
            return None, f"!!! 下载纹理失败: HTTP {img_resp.status_code}"

        img = Image.open(BytesIO(img_resp.content)).convert('RGB')
        img = img.resize((TEXTURE_TILE_SIZE, TEXTURE_TILE_SIZE), Image.LANCZOS)

        # 保存为 PNG 到 session 输出目录
        import hashlib
        lith_hash = hashlib.md5(lith_name.encode()).hexdigest()[:8]
        tile_path = os.path.join(output_dir, f'texture_tile_{lith_hash}.png')
        img.save(tile_path)
        return tile_path, None

    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"


def render_textured_view(volume_data, view_config, texture_tiles,
                          output_dir, base_name):
    """
    用 AI 纹理 tile 渲染一张视角图。

    与旧流水线的关键区别：纹理来自 AI 生成的 tile（按岩性），
    几何完全由代码控制（mask 渲染 + matplotlib 3D 投影）。

    步骤：
    1. 逐岩性渲染 mask 图（所有 layers 一起，alpha=1，纯色，白底）
    2. 用对应岩性的 AI tile 填充各 mask 区域
    3. 按 Z 深度排序岩性（深者在下，浅者在上）
    4. 合成：深层岩性纹理 → 浅层岩性纹理覆盖
    5. 渲染全几何 black-edge-only 图叠在最上层
    6. 保存 PNG

    降级策略：若某岩性无 AI tile，用其 volume_data['color'] 纯色填充
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    from config import (FIGURE_WIDTH, FIGURE_HEIGHT, FIGURE_DPI,
                         MASK_WHITE_THRESHOLD, GEOMETRY_EDGE_WIDTH)

    h_px = int(FIGURE_HEIGHT * FIGURE_DPI)
    w_px = int(FIGURE_WIDTH * FIGURE_DPI)

    # ---- 1. 逐岩性渲染 mask 并填充纹理 ----
    lith_textures = {}  # lith_name → (mask, filled_texture)

    # Z 深度排序：Z_max 大的在底层（先画）
    lith_order = sorted(
        volume_data.items(),
        key=lambda kv: np.nanmax([np.nanmax(l) for l in kv[1]['layers']
                                   if np.any(~np.isnan(l))] or [0]),
        reverse=True
    )

    for lith, data in lith_order:
        fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
        ax = fig.add_subplot(111, projection='3d')

        color_rgb = data['color'][:3]
        layers = data['layers']
        for k, Z in enumerate(layers):
            ax.plot_surface(
                data['X'], data['Y'], Z,
                color=color_rgb, alpha=1.0,  # 完全实色填充
                edgecolor='none', shade=True   # 开启 3D 光照，增强立体感
            )

        # 隐藏所有轴
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlabel(''); ax.set_ylabel(''); ax.set_zlabel('')
        ax.tick_params(axis='both', which='both', length=0, labelbottom=False, labelleft=False)
        ax.xaxis.line.set_visible(False); ax.yaxis.line.set_visible(False)
        ax.xaxis.pane.set_visible(False); ax.yaxis.pane.set_visible(False)
        ax.zaxis.pane.set_visible(False); ax.zaxis.line.set_visible(False)
        ax.grid(False)

        # 统一坐标范围（与 volume_data 对齐，避免各岩性独立缩放导致 mask 不对齐）
        all_x, all_y, all_z = [], [], []
        for d in volume_data.values():
            all_x.extend(d['X'].ravel())
            all_y.extend(d['Y'].ravel())
            for layer in d['layers']:
                valid = layer[~np.isnan(layer)]
                all_z.extend(valid.tolist())
        if all_x and all_y and all_z:
            margin = 20
            ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
            ax.set_ylim(min(all_y) - margin, max(all_y) + margin)
            ax.set_zlim(min(all_z) - 10, max(all_z) + 10)

        # set_zlim 会重新生成 Z 轴刻度，必须在其后再次清除
        ax.set_zticklabels([])

        ax.view_init(elev=view_config['elev'], azim=view_config['azim'])

        # 渲染到内存 buffer
        import io
        buf = io.BytesIO()
        plt.savefig(buf, dpi=FIGURE_DPI, pad_inches=0, facecolor='white',
                    format='png')
        buf.seek(0)
        plt.close()

        # mask 裁剪（非白像素 = 该岩性区域）
        layer_img = np.array(Image.open(buf).convert('RGB'))
        mask = np.any(layer_img < MASK_WHITE_THRESHOLD, axis=2)
        buf.close()

        # 填充纹理
        filled = np.full_like(layer_img, 255)  # 白底
        if lith in texture_tiles and os.path.exists(texture_tiles[lith]):
            # 有 AI tile：平铺填充
            tile = np.array(Image.open(texture_tiles[lith]).convert('RGB'))
            th, tw = tile.shape[:2]
            # 平铺 tile 到 mask 区域尺寸一致
            tiled = np.tile(tile, (max(1, (h_px // th) + 2),
                                   max(1, (w_px // tw) + 2), 1))
            tiled = tiled[:h_px, :w_px, :]  # 裁剪到精确尺寸
            filled[mask] = tiled[mask]
        else:
            # 降级：用纯色填充（color_rgb 为 0~1 浮点，需乘 255 转为 0~255 uint8）
            if isinstance(color_rgb[0], float) and color_rgb[0] <= 1.0:
                solid = (np.array(color_rgb) * 255).astype(np.uint8).reshape(1, 1, 3)
            else:
                solid = np.array(color_rgb, dtype=np.uint8).reshape(1, 1, 3)
            filled[mask] = solid

        lith_textures[lith] = (mask, filled)

    # ---- 2. 按 Z 深度合成（深层先画，浅层覆盖） ----
    canvas = np.full((h_px, w_px, 3), 255, dtype=np.uint8)

    for lith, _ in lith_order:
        if lith not in lith_textures:
            continue
        mask, filled = lith_textures[lith]
        canvas[mask] = filled[mask]

    # ---- 3. 保存 ----
    order = view_config.get('order', 0)
    fname = f'{base_name}_{view_config["name"]}.png'
    save_path = os.path.join(output_dir, fname)
    Image.fromarray(canvas).save(save_path)
    return save_path


def generate_ai_texture_for_single_view(geometry_path, color_map, api_key=None, api_url=None, model=None):
    """
    对单张几何图调用 AI 生成纹理图。

    参数:
        geometry_path: 带黑色描边的几何图路径
        color_map: 颜色-岩性映射
        api_key / api_url / model: 可选覆盖

    返回:
        (ai_image_url, error)
    """
    import base64
    import requests
    from config import QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL

    api_key = api_key or QWEN_API_KEY
    api_url = api_url or QWEN_API_URL
    model = model or QWEN_MODEL

    if not api_key:
        return None, "!!! API密钥未配置"

    if not os.path.exists(geometry_path):
        return None, f"!!! 几何图不存在: {geometry_path}"

    # 构建颜色描述
    color_lines = []
    for color, names in color_map.items():
        color_lines.append(f'- {color}: {names}')
    color_text = '\n'.join(color_lines)

    # 提示词：只升级纹理，不动几何
    prompt = f"""
请对参考图进行"纹理升级"——保持几何形态完全不变，只把彩色平面升级为真实的岩石纹理。

【参考图说明】
- 参考图是三维地质体的几何约束图，每一层用不同颜色表示，层位边界有黑色描边。
- 你的任务是：保持每一层的位置、厚度、边界完全不变，只把"彩色平面"替换为"对应岩性的真实岩石纹理"。

【岩性颜色对应关系】
{color_text}

【纹理升级要求】
1. **几何严格保持不变**：每一层的位置、厚度、边界轮廓必须与参考图完全一致。
2. **纹理逼真**：不同岩性应呈现符合地质学常识的岩石质感：
   - 透明矿物（萤石、石英）：晶莹剔透、半透明、玻璃光泽
   - 金属矿物（黄铜矿、黄铁矿、铅锌矿）：金属光泽、致密块状
   - 结晶岩（花岗斑岩、片麻岩）：斑状结构或片理构造
   - 沉积岩（砂岩、泥岩、砾岩）：颗粒感或层理清晰
   - 覆盖层（第四系、浮土）：松散、土状、无明显结晶
3. **颜色保持**：每一层的颜色基调与参考图一致，不要大幅偏移。
4. **光影自然**：岩石表面的自然光照，避免过度反光或卡通化。
5. **黑色描边保留**：参考图中的黑色层位边界必须保留，用于后续合成。
6. **背景纯白**：背景必须为纯白色（255,255,255）。

【重要提醒】
这是"纹理升级"任务，不是"重新绘制"任务。几何、视角、层位、厚度必须严格保持。
"""

    # 读取图片
    with open(geometry_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    img_data = f"data:image/png;base64,{b64}"

    payload = {
        "model": model,
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"image": img_data},
                    {"text": prompt}
                ]
            }]
        },
        "parameters": {
            "n": 1,
            "size": "1024*1024",
            "watermark": False,
            "prompt_extend": False     # 不允许 AI 重写结构化提示词
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=360)
        if response.status_code != 200:
            return None, f"!!! API调用失败 ({response.status_code}): {response.text}"

        result = response.json()
        output = result.get('output', {})
        choices = output.get('choices', [])
        if not choices:
            return None, f"!!! API返回格式异常: {result}"

        content = choices[0].get('message', {}).get('content', [])
        for item in content:
            if isinstance(item, dict) and 'image' in item:
                return item['image'], None

        return None, f"!!! 未找到图片: {result}"
    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"


def composite_ai_texture_with_geometry(geo_path, ai_path, output_path):
    """
    遮罩合成：用几何图的轮廓作为遮罩，把 AI 纹理填充进去。

    参数:
        geo_path: Python 几何图路径（带黑色描边）
        ai_path: AI 纹理图路径
        output_path: 输出路径

    返回:
        输出路径
    """
    import numpy as np
    from PIL import Image
    from scipy.ndimage import binary_erosion
    from config import MASK_WHITE_THRESHOLD

    # 读取几何图
    geo = np.array(Image.open(geo_path).convert('RGB'))
    h, w = geo.shape[:2]

    # 读取 AI 图，缩放到几何图尺寸
    ai = np.array(Image.open(ai_path).convert('RGB').resize((w, h)))

    # 几何图中非白像素 = 地质体区域
    geo_mask = np.any(geo < MASK_WHITE_THRESHOLD, axis=2)

    # 找出几何图的黑色描边（边缘）
    eroded = binary_erosion(geo_mask, iterations=1)
    edge_mask = geo_mask & ~eroded

    # 结果：白底
    result = np.full_like(geo, 255)

    # 用 AI 纹理填充地质体区域
    result[geo_mask] = ai[geo_mask]

    # 保留几何图的黑色描边
    result[edge_mask] = geo[edge_mask]

    Image.fromarray(result).save(output_path)
    return output_path


def reinhard_color_transfer(source_img, target_img):
    """
    Reinhard 色彩迁移：把 target 的色调迁移到 source 的风格。

    参数:
        source_img: 参考图（numpy 数组，RGB）
        target_img: 待迁移图（numpy 数组，RGB）

    返回:
        迁移后的图片（numpy 数组）
    """
    import numpy as np
    from skimage import color

    # 转到 Lab 色彩空间
    src_lab = color.rgb2lab(source_img / 255.0)
    tgt_lab = color.rgb2lab(target_img / 255.0)

    # 计算均值和标准差
    src_mean = src_lab.reshape(-1, 3).mean(axis=0)
    src_std = src_lab.reshape(-1, 3).std(axis=0)
    tgt_mean = tgt_lab.reshape(-1, 3).mean(axis=0)
    tgt_std = tgt_lab.reshape(-1, 3).std(axis=0)

    # 避免除零
    tgt_std = np.where(tgt_std < 1e-6, 1e-6, tgt_std)

    # 迁移
    result_lab = (tgt_lab - tgt_mean) * (src_std / tgt_std) + src_mean
    result_rgb = color.lab2rgb(result_lab) * 255
    return result_rgb.astype(np.uint8)


def unify_multiview_color_tones(image_paths):
    """
    统一多张图的色调，以第一张为参考。

    参数:
        image_paths: 图片路径列表（第一张作为参考）

    返回:
        修改后的图片路径列表
    """
    import numpy as np
    from PIL import Image
    from config import MULTIVIEW_COLOR_METHOD

    if len(image_paths) < 2:
        return image_paths

    # 读取第一张作为参考
    ref_img = np.array(Image.open(image_paths[0]).convert('RGB'))

    result_paths = [image_paths[0]]  # 第一张不变

    for i, path in enumerate(image_paths[1:], start=1):
        tgt_img = np.array(Image.open(path).convert('RGB'))

        # 尺寸对齐
        if tgt_img.shape != ref_img.shape:
            tgt_img = np.array(Image.open(path).convert('RGB').resize(
                (ref_img.shape[1], ref_img.shape[0])
            ))

        # 应用色彩迁移
        if MULTIVIEW_COLOR_METHOD == 'reinhard':
            result_img = reinhard_color_transfer(ref_img, tgt_img)
        else:
            # 简单的直方图匹配（备选）
            result_img = tgt_img  # 暂不实现

        # 保存
        out_path = path.replace('.png', '_unified.png')
        Image.fromarray(result_img).save(out_path)
        result_paths.append(out_path)

    return result_paths


# ==================== Excel模板生成 ====================
def generate_template():
    """生成Excel数据模板"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    
    wb = Workbook()
    
    # 定位表
    ws1 = wb.active
    ws1.title = '定位表'
    headers1 = ['钻孔编号', '开孔坐标N', '开孔坐标E', '开孔高程R', '钻孔长度', '轨迹类型']
    for col, header in enumerate(headers1, 1):
        cell = ws1.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
    
    # 示例数据
    example1 = ['ZK901', 3182455.01, 523887.25, 286, 91.27, '曲']
    for col, val in enumerate(example1, 1):
        ws1.cell(row=2, column=col, value=val)
    
    # 测斜表
    ws2 = wb.create_sheet('测斜表')
    headers2 = ['钻孔编号', '各层位长度', '方位角', '倾角']
    for col, header in enumerate(headers2, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
    
    example2 = ['ZK901', 0, 150.05, -44.97]
    for col, val in enumerate(example2, 1):
        ws2.cell(row=2, column=col, value=val)
    
    # 岩性表
    ws3 = wb.create_sheet('岩性表')
    headers3 = ['钻孔编号', '上层位长度起始刻度', '下层位长度起始刻度', '岩性描述', '建模颜色']
    for col, header in enumerate(headers3, 1):
        cell = ws3.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
    
    example3 = ['ZK901', 0, 1.18, '第四系', '#8B7355']
    for col, val in enumerate(example3, 1):
        ws3.cell(row=2, column=col, value=val)
    
    # 调整列宽
    for ws in wb.worksheets:
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    template_path = TEMPLATE_FILE
    wb.save(template_path)
    return template_path

# ==================== 构建地质体（V2 - 优化版） ====================
def build_geological_bodies_with_volume_v2(loc_df, litho_df, survey_df,
                                            n_layers=None,
                                            rbf_function=None,
                                            rbf_smooth=None,
                                            grid_resolution=None,
                                            session_id=None,
                                            method=None,
                                            kriging_variogram=None):
    """
    构建地质体模型（含多层体数据）—— 归一化坐标训练+预测，原始坐标输出
    支持 RBF 和克里金两种插值方法。

    参数:
        n_layers: 体渲染层数，None=自动计算
        rbf_function: RBF核函数，None=使用config默认值
        rbf_smooth: RBF平滑度，None=使用config默认值
        grid_resolution: 网格分辨率，None=使用config默认值
        method: 'rbf' 或 'kriging'，None=使用config默认值
        kriging_variogram: 克里金变异函数模型，None=使用config默认值
    """
    from config import (
        RBF_FUNCTION as CFG_RBF, RBF_SMOOTH as CFG_SMOOTH,
        GRID_RESOLUTION as CFG_GRID, N_LAYERS as CFG_NLAYERS,
        INTERPOLATION_METHOD as CFG_METHOD,
        KRIGING_MODEL_DEFAULT_VARIOGRAM as CFG_KRIG_VGM
    )

    if n_layers is None:
        n_layers = CFG_NLAYERS  # 可能为None，后面会走自动计算
    if rbf_function is None:
        rbf_function = CFG_RBF
    if rbf_smooth is None:
        rbf_smooth = CFG_SMOOTH
    if grid_resolution is None:
        grid_resolution = CFG_GRID
    if method is None:
        method = CFG_METHOD
    if kriging_variogram is None:
        kriging_variogram = CFG_KRIG_VGM

    print(f"==> 建模插值方法: {method}")
    if method == 'kriging':
        print(f"==> 克里金变异函数: {kriging_variogram}")
    
    # ========== 1. 孔口坐标（X=N, Y=E 约定，与 plot_drill_holes_on_ax 一致）==========
    hole_coords = {}
    for _, row in loc_df.iterrows():
        hid = row['钻孔编号']
        hole_coords[hid] = (row['开孔坐标N'], row['开孔坐标E'], row['开孔高程R'])
    
    # ========== 2. 轨迹缓存 ==========
    traj_cache = {}
    for hid in loc_df['钻孔编号']:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            lengths, xs, ys, zs = compute_trajectory(surv)
            traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
    # ========== 3. 坐标归一化参数（按 X=N, Y=E 约定）==========
    base_x = loc_df['开孔坐标N'].min()
    base_y = loc_df['开孔坐标E'].min()
    span_x = loc_df['开孔坐标N'].max() - base_x
    span_y = loc_df['开孔坐标E'].max() - base_y
    span_max = max(span_x, span_y, 1.0)
    scale = 1000.0
    scale_factor = scale / span_max

    def normalize(x, y):
        return (x - base_x) * scale_factor, (y - base_y) * scale_factor

    def denormalize(x, y):
        return x / scale_factor + base_x, y / scale_factor + base_y
    
    # ========== 4. 收集岩性顶底点（归一化坐标）==========
    litho_groups = {}
    for _, seg in litho_df.iterrows():
        hid = seg['钻孔编号']
        d_top = seg['上层位长度起始刻度']
        d_bot = seg['下层位长度起始刻度']
        lith = seg['岩性描述']
        color = parse_color(seg['建模颜色'], lith)
        if hid not in hole_coords or hid not in traj_cache:
            continue
        n0, e0, z0 = hole_coords[hid]
        traj = traj_cache[hid]
        x_top, y_top, z_top = get_interpolated_coords(traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
        x_bot, y_bot, z_bot = get_interpolated_coords(traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
        x_top, y_top = x_top[0] + n0, y_top[0] + e0
        x_bot, y_bot = x_bot[0] + n0, y_bot[0] + e0
        z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
        
        if lith not in litho_groups:
            litho_groups[lith] = {'color': color, 'top': [], 'bottom': []}
        
        x_top_n, y_top_n = normalize(x_top, y_top)
        x_bot_n, y_bot_n = normalize(x_bot, y_bot)
        
        litho_groups[lith]['top'].append((x_top_n, y_top_n, z_top))
        litho_groups[lith]['bottom'].append((x_bot_n, y_bot_n, z_bot))
    
    # ========== 5. 归一化插值网格 ==========
    grid_res = grid_resolution
    xi_n = np.linspace(0.0, scale, grid_res)
    yi_n = np.linspace(0.0, scale * (span_y / span_max), grid_res)
    xi_n, yi_n = np.meshgrid(xi_n, yi_n)
    
    # 反归一化坐标用于最终输出
    xi_orig, yi_orig = denormalize(xi_n, yi_n)
    
    # ========== 6. 自动计算 n_layers ==========
    if n_layers is None:
        all_thicknesses = []
        for lith, data in litho_groups.items():
            for top, bottom in zip(data['top'], data['bottom']):
                thickness = abs(top[2] - bottom[2])
                if 0 < thickness < 1000:
                    all_thicknesses.append(thickness)
        if all_thicknesses:
            sorted_th = np.sort(all_thicknesses)
            p5, p95 = np.percentile(sorted_th, [5, 95])
            filtered = [t for t in sorted_th if p5 <= t <= p95]
            avg_thickness = np.mean(filtered) if filtered else np.mean(all_thicknesses)
            n_layers = max(5, min(25, int(6 + avg_thickness / 30)))
            print(f"==> 根据平均厚度 ({avg_thickness:.1f}m) 自动设置层数: {n_layers}")
        else:
            n_layers = 12
    
    # ========== 7. 逐岩性插值 ==========
    bodies = {}
    volume_data = {}
    
    for lith, data in litho_groups.items():
        n_top = len(data['top'])
        n_bot = len(data['bottom'])
        print(f"岩性 {lith}: {n_top} 个顶板点, {n_bot} 个底板点")
        
        # 过滤控制点过少的岩性（避免退化成平面）
        if n_top < 5 or n_bot < 5:
            print(f"!!! 跳过 {lith}：控制点过少，无法可靠插值")
            continue
        
        top_pts = np.array(data['top'])
        bot_pts = np.array(data['bottom'])
        
        # 凸包裁剪（归一化坐标）
        all_pts = np.vstack([top_pts[:, :2], bot_pts[:, :2]])
        try:
            hull = ConvexHull(all_pts)
            center = all_pts[:, :2].mean(axis=0)
            hull_pts = all_pts[hull.vertices][:, :2]

            # 自适应外扩：基于控制点平均空间间距
            from scipy.spatial import KDTree
            tree = KDTree(all_pts[:, :2])
            distances, _ = tree.query(all_pts[:, :2], k=2)  # k=2 因 k=1 返回自身
            avg_spacing = float(np.median(distances[:, 1]))

            # 外扩量 = 2 倍平均钻孔间距，保底下限 5（归一化单位）
            hull_radius = float(np.max(np.linalg.norm(hull_pts - center, axis=1)))
            expansion = max(5.0, 2.0 * avg_spacing)
            expansion_ratio = 1.0 + expansion / max(hull_radius, 1.0)

            expanded = center + (hull_pts - center) * expansion_ratio
            hull_path = Path(expanded)
            grid_points = np.column_stack((xi_n.ravel(), yi_n.ravel()))
            inside = hull_path.contains_points(grid_points).reshape(xi_n.shape)
        except Exception:
            inside = np.ones(xi_n.shape, dtype=bool)
                
        # ========== 插值（根据 method 分支） ==========
        Z_top = None
        Z_bot = None

        if method == 'kriging':
            # 克里金插值
            try:
                from pykrige.ok import OrdinaryKriging

                # 顶面
                ok_top = OrdinaryKriging(
                    top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
                    variogram_model=kriging_variogram,
                    nlags=6, enable_plotting=False, verbose=False
                )
                z_top_result, _ = ok_top.execute('grid',
                    np.linspace(xi_n.min(), xi_n.max(), xi_n.shape[1]),
                    np.linspace(yi_n.min(), yi_n.max(), xi_n.shape[0]))
                Z_top = z_top_result

                # 底面
                ok_bot = OrdinaryKriging(
                    bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
                    variogram_model=kriging_variogram,
                    nlags=6, enable_plotting=False, verbose=False
                )
                z_bot_result, _ = ok_bot.execute('grid',
                    np.linspace(xi_n.min(), xi_n.max(), xi_n.shape[1]),
                    np.linspace(yi_n.min(), yi_n.max(), xi_n.shape[0]))
                Z_bot = z_bot_result
            except Exception as e:
                print(f"!!! 岩性 {lith} 克里金插值失败: {e}，回退到 RBF")
                method_fallback = True
            else:
                method_fallback = False
        else:
            method_fallback = True

        if method_fallback:
            # RBF 插值（作为默认或回退）
            try:
                rbf_top = Rbf(top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
                              function=rbf_function, smooth=rbf_smooth)
                rbf_bot = Rbf(bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
                              function=rbf_function, smooth=rbf_smooth)
                Z_top = rbf_top(xi_n, yi_n)
                Z_bot = rbf_bot(xi_n, yi_n)
            except Exception as e:
                print(f"!!! 岩性 {lith} 插值失败: {e}")
                continue
        
        # 裁剪异常外推
        z_combined = np.concatenate([top_pts[:, 2], bot_pts[:, 2]])
        z_lo_data = np.percentile(z_combined, 0.5)
        z_hi_data = np.percentile(z_combined, 99.5)
        z_span = z_hi_data - z_lo_data if z_hi_data > z_lo_data else 1.0
        z_lo = z_lo_data - z_span * 0.5
        z_hi = z_hi_data + z_span * 0.5
        Z_top = np.clip(Z_top, z_lo, z_hi)
        Z_bot = np.clip(Z_bot, z_lo, z_hi)
        
        # 应用凸包掩膜
        Z_top[~inside] = np.nan
        Z_bot[~inside] = np.nan
        mask = Z_top > Z_bot
        Z_top_c = np.where(mask, Z_top, Z_bot)
        Z_bot_c = np.where(mask, Z_bot, Z_top)

        # 最小厚度约束：对已被 swap 的网格（原始 Z_top < Z_bot）施加最小厚度
        # 防止穿层修复后产生厚度接近 0 的退化单元格（不影响边界自然尖灭区）
        MIN_THICKNESS = 0.1  # 10cm
        swapped = ~mask
        thin_after_swap = (Z_top_c - Z_bot_c) < MIN_THICKNESS
        fix = swapped & thin_after_swap & ~np.isnan(Z_top_c) & ~np.isnan(Z_bot_c)
        if np.any(fix):
            Z_bot_c = np.where(fix, Z_top_c - MIN_THICKNESS, Z_bot_c)

        # 统一用反归一化坐标存储
        bodies[lith] = {
            'X': xi_orig, 'Y': yi_orig,
            'Z_top': Z_top_c, 'Z_bot': Z_bot_c,
            'color': data['color']
        }
        
        layers = []
        for k in range(n_layers + 2):
            t = k / (n_layers + 1)
            Z_layer = Z_top_c * (1 - t) + Z_bot_c * t
            layers.append(Z_layer)
        
        volume_data[lith] = {
            'X': xi_orig, 'Y': yi_orig,   # 必须是 xi_orig, 不是 xi
            'layers': layers,
            'color': data['color']
        }
        
        valid_count = int(np.sum(~np.isnan(Z_top_c)))
        print(f"==> 岩性 {lith} 插值成功，有效网格点: {valid_count}")

    # ========== 记录 RBF 分析数据 ==========
    try:
        if session_id:
            from .analysis_manager import record_rbf_data, _numpy_to_list
            from config import RBF_FUNCTION, RBF_SMOOTH, GRID_RESOLUTION

            layers_info = []
            for lith, data in litho_groups.items():
                if len(data['top']) < 3 or lith not in bodies:
                    continue

                body = bodies[lith]
                grid_x = body['X'][0, :].tolist()
                grid_y = body['Y'][:, 0].tolist()

                # 顶面
                top_pts = data['top']
                z_top_valid = body['Z_top'][~np.isnan(body['Z_top'])]
                layers_info.append({
                    'layer_name': lith,
                    'part_name': '顶面',
                    'control_points': [(float(p[0]), float(p[1]), float(p[2])) for p in top_pts],
                    'grid_x': grid_x,
                    'grid_y': grid_y,
                    'z_pred': _numpy_to_list(body['Z_top']),
                    'stats': {
                        'n_points': len(top_pts),
                        'min': float(np.min(z_top_valid)) if len(z_top_valid) > 0 else None,
                        'max': float(np.max(z_top_valid)) if len(z_top_valid) > 0 else None,
                        'mean': float(np.mean(z_top_valid)) if len(z_top_valid) > 0 else None,
                        'std': float(np.std(z_top_valid)) if len(z_top_valid) > 0 else None
                    }
                })

                # 底面
                bot_pts = data['bottom']
                z_bot_valid = body['Z_bot'][~np.isnan(body['Z_bot'])]
                layers_info.append({
                    'layer_name': lith,
                    'part_name': '底面',
                    'control_points': [(float(p[0]), float(p[1]), float(p[2])) for p in bot_pts],
                    'grid_x': grid_x,
                    'grid_y': grid_y,
                    'z_pred': _numpy_to_list(body['Z_bot']),
                    'stats': {
                        'n_points': len(bot_pts),
                        'min': float(np.min(z_bot_valid)) if len(z_bot_valid) > 0 else None,
                        'max': float(np.max(z_bot_valid)) if len(z_bot_valid) > 0 else None,
                        'mean': float(np.mean(z_bot_valid)) if len(z_bot_valid) > 0 else None,
                        'std': float(np.std(z_bot_valid)) if len(z_bot_valid) > 0 else None
                    }
                })

            rbf_params = {
                'rbf_function': rbf_function or RBF_FUNCTION,
                'rbf_smooth': rbf_smooth if rbf_smooth is not None else RBF_SMOOTH,
                'grid_resolution': grid_resolution or GRID_RESOLUTION,
                'n_layers': n_layers if n_layers else 'auto'
            }
            record_rbf_data(session_id, rbf_params, layers_info)
    except Exception as e:
        print(f"!!! 记录 RBF 分析数据失败: {e}")
    # =====================================

    return bodies, volume_data


# ==================== 克里金插值分析 ====================
def perform_kriging_analysis(loc_df, litho_df, survey_df,
                              n_layers=None,
                              rbf_function=None,
                              rbf_smooth=None,
                              grid_resolution=None,
                              variogram_model=None,
                              output_dir=None,
                              base_name=None):
    """
    执行克里金插值分析，生成与 RBF 对比的 2x2 并排图。

    参数:
        loc_df: 定位表 DataFrame
        litho_df: 岩性表 DataFrame
        survey_df: 测斜表 DataFrame
        n_layers: 体渲染层数，None=自动计算
        rbf_function/rbf_smooth: RBF 参数（用于生成对比的 RBF 图）
        grid_resolution: 网格分辨率
        variogram_model: 克里金变异函数模型

    返回:
        dict: {
            'comparison_path': 并排图路径,
            'rbf_path': RBF 单独图路径,
            'kriging_path': 克里金单独图路径,
            'variance_path': 方差图路径,
            'analysis_text': 分析结论文本,
            'layer_count': 分析的岩性层数,
            'point_counts': 各层控制点数量
        }
    """
    from config import (RBF_FUNCTION as CFG_RBF, RBF_SMOOTH as CFG_SMOOTH,
                        GRID_RESOLUTION as CFG_GRID, N_LAYERS as CFG_NLAYERS,
                        KRIGING_VARIOGRAM_MODEL as CFG_VARIOGRAM,
                        FIGURE_DPI, FIGURE_WIDTH, FIGURE_HEIGHT)
    from pykrige.ok import OrdinaryKriging

    if n_layers is None:
        n_layers = CFG_NLAYERS
    if rbf_function is None:
        rbf_function = CFG_RBF
    if rbf_smooth is None:
        rbf_smooth = CFG_SMOOTH
    if grid_resolution is None:
        grid_resolution = CFG_GRID
    if variogram_model is None:
        variogram_model = CFG_VARIOGRAM
    if output_dir is None:
        output_dir = OUTPUT_FOLDER
    if base_name is None:
        from datetime import datetime
        base_name = f'kriging_{datetime.now().strftime("%y%m%d%H%M")}'

    os.makedirs(output_dir, exist_ok=True)

    # ========== 1. 孔口坐标 & 轨迹缓存 ==========
    hole_coords = {}
    for _, row in loc_df.iterrows():
        hid = row['钻孔编号']
        hole_coords[hid] = (row['开孔坐标N'], row['开孔坐标E'], row['开孔高程R'])

    traj_cache = {}
    for hid in loc_df['钻孔编号']:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            lengths, xs, ys, zs = compute_trajectory(surv)
            traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}

    # ========== 2. 坐标归一化参数（与 RBF 保持一致） ==========
    base_x = loc_df['开孔坐标N'].min()
    base_y = loc_df['开孔坐标E'].min()
    span_x = loc_df['开孔坐标N'].max() - base_x
    span_y = loc_df['开孔坐标E'].max() - base_y
    span_max = max(span_x, span_y, 1.0)
    scale = 1000.0
    scale_factor = scale / span_max

    def normalize(x, y):
        return (x - base_x) * scale_factor, (y - base_y) * scale_factor

    def denormalize(x, y):
        return x / scale_factor + base_x, y / scale_factor + base_y

    # ========== 3. 收集岩性顶底点（归一化坐标） ==========
    litho_groups = {}
    for _, seg in litho_df.iterrows():
        hid = seg['钻孔编号']
        d_top = seg['上层位长度起始刻度']
        d_bot = seg['下层位长度起始刻度']
        lith = seg['岩性描述']
        color = parse_color(seg['建模颜色'], lith)
        if hid not in hole_coords or hid not in traj_cache:
            continue
        n0, e0, z0 = hole_coords[hid]
        traj = traj_cache[hid]
        x_top, y_top, z_top = get_interpolated_coords(traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
        x_bot, y_bot, z_bot = get_interpolated_coords(traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
        x_top, y_top = x_top[0] + n0, y_top[0] + e0
        x_bot, y_bot = x_bot[0] + n0, y_bot[0] + e0
        z_top, z_bot = z_top[0] + z0, z_bot[0] + z0

        if lith not in litho_groups:
            litho_groups[lith] = {'color': color, 'top': [], 'bottom': []}
        x_top_n, y_top_n = normalize(x_top, y_top)
        x_bot_n, y_bot_n = normalize(x_bot, y_bot)
        litho_groups[lith]['top'].append((x_top_n, y_top_n, z_top))
        litho_groups[lith]['bottom'].append((x_bot_n, y_bot_n, z_bot))

    # ========== 4. 归一化插值网格 ==========
    grid_res = grid_resolution
    xi_n = np.linspace(0.0, scale, grid_res)
    yi_n = np.linspace(0.0, scale * (span_y / span_max), grid_res)
    xi_n, yi_n = np.meshgrid(xi_n, yi_n)
    xi_orig, yi_orig = denormalize(xi_n, yi_n)

    # ========== 5. 自动计算 n_layers ==========
    if n_layers is None:
        all_thicknesses = []
        for lith, data in litho_groups.items():
            for top, bottom in zip(data['top'], data['bottom']):
                thickness = abs(top[2] - bottom[2])
                if 0 < thickness < 1000:
                    all_thicknesses.append(thickness)
        if all_thicknesses:
            sorted_th = np.sort(all_thicknesses)
            p5, p95 = np.percentile(sorted_th, [5, 95])
            filtered = [t for t in sorted_th if p5 <= t <= p95]
            avg_thickness = np.mean(filtered) if filtered else np.mean(all_thicknesses)
            n_layers = max(5, min(25, int(6 + avg_thickness / 30)))
        else:
            n_layers = 12

    # ========== 6. 逐岩性插值并生成对比图 ==========
    # 取中间层作为对比截面
    mid_layer_idx = n_layers // 2

    all_results = {}
    comparison_paths = []
    point_counts_summary = {}
    analysis_lines = []
    layer_count = 0

    for lith, data in litho_groups.items():
        n_top = len(data['top'])
        n_bot = len(data['bottom'])
        if n_top < 5 or n_bot < 5:
            msg = f"【{lith}】跳过：控制点过少（顶{n_top}个/底{n_bot}个，需要≥5个）"
            print(f"!!! 克里金跳过 {msg}")
            analysis_lines.append(msg)
            continue

        top_pts = np.array(data['top'])
        bot_pts = np.array(data['bottom'])
        color_rgb = data['color'][:3]
        point_counts_summary[lith] = {'top': n_top, 'bottom': n_bot}

        # 凸包裁剪
        all_pts = np.vstack([top_pts[:, :2], bot_pts[:, :2]])
        try:
            hull = ConvexHull(all_pts)
            center = all_pts[:, :2].mean(axis=0)
            hull_pts = all_pts[hull.vertices][:, :2]
            expanded = center + (hull_pts - center) * 1.03
            hull_path = Path(expanded)
            grid_points = np.column_stack((xi_n.ravel(), yi_n.ravel()))
            inside = hull_path.contains_points(grid_points).reshape(xi_n.shape)
        except Exception:
            inside = np.ones(xi_n.shape, dtype=bool)

        # ----- RBF 插值（用于对比） -----
        try:
            rbf_top = Rbf(top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
                          function=rbf_function, smooth=rbf_smooth)
            rbf_bot = Rbf(bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
                          function=rbf_function, smooth=rbf_smooth)
            RBF_Z_top = rbf_top(xi_n, yi_n)
            RBF_Z_bot = rbf_bot(xi_n, yi_n)
        except Exception:
            print(f"!!! {lith} RBF 插值失败，跳过")
            analysis_lines.append(f"【{lith}】RBF 插值失败，跳过")
            continue

        # ----- 克里金插值 -----
        try:
            top_x_n = top_pts[:, 0]
            top_y_n = top_pts[:, 1]
            top_z = top_pts[:, 2]
            bot_x_n = bot_pts[:, 0]
            bot_y_n = bot_pts[:, 1]
            bot_z = bot_pts[:, 2]

            # 顶面克里金
            OK_top = OrdinaryKriging(
                top_x_n, top_y_n, top_z,
                variogram_model=variogram_model,
                verbose=False,
                enable_statistics=True
            )
            KRIG_Z_top, KRIG_SIGMA_top = OK_top.execute('grid', xi_n[0], yi_n[:, 0])

            # 底面克里金
            OK_bot = OrdinaryKriging(
                bot_x_n, bot_y_n, bot_z,
                variogram_model=variogram_model,
                verbose=False,
                enable_statistics=True
            )
            KRIG_Z_bot, KRIG_SIGMA_bot = OK_bot.execute('grid', xi_n[0], yi_n[:, 0])

        except Exception as e:
            err_msg = f"【{lith}】克里金插值失败: {str(e)[:100]}"
            print(f"!!! {err_msg}")
            analysis_lines.append(err_msg)
            continue

        layer_count += 1

        # ========== 裁剪异常值与凸包掩膜 ==========
        z_combined = np.concatenate([top_pts[:, 2], bot_pts[:, 2]])
        z_lo_data = np.percentile(z_combined, 0.5)
        z_hi_data = np.percentile(z_combined, 99.5)
        z_span = z_hi_data - z_lo_data if z_hi_data > z_lo_data else 1.0
        z_lo = z_lo_data - z_span * 0.5
        z_hi = z_hi_data + z_span * 0.5

        KRIG_Z_top = np.clip(KRIG_Z_top, z_lo, z_hi)
        KRIG_Z_bot = np.clip(KRIG_Z_bot, z_lo, z_hi)
        KRIG_SIGMA_top = np.abs(KRIG_SIGMA_top)
        KRIG_SIGMA_bot = np.abs(KRIG_SIGMA_bot)

        RBF_Z_top = np.clip(RBF_Z_top, z_lo, z_hi)
        RBF_Z_bot = np.clip(RBF_Z_bot, z_lo, z_hi)

        # 凸包掩膜
        KRIG_Z_top[~inside] = np.nan
        KRIG_Z_bot[~inside] = np.nan
        KRIG_SIGMA_top[~inside] = np.nan
        KRIG_SIGMA_bot[~inside] = np.nan
        RBF_Z_top[~inside] = np.nan
        RBF_Z_bot[~inside] = np.nan

        # 确保顶面 > 底面（交换 if needed）
        for Z_top, Z_bot in [(KRIG_Z_top, KRIG_Z_bot), (RBF_Z_top, RBF_Z_bot)]:
            mask = Z_top < Z_bot
            tmp = Z_top.copy()
            Z_top[mask] = Z_bot[mask]
            Z_bot[mask] = tmp[mask]

        # 取中间层做截面对比
        t_mid = mid_layer_idx / (n_layers + 1)
        KRIG_Z_mid = KRIG_Z_top * (1 - t_mid) + KRIG_Z_bot * t_mid
        RBF_Z_mid = RBF_Z_top * (1 - t_mid) + RBF_Z_bot * t_mid

        # 克里金的预测方差取顶底平均值作为截面
        KRIG_SIGMA_mid = (KRIG_SIGMA_top + KRIG_SIGMA_bot) / 2
        KRIG_SIGMA_mid[~inside] = np.nan

        # 差值
        DIFF = RBF_Z_mid - KRIG_Z_mid

        # ========== 绘制 2x2 对比图 ==========
        fig, axes = plt.subplots(2, 2, figsize=(FIGURE_WIDTH + 2, FIGURE_HEIGHT + 1))
        fig.suptitle(f'克里金 vs RBF 对比分析 — {lith}', fontsize=16, fontweight='bold', y=0.98)

        titles = [
            (f'克里金插值 ({variogram_model})', KRIG_Z_mid, None, 'RdBu_r'),
            (f'RBF 插值 ({rbf_function})', RBF_Z_mid, None, 'RdBu_r'),
            ('预测标准差（克里金）', KRIG_SIGMA_mid, 'm', 'YlOrRd'),
            ('RBF - 克里金 差值', DIFF, None, 'coolwarm')
        ]

        for idx, (title, data_arr, unit, cmap) in enumerate(titles):
            ax = axes[idx // 2][idx % 2]
            valid_data = data_arr[~np.isnan(data_arr)]
            if len(valid_data) == 0:
                ax.text(0.5, 0.5, '无有效数据', ha='center', va='center', transform=ax.transAxes, fontsize=12)
                ax.set_title(title, fontsize=11)
                continue

            vmin, vmax = np.percentile(valid_data, [1, 99]) if len(valid_data) > 10 else (valid_data.min(), valid_data.max())
            if unit == 'm' and abs(vmax - vmin) < 1:
                vmin -= 5
                vmax += 5

            cf = ax.contourf(xi_orig, yi_orig, data_arr, levels=20, cmap=cmap, vmin=vmin, vmax=vmax)
            # 叠加钻孔控制点
            ax.scatter(top_pts[:, 0] / scale_factor + base_x,
                       top_pts[:, 1] / scale_factor + base_y,
                       c='black', s=12, marker='o', alpha=0.6, label='控制点')
            ax.set_title(title, fontsize=11)
            ax.set_xlabel('开孔坐标N (m)', fontsize=8)
            ax.set_ylabel('开孔坐标E (m)', fontsize=8)
            # 坐标刻度统一为「保留两位小数的普通数字」（如 3232138.97）
            ax.ticklabel_format(style='plain', axis='both', useOffset=False)
            ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            ax.tick_params(axis='both', labelsize=7)
            fig.colorbar(cf, ax=ax, shrink=0.7)

        plt.tight_layout(rect=[0, 0, 1, 0.95])

        # 保存对比图
        lith_safe = lith.replace('/', '_').replace('\\', '_').replace(' ', '_')
        comparison_filename = f'{base_name}_comparison_{lith_safe}.png'
        comparison_path = os.path.join(output_dir, comparison_filename)
        plt.savefig(comparison_path, dpi=FIGURE_DPI, bbox_inches='tight', facecolor='white')
        plt.close()

        comparison_paths.append({
            'lith': lith,
            'path': comparison_path,
            'url': f'/outputs/{os.path.basename(comparison_path)}'
        })

        # ========== 分析结论文本 ==========
        # 使用 np.square 避免 numpy 的 ** 运算符返回只读数组
        diff_sq = np.square(DIFF)  # 总是返回可写数组
        finite_mask = np.isfinite(diff_sq)
        n_finite = np.sum(finite_mask)
        if n_finite == 0:
            rmse = 0.0
        else:
            rmse = np.sqrt(np.sum(diff_sq[finite_mask]) / n_finite)
        max_diff = np.nanmax(np.abs(DIFF)) if not np.all(np.isnan(DIFF)) else 0
        mean_sigma = np.nanmean(KRIG_SIGMA_mid) if not np.all(np.isnan(KRIG_SIGMA_mid)) else 0
        rbf_range = np.nanmax(RBF_Z_mid) - np.nanmin(RBF_Z_mid) if not np.all(np.isnan(RBF_Z_mid)) else 0
        krig_range = np.nanmax(KRIG_Z_mid) - np.nanmin(KRIG_Z_mid) if not np.all(np.isnan(KRIG_Z_mid)) else 0

        analysis_lines.append(
            f"【{lith}】控制点: 顶{n_top}个/底{n_bot}个 | "
            f"RMSE={rmse:.2f}m | 最大偏差={max_diff:.2f}m | "
            f"RBF范围={rbf_range:.1f}m | 克里金范围={krig_range:.1f}m | "
            f"平均预测标准差={mean_sigma:.2f}m"
        )

        all_results[lith] = {
            'RBF_Z_mid': RBF_Z_mid,
            'KRIG_Z_mid': KRIG_Z_mid,
            'KRIG_SIGMA_mid': KRIG_SIGMA_mid,
            'DIFF': DIFF,
            'comparison_path': comparison_path,
            'rmse': float(rmse),
            'max_diff': float(max_diff)
        }

    analysis_text = (
        f"克里金插值分析报告\n"
        f"{'='*50}\n"
        f"变异函数模型: {variogram_model}\n"
        f"分析岩性层数: {layer_count}\n"
        f"网格分辨率: {grid_resolution}×{grid_resolution}\n"
        f"对比截面: 第{mid_layer_idx+1}/{n_layers+2}层\n"
        f"{'='*50}\n"
        + "\n".join(analysis_lines) + "\n"
        f"{'='*50}\n"
        f"* RMSE 表示 RBF 与克里金之间的均方根误差\n"
        f"* 预测标准差越小表示克里金对该区域预测越自信\n"
        f"* 两者差异大时建议检查数据质量问题"
    )

    return {
        'comparison_paths': comparison_paths,
        'analysis_text': analysis_text,
        'layer_count': layer_count,
        'point_counts': point_counts_summary,
        'all_results': {k: {kk: vv for kk, vv in v.items() if kk != 'RBF_Z_mid' and kk != 'KRIG_Z_mid' and kk != 'KRIG_SIGMA_mid' and kk != 'DIFF'}
                        for k, v in all_results.items()}
    }


# ==================== 克里金曲面数值分析（新） ====================

def run_kriging_2d(x_ctrl, y_ctrl, z_ctrl, grid_res, variogram_model='spherical'):
    """
    执行 2D 普通克里金插值。

    参数:
        x_ctrl, y_ctrl, z_ctrl: 控制点坐标与值
        grid_res: 网格分辨率
        variogram_model: 变异函数模型

    返回:
        dict: {grid_x, grid_y, z_pred, z_var, success, error}
    """
    import numpy as np
    from pykrige.ok import OrdinaryKriging

    n_points = len(x_ctrl)
    if n_points < 3:
        return {
            'success': False,
            'error': f'控制点数量不足（{n_points} < 3），无法插值'
        }

    # 去重（克里金对重复点敏感）
    points = list(set(zip(x_ctrl, y_ctrl, z_ctrl)))
    if len(points) < 3:
        return {
            'success': False,
            'error': f'去重后控制点不足（{len(points)} < 3）'
        }

    x_u = np.array([p[0] for p in points])
    y_u = np.array([p[1] for p in points])
    z_u = np.array([p[2] for p in points])

    gx = np.linspace(x_u.min(), x_u.max(), grid_res)
    gy = np.linspace(y_u.min(), y_u.max(), grid_res)

    try:
        ok = OrdinaryKriging(
            x_u, y_u, z_u,
            variogram_model=variogram_model,
            nlags=6,
            enable_plotting=False,
            verbose=False
        )
        z_pred, z_var = ok.execute('grid', gx, gy)
    except Exception as e:
        return {
            'success': False,
            'error': f'克里金插值失败: {str(e)}'
        }

    return {
        'grid_x': gx,
        'grid_y': gy,
        'z_pred': z_pred,
        'z_var': z_var,
        'success': True,
        'error': None
    }


def run_rbf_2d_for_comparison(x_ctrl, y_ctrl, z_ctrl, grid_x, grid_y,
                                rbf_function=None, rbf_smooth=None):
    """
    用 RBF 对同样的控制点插值，输出与克里金相同形状的网格。
    """
    import numpy as np
    from scipy.interpolate import Rbf
    from config import RBF_FUNCTION, RBF_SMOOTH

    rbf_function = rbf_function or RBF_FUNCTION
    rbf_smooth = rbf_smooth if rbf_smooth is not None else RBF_SMOOTH

    try:
        rbf = Rbf(x_ctrl, y_ctrl, z_ctrl,
                  function=rbf_function, smooth=rbf_smooth)
        gx, gy = np.meshgrid(grid_x, grid_y)
        z_pred = rbf(gx, gy)
        return z_pred
    except Exception as e:
        print(f"!!! RBF 2D 插值失败: {e}")
        return None


def plot_kriging_comparison(
    layer_name, part_name,
    grid_x, grid_y, z_kriging, z_variance, z_rbf,
    output_path
):
    """
    生成克里金 vs RBF 的并排对比图（2x2 布局）。
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from config import FIGURE_DPI, KRIGING_VALUE_CMAP, KRIGING_VARIANCE_CMAP

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    gx, gy = np.meshgrid(grid_x, grid_y)

    all_values = np.concatenate([
        z_rbf[~np.isnan(z_rbf)].ravel(),
        z_kriging[~np.isnan(z_kriging)].ravel()
    ])
    vmin = np.min(all_values) if len(all_values) > 0 else 0
    vmax = np.max(all_values) if len(all_values) > 0 else 1

    # 左上：RBF
    ax1 = axes[0, 0]
    im1 = ax1.pcolormesh(gx, gy, z_rbf, cmap=KRIGING_VALUE_CMAP,
                          vmin=vmin, vmax=vmax, shading='auto')
    ax1.set_title(f'RBF 插值 - {layer_name} {part_name}', fontsize=13, fontweight='bold')
    ax1.set_xlabel('Easting (m)')
    ax1.set_ylabel('Northing (m)')
    plt.colorbar(im1, ax=ax1, label='高程 (m)')

    # 右上：克里金
    ax2 = axes[0, 1]
    im2 = ax2.pcolormesh(gx, gy, z_kriging, cmap=KRIGING_VALUE_CMAP,
                          vmin=vmin, vmax=vmax, shading='auto')
    ax2.set_title(f'克里金插值 - {layer_name} {part_name}', fontsize=13, fontweight='bold')
    ax2.set_xlabel('Easting (m)')
    ax2.set_ylabel('Northing (m)')
    plt.colorbar(im2, ax=ax2, label='高程 (m)')

    # 左下：差异图
    ax3 = axes[1, 0]
    diff = z_kriging - z_rbf
    max_abs = np.nanmax(np.abs(diff)) if not np.all(np.isnan(diff)) else 1
    im3 = ax3.pcolormesh(gx, gy, diff, cmap='RdBu_r',
                          vmin=-max_abs, vmax=max_abs,
                          shading='auto')
    ax3.set_title('差异图（克里金 - RBF）', fontsize=13, fontweight='bold')
    ax3.set_xlabel('Easting (m)')
    ax3.set_ylabel('Northing (m)')
    plt.colorbar(im3, ax=ax3, label='差异 (m)')

    # 右下：方差
    ax4 = axes[1, 1]
    im4 = ax4.pcolormesh(gx, gy, z_variance, cmap=KRIGING_VARIANCE_CMAP,
                          shading='auto')
    ax4.set_title(f'克里金预测方差 - {layer_name} {part_name}', fontsize=13, fontweight='bold')
    ax4.set_xlabel('Easting (m)')
    ax4.set_ylabel('Northing (m)')
    plt.colorbar(im4, ax=ax4, label='方差')

    # 坐标刻度统一为「保留两位小数的普通数字」（如 3232138.97）：
    # 关掉科学计数法与 matplotlib 默认的大数偏移量（1e6）
    for ax in axes.ravel():
        ax.ticklabel_format(style='plain', axis='both', useOffset=False)
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

    fig.suptitle(f'{layer_name} - {part_name} 克里金数值分析',
                 fontsize=16, fontweight='bold', y=0.995)

    plt.tight_layout()
    plt.savefig(output_path, dpi=FIGURE_DPI, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path


def generate_kriging_analysis_for_layer(
    layer_name, top_pts, bot_pts, output_dir, base_name,
    variogram_model=None, rbf_function=None, rbf_smooth=None
):
    """
    对单个岩性层的顶面和底面执行克里金分析，输出对比图。

    返回:
        dict: {layer_name, top_path, bot_path, top_stats, bot_stats,
               top_control_points, bot_control_points,
               top_grid_x, top_grid_y, bot_grid_x, bot_grid_y,
               top_z_kriging, top_z_variance, bot_z_kriging, bot_z_variance,
               warnings}
    """
    import os
    import numpy as np
    from config import (
        GRID_RESOLUTION, KRIGING_GRID_RES, KRIGING_DEFAULT_VARIOGRAM,
        KRIGING_MIN_POINTS_WARN
    )

    grid_res = KRIGING_GRID_RES or GRID_RESOLUTION
    variogram_model = variogram_model or KRIGING_DEFAULT_VARIOGRAM

    warnings = []
    result = {
        'layer_name': layer_name,
        'top_path': None,
        'bot_path': None,
        'top_stats': None,
        'bot_stats': None,
        'top_control_points': [],
        'bot_control_points': [],
        'top_grid_x': [],
        'top_grid_y': [],
        'bot_grid_x': [],
        'bot_grid_y': [],
        'top_z_kriging': [],
        'top_z_variance': [],
        'bot_z_kriging': [],
        'bot_z_variance': [],
        'warnings': warnings
    }

    # 处理顶面
    if len(top_pts) >= 3:
        if len(top_pts) < KRIGING_MIN_POINTS_WARN:
            warnings.append(f'{layer_name} 顶面控制点仅 {len(top_pts)} 个，分析结果可靠性较低')

        print(f"==> 分析 {layer_name} 顶面（{len(top_pts)} 个控制点）")
        kriging_result = run_kriging_2d(
            top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
            grid_res, variogram_model
        )

        if kriging_result['success']:
            z_rbf = run_rbf_2d_for_comparison(
                top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
                kriging_result['grid_x'], kriging_result['grid_y'],
                rbf_function, rbf_smooth
            )

            if z_rbf is not None:
                top_path = os.path.join(
                    output_dir,
                    f'{base_name}_kriging_{layer_name}_top.png'
                )
                plot_kriging_comparison(
                    layer_name, '顶面',
                    kriging_result['grid_x'], kriging_result['grid_y'],
                    kriging_result['z_pred'], kriging_result['z_var'],
                    z_rbf,
                    top_path
                )
                result['top_path'] = top_path
                result['top_stats'] = {
                    'n_points': int(len(top_pts)),
                    'variance_mean': float(np.nanmean(kriging_result['z_var'])),
                    'variance_max': float(np.nanmax(kriging_result['z_var'])),
                    'variance_min': float(np.nanmin(kriging_result['z_var']))
                }
                result['top_control_points'] = [
                    (float(p[0]), float(p[1]), float(p[2])) for p in top_pts
                ]
                result['top_grid_x'] = kriging_result['grid_x'].tolist()
                result['top_grid_y'] = kriging_result['grid_y'].tolist()
                result['top_z_kriging'] = kriging_result['z_pred'].ravel().tolist()
                result['top_z_variance'] = kriging_result['z_var'].ravel().tolist()
        else:
            warnings.append(f'{layer_name} 顶面克里金失败: {kriging_result["error"]}')
    else:
        warnings.append(f'{layer_name} 顶面控制点不足（{len(top_pts)} < 3），跳过')

    # 处理底面
    if len(bot_pts) >= 3:
        if len(bot_pts) < KRIGING_MIN_POINTS_WARN:
            warnings.append(f'{layer_name} 底面控制点仅 {len(bot_pts)} 个，分析结果可靠性较低')

        print(f"==> 分析 {layer_name} 底面（{len(bot_pts)} 个控制点）")
        kriging_result = run_kriging_2d(
            bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
            grid_res, variogram_model
        )

        if kriging_result['success']:
            z_rbf = run_rbf_2d_for_comparison(
                bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
                kriging_result['grid_x'], kriging_result['grid_y'],
                rbf_function, rbf_smooth
            )

            if z_rbf is not None:
                bot_path = os.path.join(
                    output_dir,
                    f'{base_name}_kriging_{layer_name}_bot.png'
                )
                plot_kriging_comparison(
                    layer_name, '底面',
                    kriging_result['grid_x'], kriging_result['grid_y'],
                    kriging_result['z_pred'], kriging_result['z_var'],
                    z_rbf,
                    bot_path
                )
                result['bot_path'] = bot_path
                result['bot_stats'] = {
                    'n_points': int(len(bot_pts)),
                    'variance_mean': float(np.nanmean(kriging_result['z_var'])),
                    'variance_max': float(np.nanmax(kriging_result['z_var'])),
                    'variance_min': float(np.nanmin(kriging_result['z_var']))
                }
                result['bot_control_points'] = [
                    (float(p[0]), float(p[1]), float(p[2])) for p in bot_pts
                ]
                result['bot_grid_x'] = kriging_result['grid_x'].tolist()
                result['bot_grid_y'] = kriging_result['grid_y'].tolist()
                result['bot_z_kriging'] = kriging_result['z_pred'].ravel().tolist()
                result['bot_z_variance'] = kriging_result['z_var'].ravel().tolist()
        else:
            warnings.append(f'{layer_name} 底面克里金失败: {kriging_result["error"]}')
    else:
        warnings.append(f'{layer_name} 底面控制点不足（{len(bot_pts)} < 3），跳过')

    return result


def transform_xy_to_lonlat(x, y, zone=None):
    """
    将 CGCS2000 3度带高斯投影坐标转为经纬度
    x: 东向坐标（可能包含带号，如 40420450.71）
    y: 北向坐标
    zone: 若为 None，则从 x 中自动提取带号（带号 = floor(x/1e6)）
    """
    # 自动提取带号
    if zone is None:
        # 如果 x > 1e6，说明包含了带号
        if x > 1e6:
            zone = int(x // 1_000_000)
            x = x - zone * 1_000_000
        else:
            zone = 40  # 默认带号（可根据实际情况调整）

    proj_str = f'+proj=tmerc +lat_0=0 +lon_0={zone*3} +k=1 +x_0=500000 +y_0=0 +ellps=GRS80 +units=m +no_defs'
    transformer = Transformer.from_crs(proj_str, 'EPSG:4326')
    lon, lat = transformer.transform(x, y)
    return lon, lat

def add_points_to_data(loc_df):
    points = []
    for _, row in loc_df.iterrows():
        try:
            lon, lat = transform_xy_to_lonlat(row['开孔坐标E'], row['开孔坐标N'])
            points.append({
                '钻孔编号': row['钻孔编号'],
                'lon': lon,                       # 经度
                'lat': lat,                       # 纬度
                '开孔坐标E': row['开孔坐标E'],     # 原始投影坐标（东）
                '开孔坐标N': row['开孔坐标N'],     # 原始投影坐标（北）
                '开孔高程R': row['开孔高程R'],
                '钻孔长度': row.get('钻孔长度', '')
            })
        except Exception as e:
            print(f"坐标转换失败 {row['钻孔编号']}: {e}")
    return points


def _compute_composite_scores(all_results):
    """
    对所有参数组合计算综合评分（归一化加权法）。

    对 RMSE、MAE、max_error 做 min-max 归一化后加权求和（值越小越差），
    再做 1−score 反转使得得分越高模型越好（1=最优，0=最差）。
    max_error 先做温和截尾（winsorize）防止极端值扭曲归一化。

    返回:
        修改 all_results 中的每个 entry，增加 'composite_score' 字段
    """
    import numpy as np
    from config import (
        SCORE_WEIGHT_RMSE, SCORE_WEIGHT_MAE, SCORE_WEIGHT_MAX_ERROR,
        SCORE_WINSORIZE_PERCENTILE
    )

    if len(all_results) == 0:
        return

    rmse_vals = np.array([e['rmse'] for e in all_results if e.get('rmse') is not None])
    mae_vals = np.array([e['mae'] for e in all_results if e.get('mae') is not None])
    max_vals = np.array([e['max_error'] for e in all_results if e.get('max_error') is not None])

    if len(rmse_vals) == 0:
        return

    # 温和截尾 max_error（p95 封顶）
    p95 = np.percentile(max_vals, SCORE_WINSORIZE_PERCENTILE)
    max_vals_clipped = np.clip(max_vals, None, p95)
    # 同步 clip all_results 中的值
    for e in all_results:
        if e.get('max_error') is not None:
            e['_max_error_clipped'] = min(e['max_error'], p95)

    def _norm(vals, vmin, vmax):
        if vmax - vmin < 1e-10:
            return np.zeros_like(vals)
        return (vals - vmin) / (vmax - vmin)

    norm_rmse = _norm(rmse_vals, rmse_vals.min(), rmse_vals.max())
    norm_mae = _norm(mae_vals, mae_vals.min(), mae_vals.max())
    norm_max = _norm(max_vals_clipped, max_vals_clipped.min(), max_vals_clipped.max())

    for i, e in enumerate(all_results):
        if e.get('rmse') is None:
            e['composite_score'] = float('-inf')
            continue
        r_idx = np.where(rmse_vals == e['rmse'])[0][0]
        m_idx = np.where(mae_vals == e['mae'])[0][0]
        x_idx = np.where(max_vals == e['max_error'])[0][0]
        raw = (SCORE_WEIGHT_RMSE * norm_rmse[r_idx]
             + SCORE_WEIGHT_MAE * norm_mae[m_idx]
             + SCORE_WEIGHT_MAX_ERROR * norm_max[x_idx])
        # 反转：得分越高模型越好（1=最优，0=最差）
        e['composite_score'] = round(float(1.0 - raw), 6)


def evaluate_rbf_loocv(x, y, z, rbf_function='multiquadric', smooth=0.01, epsilon=None):
    """
    用留一交叉验证（LOOCV）评估 RBF 模型的泛化误差。

    参数
    ----
    x, y, z : numpy 数组，控制点坐标
    rbf_function : str，核函数名
    smooth : float，平滑度
    epsilon : float 或 None，高斯核的形状参数

    返回
    ----
    dict，包含 rmse, mae, max_error, n_points 等
    """
    n = len(x)
    if n < 5:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': f'控制点数量不足（{n} < 5），无法可靠评估'
        }

    # 归一化坐标
    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()
    z_min, z_max = z.min(), z.max()

    x_span = x_max - x_min if x_max > x_min else 1.0
    y_span = y_max - y_min if y_max > y_min else 1.0
    z_span = z_max - z_min if z_max > z_min else 1.0

    x_n = (x - x_min) / x_span
    y_n = (y - y_min) / y_span
    z_n = (z - z_min) / z_span

    errors = []
    needs_epsilon = rbf_function in ['gaussian', 'multiquadric',
                                      'inverse_multiquadric', 'inverse']

    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False

        x_train = x_n[mask]
        y_train = y_n[mask]
        z_train = z_n[mask]

        try:
            kwargs = {'function': rbf_function, 'smooth': smooth}
            if epsilon is not None and needs_epsilon:
                kwargs['epsilon'] = epsilon

            rbf = Rbf(x_train, y_train, z_train, **kwargs)
            z_pred_val = float(rbf(x_n[i], y_n[i]))
            # 检测数值不稳定：预测值远超出归一化范围（归一化数据在 [0,1]）
            if not np.isfinite(z_pred_val) or abs(z_pred_val) > 10:
                continue
            err = (z_pred_val - float(z_n[i])) * z_span
            errors.append(err)
        except Exception:
            continue

    if len(errors) == 0:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': '所有点拟合均失败'
        }

    # 二次过滤 NaN，防止 numpy copy 损坏（numpy 1.26.4 bug）
    clean_errors = [e for e in errors if not np.isnan(e)]
    if len(clean_errors) == 0:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': '所有有效误差值均为 NaN'
        }
    errors_arr = np.array(clean_errors)
    return {
        'rmse': float(np.sqrt(np.mean(errors_arr ** 2))),
        'mae': float(np.mean(np.abs(errors_arr))),
        'max_error': float(np.max(np.abs(errors_arr))),
        'n_points': n,
        'success': True,
        'error': None
    }


def optimize_rbf_params(
    x, y, z,
    functions=None,
    smooths=None,
    epsilons=None,
    progress_callback=None
):
    """
    网格搜索 + LOOCV，寻找最优的 RBF 参数组合。

    遍历所有 (核函数, smooth, epsilon) 组合，用 evaluate_rbf_loocv 评估，
    返回最优参数和全部结果。

    progress_callback: 可选进度回调，签名为 callback(current, total, info)
    """
    from config import (
        RBF_OPTIMIZE_FUNCTIONS, RBF_OPTIMIZE_SMOOTHS, RBF_OPTIMIZE_EPSILONS
    )

    if functions is None:
        functions = RBF_OPTIMIZE_FUNCTIONS
    if smooths is None:
        smooths = RBF_OPTIMIZE_SMOOTHS
    if epsilons is None:
        epsilons = RBF_OPTIMIZE_EPSILONS

    needs_epsilon = {'gaussian', 'multiquadric', 'inverse_multiquadric', 'inverse'}

    # 构建组合列表
    combos = []
    for func in functions:
        for sm in smooths:
            if func in needs_epsilon:
                for eps in epsilons:
                    combos.append((func, sm, eps))
            else:
                combos.append((func, sm, None))

    total = len(combos)
    all_results = []
    best = None

    for idx, (func, sm, eps) in enumerate(combos, 1):
        result = evaluate_rbf_loocv(x, y, z, func, sm, eps)

        if not result['success']:
            if progress_callback:
                progress_callback(idx, total, f'{func}/smooth={sm} 失败: {result["error"]}')
            continue

        entry = {
            'rbf_function': func,
            'smooth': sm,
            'epsilon': eps,
            'rmse': result['rmse'],
            'mae': result['mae'],
            'max_error': result['max_error']
        }
        all_results.append(entry)

        if progress_callback:
            progress_callback(idx, total, f'{func}/smooth={sm} RMSE={result["rmse"]:.4f} MAE={result["mae"]:.4f} max_err={result["max_error"]:.4f}')

    if len(all_results) == 0:
        return {
            'best': None, 'all_results': [],
            'success': False,
            'error': '所有参数组合均失败'
        }

    # 综合评分（归一化加权：RMSE + MAE + max_error）
    _compute_composite_scores(all_results)
    all_results.sort(key=lambda e: e.get('composite_score', float('-inf')), reverse=True)
    best = all_results[0].copy()

    return {
        'best': best,
        'all_results': all_results,
        'success': True,
        'error': None
    }


def evaluate_kriging_loocv(x, y, z, variogram_model='spherical'):
    """
    用留一交叉验证（LOOCV）评估克里金模型的泛化误差。

    参数
    ----
    x, y, z : numpy 数组，控制点坐标与高程值
    variogram_model : str，变异函数模型

    返回
    ----
    dict，包含 rmse, mae, max_error, n_points, success, error
    """
    import numpy as np
    from pykrige.ok import OrdinaryKriging

    n = len(x)
    if n < 5:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': f'控制点数量不足（{n} < 5），无法可靠评估'
        }

    errors = []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False

        x_train = x[mask]
        y_train = y[mask]
        z_train = z[mask]

        try:
            ok = OrdinaryKriging(
                x_train, y_train, z_train,
                variogram_model=variogram_model,
                nlags=6, enable_plotting=False, verbose=False
            )
            z_pred, _ = ok.execute('points', [float(x[i])], [float(y[i])])
            z_pred_val = float(z_pred[0])
            # 检测数值不稳定（极端预测值）
            if not np.isfinite(z_pred_val) or abs(z_pred_val) > 1e8:
                continue
            err = z_pred_val - z[i]
            errors.append(err)
        except Exception:
            continue

    if len(errors) == 0:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': '所有点拟合均失败'
        }

    # 二次过滤 NaN，防止 numpy copy 损坏（numpy 1.26.4 bug）
    clean_errors = [e for e in errors if not np.isnan(e)]
    if len(clean_errors) == 0:
        return {
            'rmse': None, 'mae': None, 'max_error': None,
            'n_points': n, 'success': False,
            'error': '所有有效误差值均为 NaN'
        }
    errors_arr = np.array(clean_errors)
    return {
        'rmse': float(np.sqrt(np.mean(errors_arr ** 2))),
        'mae': float(np.mean(np.abs(errors_arr))),
        'max_error': float(np.max(np.abs(errors_arr))),
        'n_points': n,
        'success': True,
        'error': None
    }


def fit_variogram_full_model(x, y, z, variogram_model):
    """
    在全部数据上拟合克里金模型，提取变异函数关键参数。

    返回 dict: { nugget, sill, range_val, nugget_ratio, r_squared }
    或 None（拟合失败或无法提取参数）。
    """
    import numpy as np
    from pykrige.ok import OrdinaryKriging

    try:
        ok = OrdinaryKriging(
            x, y, z,
            variogram_model=variogram_model,
            nlags=6, enable_plotting=False, verbose=False
        )

        params = ok.variogram_model_parameters
        if params is None or len(params) == 0:
            return None

        # 不同模型参数含义不同
        # spherical/exponential/gaussian: [nugget, sill, range]
        # linear: [nugget, slope]
        # power: [nugget, scale, exponent]
        nugget = float(params[0])

        sill = None
        range_val = None
        nugget_ratio = None

        if variogram_model in ('spherical', 'exponential', 'gaussian'):
            partial_sill = float(params[1])
            range_val = float(params[2])
            total_sill = nugget + partial_sill
            sill = total_sill  # 基台值 = 块金值 + 偏基台值
            if total_sill > 0:
                nugget_ratio = round(nugget / total_sill, 4)
        elif variogram_model == 'linear':
            range_val = None  # 线性模型无变程
        elif variogram_model == 'power':
            range_val = None

        # 计算变异函数拟合的 R²
        r_squared = None
        if hasattr(ok, 'lags') and ok.lags is not None and len(ok.lags) > 1:
            try:
                # pykrige 提供 variogram_function(m, d) 计算理论变异函数值
                if hasattr(ok, 'variogram_function') and callable(ok.variogram_function):
                    fitted_semi = ok.variogram_function(ok.variogram_model_parameters, ok.lags)
                    exp_semi = ok.semivariance
                    ss_res = np.nansum((exp_semi - fitted_semi) ** 2)
                    ss_tot = np.nansum((exp_semi - np.nanmean(exp_semi)) ** 2)
                    if ss_tot > 0:
                        r_squared = round(1.0 - ss_res / ss_tot, 4)
            except Exception:
                pass

        return {
            'nugget': round(nugget, 4),
            'sill': round(sill, 4) if sill is not None else None,
            'range': round(range_val, 4) if range_val is not None else None,
            'nugget_ratio': nugget_ratio,
            'r_squared': r_squared,
        }
    except Exception:
        return None


def optimize_kriging_params(
    x, y, z,
    variograms=None,
    progress_callback=None
):
    """
    遍历候选变异函数模型 + LOOCV，寻找最优的克里金参数组合。

    参数
    ----
    x, y, z : numpy 数组，控制点坐标与高程值
    variograms : list 或 None，候选变异函数列表，None 表示使用默认配置
    progress_callback : 可选进度回调，签名为 callback(current, total, info)

    返回
    ----
    dict，包含 best, all_results, success, error
    """
    from config import KRIGING_OPTIMIZE_VARIOGRAMS

    if variograms is None:
        variograms = KRIGING_OPTIMIZE_VARIOGRAMS

    total = len(variograms)
    all_results = []
    best = None

    for idx, vgm in enumerate(variograms, 1):
        result = evaluate_kriging_loocv(x, y, z, vgm)

        if not result['success']:
            if progress_callback:
                progress_callback(idx, total, f'{vgm} 失败: {result["error"]}')
            continue

        entry = {
            'variogram_model': vgm,
            'rmse': result['rmse'],
            'mae': result['mae'],
            'max_error': result['max_error']
        }

        # 提取变异函数参数（块金值、基台值、变程、块基比、R²）
        variogram_params = fit_variogram_full_model(x, y, z, vgm)
        if variogram_params:
            entry.update(variogram_params)

        all_results.append(entry)

        if progress_callback:
            progress_callback(idx, total, f'{vgm} RMSE={result["rmse"]:.4f} MAE={result["mae"]:.4f} max_err={result["max_error"]:.4f}')

    if len(all_results) == 0:
        return {
            'best': None, 'all_results': [],
            'success': False,
            'error': '所有变异函数模型均失败'
        }

    # 综合评分（归一化加权：RMSE + MAE + max_error）
    _compute_composite_scores(all_results)
    all_results.sort(key=lambda e: e.get('composite_score', float('-inf')), reverse=True)
    best = all_results[0].copy()

    return {
        'best': best,
        'all_results': all_results,
        'success': True,
        'error': None
    }


# ==================== 模型质量评估 ====================

def check_layer_intersection(bodies, threshold=None):
    """
    检查地质体顶底面是否穿层（顶面低于底面）。

    参数:
        bodies: build_geological_bodies_with_volume_v2 返回的 bodies
        threshold: 穿层判定的最小差值（米），默认从 config 读取

    返回:
        dict 包含 has_intersection, total_cells, intersection_cells,
             intersection_ratio, details
    """
    import numpy as np
    from config import QUALITY_INTERSECTION_THRESHOLD, QUALITY_INTERSECTION_WARN_RATIO

    if threshold is None:
        threshold = QUALITY_INTERSECTION_THRESHOLD

    all_details = []
    total_cells = 0
    intersection_cells = 0

    for lith, data in bodies.items():
        Z_top = data['Z_top']
        Z_bot = data['Z_bot']
        X = data['X']
        Y = data['Y']

        # 有效网格
        valid = ~np.isnan(Z_top) & ~np.isnan(Z_bot)
        n_valid = int(np.sum(valid))
        total_cells += n_valid

        if n_valid == 0:
            continue

        # 穿层：顶面 < 底面
        gap = Z_top - Z_bot  # 正常应为正
        intersected = valid & (gap < -threshold)
        n_intersected = int(np.sum(intersected))
        intersection_cells += n_intersected

        # 记录穿层位置（最多5个）
        if n_intersected > 0:
            idx = np.where(intersected)
            for i, j in zip(idx[0][:5], idx[1][:5]):
                all_details.append({
                    'layer': lith,
                    'x': float(X[i, j]),
                    'y': float(Y[i, j]),
                    'gap': float(gap[i, j])
                })

    ratio = intersection_cells / total_cells if total_cells > 0 else 0

    return {
        'has_intersection': ratio > QUALITY_INTERSECTION_WARN_RATIO,
        'total_cells': total_cells,
        'intersection_cells': intersection_cells,
        'intersection_ratio': round(float(ratio), 6),
        'details': all_details
    }


def check_thickness_variation(bodies, max_gradient=None, min_thickness=None, max_thickness=None):
    """
    检查单层厚度的空间变化是否平滑。

    参数:
        bodies: 地质体 bodies 字典
        max_gradient: 允许的最大厚度变化率（m/m）
        min_thickness: 最小厚度（米）
        max_thickness: 最大厚度（米）

    返回:
        dict 包含 has_anomaly, layers（每层的厚度统计）
    """
    import numpy as np
    from config import (
        QUALITY_THICKNESS_MAX_GRADIENT,
        QUALITY_THICKNESS_MIN,
        QUALITY_THICKNESS_MAX
    )

    if max_gradient is None:
        max_gradient = QUALITY_THICKNESS_MAX_GRADIENT
    if min_thickness is None:
        min_thickness = QUALITY_THICKNESS_MIN
    if max_thickness is None:
        max_thickness = QUALITY_THICKNESS_MAX

    results = []

    for lith, data in bodies.items():
        Z_top = data['Z_top']
        Z_bot = data['Z_bot']
        X = data['X']
        Y = data['Y']

        # 厚度
        thickness = Z_top - Z_bot
        thickness[thickness < 0] = np.nan
        valid = ~np.isnan(thickness)

        if np.sum(valid) == 0:
            continue

        # 网格间距
        dx = np.abs(X[0, 1] - X[0, 0]) if X.shape[1] > 1 else 1.0
        dy = np.abs(Y[1, 0] - Y[0, 0]) if Y.shape[0] > 1 else 1.0

        # 厚度梯度
        try:
            grad_x = np.abs(np.gradient(np.nan_to_num(thickness), axis=1)) / dx
            grad_y = np.abs(np.gradient(np.nan_to_num(thickness), axis=0)) / dy
            grad = np.maximum(grad_x, grad_y)
            grad[~valid] = np.nan
            max_grad_val = float(np.nanmax(grad)) if np.any(~np.isnan(grad)) else 0
            anomaly = valid & (grad > max_gradient)
            anomaly_count = int(np.sum(anomaly))
        except Exception:
            max_grad_val = 0
            anomaly_count = 0

        # 厚度范围检查
        thick_valid = thickness[valid]
        t_min = float(np.min(thick_valid)) if len(thick_valid) > 0 else 0
        t_max = float(np.max(thick_valid)) if len(thick_valid) > 0 else 0
        t_mean = float(np.mean(thick_valid)) if len(thick_valid) > 0 else 0

        results.append({
            'layer': lith,
            'max_gradient': round(max_grad_val, 4),
            'anomaly_count': anomaly_count,
            'thickness_min': round(t_min, 2),
            'thickness_max': round(t_max, 2),
            'thickness_mean': round(t_mean, 2),
            'has_anomaly': anomaly_count > 0
        })

    return {
        'has_anomaly': any(r['has_anomaly'] for r in results),
        'layers': results
    }


def detect_pinch_out(bodies, min_thickness=None, reasonable_ratio=None):
    """
    识别尖灭区（厚度 < 阈值的区域）。

    参数:
        bodies: 地质体 bodies 字典
        min_thickness: 尖灭判定厚度阈值（米）
        reasonable_ratio: 合理尖灭比例阈值

    返回:
        dict 包含 layers（每层的尖灭统计）
    """
    import numpy as np
    from config import QUALITY_PINCHOUT_MIN_THICKNESS, QUALITY_PINCHOUT_REASONABLE_RATIO

    if min_thickness is None:
        min_thickness = QUALITY_PINCHOUT_MIN_THICKNESS
    if reasonable_ratio is None:
        reasonable_ratio = QUALITY_PINCHOUT_REASONABLE_RATIO

    results = []

    for lith, data in bodies.items():
        Z_top = data['Z_top']
        Z_bot = data['Z_bot']

        thickness = Z_top - Z_bot
        valid = ~np.isnan(thickness)

        if np.sum(valid) == 0:
            continue

        # 尖灭区：厚度 < 阈值
        pinch = valid & (thickness < min_thickness)
        pinch_count = int(np.sum(pinch))
        n_valid = int(np.sum(valid))
        pinch_ratio = pinch_count / n_valid if n_valid > 0 else 0

        # 判断是否为合理尖灭
        is_reasonable = pinch_ratio > reasonable_ratio

        results.append({
            'layer': lith,
            'pinch_ratio': round(float(pinch_ratio), 6),
            'pinch_count': pinch_count,
            'is_reasonable': is_reasonable,
            'comment': '合理尖灭（透镜状边缘）' if is_reasonable else '存在硬切割，建议检查'
        })

    return {'layers': results}


def evaluate_model_quality(bodies, litho_df=None):
    """
    综合评估模型质量，输出报告。

    参数:
        bodies: 地质体 bodies 字典
        litho_df: 岩性表 DataFrame（当前未使用，保留参数用于扩展）

    返回:
        dict 包含各检查项结果、综合评分、评级、扣分项和已知局限
    """
    from config import (
        QUALITY_SCORE_PENALTY_INTERSECTION,
        QUALITY_SCORE_PENALTY_THICKNESS,
        QUALITY_SCORE_PENALTY_PINCHOUT,
        QUALITY_GRADE_EXCELLENT,
        QUALITY_GRADE_GOOD,
        QUALITY_GRADE_FAIR
    )

    intersection = check_layer_intersection(bodies)
    thickness = check_thickness_variation(bodies)
    pinch_out = detect_pinch_out(bodies)

    # 综合评分
    score = 100
    penalties = []

    if intersection['has_intersection']:
        score -= QUALITY_SCORE_PENALTY_INTERSECTION
        penalties.append(f"层间穿层：-{QUALITY_SCORE_PENALTY_INTERSECTION}分")

    if thickness['has_anomaly']:
        score -= QUALITY_SCORE_PENALTY_THICKNESS
        penalties.append(f"厚度异常：-{QUALITY_SCORE_PENALTY_THICKNESS}分")

    # 尖灭异常：合理尖灭不扣分，硬切割扣分
    pinch_anomaly = any(not r['is_reasonable'] for r in pinch_out['layers'])
    if pinch_anomaly:
        score -= QUALITY_SCORE_PENALTY_PINCHOUT
        penalties.append(f"尖灭异常：-{QUALITY_SCORE_PENALTY_PINCHOUT}分")

    score = max(0, score)

    if score >= QUALITY_GRADE_EXCELLENT:
        grade = '优秀'
        grade_color = '#2E7D32'
    elif score >= QUALITY_GRADE_GOOD:
        grade = '良好'
        grade_color = '#1565C0'
    elif score >= QUALITY_GRADE_FAIR:
        grade = '一般'
        grade_color = '#F57C00'
    else:
        grade = '差'
        grade_color = '#C62828'

    # 已知局限
    limitations = []
    if intersection['has_intersection']:
        limitations.append('层间存在穿层现象，需检查数据或调整插值参数')
    if thickness['has_anomaly']:
        limitations.append('部分区域厚度变化剧烈，可能存在插值失真')
    limitations.append('未考虑断层影响（如研究区存在断层，建议在断层附近补充钻孔）')
    limitations.append('未考虑垂向各向异性（2D 插值方法的固有局限）')

    # ========== 参数调整建议 ==========
    recommendations = []

    # 穿层建议
    if intersection['has_intersection']:
        recommendations.append({
            'type': 'intersection',
            'severity': 'warning',
            'text': '层间穿层说明插值在局部区域产生了震荡。建议：① 降低网格分辨率(GRID_RESOLUTION) ② 在穿层区域补充钻孔控制点 ③ 切换为克里金插值（平滑性更好）'
        })

    # 厚度梯度异常建议
    if thickness['has_anomaly']:
        highly_anomalous = any(r['anomaly_count'] > 20 for r in thickness['layers'])
        smooth_advice = '增大 RBF_SMOOTH 参数值(建议 0.5~2.0)' if highly_anomalous else '适当增大 RBF_SMOOTH'
        recommendations.append({
            'type': 'thickness',
            'severity': 'warning',
            'text': f'厚度梯度异常区域可能存在插值失真。建议：① {smooth_advice} ② 在异常区域加密钻孔控制点 ③ 更换核函数(如 thin_plate→multiquadric)'
        })

    # 尖灭建议
    pinch_hard = [r for r in pinch_out['layers'] if not r['is_reasonable']]
    if pinch_hard:
        layers_str = '、'.join([r['layer'] for r in pinch_hard])
        recommendations.append({
            'type': 'pinchout',
            'severity': 'warning',
            'text': f'岩性 {layers_str} 存在硬切割尖灭。建议检查边界控制点是否过少，或增大网格分辨率使尖灭过渡更平滑'
        })

    # 若整体评分良好，给出肯定建议
    if score >= QUALITY_GRADE_EXCELLENT:
        recommendations.append({
            'type': 'overall',
            'severity': 'info',
            'text': '模型质量优秀，当前插值参数配置合理，无需调整'
        })
    elif score >= QUALITY_GRADE_GOOD:
        recommendations.append({
            'type': 'overall',
            'severity': 'info',
            'text': '模型质量良好，可尝试微调参数进一步提升：如适当降低网格分辨率或增大 RBF 平滑度'
        })

    # 通用建议
    recommendations.append({
        'type': 'general',
        'severity': 'info',
        'text': '提示：模型质量评估仅基于已有钻孔数据的插值结果，建议结合地质先验知识综合判断。如需更高精度，应考虑在关键区域补充钻孔'
    })

    return {
        'layer_intersection': intersection,
        'thickness_variation': thickness,
        'pinch_out': pinch_out,
        'overall_score': score,
        'overall_grade': grade,
        'grade_color': grade_color,
        'penalties': penalties,
        'limitations': limitations,
        'recommendations': recommendations
    }