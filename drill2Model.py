import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import Rbf
from matplotlib import font_manager
from scipy.interpolate import interp1d
from scipy.spatial import ConvexHull
from matplotlib.path import Path
import argparse
import os,sys
from datetime import datetime

# ==================== 字体设置 ====================
try:
    font_path = '/Users/kaner/Library/Fonts/FangSong_GB2312.ttf'
    prop = font_manager.FontProperties(fname=font_path)
    plt.rcParams['font.family'] = prop.get_name()
except:
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

# ==================== 颜色解析 ====================
def parse_color(color_str, lith_name=None):
    """
    解析颜色字符串，返回 (r, g, b, alpha) 元组
    """
    alpha = 1.0
    if lith_name:
        if '矿' in lith_name:
            alpha = 0.8
        elif '矿化' in lith_name:
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
    print(f"警告: 无法解析颜色 '{color_str}'，使用灰色")
    return (0.5, 0.5, 0.5, alpha)

# ==================== 钻孔轨迹计算 ====================
def compute_trajectory(df_survey):
    """
    根据测斜数据计算钻孔轨迹点（相对孔口）
    要求 DataFrame 有 '各层位长度', '方位角', '倾角' 列
    返回: lengths (正值), xs, ys, zs (z为高程，孔口高程需另行添加)
    """
    df = df_survey.sort_values('各层位长度', ascending=True)
    lengths = df['各层位长度'].values
    az = np.radians(df['方位角'].values)
    inc = np.radians(np.abs(df['倾角'].values))  # 倾角取绝对值
    xs = [0.0]
    ys = [0.0]
    zs = [0.0]  # 相对孔口，向下为负
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

# ==================== 插值构建地质体（含多层体） ====================
def create_interactive_model(volume_data, hole_ids, loc_df, survey_df, litho_df, output_path):
    import plotly.graph_objects as go
    fig = go.Figure()
    
    # 绘制地质体（多层表面），每个岩性只显示一个图例
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
                showlegend=show_legend,
                name=lith if show_legend else "",
                hoverinfo='skip'
            ))
    
    # 绘制钻孔（不添加图例）
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
        # 中心线
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode='lines',
            line=dict(color='gray', width=2, dash='dash'),
            showlegend=False,
            hoverinfo='skip'
        ))
        # 岩性段
        litho = litho_df[litho_df['钻孔编号'] == hid].sort_values('上层位长度起始刻度', ascending=True)
        for _, seg in litho.iterrows():
            d_top = seg['上层位长度起始刻度']
            d_bot = seg['下层位长度起始刻度']
            lith_name = seg['岩性描述']
            color = parse_color(seg['建模颜色'], lith_name)
            if d_top < lengths[0]: d_top = lengths[0]
            if d_bot > lengths[-1]: d_bot = lengths[-1]
            if d_top >= d_bot: continue
            n_points = max(3, int((d_bot - d_top) / 0.5))
            n_points = min(n_points, 200)
            d_sample = np.linspace(d_top, d_bot, n_points)
            x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)
            if len(x) == 0:
                continue
            color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode='lines',
                line=dict(color=color_str, width=6),
                showlegend=False,
                hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.1f}}m<extra></extra>'
            ))
        # 钻孔编号
        fig.add_trace(go.Scatter3d(
            x=[x0], y=[y0], z=[z0+3],
            mode='text',
            text=[hid],
            textfont=dict(size=14, color='black', family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 布局
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    all_z = loc_df['开孔高程R'].values
    z_min = min(all_z)
    for hid in hole_ids:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            _, _, _, zs = compute_trajectory(surv)
            row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
            zs += row['开孔高程R']
            if len(zs) > 0:
                z_min = min(z_min, np.min(zs))
    margin = 20
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='Northing (m)', range=[all_n.min()-margin, all_n.max()+margin]),
            yaxis=dict(title='Easting (m)', range=[all_e.min()-margin, all_e.max()+margin]),
            zaxis=dict(title='Elevation (m)', range=[z_min-10, all_z.max()+5]),
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.0))
        ),
        width=1200,
        height=800,
        title='交互式三维地质体模型',
        legend=dict(
            title='岩性',
            font=dict(size=12),
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='black',
            borderwidth=1
        )
    )
    fig.write_html(output_path)
    print(f'交互式模型已保存: {output_path}')

# ==================== Matplotlib 绘图（标注/无标注） ====================
def plot_bodies_mpl(bodies, hole_ids, loc_df, survey_df, litho_df, output_dir, suffix, labeled=True):
    fig = plt.figure(figsize=(14, 11))
    ax = fig.add_subplot(111, projection='3d')
    
    # 绘制钻孔（仅标注版）
    if labeled:
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
            litho = litho_df[litho_df['钻孔编号'] == hid].sort_values('上层位长度起始刻度', ascending=True)
            for idx, seg in litho.iterrows():
                d_top = seg['上层位长度起始刻度']
                d_bot = seg['下层位长度起始刻度']
                lith_name = seg['岩性描述']
                color = parse_color(seg['建模颜色'], lith_name)
                if d_top < lengths[0]: d_top = lengths[0]
                if d_bot > lengths[-1]: d_bot = lengths[-1]
                if d_top >= d_bot: continue
                d_sample = np.linspace(d_top, d_bot, max(3, int((d_bot-d_top)/0.5)))
                x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)
                ax.plot(x, y, z, color=color[:3], alpha=color[3], linewidth=6,
                        label=lith_name if labeled and idx==0 else "")
            if labeled:
                ax.text(x0, y0, z0+2, hid, color='black', fontsize=10, ha='center', va='bottom')
    
    # 绘制地质体表面
    all_z = []
    for lith, data in bodies.items():
        # 检查是否有有效数据
        if np.all(np.isnan(data['Z_top'])) or np.all(np.isnan(data['Z_bot'])):
            print(f"警告：{lith} 的 Z_top 或 Z_bot 全为 NaN，跳过绘制")
            continue
        color = data['color']
        ax.plot_surface(data['X'], data['Y'], data['Z_top'],
                        color=color[:3], alpha=color[3], edgecolor='none',
                        label=lith if labeled else "")
        ax.plot_surface(data['X'], data['Y'], data['Z_bot'],
                        color=color[:3], alpha=color[3]*0.6, edgecolor='none')
        # 收集有效Z值用于范围
        z_top_valid = data['Z_top'][~np.isnan(data['Z_top'])]
        z_bot_valid = data['Z_bot'][~np.isnan(data['Z_bot'])]
        all_z.extend(z_top_valid)
        all_z.extend(z_bot_valid)
    
    if not labeled:
        ax.axis('off')
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')
        plt.title('')
        plt.tight_layout(pad=0)
        fname = f'3D_model_unlabeled_{suffix}.png'
        plt.savefig(os.path.join(output_dir, fname), dpi=300, bbox_inches='tight', pad_inches=0, facecolor='white')
        print(f'保存无标注图: {fname}')
    else:
        ax.set_xlabel('Northing (m)')
        ax.set_ylabel('Easting (m)')
        ax.set_zlabel('Elevation (m)')
        ax.view_init(elev=25, azim=-60)
        # 设置Z轴范围，处理空值或NaN
        if all_z:
            # 过滤掉NaN
            all_z_clean = [z for z in all_z if not np.isnan(z)]
            if all_z_clean:
                z_min = min(all_z_clean) - 10
                z_max = max(all_z_clean) + 5
                ax.set_zlim(z_min, z_max)
            else:
                # 备用：从定位表获取高程范围
                z_min = loc_df['开孔高程R'].min() - 20
                z_max = loc_df['开孔高程R'].max() + 10
                ax.set_zlim(z_min, z_max)
        else:
            # 备用
            z_min = loc_df['开孔高程R'].min() - 20
            z_max = loc_df['开孔高程R'].max() + 10
            ax.set_zlim(z_min, z_max)
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), loc='upper right', fontsize=8)
        plt.title('三维地质体模型（插值）', fontsize=14)
        plt.tight_layout()
        fname = f'3D_model_labeled_{suffix}.png'
        plt.savefig(os.path.join(output_dir, fname), dpi=300, bbox_inches='tight')
        print(f'保存标注图: {fname}')
    plt.close(fig)

# ==================== 三维插值建模 ====================
def build_geological_bodies_with_volume(loc_df, litho_df, survey_df, n_layers=10):
    # 获取孔口坐标（含高程）
    hole_coords = {}
    for _, row in loc_df.iterrows():
        hid = row['钻孔编号']
        hole_coords[hid] = (row['开孔坐标N'], row['开孔坐标E'], row['开孔高程R'])
    
    # 轨迹缓存
    traj_cache = {}
    for hid in loc_df['钻孔编号']:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            lengths, xs, ys, zs = compute_trajectory(surv)
            traj_cache[hid] = {'lengths': lengths, 'xs': xs, 'ys': ys, 'zs': zs}
    
    # 收集岩性顶底点
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
        litho_groups[lith]['top'].append((x_top, y_top, z_top))
        litho_groups[lith]['bottom'].append((x_bot, y_bot, z_bot))
    
    # 打印每个岩性的点数
    for lith, data in litho_groups.items():
        print(f"岩性 {lith}: {len(data['top'])} 个顶底控制点")
    
    # 确定插值网格（扩大范围）
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    x_min, x_max = all_n.min() - 50, all_n.max() + 50  # 加大缓冲
    y_min, y_max = all_e.min() - 50, all_e.max() + 50
    grid_res = 30  # 提高分辨率
    xi = np.linspace(x_min, x_max, grid_res)
    yi = np.linspace(y_min, y_max, grid_res)
    xi, yi = np.meshgrid(xi, yi)
    
    bodies = {}
    volume_data = {}
    for lith, data in litho_groups.items():
        if len(data['top']) < 2:  # 放宽至2个点
            print(f"跳过 {lith}，仅 {len(data['top'])} 个点")
            continue
        top_pts = np.array(data['top'])
        bot_pts = np.array(data['bottom'])
        # 改用全局凸包作为掩膜（所有点联合）
        all_pts = np.vstack([top_pts[:, :2], bot_pts[:, :2]])
        try:
            hull = ConvexHull(all_pts)
            hull_path = Path(all_pts[hull.vertices])
            grid_points = np.column_stack((xi.ravel(), yi.ravel()))
            inside = hull_path.contains_points(grid_points).reshape(xi.shape)
        except:
            inside = np.ones(xi.shape, dtype=bool)
        try:
            # 增大平滑参数
            rbf_top = Rbf(top_pts[:,0], top_pts[:,1], top_pts[:,2], function='linear', smooth=2.0)
            rbf_bot = Rbf(bot_pts[:,0], bot_pts[:,1], bot_pts[:,2], function='linear', smooth=2.0)
        except Exception as e:
            print(f"岩性 {lith} 插值失败: {e}")
            continue
        Z_top = rbf_top(xi, yi)
        Z_bot = rbf_bot(xi, yi)
        # 应用掩膜
        Z_top[~inside] = np.nan
        Z_bot[~inside] = np.nan
        # 保证顶面在底面之上
        mask = Z_top > Z_bot
        Z_top_c = np.where(mask, Z_top, Z_bot)
        Z_bot_c = np.where(mask, Z_bot, Z_top)
        bodies[lith] = {'X': xi, 'Y': yi, 'Z_top': Z_top_c, 'Z_bot': Z_bot_c, 'color': data['color']}
        # 体层
        layers = []
        for k in range(n_layers + 2):
            t = k / (n_layers + 1)
            Z_layer = Z_top_c * (1 - t) + Z_bot_c * t
            layers.append(Z_layer)
        volume_data[lith] = {'X': xi, 'Y': yi, 'layers': layers, 'color': data['color']}
        print(f"岩性 {lith} 插值成功，有效网格点: {np.sum(~np.isnan(Z_top_c))}")
    
    return bodies, volume_data

# ==================== Plotly 可交互模型 ====================
def create_interactive_model(volume_data, hole_ids, loc_df, survey_df, litho_df, output_path):
    import plotly.graph_objects as go
    fig = go.Figure()
    
    # --- 数据范围（用于放置假散点）---
    all_n = loc_df['开孔坐标N'].values
    all_e = loc_df['开孔坐标E'].values
    all_z = loc_df['开孔高程R'].values
    # 计算所有钻孔的最小高程（用于假点位置）
    z_min_all = min(all_z)
    for hid in hole_ids:
        surv = survey_df[survey_df['钻孔编号'] == hid]
        if len(surv) > 0:
            _, _, _, zs = compute_trajectory(surv)
            row = loc_df[loc_df['钻孔编号'] == hid].iloc[0]
            zs += row['开孔高程R']
            if len(zs) > 0:
                z_min_all = min(z_min_all, np.min(zs))
    
    # --- 绘制地质体（多层表面）---
    for lith, data in volume_data.items():
        color = data['color']
        color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'
        layers = data['layers']
        if not layers:
            continue
        # 绘制每一层表面，不显示图例和colorbar
        for k, Z in enumerate(layers):
            opacity = 0.2 + 0.5 * (k / (len(layers)-1)) if len(layers)>1 else 0.5
            fig.add_trace(go.Surface(
                x=data['X'], y=data['Y'], z=Z,
                colorscale=[[0, color_str], [1, color_str]],
                opacity=opacity,
                showscale=False,      # 隐藏colorbar
                showlegend=False,     # 不显示在图例中
                hoverinfo='skip'
            ))
        # 添加一个不可见的散点作为图例色块
        # 将点放在模型范围外很远的地方，避免干扰视图
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
    
    # --- 绘制钻孔（与之前相同，但图例已去掉）---
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
        
        # 钻孔中心线
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode='lines',
            line=dict(color='gray', width=2, dash='dash'),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # 岩性段
        litho = litho_df[litho_df['钻孔编号'] == hid].sort_values('上层位长度起始刻度', ascending=True)
        for _, seg in litho.iterrows():
            d_top = seg['上层位长度起始刻度']
            d_bot = seg['下层位长度起始刻度']
            lith_name = seg['岩性描述']
            color = parse_color(seg['建模颜色'], lith_name)
            if d_top < lengths[0]: d_top = lengths[0]
            if d_bot > lengths[-1]: d_bot = lengths[-1]
            if d_top >= d_bot: continue
            n_points = max(3, int((d_bot - d_top) / 0.5))
            n_points = min(n_points, 200)
            d_sample = np.linspace(d_top, d_bot, n_points)
            x, y, z = get_interpolated_coords(lengths, xs, ys, zs, d_sample)
            if len(x) == 0: continue
            color_str = f'rgb({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)})'
            fig.add_trace(go.Scatter3d(
                x=x, y=y, z=z,
                mode='lines',
                line=dict(color=color_str, width=6),
                showlegend=False,
                hovertemplate=f'钻孔: {hid}<br>岩性: {lith_name}<br>高程: %{{z:.1f}}m<extra></extra>'
            ))
        # 钻孔编号
        fig.add_trace(go.Scatter3d(
            x=[x0], y=[y0], z=[z0+3],
            mode='text',
            text=[hid],
            textfont=dict(size=14, color='black', family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # --- 布局设置 ---
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
        title='交互式三维地质体模型'
    )
    fig.write_html(output_path)
    print(f'交互式模型已保存: {output_path}')

# ==================== 模拟光源生成深度图 ====================
def generate_depth_map_from_volume(volume_data, output_path, light_dir=(-1, -1, 0.5)):
    """
    使用 volume_data 的多层体数据生成深度图（高对比度）
    """
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    
    fig = plt.figure(figsize=(14, 11))
    ax = fig.add_subplot(111, projection='3d')
    
    # 收集所有Z值
    all_z = []
    for data in volume_data.values():
        if 'layers' in data and data['layers']:
            for layer in data['layers']:
                valid = layer[~np.isnan(layer)]
                all_z.extend(valid)
    if not all_z:
        print("警告: 无有效Z值，无法生成深度图")
        return
    
    z_min, z_max = min(all_z), max(all_z)
    z_range = z_max - z_min if z_max > z_min else 1.0
    
    # 光源方向
    light_dir = np.array(light_dir, dtype=float)
    light_dir = light_dir / (np.linalg.norm(light_dir) + 1e-8)
    
    # 对每个岩性，使用中间层
    for lith, data in volume_data.items():
        if 'layers' not in data or not data['layers']:
            continue
        X, Y = data['X'], data['Y']
        layers = data['layers']
        
        # 使用中间层作为代表面
        mid_idx = len(layers) // 2
        Z = layers[mid_idx].copy()
        
        if np.all(np.isnan(Z)):
            for layer in layers:
                if not np.all(np.isnan(layer)):
                    Z = layer.copy()
                    break
            else:
                continue
        
        # 计算法线和光照
        dz_dx, dz_dy = np.gradient(Z)
        normals = np.stack([-dz_dx, -dz_dy, np.ones_like(dz_dx)], axis=-1)
        norm_length = np.sqrt(np.sum(normals**2, axis=-1))
        normals = normals / (norm_length[:, :, np.newaxis] + 1e-8)
        
        # 计算光照强度（增加环境光成分）
        intensity = np.dot(normals, light_dir)
        # 添加环境光 0.3，使暗部更亮，同时保持方向感
        intensity = 0.4 + 0.6 * intensity
        intensity = np.clip(intensity, 0.25, 1.0)
        
        # 深度归一化
        depth_norm = (Z - z_min) / z_range
        
        # 使用非线性变换增强浅部与深部的对比度
        # 指数变换：浅部（depth_norm小）更亮，深部（depth_norm大）更暗
        # gamma < 1 使浅部更亮，深部更暗
        gamma = 0.5
        depth_weight = (1.0 - depth_norm) ** gamma
        # 或者使用平方根变换：depth_weight = np.sqrt(1.0 - depth_norm)
        
        # 结合光照强度，并扩大亮度范围
        final_value = depth_weight * intensity
        # 拉伸到 0.15~1.0，确保最暗处也有一定亮度
        final_value = 0.25 + 0.75 * final_value
        final_value = np.clip(final_value, 0.05, 1.0)
        final_value[np.isnan(Z)] = np.nan
        
        # 绘制该层
        ax.plot_surface(X, Y, Z, facecolors=plt.cm.gray(final_value),
                        edgecolor='none', alpha=1.0, vmin=0, vmax=1)
    
    # 黑色背景
    ax.set_facecolor('black')
    fig.patch.set_facecolor('black')
    ax.axis('off')
    ax.view_init(elev=25, azim=-60)
    
    # 调整视图范围
    all_n, all_e = [], []
    for data in volume_data.values():
        if 'X' in data and 'Y' in data:
            all_n.extend(data['X'].ravel())
            all_e.extend(data['Y'].ravel())
    if all_n and all_e:
        margin = 20
        ax.set_xlim(min(all_n)-margin, max(all_n)+margin)
        ax.set_ylim(min(all_e)-margin, max(all_e)+margin)
        ax.set_zlim(z_min-10, z_max+10)
    
    plt.tight_layout(pad=0)
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                pad_inches=0, facecolor='black')
    plt.close()
    print(f'深度图已保存: {output_path}')

# ==================== 主函数 ====================
def main(input_path, output_dir):
    loc_df = pd.read_excel(input_path, sheet_name='定位表')
    survey_df = pd.read_excel(input_path, sheet_name='测斜表')
    litho_df = pd.read_excel(input_path, sheet_name='岩性表')
    
    hole_ids = loc_df['钻孔编号'].unique()
    suffix = datetime.now().strftime('%y%m%d%H%M')
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建体模型
    print("正在构建地质体模型（含多层插值）...")
    bodies, volume_data = build_geological_bodies_with_volume(loc_df, litho_df, survey_df, n_layers=12)
    
    if not bodies:
        print("错误：未生成任何地质体，请检查数据")
        return

    # 1. 生成标注图
    plot_bodies_mpl(bodies, hole_ids, loc_df, survey_df, litho_df, output_dir, suffix, labeled=True)
    # 2. 生成无标注图
    plot_bodies_mpl(bodies, hole_ids, loc_df, survey_df, litho_df, output_dir, suffix, labeled=False)
    # 3. 生成交互式HTML
    html_path = os.path.join(output_dir, f'interactive_model_{suffix}.html')
    create_interactive_model(volume_data, hole_ids, loc_df, survey_df, litho_df, html_path)
    
    # 4. 生成带光照的深度图（新增）
    depth_path = os.path.join(output_dir, f'depth_map_{suffix}.png')
    generate_depth_map_from_volume(volume_data, depth_path, light_dir=[-1, -1, 0.5])

    print("所有模型生成完成！")

# ==================== 命令行入口 ====================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="生成钻孔地层示意图和深度图，供 ComfyUI 使用")
    parser.add_argument("--drilldata", "-d", required=True, help="钻孔数据 Excel 文件路径")
    parser.add_argument("--output", "-o", default="/Users/kaner/comfy_project/temp/mineModel", help="图片输出目录")
    args = parser.parse_args()

    # 检查输入文件是否存在
    if not os.path.isfile(args.drilldata):
        print(f"!!! 文件不存在: {args.drilldata}")
        sys.exit(1)

    main(args.drilldata, args.output)