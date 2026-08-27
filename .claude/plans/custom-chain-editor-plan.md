# 袋布自由边界 + 小表袋 custom 净形：结构化编辑器（通用化 CustomShapeEditor）

## Context

袋布的「腰头锚点 → 自由过渡 → 侧缝锚点」引擎侧早已全参数化，但前端只有单行 JSON
文本框（tuple 类型统一渲染 `type="json"`），与后贴袋改造前同款不可用。小表袋
custom 模式同构。本次把 CustomShapeEditor 通用化，覆盖两类新对象：

- **袋布（open 链）**：`front_pouch_nodes`（K 节点）+ `front_pouch_edges`
- **小表袋（closed 链、富边格式）**：`watch_pocket_points` + `watch_pocket_edges`

### 探索已确认的关键事实（实现时直接采信）

- **袋布链结构**（`front_pouch_steps.py` L108-130 / options `_check_front_pouch`）：
  链 = P_w0 → K1..Kn → P_s0（**开放链**）；K 节点相对 O（有效腰口侧缝腰点 b）的
  `(dx, dy 向下正)`；**节点 ≥2**、**边数 = 节点数 + 1**（首段接 P_w0、末段接 P_s0）；
  锚点不在存储数据里——P_w0 = 腰弧上 `p1_dist + waist_safe` 弧长处、P_s0 = P2 沿侧缝
  下探 `side_safe`，由整版几何实时算出。
- **小表袋 custom**（`front_pocket_steps.py` L621-647）：锚点相对参考点 A
  （= O + (offset_from_side, −offset_from_top)）的 `(dx, dy 向下正)`，**≥3 闭合**
  （边数=点数、隐式闭合）；另有 `rotate_deg` 绕 A 旋转（仅影响摆放）。
  **存储帧恰好与后贴袋同规范（v/dy 向下正）**——前贴袋 dy 向上正是唯一异类（已有 flip 机制）。
- **边形态三模式**（`curves.edge_geom`，options `_normalize_edge_specs`）：
  `("line",)` / `("arc", 弧高, 弧顶分位)` / `("bezier", α°, κ1, β°, κ2)`
  （C1 = A + κ1·L0·û(α)、C2 = B + κ2·L0·û(β)，û 为弦向旋转）。校验：|弧高|≤10；
  **弧顶分位袋布闭区间 [0.1,0.9]、小表袋/机头开区间 (0,1)**；bezier |α|,|β|≤90°、
  κ∈(0,1]。与贴袋边 `(bulge, at)` 二元组**格式不同**——贴袋格式不动（已上线数据），
  编辑器内部按 edge_format 区分两种边模型。
- 三对象 = mode × edge_format 的正交组合：贴袋 `closed+bulge`（现状）、
  小表袋 `closed+spec`、袋布 `open+spec`。
- 袋布近似锚点可前端直算（预览用，标注近似、整版为准）：
  P_w0 ≈ `(−(front_pocket_p1_dist + front_pouch_waist_safe), 0)`（腰弧近似水平）；
  P_s0 ≈ `(0, front_pocket_p2_drop + front_pouch_side_safe)`（侧缝近似竖直，内凹未计）。
  四个键全在 options 里，编辑器可直读。
- 现成机制：custom_shape 虚拟参数 + `_HIDDEN` + ParamPanel 分支（本次已修好
  虚拟参数 visible_if 挂接坑）；seed 通道（engine-first 回退阶梯）；编辑器拖拽/表格骨架。

## 实现方案

### 1. 引擎：袋型预设纯函数 + seed 泛化

- **新建 `src/ylpattern/formulas/pouch.py`**：`pouch_chain_preset(shape,
  waist_safe, side_safe) -> (nodes, edges)`，以默认值规律化定义三预设
  （默认参数 4/8 下与现默认 `((5,16),(1.5,13.5)) + (line, arc(2.5,0.6), line)`
  逐位一致，金标钉死）：
  - `"standard"` 标准斜底：K1=(waist_safe+1, 2·side_safe)、
    K2=(waist_safe−2.5, 1.6875·side_safe)，edges=(line, arc(2.5, 0.6), line)；
  - `"round_bottom"` 圆弧底：同节点、中段 arc(4.0, 0.5)；
  - `"deep_rect"` 加深方袋：K1=(waist_safe+1.5, 2.6·side_safe)、
    K2=(waist_safe−3, 2.3·side_safe)，edges 全 line。
  预设属新设计，同步在 `.doc/袋布绘制.md` §三 补一小节登记（文档先行口径）。
- **`webschema.seed_patch_shape` 泛化**：kind 增加 `"front_pouch"`（按
  waist_safe/side_safe 取数调 preset_chain；front_patch/back_patch 分支不动），
  edges 返回完整 spec 格式（`[["line"], ["arc",2.5,0.6], ...]`）。小表袋
  **不做 seed 导入**（facing_intersect 几何依赖整版、纯预设意义不大），仅编辑。
- engine_glue / `/api/seed`：请求 kind 枚举放宽即可（现有通道零结构变化）。

### 2. schema：两个新虚拟参数 + _HIDDEN

- SECTIONS：袋布组 `front_pouch_nodes/edges` 两键换成虚拟条目 `("front_pouch_chain",
  None)`（链恒自定义，无参数级 gate；组级 gate front_pouch+front_pocket 已有）；
  小表袋组 `watch_pocket_points/edges` 换 `("watch_pocket_custom",
  {"param":"watch_pocket_mode","values":["custom"]})`（沿用该组现有 gate 声明口径，
  虚拟 spec 挂 visible_if——走本次修好的挂接路径）。
- `build_schema` 特判扩展产出 spec（沿用 *_custom 分支）：
  - `front_pouch_chain`：`{type:"custom_shape", mode:"open", edge_format:"spec",
     kind:"front_pouch", points_key:"front_pouch_nodes", edges_key:"front_pouch_edges",
     v_positive:"down", anchor_keys:["front_pocket_p1_dist",
     "front_pouch_waist_safe","front_pocket_p2_drop","front_pouch_side_safe"],
     choices:["standard","round_bottom","deep_rect"]}`
  - `watch_pocket_custom`：`{type:"custom_shape", mode:"closed", edge_format:"spec",
     kind:"watch_pocket", points_key:"watch_pocket_points",
     edges_key:"watch_pocket_edges", v_positive:"down", choices:[]}`
  - 贴袋两 spec 补 `mode:"closed", edge_format:"bulge"`（显式化，前端不再靠缺省）。
- `_HIDDEN` 增加 `front_pouch_nodes/edges`、`watch_pocket_points/edges` 4 键
  （422 归因承接、toml 导出不受影响，同贴袋口径）。

### 3. 前端：CustomShapeEditor 通用化

- **types.ts**：`EdgeSpec = (string|number)[]`（变长元组）；`ParamSpec` 加
  `mode?/edge_format?/anchor_keys?`；`SeedResult.edges` 放宽为 `EdgeSpec[]`。
- **CustomShapeEditor** 三处扩展（贴袋行为逐位不变为红线）：
  1. **边格式双模型**：`edge_format:'bulge'` 走现状 (弧高, 位置) 两列；
     `'spec'` 边表每行 = 模式 Select（line/arc/bezier）+ 依模式启用的参数列
     （arc 用前两列=弧高/位置；bezier 用四列 α°/κ1/β°/κ2，窄列；line 全禁用），
     列头「模式 | 弧高/α° | 位置/κ1 | β° | κ2」+ hint 解释两种模式的列含义。
     模式切换时该边参数重置为该模式默认值（arc=(2,0.5)、bezier=(30,0.4,−30,0.4)）。
  2. **open 模式**：点表只编 K 节点（下限 2）；边数=点数+1，增删点同步增删
     相邻边（默认 line）；无闭合边。预览画开放链 + 两端**近似锚点**（方块标记、
     标注「近似」，由 anchor_keys 读 options 前端直算，锚点不可拖）。
  3. **spec 预览渲染**：line 直线；arc 沿用 Q 二次近似 + 屏幕法向 (dy,−dx)；
     bezier 控制点前端按 edge_geom 同式复算 → SVG C 命令（**显示层近似**，
     引擎为准，注释登记——与贴袋 arc apex 前端复算同类口径）。小表袋（closed+spec）
     预览不画整体旋转（rotate_deg 只影响摆放，hint 注明）。
- **ParamPanel**：custom_shape 分支把 `options`（或 anchor 数值）传入编辑器
  （近似锚点在编辑器内算，纯显示近似）；422 错误合并扩展到新 4 个隐藏键。
- **useDraft**：`seedShape` kind 放宽；前端 SeedPayload/edges 类型同步。

### 4. 测试

- `tests/test_pouch_formula.py`（新）：三预设金标（默认参数逐位=现默认链）。
- `tests/test_webschema.py`：两新虚拟 spec 元数据（mode/edge_format/anchor_keys/
  gate 挂接）+ _HIDDEN 4 键 + seed front_pouch 金标。
- `tests/test_engine_glue.py`：seed kind=front_pouch 双通道全等。
- 既有袋布/小表袋绘制与裁片测试零改动通过（纯 UI 层，引擎几何不动——
  仅新增 formulas 预设与 seed，steps 不改）。

### 5. 文档

- `.doc/袋布绘制.md` §三：三预设登记（一小节）。
- `.doc/python工程设计.md` §10.7：编辑器条目扩 mode/edge_format/近似锚点口径；
  §10.6：`formulas/pouch` 条目；§10.8：seed kind 扩展一句。

## 实现顺序

1. formulas/pouch + seed 泛化 + schema 虚拟参数/_HIDDEN → pytest 全绿 → build:engine。
2. 编辑器通用化（spec 边表 → open 模式/锚点 → 预览渲染）+ ParamPanel/useDraft 接线
   → npm build。
3. 小表袋接入验证（gate=custom 才显示）。
4. 文档同步。

## 验证

```bash
python -m pytest tests/ -q
cd webapp/frontend && npm run build
```

手动端到端（uvicorn + npm dev）：
1. 开 front_pocket+front_pouch → 袋布组出现「自由边界编辑器」（open 模式）：
   默认链两节点三边、近似锚点方块、整版对照锚点偏差在腰弧/侧缝曲率量级。
2. 导入 standard → 与默认一致；round_bottom → 中段变弧；改 waist_safe/side_safe
   → 近似锚点实时移动；拖 K 节点 → nodes 回写、整版重生成袋形正确。
3. 边模式切 bezier → 4 参数列启用、预览 C 曲线平滑；非法值（κ=0、|α|>90）行内提示。
4. 小表袋 mode=custom → 编辑器出现（closed+spec、无闭合边差异）；切回
   facing_intersect → 编辑器隐藏（gate）。
5. `?engine=off` → seed 走 HTTP 正常；非法 options → 422 回显编辑器上方。
