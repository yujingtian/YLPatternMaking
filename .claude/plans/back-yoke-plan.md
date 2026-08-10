# 后机头/育克绘制 程序化方案

## 依据
- 权威步骤：[打版流程.md](打版流程.md)「后机头/育克绘制」（用户已新增）
- 实现参考：[.doc/后机头绘制.md](.doc/后机头绘制.md)
- 模板：[front_pocket_steps.py](src/ylpattern/steps/front_pocket_steps.py) 的 `draw_front_watch_pocket`（锚点链 + `edge_geom` 逐边 line/arc/bezier，最接近的既有实现）

## 改动链条（CLAUDE.md 工作流：选项 -> 步骤 -> 流程 -> 金标测试；无公式层新增——纯几何）

### 1. PatternOptions（[params/options.py](src/ylpattern/params/options.py)）
新增字段（紧跟 `back_dart_*` 后片省一组之后）：
- `back_yoke: bool = False` — 开关
- `back_yoke_cb_dist: float = 4.0` — P0 后浪端点：自腰头内缝顶点沿后浪线向下量取弧长 D_cb（§1）
- `back_yoke_side_dist: float = 3.0` — PN 侧缝端点：自腰头外缝顶点沿外缝线向下量取弧长 D_side（§1）
- `back_yoke_mid_anchors: tuple[tuple[float,float],...] = ()` — 下口中间锚点 `(u, depth)`：u=弦上比例 0~1（严格递增）、depth=偏离弦深度（cm，正值向下凸入裤身，0=压弦）；空=直线（打版流程.md：无锚点即直线）
- `back_yoke_edges: tuple = (("line",),)` — 逐段形态，个数=锚点数+1；line/arc/bezier（与袋布/小表袋同口径）

`__post_init__` 校验：dist>0；u∈(0,1) 严格递增；|depth|≤10；边形态 line/arc/bezier 合法；边数=锚点数+1。归一化为元组（复用 watch_pocket 校验风格）。

### 2. 步骤函数（新文件 [steps/back_yoke_steps.py](src/ylpattern/steps/back_yoke_steps.py)）
`draw_back_yoke(ctx) -> NamedCurve | NamedLine | None`：

**端点定位（§1 弧长量取驱动）**：
- 量取起点：弯腰头=`back.lower_waist_center_point`/`back.lower_waist_side_point`（O'/X'，链上再下移腰头宽 W）；直腰头=`back.rise_top_point`/`back.waist_side_point`（O/X）
- P0 = `point_along_chain((rise_slant, rise_curve), d_cb)`，d_cb = D_cb（直）/ W+D_cb（弯）
- PN = `point_along_chain((_reverse_bezier(outseam_hip_waist), outseam_upper, outseam_lower), d_side)`，d_side = D_side（直）/ W+D_side（弯）
  - `_reverse_bezier(b) = CubicBezier(b.p3, b.p2, b.p1, b.p0)`：外缝髋腰弧原方向 臀(t=0)->腰(t=1)，反向得 腰->臀，自腰端向下量取

**下口线（§2 N-Point 分段拓扑）**：
- 节点链 `[P0, 中间锚点..., PN]`；中间锚点 `P0.lerp(PN, u) + n·depth`，n=弦法向（取 dy<0 朝下/入裤身）
- 逐段 `edge_geom(a, b, spec)`，line→add_line(role="struct")、arc/bezier→add_curve

**上版元素**：`back.yoke_cb_point`(P0)、`back.yoke_side_point`(PN)、`back.yoke_mid_pt{i}`、`back.yoke_bottom_seg{i}`。上口（腰头线/下腰头线）已存在，两侧（后浪/外缝子段）为既有曲线，不重画——只上版分割下口线（先画后裁）。

### 3. 流程（[flows/back_flow.py](src/ylpattern/flows/back_flow.py)）
BACK_FLOW 末尾追加阶段 10：`yoke.draw_back_yoke`（在 `draw_back_darts` 之后）。

### 4. 金标测试（新文件 [tests/test_back_yoke_steps.py](tests/test_back_yoke_steps.py)）
沿用 test_back_steps.py 的 M/O（H=96, Δ=1.0, 直腰头扣 4，腰线 y=98）：
- 默认跳过；端点弧长校验（P0 在后中斜线上 -> O.distance_to(P0)=D_cb；PN 用 `outseam_hip_waist.split(t)[1].length()==D_side`，同 lower_waistband 测法）
- 弯腰头：链上距离 = W+D_cb / W+D_side
- 默认无锚点=单段直线 P0->PN（struct）；1 锚点 (0.5,1.5) 下凸；自定义 line/arc/bezier 三段（bezier 控制点构造校验，同 watch_pocket）
- 选项校验（dist≤0、u 越界、边数不符、非法边形态）

### 5. 文档
- [打版流程.md](打版流程.md)：修笔误「直摇头」->「直腰头」（用户已写就步骤，内容不动）
- [CLAUDE.md](CLAUDE.md)「当前实现状态」：后机头移入已实现；修正小表袋误列未程序化

## 范围决策（需确认）
`.doc` 共 5 节，本方案实现 §1 端点定位 + §2 分段拓扑（核心，与打版流程.md 一致）。**不实现**：
- **§4 后中正交约束**（segment 0 ⟂ 后中线 90°）：.doc 标为「硬性」，但打版流程.md（唯一权威来源）未提；仅对 bezier 首段可干净实现（强锁 P0 把柄法向），对 line/arc 无法不侵入用户锚点。**建议本期跳过**，留作后续精化，docstring 注明。
- **§5 吃势补偿 + 对位标记**：属工艺/缝边层（ease、notch），用户已说「绘制不要管缝边和缩水」，跳过。
- **§3 省量吸收**：已由 `back_waist_dart`（约克转移量）在后腰长口径体现，yoke 几何不另做。

若希望本期一并实现 §4（至少 bezier 首段法向锁定），请在审批时说明。
