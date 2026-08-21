"""裁片收集：按固定顺序构建全部已开启裁片（推码方案步 2）。

api/cli 原各自维护一份 ~100 行平行收集分支（api.py / cli.py 逐片 if
build），推码多码编排（步 4）第三次复用同一逻辑，收敛于此。flows 层
无输出职责：**不写任何文件、不 import exporters**（分层红线）。

固定顺序（与原 api/cli 逐分支一致，保证 DXF Category 序号稳定）：
waistband / back_yoke / front_facing|front_patch / front_pouch /
front_fly_single(+front_fly_double) / watch_pocket / belt_loop /
back_patch / front_piece / back_piece。

开关判定读 ctx.options（back_yoke / front_pocket_facing / front_patch /
front_pouch / fly_separate / watch_pocket / belt_loop / back_patch，与原
分支一致）；未开启的片不构建、记入 skips。门襟双排关闭只回单片。

接受的行为差异（相对原 api/cli）：原"仅设某片 SVG 时只 build 该片"的
惰性构建 -> 全收集（build 开销相对整版可忽略，裁片集合一致）。
"""

from __future__ import annotations

from ..draft import DraftContext
from ..pieces import PatternPiece


def collect_pieces(ctx: DraftContext) -> tuple[list[PatternPiece], list[str]]:
    """按固定顺序构建全部已开启裁片，返回 (裁片列表, 跳过说明列表)。"""
    o = ctx.options
    pieces: list[PatternPiece] = []
    skips: list[str] = []

    # 腰头：净样元素整版必有，无开关守卫
    from .waistband_flow import build_waistband
    piece, _wb = build_waistband(ctx)
    pieces.append(piece)

    if o.back_yoke:
        from .yoke_flow import build_yoke
        piece, _yk = build_yoke(ctx)
        pieces.append(piece)
    else:
        skips.append("机头裁片未开启（back_yoke=False），跳过 DXF 合集")
    if o.front_pocket_facing or o.front_patch:
        from .front_pocket_flow import build_front_pocket
        piece, _fp = build_front_pocket(ctx)
        pieces.append(piece)
    else:
        skips.append("前口袋裁片未开启（front_pocket_facing/front_patch "
                     "均为 False），跳过 DXF 合集")
    if o.front_pouch:
        from .front_pouch_flow import build_front_pouch
        piece, _ph = build_front_pouch(ctx)
        pieces.append(piece)
    else:
        skips.append("袋布裁片未开启（front_pouch=False），跳过 DXF 合集")
    if o.fly_separate:
        from .front_fly_flow import build_front_fly
        p_single, p_double, _ff = build_front_fly(ctx)
        pieces.append(p_single)
        if p_double is not None:      # 双排关闭（fly_sep_double=False）只回单片
            pieces.append(p_double)
    else:
        skips.append("门襟裁片未开启（fly_separate=False），跳过 DXF 合集")
    if o.watch_pocket:
        from .watch_pocket_flow import build_watch_pocket
        piece, _wp = build_watch_pocket(ctx)
        pieces.append(piece)
    else:
        skips.append("小表袋裁片未开启（watch_pocket=False），跳过 DXF 合集")
    if o.belt_loop:
        from .belt_loop_flow import build_belt_loop
        piece, _bl = build_belt_loop(ctx)
        pieces.append(piece)
    else:
        skips.append("裤耳裁片未开启（belt_loop=False），跳过 DXF 合集")
    if o.back_patch:
        from .back_patch_flow import build_back_patch
        piece, _bp = build_back_patch(ctx)
        pieces.append(piece)
    else:
        skips.append("后贴袋裁片未开启（back_patch=False），跳过 DXF 合集")

    # 前后大片：净样元素整版必有，无开关守卫
    from .front_piece_flow import build_front_piece
    piece, _fpc = build_front_piece(ctx)
    pieces.append(piece)
    from .back_piece_flow import build_back_piece
    piece, _bpc = build_back_piece(ctx)
    pieces.append(piece)
    return pieces, skips
