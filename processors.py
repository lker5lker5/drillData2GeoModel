# processors.py
# 核心处理函数

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import Rbf
from scipy.interpolate import interp1d
from scipy.spatial import ConvexHull
from matplotlib.path import Path
import plotly.graph_objects as go
import os
from datetime import datetime
import json
import requests
import base64
import dashscope
import pyproj

from pyproj import Transformer
from dashscope import MultiModalConversation
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
def get_color_map_from_excel(file_path):
    """
    从Excel的岩性表中提取颜色映射
    返回: dict {颜色值: 岩性名称}
    """
    color_map = {}
    try:
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')
        # 获取唯一颜色对应的岩性描述
        for _, row in litho_df.iterrows():
            color = str(row['建模颜色']).strip()
            lith_name = str(row['岩性描述']).strip()
            if color and lith_name and color != 'nan':
                # 如果同一个颜色有多个岩性，合并显示
                if color in color_map:
                    if lith_name not in color_map[color]:
                        color_map[color] = color_map[color] + '、' + lith_name
                else:
                    color_map[color] = lith_name
        return color_map
    except Exception as e:
        print(f"!!! 读取颜色映射失败: {e}")
        return {}


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


# ==================== 轨迹计算 ====================
def compute_trajectory(df_survey):
    """根据测斜数据计算钻孔轨迹点"""
    df = df_survey.sort_values('各层位长度', ascending=True)
    lengths = df['各层位长度'].values
    az = np.radians(df['方位角'].values)
    inc = np.radians(np.abs(df['倾角'].values))
    
    xs = [0.0]
    ys = [0.0]
    zs = [0.0]
    
    for i in range(1, len(lengths)):
        delta = lengths[i] - lengths[i-1]
        dz = -delta * np.sin(inc[i])
        horiz = delta * np.cos(inc[i])
        dx = horiz * np.cos(az[i])
        dy = horiz * np.sin(az[i])
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
        ax.set_zlabel('Elevation (m)', fontsize=12, fontweight='bold', labelpad=10)
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
    if not labeled and all_z:
        z_max_val = max(all_z)
        z_min_val = min(all_z)
        # 显示高度范围
        fig.text(
            0.90, 0.10,
            f'高程范围\n{z_min_val:.0f} ~ {z_max_val:.0f} m',
            fontsize=10, color='#333',
            ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.4',
                      facecolor='#f5f5f5', edgecolor='#999',
                      linewidth=1, alpha=0.9)
        )
         
        # 在 figure 右侧添加一个辅助坐标轴绘制标尺
        # [左, 下, 宽, 高] 归一化坐标
        cax = fig.add_axes([0.90, 0.25, 0.025, 0.5])
        
        # 生成一个渐变色条（从亮到暗，模拟深度）
        gradient = np.linspace(1, 0, 256).reshape(-1, 1)
        cax.imshow(gradient, aspect='auto', cmap='gray_r',
                   extent=[0, 1, z_min_val, z_max_val])
        
        # 设置标尺的刻度和标签
        cax.set_xticks([])
        cax.set_yticks(np.linspace(z_min_val, z_max_val, 6))
        cax.set_yticklabels(
            [f'{v:.0f}' for v in np.linspace(z_min_val, z_max_val, 6)],
            fontsize=10
        )
        cax.yaxis.tick_right()
        cax.yaxis.set_label_position('right')
        cax.set_ylabel('Elevation (m)', fontsize=11, fontweight='bold',
                       rotation=270, labelpad=20)
        cax.tick_params(axis='y', length=4, width=1.2)
        
        # 边框
        for spine in cax.spines.values():
            spine.set_linewidth(1.2)
            spine.set_color('#333')

    plt.savefig(save_path, dpi=FIGURE_DPI, pad_inches=0, facecolor='white')
    plt.close()
    return save_path    

# ==================== 构建地质体 ====================
def build_geological_bodies_with_volume(loc_df, litho_df, survey_df):
    """构建地质体模型（含体数据）"""
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
        
        x_top, y_top, z_top = get_interpolated_coords(
            traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
        x_bot, y_bot, z_bot = get_interpolated_coords(
            traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
        
        x_top, y_top = x_top[0] + n0, y_top[0] + e0
        x_bot, y_bot = x_bot[0] + n0, y_bot[0] + e0
        z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
        
        if lith not in litho_groups:
            litho_groups[lith] = {'color': color, 'top': [], 'bottom': []}
        litho_groups[lith]['top'].append((x_top, y_top, z_top))
        litho_groups[lith]['bottom'].append((x_bot, y_bot, z_bot))
    
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    x_min, x_max = all_n.min() - 50, all_n.max() + 50
    y_min, y_max = all_e.min() - 50, all_e.max() + 50
    
    grid_res = GRID_RESOLUTION
    xi = np.linspace(x_min, x_max, grid_res)
    yi = np.linspace(y_min, y_max, grid_res)
    xi, yi = np.meshgrid(xi, yi)
    
    # 全局掩膜
    all_top_pts = []
    for data in litho_groups.values():
        all_top_pts.extend(data['top'])
    
    if not all_top_pts:
        return {}, {}
    
    all_top_pts = np.array(all_top_pts)
    try:
        hull = ConvexHull(all_top_pts[:, :2])
        hull_path = Path(all_top_pts[hull.vertices][:, :2])
        grid_points = np.column_stack((xi.ravel(), yi.ravel()))
        global_mask = hull_path.contains_points(grid_points).reshape(xi.shape)
    except:
        global_mask = np.ones(xi.shape, dtype=bool)
    
    bodies = {}
    volume_data = {}
    
    for lith, data in litho_groups.items():
        if len(data['top']) < 2:
            continue
        
        top_pts = np.array(data['top'])
        bot_pts = np.array(data['bottom'])
        
        try:
            rbf_top = Rbf(top_pts[:,0], top_pts[:,1], top_pts[:,2], 
                         function='linear', smooth=RBF_SMOOTH)
            rbf_bot = Rbf(bot_pts[:,0], bot_pts[:,1], bot_pts[:,2], 
                         function='linear', smooth=RBF_SMOOTH)
        except:
            continue
        
        Z_top = rbf_top(xi, yi)
        Z_bot = rbf_bot(xi, yi)
        Z_top[~global_mask] = np.nan
        Z_bot[~global_mask] = np.nan
        
        mask = Z_top > Z_bot
        Z_top_c = np.where(mask, Z_top, Z_bot)
        Z_bot_c = np.where(mask, Z_bot, Z_top)
        
        bodies[lith] = {
            'X': xi, 'Y': yi,
            'Z_top': Z_top_c,
            'Z_bot': Z_bot_c,
            'color': data['color']
        }
        
        layers = []
        n_layers = N_LAYERS
        for k in range(n_layers + 2):
            t = k / (n_layers + 1)
            Z_layer = Z_top_c * (1 - t) + Z_bot_c * t
            layers.append(Z_layer)
        
        volume_data[lith] = {
            'X': xi, 'Y': yi,
            'layers': layers,
            'color': data['color']
        }
    
    return bodies, volume_data

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
            xaxis=dict(title='Northing (m)', range=[all_n.min()-margin, all_n.max()+margin]),
            yaxis=dict(title='Easting (m)', range=[all_e.min()-margin, all_e.max()+margin]),
            zaxis=dict(title='Elevation (m)', range=[z_min_all-10, all_z.max()+5]),
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
def call_qwen_api_for_modeling(image_paths, color_map=COLOR_MAP, api_key=QWEN_API_KEY, api_url=QWEN_API_URL, model=QWEN_MODEL):
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

    # ========== 3. 构建 content 数组 ==========
    content_list = []
    for path in image_paths:
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
            content_list.append({"image": f"data:image/png;base64,{b64}"})
    content_list.append({"text": AI_GEOMODEL_PROMPT})

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

# ==================== 从 drill2Model 整合的核心函数 ====================
def build_geological_bodies_with_volume_v2(loc_df, litho_df, survey_df, n_layers=N_LAYERS):
    """构建地质体模型（含多层体数据）"""
    
    # ========== 1. 孔口坐标 ==========
    hole_coords = {}
    for _, row in loc_df.iterrows():
        hid = row['钻孔编号']
        hole_coords[hid] = (row['开孔坐标E'], row['开孔坐标N'], row['开孔高程R'])
    
    # ========== 2. 轨迹缓存 ==========
    traj_cache = {}
    for hid in loc_df['钻孔编号']:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            lengths, xs, ys, zs = compute_trajectory(surv)
            traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
    # ========== 3. 坐标归一化参数 ==========
    base_e = loc_df['开孔坐标E'].min()
    base_n = loc_df['开孔坐标N'].min()
    span_e = loc_df['开孔坐标E'].max() - base_e
    span_n = loc_df['开孔坐标N'].max() - base_n
    span_max = max(span_e, span_n, 1.0)
    scale = 1000.0
    scale_factor = scale / span_max
    
    def normalize(x, y):
        return (x - base_e) * scale_factor, (y - base_n) * scale_factor
    
    def denormalize(x, y):
        return x / scale_factor + base_e, y / scale_factor + base_n
    
    # ========== 4. 收集岩性顶底点（归一化坐标） ==========
    litho_groups = {}
    for _, seg in litho_df.iterrows():
        hid = seg['钻孔编号']
        d_top = seg['上层位长度起始刻度']
        d_bot = seg['下层位长度起始刻度']
        lith = seg['岩性描述']
        color = parse_color(seg['建模颜色'], lith)
        if hid not in hole_coords or hid not in traj_cache:
            continue
        e0, n0, z0 = hole_coords[hid]   # 注意：E 在前，N 在后
        traj = traj_cache[hid]
        x_top, y_top, z_top = get_interpolated_coords(
            traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_top])
        x_bot, y_bot, z_bot = get_interpolated_coords(
            traj['lengths'], traj['xs'], traj['ys'], traj['zs'], [d_bot])
        
        # 加上孔口坐标（X=东, Y=北）
        x_top, y_top = x_top[0] + e0, y_top[0] + n0
        x_bot, y_bot = x_bot[0] + e0, y_bot[0] + n0
        z_top, z_bot = z_top[0] + z0, z_bot[0] + z0
        
        if lith not in litho_groups:
            litho_groups[lith] = {'color': color, 'top': [], 'bottom': []}
        
        # 归一化 XY
        x_top_n, y_top_n = normalize(x_top, y_top)
        x_bot_n, y_bot_n = normalize(x_bot, y_bot)
        
        litho_groups[lith]['top'].append((x_top_n, y_top_n, z_top))
        litho_groups[lith]['bottom'].append((x_bot_n, y_bot_n, z_bot))
    
    # ========== 5. 归一化插值网格（保持纵横比） ==========
    grid_res = GRID_RESOLUTION
    x_min_n, x_max_n = 0.0, scale
    y_min_n, y_max_n = 0.0, scale * (span_n / span_max)
    xi_n = np.linspace(x_min_n, x_max_n, grid_res)
    yi_n = np.linspace(y_min_n, y_max_n, grid_res)
    xi_n, yi_n = np.meshgrid(xi_n, yi_n)
    
    # 把归一化网格映射回原始坐标（用于最终存储）
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
            computed_layers = int(6 + avg_thickness / 30)
            n_layers = max(5, min(25, computed_layers))
            print(f"==> 根据平均厚度 ({avg_thickness:.1f}m) 自动设置层数: {n_layers}")
        else:
            n_layers = 12
            print(f"==> 无法计算平均厚度，使用默认层数: {n_layers}")
    
    # ========== 7. 逐岩性插值 ==========
    bodies = {}
    volume_data = {}
    
    for lith, data in litho_groups.items():
        n_top = len(data['top'])
        n_bot = len(data['bottom'])
        print(f"岩性 {lith}: {n_top} 个顶板点, {n_bot} 个底板点")
        
        # 提高过滤阈值到 5，避免单点/双点岩性退化为平面
        if n_top < 5 or n_bot < 5:
            print(f"!!! 跳过 {lith}：控制点过少，无法可靠插值")
            continue
        
        top_pts = np.array(data['top'])
        bot_pts = np.array(data['bottom'])
        
        # 凸包裁剪（归一化坐标）
        all_pts = np.vstack([top_pts[:, :2], bot_pts[:, :2]])
        try:
            hull = ConvexHull(all_pts)
            hull_path = Path(all_pts[hull.vertices])
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
        
        # ========== 关键修复：在归一化网格上预测 ==========
        Z_top = rbf_top(xi_n, yi_n)   # ← 用 xi_n, yi_n，不是 xi, yi
        Z_bot = rbf_bot(xi_n, yi_n)
        
        # 裁剪异常外推值
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
        
        # 保证顶面在底面之上
        mask = Z_top > Z_bot
        Z_top_c = np.where(mask, Z_top, Z_bot)
        Z_bot_c = np.where(mask, Z_bot, Z_top)
        
        # ========== 存储时用原始坐标（保持一致） ==========
        bodies[lith] = {
            'X': xi_orig, 'Y': yi_orig,
            'Z_top': Z_top_c, 'Z_bot': Z_bot_c,
            'color': data['color']
        }
        
        # 体层
        layers = []
        for k in range(n_layers + 2):
            t = k / (n_layers + 1)
            Z_layer = Z_top_c * (1 - t) + Z_bot_c * t
            layers.append(Z_layer)
        
        volume_data[lith] = {
            'X': xi_orig, 'Y': yi_orig,   # ← 关键：用 xi_orig, yi_orig
            'layers': layers,
            'color': data['color']
        }
        
        valid_count = int(np.sum(~np.isnan(Z_top_c)))
        print(f"==> 岩性 {lith} 插值成功，有效网格点: {valid_count}")
    
    return bodies, volume_data

def generate_depth_map_from_volume_v2(volume_data, output_path, light_dir=(-1, -1, 0.5)):
    """
    从 volume_data 生成深度图（与交互模型形态一致）
    """
    # 收集所有Z值
    all_z = []
    for data in volume_data.values():
        if 'layers' in data and data['layers']:
            for layer in data['layers']:
                valid = layer[~np.isnan(layer)]
                all_z.extend(valid)
    
    if not all_z:
        print("!!! 无有效Z值，无法生成深度图")
        return
    
    z_min, z_max = min(all_z), max(all_z)
    z_range = z_max - z_min if z_max > z_min else 1.0
    
    fig = plt.figure(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax = fig.add_subplot(111, projection='3d')
    
    # 光源方向
    light_dir = np.array(light_dir, dtype=float)
    light_dir = light_dir / (np.linalg.norm(light_dir) + 1e-8)
    
    # 计算所有数据的范围
    all_n, all_e = [], []
    for data in volume_data.values():
        if 'X' in data and 'Y' in data:
            all_n.extend(data['X'].ravel())
            all_e.extend(data['Y'].ravel())
    
    if not all_n or not all_e:
        print("!!! 无有效坐标数据")
        return
    
    margin = 20
    x_min, x_max = min(all_n) - margin, max(all_n) + margin
    y_min, y_max = min(all_e) - margin, max(all_e) + margin
    
    # 对每个岩性，使用所有层绘制
    for lith, data in volume_data.items():
        if 'layers' not in data or not data['layers']:
            continue
        
        X, Y = data['X'], data['Y']
        layers = data['layers']
        
        for Z in layers:
            if np.all(np.isnan(Z)):
                continue
            
            # 计算法线和光照
            dz_dx, dz_dy = np.gradient(Z)
            normals = np.stack([-dz_dx, -dz_dy, np.ones_like(dz_dx)], axis=-1)
            norm_length = np.sqrt(np.sum(normals**2, axis=-1))
            normals = normals / (norm_length[:, :, np.newaxis] + 1e-8)
            
            intensity = np.dot(normals, light_dir)
            intensity = 0.4 + 0.6 * intensity
            intensity = np.clip(intensity, 0.25, 1.0)
            
            depth_norm = (Z - z_min) / z_range
            gamma = 0.5
            depth_weight = (1.0 - depth_norm) ** gamma
            
            final_value = depth_weight * intensity
            final_value = 0.25 + 0.75 * final_value
            final_value = np.clip(final_value, 0.05, 1.0)
            final_value[np.isnan(Z)] = np.nan
            
            ax.plot_surface(
                X, Y, Z,
                facecolors=plt.cm.gray(final_value),
                edgecolor='none',
                alpha=1.0,
                vmin=0, vmax=1
            )
    
    # 黑色背景
    ax.set_facecolor('black')
    fig.patch.set_facecolor('black')
    ax.axis('off')
    ax.view_init(elev=VIEW_ELEVATION, azim=VIEW_AZIMUTH)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_zlim(z_min - 10, z_max + 10)
    
    plt.tight_layout(pad=0)
    plt.savefig(output_path, dpi=DEPTH_MAP_DPI, bbox_inches='tight',
               pad_inches=0, facecolor='black')
    plt.close()
    print(f"==> 深度图已保存: {output_path}")


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