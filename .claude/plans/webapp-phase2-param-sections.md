# Web 二期：参数面板两段式分组（整版绘制 / 裁片）

> 设计文档（2026-08-25 批准实施），与一期 [webapp-phase1.md](webapp-phase1.md) 同目录惯例。

## 背景

webapp 参数面板原为 18 个平铺分组（`webapp/backend/schema.py` 的 `GROUPS`），多个组内绘制参数与工艺参数混放（如腰头组里 `waistband_type/width` 与 `waistband_seam_allowances/shrinkage_*` 同组）。改为两段式：

- **整版绘制**：一切画在整版 DraftSheet 上的参数（核心测量、款式开关、框架、腰头/口袋/袋布/小表袋/门襟/后机头/后贴袋绘制、腿部弧线、毗围、版面）
- **裁片**：全局缩水/缝边 + 各独立裁片的缝份、缩水率、刀口、裁片构造参数

与引擎架构对齐：FULL_FLOW（先画）vs 裁切链 flow（后裁：cutter 缩水+缝边 → exporters）。已确认：袋布/小表袋/前贴袋/后贴袋/门襟（连裁+独立叠画）/后机头的绘制步骤**全部在 FULL_FLOW 内**，形状/定位参数确属整版；裤耳例外（`build_belt_loop` 不依赖整版几何），整组归裁片。

**归属判定规则**：凡影响整版 DraftSheet 几何 → 整版绘制；凡只影响裁切链（缩水/缝边/刀口/折边撇势/排料方向/裁片构造如双排、整条分片、门襟延展）→ 裁片。

**硬性约定（用户口径 2026-08-25）**：每个裁片的自有工艺参数必须与其裁片同组、不可分割——前后片的缝份/裆尖角/刀口/缩水率合并进 craft_front_piece / craft_back_piece（修复原缩水率被拆到「缩水与缝边」组的不一致）。

## 决策

1. **schema 结构 breaking-change**：`build_schema()` 返回 `{"sections": [...], "adjustable_points": ...}`；消费方仅 ParamPanel、App.tsx、test_web_api.py 三处且全在本仓。
2. **白名单组织**：`GROUPS` → 模块级 `SECTIONS: list[dict]`，每段 `{"key","label","collapsed","groups":[...]}`；组 dict 形状、params 条目（str / (name, gate) 元组）、gate 三种形态、pocket_type/fly_type 虚拟参数特判、`_HIDDEN`、`_ENUMS`、`_param_spec` 全部原样，只换挂载点为双层循环。
3. **前端嵌套 Collapse**（外层 section、内层组）；默认态全部由 schema 的 collapsed 字段驱动（修复前端忽略 collapsed、硬编码 `defaultActiveKey=['measurements']` 的遗留）。
4. **兜底逻辑**：白名单外参数仍追加 misc 组，按 `g["key"]=="misc"` 记录引用，None 则 raise。
5. **组级 gate 无法表达 OR**（前端组级是 AND 语义）：craft_front_pocket 组 gate=None、全参数带参数级 gate（OR），两开关全关时 params 过滤空 → 前端自动隐藏整组。

## 结构（两段 26 组）

### Section `draft`「整版绘制」（15 组，collapsed=False；除 measurements 外各组 collapsed=True）

| key | label | 内容 |
|---|---|---|
| measurements | 基础测量 | 8 项原样，**key 不可变**（前端按 `g.key==='measurements'` 区分值来源） |
| switches | 款式开关 | 原样 |
| frame | 臀腰裆框架 | 原样 |
| waistband | 腰头绘制 | type/width/front_drop/side_rise/front·back_waist_curve_sag（fly_extension/full_piece/grain/seam/shrinkage_* 迁裁片） |
| front_pocket | 前口袋绘制 | 口袋类型下拉+袋口/贴袋形态参数（gate 原样）+ param_visible_if/except 原样 |
| facing | 袋贴 | 绘制 8 项（facing_seam_allowances 迁裁片） |
| pouch | 袋布绘制 | waist_safe/side_safe/nodes/edges |
| watch | 小表袋绘制 | mode/width/taper/offsets/rotate/points/edges |
| fly | 门襟绘制 | fly_type 下拉+共用宽深底角(gate=[fly,fly_separate])+turnback/stitch_inset(gate=fly) |
| back_dart | 后省 | 原样 |
| back_yoke | 后机头绘制 | cb_dist/side_dist/mid_anchors/edges（draft 只画分割下口线） |
| back_patch | 后贴袋绘制 | 定位+形态参数（形态 gate 原样） |
| legs | 腿部与弧线微调 | 原样 |
| thigh | 毗围限制 | 原样 |
| misc | 版面杂项 | 原样（兜底目标，置本段末） |

### Section `pieces`「裁片」（11 组，collapsed=True；组序：全局工艺→各裁片→前后片）

| key | label | params（gate） | 组 gate |
|---|---|---|---|
| craft_global | 全局工艺 | shrinkage_enabled/warp/weft、seam_allowance、show_seam_allowance | 无 |
| craft_waistband | 腰头裁片 | fly_extension、full_piece、grain、seam_allowances、shrinkage_warp/weft | 无 |
| craft_front_pocket | 前口袋裁片 | front_patch_seam_allowances(front_patch)、front_pocket_facing_seam_allowances(front_pocket_facing)、shrinkage_warp/weft([front_pocket,front_patch]) | 无（参数级 OR） |
| craft_pouch | 袋布裁片 | seam_allowances、shrinkage_warp/weft | [front_pouch,front_pocket] |
| craft_watch | 小表袋裁片 | seam_allowances、shrinkage_warp/weft | [watch_pocket,front_pocket] |
| craft_fly | 门襟裁片 | fly_sep_extra/double、fly_seam_allowances、fly_shrinkage_warp/weft（参数级 fly_separate 保留） | fly_separate |
| craft_back_yoke | 后机头裁片 | join_fillet、side/cb_corner_mirror、seam_allowances、shrinkage_warp/weft | back_yoke |
| craft_back_patch | 后贴袋裁片 | top_hem_taper、notch_type、notch_depth、seam_allowances、shrinkage_warp/weft | back_patch |
| craft_belt | 裤耳裁片 | belt_loop_width/unit_length/count/waste | belt_loop |
| craft_front_piece | 前片 | front_piece_seam_allowances/crotch_corner/notch_type/shrinkage_warp/weft | 无 |
| craft_back_piece | 后片 | back_piece_* 同上 | 无 |

注：`front_pocket_seam_allowances` 不存在，实际为 `front_patch_seam_allowances`（options.py 定义、front_pocket_flow 消费）。

## 前端行为

- 嵌套 Collapse：外层 section（defaultActiveKey 由 section.collapsed 驱动），内层组（由 group.collapsed 驱动）；默认态 = 整版段展开+仅基础测量组开，裁片段收起。
- 搜索/错误 Badge/gate-hint 不上卷 section 标题；非搜索态 section 内组全隐则隐 section。
- gateOn/pocketTypeOf/flyTypeOf/errorMap/ParamInput 零改动。

## 验证

pytest tests/test_web_api.py（覆盖测试三层遍历 + 结构测试：段序/组 key 唯一/迁移抽查/前后片同组）→ npm run build → uvicorn 手查（折叠默认态、gate 联动、虚拟下拉、搜索、错误徽标、改值出 SVG）。
