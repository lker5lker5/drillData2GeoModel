
def call_qwen_api_for_modeling(image_paths, color_map=None, api_key=QWEN_API_KEY):
    """
    调用Qwen API生成AI建模图（返回n张）
    使用 qwen-image-3.0-pro 模型
    传入侧视图和前视图作为参考图
    """
    if not api_key:
        return None, "!!! API密钥未配置，请设置QWEN_API_KEY环境变量"
    
    # 设置API密钥
    dashscope.api_key = api_key
    
    # 检查文件是否存在
    valid_paths = []
    for path in image_paths:
        if os.path.exists(path):
            valid_paths.append(path)
        else:
            print(f"!!! 图片不存在: {path}")
    
    if len(valid_paths) < 2:
        return None, f"!!! 至少需要2张参考图，当前只有 {len(valid_paths)} 张"
    
    # ========== 从color_map构建颜色描述（去重） ==========
    if color_map and isinstance(color_map, dict):
        color_groups = {}
        for color, names in color_map.items():
            if color not in color_groups:
                color_groups[color] = set()
            if '、' in names:
                for name in names.split('、'):
                    color_groups[color].add(name.strip())
            else:
                color_groups[color].add(names.strip())
        
        color_relations = []
        for color, name_set in color_groups.items():
            name_list = sorted(list(name_set))
            name_str = '/'.join(name_list)
            color_relations.append(f'{color} 对应 {name_str}')
        color_relations_text = '；'.join(color_relations)
    else:
        color_relations_text = '各岩性用对应颜色表达'
    
    print(f"==> 颜色映射: {color_relations_text}")
    
    # ========== 构建提示词 ==========
    prompt_text = f"""
基于参考图的几何结构和材质细节，生成一张逼真的地质三维模型渲染图。
严格遵循以下颜色与岩性对应关系：
{color_relations_text}

要求：
1. 保持参考图的断层形态和层位关系、层位厚度比例不变
2. 应用参考图的岩石纹理和光照效果，地质体纹理逼真，岩石质感真实
3. 各岩性用对应颜色准确表达，生成的背景为白色
4. 生成高质量的三维地质结构渲染图
"""
    
    print(f"==> 提示词: {prompt_text}")
    
    # ========== 构建消息内容 ==========
    content_list = []
    for path in valid_paths:
        with open(path, 'rb') as f:
            base64_data = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(path)[-1].lower()
            mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png"
            img_b64 = f"data:{mime_type};base64,{base64_data}"
            content_list.append({"image": img_b64})
    
    content_list.append({"text": prompt_text})
    
    messages = [
        {
            "role": "user",
            "content": content_list
        }
    ]
    
    print(f"==> 正在调用 {QWEN_MODEL} 生成地质模型...")
    
    try:
        response = MultiModalConversation.call(
            model=QWEN_MODEL,
            messages=messages,
            result_format='message',
            size='1024*1024',
            watermark=False,
            prompt_extend=True,
            n=2  # 生成n张图片
        )
        
        print(f"==> Qwen响应状态: {response.status_code}")
        
        if response.status_code == 200:
            output = response.output.choices[0].message.content
            image_urls = []
            for item in output:
                if 'image' in item:
                    image_urls.append(item['image'])
                    print(f"==> 生成图片URL: {item['image']}")
                elif 'text' in item:
                    print(f"==> 模型回复: {item['text']}")
            
            if image_urls:
                return image_urls, None  # 返回列表
            else:
                return None, "!!! API返回格式异常: 未找到图片"
        else:
            return None, f"!!! API调用失败 (状态码{response.status_code}): {response.message}"
            
    except Exception as e:
        return None, f"!!! API调用异常: {str(e)}"