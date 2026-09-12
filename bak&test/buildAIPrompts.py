#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从钻孔数据 Excel 文件中提取颜色-岩性映射，生成完整的 AI 提示词。
用法:
    python build_prompt.py -i 钻孔数据.xlsx [-o prompt.txt]

如果不指定 -o，则提示词直接打印到控制台。
"""

import argparse
import pandas as pd
import sys

# ==================== 颜色映射提取（复用 processors.py 逻辑） ====================
def get_color_map_from_dataframe(litho_df):
    """
    从岩性 DataFrame 中提取颜色映射，去重并合并同名岩性。
    返回: dict {颜色值: 岩性名称}，多个岩性用顿号连接。
    """
    color_map = {}
    for _, row in litho_df.iterrows():
        color = str(row['建模颜色']).strip()
        lith_name = str(row['岩性描述']).strip()
        # 跳过无效值
        if not color or not lith_name:
            continue
        if color.lower() in ['nan', 'none', ''] or lith_name.lower() in ['nan', 'none', '']:
            continue
        # 合并相同颜色
        if color in color_map:
            existing = color_map[color]
            if lith_name not in existing:
                color_map[color] = existing + '、' + lith_name
        else:
            color_map[color] = lith_name
    return color_map


def build_prompt_from_excel(file_path):
    """
    读取 Excel 文件，提取颜色映射，构建完整的 AI 提示词。
    返回提示词字符串。
    """
    # 读取三个表
    try:
        loc_df = pd.read_excel(file_path, sheet_name='定位表')
        survey_df = pd.read_excel(file_path, sheet_name='测斜表')
        litho_df = pd.read_excel(file_path, sheet_name='岩性表')
    except Exception as e:
        print(f"读取 Excel 失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 提取颜色映射
    color_map = get_color_map_from_dataframe(litho_df)
    if not color_map:
        print("警告: 未提取到任何有效颜色映射，将使用默认描述。", file=sys.stderr)

    # 构建颜色对应关系描述
    if color_map:
        color_lines = []
        for color, names in color_map.items():
            color_lines.append(f'- {color}: {names}')
        color_relations = '\n'.join(color_lines)
    else:
        color_relations = "各岩性用对应颜色表达（请根据实际数据补充颜色-岩性对照表）。"

    # 统计信息（供参考）
    hole_count = len(loc_df['钻孔编号'].unique()) if '钻孔编号' in loc_df.columns else len(loc_df)
    litho_types = len(litho_df['岩性描述'].unique()) if '岩性描述' in litho_df.columns else 0

    # 构建完整提示词
    prompt = f"""
基于参考图的几何结构和材质细节，生成一张逼真的地质三维模型渲染图。
严格遵循以下颜色与岩性对应关系：
{color_relations}

要求：
1. 保持参考图的断层形态和层位关系、层位厚度比例不变
2. 应用参考图的岩石纹理和光照效果，地质体纹理逼真，岩石质感真实
3. 各岩性用对应颜色准确表达，生成的背景为白色
4. 生成高质量的三维地质结构渲染图
5. 生成的图添加刻度尺表示深度信息
"""
    return prompt


# ==================== 命令行入口 ====================
def main():
    parser = argparse.ArgumentParser(description='从钻孔 Excel 生成 AI 提示词')
    parser.add_argument('-i', '--input', required=True, help='钻孔数据 Excel 文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（不指定则打印到控制台）')
    args = parser.parse_args()

    prompt = build_prompt_from_excel(args.input)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"提示词已保存至: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("生成的完整 AI 提示词：")
        print("=" * 60)
        print(prompt)


if __name__ == '__main__':
    main()