# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

牛仔裤数字化打版系统（Python ≥3.10，核心层零第三方依赖）。把手工打版工程化：**打版师的每一笔（定一个点、画一条线）在程序中都有且仅有一个对应的生成函数**，按流程编排逐步绘制，先画后裁。

## 常用命令

```bash
pip install -e ".[dev]"        # 安装（含 pytest + ezdxf，DXF 测试可跑；生产装 .[dxf] 即可）
python -m pytest tests/ -q     # 全部测试
python -m pytest tests/test_steps.py -q              # 单文件
python -m pytest tests/ -k "waistline" -q            # 按名称过滤
# 出图：改 examples/ 下尺寸单参数即可，用 CLI 生成整版 + 各独立裁片 SVG
python -m ylpattern.cli draft --size examples/size_female_165.toml \
    --svg out/sheet.svg --trace out/trace.txt --report out/report.txt \
    --waistband-svg out/waistband.svg --yoke-svg out/yoke.svg \
    --front-pocket-svg out/front_pocket.svg \
    --front-pouch-svg out/front_pouch.svg \
    --front-fly-single-svg out/front_fly_single.svg \
    --front-fly-double-svg out/front_fly_double.svg \
    --watch-pocket-svg out/watch_pocket.svg \
    --back-patch-svg out/back_patch.svg \
    --front-piece-svg out/front_piece.svg \
    --back-piece-svg out/back_piece.svg
# DXF（裁床/服装 CAD，R12/mm 折线，需 pip install 'ylpattern[dxf]'）：
#   --dxf out/sheet.dxf 整版一张；--pieces-dxf out/pieces.dxf 全部裁片平铺合一张
# CLI 还支持 --until 步骤名：执行到该步停止，输出中间版调版
# 代码内调用：from ylpattern import run；run(waist=..., hip=..., svg=...)（详见 api.run docstring）
```

## 文档驱动的开发方式（本项目最重要的工作流）

- [打版流程.md](打版流程.md) 是步骤的唯一权威来源；[.doc/](.doc/) 下每篇推导文档对应一类公式（臀围、裆、腰、腿、腰头、口袋、袋布、门襟、贴袋、毗围……），[.doc/python工程设计.md](.doc/python工程设计.md) 是工程设计文档。**文档先行**：部分特征先有推导文档、后程序化，属正常在建状态。
- 用户的典型操作：在打版流程.md 里新增/修改一个步骤 → 要求"程序化"。对应改动链条：**公式层（`formulas/`）→ 选项（`PatternOptions` 需同步 `api.run()` 显式参数透传）→ 步骤函数（`steps/*.py`，按部件分文件：`front_steps` / `back_steps` / `front_pocket_steps` / `front_pouch_steps` / `front_fly_steps` / `back_yoke_steps` / `back_patch_steps` / `waistband_steps`）→ 流程列表（`flows/*.py`）→ 金标测试**。腰头裁片另走裁切链：`steps/waistband_steps` + `flows/waistband_flow`（`build_waistband(main_ctx)` 从整版提取腰弧净长）-> `cutter`（缩水+缝边）-> `exporters/piece_svg`（独立 SVG），不在 FULL_FLOW 内。后机头裁片同走裁切链：`flows/yoke_flow`（`build_yoke(main_ctx)` 从整版提取机头四边界，有省时绕省尖旋转闭合 + 拼合处 G1 倒圆）-> `cutter` -> 刀口（净样角点沿净线延长线交缝边、净刀口沿外法向交缝边，§5.1）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。前口袋裁片同走裁切链：`flows/front_pocket_flow`（`build_front_pocket(main_ctx)` 从整版提取袋贴/贴袋净样边界，按 front_pocket_facing/front_patch 派发）-> `cutter` -> 刀口（袋贴袋口净线端点沿切线延长线交缝边、净样线+缝边成对；贴袋净角点沿相邻净线延长线交缝边，§2.2）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。袋布裁片同走裁切链：`flows/front_pouch_flow`（`build_front_pouch(main_ctx)` 从整版提取袋布大片/小片净样，小片沿内边 P_w0-K1 轴对称、按省/无省取袋口挖削线，拼成一片式对折轮廓）-> `cutter`（缩水默认 0 隔离大身面料 + 缝边）-> 刀口（底层完整侧袋口弧线端点沿切线延长线交缝边、挖削侧免打口 + 前口袋弧线/省弧线辅助线，§5）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。门襟裁片同走裁切链：`flows/front_fly_flow`（`build_front_fly(main_ctx)` 从整版提取独立门襟净样，单排原样提取、双排去底角 J 弧外缘平行化后沿内边轴镜像展开成对折片）-> `cutter`（缩水+缝边+刀口沿外法向投影至毛样外沿，§2/§4）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。小表袋裁片同走裁切链：`flows/watch_pocket_flow`（`build_watch_pocket(main_ctx)` 从整版提取小表袋净样，按 watch_pocket_mode 派发：袋贴相交延伸取底边袋贴内边子段、全自定义拷贝锚点闭合链）-> `cutter`（里料缩水默认 0 隔离大身面料 + 缝边）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。后贴袋裁片同走裁切链：`flows/back_patch_flow`（`build_back_patch(main_ctx)` 从整版 1:1 完整复制四形态净样，依赖 back_yoke 定位；大身面料缩水 None 回退全局 + 分区缝边 + 袋口镜像折边/撇势 + 袋口 4 刀（净口两角沿侧缝边/顶部线延长线交缝边、打在缝边上、底部不打口，§4））-> `cutter` -> `exporters/piece_svg`，亦不在 FULL_FLOW 内。前片裁片同走裁切链：`flows/front_piece_flow`（`build_front_piece(main_ctx)` 从整版提取前片大片净样，弯腰头剥离/口袋挖削/连裁门襟三形态条件矩阵装配净边 -> `cutter`（缩水+缝边+裆尖角部：镜像折角/纯尖角跟随净样（贝塞尔多项式自然外延求交成尖，不抹圆））-> 刀口法向投影至毛样外沿 -> `exporters/piece_svg`，臀/膝/毗围辅助线随净边截断），亦不在 FULL_FLOW 内。后片裁片同走裁切链：`flows/back_piece_flow`（`build_back_piece(main_ctx)` 从整版提取后片主裁片净样（剥离腰头与机头），有 yoke 沿机头下口线截断/无机头取腰口弧三形态装配净边 -> `cutter`（缩水+缝边+后浪浪尖镜像折角/纯尖角）-> 刀口（法向投影 + 上边界两角净线延长线射线刀口/贴袋对位顶部刀口交毛样外沿）-> `exporters/piece_svg`，臀/横裆/膝围辅助线随净边截断 + 后贴袋顶线/定位孔 drills），亦不在 FULL_FLOW 内。步骤 docstring 和 `basis` 字段必须标注依据的文档章节。

## 分层架构（依赖方向自上而下，禁止反向）

`cli/api → exporters → flows → steps → draft → formulas → geometry → params`（**禁止反向**；尤其 `params/` 不能 import `formulas/`）

- **steps/**：核心层。每个函数对应手工打版的一笔，只做**定位与上版**；数值计算必须调 `formulas/`（纯 float 函数），经验常数一律收敛到 `PatternOptions`，步骤层不硬编码。
- **draft/**：`DraftContext` 是步骤间唯一协作通道——步骤只能 `ctx.point/line/curve("front.xxx")` 读取前面步骤的元素，禁止函数间直接传几何体；产物全程可溯源。
- **flows/**：声明式有序步骤列表；`FlowRunner` 按序执行，支持 `until` 中断与 `trace` 追踪。`FULL_FLOW = [*FRONT_FLOW, *BACK_FLOW]` 串联整版。**毗围闭环是唯一例外**（[flows/closure.py](src/ylpattern/flows/closure.py) 的 `run_with_thigh_closure`）：开 `thigh_limit` 后，整版绘制 → 测前后毗围实测 → ΔW = 目标 − 实测 → 按前后片毗围推导.md §三双轨分流把修正量换算为选项增量 → 整版重跑至收敛；api 与 cli 入口都走它。选择重跑而非版上补丁，是为了让浪长闭合、裤中线等不变量自动保持（"不破坏裤子原本的结构"，打版流程.md 后片步骤 8）。
- **先画后裁**：前后片在同一全局坐标系的一张 `DraftSheet` 上绘制（后片整体置于前片右侧、间距 `piece_gap`，五条水平线等高，后片直接读 `front.xxx` 基准线，故后片必须在前片之后执行）；裁切层（cutter/pieces）已为腰头、后机头等独立裁片落地（`build_waistband` / `build_yoke` 另建局部 sheet、经缩水+缝边出独立 SVG），但主版布尔裁除未实现，故口袋/贴袋等仍只上版边界线、不做布尔裁除。

## 关键约定

- **坐标系**（与打版流程.md 一致）：原点 = 外侧缝参考线 ∩ 脚口线；X 向右朝内侧缝（裤宽），Y 向上朝腰头（裤长）；单位 cm，内部 float。
- **腰头扣除口径**：`outseam`/`front_rise`/`back_rise` 均为**含腰头的成衣量**。直腰头打版时统一经 `PatternOptions.rise_on_pattern()` 换算（扣腰头宽）；弯腰头不扣。任何使用浪长/裤长的步骤都必须走这一个口子，不要自行扣减。
- **前后片调节量方向**：一律**前减后加**（臀围 Δ、腰围 balance 同向）。前片 = H/4 − Δ、W/4 − balance。
- **可选步骤（开关驱动）**：口袋 / 袋贴 / 贴袋 / 袋布 / 小表袋 / 后片腰省 / 后机头 / 毗围限制等都是 `PatternOptions` 上的 `bool` 开关；开关关闭或前置条件不满足（如**袋贴 `front_pocket_facing`、袋布 `front_pouch`、小表袋 `watch_pocket` 均依赖 `front_pocket` 主切口；小表袋相交模式 `facing_intersect` 额外强依赖 `front_pocket_facing`**；毗围依赖大腿围录入）时步骤返回 `None`，`FlowRunner` 标注"跳过"不上版。开关与几何参数同收敛于 `PatternOptions`。
- **测试风格**：金标测试——测试文件头部注释写明参数下的手工演算结果，断言精确值；推导文档里的案例直接转成公式层金标（见 tests/test_waist.py）。
- 复合线（如前浪 = 斜线 + 凹弧）作为同一步骤的多个元素上版，是"一函数一元素"原则的显式例外。

## 元素命名与 ctx 存取

- 元素名 `"front.xxx"` / `"back.xxx"`（部件前缀 + 语义名），全局唯一。上版：`ctx.add_point/line/curve(name, geom, step=_STEP, basis=..., label=..., role=...)`；读取：`ctx.point/line/curve(name)` 返回**几何体**（Point/LineSegment/CubicBezier），类型不符抛 TypeError。
- `_STEP = "draw_xxx"`（或 `__name__`）作步骤来源标记；`basis` 写依据文档章节+关键数值，供 trace/报表溯源。
- `DraftSheet` 是元素容器，`ctx.sheet.get(name)` 取元素本体（含 role/label），`ctx.sheet` 可 `"name" in sheet` 判存在。

## 实现前定向读（隐性规则，代码里看不出来）

写新步骤/特征前，按触发场景**定向读** [.doc/python工程设计.md](.doc/python工程设计.md) §十（按需，别全读）：

- 画局部特征框（口袋/袋布/门襟/贴袋等局部 u-v 系）-> §10.1（原点、轴正方向、旋转顺时针为正）
- role/SVG 图层与渲染 -> §10.3
- 架构依赖红线（params 禁 import formulas 等）-> §10.4（亦见本文「分层架构」）
- Edit 改中文代码/文档失配 -> §10.5（全角 Unicode 与 fallback）
- 不确定某特征是否已程序化 -> §10.6

**几何 API（`geometry/`、`draft/curves.py`）不查文档，直接读代码**，签名与易踩坑点已在代码 docstring 标注，文档不重复维护。
