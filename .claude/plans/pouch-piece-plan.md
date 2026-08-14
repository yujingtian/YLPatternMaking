# 口袋布独立裁片 (Front Pouch Piece) 实现计划

依据：[.doc/裁片/口袋布裁片.md](.doc/裁片/口袋布裁片.md) §2~§6。裁片另走裁切链
（同 `front_pocket_flow` / `yoke_flow`），**不入 FULL_FLOW**。

## 一、几何方案（核心）

前片上只画了袋布的一半（大片=底层 / 小片=面层，1:1 重合，由 `draw_front_pouch` 上版）。
裁片为**一片式对折**，以内边为对称轴把面层镜像翻出，与底层拼合成单闭合轮廓。

- **对称轴（折叠轴）**：`front.pouch_waist_anchor`(P_w0) → `front.pouch_node1`(K1) 连线
  （用户指定：内边=靠近前浪的一边，暂以 P_w0-K1 直线近似）。
- **底层（底层大轮廓）**：大片**原样复制**（§2.1「严格复制前片袋布轮廓」）。
  闭合路径 P_w0 → K1 → … → Kn → P_s0 → 侧缝链 → b → 腰弧 → P_w0。
- **面层（轴对称出来的一半，§2.2 挖削）**：小片沿 P_w0-K1 **镜像**。
  小片上版时上沿已走袋口挖削（侧缝 P_s0→P2 + 袋口切削线 P2→P1′ + 腰弧 P1′→P_w0），
  镜像即得挖削后面层，无需再做布尔运算：
  - **有省**：小片袋口边 = 反向 `front.pocket_mouth`（切削线 C_cut = 口袋省弧线，§2.2）。
  - **无省**：`front.pocket_mouth` 此时 = `front.pocket_mouth_baseline`（净线 = 口袋弧线）。
- **对折边 P_w0-K1 为内部折叠线**，不在裁片周界上。
- **合并单闭合轮廓**（绕一周）：
  底层非折叠边 `K1→…→P_s0→b→P_w0` ＋ 镜像面层非折叠边**反转** `P_w0→P1″→P2′→P_s0′→…→K2′→K1`
  （P1″/P2′/P_s0′/K2′ 为 P1′/P2/P_s0/K2 的镜像点）。

> 说明：底层用大片原样（非全对称），面层用镜像小片——这与用户指令「严格复制前片袋布轮廓
> ＋ 轴对称出来的一半挖掉口袋部分」一致，且复用已上版的小片挖削，免布尔运算。

## 二、改动链条（文档驱动工作流）

### 1. 公式层（`formulas/`）
无新增（纯几何镜像，无新数值公式）。

### 2. 选项（`params/options.py` + `params/__init__.py`）
- 新增 `PouchSeamAllowances` dataclass（cm，§4）：
  - `fold: float = 0.0`（对折线，放量为 0；内部边，周界不使用，仅文档化）
  - `mouth: float = 1.0`（挖削袋口弧线，§4 常规缝边）
  - `waist: float = 1.0`（腰头边，与前片腰头缝份一致）
  - `side: float = 1.0`（侧缝边，与前片侧缝缝份一致）
  - `bottom: float = 1.2`（袋底与外围，§4 取 1~1.5 中值）
  - `from_dict` 类方法（同其它 SA dataclass）。
- `PatternOptions` 新增字段：
  - `front_pouch_seam_allowances: PouchSeamAllowances = field(default_factory=...)`
  - `front_pouch_shrinkage_warp: float = 0.0`（口袋布不缩水，§3 强制 0、隔离大身面料；可覆盖）
  - `front_pouch_shrinkage_weft: float = 0.0`
- `__post_init__`：SA 类型校验 + 各字段非负；缩水率 ∈ [0, 0.2)（同 front_pocket 口径，但默认 0 非 None）。
- `from_file`：`front_pouch_seam_allowances` 走 `PouchSeamAllowances.from_dict`。
- `params/__init__.py`：导出 `PouchSeamAllowances`。

### 3. 步骤函数（`steps/front_pouch_steps.py`）
**无改动**。大片/小片净样边界已由 `draw_front_pouch` 上版（`front.pouch_large_*` /
`front.pouch_small_*`），裁片流程直接提取。

### 4. 流程（新建 `flows/front_pouch_flow.py`）
`build_front_pouch(main_ctx) -> (PatternPiece, DraftContext)`，自含裁片（非 FlowRunner）：

几何小工具（复用 front_pocket_flow/yoke_flow 同款）：
- `_reflect_point(p, axis_a, axis_b)`：点关于直线 axis_a→axis_b 的镜像
  （proj = A + d·((P−A)·d/|d|²)；P′ = 2·proj − P；用 Point+Vector / Point−Point 口径）。
- `_reflect_geom(g, axis_a, axis_b)`：直线/贝塞尔控制点同步镜像（保贝塞尔性）。
- `_reverse_geom` / `_to_local_geom`(Y 反射：X 不翻避镜像、Y 翻让腰头在上，同 front_pocket_flow)
  / `_to_local_point` / `_geom_sample` / `_signed_area` / `_vertical_grain`：照搬 front_pocket_flow。

提取（主版坐标）：
- `_collect_large_edges(ctx)` → 底层非折叠命名边（K1→P_w0 走向）：
  - 节点链 `front.pouch_large_seg2..segN`（跳 seg1=P_w0→K1 折叠边）→ name `"bottom"`
  - 侧缝链 `front.pouch_side_edge`（单段）或 `front.pouch_side_edge_thigh`+`_hip`（两段）→ `"side"`
  - 腰弧 `front.pouch_large_waist_edge` → `"waist"`
- `_collect_small_edges(ctx)` → 面层非折叠命名边（K1→P_w0 走向）：
  - 节点链 `front.pouch_small_seg2..segN`（跳 seg1）→ `"bottom"`
  - 侧缝 `front.pouch_small_side_seg{i}` → `"side"`
  - 袋口 `front.pouch_small_mouth_seg{i}` → `"mouth"`
  - 腰弧 `front.pouch_small_waist_edge` → `"waist"`

装配：
1. 轴 P_w0=`front.pouch_waist_anchor`、K1=`front.pouch_node1`。
2. 底层边 = `_collect_large_edges`（原样）。
3. 面层边 = `_reflect_geom` 镜像 `_collect_small_edges` 各边 → 整表反转（list 反转 + 每条 geom 反转），
   命名加 `"_m"` 后缀（`bottom_m`/`side_m`/`waist_m`/`mouth`）——折叠点 P_w0、K1 处异名边
   **强制 miter**（同 yoke 镜像折角口径），避免同名录边跳过 miter 致折叠角缝份缺量。
4. 合并 edges_main = 底层边 ＋ 镜像反转面层边（K1→…→P_w0→…→K1 闭合）。
5. 局部坐标（Y 反射，origin=P_w0）→ 自定向（shoelace>0 则反转，目标 <0 保 cutter 外扩）。
6. 刀口（§5）：P_w0、K1（折叠对位）＋ P1″、P2′（袋口起止；P1″=镜像(P1′/P1)，P2′=镜像 P2）。
7. 标记（marks）：折叠线 P_w0→K1（局部坐标，作画稿折叠指示）。
8. 丝缕（§6）：竖向=经（继承大片裤中线方向），`_vertical_grain`。
9. 缩水（§3）：`warp/weft = front_pouch_shrinkage_*`（默认 0 → 跳过 apply_shrinkage，shrunk=net）。
10. 缝边：sa dict（含 `_m` 变体同值）→ `add_seam_allowance`。
11. 局部 ctx 留命名边供 trace（同 front_pocket_flow `_finish_piece` 口径）。

### 5. 流程列表（`flows/`）
**不入 FULL_FLOW**（裁片另走裁切链）。

### 6. API / CLI
- `api.run()`：新增形参 `front_pouch_svg: str | None = None`；透传 `front_pouch_seam_allowances`
  与 `front_pouch_shrinkage_warp/weft` 到 `PatternOptions(...)`；整版后段加
  `if front_pouch_svg and o.front_pouch: build_front_pouch(ctx) → write_piece_svg`（同 front_pocket_svg 口径，
  `--until` 中断时不生成）。docstring 补 `front_pouch_svg` 说明。
- `cli.py`：`p_draft.add_argument("--front-pouch-svg", ...)`；`_cmd_draft` 加对应分支（同 `--front-pocket-svg`）。

### 7. 金标测试（新建 `tests/test_pouch_piece.py`）
口径同 `test_front_pocket_piece.py`（几何不变量，不硬编坐标）：
- 闭合性（首末端点衔接）、shoelace<0（自定向）、毛样 bbox 不窄于净样（外法向外扩）。
- **镜像对称性**：面层各边 = 底层对应边关于 P_w0-K1 的镜像（节点链/侧缝/腰弧逐对校验）。
- 袋口挖削：面层袋口边 = 镜像(小片袋口)；有省用 `front.pocket_mouth`、无省用 baseline。
- 缩水=0：默认 `shrunk_edges` 为空（或与 net 重合）。
- 刀口：P_w0/K1/P1″/P2′ 在周界上。
- 丝缕竖向；直腰头/弯腰头两 fixture。
- SVG 渲染不报错（`render_piece_svg`）。

## 三、不实现 / 留待后续
- §5.4 袋贴定位刀口（依赖袋贴内边在底层上的投影，复杂，暂缓）。
- 主版布尔裁除仍不实现（口袋/贴袋等仍只上版边界线，本项目既有口径）。
