# config.py
# 固定参数和配置信息

import os

# 基础路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
TEMPLATE_FOLDER = os.path.join(BASE_DIR, 'templates')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')

# 确保目录存在
for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMPLATE_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 文件配置
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Excel模板文件名
TEMPLATE_FILE = os.path.join(TEMPLATE_FOLDER, 'drill_data_template.xlsx')

# ==================== 地图与坐标转换 ====================
ZJ_TIANDITU_HOST = 'api.tianditu.gov.cn'
ZJ_TIANDITU_KEY = os.environ.get('ZJ_TIANDITU_KEY')

# ==================== 绘图配置 =========================
FIGURE_DPI = 300
FIGURE_WIDTH = 14
FIGURE_HEIGHT = 11

# 3D模型视角配置
VIEW_CONFIGS = [
    {
        'order': 1,
        'name': 'main_view',
        'label': '立体全景视图（主视图）',
        'elev': 25,
        'azim': -45,
        'user_tip': '报告首页主视图，展示矿体总体形态、空间延伸关系及与地形的空间关系。作为所有报告和AI参考图的主视图，固定模型位置、画幅和比例。'
    },
    {
        'order': 2,
        'name': 'east_west_section',
        'label': '东西向侧视图（从东侧向西看）',
        'elev': 0,
        'azim': 0,
        'user_tip': '检查矿体东西向延伸、厚度变化及不同地层的垂向关系。如需真正地质剖面应另外生成垂直剖切面。'
    },
    {
        'order': 3,
        'name': 'north_south_section',
        'label': '南北向侧视图（从北侧向南看）',
        'elev': 0,
        'azim': 90,
        'user_tip': '检查矿体南北向延伸、倾伏趋势和厚度变化。与东西向图使用相同Z轴范围，便于比较矿体垂向变化。'
    },
    {
        'order': 4,
        'name': 'top_down_view',
        'label': '俯视平面图（正上方下看）',
        'elev': 90,
        'azim': -90,
        'user_tip': '判断矿体平面展布、走向和边界。可叠加钻孔位置和勘探线，便于报告审查。'
    },
    {
        'order': 5,
        'name': 'supplementary_view',
        'label': '补充立体视图（东南方向俯瞰）',
        'elev': 25,
        'azim': 135,
        'user_tip': '补充主视图背面被遮挡的结构，检查主视图不易观察的矿体边界和延伸方向。用于报告补充图和AI建模的第二个立体参考方向。'
    },
    {
        'order': 6,
        'name': 'iso_view',
        'label': '标准等轴测视图（等轴测投影）',
        'elev': 35.264,  # arctan(1/√2) ≈ 35.264°, 真正的等轴测投影角
        'azim': -45,
        'user_tip': '标准化三维形态对比，用于技术报告和不同模型版本之间的视觉比较。固定坐标轴显示比例与投影方式。'
    },
]

# 插值配置
GRID_RESOLUTION = 50
N_LAYERS = None # 12
RBF_SMOOTH = .1 # 2.0，由于做了归一化处理，可以做精确插值
RBF_FUNCTION = 'multiquadric' # 'linear' 'gussian' 'multiquadric' 'inverse' 'thin_plate'

# ==================== 钻孔圆柱样式配置 ====================
# 钻孔样式：'cylinder'（圆柱，默认）或 'line'（线段，备选）
DRILL_STYLE = 'cylinder'

# 圆柱半径（单位：米）
DRILL_RADIUS = 3.0

# 圆柱圆周的分段数（8 表示八角柱，越大越圆润但越慢）
DRILL_CYLINDER_SIDES = 8

# 沿钻孔轨迹的采样步长（单位：米，越小越平滑但越慢）
DRILL_SAMPLE_STEP = 1.5

# 降级策略：当钻孔段总数超过此值时，自动降级为线段
DRILL_DEGRADE_THRESHOLD = 2000

# 降级策略：当钻孔段总数超过此值时，强制为极简线段
DRILL_FORCE_LINE_THRESHOLD = 5000

# 降级模式下的线段宽度
DRILL_LINE_WIDTH = 6

# Session 超时配置（分钟）
SESSION_TIMEOUT_MINUTES = 60

# 服务器配置
HOST = '0.0.0.0'
PORT = 5001
DEBUG = True

# AI配置
QWEN_API_KEY = os.environ.get('QWEN_KEY')
QWEN_MODEL = 'qwen-image-3.0-pro'
QWEN_API_URL = 'https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'

# AI 生图使用的默认参考视图（按 view name 标识）
# 对应：立体全景视图 + 南北向剖面 + 东西向剖面
AI_DEFAULT_REFERENCE_VIEWS = ['main_view', 'east_west_section', 'north_south_section']

# ==================== 缓存配置 ====================
# 缓存有效期（小时）
CACHE_TTL_HOURS = 24

# 后台清理线程的扫描间隔（秒）
CACHE_CLEANUP_INTERVAL = 3600

# 缓存存储目录名（位于 outputs/ 下）
CACHE_DIR_NAME = '_cache'

# 是否启用缓存
CACHE_ENABLED = True

# ==================== AI 图评分配置 ====================
# 评分权重
SCORE_WEIGHT_SSIM = 0.6      # 结构相似度权重
SCORE_WEIGHT_COLOR = 0.4     # 色调相似度权重

# 分数差距阈值（低于此值视为"接近"，两张都保留并提示）
SCORE_DIFF_THRESHOLD = 0.05

# 推荐标记阈值（高于此值才标记为"推荐"）
SCORE_RECOMMEND_THRESHOLD = 0.7

# ==================== 多视角 AI 生成配置 ====================
# 可选的生成数量
MULTIVIEW_COUNT_OPTIONS = [1, 2, 3, 4, 5, 6]
MULTIVIEW_DEFAULT_COUNT = 6

# 用于多视角生成/纹理升级的视图顺序（order 值），全部 6 个视角
MULTIVIEW_VIEW_ORDERS = [1, 2, 3, 4, 5, 6]

# ==================== 多视角纹理升级配置 ====================
# 是否启用遮罩合成模式
MULTIVIEW_USE_MASK_COMPOSITE = True

# 是否启用色调统一后处理
MULTIVIEW_UNIFY_COLOR = True

# 色调统一方法：'reinhard' 或 'histogram'
MULTIVIEW_COLOR_METHOD = 'reinhard'

# 几何图黑色描边的线宽（像素）
GEOMETRY_EDGE_WIDTH = 0.5

# 遮罩合成时，几何图"非白像素"的阈值
MASK_WHITE_THRESHOLD = 240

# ==================== 纹理 tile 生成配置 ====================
# AI 生成的纹理贴片最终尺寸（像素）
TEXTURE_TILE_SIZE = 1024
# AI 生成时的输出尺寸（与 tile 最终尺寸一致，避免下采样损失细节）
TEXTURE_GENERATE_SIZE = 1024
# 纹理生成时不扩展 prompt（生成式模型不可控，纹理生成不需要扩展）
TEXTURE_PROMPT_EXTEND = False

# ==================== 克里金插值配置 ====================
# 默认变异函数模型
KRIGING_VARIOGRAM_MODEL = 'spherical'
# 允许前端选择的变异函数模型
KRIGING_VARIOGRAM_OPTIONS = ['spherical', 'exponential', 'gaussian', 'linear', 'power']

# ==================== 插值方法配置 ====================
# 默认插值方法：'rbf' 或 'kriging'
INTERPOLATION_METHOD = 'rbf'
# 前端可选的插值方法
INTERPOLATION_METHOD_OPTIONS = ['rbf', 'kriging']

# ==================== 建模参数前端可调配置 ====================
# 允许用户在前端调整的参数清单
USER_ADJUSTABLE_PARAMS = {
    'GRID_RESOLUTION': {
        'label': '网格分辨率',
        'type': 'number',
        'group': '建模参数',
        'min': 10,
        'max': 100,
        'step': 1,
        'default': GRID_RESOLUTION,
        'description': '网格越密模型越精细，但计算越慢'
    },
    'N_LAYERS': {
        'label': '体渲染层数',
        'type': 'number_or_auto',
        'group': '建模参数',
        'min': 5,
        'max': 50,
        'step': 1,
        'default': N_LAYERS,
        'description': '体渲染的层数。自动模式下根据岩性厚度计算'
    },
    'DRILL_STYLE': {
        'label': '钻孔样式',
        'type': 'enum',
        'group': '钻孔显示参数',
        'options': ['cylinder', 'line'],
        'default': DRILL_STYLE,
        'description': 'cylinder = 圆柱体，line = 线段'
    },
    'DRILL_RADIUS': {
        'label': '钻孔半径（米）',
        'type': 'number',
        'group': '钻孔显示参数',
        'min': 0.5,
        'max': 20.0,
        'step': 0.5,
        'default': DRILL_RADIUS,
        'description': '钻孔圆柱的半径。建议 1~5 米'
    },
    'RBF_FUNCTION': {
        'label': 'RBF核函数',
        'type': 'enum',
        'group': '插值参数',
        'options': ['multiquadric', 'thin_plate', 'linear', 'inverse_multiquadric', 'gaussian'],
        'default': RBF_FUNCTION,
        'description': 'RBF 插值的核函数类型'
    },
    'RBF_SMOOTH': {
        'label': 'RBF平滑度',
        'type': 'number',
        'group': '插值参数',
        'min': 0,
        'max': 10,
        'step': 0.01,
        'default': RBF_SMOOTH,
        'description': 'RBF 插值的平滑参数，越大越平滑'
    },
    'INTERPOLATION_METHOD': {
        'label': '插值方法',
        'type': 'enum',
        'group': '插值参数',
        'options': ['rbf', 'kriging'],
        'default': INTERPOLATION_METHOD,
        'description': '插值方法：rbf（径向基函数）或 kriging（克里金）'
    },
    'KRIGING_VARIOGRAM': {
        'label': '克里金变异函数',
        'type': 'enum',
        'group': '插值参数',
        'options': ['spherical', 'exponential', 'gaussian', 'linear', 'power'],
        'default': KRIGING_VARIOGRAM_MODEL,
        'description': '克里金插值的变异函数模型'
    },
}

# 参数存储目录名（位于 uploads/{session_id}/ 下）
SESSION_PARAMS_FILENAME = 'user_params.json'

# ==================== 克里金分析配置（曲面分析） ====================
# 默认变异函数模型
KRIGING_DEFAULT_VARIOGRAM = 'spherical'

# 网格分辨率（None 表示从 GRID_RESOLUTION 读取）
KRIGING_GRID_RES = None

# 控制点数量低于此值时给出警告
KRIGING_MIN_POINTS_WARN = 10

# 热力图配色
KRIGING_VALUE_CMAP = 'viridis'
KRIGING_VARIANCE_CMAP = 'hot_r'

# 缓存类型标识
KRIGING_SURFACE_CACHE_TYPE = 'kriging_surface'

# ==================== 数据说明页面配置 ====================
ENABLE_DATA_REPORT = True
ANALYSIS_CACHE_TYPE = 'analysis'
REPORT_SCATTER_COLOR = '#1565C0'
REPORT_HISTOGRAM_COLOR = '#2E7D32'
REPORT_DIFF_COLOR = '#F57C00'
REPORT_SCATTER_MAX_POINTS = 500

# ==================== 克里金参数分析配置 ====================
# 候选变异函数模型列表
KRIGING_OPTIMIZE_VARIOGRAMS = ['spherical', 'exponential', 'gaussian', 'linear', 'power']

# 克里金建模默认变异函数模型
KRIGING_MODEL_DEFAULT_VARIOGRAM = 'spherical'
# 前端可选的克里金建模变异函数模型
KRIGING_MODEL_VARIOGRAM_OPTIONS = ['spherical', 'exponential', 'gaussian', 'linear', 'power']

# 参数分析缓存类型
KRIGING_ANALYSIS_CACHE_TYPE = 'kriging_analysis'

# RMSE 参考标准（复用 RBF 的标准）
KRIGING_RMSE_STANDARDS = [
    {'max': 5,   'label': '优秀', 'suggestion': '直接采用',           'color': '#2E7D32'},
    {'max': 15,  'label': '良好', 'suggestion': '可用于宏观展示',     'color': '#1565C0'},
    {'max': 30,  'label': '一般', 'suggestion': '需检查数据质量',     'color': '#F57C00'},
    {'max': 99999, 'label': '差', 'suggestion': '数据可能有问题，或控制点分布太稀疏', 'color': '#C62828'},
]

# 块基比（Nugget/Sill Ratio）参考标准
KRIGING_NUGGET_RATIO_STANDARDS = [
    {'max': 0.25,   'label': '强空间相关性', 'description': '块金效应弱，空间变异主要由结构性因素引起', 'color': '#2E7D32'},
    {'max': 0.75,   'label': '中等空间相关性', 'description': '空间变异由结构性因素和随机因素共同引起', 'color': '#F57C00'},
    {'max': 99999,  'label': '弱空间相关性', 'description': '块金效应强，接近纯块金效应，空间自相关性弱', 'color': '#C62828'},
]

# R² 参考标准（R² 越高越好，使用 min 阈值）
KRIGING_R2_STANDARDS = [
    {'min': 0.9,   'label': '优秀', 'description': '变异函数模型拟合效果很好', 'color': '#2E7D32'},
    {'min': 0.7,   'label': '良好', 'description': '变异函数模型拟合效果较好', 'color': '#1565C0'},
    {'min': 0.5,   'label': '一般', 'description': '变异函数模型拟合效果一般', 'color': '#F57C00'},
    {'min': -99999, 'label': '差', 'description': '变异函数模型拟合效果差，需考虑更换模型或检查数据', 'color': '#C62828'},
]

# ==================== RBF 参数分析配置 ====================
# 是否启用 RBF 参数分析功能
ENABLE_RBF_ANALYSIS = True

# 候选核函数列表
RBF_OPTIMIZE_FUNCTIONS = [
    'multiquadric',
    'thin_plate',
    'linear',
    'inverse_multiquadric',
    'gaussian'
]

# 候选 smooth 值
RBF_OPTIMIZE_SMOOTHS = [0, 0.0001, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0]

# 候选 epsilon 值（仅 gaussian 使用）
RBF_OPTIMIZE_EPSILONS = [0.1, 0.5, 1.0, 2.0]

# 参数分析缓存类型
RBF_ANALYSIS_CACHE_TYPE = 'rbf_analysis'

# ==================== RBF/Kriging 综合评分配置 ====================
# 综合评分权重（归一化加权：综合分 = w_rmse×norm_rmse + w_mae×norm_mae + w_max×norm_max_err）
# 权重之和应为 1.0
SCORE_WEIGHT_RMSE = 0.5       # RMSE 权重：对大偏差敏感（平方惩罚），地质建模关键
SCORE_WEIGHT_MAE = 0.3        # MAE 权重：反映"典型误差"水平
SCORE_WEIGHT_MAX_ERROR = 0.2  # 最大误差权重：防止"平均好但某处极差"
# 温和截尾分位数：归一化前将 max_error 截尾到此分位数，防止极端值扭曲评分
SCORE_WINSORIZE_PERCENTILE = 95

# RMSE 参考标准
RBF_RMSE_STANDARDS = [
    {'max': 5,   'label': '优秀', 'suggestion': '直接采用',           'color': '#2E7D32'},
    {'max': 15,  'label': '良好', 'suggestion': '可用于宏观展示',     'color': '#1565C0'},
    {'max': 30,  'label': '一般', 'suggestion': '需检查数据质量',     'color': '#F57C00'},
    {'max': 99999, 'label': '差', 'suggestion': '数据可能有问题，或控制点分布太稀疏', 'color': '#C62828'},
]

# 综合评分参考标准（composite_score 为归一化加权值，1=最优，0=最差）
RBF_COMPOSITE_STANDARDS = [
    {'min': 0.90, 'label': '优秀', 'suggestion': '各指标均表现优异，直接采用', 'color': '#2E7D32'},
    {'min': 0.75, 'label': '良好', 'suggestion': '综合表现较好，可用于生产',   'color': '#1565C0'},
    {'min': 0.50, 'label': '一般', 'suggestion': '部分指标偏高，建议检查',     'color': '#F57C00'},
    {'min': 0.00, 'label': '差',   'suggestion': '多项指标均不理想，需排查数据或调整参数', 'color': '#C62828'},
]

# ==================== 模型质量评估配置 ====================
# 是否启用模型质量评估
ENABLE_QUALITY_CHECK = True

# 缓存类型
QUALITY_CHECK_CACHE_TYPE = 'quality_check'

# 层间关系检查
QUALITY_INTERSECTION_THRESHOLD = 0.5   # 穿层判定最小差值（米）
QUALITY_INTERSECTION_WARN_RATIO = 0.01 # 穿层比例超过 1% 警告
QUALITY_INTERSECTION_FAIL_RATIO = 0.05 # 穿层比例超过 5% 不合格

# 厚度变化检查
QUALITY_THICKNESS_MAX_GRADIENT = 0.5   # 允许的最大厚度变化率（米/米）
QUALITY_THICKNESS_MIN = 0.5            # 最小厚度（米）
QUALITY_THICKNESS_MAX = 200.0          # 最大厚度（米）

# 尖灭识别
QUALITY_PINCHOUT_MIN_THICKNESS = 1.0   # 尖灭判定厚度阈值（米）
QUALITY_PINCHOUT_REASONABLE_RATIO = 0.20 # 尖灭比例超过 20% 算合理尖灭

# 综合评分权重
QUALITY_SCORE_PENALTY_INTERSECTION = 30   # 穿层扣分
QUALITY_SCORE_PENALTY_THICKNESS = 20      # 厚度异常扣分
QUALITY_SCORE_PENALTY_PINCHOUT = 10       # 尖灭异常扣分

# 综合评级阈值
QUALITY_GRADE_EXCELLENT = 90
QUALITY_GRADE_GOOD = 75
QUALITY_GRADE_FAIR = 60