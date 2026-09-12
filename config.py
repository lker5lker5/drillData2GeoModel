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
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Excel模板文件名
TEMPLATE_FILE = os.path.join(TEMPLATE_FOLDER, 'drill_data_template.xlsx')

# 绘图配置
FIGURE_DPI = 300
FIGURE_WIDTH = 14
FIGURE_HEIGHT = 11

# 3D模型视角配置
VIEW_ELEVATION = 25
VIEW_AZIMUTH = -60

VIEW_CONFIGS = [
    {
        'order': 1,
        'name': 'main_view',
        'label': '立体全景视图（西北上空俯瞰）',
        'elev': 25,
        'azim': -60,
        'user_tip': '站在矿体西北方向的高处向下俯视。坐标约定：X=东、Y=北、Z=上。'
    },
    {
        'order': 2,
        'name': 'south_north_view',
        'label': '东西向剖面（从南侧向北看）',
        'elev': 0,
        'azim': 180,
        'user_tip': '站在矿体正南侧，水平向北看。屏幕左侧是西、右侧是东。观察东西方向的厚度变化。'
    },
    {
        'order': 3,
        'name': 'west_east_view',
        'label': '南北向剖面（从西侧向东看）',
        'elev': 0,
        'azim': 90,
        'user_tip': '站在矿体正西侧，水平向东看。屏幕左侧是南、右侧是北。观察南北方向的厚度变化。'
    },
    {
        'order': 4,
        'name': 'iso_view',
        'label': '标准等轴测视图（45°斜俯视）',
        'elev': 30,
        'azim': -45,
        'user_tip': '从西北方向以45°俯角观察，三个坐标轴比例接近1:1:1，透视失真最小。'
    },
    {
        'order': 5,
        'name': 'north_south_view',
        'label': '东西向剖面（从北侧向南看）',
        'elev': 0,
        'azim': 0,
        'user_tip': '站在矿体正北侧，水平向南看。屏幕左侧是东、右侧是西，与图2反向。'
    },
]

# 插值配置
GRID_RESOLUTION = 30
N_LAYERS = None # 12
RBF_SMOOTH = 1.0 # 2.0
RBF_FUNCTION = 'linear' # 'linear' 'gussian' 'multiquadric' 'inverse' 'thin_plate'

# 深度图配置
# LIGHT_DIRECTION = [-1, -1, 0.5]
# DEPTH_MAP_DPI = 300

# 服务器配置
HOST = '0.0.0.0'
PORT = 5001
DEBUG = True

# AI配置
QWEN_API_KEY = os.environ.get('QWEN_KEY')
QWEN_MODEL = 'qwen-image-3.0-pro'
# 个人API地址
# QWEN_API_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
# Token Plan地址
QWEN_API_URL = 'https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'

# 颜色映射（用于AI识别）
COLOR_MAP = {}

# ==================== 地图与坐标转换 ====================
PROJECTION_ZONE = 40  # 投影带号
ZJ_TIANDITU_HOST = 'api.tianditu.gov.cn'
ZJ_TIANDITU_KEY = os.environ.get('ZJ_TIANDITU_KEY', 'bfc9dea0d2d01bf8b47ded0136142bf0')
TIANDITU_PROJECTION = 'w'