# -*- coding: utf-8 -*-
"""局部特写裁剪支路（2026-09-30 特征尺度修复；同日扩后贴袋）。

诊断（三连实验，决策日志 §九）：整照经 VLM 端点输入降采样后腰头区
（整照里仅 ~200px 高）细节低于模型可分辨阈值——S2 整轮不报
waistband_type 落引擎默认、带判据定向问仍幻觉误读；同一张照裁腰头区
放大 2× 再喂，同模型立刻判对（straight→curved conf 0.9，证据正确）。
后贴袋袋底同陷阱（整照里袋底尖仅十几像素，钝角浅尖盾形被判
rectangle，2026-09-30 实测），裁块机制照方抓药扩 make_back_pocket_crops。

修法：S2 摄入（及对应部位组聚焦复查）时自动裁特征区放大，作**辅助图**
附进同一次 VLM 调用——只喂模型细看，不进照片指纹（vlm_cache 记账按
用户原图）、不进探针/几何。姿态假设 = 平铺、腰在上（用户上传惯例；
腰在下的构图裁不到，判据退回整照读法，二期可加方向检测）。
Pillow 缺失、解码失败、任何异常一律静默降级为无辅助图（零打扰：
辅助图失败绝不拦主提取）。
"""
from __future__ import annotations

from pathlib import Path

try:                      # Pillow 是 [agent] 可选依赖；缺了就不附辅助图
    from PIL import Image, ImageOps
    _PIL_OK = True
except ImportError:       # pragma: no cover - 环境无 Pillow 时
    Image = ImageOps = None
    _PIL_OK = False

# 裁剪框（占原图比例）：
#   腰头 = 上带区：顶部 42% 高、两侧各收 6% 宽（去床单背景）
_BOX = (0.06, 0.0, 0.94, 0.42)
#   后贴袋 = 育克之下、裆部之上的中带（平铺背面照双袋惯例落位；框取
#   宽松——裁多由模型按画面自辨，裁不到时判据退回整照读法兜底）
_POCKET_BOX = (0.05, 0.24, 0.95, 0.64)
#   前袋口 = 腰头下缘到臀线的中带、整幅宽（两侧袋口都进框，模型读任一
#   侧；2026-10-02 特征尺度第三贴——整照上袋口曲线仅几十像素，VLM 分
#   不清上端切向，bulge/tangent 误判的根因与腰头/后贴袋同族）
_MOUTH_BOX = (0.06, 0.12, 0.94, 0.56)
# 长边放大目标：小图 ×2（端点降采样后仍比整照里的特征区大 ~2 倍），
# 大图不再放大（端点反正要压，省字节）
_UPSCALE_LONG = 1200


def _crop_one(src: str, out_dir: str, name: str, box: tuple) -> str | None:
    """单张裁剪（box=占原图比例 (x0,y0,x1,y1)）：成功返回产物路径，
    任何失败返回 None。产物名 = {name}.jpg，调用方自保证不重名。"""
    if not _PIL_OK:
        return None
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)       # 手机照 EXIF 转向
            w, h = im.size
            x0, y0, x1, y1 = box
            box_px = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
            if box_px[2] - box_px[0] < 40 or box_px[3] - box_px[1] < 40:
                return None                        # 图太小，裁了也没意义
            region = im.crop(box_px)
            long_edge = max(region.size)
            scale = 2 if long_edge < _UPSCALE_LONG else 1
            if scale > 1:
                region = region.resize(
                    (region.width * scale, region.height * scale),
                    Image.LANCZOS)
            out = Path(out_dir) / f"{name}.jpg"
            region.convert("RGB").save(out, "JPEG", quality=90)
            return str(out)
    except Exception:                              # 解码失败/损坏文件等
        return None


def make_waistband_crops(photos, photo_meta, out_dir):
    """从首张正面 + 首张背面照裁腰头区放大图。

    photos: 用户原图路径列表；photo_meta: [{category, note}]（可 None/
    缺齐——缺 meta 时首图按正面对待，且只裁一张防猜错）。返回
    (crop_paths, crop_metas, notes)：metas 与 paths 对齐、category=other
    （note 向模型说明来源与用途，走 build_prompt 照片清单既有渲染）；
    notes 为披露文案（进 ExtractResult.crop_notes）。全失败返回空三元组。
    """
    paths = [str(p) for p in (photos or []) if p]
    if not paths:
        return [], [], []
    metas = list(photo_meta or [])
    targets: list[tuple[str, str]] = []            # (路径, 正面|背面)
    first_front = first_back = None
    for i, p in enumerate(paths):
        cat = str((metas[i] or {}).get("category") or "").strip() \
            if i < len(metas) and metas[i] else ""
        if cat == "front" and first_front is None:
            first_front = p
        elif cat == "back" and first_back is None:
            first_back = p
    if first_front is None and first_back is None:
        first_front = paths[0]                     # 无 meta：首图按正面
    if first_front is not None:
        targets.append((first_front, "正面"))
    if first_back is not None:
        targets.append((first_back, "背面"))

    crop_paths, crop_metas, notes = [], [], []
    for i, (src, side) in enumerate(targets):
        out = _crop_one(src, out_dir, f"wb_crop_{i}",
                        _BOX)
        if out is None:
            continue
        crop_paths.append(out)
        crop_metas.append({
            "category": "other",
            "note": f"工程自动辅助图：{side}照的腰头区放大裁剪（非用户上传），"
                    "专用于细看腰头形态（waistband_type）与后腰细节",
        })
    if crop_paths:
        notes.append(f"腰头放大辅助图 {len(crop_paths)} 张已附"
                     "（首张正面/背面照自动裁剪，特征尺度修复）")
    return crop_paths, crop_metas, notes


def make_back_pocket_crops(photos, photo_meta, out_dir):
    """从首张背面照裁后贴袋区放大图（back_patch_shape 特征尺度修复）。

    选图口径比腰头保守：只认 meta 明示的 back 照；无 meta 且整包只有
    一张照时也裁（分面交给模型按画面自辨）；多照无 meta 不猜——后贴袋
    在正面照上不存在，裁错面是主动错误证据。返回同 make_waistband_crops。
    """
    paths = [str(p) for p in (photos or []) if p]
    if not paths:
        return [], [], []
    metas = list(photo_meta or [])
    src = None
    for i, p in enumerate(paths):
        if i < len(metas) and metas[i] and \
                str((metas[i] or {}).get("category") or "").strip() == "back":
            src = p
            break
    if src is None and len(paths) == 1:
        src = paths[0]
    if src is None:
        return [], [], []
    out = _crop_one(src, out_dir, "bp_crop_back", _POCKET_BOX)
    if out is None:
        return [], [], []
    return ([out],
            [{"category": "other",
              "note": "工程自动辅助图：背面照的两侧后贴袋区放大裁剪"
                      "（非用户上传），专用于细看后贴袋形状"
                      "（back_patch_shape）与袋底细节"}],
            ["后贴袋放大辅助图 1 张已附（背面照自动裁剪，特征尺度修复）"])


def make_front_pocket_crops(photos, photo_meta, out_dir):
    """从首张正面照裁前袋口区放大图（2026-10-02 特征尺度第三贴）。

    整照上袋口曲线经端点降采样仅几十像素，三段判读（bulge/tangent 判型：
    看两端末段直不直）低于模型可分辨阈值——判据已教而放大不足，模型
    「看了但分不清」（实照判 bulge conf 0.65 vs 用户/像素定标 tangent）。
    选图口径同 make_back_pocket_crops（保守）：只认 meta 明示的 front
    照；无 meta 且单照也裁（分面模型自辨）；多照无 meta 不猜——前袋口
    在背面照上不存在，裁错面是主动错误证据。框取整幅宽（两侧袋口都
    进框）。返回同 make_waistband_crops。
    """
    paths = [str(p) for p in (photos or []) if p]
    if not paths:
        return [], [], []
    metas = list(photo_meta or [])
    src = None
    for i, p in enumerate(paths):
        if i < len(metas) and metas[i] and \
                str((metas[i] or {}).get("category") or "").strip() == "front":
            src = p
            break
    if src is None and len(paths) == 1:
        src = paths[0]
    if src is None:
        return [], [], []
    out = _crop_one(src, out_dir, "fp_crop_front", _MOUTH_BOX)
    if out is None:
        return [], [], []
    return ([out],
            [{"category": "other",
              "note": "工程自动辅助图：正面照的两侧前袋口区放大裁剪"
                      "（非用户上传），专用于细读袋口三段（上段/中段/下段）"
                      "判型（front_pocket_mouth_mode）、弧深与小表袋细节"}],
            ["前袋口放大辅助图 1 张已附（正面照自动裁剪，特征尺度修复）"])
