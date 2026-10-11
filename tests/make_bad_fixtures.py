# tests/fixtures/make_bad_fixtures.py
"""
生成回归测试用的坏数据样本。
用法：python3 tests/fixtures/make_bad_fixtures.py
输出：与本脚本同目录下的 bad_*.xlsx
"""
from pathlib import Path
from openpyxl import Workbook

OUT_DIR = Path(__file__).parent

# 约定的三表列名（与项目说明文档 v2 §2.1 一致）
LOC_HEADERS = ["钻孔编号", "开孔坐标N", "开孔坐标E", "开孔高程R"]
INC_HEADERS = ["钻孔编号", "侧斜深度", "倾角", "方位角"]
LIT_HEADERS = ["钻孔编号", "上层位长度起始刻度", "下层位长度起始刻度", "岩性描述", "建模颜色"]

# 最小有效数据，作为坏数据的底子
VALID_LOC = [
    LOC_HEADERS,
    ["ZK001", 1000.0, 2000.0, 500.0],
    ["ZK002", 1100.0, 2100.0, 510.0],
]
VALID_INC = [
    INC_HEADERS,
    ["ZK001", 0.0, 90.0, 0.0],
    ["ZK002", 0.0, 90.0, 0.0],
]
VALID_LIT = [
    LIT_HEADERS,
    ["ZK001", 0.0, 10.0, "砂岩", "#FF0000"],
    ["ZK001", 10.0, 20.0, "泥岩", "#00FF00"],
    ["ZK002", 0.0, 15.0, "砂岩", "#FF0000"],
]


def write_wb(path, sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    print(f"  -> {path.name}")


def main():
    print("生成坏数据样本：")

    # 1. 缺“岩性表”
    write_wb(OUT_DIR / "bad_missing_lithology.xlsx", {
        "定位表": VALID_LOC,
        "测斜表": VALID_INC,
    })

    # 2. 缺“定位表”
    write_wb(OUT_DIR / "bad_missing_location.xlsx", {
        "测斜表": VALID_INC,
        "岩性表": VALID_LIT,
    })

    # 3. 定位表列名错误
    bad_loc = [["钻孔编号", "X坐标", "Y坐标", "高程"]] + VALID_LOC[1:]
    write_wb(OUT_DIR / "bad_wrong_columns.xlsx", {
        "定位表": bad_loc,
        "测斜表": VALID_INC,
        "岩性表": VALID_LIT,
    })

    # 4. 只有表头无数据行
    write_wb(OUT_DIR / "bad_empty_rows.xlsx", {
        "定位表": [LOC_HEADERS],
        "测斜表": [INC_HEADERS],
        "岩性表": [LIT_HEADERS],
    })

    # 5. 建模颜色非法（"red" 而非 #RRGGBB）
    bad_lit = [LIT_HEADERS] + [r[:-1] + ["red"] for r in VALID_LIT[1:]]
    write_wb(OUT_DIR / "bad_color.xlsx", {
        "定位表": VALID_LOC,
        "测斜表": VALID_INC,
        "岩性表": bad_lit,
    })

    print("完成。")


if __name__ == "__main__":
    main()
