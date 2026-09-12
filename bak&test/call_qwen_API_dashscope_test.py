import os
import base64
import requests
import dashscope
from dashscope import MultiModalConversation

# ================= 配置区域 =================
# 1. 设置 API Key
dashscope.api_key = 'sk-ws-H.EHLREYI.uU4p.MEUCIQDp5mlQ1Y3tkwcpYQbtAJPQHruRJXNS2142OOvjBbSWBQIgPWFhRKx_I_RdK7x1Ag035e5DzPAwv6xK15MmsxQ7C3o'

# 2. 选择一张最具代表性的参考图 (不要一次传5张)
# 建议选那张能看清整体结构的图
image_paths = [
    "/Users/kaner/comfy_project/scripts/geoModel/drill2ModelApp_DpSk/outputs/model_2607281559_unlabeled_side_view.png",
    "/Users/kaner/comfy_project/scripts/geoModel/drill2ModelApp_DpSk/outputs/model_2607281559_unlabeled_front_view.png"
]

# ✅ 修改点2：提示词中明确引用"图1"和"图2"，与数组顺序严格对应
prompt_text = """
基于图1的几何结构和图2的材质细节，生成一张逼真的地质三维模型渲染图。
严格遵循以下颜色与岩性对应关系：
- #9F7AEA (紫色): 矿化带
- #00FFCC (青绿色): 萤石矿体
- #8B7355 (棕色): 顶部普通岩土层
- #4A5568 (深灰色): 底部/主体普通岩土层
要求：保持图1的断层形态和层位关系不变，应用图2的岩石纹理和光照效果，背景为白色。
"""

def encode_image_to_base64(image_path):
    """将本地图片转为 Base64 Data URI 格式"""
    try:
        with open(image_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(image_path)[-1].lower()
            mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png"
            return f"data:{mime_type};base64,{base64_data}"
    except Exception as e:
        print(f"❌ 图片读取失败: {e}")
        return None

def call_geo_model():
    # 构建消息内容：按顺序添加2张参考图 + 提示词
    content_list = []
    for path in image_paths:
        if os.path.exists(path):
            img_b64 = encode_image_to_base64(path)
            if img_b64:
                content_list.append({"image": img_b64})
        else:
            print(f"⚠️ 警告: 图片 {path} 不存在，已跳过")

    # 提示词必须放在最后，且明确引用"图1""图2"
    content_list.append({"text": prompt_text})

    messages = [
        {
            "role": "user",
            "content": content_list
        }
    ]

    print("🚀 正在调用 qwen-image-2.0-pro 生成地质模型...")

    # ✅ 修改点3：使用 qwen-image-2.0-pro 模型
    response = MultiModalConversation.call(
        model='qwen-image-2.0-pro',
        messages=messages,
        result_format='message',
        size='1024*1024',       # 可指定输出尺寸，范围 512*512 ~ 2048*2048
        watermark=False,        # 不添加水印
        prompt_extend=True,      # 启用提示词优化
        n = 4
    )

    # 处理返回结果
    if response.status_code == 200:
        output = response.output.choices[0].message.content
        for i, item in enumerate(output):
            if 'image' in item:
                img_url = item['image']
                print(f"✅ 第{i+1}张图片URL: {img_url}")
                download_image(img_url, f"geological_model_result_{i+1}.png")
    else:
        print(f"❌ 调用失败: {response.code} - {response.message}")
        return None

def download_image(url, save_name):
    """下载图片到本地"""
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            with open(save_name, 'wb') as f:
                f.write(resp.content)
            print(f"💾 图片已保存至: {save_name}")
        else:
            print(f"❌ 下载失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ 下载出错: {e}")

if __name__ == '__main__':
    call_geo_model()