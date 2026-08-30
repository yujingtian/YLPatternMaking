"""5015 档案：五代款正常脚边（单码 S，无推码）。

实读块清单（.doc/工厂DXF逆向解析.md §3）：
- ``前`` -> 前片；``机头`` **x2 子片 = 后片(大) + 真机头(小)**——后片
  藏在机头块里是最大识别陷阱；``腰`` -> 腰头；``前代``（"前袋"误写）
  -> 袋贴+袋身融合方片，袋口弧 162.6mm 是片内层 8 线；
- ``双排``/``单排``/``裤耳`` 识别不入测量；
- 匿名块 x2 子片按面积降序 = 后贴袋 + 小表袋。
"""

from __future__ import annotations

from .profiles import (StyleProfile, SubSpec, by_name_blocks, register,
                       _back_body_check, _near_square_with_arc,
                       _waistband_check, _yoke_check)

PROFILE_5015 = StyleProfile(
    key="5015",
    description="五代款正常脚边（单码）",
    block_map={
        "前": (SubSpec("front_body", "前片大片"),),
        "机头": (SubSpec("back_body", "后片（藏在机头块，净面积大者）",
                        check=_back_body_check),
                 SubSpec("yoke", "真机头", check=_yoke_check)),
        "腰": (SubSpec("waistband", "腰头条带（可 1 环含左右两根）",
                      check=_waistband_check),),
        "前代": (SubSpec("fused_pocket", "袋贴+袋身融合方片",
                        check=_near_square_with_arc),),
        "双排": (by_name_blocks()[0],),
        "单排": (by_name_blocks()[1],),
        "裤耳": (by_name_blocks()[2],),
    },
    anonymous=(SubSpec("back_patch", "后贴袋（匿名面积大者）"),
               SubSpec("watch_pocket", "小表袋（匿名面积小者）")),
    notes=("5015 无推码：SAMPLE SIZE: S 单码，[size_run] 不发射",),
)

register(PROFILE_5015)
