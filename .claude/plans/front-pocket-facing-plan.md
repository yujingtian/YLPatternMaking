# 前口袋袋贴（facing）绘制 程序化方案

## 依据
- 权威步骤：[打版流程.md](打版流程.md) 第 88 行「前口袋袋贴绘制」（用户已新增）
- 实现参考：[.doc/前口袋绘制.md](.doc/前口袋绘制.md) §三.3.(1) 袋贴绘制几何算法
- 模板：[front_pocket_steps.py](src/ylpattern/steps/front_pocket_steps.py) 的 `draw_front_pocket`（沿弧量取锚点、共线渐变偏置控制点、子段闭合边界，最接近的既有实现）与 `draw_front_pouch`（依赖前口袋主切口、复用 `effective_waist`）

## 核心几何（§三.3.(1)）

袋贴 = 表布裁片，遮盖袋口挖空区。三个特征量 + 一条偏置内边：
- **袋贴腰头顶点 P_fw**：有省→自口袋省顶点 P1′、无省→自袋口腰头顶点 P1，沿腰头线（腰弧）朝前浪顶点量取距离 A（=w_facing）
- **袋贴侧缝顶点 P_fs**：自口袋侧缝顶点 P2 沿外缝弧向下量取距离 A（等距约束 d_side = w_facing）
- **袋贴内边 L_inner**：基准曲线 C_ref（有省=切削线 C_cut、无省=净线 C）沿裤身内部法向 N(t) 等间距平行偏置 w_facing
- **闭合拓扑 Ω_facing**：外缝弧段 [O→P_fs] + L_inner + 腰头线段 [P_fw→O]（O=有效腰口侧缝腰点 b）

## 改动链条（CLAUDE.md 工作流：选项 -> 步骤 -> 流程 -> 金标测试；无公式层新增--纯几何）

### 1. PatternOptions（[params/options.py](src/ylpattern/params/options.py)）
在前口袋一组（`front_pocket_mouth_corners` 之后、前贴袋之前）新增 2 字段：
- `front_pocket_facing: bool = False` - 袋贴绘制开关（可选步骤，依赖 front_pocket 主切口）
- `front_pocket_facing_width: float = 3.5` - 袋贴宽 w_facing（cm，即距离 A；腰头端量取 = 侧缝端下落 = 内边偏置间距，三者等距，§三.3.(1)；schema `facing_width_mm=35`）

`__post_init__` 校验：`0.0 < facing_width <= 10.0`（同口袋参数风格，防单位错误）。

### 2. 步骤函数（[steps/front_pocket_steps.py](src/ylpattern/steps/front_pocket_steps.py) 新增 `draw_front_pocket_facing`）
- 开关关 → return None；`front.pocket_p1` 不在 sheet → raise ValueError（依赖主切口，同 pouch/watch_pocket 口径）
- 读 `effective_waist(ctx)` → (b, w_arc, s_side)；`s_arc = ctx.curve("front.outseam_arc")`；dw = `front_pocket_dart_width`

**P_fw（袋贴腰头顶点）**：起点弧长 = `p1_dist + (dw if dw>0 else 0)`（有省从 P1′、无省从 P1），沿腰弧朝前浪顶点再量 w_facing → `w_arc.point_at_length(起点弧长 + w_facing)`；越界（≥腰弧总长）raise
**P_fs（袋贴侧缝顶点）**：P2 弧长位置 = `s_side - p2_drop`，沿外缝弧向下再 w_facing → `s_arc.point_at_length(s_side - p2_drop - w_facing)`；越界（≤0）raise

**L_inner（袋贴内边，C_ref 法向偏置 w_facing，端点锁 P_fw/P_fs）**：
- 基准 C_ref：有省 = `front.pocket_mouth`（切削线），无省 = `front.pocket_mouth_baseline`（净线）；polyline 模式取对应 `_segN`
- 内法向 N(t) = `tangent_at(t).perpendicular()`，用 `front.crease_point` 判内侧翻向（同 `draw_front_pocket` tangent 模式 `_inward`）
- **Bezier 模式（bulge/tangent）**：`CubicBezier(P_fw, cref.p1 + w·N(1/3), cref.p2 + w·N(2/3), P_fs)` —— 内部控制点法向偏置（同 C_cut 控制点域偏置口径），端点锁到 P_fw/P_fs 满足闭合拓扑（自然偏置端点不在腰弧/外缝弧上，须锁）
- **polyline 模式**：折角顶点各沿弦法向 n（向内侧，由 crease_point 定向）平移 w，端点锁 P_fw/P_fs，逐段直线 `front.pocket_facing_inner_segN`（同 `front.pocket_mouth_segN` 风格）

**闭合边界**（Ω_facing = O→P_fw 腰弧子段 + L_inner + P_fs→O 外缝弧子段）：
- `front.pocket_facing_waist_edge` = `w_arc.split(t_fw)[0]`（b→P_fw，同 `front.pocket_waist_edge` b→P1）
- `front.pocket_facing_outseam_edge` = `curves.bezier_subrange(s_arc, t_fs, t_side)`（P_fs→b，同 `front.pocket_outseam_edge` P2→b）

**上版元素**：`front.pocket_facing_waist`/`_side`（Point）、`front.pocket_facing_inner`（Curve，Bezier 模式）或 `_segN`（Line，polyline 模式）、两条闭合边（Curve）；docstring + basis 标注 §三.3.(1)。

### 3. 流程（[flows/front_flow.py](src/ylpattern/flows/front_flow.py)）
阶段 8 在 `draw_front_pocket` 后插入 `fps.draw_front_pocket_facing`（紧贴主切口，先于 watch_pocket/patch）；阶段 8 注释补「袋贴」。

### 4. 金标测试（新文件 [tests/test_pocket_facing_steps.py](tests/test_pocket_facing_steps.py)）
沿用 test_pocket_steps.py 的 M/O（H=96, Δ=1.0, 直腰头扣 4，腰线 y=98；细采样 `_arc_length_between` 数值金标）：
- P_fw 在腰弧上、自 P1′（有省）/P1（无省）沿弧量取 = w_facing；朝前浪顶点侧（x 更大）
- P_fs 在外缝弧上、自 P2 向下沿弧量取 = w_facing；低于 P2
- L_inner 端点 == P_fw / P_fs；内部采样点（t=0.3/0.5/0.7）到 C_ref 的法向距离 ≈ w_facing（`foot_on_bezier` 求最近点）
- 闭合边弧长：腰弧边 = p1_dist+dw+w_facing（有省）/ p1_dist+w_facing（无省）；外缝弧边 = p2_drop+w_facing
- 无省时 C_ref = 净线 `front.pocket_mouth_baseline`；polyline 模式逐段直线、折角平移校验
- 弯腰头兼容（锚点相对下腰头线 B'，经 `effective_waist`）；开关关闭跳过；front_pocket 未开 raise；选项校验（width≤0、>10）

## 范围决策
实现 §三.3.(1) 全部（端点定位 + 内边偏置 + 闭合拓扑），与打版流程.md 第 88 行一致。**不实现**（先画后裁，裁切层未建，同现有口袋步骤口径）：
- 布尔裁除、缝份/缩水、明线、防翻吃边（§三.3.(2) ease）、DXF 图层（§六）
- L_inner 为控制点域法向偏置近似（非精确平行曲线）；端点锁 P_fw/P_fs 保证闭合，内部形状跟随 C_ref 平行--结构线精度足够，裁切层届时精化
