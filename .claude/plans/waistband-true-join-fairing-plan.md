# 腰头独立裁片：真拼合 + 局部圆顺（v0.7）

## Context（为什么改）

**问题**：`front_waist_curve_sag` / `back_waist_curve_sag` 改变整版腰弧形状，但腰头独立裁片形状完全不响应。原因：裁片是**两标量参数化合成**，不是几何拼合——

- [waistband_flow.py:79-118](src/ylpattern/flows/waistband_flow.py#L79-L118) `extract_waistband_spec` 从整版只提取 3 个标量（l_front / l_back / computed_drop），前后腰弧的真实几何（sag、端切线、曲率）在此全部丢弃；
- 下口线用 [curves.py:152](src/ylpattern/draft/curves.py#L152) `waistband_curve(l_half, drop)` 合成抛物线 y=−drop·t²，唯一形状输入是 drop；
- drop 来自 `_auto_drop`（[waistband_flow.py:55-76](src/ylpattern/flows/waistband_flow.py#L55-L76)）：绕侧缝腰点**同侧旋转**对齐后量端点高差——退化拼法（无跨缝反射），实测只还原真实矢高约三成、对 curve_sag 零响应（sag 改的是弧中段凹势，端点高差几乎不动）。

**历史**：2026-08-28 早些时候的会话已实施过 v0.6 真拼合 + v0.6.2 整段单贝塞尔圆顺，被用户整体回退（git 无痕迹，只剩 out/ 产物与 pyc）。回退主因：v0.6 为保后中镜像不出 W 形，在 back_steps 腰弧构造源头加了 `cap_sag_p2_to_start_tangent`，**把 back_waist_curve_sag 限到 ~0.2，用户拒绝主版凹量被削**。次要原因：v0.6.2 整段单贝塞尔重拟合与身片点态偏差 1~2cm。

**用户本次拍板口径**：想要的效果 = 前后腰弧**整体真拼合之后、再圆顺**（ET 手工流程：前后腰头侧缝拼合 → 修顺 → 后中轴对称 → 整根修顺）；**sag 必须全量生效，不加任何上限**。

## 硬约束（不可违反）

1. **`back_steps.py` / `front_steps.py` 的腰弧构造一律不动**——尤其禁止任何形式的 sag 上限/压回（上版回退的直接原因）。两处构造已确认：前弧 [front_steps.py:235-277](src/ylpattern/steps/front_steps.py#L235-L277) `CubicBezier(b, p1, p2, a)`，B 端 90° 法则（柄 `waist_rect_len`）+ `waist_sag_p2(b,a,p1,at=2/3,sag)`；后弧 [back_steps.py:303-329](src/ylpattern/steps/back_steps.py#L303-L329) `CubicBezier(a, p1, p2, b)`，A 端 ⟂ 后中斜线 + `waist_sag_p2(a,b,p1,at=0.5,sag)`。
2. 圆顺 = **局部窗口 blend，不是全局单贝塞尔重拟合**（点态偏差 1~2cm 已被否）；窗口外与拼合弧逐点一致（「无限接近拼合效果」），窗口内重塑 ~mm 级。
3. **段数仅随选项集变化**（直/弯、后省数 0~2、口袋省有无、fly），同一 options 跨码恒定（推码跨码对应，多码 DXF 不能因码漂移边数）。
4. 直腰头维持代数求和矩形不动，其全路径零改动；弯腰头省道**真闭口**（绕省尖旋转闭合；后腰省 + 前口袋吃省均经常出现，用户 2026-08-28 确认必须支持）——长度收敛到省闭后净长，闭口折角由圆顺窗消化。
5. cutter / pieces / exporters 不动（同名 role 边平滑续接已支持，[cutter.py:674-675](src/ylpattern/cutter.py#L674-L675)）。
6. 分层红线：新曲线工具进 `draft/curves.py`；flow 私有 helper 留在 waistband_flow（yoke_flow 先例）。

## 设计方案

### 1. `draft/curves.py`：新增 `g2_blend`（置于 `waist_sag_p2` 之后），删 `waistband_curve`

```python
def g2_blend(p0: Point, t0: Vector, k0: float, p1: Point, t1: Vector, k1: float, *,
             h_init: float | None = None, max_iter: int = 20, tol: float = 1e-9
             ) -> CubicBezier | None
```

- 构造 B0=P、B1=P+t0·h0、B2=Q−t1·h1、B3=Q（t0/t1 沿行进方向单位切向，h>0 待求），两端全匹配 (位置, 切向, 曲率)。令 D=Q−P、a=cross(t0,D)、b=cross(t1,D)、c=cross(t0,t1)，解联立：`F0: (2/3)(a−h1·c)=k0·h0²`、`F1: (2/3)(b+h0·c)=k1·h1²`（κ 符号约定同 `CubicBezier.curvature_at`）。
- 求解：Gauss-Seidel 定点（首选，每式对另一变量线性，≤8 轮；侧缝窗两端切向夹角 <1°，c≈0.017 耦合极弱）→ 2×2 牛顿兜底（解析雅可比，仅 κ 与 c 同时趋零才奇异）。初值 h0=h1=h_init（≈0.4×窗长，与 yoke `_g1_fillet` 手柄尺度同量级）。
- 接受判据：残差 <1e-9、h∈(1e-3, 1.5|D|]、无 NaN；不满足返回 **None**（调用方回退 G1）。
- 同文件**删除 `waistband_curve`**（改造后无消费者）；tests/test_curves.py 删其两个单测、增 `g2_blend` 单测（圆弧复现 R=20 端 κ 精确/中点偏离 ≤0.2%·R；无解返 None；直线退化 k=0,c=0 → None→G1 口径；+κ 左弯符号约定）。

### 2. `flows/waistband_flow.py`：几何提取 + 反射拼合（删 `_auto_drop`）

私有 helper（yoke `_rotate_geom` 风格，全用现有原语 `Point.rotate_around` / `Vector.perpendicular`）：

- `_xform_bezier(b, f)`：4 控制点过映射 f。
- `_place_front_arc(front_arc, hip_front, back_arc, hip_back) -> CubicBezier`：
  ① θ = 前后**真实侧缝线**（侧缝腰点 B→臀围外缝点弦向，结构稳定，沿 `_auto_drop` 取材口径）的夹角；
  ② 前弧绕 B_front 旋转 θ、平移使 B_front→B_back；
  ③ **跨后片侧缝线反射** v′ = 2·v_par − v —— 物理平摊缝拼合（v0.6 验证口径；旧 `_auto_drop` 同侧旋转是退化口径）。
- `_local_frame(back_arc, hip_inner_back) -> (origin, X̂, Ŷ)`：origin = A_back = back_arc.p0；X̂ = unit(back_arc.tangent_at(0))——90° 法则已保证 X̂ ⟂ 后中斜线 ⇒ 局部 Y 轴 ∥ 后中斜线（= 物理后中缝方向、镜像轴）；Ŷ = X̂ 的垂向中朝下者（与 unit(hip_inner_back−origin) 点积为正）。
- `_to_local(geom, origin, X̂, Ŷ)`：v=q−origin → Point(v·X̂, v·Ŷ)。

**省道闭口（提取阶段、主版坐标；闭口先于拼合放置——均为刚体变换、次序可换）**：

- `_close_back_darts(arc, ctx) -> tuple[CubicBezier, ...]`：后省按 A→B 顺序物理闭省——每次在**当前链**上求省腿线 ∩ 弧（线-贝塞尔求交，提升 [yoke_flow.py:98-134](src/ylpattern/flows/yoke_flow.py#L98-L134) 复用），绕省尖 `back.dart{i}_apex` 旋转远侧子链（控制点 `Point.rotate_around`，精确保贝塞尔性），**同步变换后续省的腿/尖**（物理等价的共轭复合）；闭口即切除省口弧段（长 ≈ 省宽）。几何载体 `back.dart{i}_leg_inner/leg_outer`（线段）+ `apex`（点）；存在性/宽度守卫同现行 back_w 求和口径。
- `_close_pocket_dart(arc, ctx) -> tuple[CubicBezier, ...]`：前口袋吃省——P1=`front.pocket_p1`、P1′=`front.pocket_p1_transfer` 均在弧上（`t_at_length` 复参），切除中段，远侧（前中侧）刚体变换使 P1′→P1 **且切向对齐**（C1 闭口 = 吃省缝平物理口径）；守卫同现行 front_w 口径。
- 闭口折角（后省 θ≈atan(省宽/省腿长)，可达 10°+）是圆顺窗的输入之一，见 §3。

`extract_waistband_spec` 弯腰头分支：取 `front/back.waistline_arc` → **闭省** → `_place_front_arc` → `_local_frame` → 分段 `_to_local` → 存 spec；`l_*` = 闭省后链实长（直腰头分支原样代数扣减）。上/下腰弧 <0.5cm 容忍口径沿用（按用户口径与 ADJUSTABLES 绑定均取上腰弧）。

`WaistbandSpec` 重构：删 `computed_drop`；`l_front/l_back/l_half`（直=扣省代数和；弯=闭省后链实长，报表/丝缕用）；新增 `back_chain`、`front_chain: tuple[CubicBezier, ...] | None`（闭省后局部系分段链，无省时 1 元组；back 首 t=0=后中原点，front 首 t=0=侧缝点）。

`_project_corner_notches`（[waistband_flow.py:128-174](src/ylpattern/flows/waistband_flow.py#L128-L174)）名称按模式解析，加 `_edge(local, name)` helper：弯腰头下后中端切向载体 `wb.bottom_right`→`wb.bottom_right_cb_blend`（blend 后起端切向恰 = X̂，「原点垂线」语义不变）、前中端→`wb.bottom_right_front`、`wb.top_right`→`wb.top_right_front`、fly=0 分支 `wb.top_left/bottom_left`→对应 `*_front` 端段。

### 3. `steps/waistband_steps.py`：弯腰头链式绘制（直腰头分支零改动）

- 新增 `_bottom_chain(o, spec) -> list[tuple[str, CubicBezier]]`（弯腰头，**一般化规则：起端（后中）+ 每个链内接缝各开一个 G2 圆顺窗**）：
  ```
  接缝 = 闭省接缝（每个后省 1 个、口袋省 1 个）+ 侧缝拼合点（back_chain 末 ∩ front_chain 首）
  每个接缝：两侧各退 w = min(0.4·邻段长, max(0.25, o.waistband_blend_side))，
            段 = g2_blend(入侧@割点 全匹配, 出侧@割点 全匹配)，失败回退 _g1_blend
  起端（后中）：w_cb = min(0.4·首段长, max(0.25, o.waistband_blend_cb))；
            段 = g2_blend(原点, X̂, κ(t1), 首段@t1 的点/切向/κ)——κ0=κ(t1) 等曲率穿窗，走曲率符号守卫
  余段 = bezier_subrange(原链段, …)   # 窗口外逐点 = 闭省拼合弧
  ```
  - 半片下口段数 = **4 + 2×d**（d = 后省数 + 口袋省 0/1）：无省 4、1 省 6、3 省（2 后省+口袋省）10——仅随选项集变化、同 options 跨码恒定；整片边数 = 4×(4+2d) + 4（直 8 不变）。
  - 命名（按后中→前中遍历序）：起端窗 `wb.bottom_right_cb_blend`；接缝窗按事件命名 `wb.bottom_right_dart{i}`（后省 i）/ `wb.bottom_right_mid_seam`（侧缝）/ `wb.bottom_right_pdart`（口袋省）；余段 `wb.bottom_right_back{k}` / `wb.bottom_right_front{k}`。
  - 闭省折角大（可达 10°+），窗长统一用 `waistband_blend_side`、0.4×邻段钳制自然限幅；多窗不相交由钳制保证（相邻余段 ≥ 0.2×段长）。
- **后中段曲率符号守卫**（在 waistband_steps 内，不进 g2_blend）：窗内采样 8 点 κ 与 k_ref 同号（或零）且 local y ≥ −0.02（不上鼓穿起端切线）；违例 → 窗宽 ×1.5 重试一次 → κ0 减半 → G1 回退。镜像 C2 依据：过原点、切 X̂ 的曲线，镜像+反向参数化在原点曲率自动相等——起端切向 = X̂ 即后中 C1/C2 保证，W 形只能来自窗内上鼓，守卫封死（**无需限 sag**）。
- 新增 `_g1_blend(p0, t0, p1, t1, h)`（[yoke_flow.py:223-242](src/ylpattern/flows/yoke_flow.py#L223-L242) `_g1_fillet` 同口径）。
- 上口对应 4 段：每段 `CubicBezier(p0+n_s·W, p1+n_s·W, p2+n_e·W, p3+n_e·W)`（段两端口各用端法向平移——段内端切向严格 ∥ 下口，平移性质），段接头法向取两侧平均保共点 ⇒ 上口链自动 C1；两端（前中/后中）用单侧端法向，right_end 仍与端切向严格直角。
- 镜像/搭门/封边/刀口/丝缕：逐段化，复用现有 `_mirror_x/_reverse/_end_tangent/_up_normal`（已按单几何参数化，天然兼容）。`draw_wb_*` 签名 (ctx, spec) 不变。
- `EDGE_ORDER` 常量 → **由链构造器派生**：`_bottom_chain` 同一函数产出有序 (name, role) 清单，绘制与装配共用单一事实源（直腰头仍旧 8 项不变）；弯腰头按遍历序组装 bottom/top 多段 + `right_end`/`left_end`/`top_fly`/`bottom_fly`（fly=0 装配滤零长边）。
- cutter/pieces/exporters 零改动（同名 role 多边平滑续接已验证）。

### 4. 参数面：删 `waistband_front_drop`、增两个圆顺窗长

| 文件 | 改动 |
|---|---|
| [params/options.py](src/ylpattern/params/options.py):477、:570-572 | 删字段+校验；新增 `waistband_blend_cb: float = 3.0`、`waistband_blend_side: float = 2.5`（校验 0<x≤10） |
| options.py `from_dict`（:928 附近） | 一次性垫片 `raw.pop("waistband_front_drop", None)` + stderr 告警——TOML 链 `from_file→from_dict→cls(**raw)` 对未知键抛 TypeError，垫片保旧尺寸单过渡一版 |
| [api.py](src/ylpattern/api.py):134、:321、:648 | 删形参/docstring/透传（顺带消除 api 默认 1.5 ≠ options 默认 None 的既有不一致）；新增两窗长透传 |
| [webschema.py](src/ylpattern/webschema.py):229 craft_waistband 组 | 删该键、加入两个窗长参数（前端 schema 驱动，grep 证实无硬编码） |
| examples/size_female_zhitong.toml:262、size_female_165.toml:254 | 删注释行（本就不生效） |

### 5. 文档 [.doc/裁片/腰头裁片.md](.doc/裁片/腰头裁片.md) v0.5 → v0.7

§二参数增删；§三改写为「直=代数求和（不变）；弯=上腰弧真拷贝 + **省道绕尖旋转闭口**（后省/口袋省，长度收敛净长）」；§四分支B 重写（真拼合 → 接缝圆顺窗一般化规则：后中 + 每个闭省接缝 + 侧缝 → 后中镜像 → 上口多段偏移 → 边名由链构造器派生）；§五加「段数仅随选项集变化」推码注记；版本头 v0.7 + 变更记录（写明 v0.6 cap_sag 被拒、v0.6.2 全局重拟合偏差 1~2cm 教训 → 局部窗口 blend 的动机）。

## 实施顺序

1. `curves.g2_blend` + test_curves 单测（先行，独立可验）
2. options / api / webschema 参数面（含 from_dict 垫片）
3. waistband_flow 几何提取（含省道闭口 `_close_back_darts`/`_close_pocket_dart`）+ 反射拼合 + WaistbandSpec 重构（删 `_auto_drop`、删 `waistband_curve` 调用）
4. waistband_steps 链式绘制 + `edge_order(o)`
5. `_project_corner_notches` 名称适配
6. tests/test_waistband_piece.py 重写 + 新金标
7. 文档 v0.7、examples 清理
8. 全量测试 + 出图目检

## 验证

**单测**（`python -m pytest tests/ -q` 全绿）：

- 重写：`test_piece_net_edges_closed`（参数化：直 8；弯按 d=省数合计 = 4×(4+2d)+4，无省 20、fly0 再 −2）、`test_piece_curved_top_normal_offset`（链式：上口端差 ⊥ 下口端切向且 =W、上口相邻段共点 1e-12、下口链总长 ≈ L_back+L_front）、`test_curved_ends_right_angle` / `test_notches_*`（边名换链端段）、`test_options_validation`（drop raise 删、窗长越界 raise 增）。
- 删除：`test_dynamic_drop_auto/_override/_straight_is_zero`（drop 语义亡）、`test_waistband_curve_drop_zero_is_line/_length_exact`（函数删除）。
- 新增 `test_curved_join_placement`（替代 drop 三测）：缝点共点（spec.front_arc.p0 == spec.back_arc.p3）；前中 local y > 0 且 < 8（拼合后前中低于后中，物理 drop 显影）；前弧起切向与后弧末切向开角 > 90°（反射方向正确性守卫）。
- 新增金标：
  - **(a) sag 响应**（用户原始投诉的回归测试）：CURVED 两版 back_waist_curve_sag=0.2 vs 0.4 → spec.back_arc 弦中点下凹 == sag（构造保证）；裁片 `bottom_right_back` 段中点对未圆顺弦偏离 ≥ 0.9×sag；Δ矢高 ≥ 0.15cm。
  - **(b) 拼合保真**：窗口外（back_rest/front_rest 全采样）与参考链 [back_arc, front_arc] 偏差 ≤ 0.01cm；blend 端点位置 1e-9、切向角差 <1e-6°、κ 比 <1e-6（G2 达成时）；窗口内偏差 ≤ 1.0cm 且量级 ~mm。
  - **(c) 后中无 W**：cb_blend 采样 κ 同号；窗内 y ≥ −0.02；镜像对称 |chain(x)−chain(−x)| < 1e-9。
  - **(d) 侧缝接缝连续**：seam_blend↔front_rest 端切向角 < 0.01°、κ 比 < 1e-3（G1 回退路径仅断言切向同向）。
  - **(e) 推码不变量**：同一 options 两码（不同 Measurements）弯腰头 `len(net_edges)` 相等（= 4×(4+2d)+4）。
  - **(f) 省道闭口金标**：闭后链长 == 原弧长 − Σ省口弧段长（1e-9），与现行代数扣减交叉验证差 < 3%（弧 vs 弦二阶量）；腿重合角 < 1e-6；双后省累积用例；P1′→P1 精确重合且闭口处切向连续；闭口接缝圆顺后切向角 < 0.01°、κ 比 < 1e-3。

**出图目检**：

```bash
python -m ylpattern.cli draft --size examples/size_female_zhitong.toml \
    --svg out/zhitong_sheet.svg --waistband-svg out/zhitong_wb.svg
# A/B：back_waist_curve_sag 0.2 与 0.4 各出一张腰头 SVG，肉眼确认裁片弧度随 sag 响应、后中无尖峰/W 形
# 再出一版弯腰头+后省+口袋吃省（开 options），确认闭省处圆顺无鼓包、下口总长 ≈ 净腰围（闭省后净长）
```

- Web 端（引擎改了要重打包）：`cd webapp/frontend && npm run build:engine`，`npm run dev` 后拖 `front/back.waistline_arc` 把手（ADJUSTABLES 已绑定 sag）→ 腰头裁片随动。

**完成后**：更新记忆——`waistband-drop-degenerate-join`/`waistband-splice-fairing` 改为 v0.7 局部圆顺口径；`waistband-p2-same-side-guard` 标注 cap 方案已被用户否决、改由符号守卫+局部圆顺实现。

## 风险与边界

- **推码不变量**：段数只依赖选项集（直弯/省数/fly），窗长比例钳制（0.4×邻段）+ 正下限 → 同 options 任一码段数恒定；装配零长滤除（1e-9）永不触发（窗长下限 ≥ 0.25cm ≪ 腰弧 20cm+）。
- **省道求交退化**：省腿近并行弧切线时线-贝塞尔求交不稳 → 抛错可溯源（不静默忽略）；省口跨弧端点等病态由存在性/宽度守卫前置拦截。
- **退化清单**：κ 方程无解（h 越界→None→G1）；c≈0 且 κ≈0（直线窗→G1）；fly=0（18 边 + 刀口 fly=0 分支换名）；直腰头全路径未动（现有直腰头测试即回归网）；反射方向错由 test_curved_join_placement 开角守卫兜底。
- **性能**：每半片 2 次 blend，定点 ≤8 + 牛顿 ≤20 轮 O(1)，远轻于既有 t_at_length 采样二分，无感。
- **ADJUSTABLES / front_pocket 零触碰**：P1/P1′ 弧上点、foot_on_bezier 投影均属整版步骤；v0.4「不打省位/侧缝刀口」口径不变。
