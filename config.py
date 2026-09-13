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

# ==================== 地图与坐标转换 ====================
PROJECTION_ZONE = 40  # 投影带号
ZJ_TIANDITU_HOST = 'api.tianditu.gov.cn'
ZJ_TIANDITU_KEY = os.environ.get('ZJ_TIANDITU_KEY', 'bfc9dea0d2d01bf8b47ded0136142bf0')
TIANDITU_PROJECTION = 'w'

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
QWEN_MODEL = 'qwen-image-2.0-pro'
# 个人API地址
# QWEN_API_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
# Token Plan地址
QWEN_API_URL = 'https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'

# 颜色映射（用于AI识别）
COLOR_MAP = {}

AI_REFERENCE_IMGS = [1, 4, 5]   # 对应：图1(main_view)、图4(iso_view)、图5(north_south_view)

AI_GEOMODEL_PROMPT = """
请根据以下3张同一地质体的不同视角参考图，生成一张统一、逼真的三维地质结构模型渲染图。

【坐标约定】
本模型采用地质行业标准坐标：
- X 轴：东向
- Y 轴：北向
- Z 轴：高程（向上为正）

【重要】每张图的左上角标注有原始序号，请严格按以下说明理解（注意：本次仅提供3张图，编号不连续）：

- 图1（立体全景视图·西北俯瞰）—— 站在矿体西北方向的高处俯视。展示地质体的整体三维形态、走向和倾伏方向，作为几何形态的**主参考**。

- 图4（标准等轴测视图·45°斜俯视）—— 从西北方向以45°俯角观察，三个坐标轴比例接近1:1:1。作为**空间比例锚定参考**，用于校准模型的纵横比和纵深尺度。

- 图5（立体视图·东南方向俯瞰）—— 从东南方向观察，与图1形成对侧视角。用于补充地质体东南侧的形态，确保模型**背面结构完整、无遮挡缺失**。

【关键说明】
- 上述3张图是同一个地质体的不同视角，请综合理解其三维空间结构，不要将它们视为多个独立物体。
- 参考图左上角的"图N"是编号标识，请在生成结果中忽略这些序号文字，只关注地质体的形态和颜色。
- 图1和图5互为反向补充，共同约束地质体的完整轮廓。

【参考图的性质说明】
上述参考图是**基于有限钻孔数据通过数学插值生成的初步模型**，具有以下特点：
- 其边界受钻孔控制点的空间分布范围限制，呈现为"被凸包裁剪"的形态，边缘生硬。
- 部分区域由于缺乏钻孔控制，会出现"凹陷""空洞"或"突然中断"。
- 这些不完整的边界**不代表真实地质体的实际边界**，仅代表"钻孔控制范围内的已知部分"。

【您的任务——科学化的地质填充】
请以参考图为骨架约束，运用地质学常识进行科学化的推断与填充，生成一个相对完整、符合地质规律的三维地质体：

1. **保持钻孔控制区的形态不变**：参考图中由钻孔数据明确约束的形态、厚度、倾角必须严格保留。

2. **填充缺失区域**：
   - 地层延续性：同一岩性在空间上应保持连续。
   - 厚度渐变：地层厚度变化应平滑过渡。
   - 倾角合理：保持在合理范围（0°~60°）。
   - 边界外延：地质体边缘应自然延伸至模型边界。

3. **合理外推与尖灭**：
   - 延续性强的岩性（基岩、厚层砂岩）应稳定延伸至模型边界。
   - 透镜状、脉状矿体可合理"尖灭"，但应有渐变过渡。

4. **整体协调性**：填充后的地质体应像一个"完整的地质块体"，各岩性之间过渡自然，无突兀断裂、无悬空结构。

【岩性纹理逼真度要求——重要】
不同岩性应呈现**符合地质学常识的岩石质感**，避免所有岩性都是"一坨彩色黏土"。请根据岩性名称推断其应有的真实质感，**避免所有岩性使用同一种"塑料感"材质**。

【深度与高程信息】
- Z 轴表示高程（单位：米），数值越大表示位置越浅，数值越小表示位置越深。
- 图片右侧有灰度标尺条（深度标尺），亮色代表浅部，暗色代表深部。
- 请保持参考图所示的高程比例，不要过度压缩或拉伸垂直方向。

【颜色与岩性对应关系】
{color_relations}

【生成要求】
1. **岩石纹理逼真，各岩性呈现其独特的地质质感**（详见上方"岩性纹理逼真度要求"）
2. 各岩性严格使用上述对应颜色表达，颜色饱和度适中
3. 保持图1的整体三维形态、图4的空间比例、图5的东南侧结构
4. 图1和图5互为反向补充，确保地质体南北两侧结构完整
5. 地质体应呈现为完整连续的地质块体，边缘自然过渡
6. 各岩性之间过渡自然，层位连续，无突兀断裂或空洞
7. 保持参考图所示的高程比例，不要过度压缩或拉伸垂直方向
8. 光照自然，具有地质剖面的专业感，避免过度反光或卡通化
9. 背景为纯白色，无任何文字、标注或坐标系
10. 图像风格为科学分析+符合地质真实的图片
11. 输出为单张高质量的三维地质结构渲染图，分辨率不低于1024x1024
"""