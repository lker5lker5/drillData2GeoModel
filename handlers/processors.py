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
        # 标注版：完整坐标轴
        ax.set_xlabel('开孔坐标E (m)')
        ax.set_ylabel('开孔坐标N (m)')
        ax.set_zlabel('海拔高度 (m)')
        ax.grid(True, alpha=0.3)
    else:
        # ========== 无标注版：仅保留 Z 轴 + 深度标尺 ==========
        # 隐藏 X/Y 轴刻度和标签
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
        #    （matplotlib 会基于 zlim 自动生成刻度）
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

        # 关闭科学计数法
        ax.ticklabel_format(style='plain', axis='x', useOffset=False)
        ax.ticklabel_format(style='plain', axis='y', useOffset=False)
        ax.ticklabel_format(style='plain', axis='z', useOffset=False)

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
    base_n = loc_df['开孔坐标N'].min()
    base_e = loc_df['开孔坐标E'].min()
    
    # 预处理：将坐标平移到相对坐标系（避免绝对值太大导致绘图拥挤）
    loc_df_rel = loc_df.copy()
    loc_df_rel['开孔坐标N'] = loc_df['开孔坐标N'] - base_n
    loc_df_rel['开孔坐标E'] = loc_df['开孔坐标E'] - base_e
    
    for config in views_configs:
        fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
        ax = fig.add_subplot(111, projection='3d')
        
        # 复用统一的钻孔绘制函数
        legend_labels, legend_entries = plot_drill_holes_on_ax(
            ax, loc_df_rel, survey_df, litho_df,
            legend_labels=set(),
            show_labels=True,
            show_legend=True
        )

        ax.set_xlabel('北 (m)')
        ax.set_ylabel('东 (m)')
        ax.set_zlabel('海拔 (m)')
        ax.view_init(elev=config['elev'], azim=config['azim'])

        all_n_rel = loc_df_rel['开孔坐标N'].values
        all_e_rel = loc_df_rel['开孔坐标E'].values
        margin = 20
        ax.set_xlim(all_n_rel.min() - margin, all_n_rel.max() + margin)
        ax.set_ylim(all_e_rel.min() - margin, all_e_rel.max() + margin)

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

    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    all_z = loc_df['开孔高程R'].values
    z_min_all = min(all_z)

    for hid in hole_ids:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            _, _, _, zs = compute_trajectory(surv)
            row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
            zs += row['开孔高程R']
            if len(zs) > 0:
                z_min_all = min(z_min_all, np.min(zs))

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

    # ==== 仅绘制钻孔（无地质体）====
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
            if len(x) == 0:
                continue

            color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'

            if use_style == 'cylinder':
                cyl_x, cyl_y, cyl_z, cyl_i, cyl_j, cyl_k = build_plotly_cylinder_mesh(
                    x, y, z, radius=drill_radius, sides=DRILL_CYLINDER_SIDES
                )
                fig.add_trace(go.Mesh3d(
                    x=cyl_x, y=cyl_y, z=cyl_z,
                    i=cyl_i, j=cyl_j, k=cyl_k,
                    color=color_str,
                    opacity=0.9,
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<extra></extra>'
                ))
            else:
                fig.add_trace(go.Scatter3d(
                    x=x, y=y, z=z,
                    mode='lines',
                    line=dict(color=color_str, width=5),
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.1f}}m<extra></extra>'
                ))

        fig.add_trace(go.Scatter3d(
            x=[x0], y=[y0], z=[z0 + 3],
            mode='text',
            text=[hid],
            textfont=dict(size=12, color='black', family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))

    margin = 20
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='开孔坐标N (m)', range=[all_n.min() - margin, all_n.max() + margin]),
            yaxis=dict(title='开孔坐标E (m)', range=[all_e.min() - margin, all_e.max() + margin]),
            zaxis=dict(title='海拔高度 (m)', range=[z_min_all - 10, all_z.max() + 5]),
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.0),
                center=dict(x=0, y=0, z=0)
            )
        ),
        autosize=True,
        title='交互式钻孔模型',
        margin=dict(l=5, r=5, t=40, b=5),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )

    html_path = os.path.join(output_dir, f'{base_name}.html')
    fig.write_html(html_path, config={
        'responsive': True,
        'scrollZoom': True,
        'displayModeBar': True
    })
    return html_path


# ==================== 交互式模型生成（已有，不修改） ====================
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
    all_z = loc_df['开孔高程R'].values
    z_min_all = min(all_z)
    
    for hid in hole_ids:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            _, _, _, zs = compute_trajectory(surv)
            row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
            zs += row['开孔高程R']
            if len(zs) > 0:
                z_min_all = min(z_min_all, np.min(zs))
    
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
    
    # 绘制地质体
    for lith, data in volume_data.items():
        color = data['color']
        color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'
        layers = data['layers']
        
        if not layers:
            continue
        
        for k, Z in enumerate(layers):
            show_legend = (k == 0)
            opacity = 0.2 + 0.5 * (k / (len(layers)-1)) if len(layers)>1 else 0.5
            fig.add_trace(go.Surface(
                x=data['X'], y=data['Y'], z=Z,
                colorscale=[[0, color_str], [1, color_str]],
                opacity=opacity,
                showscale=False,
                showlegend=show_legend,
                name=lith if show_legend else "",
                hoverinfo='skip'
            ))
        
        dummy_x = all_n.min() - 500
        dummy_y = all_e.min() - 500
        dummy_z = z_min_all - 500
        fig.add_trace(go.Scatter3d(
            x=[dummy_x], y=[dummy_y], z=[dummy_z],
            mode='markers',
            marker=dict(color=color_str, size=10),
            name=lith,
            showlegend=True,
            hoverinfo='skip'
        ))
    
    # 绘制钻孔
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
            
            d_sample = np.linspace(d_top, d_bot, max(3, int((d_bot-d_top)/0.5)))
            x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)
            if len(x) == 0:
                continue
            
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
                    opacity=0.9,
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<extra></extra>'
                ))
            else:
                # 原有线段模式
                fig.add_trace(go.Scatter3d(
                    x=x, y=y, z=z,
                    mode='lines',
                    line=dict(color=color_str, width=5),
                    showlegend=False,
                    hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.1f}}m<extra></extra>'
                )) 
        
        fig.add_trace(go.Scatter3d(
            x=[x0], y=[y0], z=[z0+3],
            mode='text',
            text=[hid],
            textfont=dict(size=12, color='black', family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    margin = 20
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='开孔坐标N (m)', range=[all_n.min()-margin, all_n.max()+margin]),
            yaxis=dict(title='开孔坐标E (m)', range=[all_e.min()-margin, all_e.max()+margin]),
            zaxis=dict(title='海拔高度 (m)', range=[z_min_all-10, all_z.max()+5]),
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
    fig.write_html(html_path, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': True})
    
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

    # ========== 3. 动态构建视角描述 ==========
    if view_metas and len(view_metas) >= 3:
        view_descriptions = []
        for i, vm in enumerate(view_metas):
            prefix = ''
            if i == 0:
                prefix = '作为几何形态的**主参考**，用于确定地质体的整体空间轮廓'
            elif i == 1:
                prefix = '作为垂向结构的**精确约束**。此图的每一条岩性分界线的高程位置，必须在生成结果中严格对应'
            elif i == 2:
                prefix = '与上一张正交，共同约束三维形态'
            view_descriptions.append(f'- {vm["label"]} —— {vm.get("user_tip", "")}（{prefix}）')

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
7. **深度标尺必须完整生成，且与地质体层位深度严格对应**
8. 光照自然，具有地质剖面的专业感，避免过度反光或卡通化
9. 背景为纯白色，无任何多余文字或标注（深度标尺除外）
10. 图像风格为科学分析 + 符合地质真实的图片
11. 输出为单张高质量的三维地质结构渲染图，分辨率不低于1024x1024
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
            "prompt_extend": True
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
    """把 color_map dict 转为文本描述字符串"""
    lines = []
    for color, names in color_map.items():
        lines.append(f'- {color}: {names}')
    return '\n'.join(lines)


def call_qwen_api_for_multiview(anchor_image, target_image, color_map,
                                  api_key=None, api_url=None, model=None):
    """
    以最优 AI 图为主锚，生成目标视角的 AI 图。

    参数:
        anchor_image: 主锚图路径（最优 AI 图）
        target_image: 目标视角的 Python 无标注图路径
        color_map: 颜色映射 dict
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

    # 构建提示词
    color_text = color_map_to_text(color_map)
    prompt = f"""
请生成一张三维地质体渲染图。

【参考图说明】
- 图1：已生成的高质量 AI 纹理图（主锚图）—— 参考它的岩石纹理、光影风格、色调。
- 图2：目标视角的几何约束图 —— 参考它的几何结构、层位分布、视角。

【任务】
生成一张新图，满足：
1. 几何结构：严格遵循图2的层位分布、层间厚度、视角
2. 岩石纹理：参考图1的纹理风格，保持视觉一致
3. 颜色规范：严格遵循下方的颜色-岩性对应
4. 背景纯白，无文字标注
5. 不同岩性应呈现符合地质学常识的岩石质感（透明矿物晶莹剔透、金属矿物金属光泽、结晶岩有结晶结构等）

【颜色-岩性对应关系】
{color_text}
"""

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
            "prompt_extend": True
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


def add_annotations_to_ai_image(ai_image_path, output_path, z_min, z_max):
    """
    在 AI 图上叠加深度标尺（带标注版）。

    参数:
        ai_image_path: AI 生成图路径
        output_path: 输出路径
        z_min, z_max: 高程范围（米）
    """
    from PIL import Image, ImageDraw, ImageFont

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
        draw.text((ruler_x + ruler_width + 12, y - 8), f'{int(z_val)}m', fill='black')

    # 标题
    draw.text((ruler_x, ruler_top - 30), '深度标尺', fill='black')

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
            "prompt_extend": True
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
            # 向外扩展 3% 的边界
            center = all_pts[:, :2].mean(axis=0)
            hull_pts = all_pts[hull.vertices][:, :2]
            expanded = center + (hull_pts - center) * 1.03   # 外扩 3%
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
            ax.ticklabel_format(style='plain', axis='both', useOffset=False)
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

        if best is None or result['rmse'] < best['rmse']:
            best = entry.copy()

        if progress_callback:
            progress_callback(idx, total, f'{func}/smooth={sm} RMSE={result["rmse"]:.4f}')

    if best is None:
        return {
            'best': None, 'all_results': [],
            'success': False,
            'error': '所有参数组合均失败'
        }

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

        if best is None or result['rmse'] < best['rmse']:
            best = entry.copy()

        if progress_callback:
            progress_callback(idx, total, f'{vgm} RMSE={result["rmse"]:.4f}')

    if best is None:
        return {
            'best': None, 'all_results': [],
            'success': False,
            'error': '所有变异函数模型均失败'
        }

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