"""工厂 DXF 反解析（.doc/工厂DXF逆向解析.md）。

入口 ``reverse_dxf(path)``：读取 -> 识别 -> 测量 -> 档差 -> 发射尺寸单
TOML；分层 1（尺寸单 8 测量值）+ 层 2（可直接量测 options）+ 层 3
（多码档差 [size_run]）。形状系数逆拟合（层 4）不在本期。

依赖方向：本包与 cli/api 同层，只 import params + geometry + stdlib；
ezdxf 仅 reader 惰性引入（可选 extra dxf）。
"""

from dataclasses import dataclass, field

from .errors import ReverseError
from .geomops import (chain_above, chain_between, chain_length_mm,
                      chord_span_mm, rigid_fit_offset, slope_between,
                      strip_width_mm)
from .identify import (ROLE_IDS, RoleReport, assign_roles, detect_profile,
                       piece_inventory_lines)
from .model import (DocHeader, FactoryDoc, LabeledPoint, OpenLine, PieceMeta,
                    Ring, SubPiece, size_sort_key)
from .profiles import StyleProfile, SubSpec, get_profile, known_profiles
from .reader import (fix_mojibake, parse_block_name,
                     parse_shrinkage_annotation, parse_shrinkage_filename,
                     read_dxf, require_ezdxf)


@dataclass
class ReverseResult:
    """一次反解析的完整结果（probe 模式下 calib 及之后各段为空）。"""

    doc: FactoryDoc
    profile: StyleProfile | None = None
    roles: RoleReport | None = None
    calib: object | None = None                  # Calibration（probe 缺省）
    base: str = ""                               # 基码（头标 SAMPLE SIZE）
    measured: dict = field(default_factory=dict)  # 码 -> MeasuredSize
    options: dict | None = None                  # 层 2（仅基码）
    warns: list[str] = field(default_factory=list)
    size_run: dict | None = None                 # 层 3（grade.py 产出）


def reverse_dxf(path: str, *, style: str = "auto",
                probe_only: bool = False) -> ReverseResult:
    """工厂 DXF -> ReverseResult（读取/识别/标定/测量一条龙）。

    probe_only=True 时只读取+识别（新款 bring-up：先看件清单再补档案），
    不标定不测量。ReverseError 向上抛（cli 捕获后退出码 2）。
    """
    require_ezdxf()
    doc = read_dxf(path)
    profile = detect_profile(doc, style)
    roles = assign_roles(doc, profile)
    res = ReverseResult(doc=doc, profile=profile, roles=roles)
    if probe_only:
        return res

    from .measure import Calibration, measure_8, measure_options
    res.calib = Calibration.from_doc(doc)
    base = doc.header.sample_size
    if base not in doc.sizes:
        base = doc.sizes[0] if doc.sizes else ""
    res.base = base
    for label in doc.sizes:
        res.measured[label] = measure_8(label, roles.for_size(label), res.calib)
    res.options, res.warns = measure_options(
        base, roles.for_size(base), res.measured[base], res.calib)
    if len(doc.sizes) > 1:                   # 多码：层 3 档差
        from .grade import grade_from_measurements
        res.size_run, gwarns = grade_from_measurements(
            res.measured, base, profile.key, order=list(doc.sizes))
        res.warns.extend(gwarns)
    return res


__all__ = ["ReverseError", "ReverseResult", "reverse_dxf", "DocHeader",
           "FactoryDoc", "LabeledPoint", "OpenLine", "PieceMeta", "Ring",
           "SubPiece", "ROLE_IDS", "RoleReport", "StyleProfile", "SubSpec",
           "assign_roles", "chain_above", "chain_between", "chain_length_mm",
           "chord_span_mm", "detect_profile", "fix_mojibake", "get_profile",
           "known_profiles", "parse_block_name", "parse_shrinkage_annotation",
           "parse_shrinkage_filename", "piece_inventory_lines", "read_dxf",
           "require_ezdxf", "rigid_fit_offset", "size_sort_key",
           "slope_between", "strip_width_mm"]
