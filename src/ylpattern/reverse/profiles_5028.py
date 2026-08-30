"""5028 档案：九分 4 公分脚边前袋贴（6 码推码 S~3XL，基码 M）。

与 5015 的差异（.doc/工厂DXF逆向解析.md §3）：
- 小表袋是命名块 ``火机袋``（5015 是匿名子片）；
- 匿名块 x5 子片语义未知（191x141 / 160x97 / 156x52 细条 / 102x157 /
  102x102）——不入测量，细条（长短边比 ≥3）标 unknown_strip 告警；
- 多码：档差提取走 grade.py（逐码独立测量再差分，禁顶点索引对应）。
"""

from __future__ import annotations

from .profiles import (StyleProfile, SubSpec, by_name_blocks, register,
                       _back_body_check, _near_square_with_arc,
                       _waistband_check, _yoke_check)

PROFILE_5028 = StyleProfile(
    key="5028",
    description="九分 4 公分脚边前袋贴（6 码推码）",
    block_map={
        "前": (SubSpec("front_body", "前片大片"),),
        "机头": (SubSpec("back_body", "后片（藏在机头块，净面积大者）",
                        check=_back_body_check),
                 SubSpec("yoke", "真机头", check=_yoke_check)),
        "腰": (SubSpec("waistband", "腰头条带（qty2，净 772x101 可左右两根）",
                      check=_waistband_check),),
        "前代": (SubSpec("fused_pocket", "袋贴+袋身融合方片",
                        check=_near_square_with_arc),),
        "火机袋": (SubSpec("watch_pocket", "小表袋（命名块）"),),
        "双排": (by_name_blocks()[0],),
        "单排": (by_name_blocks()[1],),
        "裤耳": (by_name_blocks()[2],),
    },
    anonymous=(),            # x5 子片语义未知：全部不指派（细条另标 unknown_strip）
    strip_aspect=3.0,
    notes=("5028 匿名 x5 子片语义未知，不入测量/选项",),
)

register(PROFILE_5028)
