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
# 代码内调用：from ylpattern import run；run(waist=..., hip=..., svg=...)（见 draft_test.py）
```

## 文档驱动的开发方式（本项目最重要的工作流）

- [打版流程.md](打版流程.md) 是步骤的唯一权威来源；[.doc/](.doc/) 下每篇推导文档对应一类公式（臀围、裆、腰、腿、腰头、口袋、袋布、门襟、贴袋、毗围……），[.doc/python工程设计.md](.doc/python工程设计.md) 是工程设计文档（§5 的约束会被代码注释引用）。**文档先行**：门襟 / 后机头 / 后贴袋等目前只有推导文档、尚未程序化，属正常在建状态。
- 用户的典型操作：在打版流程.md 里新增/修改一个步骤 → 要求"程序化"。对应改动链条：**公式层（`formulas/`）→ 选项（`PatternOptions`）→ 步骤函数（`steps/*.py`，按部件分文件：`front_steps` / `back_steps` / `front_pocket_steps` / `front_pouch_steps`）→ 流程列表（`flows/*.py`）→ 金标测试**。步骤 docstring 和 `basis` 字段必须标注依据的文档章节。

## 分层架构（依赖方向自上而下，禁止反向）

`cli/api → exporters → flows → steps → draft → formulas → geometry → params`

- **steps/**：核心层。每个函数对应手工打版的一笔，只做**定位与上版**；数值计算必须调 `formulas/`（纯 float 函数），经验常数一律收敛到 `PatternOptions`，步骤层不硬编码。
- **draft/**：`DraftContext` 是步骤间唯一协作通道 —— 步骤只能 `ctx.point/line/curve("front.xxx")` 读取前面步骤的元素，禁止函数间直接传几何体。产物是 `NamedPoint/NamedLine/NamedCurve`，携带 name/step/basis/label，全程可溯源；`NamedLine.role` 区分 `"ref"`（参考线，SVG 灰虚线）与 `"struct"`（结构线，实线）。
- **flows/**：声明式有序步骤列表；`FlowRunner` 按序执行，支持 `until` 中断与 `trace` 追踪。`FULL_FLOW = [*FRONT_FLOW, *BACK_FLOW]` 串联整版。**毗围闭环是唯一例外**（[flows/closure.py](src/ylpattern/flows/closure.py) 的 `run_with_thigh_closure`）：开 `thigh_limit` 后，整版绘制 → 测前后毗围实测 → ΔW = 目标 − 实测 → 按前后片毗围推导.md §三双轨分流把修正量换算为选项增量 → 整版重跑至收敛；api 与 cli 入口都走它。选择重跑而非版上补丁，是为了让浪长闭合、裤中线等不变量自动保持（"不破坏裤子原本的结构"，打版流程.md 后片步骤 8）。
- **先画后裁**：前后片在同一全局坐标系的一张 `DraftSheet` 上绘制（后片整体置于前片右侧、间距 `piece_gap`，五条水平线等高，后片直接读 `front.xxx` 基准线，故后片必须在前片之后执行）；裁切层（cutter/pieces）尚未实现，故口袋/贴袋等只上版边界线、不做布尔裁除。

## 关键约定

- **坐标系**（与打版流程.md 一致）：原点 = 外侧缝参考线 ∩ 脚口线；X 向右朝内侧缝（裤宽），Y 向上朝腰头（裤长）；单位 cm，内部 float。
- **腰头扣除口径**：`outseam`/`front_rise`/`back_rise` 均为**含腰头的成衣量**。直腰头打版时统一经 `PatternOptions.rise_on_pattern()` 换算（扣腰头宽）；弯腰头不扣。任何使用浪长/裤长的步骤都必须走这一个口子，不要自行扣减。
- **前后片调节量方向**：一律**前减后加**（臀围 Δ、腰围 balance 同向）。前片 = H/4 − Δ、W/4 − balance。
- **可选步骤（开关驱动）**：口袋 / 贴袋 / 袋布 / 后片腰省 / 毗围限制等都是 `PatternOptions` 上的 `bool` 开关；开关关闭或前置条件不满足（如袋布依赖 `front_pocket`、毗围依赖大腿围录入）时步骤返回 `None`，`FlowRunner` 标注"跳过"不上版。开关与几何参数同收敛于 `PatternOptions`。
- **测试风格**：金标测试 —— 测试文件头部注释写明参数下的手工演算结果，断言精确值；推导文档里的案例直接转成公式层金标（见 tests/test_waist.py）。
- 复合线（如前浪 = 斜线 + 凹弧）作为同一步骤的多个元素上版，是"一函数一元素"原则的显式例外。

## 工程速查（AI 开工必读，减少反复摸索）

下面是本文档其余部分没写、但每次开工都要重新摸索的实操细节。

### 坐标系：全局版 + 局部特征框

- **全局版坐标系**（打版流程.md / 上文"关键约定"）：原点 = 外侧缝 ∩ 脚口，X 右 = 内侧缝（裤宽），Y 上 = 腰头（裤长）。前后片同框，后片在前片右侧（间距 `piece_gap`），五条水平参考线等高。
- **局部特征框**（反复出现的模式）：口袋 / 袋布 / 门襟等特征上版时常另建**局部坐标系**按文档推导--取特征锚点为局部原点 O，两轴沿特征的两条基准方向。例：门襟 O = 前浪 ∩ 裤身顶边，Y 沿前浪下行、X 垂直前浪朝外凸；袋布 O = 腰外缝顶点，x 朝门襟、y 向下。局部 → 全局：`o_pt + x_dir.scale(x) + y_dir.scale(y)`（`x_dir = y_dir.perpendicular()`）。**看步骤代码先认局部框**，否则坐标会读反。

### 几何 API 速查（geometry/）

- `Point(x,y)` 不可变：`+Vector`、`-Point → Vector`、`distance_to`、`lerp`、`midpoint`。
- `Vector(dx,dy)`：`length`、`normalized()`、`perpendicular()`（**逆时针 90° 并归一化**，法向方向以此为准）、`scale(k)`、`rotate(deg)`。
- `LineSegment(a,b)`：`length` 是**属性**（不是方法！）、`direction`（a→b 单位向量）、`horizontal`/`vertical` 工厂。
- `CubicBezier(p0,p1,p2,p3)`：`point_at(t)`、`tangent_at(t)`（未归一化）、`length()`（折线近似，**是方法**）、`t_at_length(s)`/`point_at_length(s)`（按弧长定位）、`t_at_y(y)`/`point_at_y(y)`（按高度定位，要求 y 单调）、`split(t)`（de Casteljau，返回两段）、`angle_with(other)`（拼接切线夹角，180°=顺滑）。
- 90° 圆角贝塞尔逼近常数 `4/3×tan(§rad)≈0.5523`（`front_fly_steps._QUARTER_K`），柄长 = 常数 × R。
- `draft/curves.py` 公共弧线库：`arc_through`（弧高式）、`sag_curve`（弧顶精确 sag）、`crotch_curve`（切线+凹深）、`front_rise`/`back_rise`（前/后浪复合线按总浪长闭合反推顶点）、`point_along_chain`（沿"直线+曲线"复合链量取弧长，量腰头宽/开深等）、`bezier_subrange`（取曲线参数子段）。

### role 与 SVG 渲染（exporters/svg.py）

- `NamedLine.role` / `NamedCurve.role`：`"struct"`（结构线，实线深色 #2c3e50）/ `"ref"`（参考线，灰虚线 #999 dasharray）。`NamedLine` 默认 `ref`，`NamedCurve` 默认 `struct`。
- SVG 图层顺序（后绘盖上）：`reference`(ref 线) → `struct`(struct 线) → `curves`(全部曲线，按 role 分 `.curve` 实线 / `.curveref` 虚线) → `elements`(点)。要让某条**曲线**画虚线，给 `add_curve(..., role="ref")`（曲线默认 struct 实线，role 原本不生效，现已支持）。
- 注意：[.doc/python工程设计.md](.doc/python工程设计.md) §5.7 的图层表（net/seam/annotation…）与目录里的 `cutter.py`/`pieces.py`/`validation.py`/`dxf.py` 是**设计期设想，尚未实现**；实际图层与已实现模块见上。该文档是"目标态"，遇不一致以代码为准。

### Unicode 约定（编辑文件易踩坑）

代码与文档的中文标点是**全角 Unicode**，不是 ASCII。用 Edit 工具替换时 `old_string` 必须用对应字符，否则不匹配：
- 箭头 `→` = U+2192（注释"A → B"用它，**不是** ASCII `->`；只有类型注解 `-> float` 才是 ASCII）。
- 破折号 `—` = U+2014（不是 `--`）；减号 `−` = U+2212（不是 `-`）。
- `°`(度)、`×`(乘)、`§`(节)、`≈`(约) 均为 Unicode。
- 替换含这些字符的段落若不匹配，改用**按 ASCII 标记截取**（Python 脚本 `s[s.index(start):s.index(end)]`）或只替换纯 ASCII 子串；heredoc `python3 <<EOF` 在 Windows Git Bash 会挂起，写脚本文件再 `python` 运行。

### 架构约束细节

- 依赖链 `cli/api → exporters → flows → steps → draft → formulas → geometry → params`：**禁止反向**。尤其 `params/`（最底层）**不能 import `formulas/`**（formulas 在其上方）——需公式参与的跨字段校验放**步骤层**（步骤可调 formulas），`PatternOptions.__post_init__` 只做单字段范围校验。
- `formulas/` **只依赖标准库**（`math`），输入输出纯 float，不碰 geometry/params。
- `steps/` 只做定位与上版：数值调 `formulas/`，几何构造调 `geometry/` 与 `draft/curves.py`，经验常数读 `PatternOptions`。

### 元素命名与 ctx 存取

- 元素名 `"front.xxx"` / `"back.xxx"`（部件前缀 + 语义名），全局唯一。上版：`ctx.add_point/line/curve(name, geom, step=_STEP, basis=..., label=..., role=...)`；读取：`ctx.point/line/curve(name)` 返回**几何体**（Point/LineSegment/CubicBezier），类型不符抛 TypeError。
- `_STEP = "draw_xxx"`（或 `__name__`）作步骤来源标记；`basis` 写依据文档章节+关键数值，供 trace/报表溯源。
- `DraftSheet` 是元素容器，`ctx.sheet.get(name)` 取元素本体（含 role/label），`ctx.sheet` 可 `"name" in sheet` 判存在。
- 复合线（前浪 = 斜线 + 裆弯弧）= 同一步骤上版多个元素，是"一函数一元素"的显式例外。

### 当前实现状态（已程序化）

已实现：前片（`front_steps`）、后片（`back_steps`）、前口袋（`front_pocket_steps`）、袋布（`front_pouch_steps`）、前贴袋、门襟（`front_fly_steps`，连裁/独立两形态）、毗围闭环（`flows/closure.py`）。只有 `.doc/` 推导文档、尚未程序化：后机头 / 后贴袋 / 小表袋等（在建）。尚未实现：裁切层（cutter/pieces）、DXF 导出、结构校验器。
