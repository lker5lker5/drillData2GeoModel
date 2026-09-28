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
                            legend_labels=None, show_labels=True, show_legend=True):
    """
    在给定的 3D 坐标轴上绘制所有钻孔轨迹和岩性段。
    
    参数:
        ax: matplotlib 3D 坐标轴
        loc_df: 定位表 DataFrame
        survey_df: 测斜表 DataFrame
        litho_df: 岩性表 DataFrame
        legend_labels: 已存在的图例集合（set），用于去重。若为 None 则新建。
        show_labels: 是否显示钻孔编号
        show_legend: 是否显示图例（每个岩性只显示一次）
    返回:
        legend_labels: 更新后的图例集合
    """
    if legend_labels is None:
        legend_labels = set()
    
    total_segments = len(litho_df)
    
    if DRILL_STYLE == 'line' or total_segments > DRILL_FORCE_LINE_THRESHOLD:
        use_style = 'line'
        if total_segments > DRILL_FORCE_LINE_THRESHOLD:
            print(f"==> 钻孔段数 {total_segments} 超过强制阈值 {DRILL_FORCE_LINE_THRESHOLD}，使用极简线段模式")
    elif total_segments > DRILL_DEGRADE_THRESHOLD:
        use_style = 'line'
        print(f"==> 钻孔段数 {total_segments} 超过降级阈值 {DRILL_DEGRADE_THRESHOLD}，自动降级为线段模式")
    else:
        use_style = DRILL_STYLE
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
            
            show_this_label = show_legend and (lith_name not in legend_labels)
        
            # 根据 DRILL_STYLE 选择绘制方式
            if DRILL_STYLE == 'cylinder':
                plot_cylinder_segment(ax, x, y, z, color,
                                    radius=DRILL_RADIUS,
                                    sides=DRILL_CYLINDER_SIDES)
                # 图例通过一个代理线段实现
                if show_this_label:
                    ax.plot([], [], [], color=color[:3], linewidth=6,
                            label=lith_name)
                    legend_labels.add(lith_name)
            else:
                # 原有线段模式
                ax.plot(x, y, z, color=color[:3], alpha=color[3], linewidth=6,
                        label=lith_name if show_this_label else "")
                if show_this_label:
                    legend_labels.add(lith_name)

        # 钻孔编号
        if show_labels:
            ax.text(x0, y0, z0 + 3, hid, color='black', fontsize=12,
                    ha='center', va='bottom', weight='bold')
    
    return legend_labels

# 增加水印
def add_view_order_watermark(fig, order, label=''):
    """在 figure 左上角绘制序号水印（图1、图2...）"""
    watermark = f'图 {order}'
    if label:
        watermark += f'  {label}'
    fig.text(
        0.02, 0.98, watermark,
        fontsize=22, fontweight='bold', color='#1a237e',
        ha='left', va='top',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='#1a237e', linewidth=2, alpha=0.95),
        zorder=10000
    )

def draw_single_model_view(volume_data, loc_df, survey_df, litho_df, 
                            view_config, output_dir, base_name, labeled=True):
    """
    绘制单个视角的三维地质体模型图。
    
    参数:
        volume_data: build_geological_bodies_with_volume_v2 返回的体数据
        view_config: {'name': ..., 'label': ..., 'elev': ..., 'azim': ...}
        labeled: True → 带钻孔、图例、完整坐标轴；False → 仅地质体+Z轴
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
    
    # 2. 标注版：额外绘制钻孔、图例、编号
    if labeled:
        legend_labels = plot_drill_holes_on_ax(
            ax, loc_df, survey_df, litho_df,
            legend_labels=set(),
            show_labels=True,
            show_legend=True
        )
        if legend_labels:
            ax.legend(loc='upper right', fontsize=8)
    
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

    # ========== 添加序号水印 ==========
    order = view_config.get('order', 0)
    if order > 0:
        add_view_order_watermark(fig, order, view_config.get('label', ''))

    # ========== 保存（文件名带序号前缀） ==========
    if labeled:
        plt.tight_layout(pad=0.5)
    
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
        legend_labels = plot_drill_holes_on_ax(
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
        
        if legend_labels:
            ax.legend(loc='upper right', fontsize=8)
        
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

# ==================== 交互式模型生成 ====================
def generate_interactive_model(loc_df, survey_df, litho_df, output_dir, base_name):
    """生成可交互式3D模型"""
    bodies, volume_data = build_geological_bodies_with_volume_v2(loc_df, litho_df, survey_df, n_layers=N_LAYERS)
    
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
    
    if DRILL_STYLE == 'line' or total_segments > DRILL_FORCE_LINE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly: 使用线段模式（段数 {total_segments}）")
    elif total_segments > DRILL_DEGRADE_THRESHOLD:
        use_style = 'line'
        print(f"==> Plotly: 段数 {total_segments} 超降级阈值，使用线段模式")
    else:
        use_style = DRILL_STYLE
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
            
            if DRILL_STYLE == 'cylinder':
                # 生成 Plotly 圆柱网格
                cyl_x, cyl_y, cyl_z, cyl_i, cyl_j, cyl_k = build_plotly_cylinder_mesh(
                    x, y, z, radius=DRILL_RADIUS, sides=DRILL_CYLINDER_SIDES
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
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.0))
        ),
        width=1200,
        height=800,
        title='交互式三维地质体模型',
        legend=dict(
            x=1.02,
            y=1,
            xanchor='left',
            yanchor='top',
            font=dict(size=11)
        )
    )
    
    html_path = os.path.join(output_dir, f'{base_name}.html')
    fig.write_html(html_path)
    
    return html_path

# ==================== AI建模 ====================
def call_qwen_api_for_modeling(image_paths, color_map=None, api_key=QWEN_API_KEY, api_url=QWEN_API_URL, model=QWEN_MODEL):
    """
    调用 Token Plan API 生成 AI 建模图。
    使用 HTTP 直接请求，无需 dashscope SDK。
    """
    if not api_key:
        return None, "!!! API密钥未配置，请设置 QWEN_KEY 环境变量"

    # ========== 1. 检查图片 ==========
    # 按 order 严格排序，确保与提示词编号一致
    sorted_views = sorted(VIEW_CONFIGS, key=lambda v: v.get('order', 0))

    image_paths = []
    for order in AI_REFERENCE_IMGS:
        # 找到对应 order 的视图配置
        view = next((v for v in sorted_views if v.get('order') == order), None)
        if not view:
            print(f"!!! 未找到 order={order} 的视图配置")
            continue
        
        order_prefix = f'{order:02d}_'
        pattern_suffix = f'unlabeled_{order_prefix}{view["name"]}.png'
        
        found = False
        for filename in os.listdir(OUTPUT_FOLDER):
            if filename.endswith(pattern_suffix):
                image_paths.append(os.path.join(OUTPUT_FOLDER, filename))
                print(f"==> 图{order} ({view['label']}): {filename}")
                found = True
                break
        
        if not found:
            print(f"!!! 未找到 图{order} 对应的图片: {pattern_suffix}")

    if len(image_paths) < 3:
        return None, f"!!! 需要3张参考图，当前只找到 {len(image_paths)} 张"

    print(f"==> 已选 {len(image_paths)} 张参考图（按图{AI_REFERENCE_IMGS}顺序）")

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

    geomodel_prompt=f"""
请根据以下3张同一地质体的不同视角参考图，生成一张统一、逼真的三维地质结构模型渲染图。

【坐标约定】
本模型采用地质行业标准坐标：
- X 轴：东向（Easting）
- Y 轴：北向（Northing）
- Z 轴：高程（Elevation，向上为正）
【重要】每张图的左上角标注有原始序号，请严格按以下说明理解（注意：本次仅提供3张图，编号不连续）：
- 图1（立体全景视图·西北俯瞰）—— 站在矿体西北方向的高处俯视。展示地质体的整体三维形态、走向和倾伏方向，作为几何形态的**主参考**，用于确定地质体的整体空间轮廓。
- 图3（南北向剖面·从西侧向东看）—— 站在矿体正西侧，水平向东看。屏幕水平方向为南北（Y 轴），左侧南、右侧北。展示地质体在南北方向的**厚度变化和层位深度**，作为垂向结构的**精确约束**。这张图上的每一条岩性分界线的高程位置，必须在生成结果中严格对应。
- 图5（东西向剖面·从北侧向南看）—— 站在矿体正北侧，水平向南看。屏幕水平方向为东西（X 轴，反向），左侧东、右侧西。展示地质体在东西方向的**厚度变化和层位深度**，与图3正交，共同约束三维形态。

【关键说明】
- 上述3张图是同一个地质体的不同视角，请综合理解其三维空间结构，不要将它们视为多个独立物体。
- 参考图左上角的"图N"是编号标识，请在生成结果中忽略这些序号文字，只关注地质体的形态和颜色。
- 图3和图5是两个正交剖面，它们的**岩性分界线的深度位置必须严格对应**，这两个剖面的交点处（即钻孔位置附近）的层位深度应完全一致。

【参考图的性质说明】
上述参考图是**基于有限钻孔数据通过数学插值生成的初步模型**，具有以下特点：
- 其边界受钻孔控制点的空间分布范围限制，呈现为"被凸包裁剪"的形态，边缘生硬。
- 部分区域由于缺乏钻孔控制，会出现"凹陷""空洞"或"突然中断"。
- 这些不完整的边界**不代表真实地质体的实际边界**，仅代表"钻孔控制范围内的已知部分"。

【您的任务——科学化的地质填充】
请以参考图为骨架约束，运用地质学常识进行科学化的推断与填充，生成一个相对完整、符合地质规律的三维地质体：
1. **保持钻孔控制区的形态和深度不变**：
   - 参考图中由钻孔数据明确约束的**岩性分界线深度**必须严格保留。
   - 每一层的**顶板高程和底板高程**必须与图3和图5剖面中显示的数值一致。
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
3. 保持图1的整体三维形态、图3的南北向剖面深度、图5的东西向剖面深度
4. 图3和图5的岩性分界线在交点处深度必须一致
5. 地质体应呈现为完整连续的地质块体，边缘自然过渡
6. **层位必须严格按深度从上到下排列，禁止上下颠倒或穿插**
7. **深度标尺必须完整生成，且与地质体层位深度严格对应**
8. 光照自然，具有地质剖面的专业感，避免过度反光或卡通化
9. 背景为纯白色，无任何多余文字或标注（深度标尺除外）
10. 图像风格为科学分析 + 符合地质真实的图片
11. 输出为单张高质量的三维地质结构渲染图，分辨率不低于1024x1024
"""
    # ========== 3. 构建 content 数组 ==========
    content_list = []
    for path in image_paths:
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
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
        response = requests.post(api_url, headers=headers, json=payload, timeout=180)
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
def build_geological_bodies_with_volume_v2(loc_df, litho_df, survey_df, n_layers=N_LAYERS):
    """构建地质体模型（含多层体数据）—— 归一化坐标训练+预测，原始坐标输出"""
    
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
    grid_res = GRID_RESOLUTION
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
                
        # RBF 在归一化坐标上训练
        try:
            rbf_top = Rbf(top_pts[:, 0], top_pts[:, 1], top_pts[:, 2],
                          function=RBF_FUNCTION, smooth=RBF_SMOOTH)
            rbf_bot = Rbf(bot_pts[:, 0], bot_pts[:, 1], bot_pts[:, 2],
                          function=RBF_FUNCTION, smooth=RBF_SMOOTH)
        except Exception as e:
            print(f"!!! 岩性 {lith} 插值失败: {e}")
            continue
        
        # 在归一化网格上预测
        Z_top = rbf_top(xi_n, yi_n)
        Z_bot = rbf_bot(xi_n, yi_n)
        
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
    
    return bodies, volume_data

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