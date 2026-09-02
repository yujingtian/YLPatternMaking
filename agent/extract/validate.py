"""静态校验：零复制复用 params.validate.build_issues + 派生值区间复核。

分工：
- build_issues（web 同款）：构造期异常逐键归因 + 跨选项前置条件；
- derive_sanity：derive/families 产物越出知识库区间的防御性复核（derive 内
  已 clamp，这里是第二道网——发射前的最后闸口，warning 级不阻断）。
"""

from __future__ import annotations

from ylpattern.params.validate import Issue, build_issues

# 派生区间（与知识库条目同源：K3 clamp[1.5,5] / K4 ③极限 1.5 / Δ 矩阵界）
_DERIVED_RANGES: dict[str, tuple[float, float, str]] = {
    "back_intake": (1.5, 5.0, "K3 后中内收 15:X 模数界"),
    "rise_adjust": (-3.5, 4.5, "直裆深推导.md §三 Δ 矩阵界"),
    "front_pocket_dart_width": (0.0, 1.5, "K4 ③ 袋口转省极限 1.5（超限袋口外翻）"),
    "front_intake_ratio": (0.05, 0.9, "K2 前中内收记账界（低腰 0.15~高腰 0.4+）"),
    "waist_balance": (-1.0, 1.0, "腰围前后片调节量工程界"),
    "delta": (0.0, 2.0, "前后片臀围推导.md §四（引擎守卫同界）"),
}


def validate_candidate(measurements: dict,
                       options: dict) -> tuple[bool, list[Issue]]:
    """dict 形式尺寸 + 选项 -> (可构造, 问题清单)。error 级即阻断。"""
    issues = list(build_issues(measurements, options))
    issues.extend(derive_sanity(options))
    return not any(i.level == "error" for i in issues), issues


def derive_sanity(options: dict) -> list[Issue]:
    """发射值区间复核（warning 级：derive 已 clamp，出界=实现回归）。"""
    out: list[Issue] = []
    for key, (lo, hi, src) in _DERIVED_RANGES.items():
        v = options.get(key)
        if isinstance(v, (int, float)) and not (lo <= v <= hi):
            out.append(Issue(key, f"{key}={v} 越界 [{lo}, {hi}]（{src}）",
                             level="warning"))
    return out


def issue_keys(issues: list[Issue]) -> set[str]:
    """问题清单归因出的候选键集合（None/无参问题不计）。"""
    return {i.param for i in issues if i.param}
