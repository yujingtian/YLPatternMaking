# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

牛仔裤数字化打版系统（Python ≥3.10，核心层零第三方依赖）。把手工打版工程化：**打版师的每一笔（定一个点、画一条线）在程序中都有且仅有一个对应的生成函数**，按流程编排逐步绘制，先画后裁。

## 常用命令

```bash
pip install -e ".[dev]"        # 安装（含 pytest）
python -m pytest tests/ -q     # 全部测试
python -m pytest tests/test_steps.py -q              # 单文件
python -m pytest tests/ -k "waistline" -q            # 按名称过滤
python draft_test.py           # 快速出图（改文件里的参数即可）→ out/sheet.svg
python -m ylpattern.cli draft --size examples/size_female_165.toml \
    --svg out/sheet.svg --trace out/trace.txt --report out/report.txt
# CLI 还支持 --until 步骤名：执行到该步停止，输出中间版调版
```

## 文档驱动的开发方式（本项目最重要的工作流）

- [打版流程.md](打版流程.md) 是步骤的唯一权威来源；[.doc/](.doc/) 下每篇推导文档对应一类公式（臀围、裆、腰、腿、腰头……），[.doc/python工程设计.md](.doc/python工程设计.md) 是工程设计文档（§5 的约束会被代码注释引用）。
- 用户的典型操作：在打版流程.md 里新增/修改一个步骤 → 要求"程序化"。对应改动链条：**公式层（`formulas/`）→ 选项（`PatternOptions`）→ 步骤函数（`steps/front_steps.py`）→ 流程列表（`flows/front_flow.py`）→ 金标测试**。步骤 docstring 和 `basis` 字段必须标注依据的文档章节。

## 分层架构（依赖方向自上而下，禁止反向）

`cli/api → exporters → flows → steps → draft → formulas → geometry → params`

- **steps/**：核心层。每个函数对应手工打版的一笔，只做**定位与上版**；数值计算必须调 `formulas/`（纯 float 函数），经验常数一律收敛到 `PatternOptions`，步骤层不硬编码。
- **draft/**：`DraftContext` 是步骤间唯一协作通道 —— 步骤只能 `ctx.point/line/curve("front.xxx")` 读取前面步骤的元素，禁止函数间直接传几何体。产物是 `NamedPoint/NamedLine/NamedCurve`，携带 name/step/basis/label，全程可溯源；`NamedLine.role` 区分 `"ref"`（参考线，SVG 灰虚线）与 `"struct"`（结构线，实线）。
- **flows/**：声明式有序步骤列表；`FlowRunner` 按序执行，支持 `until` 中断与 `trace` 追踪。
- **先画后裁**：前后片在同一全局坐标系的一张 `DraftSheet` 上绘制；裁切层（cutter/pieces）尚未实现。

## 关键约定

- **坐标系**（与打版流程.md 一致）：原点 = 外侧缝参考线 ∩ 脚口线；X 向右朝内侧缝（裤宽），Y 向上朝腰头（裤长）；单位 cm，内部 float。
- **腰头扣除口径**：`outseam`/`front_rise`/`back_rise` 均为**含腰头的成衣量**。直腰头打版时统一经 `PatternOptions.rise_on_pattern()` 换算（扣腰头宽）；弯腰头不扣。任何使用浪长/裤长的步骤都必须走这一个口子，不要自行扣减。
- **前后片调节量方向**：一律**前减后加**（臀围 Δ、腰围 balance 同向）。前片 = H/4 − Δ、W/4 − balance。
- **测试风格**：金标测试 —— 测试文件头部注释写明参数下的手工演算结果，断言精确值；推导文档里的案例直接转成公式层金标（见 tests/test_waist.py）。
- 复合线（如前浪 = 斜线 + 凹弧）作为同一步骤的多个元素上版，是"一函数一元素"原则的显式例外。
