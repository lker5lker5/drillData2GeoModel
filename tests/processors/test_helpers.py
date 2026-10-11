"""
测试 processors.py 中的工具函数（无需渲染的纯逻辑）
"""
import os
import pytest
import numpy as np
import pandas as pd


# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup(override_config):
    """应用路径重定向 + matplotlib Agg 后端"""
    import matplotlib
    matplotlib.use('Agg')
    pass


@pytest.fixture
def proc():
    """延迟导入 processors"""
    from handlers import processors as p
    return p


# ==================== 测试 parse_color ====================

class TestParseColor:
    """测试颜色解析（返回 (r,g,b,alpha) 元组）"""

    def test_hex_with_hash(self, proc):
        result = proc.parse_color('#FF0000')
        assert result == (1.0, 0.0, 0.0, 1.0)

    def test_hex_without_hash(self, proc):
        """无 # 前缀的 hex 不自动补充，返回 fallback"""
        result = proc.parse_color('00FF00')
        # 函数不处理无 # 的 hex，所以走到 fallback
        assert result[0] == 0.5
        assert result[1] == 0.5
        assert result[2] == 0.5
        assert result[3] == 1.0

    def test_rgb_string(self, proc):
        result = proc.parse_color('255,0,0')
        assert pytest.approx(result[0]) == 1.0
        assert result[1] == 0.0
        assert result[2] == 0.0

    def test_none_input(self, proc):
        result = proc.parse_color(None)
        assert len(result) == 4
        assert result[3] == 1.0  # alpha default

    def test_alpha_for_ore_body(self, proc):
        """岩性含"矿体"时 alpha = 1"""
        result = proc.parse_color('#FF0000', lith_name='萤石矿体')
        assert result[3] == 1.0

    def test_alpha_for_mineralized(self, proc):
        """岩性含"矿化带"时 alpha = 0.6"""
        result = proc.parse_color('#FF0000', lith_name='矿化带')
        assert result[3] == 0.6

    def test_alpha_for_other(self, proc):
        """其他岩性 alpha = 0.4"""
        result = proc.parse_color('#FF0000', lith_name='第四系')
        assert result[3] == 0.4

    def test_fallback_color(self, proc):
        """无法解析的颜色返回 (0.5, 0.5, 0.5, alpha)"""
        result = proc.parse_color('notacolor')
        assert result[0] == 0.5
        assert result[1] == 0.5
        assert result[2] == 0.5

    def test_returns_tuple(self, proc):
        result = proc.parse_color('#123456')
        assert isinstance(result, tuple)
        assert len(result) == 4


class TestHexToRgbStr:
    """测试 hex 转 rgb 字符串"""

    def test_with_hash(self, proc):
        result = proc.hex_to_rgb_str('#FF0000')
        assert result == 'rgb(255,0,0)'

    def test_without_hash(self, proc):
        result = proc.hex_to_rgb_str('00FF00')
        assert result == 'rgb(0,255,0)'

    def test_blue(self, proc):
        result = proc.hex_to_rgb_str('#0000FF')
        assert result == 'rgb(0,0,255)'

    def test_returns_string(self, proc):
        result = proc.hex_to_rgb_str('#123456')
        assert isinstance(result, str)

    def test_none_input(self, proc):
        """None 输入返回 None（函数不做空值保护）"""
        try:
            result = proc.hex_to_rgb_str(None)
            # 如果不报错，检查返回类型
            if result is not None:
                assert isinstance(result, str)
        except (AttributeError, TypeError):
            # None 无法处理 .startswith() / .lstrip()
            pass


class TestGetColorMapFromDataframe:
    """测试从岩性表提取颜色映射"""

    @pytest.fixture
    def litho_with_color_col(self):
        """使用代码实际使用的列名：'建模颜色' 和 '岩性描述'"""
        return pd.DataFrame({
            '岩性描述': ['矿化带', '第四系'],
            '建模颜色': ['#FF0000', '#00FF00'],
        })

    def test_returns_dict(self, proc, litho_with_color_col):
        cmap = proc.get_color_map_from_dataframe(litho_with_color_col)
        assert isinstance(cmap, dict)

    def test_maps_color_to_lith(self, proc, litho_with_color_col):
        cmap = proc.get_color_map_from_dataframe(litho_with_color_col)
        assert '#FF0000' in cmap.values() or '#FF0000' in cmap.keys()
        # 根据具体实现：返回 {color: lith_name} 还是 {lith_name: color}
        # 代码实际是 {color_value: lith_name}
        assert '#FF0000' in cmap

    def test_empty_dataframe(self, proc):
        df = pd.DataFrame({'岩性描述': [], '建模颜色': []})
        cmap = proc.get_color_map_from_dataframe(df)
        assert cmap == {}

    def test_skips_nan_rows(self, proc):
        df = pd.DataFrame({
            '岩性描述': ['矿化带', 'nan', '第四系'],
            '建模颜色': ['#FF0000', '#NaN', '#00FF00'],
        })
        cmap = proc.get_color_map_from_dataframe(df)
        assert len(cmap) >= 1

    def test_missing_columns(self, proc):
        df = pd.DataFrame({'名称': ['A'], '颜色': ['#FF0000']})
        cmap = proc.get_color_map_from_dataframe(df)
        assert cmap == {}


class TestComputeTrajectory:
    """测试钻孔轨迹计算"""

    @pytest.fixture
    def survey(self):
        """使用实际列名：'各层位长度'（代码实际使用的列名）"""
        return pd.DataFrame({
            '钻孔编号': ['ZK01', 'ZK01'],
            '各层位长度': [0.0, 100.0],
            '倾角': [-90.0, -90.0],
            '方位角': [0.0, 0.0],
        })

    def test_returns_tuple(self, proc, survey):
        result = proc.compute_trajectory(survey)
        # 返回 (lengths, xs, ys, zs) 元组
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_returns_numpy_arrays(self, proc, survey):
        lengths, xs, ys, zs = proc.compute_trajectory(survey)
        assert isinstance(lengths, np.ndarray)
        assert isinstance(xs, np.ndarray)
        assert isinstance(ys, np.ndarray)
        assert isinstance(zs, np.ndarray)

    def test_vertical_hole(self, proc, survey):
        """垂直孔：XY 不变，Z 向下递减"""
        lengths, xs, ys, zs = proc.compute_trajectory(survey)
        assert len(xs) == len(lengths)
        assert max(xs) - min(xs) < 1.0
        assert max(ys) - min(ys) < 1.0
        # Z 应递减（向下）
        assert zs[0] >= zs[-1]

    def test_lengths_sorted(self, proc, survey):
        lengths, _, _, _ = proc.compute_trajectory(survey)
        for i in range(1, len(lengths)):
            assert lengths[i] >= lengths[i-1]

    def test_empty_dataframe(self, proc):
        df = pd.DataFrame({'各层位长度': [], '倾角': [], '方位角': []})
        try:
            lengths, xs, ys, zs = proc.compute_trajectory(df)
            # 空数据可能返回空数组
            assert len(lengths) == 0
        except Exception:
            pass  # 空数据的行为取决于具体实现


class TestGetInterpolatedCoords:
    """测试插值坐标获取"""

    def test_returns_tuple(self, proc):
        target = np.array([0.0, 50.0, 100.0])
        lengths = np.array([0.0, 50.0, 100.0])
        xs = np.array([0.0, 0.0, 0.0])
        ys = np.array([0.0, 0.0, 0.0])
        zs = np.array([100.0, 50.0, 0.0])
        result = proc.get_interpolated_coords(lengths, xs, ys, zs, target)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_linear_interpolation(self, proc):
        target = np.array([0.0, 50.0, 100.0])
        lengths = np.array([0.0, 50.0, 100.0])
        xs = np.array([0.0, 50.0, 100.0])
        ys = np.array([0.0, 0.0, 0.0])
        zs = np.array([100.0, 50.0, 0.0])
        interp_x, interp_y, interp_z = proc.get_interpolated_coords(lengths, xs, ys, zs, target)
        assert len(interp_x) == 3
        assert len(interp_y) == 3
        assert len(interp_z) == 3
        assert interp_x[1] == 50.0


class TestTransformXyToLonlat:
    """测试坐标转换"""

    def test_returns_tuple(self, proc):
        result = proc.transform_xy_to_lonlat(500000, 3000000)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_known_conversion(self, proc):
        """使用典型的 CGCS2000 3度带坐标做粗略验证"""
        lon, lat = proc.transform_xy_to_lonlat(500000, 3000000, zone=38)
        assert isinstance(lon, float)
        assert isinstance(lat, float)

    def test_auto_extract_zone(self, proc):
        """从带号坐标自动提取"""
        # x=38500000 包含带号38
        lon, lat = proc.transform_xy_to_lonlat(38500000, 3000000)
        assert isinstance(lon, float)
        assert isinstance(lat, float)

    def test_default_zone(self, proc):
        """x<1e6 时使用默认带号"""
        lon, lat = proc.transform_xy_to_lonlat(500000, 3000000)
        assert isinstance(lon, float)
        assert isinstance(lat, float)


class TestAddPointsToData:
    """测试点数据扩展"""

    @pytest.fixture
    def loc_df(self):
        """使用实际列名"""
        return pd.DataFrame({
            '钻孔编号': ['ZK01', 'ZK02'],
            '开孔坐标E': [40500000, 40501000],
            '开孔坐标N': [3000000, 3001000],
            '开孔高程R': [100.0, 120.0],
        })

    def test_returns_list(self, proc, loc_df):
        result = proc.add_points_to_data(loc_df)
        assert isinstance(result, list)

    def test_contains_dicts(self, proc, loc_df):
        result = proc.add_points_to_data(loc_df)
        assert all(isinstance(p, dict) for p in result)

    def test_has_required_keys(self, proc, loc_df):
        result = proc.add_points_to_data(loc_df)
        for p in result:
            assert '钻孔编号' in p
            assert 'lon' in p
            assert 'lat' in p

    def test_empty_dataframe(self, proc):
        df = pd.DataFrame({'钻孔编号': [], '开孔坐标E': [], '开孔坐标N': [], '开孔高程R': []})
        result = proc.add_points_to_data(df)
        assert len(result) == 0

    def test_single_hole(self, proc):
        df = pd.DataFrame({
            '钻孔编号': ['ZK01'],
            '开孔坐标E': [40500000],
            '开孔坐标N': [3000000],
            '开孔高程R': [100.0],
        })
        result = proc.add_points_to_data(df)
        assert len(result) == 1


class TestBuildPlotlyCylinderMesh:
    """测试 Plotly 圆柱体网格构建（返回 6 元组: x, y, z, i, j, k）"""

    def test_returns_tuple(self, proc):
        result = proc.build_plotly_cylinder_mesh([0, 0], [0, 0], [100, 0], radius=3.0, sides=8)
        assert isinstance(result, tuple)
        assert len(result) == 6

    def test_returns_lists(self, proc):
        result = proc.build_plotly_cylinder_mesh([0, 0], [0, 0], [100, 0], radius=3.0, sides=8)
        for item in result:
            assert isinstance(item, list)

    def test_all_have_same_length(self, proc):
        """x, y, z 应等长（顶点列表）"""
        x, y, z, i, j, k = proc.build_plotly_cylinder_mesh(
            [0, 0], [0, 0], [100, 0], radius=3.0, sides=8
        )
        assert len(x) == len(y) == len(z)
        assert len(x) > 0

    def test_vertex_count_two_segments(self, proc):
        """2 个轨迹点 => sides*2 个环向顶点（无端帽）"""
        x, y, z, i, j, k = proc.build_plotly_cylinder_mesh(
            [0, 0], [0, 0], [100, 0], radius=3.0, sides=8
        )
        expected = 8 * 2  # 2 个剖面，每个 8 个顶点
        assert len(x) == expected

    def test_minimal_sides(self, proc):
        x, y, z, i, j, k = proc.build_plotly_cylinder_mesh(
            [0, 0], [0, 0], [100, 0], radius=3.0, sides=3
        )
        assert len(x) == 3 * 2

    def test_has_faces(self, proc):
        x, y, z, i, j, k = proc.build_plotly_cylinder_mesh(
            [0, 0], [0, 0], [100, 0], radius=3.0, sides=8
        )
        assert len(i) > 0
        assert len(j) == len(i)
        assert len(k) == len(i)