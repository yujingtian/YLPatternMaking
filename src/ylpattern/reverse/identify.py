"""裁片识别：块名/匿名子片 -> 角色指派（.doc/工厂DXF逆向解析.md §3）。

两款特化策略：
- 命名块查档案 block_map；多子片块按**净面积降序**对位 SubSpec 序
  （机头块 = 后片 + 真机头）；
- 匿名块子片按面积降序对位档案 anonymous 序（5015：后贴袋 + 表袋）；
- 档案外的件名/未指派子片进 unassigned 清单；细条（档案给了阈值时）
  标 unknown_strip 告警，不入测量；
- 款号识别：头标 STYLE NAME 优先，块名款号段多数表决兜底。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import profiles_5015, profiles_5028   # noqa: F401  模块级注册副作用
from .errors import ReverseError
from .model import FactoryDoc, SubPiece
from .profiles import ROLE_IDS, StyleProfile, get_profile, known_profiles

# 测量关键角色（缺失时逐码告警；measure 会因缺片失败，这里先给提示）
_CRITICAL = ("front_body", "back_body", "yoke", "waistband", "fused_pocket")

_STYLE_DIGITS = re.compile(r"(\d{3,})")      # 款号数字段（3 位起）


@dataclass
class RoleReport:
    """逐码角色指派结果 + 告警/未指派清单。"""

    profile: StyleProfile
    by_size: dict[str, dict[str, SubPiece]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)          # "[码] ..." 前缀
    unassigned: list[tuple[str, str]] = field(default_factory=list)

    def for_size(self, size: str) -> dict[str, SubPiece]:
        return self.by_size.get(size, {})

    def one(self, role: str, size: str) -> SubPiece:
        """取该码该角色的唯一子片；缺失抛 ReverseError（列已有角色）。"""
        sub = self.for_size(size).get(role)
        if sub is None:
            have = ", ".join(sorted(self.for_size(size)) or ("无",))
            raise ReverseError(
                f"码 {size} 缺角色 '{role}'（已有：{have}）——"
                "检查识别报告或用 --probe 看件清单")
        return sub

    def maybe(self, role: str, size: str) -> SubPiece | None:
        return self.for_size(size).get(role)


def detect_profile(doc: FactoryDoc, style: str = "auto") -> StyleProfile:
    """定档案：显式款号优先，auto 时头标 STYLE NAME -> 块名款号段多数。"""
    if style != "auto":
        profile = get_profile(style)
        if profile is None:
            raise ReverseError(
                f"未登记的款号 '{style}'（已登记：{', '.join(known_profiles())}）；"
                "新款先用 --probe 看件清单再补档案")
        return profile
    votes: dict[str, int] = {}
    m = _STYLE_DIGITS.search(doc.header.style_name or "")
    if m:
        votes[m.group(1)] = votes.get(m.group(1), 0) + 10     # 头标权重高
    for p in doc.pieces:
        seg = p.block_key.split(".", 1)[0]
        m = _STYLE_DIGITS.search(seg)
        if m:
            votes[m.group(1)] = votes.get(m.group(1), 0) + 1
    for key, _ in sorted(votes.items(), key=lambda kv: -kv[1]):
        profile = get_profile(key)
        if profile is not None:
            return profile
    seen = ", ".join(sorted({p.block_key.split(".", 1)[0] for p in doc.pieces}))
    raise ReverseError(
        f"无法识别款型（候选款号：{seen or '无'}；"
        f"已登记：{', '.join(known_profiles())}）。用 --probe 看件清单")


def assign_roles(doc: FactoryDoc, profile: StyleProfile) -> RoleReport:
    """逐码指派角色；计数失配按面积降序对位尽力而为并告警。"""
    report = RoleReport(profile=profile)
    for note in profile.notes:
        report.notes.append(f"[档案] {note}")
    for size in doc.sizes:
        pieces = doc.by_size(size)
        mapping = _assign_one_size(pieces, profile, size, report)
        report.by_size[size] = mapping
        missing = [r for r in _CRITICAL if r not in mapping]
        if missing:
            report.notes.append(
                f"[{size}] 缺测量关键角色：{', '.join(missing)}")
    return report


def _assign_one_size(pieces: list[SubPiece], profile: StyleProfile,
                     size: str, report: RoleReport) -> dict[str, SubPiece]:
    mapping: dict[str, SubPiece] = {}
    entries: list[tuple[str, tuple[SubSpec, ...]]] = \
        [(hint, specs) for hint, specs in profile.block_map.items()]
    if profile.anonymous:
        entries.append(("", profile.anonymous))

    for name_hint, specs in entries:
        subs = sorted((p for p in pieces if p.name_hint == name_hint),
                      key=lambda p: -p.net_or_gross().area())
        if not subs:
            roles = ", ".join(s.role for s in specs)
            report.notes.append(f"[{size}] 块 '{name_hint or '(匿名)'}' 缺失"
                                f"（角色：{roles}）")
            continue
        if len(subs) != len(specs):
            report.notes.append(
                f"[{size}] 块 '{name_hint or '(匿名)'}' 子片数 {len(subs)} "
                f"≠ 档案 {len(specs)}，按净面积降序对位尽力而为")
        for sub, spec in zip(subs, specs):
            mapping[spec.role] = sub
            score = spec.check(sub) if spec.check else 1.0
            if score < 0.5:
                report.notes.append(
                    f"[{size}] 角色 {spec.role}（{sub.block_key}#{sub.sub_index}）"
                    f"确认谓词得分 {score:.2f}，低置信")
            elif score < 1.0:
                report.notes.append(
                    f"[{size}] 角色 {spec.role}（{sub.block_key}#{sub.sub_index}）"
                    f"确认谓词得分 {score:.2f}")

    assigned_ids = {id(p) for p in mapping.values()}
    for p in pieces:
        if id(p) in assigned_ids:
            continue
        reason = _unassigned_reason(p, profile)
        report.unassigned.append((f"{p.block_key}#{p.sub_index}", reason))
        if reason.startswith("细条"):
            mapping["unknown_strip"] = p
            report.notes.append(
                f"[{size}] 匿名细条 {p.block_key}#{p.sub_index} 语义未知，"
                "不入测量/选项")
    return mapping


def _unassigned_reason(p: SubPiece, profile: StyleProfile) -> str:
    if p.name_hint == "":
        aspect = _aspect(p)
        if profile.strip_aspect is not None and aspect >= profile.strip_aspect:
            return f"细条（长短边比 {aspect:.1f} ≥ {profile.strip_aspect}）"
        return "匿名未识别（档案无对应角色）"
    return f"件名 '{p.name_hint}' 未登记"


def _aspect(p: SubPiece) -> float:
    x0, y0, x1, y1 = p.net_bbox()
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    return max(w, h) / min(w, h)


def piece_inventory_lines(doc: FactoryDoc) -> list[str]:
    """--probe 件清单文本行（块/子片/名/净 bbox/顶点数）。"""
    lines = [f"件总数 {len(doc.pieces)}；码 {', '.join(doc.sizes) or '无'}"]
    counts = doc.piece_counts()
    for (name_hint, size), n in sorted(counts.items(),
                                       key=lambda kv: (kv[0][1], kv[0][0])):
        lines.append(f"  块 '{name_hint or '(匿名)'}' @ {size} x{n}")
    for p in doc.pieces:
        x0, y0, x1, y1 = p.net_bbox()
        ring = p.net_or_gross()
        lines.append(
            f"    #{p.sub_index} {p.block_key}: 净bbox "
            f"{x1 - x0:.0f}x{y1 - y0:.0f} @{x0:.0f},{y0:.0f} "
            f"顶点 {len(ring.pts)} 周长 {ring.perimeter():.0f}mm")
    return lines


__all__ = ["ROLE_IDS", "RoleReport", "detect_profile", "assign_roles",
           "piece_inventory_lines"]
