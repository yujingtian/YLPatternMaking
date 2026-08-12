# 腰头裁片（直/弯、有/无省）程序化方案

## 依据
- 权威文档：[.doc/裁片/腰头裁片.md](.doc/裁片/腰头裁片.md) v0.3（净样 -> 缩水 -> 缝边三段式，独立 SVG）
- 工程设计：[.doc/python工程设计.md](.doc/python工程设计.md) §5.5 裁切层（cutter/pieces 尚未实现，本任务奠基）、§10.3 图层
- 长度提取源：[front_steps.py](src/ylpattern/steps/front_steps.py) `draw_front_waist_outseam_curves` 产物 `front.waistline_arc`（阶段4，t=0 侧缝 B -> t=1 前中 A）；[back_steps.py](src/ylpattern/steps/back_steps.py) `draw_back_waistband_arc` 产物 `back.waistline_arc`（阶段3，t=0 后中 A -> t=1 侧缝 B）
- 省位源：前省 = 前口袋吃省 `front_pocket_dart_width`（阶段8 `draw_front_pocket`，P1 自侧缝沿腰弧量取 `front_pocket_p1_dist`、P1′ 再量 dw）；后省 = `draw_back_darts` 产物 `back.dart{i}_leg_inner` 端点 p_in（省口内侧=后中侧，阶段9）

## 核心几何（腰头裁片.md §三~§五）

**代数求和与侧缝拼合推算**（§三）：
- `L_back = back.waistline_arc.length() − Σ(活跃后省宽 w_i)`
- `L_front = front.waistline_arc.length() − (front_pocket_dart_width，若 front_pocket 且 dw>0)`
- `L_half = L_front + L_back`
- **弯腰头下沉量 (Drop) 2D 拼合推算**：在平面内，读取前后片腰围线与**真实侧缝线（而非侧缝端点处的腰线切线）**的几何夹角。以侧缝腰点为圆心，旋转前片腰弧，使前片侧缝线与后片侧缝线完全重合。测量旋转后，前中点相对于后中点的纵向高度差，得出绝对精准的 `computed_drop`。（若用户手动指定 `waistband_front_drop`，则覆盖此计算值）。
- 口径：直/弯腰头统一读**上腰弧** `front/back.waistline_arc`（用户指引阶段4/3；弯腰头下腰弧为贴身边，差 <0.5cm，§三「代数求和」口径容忍）

**基础轮廓（半片，局部坐标系：原点=后中 O(0,0)，Y向下，X向右）**：
- 直腰头：矩形 L_half × `waistband_width`，底边水平
- 弯腰头：底边 = 长度精确等于 L_half 的三次贝塞尔（新增 `curves.waistband_curve`）：P0=(0,0) 后中、P3=(X, `computed_drop`) 前中下沉、**P1=(X/3, 0) 保证后中切线水平以利于镜像、P2=(2X/3, computed_drop/3) 生成均匀抛物线弧（两端自然倾斜斜出，彻底解决S型畸变）**；右端法向封闭；二分求 X 使 `length()==L_half`。**上口线与端点 = 基于底边进行真实的法向平移（Offset）生成，解决端点垂直一刀切导致的缝合畸变问题。**

**刀口（§三.2，自后中沿下口线量取净弧长，单刀口）**：
- 后省对位点（如有）= 后腰后段 = `p_in` 投影到 `back.waistline_arc` 的弧长（精确；新增 `_arc_length_of_point` 采样最近 t -> `split(t)[0].length()`）
- 侧缝对位点 = `L_back`
- 前省对位点（如有）= `L_back + front_pocket_p1_dist`（前腰后段，P1 自侧缝沿弧量取）

**对称 + 搭门（§三.3）**：`waistband_full_piece=True` 以 x=0 后中线为轴镜像半片至左侧（刀口同步镜像）；左片前中端外延 `waistband_fly_extension`（直角封口；宝剑头/圆角留后续）

**裁切三段（§五，Cutter 严格顺序）**：
1. 净样 = 上述闭合轮廓 + 刀口
2. 缩水 = 仿射缩放 `x·(1+shrinkage_warp)`、`y·(1+shrinkage_weft)`（腰头长向=经、宽向=纬），刀口同步偏移
3. 缝边 = **缩水后**净样各边外扩（上口 −top、下口 +bottom、左端 −left_end、右端 +right_end；后中为折线不外扩），独立缝份角点阶梯连接；**缝份不叠加缩水**

## 改动链条（CLAUDE.md：选项 -> 公式/曲线 -> 裁片层 -> 步骤 -> 流程 -> 输出 -> 接口 -> 金标）

### 1. PatternOptions（[params/options.py](src/ylpattern/params/options.py)）
腰头一组（`waistband_width` 后）新增：
- **`waistband_front_drop: float | None = None`** - 弯腰头前中下沉量（cm）。**默认 None 为系统根据真实侧缝线夹角自动推算**；填入数值则强制覆盖手动微调。
- `waistband_fly_extension: float = 3.5` - 门襟搭门量（cm，左片前中外延）
- `waistband_full_piece: bool = True` - True=整条（本期实现）；False=沿后中分两片（留后续）
- `shrinkage_warp: float = 0.0` / `shrinkage_weft: float = 0.0` - 经/纬向缩水率（0.03=3%）
- `waistband_seam_allowances: WaistbandSeamAllowances` - 新建 frozen dataclass（top=1.0/bottom=1.0/left_end=1.2/right_end=1.0；`from_dict` 接 TOML 子表）

`__post_init__`：若填 front_drop 则 ≥0、fly_extension≥0、shrinkage∈[0,0.2)、各缝份≥0。`from_file` 支持 `[options.waistband_seam_allowances]`。

### 2. 公共曲线（[draft/curves.py](src/ylpattern/draft/curves.py) 新增 `waistband_curve`）
`waistband_curve(length, drop) -> CubicBezier`：**二次抛物线近似（单端水平 + 端点斜出）** + 二分求 X 闭环 length；docstring 标注腰头裁片.md §四.分支B。

### 3. 裁片层（新建 [pieces.py](src/ylpattern/pieces.py) + [cutter.py](src/ylpattern/cutter.py)）
`pieces.py`：
- `PieceEdge(name, geom: LineSegment|CubicBezier)` - 命名边（top/bottom/left_end/right_end）
- `PatternPiece(name, net_edges, notches, grain, label, shrunk_edges=(), shrunk_notches=(), gross_edges=(), gross_notches=())` - 净/缩水/毛三态

`cutter.py`：
- `apply_shrinkage(piece, warp, weft) -> piece'` - 仿射缩放 net_edges+notches 填 shrunk_*
- `add_seam_allowance(piece, allowances) -> piece'` - 对 shrunk_edges 各边按缝份外扩（直线 `offset` / 曲线控制点平移），角点阶梯连接，填 gross_*（刀口取缩水后位置）

### 4. 腰头步骤（新建 [steps/waistband_steps.py](src/ylpattern/steps/waistband_steps.py)）
`WaistbandSpec`（frozen dataclass）：**新增 `computed_drop: float` 字段**；l_front/l_back/l_half、back_dart_notches/front_dart_notch/side_notch、has_*_dart。步骤签名 `(ctx, spec) -> NamedElement`（自含裁片，非 FlowRunner 编排，同 closure.py 口径）：
- `draw_wb_bottom_edge` / `draw_wb_top_edge` - 下/上口线（直=LineSegment，弯=`waistband_curve` **基于 `computed_drop`**，且上口线采用**真法向偏移算法**，非垂直平移）
- `draw_wb_ends` - 半片两端竖直线（后中 + 前中，**前中端点顺延弧线法向倾斜封闭**）
- `draw_wb_mirror` - 镜像左半片边元素
- `draw_wb_fly_extension` - 左端外延 fly_extension
- `draw_wb_notches` - 刀口点（半片 + 镜像）
- `draw_wb_grain` - 丝缕线（长向水平线 + 箭头）
各步 `ctx.add_*` 上版独立 sheet，docstring/basis 标注腰头裁片.md 章节。

### 5. 腰头流程（新建 [flows/waistband_flow.py](src/ylpattern/flows/waistband_flow.py)）
- `extract_waistband_spec(main_ctx) -> WaistbandSpec` - 读 `front/back.waistline_arc` + 省元素，代数求和算净长 + 投影算刀口位。**新增逻辑：废弃平面腰头切线对齐法（会导致向上旋转抵消落差），改用读取真实的裤身侧缝线倾角，模拟纸样旋转直至侧缝重合，推导出极其精准的前中下沉量 `auto_drop`。将 `auto_drop`（或用户覆盖值）填入 `computed_drop`**。
- `build_waistband(main_ctx) -> PatternPiece` - 建 local DraftContext -> 跑步骤 -> 装 PatternPiece(net) -> `apply_shrinkage` -> `add_seam_allowance` -> 返回三态裁片
- `_arc_length_of_point(curve, p)` - 采样最近 t -> `split(t)[0].length()`（后省 p_in 投影用）

### 6. 输出（新建 [exporters/piece_svg.py](src/ylpattern/exporters/piece_svg.py)）
`render_piece_svg(piece) / write_piece_svg(piece, path)`：局部坐标 **Y 向下不翻转**（区别于整版 svg.py），仅缩放平移；图层：gross（实线 #2c3e50 最终裁切线）+ shrunk_net（虚线）+ net（淡虚线）+ notches（红色短垂线）+ grain（双向箭头）+ 标注（片名/净长宽）。

### 7. 接口（[api.py](src/ylpattern/api.py) + [cli.py](src/ylpattern/cli.py)）
- `api.run(..., waistband_svg: str | None = None, ...)` - 整版跑完后 `build_waistband(ctx)` -> `write_piece_svg`；新增 waistband_* 参数透传 PatternOptions
- `cli.py` `draft` 加 `--waistband-svg` 旗标

### 8. 金标测试（新建 [tests/test_waistband_piece.py](tests/test_waistband_piece.py)）
M=Measurements(waist=70,hip=96,knee=46,hem=36,front_rise=25,back_rise=33,outseam=102,thigh=58)，`FlowRunner(M,O).run(FULL_FLOW)`：
- **净长**：无省 L_half=前+后腰弧长；有省 L_half=弧长−省宽（前后独立校验）
- **2D 侧缝拼合 Drop**：测试不指定 `waistband_front_drop` 时，系统能否通过前/后真实侧缝线的几何重合，推算出精准的 `computed_drop`；测试指定数值时是否成功覆盖。
- **端点法向闭合**：验证弯腰头的左右端点是否呈自然法向倾斜，不再是垂直直线。
- **刀口位**：侧缝=L_back；后省=p_in 投影弧长；前省=L_back+p1_dist；刀口在下口线上、镜像对称
- **轮廓闭合**：首尾相接；直腰头矩形对边等长。
- **缩水**：各点 x·(1+warp)、y·(1+weft)；刀口同步
- **缝边**：gross 各边距 shrunk_net=对应缝份；角点=net角±缝份
- **SVG**：生成不抛错、含 gross/net/grain
- **边界**：弯腰头 drop=0 退化直线；缝份负数 raise；shrinkage 越界 raise

## 范围决策
实现腰头裁片.md §二~§五 全流程（净样 -> 缩水 -> 缝边 -> 独立 SVG），覆盖 直/弯腰头 × 有/无省 四组合。**本期不做**：
- `waistband_full_piece=False`（沿后中分两片）—— 默认 True 整条先通
- 宝剑头/圆角封口 —— 直角封口先通
- DXF 导出、结构校验器（§5.8，独立任务）