# 牛仔裤打版系统 —— Python 工程设计文档

> 版本：v0.5
> 日期：2026-09-07
> 关联文档：[打版流程.md](../打版流程.md)、[前后片臀围推导.md](前后片臀围推导.md)、[决策日志.md](决策日志.md)（口径演进史归档）
>
> v0.5 修订：§十瘦身为纯规格态（日期叙事/废弃方案/纠偏过程归 [决策日志.md](决策日志.md)）、裁切层踩坑独立为 §10.10、§一~九与当前实现对账（非目标/路线图/裁切层现状）。
> 早期修订（v0.2 核心架构、v0.3 曲线绘制策略、v0.4 §十迁入）见决策日志。

---

## 一、项目概述与核心设计理念

将牛仔裤手工打版过程工程化：**手工打版时打版师的每一笔（定一个点、画一条线），在程序中都有且仅有一个对应的生成函数**。程序不"整体生成裁片"，而是像打版师一样，按照制定好的流程逐步绘制。

### 1.1 三条核心设计原则

#### 原则一：每个点、每条线 = 一个具名生成函数

- 打版流程中的每一个绘图动作（"从外侧缝向右量取臀围宽度得到内侧缝线"、"在立裆线上取前裆点"）都实现为独立函数；
- 函数命名与打版步骤一一对应，可追溯到打版文档的具体步骤；
- 每个函数返回一个**具名绘图元素**（NamedElement），携带名字、几何体、来源步骤，全程可查询、可调试、可标注。

```python
def front_hip_width_point(ctx: DraftContext) -> NamedPoint:
    """前片步骤：从外侧缝参考线向右量取 H前，得到内侧缝参考点。
    依据：打版流程.md §前片打版实操坐标化步骤 1"""
    ...
```

#### 原则二：流程编排（Pipeline）驱动绘制

- 打版步骤被声明为**有序的步骤列表**（Flow），编排器按序调用，逐步把元素画到"版"上；
- 步骤之间通过**绘图上下文（DraftContext）**传递已生成的元素 —— 后续步骤引用前面步骤产出的点/线（如"以步骤 3 的裆点为起点"），绝不重复计算；
- 流程本身可读、可调：可以只执行到第 N 步输出中间状态（调版时看基础线框架），也可以插入/替换单个步骤（换版型）。

#### 原则三：先画后裁（Draft-then-Cut）

- 前片、后片在**同一张版（DraftSheet）**上按真实打版方式依次完整绘制（后片常叠加借用前片的参考线）；
- 全部绘制完成后，由**裁切器（Cutter）**按闭合轮廓把每个裁片一个一个独立"裁"出来：前片、后片、腰头、Yoke……各自成为独立的 `PatternPiece`；
- 裁出的裁片带自己的局部坐标、净样/毛样轮廓、对位记号，进入输出层。

### 1.2 设计目标

| 目标 | 说明 |
| :--- | :--- |
| **步骤可溯源** | 每个元素能回答"我是谁、由哪一步生成、依据哪条公式" |
| **结果可复算** | 同一参数输入输出完全确定，无随机无隐藏状态 |
| **流程可中断** | 可执行到任意步骤输出中间版（基础线框架/关键点版），辅助调版 |
| **裁片可校验** | 裁出后做结构校验（臀围闭合、侧缝等长、裆弯顺滑等） |
| **输出可生产** | SVG 供预览调版，DXF 供 CAD/裁床 |

### 1.3 非目标（当前阶段不做）

- 层 3 放码点云 / 反测读取器（推码二期预留；多码推码核心已实现——尺码表 + 逐码重打版 + 多码单文件 DXF，见 §10.6 推码条目）
- 主版布尔裁除（口袋/贴袋等仍只上版边界线；独立裁片走各自 flow 从整版提取）

---

## 二、技术选型

| 类别 | 选型 | 理由 |
| :--- | :--- | :--- |
| 语言 | Python ≥ 3.10 | dataclass / 类型注解适合几何建模 |
| 核心计算 | 纯标准库（`math`） | 公式均为代数运算，核心层零第三方依赖 |
| 曲线 | 自实现三次贝塞尔 | 打版曲线控制点少，无需 NURBS 库 |
| 预览输出 | 手写 SVG 生成器 | 轻量、浏览器直接查看、支持分层 |
| 生产输出 | `ezdxf`（可选依赖） | DXF 对接 CAD / 自动裁床 |
| 参数校验 | `dataclasses`（必要时 pydantic v2） | 尺寸单校验与序列化 |
| 测试 | `pytest` | 标准选型 |

---

## 三、坐标系约定（全局唯一约定）

与 [打版流程.md](../打版流程.md) 保持一致：

```
        Y ↑（朝向腰头，代表裤长）
        │
  腰围线 ─────────────────
  臀围线 ─────────────────
  立裆线 ─────────────────
  膝围线 ─────────────────
  脚口线 ─────O──────────→  X（朝向内侧缝，代表裤宽）
        (0,0) = 外侧缝参考线 ∩ 脚口水平线
```

- 单位 **cm**，内部一律 `float`，仅输出层按需保留 1~2 位小数；
- **整张版共用一个全局坐标系**（前后片在同一坐标系绘制，符合手工打版习惯）；裁切为独立裁片时，由 Cutter 负责把轮廓转换到裁片局部坐标系；
- 坐标一律使用不可变值对象 `Point(x, y)`，禁止裸 tuple。

---

## 四、整体架构

```
┌──────────────────────────────────────────────────┐
│ 接口层  cli/        命令行入口、尺寸单加载           │
├──────────────────────────────────────────────────┤
│ 输出层  exporters/  SVG（分层）/ DXF / 尺寸报表     │
├──────────────────────────────────────────────────┤
│ 裁切层  cutter.py   从版上按闭合轮廓逐个裁出裁片    │
│         pieces.py   PatternPiece（净样/毛样/记号）  │
├──────────────────────────────────────────────────┤
│ 流程层  flows/      前片流程、后片流程：有序步骤编排  │
├──────────────────────────────────────────────────┤
│ 绘制层  draft/      绘图上下文 DraftContext         │
│                     版 DraftSheet（元素容器）        │
│                     具名元素 NamedPoint/Line/Curve  │
├──────────────────────────────────────────────────┤
│ 步骤层  steps/      ★ 核心：每个点/线的生成函数      │
│                     （front_steps / back_steps）    │
├──────────────────────────────────────────────────┤
│ 公式层  formulas/   纯函数公式库（臀围/裆/腰/腿）     │
├──────────────────────────────────────────────────┤
│ 几何层  geometry/   Point / Line / Bezier / Polygon │
├──────────────────────────────────────────────────┤
│ 参数层  params/     Measurements / PatternOptions   │
└──────────────────────────────────────────────────┘
```

### 目录结构

目录结构以 `src/ylpattern/` 实际代码为准。步骤层按部件分文件：`front_steps` / `back_steps` / `front_pocket_steps` / `front_pouch_steps` / `front_fly_steps` / `back_yoke_steps` / `back_patch_steps` / `waistband_steps`；`draft/curves.py` 为公共弧线库；`reverse/` 为工厂 DXF 反解析（与 cli/api 同层）。**外围薄壳**（不在引擎包内、依赖方向只许壳 → 引擎）：`webapp/`（Web 端 + Pyodide 本地引擎，§10.7/§10.8）、`agent/`（全部大模型代码，§10.9）。未实现模块（validation）见 §10.6。

---

## 五、核心模块设计

### 5.1 参数层 `params/`

```python
@dataclass(frozen=True)
class Measurements:
    waist: float        # 腰围（成品）
    hip: float          # 臀围 = 净臀围 + 放松量
    knee: float         # 膝围
    hem: float          # 裤口
    front_rise: float   # 前浪
    back_rise: float    # 后浪
    outseam: float      # 裤长
    thigh: float        # 大腿围

@dataclass(frozen=True)
class PatternOptions:
    delta: float = 1.0               # 前后片臀围单侧调节量（Δ 预设见推导文档 §四）
    front_crotch_adjust: float = 0.0 # 前小裆修正（紧身款 -0.5~-1.0）
    waistband_type: WaistbandType = WaistbandType.STRAIGHT
    fit: Fit = Fit.REGULAR
    seam_allowance: float = 1.0
```

尺寸单支持 **TOML**（推荐，`#` 行内注释，可读性好）与 JSON 两种格式，按扩展名自动识别，保存为"客户尺寸档案"。

### 5.2 绘制层 `draft/` —— 元素、上下文、版

**具名元素**：所有绘制产物的基类，携带三重身份信息：

```python
@dataclass(frozen=True)
class NamedPoint:
    name: str            # 语义名，如 "front.crotch_point"（前裆点）
    geom: Point
    step: str            # 生成它的步骤函数名
    basis: str = ""      # 依据（公式/文档章节），用于报表与调试
```

`NamedLine`、`NamedCurve` 同理。元素**不可变**，生成后只增不改。

**绘图上下文 DraftContext**：步骤函数之间唯一的协作通道。

```python
class DraftContext:
    measurements: Measurements
    options: PatternOptions
    sheet: DraftSheet

    def add(self, element: NamedElement) -> None: ...      # 上版
    def point(self, name: str) -> Point: ...               # 取前面步骤的点
    def line(self, name: str) -> LineSegment: ...
```

规则：**步骤函数只能通过 context 读取前面步骤的元素**，禁止函数间直接传参几何体 —— 这样任意中断点处的 sheet 都是完整自洽的中间版。

**DraftSheet**：整张版的元素容器，提供按名称/类型/步骤的查询，以及按图层导出。

### 5.3 步骤层 `steps/` —— 每个点、每条线一个函数

这是系统的核心。以前片基础框架为例（对应 [打版流程.md](../打版流程.md) 前片步骤 1）：

```python
# steps/front_steps.py —— 每个函数对应手工打版的一笔

def draw_hem_line(ctx) -> NamedLine:
    """脚口参考线：过原点 O(0,0) 的水平线。"""

def draw_knee_line(ctx) -> NamedLine:
    """膝围参考线：脚口线上移（裤长 − 膝位高）。"""

def draw_crotch_line(ctx) -> NamedLine:
    """立裆参考线：脚口线上移（裤长 − 前浪）。"""

def draw_hip_line(ctx) -> NamedLine:
    """臀围参考线：立裆线上移立裆深的 1/3（经验，可调）。"""

def draw_waist_line(ctx) -> NamedLine:
    """腰围参考线：脚口线上移裤长。"""

def draw_front_hip_width(ctx) -> NamedPoint:
    """臀围宽度点：从外侧缝参考线向右量取 H前 = H/4 − Δ。
    依据：前后片臀围推导.md §三.1"""

def draw_inner_seam_refline(ctx) -> NamedLine:
    """内侧缝垂直参考线：过臀围宽度点的铅锤线 → 完成大矩形框架。"""
```

约束：
- **一个函数只画一个元素**（一个点或一条线/曲线），组合动作由 Flow 编排，不在函数内嵌套；
- 函数内所有数值计算必须调用 `formulas/`，步骤函数只做"定位与上版"，不写公式；
- 函数 docstring 写明：打版动作、依据的文档章节、引用了哪些已有元素。

### 5.3.1 曲线（弧线）绘制策略

打版弧线由 `draft/curves.py` 的参数化公共函数生成。规则：能用公共函数就用（形状仅由参数区分）；裁片特有、公共函数表达不了的曲线允许步骤自行构造贝塞尔控制点，docstring 写明依据；判断标准是「被两处以上使用或预期反复调参 → 收进公共库」。公共曲线函数的每个参数都必须是有物理意义的量（cm、角度、弦长比例），禁止纯形状魔法数。实际函数清单与签名直接读 `draft/curves.py`（docstring 自带说明，§10.2 已改为指向代码）。

### 5.4 流程层 `flows/` —— 有序编排

流程就是一个**声明式的步骤列表**：

```python
# flows/front_flow.py
FRONT_FLOW = [
    # —— 阶段 1：建立基础参考线与"大矩形"框架 ——
    draw_hem_line,
    draw_knee_line,
    draw_crotch_line,
    draw_hip_line,
    draw_waist_line,
    draw_front_hip_width,
    draw_inner_seam_refline,
    # —— 阶段 2：裆部结构 ——
    draw_front_crotch_extension,   # 小裆宽 W小裆 = H/20
    draw_front_crotch_curve,       # 前裆弯（贝塞尔）
    # —— 阶段 3：腰、侧缝、内缝、脚口 ……（随打版文档补全逐步扩充）
]

# flows/back_flow.py 同理；后片步骤可通过 context 引用前片已有参考线
```

**FlowRunner** 的能力：

```python
runner = FlowRunner(measurements, options)
runner.run(FRONT_FLOW + BACK_FLOW)           # 全流程
runner.run(FRONT_FLOW, until="draw_hip_line")  # 只画到臀围线（调版）
runner.run(FRONT_FLOW, trace=True)           # 逐步打印"画了什么、依据是什么"
```

- `until` 中断：输出任意中间状态的版（如只看"大矩形框架"）；
- `trace` 追踪：逐步输出"步骤名 → 生成元素 → 关键数值"，相当于把打版过程写成带数值的操作记录；
- 换版型 = 替换/插入步骤函数（如小脚裤替换脚口收放步骤），流程机制不变。

### 5.5 裁切层 `cutter.py` —— 先画后裁

前后片绘制完成后，Cutter 按闭合轮廓从版上逐个圈取裁片 → 净样三态（net/shrunk/gross）→ 局部坐标 → 缩水 + 缝边偏移 → 刀口/记号，产出独立 `PatternPiece`。已为全部独立裁片落地（腰头/机头/前口袋/袋布/门襟/小表袋/后贴袋/前后大片；裤耳净裁不走 cutter）；主版布尔裁除未实现（口袋等只上版边界线）。各裁片口径见 §10.6 分条目。

### 5.6 裁片 `pieces.py`

`PatternPiece`：net/shrunk/gross 三态轮廓 + 刀口（shrunk/gross 双位）+ 内部标记 marks + 定位孔 drills + 丝缕线 + notes；`apply_shrinkage` / `add_seam_allowance`（含 hem 袋口折边、corner_treatments 角部处理）分步生成。

### 5.7 输出层 `exporters/`

SVG（整版调版预览分图层 + 独立裁片 SVG）+ DXF（生产：整版一张 / 裁片合集 AAMA 块结构 / 多码推板）+ 报表（中间尺寸 + trace 记录）。图层与 role 渲染见 §10.3，DXF 口径见 §10.3.1。

### 5.8 校验器 `validation.py`

裁片裁出后做结构校验：臀围闭合（2×(H前+H后) = H ± 0.05）、前后侧缝/内缝等长（差 ≤ 0.3 cm）、裆弯拼接顺滑（切线夹角 ≥ 170°）、轮廓闭合无自交。失败告警不中断，结果附报表。**尚未实现**，规则容差待实现时细化。

---

## 六、典型使用流程

命令行用法见 [CLAUDE.md](../CLAUDE.md)「常用命令」（`ylpattern draft --size ... --svg/--trace/--report`，支持 `--until` 中断调版与各独立裁片 `--xxx-svg` / `--pieces-dxf` 出口）。尺寸单 `size.toml`（TOML，支持 `#` 注释）格式：

```toml
[measurements]
waist      = 70    # 腰围（成品）
hip        = 96    # 臀围 = 净臀围 + 放松量
knee       = 46    # 膝围
hem        = 36    # 裤口
front_rise = 25    # 前浪
back_rise  = 33    # 后浪
outseam    = 102   # 裤长
thigh      = 58    # 大腿围

[options]
delta = 1.0                 # 前后片臀围单侧调节量
fit = "regular"             # skinny / slim / regular / loose
waistband_type = "straight" # straight 直腰头 / curved 弯腰头
```

---

## 七、测试策略

| 层级 | 测试内容 |
| :--- | :--- |
| `formulas/` | 文档公式金标测试：手工演算值作 expected，逐公式对照 |
| `steps/` | **步骤契约测试**：每步产出的元素名存在、几何值与金标一致、引用的前置元素已存在 |
| `flows/` | 中断测试：任意 `until` 点中断，版状态自洽；步骤缺失依赖时报清晰错误 |
| `cutter/` | 裁片闭合、轮廓无自交、局部坐标正确、记号归属正确 |
| 端到端 | 固定尺寸单 → SVG 快照对比（防回归） |

原则：经验值可随打版实践调整，但**每次调整必须同步更新金标测试与函数 docstring 的依据注释**，保持代码-文档-测试三方一致。

### 7.1 金标测试写法速查（写新步骤前先看，免读旧测试）

**模块头**：固定一组规范量体 `M` + 选项 `O` 挂模块级，文件头 docstring 写明该参数下的手工演算金标值。前/后片步骤测试共用：`M = Measurements(waist=70, hip=96, knee=46, hem=36, front_rise=25, back_rise=33, outseam=102, thigh=58)`、`O = PatternOptions(delta=1.0, ...)`；直腰头扣腰头宽 4 → 腰线 y=98、后浪闭合目标 33−4=29。

**fixture**：`@pytest.fixture()` 返回 `FlowRunner(M, O).run(FLOW)`，测试函数以 `ctx` 入参取元素。前片用 `FRONT_FLOW`、后片用 `FULL_FLOW`（后片读前片基准线，必须整版跑）。

**断言口径**：
- 浮点 `== pytest.approx(v)`；`Point` 不可直接 approx，逐坐标 `assert a.x == pytest.approx(b.x)` 或手写 `_assert_point_approx(a, b)` 辅助。
- 上游坐标是算出来的（机头端点、腰弧顶点等）时，**用几何不变量断言**而非硬编坐标：边长 `distance_to`、平行 `cross≈0`（叉积 `a.dx*b.dy - a.dy*b.dx`）、垂直 `dot≈0`（点积）、方向（`.y <` / `.x >`）。
- **独立复算**：期望值用文档公式从 ctx 上游元素重新推出（如后贴袋测试自建 û/v̂），不复用步骤内部逻辑，方为真金标。

**每个可选步骤特征的标准测试集**（照此覆盖，缺一不可）：
- `_skipped_by_default`：开关关 → 元素不在 `ctx.sheet`；
- 依赖缺失：前置开关关 → `pytest.raises(ValueError, match=...)`；
- 定位锚点 / 关键点金标值；
- 各形态变体（rectangle / baker_shield / angular / custom）逐个；
- 旋转（若支持）：刚性（边长不变）+ 方向；
- 弯腰头变体（若腰头敏感）；
- `_no_seam_allowance_at_draft_stage`：先画后裁，无毛样（cut）元素；
- `_options_validation`：每个 `ValueError` 分支一条 `pytest.raises`；
- 归一化（`_custom_edges_normalized` 等）：列表入参 → 元组化校验。

文件命名 `tests/test_<部件>_steps.py`（如 `test_back_patch_steps.py`）；公式层金标见 `tests/test_waist.py` 等（推导文档案例直转）。


---

## 八、开发路线图

> 2026-09 对账：M1~M5 已全部交付；M6+ 中后约克（后机头/育克）与放码推板（多码 SizeRun）已实现，版型库未做；另落地了规划外的大门襟/袋布/小表袋/后贴袋/裤耳等独立裁片链、工厂 DXF 反解析、Web 端/本地引擎/agent（§十）。本表留档初始规划，现行实现态以 §十 为准。

| 阶段 | 内容 | 产出 |
| :--- | :--- | :--- |
| **M1 骨架** | params + geometry + draft（元素/上下文/版）+ formulas/hip.py | 可跑通"画五条参考线+大矩形"并输出 SVG |
| **M2 前片全流程** | 前片全部步骤函数：裆部、腰、侧缝、内缝、脚口 | 单前片完整绘制 + trace 记录 |
| **M3 裁切与输出** | Cutter + PatternPiece + 裁片 SVG/DXF | 前片独立裁出，净/毛样输出 |
| **M4 后片** | 后片步骤：后翘、后立裆斜线、大裆弯、Yoke 预留分割线 | 前后片同版绘制、成套裁片 |
| **M5 腰头与完善** | 直/弯腰头、校验器完善、报表完善 | 可交付生产文件 |
| **M6+（二期）** | 后约克、放码推板、版型库（小脚/阔腿/工装） | —— |

> 注意 M1 的目标就是"大矩形框架"——与打版流程文档前片步骤 1 完全对应，每一步都可可视化验证后再往下走。

---

## 九、风险与对策

| 风险 | 对策 |
| :--- | :--- |
| 打版步骤文档尚未写全（目前只有前片基础框架一节），步骤函数无法一次实现完整 | 架构支持**增量补步骤**：Flow 是列表，文档补一节，steps 加几个函数即可；M1 先打通机制 |
| 步骤间元素名依赖写错，运行到一半才报错 | FlowRunner 启动前做**静态依赖检查**：解析每个步骤声明的 `requires`，提前发现缺失 |
| 经验公式多流派，数值有争议 | 经验值一律收敛到 `PatternOptions`，步骤函数与公式函数只实现机制 |
| 浮点精度导致校验误报 | 校验统一容差（默认 0.05 cm），舍入只发生在输出层 |

---

## 十、实现态速查（以代码为准）

> 本节由 [CLAUDE.md](../CLAUDE.md) 的"工程速查"迁入（v0.4），记录已实现代码的实操约定。上文 §一~九为目标设计态，遇不一致以本节与实际代码为准。
>
> **只写现行规格（v0.5 起）**：口径变更的日期、废弃方案与纠偏过程一律归 [决策日志.md](决策日志.md)；本节引用处只标「演进见决策日志」。

### 10.1 局部特征框坐标系

口袋 / 袋布 / 门襟等特征上版时常另建**局部坐标系**按文档推导——取特征锚点为局部原点 O，两轴沿特征的两条基准方向：
- 门襟 O = 前浪 ∩ 裤身顶边，Y 沿前浪下行、X 垂直前浪朝外凸；
- 袋布 O = 腰外缝顶点，x 朝门襟、y 向下。
- 后贴袋 O = 育克底线 ∩ 后浪线（机头后浪端点 `back.yoke_cb_point`），u 自后浪朝侧缝（沿约克底线）、v 向下；u 轴沿约克底线方向（非全局水平），θ=0 袋口 ∥ 约克底线 ≈ 后腰线。依赖 back_yoke。
- 腰头裁片 O = 后中点，**X 向右朝前中、Y 向下**（与全局版坐标 Y 向上相反！），半片置于 x>0，full_piece 时镜像至 x<0。绘制在独立 DraftSheet（`flows/waistband_flow.build_waistband` 另建 ctx，非主版 sheet）；下口线弧长自后中（O）起算。

局部 → 全局：`o_pt + x_dir.scale(x) + y_dir.scale(y)`（`x_dir = y_dir.perpendicular()`）。**看步骤代码先认局部框**，否则坐标会读反。

### 10.2 几何 API：直接读代码

`geometry/`（Point/Vector/LineSegment/CubicBezier）与 `draft/curves.py` 的签名、行为**以代码为准**，docstring 已标注易踩坑点（`LineSegment.length` 是属性、`CubicBezier.length()` 是方法、`Vector.perpendicular()` 逆时针 90° 归一化、`tangent_at` 未归一化、`t_at_y` 要求 y 单调、`Point - Vector` 不支持只支持 `Point - Point→Vector`/`Point + Vector→Point` 故点减向量写作 `p + v.scale(-1)`；`Point(x, y)` 直接构造的点没有 dx/dy/normalized〔向量属性在 Vector 上，须经 `p − q` 得 Vector 再做向量运算〕）。文档不重复维护，避免代码-文档双线失步；需要时直接读对应模块。

### 10.3 role 与 SVG 渲染（exporters/svg.py）

- `NamedLine.role` / `NamedCurve.role`：`"struct"`（结构线，实线深色 #2c3e50）/ `"ref"`（参考线，灰虚线 #999 dasharray）。`NamedLine` 默认 `ref`，`NamedCurve` 默认 `struct`。
- SVG 图层顺序（后绘盖上）：`reference`(ref 线) → `struct`(struct 线) → `curves`(全部曲线，按 role 分 `.curve` 实线 / `.curveref` 虚线) → `elements`(点)。要让某条**曲线**画虚线，给 `add_curve(..., role="ref")`（曲线默认 struct 实线，现已支持 role 生效）。
- 注意：§5.7 的图层表（net/seam/annotation…）原为设计期设想；`cutter.py`/`pieces.py` 已为腰头裁片落地（独立 SVG），`validation.py` 仍尚未实现。
- 独立裁片 SVG（`exporters/piece_svg.py`）：裁片局部坐标 **Y 向下**，渲染时**不翻转**（仅缩放平移），区别于整版 `svg.py`（版坐标 Y 向上、渲染翻转）。图层：net/shrunk_net 净样轮廓（深色 **#2c3e50 实线**主轮廓，2026-08 用户口径；两者互斥——net 仅在未缩水时绘制、已缩水省略，缩水时唯一内轮廓基准是 shrunk_net，两条内轮廓并存易误读曾致用户把未缩水净样认成多余轮廓）/ gross 毛样缝边线（**橙色 #e67e22 实线**，与净样区分色，最终裁切线）/ notches（红）/ grain 丝缕线（蓝）/ marks 内部标记弧线（绿虚线 `.markline`，袋贴的袋口净线/吃省边、前片的臀/膝/毗围辅助线等，净样坐标、随缩水同比例变换）。缝边显示总开关 `show_seam_allowance=False` 时（`render_piece_svg(show_seam=False)`）：毛样 gross 层不绘制、画布 bbox 收缩回净样、刀口**整层不绘制**（缝边刀口随缝边同步隐藏，净线位刀口一并隐藏；DXF 侧仍回退净线刀口，§10.6 缝边显示总开关条目）。

### 10.3.1 DXF 输出（exporters/_dxf_base.py + dxf.py + piece_dxf.py）

裁床切割/服装 CAD（富怡/ET/格柏）口径，CLI `--dxf`（整版一张）+ `--pieces-dxf`（全部裁片平铺合一张），api.run 同名参数。依赖 ezdxf（可选 extra `dxf`，exporters 内 lazy import，未装且传参时 RuntimeError 带安装指引；核心零依赖不变）。

- **版本 R12（AC1009）+ 折线**：实体白名单仅 LINE/CIRCLE/2D POLYLINE/TEXT（LWPOLYLINE/SPLINE/MTEXT 均 R13+，R12 下 ezdxf 抛错）；闭合用 `close=True` 不追加重复尾点；R12 无线宽/true color（CAD 端按颜色打印样式）。
- **单位 mm**：坐标 cm×10；R12 无 $INSUNITS（R2000+），以 TEXT "UNITS=MM (DXF R12)" 兜底声明。
- **曲线离散**：`_dxf_base.flatten_bezier` 弦高公差递归（判据=控制点到弦垂直距离上界，de Casteljau split 精确细分），默认公差 0.01cm=0.1mm（裁床典型精度），max_depth=12 防病态输入；共线控制点直接两端点。
- **全 ASCII**：层名与 TEXT 均 ASCII（R12 单行 TEXT + cp1252/SHX 跨软件易乱码），元素标注取 name、裁片标注取 piece.name + 净长宽数字，中文 label 只留在 SVG。 TEXT 字高 TEXT_HEIGHT_MM=10mm（2.5mm 在 ET 08 下几乎不可见）。
- **图层映射**：整版 REF(8,DASHED)/STRUCT(7)/CURVE(7)/POINT(1)/TEXT(7)，role->层与 SVG 同口径（ref 虚线入 REF）；**裁片合集用 AAMA 数字图层**（服装 CAD 不识别 CUT/NET 等自定义英文层名，是老软件解析失败黑屏的主因之一）：`piece_dxf._LAYER_MAP 语义->ET08 方言数字层（层号逆向 ET08 自导出件，不照搬标准 AAMA）：1=裁切轮廓+片名与魔法标签信息文本 / 14=净样+缝合线（NET 与含缩水净样 SHRUNK 同落 14——ET08 方言净样层、必为闭合环，见下条）/ 8=内部画线（臀/膝/毗围围度辅助线、袋口净线、省弧--MARK 落 8；**净样禁落 8**，ET08 会当普通内部线白色显示不识别）/ 3=普通轮廓顶点/放码点（**非刀口层**，勿放刀口）/ 4=刀口专属层：POINT 必附组码 30（Z 深度，NOTCH_Z_MM=1.524）与组码 50（开口角度，取 `_notch_segment` 内法向在 mm 输出系方向 atan2(-dy,dx)，局部系 Y 向下、输出 Y 翻转；缺角度 CAD 不知开口朝向、不显示）；**且 ET 按裁切折线顶点吸附挂接刀口符号，段中间的刀口点不显示**——腰头刀口恰与阶梯角顶点重合而能显示、机头延长线交缝边点全在段中而集体不显示（第五轮实测修订）。顶点吸附还隐含**切线可判**要求：刀口恰落 miter/阶梯**角顶点**（两侧折线不共线）时 CAD 无法判定开口方向、渲染成十字孤立点（门襟刀口 2026-08 报障即此）——刀口生成端（各 flow `_project_notches`）须保证落点在**段中或共线顶点**上（共线插入成顶点后两侧折线共线、切线唯一），角点命中的刀口不得走法向均值（角平分）投到 miter 顶点。修法 `piece_dxf._with_notch_vertices`：CUT 折线把落在其上（垂距 ≤1e-3cm）且严格段中的刀口点**共线插入为顶点**（几何不变、其他 CAD 无副作用，`_render_piece_into` 写 CUT 时统一施加）；不在折线上的刀口（后片卷边起折等内部位标记、未做毛样投影的净位刀口）不插也不挂边符号/ 13=定位孔专属层：单纯 POINT（CAD 读 AAMA 见层 13 POINT 自动渲染标准、不受缩放影响的钻孔十字/圆圈符号）/ 7=纱向线。**坑**：刀口/定位孔的表示历经四轮实测修订，现行口径：刀口=层 4 POINT+组码 30/50、定位孔=层 13 单纯 POINT；历史方案均废弃--「POINT+TEXT 成对」会把定位孔误渲染成放码刀口（_add_mark_text 已删）、「层 3 纯 POINT」混淆了顶点层与刀口层、「层 8 真实 CIRCLE」r=0.5mm 过小完全不可见；ezdxf 对 height=0 有创建期钳制（回默认 2.5），若再需字高 0 只能文件级后处理，落错层（如辅助线落层 2）会被默认隐藏--围度辅助线曾因 MARK 落层 2 在 ET 里不可见；实测 ET 08 层 8 显示最稳，内部线归 8 恢复；层 "0" 为 DXF 保留层不可重建，文本并入层 1；三态/回退规则同 piece_svg；缝边显示总开关 show_seam_allowance=False 时层 1 CUT 闭合折线不绘制（层 1 片名/标签文本照常）、刀口同回退净线口径（§10.6）。
- **净样 = 层 14 闭合环（ET08 方言，逆向 5336 大货样本，2026-08 实测坑）**：净样/含缩水净样整圈链成**一条闭合 POLYLINE 落层 14**，与层 1 毛样闭合环同构成对（ET08 自导出件每片即"层 1 闭合毛样环 + 层 14 闭合净样环"，层 14 环对层 1 环内缩恒为缝份，实测样本 3.0/5.1/12.7/16.5mm 等距；样本另见层 2 POINT=对位点、层 3 POINT=放码点/轮廓顶点，本工程未用）。两个坑：① **层号**——标准 AAMA 净样在层 8，但 ET08 的层 8 只是普通内部线，净样落 8 显示白色散线、不被识别为缝合线，且 ET 以毛样轮廓兜底 → 毛样净样重叠；② **闭合**——逐边各写一条开放折线同样被当散线（`_render_piece_into`：net/shrunk_edges 本是有序闭合轮廓，逐边离散点直接首尾相接成一点列，`add_polyline(closed=True)` 统一去接口重复点与闭合首尾点）。marks 内部画线（袋口净线/省弧/围度辅助线）为真开放线、落层 8。金标：tests/test_piece_dxf.py `test_net_shrunk_exclusive`（层 14 每片恰 1 条闭合环 + 顶点数=各边离散点首尾相接去重；层 8 只剩开放 marks）。
- **AAMA 块结构（裁片合集）**：每片一个 BLOCK（块名={片名}-{尺码} 组合〔如 WAISTBAND-30，多尺码同文件不冲突，2026-08 起；此前仅 piece.name〕，ASCII 大写化/去非法字符〔字母数字/下划线/连字符，清洗正则放行连字符〕/截 31 字符/唯一化，块内为片局部 mm 坐标），Model Space 仅放 INSERT（插入点=平铺偏移）+ 全局声明 TEXT--服装 CAD 按块识别"一个裁片"，散线无法归组。块与块引用必须显式落层 1（block.block.dxf.layer 与 add_blockref(dxfattribs={"layer": ...})）：默认层 0 会被 ET 08 直接过滤丢弃（解析为空白）。`set_extents` 的 bbox 收集相应支持 INSERT 展开（`_collect_bbox`，块内容按块缓存、插入点+缩放+旋转变换；本工程恒等变换）。块中央另有 AAMA 信息 **5 行魔法标签** TEXT（`Piece Name:` / `Size:` / `Annotation: `〔无注释留空但此行必须存在〕/ `Quantity:` / `Category: {逐片序号}`〔0 起递增——ET08 自导出件实测为片序号，需求.md 原定"固定填 1"不准确〕，ET08 不按图层名识码、靠抓取图层 1 内这 5 行固定格式文本自动重构裁片尺码表〔逆向大货 DXF 所得，需求.md §3.2〕；全落层 1、字高 10mm、行距 1.5 倍字高=15mm 垂直等距、**Piece Name 在最下、块系 mm Y 逐行 +15 递增**〔屏上自下而上，ET08 自导出件同构；初版曾写反为自上而下〕、整组以片 bbox 中央居中；**块内标签只管片级信息，ET08 底部尺码栏（"*" ↔ 尺码号）的数据源是模型空间 6 行全局文档头**〔`_add_doc_header`：Style Name / Creation Date / Author / Sample Size / Grading Rule Table / Units: METRIC，图层 1、行距 15mm 自上而下——两份大货样本（5336/5156）同构逆向；2026-08 实测只补块内标签尺码栏仍为 "*"；`render_pieces_dxf`/`write_pieces_dxf` 新增 `style_name="noname"` 参数填 Style Name/Grading Rule Table 两行，暂无订单元数据来源〕；图层映射同步**静态固化**——禁止任何"动态尺码图层"重构，图层重命名触发 ET08 严格图层校验直接黑屏；`render_pieces_dxf(size=, qty=)` 由调用方传入，默认 "-" / 1，PatternPiece 不携带尺码数量；size 来源 = `PatternOptions.size_label`，cli/api 两入口统一透传 `o.size_label`（2026-08 起接通，此前两入口均未传、DXF 恒显示 "SIZE: -"），TOML `[options]` 主表键 `size_label`）。
- **999 注释组**：`_dxf_base.save_doc(doc, path, comment=)` 写盘后在文件最前手动前置 999 标识（AAMA_NOTE = "ANSI/AAMA"，老版软件对长字符串强校验失败，必须短标识）--ezdxf 的 `Drawing.comments` 在 R12 导出时**不落盘**（实测无 999 组码），999 允许出现在任意记录间、解析器按注释跳过；换行风格跟随原文件。附：ET08 自导出件连 HEADER section 都没有（999 + BLOCKS + ENTITIES 即全部）；本工程保留白名单最小 HEADER 供 ezdxf 回读/回归断言，ET08 亦兼容。
- **裁片坐标**：局部系 Y 向下，块内变换 X=(x-x0)*10、Y=(y1-y)*10，平铺偏移全落在 INSERT 插入点上 -- 翻转后 DXF 显示与 SVG 屏幕视觉逐点重合、手性不变（不镜像）；shelf 行装箱平铺（行宽上限 200cm、片间距 3cm）。
- **刀口/定位孔画法**：裁片合集见上条图层映射（刀口=层 4 POINT+组码 30/50，定位孔=层 13 POINT）；整版 dxf.py 无刀口、定位孔=r0.5mm CIRCLE（DRILL_RADIUS_MM）；`NOTCH_LEN_CM=0.5` 专供 `_notch_segment` 求刀口内法向方向算组码 50（不再画 LINE 刻线，POINT+30/50 是现行口径）；丝缕线 LINE+TEXT "GRAIN"（省略箭头）。
- **范围变量（老 CAD 黑屏坑）**：`saveas -> update_all()` 会用 **modelspace 布局属性** `msp.dxf.extmin/extmax/limmin/limmax` 覆写同名 header 变量，布局属性默认是 (±1e20) 哨兵值/A3 图幅——只写 header 会在写盘时被冲掉。`_dxf_base.set_extents(doc)` 在渲染完成后按实体 bbox 把值设到 **msp.dxf 上**（header 同步直写供保存前内存读取）；老服装 CAD（ET 2008 等）直接拿 $EXTMIN/$EXTMAX 做初始视图/全图缩放，哨兵值导致打开黑屏，AutoCAD 自行重算无碍。回归断言在**回读文件**上（内存断言抓不住 save 时覆写）。
- **R12 兼容清洗（ET 08 打不开/解析空白）：**ezdxf 写出的 R12 带大量老服装CAD 兼容性差的可选特性。_dxf_base.save_doc 写盘后经 _strip_r12_compat 把文件裁成「最小 HEADER + BLOCKS + ENTITIES」AAMA 骨架（对照实测 ET 能直开的大货DXF：999 ANSI/AAMA + BLOCKS，无 TABLES、无一个 group 5）：① TABLES 等 BLOCKS/ENTITIES 以外的 section 整段剔除；② HEADER 只留白名单 $ACADVER/$DWGCODEPAGE/$EXTMIN/$EXTMAX（完全无 HEADER ezdxf 回读直接 IndexError，$EXTMIN/$EXTMAX 是 ET 初始视图依据不能丢）；③ 块名 $/_ 开头的 ezdxf 骨架块（$Model_Space/$Paper_Space/_ARCHTICK）连实体到 ENDBLK 整块剔除；④ 全部 handle 对（group 5）与 1001 XDATA 块剔除。按组码-值严格成对解析过滤，不碰坐标值。**坑**：组码右对齐带空格（'  0'），字符串比较前必须 strip；section 名在SECTION 对的**下一对**（2 码），别误取 "SECTION" 自身。另外 AAMA 块与块引用必须显式落层 1（默认层 0 被 ET 08 直接过滤丢弃、解析为空白），AAMA_NOTE 用短标识 "ANSI/AAMA"（长字符串老版强校验失败），TEXT_HEIGHT_MM=10mm（2.5mm 在 ET 08 下几乎不可见）。
### 10.4 架构约束细节

- 依赖链 `cli/api → exporters → flows → steps → draft → formulas → geometry → params`：**禁止反向**。尤其 `params/`（最底层）**不能 import `formulas/`**（formulas 在其上方）——需公式参与的跨字段校验放**步骤层**（步骤可调 formulas），`PatternOptions.__post_init__` 只做单字段范围校验。
- `formulas/` **只依赖标准库**（`math`），输入输出纯 float，不碰 geometry/params。
- `steps/` 只做定位与上版：数值调 `formulas/`，几何构造调 `geometry/` 与 `draft/curves.py`，经验常数读 `PatternOptions`。
- `reverse/`（工厂 DXF 反解析）与 cli/api 同层：**只 import params + geometry + 标准库**，禁入 flows/steps/draft/formulas/exporters；ezdxf 仅 `reader.py` 惰性引入（同 exporters/_dxf_base 口径，缺依赖 RuntimeError 带安装指引）。TOML 发射手写序列化器（tomllib 只读不写，核心零依赖），发射前经 `Measurements.from_dict` + `PatternOptions.from_dict` 回验——写引擎读不进的文件不如不写。

### 10.5 排版与 Unicode 编码踩坑指南

代码与文档的中文标点是**全角 Unicode**，不是 ASCII。用 Edit 工具替换时 `old_string` 必须用对应字符，否则不匹配：
- 箭头 `→` = U+2192（注释"A → B"用它，**不是** ASCII `->`；只有类型注解 `-> float` 才是 ASCII）。
- 破折号 `—` = U+2014（不是 `--`）；减号 `−` = U+2212（不是 `-`）。
- `°`(度)、`×`(乘)、`§`(节)、`≈`(约) 均为 Unicode。
- 替换含这些字符的段落若不匹配，改用**按 ASCII 标记截取**（Python 脚本 `s[s.index(start):s.index(end)]`）或只替换纯 ASCII 子串；heredoc `python3 <<EOF` 在 Windows Git Bash 会挂起，写脚本文件再 `python` 运行。
- 纯中文注释行（如段头 `# -- 袋布（pouch）：…§一~§五）--`，无 ASCII 子串）连单行整配也失配时：改用 Python 脚本按附近 ASCII 行（如字段声明 `front_pouch: bool = False`）的 `line.startswith(...)` 定位行号、按行号 insert，彻底避开中文匹配。
- **Windows 环境两个反复出现的坑**：① `git stash pop` 会被已跟踪的 `__pycache__/*.pyc` 冲突卡住（error: would be overwritten by merge，stash 保留但工作树退回 HEAD）——先 `find src -name '__pycache__' -type d -exec rm -rf {} +` 再重新 pop（已连续两次踩中）；② Windows 控制台默认 GBK，CLI 不带 `--svg/--report` 直接打印全量报表时，报表文本含的全角减号 `−`(U+2212) 触发 `UnicodeEncodeError`——加 `PYTHONIOENCODING=utf-8` 环境变量或输出到 `--report` 文件即可，非代码缺陷。
- **示例尺寸单是活文件，测试勿断言其可变状态**：examples/ 两份尺寸单使用者会随手改（开关 show_seam_allowance / size_run.enabled、改 order 码序）——test_size_run_api 已两度被绊（order 改 27-32 六码、enabled 关掉致 load_size_run 返回 None）；需断言示例内容时复制到 tmp_path 并归一可变行（正则强制 `enabled = true`）再加载，原文件只测"不抛错"（2026-08 定此口径）。
- **缝边尖点曲率峰在端点不在中点**：判「缝份 ≥ 内凹曲率半径（sa·κ ≥ 1）」只算 t=0.5 的 κ 会漏判——端部控制柄急转时 κ(0) = (2/3)·cross(P1−P0, P2−2P1+P0)/|P1−P0|³ 可远超中点（2026-08 test_cutter 对照用例实测 κ(0)≈1.9 vs κ(0.5)≈0.10）；金标/检测须全程扫 κ。相关口径：缝边偏移（`cutter._offset_points_adaptive`）、外延偏移（`_extrapolate_offset`）、净样 flatten（`exporters/_dxf_base.flatten_bezier`）三处公差统一 0.1mm——`cutter.SEAM_OFFSET_TOL_CM` ↔ `_dxf_base.FLATTEN_TOL_CM` 同值锚定，依赖方向禁止核心层 import exporters，改公差两处同改。
- **浮点左结合乘除会在端点越界**：`total * k / (n-1)` 左结合时 fl(total·k) 舍入可上冲，除回 (n−1) 后微超 total，等弧长重采样的游标推进循环在 k=n−1 处走完末段再取 `points[seg_i+1]` 即 IndexError（reverse/geomops.resample_chain，5028 真件首发、5015 浮点运气好未触发）——先除后乘 `total * (k/(n-1))` + `min(·, total)` 钳制；凡"游标推进 + 浮点比较"的同构写法都要防端点。

### 10.6 当前实现状态（已程序化）

已实现：前片（`front_steps`）、后片（`back_steps`）、前口袋 + 袋贴（`front_pocket_steps`，含弯腰头+有省量时 P1/P1′ 延长至上腰头线；袋贴 `draw_front_pocket_facing` 详见下文）、袋布（`front_pouch_steps`）、前贴袋、小表袋、门襟（`front_fly_steps`，连裁/独立两形态）、后机头/育克（`back_yoke_steps`，弯/直腰头两端点弧长量取 + 下口线 N 点分段拓扑）、后贴袋（`back_patch_steps`，育克底线∩后浪线定位 + 局部 u-v 框四形态 + 仿射旋转）、毗围闭环（`flows/closure.py`）、腰头裁片（`steps/waistband_steps` + `flows/waistband_flow` + 裁切层 `pieces`/`cutter` + `exporters/piece_svg`，腰头裁片.md v0.9：直/弯腰头 × 有/无省，净样 -> 缩水 -> 缝边独立 SVG；直 = 代数求和矩形、弯 = 前后腰弧真拼合 + 省道闭口 + 整根均匀圆弧，`build_waistband(main_ctx)`）。裁切层（`pieces.PatternPiece` 三态净/缩水/毛 + 可选 `marks` 内部标记弧线〔净样坐标、随缩水同比例变换、不随缝边，前片裁片.md §3.3〕+ `cutter.apply_shrinkage`/`add_seam_allowance`〔含 `hem=` 袋口折边参数，`HemTreatment`〕）已为腰头、后机头、前口袋（袋贴/贴袋）、袋布（一片式对折）、门襟（单排/双排）、小表袋、后贴袋、前片大片落地（`add_seam_allowance` 的缝份参数鸭子类型化：任意字段名=边名的缝份 dataclass〔`WaistbandSeamAllowances`/`FrontFacingSeamAllowances`/`FrontPatchSeamAllowances`/`FlySeamAllowances`/`WatchPocketSeamAllowances`/`BackPatchSeamAllowances`/`FrontSeamAllowances`，cutter `_sa_amount` 走 `getattr`〕 或 边名→量 dict，机头用 `{top,bottom,cb,side}`），后片大片已随后片裁片落地（见下文）；**裤耳裁片是唯一不走 cutter 的裁片**（净裁，见下文条目）。尚未实现：结构校验器。

腰长不变量（公式层 `formulas/waist.py`）：**纸样腰长 = 成品目标 + 该边缘所有省口宽合计**——省只改形、不改缝后长度。`waist_front_target` 增 `pocket_dart` 形参（前口袋吃省 ΔW 经守卫 `pocket_dart_takeup(pocket_enabled, dart_width)` 计入：口袋开关开启且 >0 才生效，`front_steps` 腰线两步调用）；`waist_back_target` 增 `darts` 形参（后腰省省口合计经守卫 `back_darts_takeup(dart_enabled, widths)` 计入：开关开启取单省 >0 之和，`back_steps` 腰线两步调用，与 `draw_back_darts` 绘制守卫同口径）。**参数语义收窄**：`front_waist_dart`/`back_waist_dart` 改为纯腰长调节量（**键名保留**），不再含、也不对应任何绘制省宽——旧尺寸单若曾把省宽手工折叠进 back_waist_dart，需下调回纯调节量（行为变更披露见决策日志）。腰头裁切链零逻辑改动：直腰头代数扣减的 front_w 改用 `pocket_dart_takeup` 同源守卫，弯腰头真闭省自然正确，均不双算。上腰弧变长后外缝弧反而变短（侧缝收量被吃省分走）：袋贴侧深可用弧长相应缩小。口径权威：牛仔裤前后片腰围推导.md §三.2 腰长不变量注记、打版流程.md 前片步骤 3/后片步骤 3/9/前口袋节。金标：tests/test_waist.py（target 省口项 + 两守卫）、test_back_steps.py 省组（|AB| = 17.5 + Σ省宽）。

裤耳裁片已程序化：`build_belt_loop(main_ctx)`（`flows/belt_loop_flow`，裤耳裁片.md §1~§4；自含裁片，非 FlowRunner 编排，同 `build_watch_pocket` 口径）。与其它裁片不同：不从整版提取边界、**不依赖整版几何**（main_ctx 只取 options），是纯净尺寸裁片--宽 = `belt_loop_width`（成品净宽），总长 = `belt_loop_unit_length × belt_loop_count + belt_loop_waste`（单根成品长 × 总根数〔通常 5〕+ 裁剪/车缝损耗，默认 6.0×5+3.0=33.0cm），整根连裁一条（车缝时再剪断）。**净裁无缝份（§1 毛边/不折边）故不走 cutter**：无缩水/无缝边/无刀口，`gross_polygon` 直接取净样四角（`with_gross(净样角点, ())`）；丝缕线竖向贯穿（§3 直丝缕=长度方向，局部系 Y 向下，与前后片经向一致由排料保证）；数量/净裁/毛边工艺备注进 `notes` 与 label（§4 内部标记）。局部 ctx 留 `belt_loop.edge0~3` 供 trace/调试。选项字段：`belt_loop`（开关，默认 False，独立无前置依赖）/ `belt_loop_width` / `belt_loop_unit_length` / `belt_loop_count` / `belt_loop_waste`（新增字段已同步 api.run() 显式参数透传）。输出：`--belt-loop-svg` 旗标 / `api.run(belt_loop_svg=...)`；`--pieces-dxf` 合集自动收片（块名 BELT_LOOP-{尺码}）。金标：tests/test_belt_loop_piece.py。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）已在 [options] 录入全部 5 个字段（belt_loop=true，小表袋块之后）。

DXF 导出已程序化（`exporters/_dxf_base.py` + `dxf.py` + `piece_dxf.py`，图层/坐标/编码约定详见 §10.3.1；裁床/服装 CAD 口径 R12/mm）：整版 `--dxf`（DraftSheet → REF/STRUCT/CURVE/POINT/TEXT 五层，role 分层同 SVG 口径）与裁片合集 `--pieces-dxf`（全部开启开关的裁片 shelf 行装箱平铺合一张，ET08 方言口径：数字图层 1/14/8/4/13/7（裁切/净样+缩水/内部画线/刀口/定位孔/纱向；净样=层 14 **单条闭合环**与 CUT 同构——ET08 方言净样层、逆向 5336 大货样本，标准 AAMA 的层 8 在 ET08 只是内部画线层，净样落 8 白色显示不被识别致毛样净样重叠，§10.3.1）+ 每片一个 BLOCK 经 INSERT 摆放 + 块中央 5 行魔法标签信息文本 + 模型空间 6 行全局文档头（Sample Size 行 = ET08 底部尺码栏数据源，ET08 自动识码口径，§10.3.1） + 文件头 999 AAMA 注释（详见 §10.3.1），刀口=层 4 POINT 附组码 30/50 且 ET 顶点吸附——CUT 折线共线插入刀口点为顶点（§10.3.1 第五轮实测修订）、裁片局部 Y 翻转不镜像、多片共用功能层靠 TEXT 片名区分）。入口：api.run 同名参数 `dxf`/`pieces_dxf` 与 cli `--dxf`/`--pieces-dxf` 平行实现已同步（SIZE 信息行尺码 = `PatternOptions.size_label`：订单元数据、不参与几何，TOML `[options]` 主表键、api.run 显式参数 `size_label` 透传，默认 "-"；两示例尺寸单已录入 "30"/"29"）——裁片分支由 (xxx_svg or pieces_dxf) 触发、build 一次按需写 SVG 并收进合集末尾一并出 DXF，未开开关时打印跳过提示。ezdxf 为可选 extra `dxf`（exporters 内 lazy import，缺依赖 RuntimeError 带安装指引；dev extra 已含 ezdxf 供 22 个 DXF 测试用例跑，含 $EXTMIN/$EXTMAX 回读文件级回归断言——防老 CAD（ET 08）黑屏的 set_extents 坑，详见 §10.3.1 范围变量条目）。

整版标注显示总开关已程序化：`PatternOptions.show_labels`（bool，默认 True；出口层显示控制，同 show_seam_allowance 定位——不改几何、报表不受影响）。False 时整版 SVG 三类文字标注（参考线名 reflabel/结构线名 structlabel/关键点名 ptlabel，exporters/svg.py 的 render/write_sheet_svg 加 show_labels 形参）全不绘制，线与点照常、画布尺寸不变（画布只由几何算）。api.run 显式参数透传，cli --svg 与 web /api/draft/sheet 统一消费 o.show_labels，多码 run_size_run 的基码整版 SVG 同透传（web schema 归整版段·版面杂项组）。**口径：只管整版 SVG**——裁片 SVG/DXF 无文字标注；整版 DXF 的 TEXT 层发 ASCII 元素名（R12 中文易乱码，CAD 校对用，§10.3.1）不随本开关隐藏。金标：tests/test_show_labels.py（合成小版两类模式 <text> 计数/线点保留/画布同尺寸）+ tests/test_web_api.py 端到端（options 透传后 0 处 <text>）。

缝边显示总开关已程序化：`PatternOptions.show_seam_allowance`（bool，默认 True；TOML [options] 主表键，from_file 走 cls(**data) 自动生效；api.run 显式参数透传，cli/api 两入口裁片 SVG 与裁片 DXF 出口统一消费 o.show_seam_allowance，多码 run_size_run 的 write_size_run_dxf 同透传；piece_svg.render/write_piece_svg 与 piece_dxf 各 render/write 函数均加 show_seam 形参）。设计定位是**出口层显示控制而非计算级跳过**：几何全链路照常（缩水/缝边/毛样折线/gross_notches 投影后处理/报表/notes 全不变——若在 flow 级跳过 add_seam_allowance，各 flow 把刀口投到毛样外沿的后处理会集体断链），仅出口不绘制：SVG 不画毛样层 id="gross"、画布 bbox 收缩回净样（不留毛样空边）；DXF 层 1 CUT 闭合折线不画（层 1 片名/魔法标签文本照常）、平铺与片 bbox 同收缩。**刀口随缝边隐藏（SVG/DXF 口径不同）**：SVG 隐藏缝边时刀口**整层不绘制**（用户口径：缝边刀口随缝边同步隐藏，净线位刀口 shrunk/notches 一并隐藏，净样交换视图只留轮廓/内部线/丝缕/定位孔）；DXF 净样交换文件仍**回退净线口径**——gross_notches 落在毛样外沿、隐藏后悬在净样外空白处，刀口源改取 shrunk_notches or notches（显示时仍是 gross_notches or shrunk_notches or notches；`use_dirs = notch_pts is piece.gross_notches` 恒等式检查天然防 gross_notch_dirs 错位）。裤耳净裁无缝份，开关无感。**DXF 隐藏缝边后无裁切线 = 净样交换文件，不能上裁床**，需切割文件时打开开关重出。历史注：`seam_allowance: float = 1.0` 是遗留死参数（全库唯一引用是自身校验且强制 >0，逐字段填 0 合法但不统一），控制缝边显隐的正解即本开关。金标：tests/test_show_seam.py（合成裁片 SVG 图层有无/画布收缩/刀口回退坐标 + DXF 层 1 无 POLYLINE 有 TEXT/层 14 恰 1 条闭合环/刀口 POINT 坐标 + Options 构造）。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）已在 [options] 主表录入（默认 true；紧邻的 seam_allowance 遗留字段注释已标注"当前无实际作用"）。

缩水总开关已程序化：`PatternOptions.shrinkage_enabled`（bool，默认 True；TOML [options] 主表键，from_file 走 cls(**data) 自动生效，api.run 显式参数透传）。**与 show_seam_allowance 性质相反：这是计算级跳过而非出口层显示控制**--False 时全部裁片不做缩水（净样直接加缝边，shrunk == net 或率 0 守卫分支干脆不构建 shrunk，「缩水：」notes 不出现），出口照常画毛样/缝边/刀口。解析统一收敛到新方法 **`o.shrinkage_rates(专用warp, 专用weft)`**（params 层，rise_on_pattern 同级）：专用率 None 回退全局率（主面料口径），总开关 False 时一律归 (0, 0)；**字段原值保留不改写**（False 不是把率清 0 存储，仅解析口收缩，重开即恢复）。全部 9 个缩水消费 flow（waistband/yoke/front_pocket/fly/back_patch/front_piece/back_piece/front_pouch/watch_pocket）统一走该口，勿在 flow 里手写回退。**腰头专用缩水率 `waistband_shrinkage_warp/weft`（float | None = None）**：与机头/门襟等七片同口径（None 回退全局，flow 走 shrinkage_rates，api.run 透传，zhitong.toml 已录入；演进见决策日志）。flow 内 pinned 刀口/切向方向的 shrink_scale 自叠点（front_pouch 的 sx/sy、back_piece/front_piece 的 pinned 等）因引用同函数局部 warp/weft 自动同源。袋布/小表袋里料默认 0 不受影响，但显式录了非 0 率也会被总开关关掉（口径：总开关是"这单不做缩水处理"，不做区分）。金标：tests/test_shrinkage_switch.py（解析矩阵 + FULL_FLOW 全开关 11 片端到端：关时逐边相等/notes 无缩水、开时真实缩放）。

推码（多尺码 SizeRun）已程序化：`params/sizerun.py`（SizeRun/SizeBand/SizeEntry + load_size_run）+ `flows/collect.py`（collect_pieces）+ `exporters/piece_dxf.render_size_run_dxf` + `api.run_size_run`。架构路线：**尺码表进、逐码参数化重打版**——不做点位移生成几何，每码用该码 Measurements 完整重跑整版（毗围闭环逐码独立收敛），浪长闭合等结构不变量自动保持；跨码唯一变量是 Measurements（`options_for(label, o)` 只改 size_label，其余约 150 选项全码共享）。小裁片跨码行为由此自动决定，无需逐片拍板：尺寸驱动片（前后大片/腰头/机头/门襟长度跟 front_rise）逐码变；锚定片（前口袋/袋贴/袋布——p1_dist/p2_drop 是常数但锚在每码重画的腰弧/外缝弧上）标称袋口不变、位置随码走；设计常数片（后贴袋/小表袋净形）全码恒定只挪位。若日后要贴袋随码放：把对应常数从 PatternOptions 挪进 formulas 挂 Measurements 推导（或扩 size_run 档差通道），**勿开"逐码选项"**——那与"尺寸是唯一跨码变量"路线冲突。
1. SizeRun schema（TOML `[size_run]` 段；示例见 `examples/size_female_zhitong.toml` 文末〔直筒单与尺码表同文件〕）：`enabled`（**总开关**，缺省 true；false = 整段失效、load_size_run 返回 None——cli/api 探测口共认，等效删段但免删；非布尔报错防 "false" 字符串恒真）/ `base`（基码 = Sample Size；回退 [options] size_label > order[0]）/ `style`（订单号，须 ASCII，进 DXF 头 Style Name/Grading Rule Table 两行）/ `order`（码序：显式 > 自动 = band.sizes 声明序串联 + 显式键序追加，去重保首现；字母码/"36L" 无需数值解析，**永不做数值猜测**）/ `[[size_run.band]]` 分段档差（8 参数 = 相邻码步进 cm；**步进归属：码 i→i+1 取 i+1 所属段**（"32→33 跨段取 33 所在大码段"＝工厂"33 码起放大档"习惯）；无 band 覆盖的码须 `[size_run.sizes.X]` 显式补全，否则报缺参清单）/ `[size_run.sizes.X]` 逐码显式（子集键覆盖展开值＝单码特调；全 8 键且无 band = 纯显式形态，两种形态已拍板都支持）。展开自基码双向累加（v[i+1]=v[i]+step / v[i-1]=v[i]-step）；thigh 特例：基码 thigh=0（未录入）时忽略一切 thigh 步进（全码 0），显式 thigh>0 可单码启用；每码构造 Measurements **复用全部交叉校验**（失败消息带码标签）。校验全中文 ValueError 含实际值（未知键/跨段重复码/order 缺码/基码不在码序/style 非 ASCII/无来源码清单）。纯参数层**不 import formulas**（档差累加是算术非公式）。
2. `collect_pieces(ctx)`（`flows/collect.py`）：按固定顺序构建全部已开启裁片（waistband / back_yoke / front_facing|front_patch / front_pouch / front_fly_single(+front_fly_double) / watch_pocket / belt_loop / back_patch / front_piece / back_piece，与原 api/cli 逐分支一致，保证 DXF Category 序号稳定），返回 (裁片列表, 跳过说明列表)；**不写任何文件、不 import exporters**（flows 层无输出职责）。api.py/cli.py 原双份平行收集分支（~122/~161 行）已换用（推码方案步 2）；接受的行为差异：原"仅设某片 SVG 时只 build 该片"的惰性 → 全收集（build 开销可忽略，裁片集合一致）；cli 原 8 组 `--until` 逐片 elif 警告收敛为外层一条。
3. 多码单文件 DXF（`piece_dxf.render_size_run_dxf` / `write_size_run_dxf`）：groups = [(码标签, 该码裁片列表)] 码序，每码一条摆放带（带内 _layout shelf 行装箱，带沿 Y 叠放、间距 BAND_GAP_CM=8cm、首带贴原点）；**仍共 AAMA 数字图层，绝不建每码图层**（ET08 图层校验黑屏）——分码靠既有机制：块名 `{片名}-{码}` + 块内 5 行魔法标签 Size 行 = 本码 + 模型空间 Sample Size = 基码（ET08 底部尺码栏数据源，导入后按码切换显示对应裁片）；**Category 码内 0 起重置**（同片名跨码 Category 相同，ET08 参考件口径）；多码时每带左上码标 TEXT "SIZE {码}"（层 1，ASCII，人读辅助，ET08 分码不依赖它）。`render_pieces_dxf`/`write_pieces_dxf` = 单组退化 wrapper（现有 341 行金标不动全绿 = 等价证明）。金标：tests/test_size_run_dxf.py（块数/块名/Sample Size/Category 重置/带叠放精确重建 INSERT/码标/写盘回读）。
4. 入口：`api.run_size_run(size_file, *, pieces_dxf, svg/trace/report)`（文件驱动，不复制 180 kwargs）——load_size_run（无段或 enabled = false 时 ValueError 提示走 run）→ 按码序逐码 run_with_thigh_closure + collect_pieces 收 groups → write_size_run_dxf(sample_size=run.base, style_name=run.style_name)；返回 {码: DraftContext}（码序）。输出口径 v1：svg/trace/report **只出基码**（整版是人工调版工具，版师只调基码；看任一单码细版 = 复制尺寸单关 enabled 或删 [size_run] 段）。毗围不收敛**报告而非失败**：逐码打印「码 / 残余 ΔW / 裁片数」（私有 `_last_residual` 从 closure trace 文本解析末轮 ΔW，零核心侵入；示例实测 8 码 7 收敛、38 码残余 −0.36 红线钳制出片）。cli `draft` 开头 `load_size_run(args.size)` 探测：无 [size_run] 段或 enabled = false 走原单码路径原样；有段且开 → `--until` 与缺 `--pieces-dxf` 报错退出 2、逐片 `--xxx-svg` 忽略并 stderr 提示。金标：tests/test_sizerun.py（含 .doc/臀围线推导.md §四 W26~W34 表展开逐一相等——注意逐码步进为腰 5.0/臀 4.0，W26~W34 是 2 英寸码）、tests/test_collect.py、tests/test_size_run_api.py（端到端）。

工厂 DXF 反解析已程序化（`src/ylpattern/reverse/` + cli `reverse` 子命令；**口径权威 = [.doc/工厂DXF逆向解析.md](工厂DXF逆向解析.md)**，本条只记工程定位）：布衣科技 R12/mm 方言 DXF → 尺寸单 TOML，范围**层 1+2+3**（8 测量键 / 可量测·可观测选项 / 多码档差 `[size_run]`），**层 4 形状逆拟合与层 5 逐锚点形状不做**（报告列"未恢复清单"）。模块链 reader（唯一碰 ezdxf：乱码还原/块拆子片/层分类）→ identify（两款特化档案 5015/5028 + 谓词打分；新款 `--probe` 出件清单 bring-up，未登记款退出 2）→ measure（还原换算 成衣cm = 净样mm×(1−率)÷10，**乘法口径与 cutter 除法互逆**；调节量族/前后中内收/腰头/缝份/缩水；挖削口袋——p1_dist/p2_drop = 前代袋口段/侧边段还原弧长、袋口形态 = 前片袋口弧各向异性还原后的弦法向剖面 `chord_profile`（≥8° 折角→polyline 折角表、平滑单峰→bulge 弧高/弧顶弦位（**发射换算引擎单位**：bulge=真弧高÷2、bulge_at=(f−0.3125)/0.375——arc_through 渲染弧高=2×bulge、弧顶弦位=0.375·bulge_at+0.3125 仅落弦中段 [0.31,0.69]，越界钳端点）；dart/paring_n 单弧不可分离且无省痕、tangent 不可辨识，保默认并披露，「推测完整」用户口径）；**袋贴内边 = 前代净边底部大弧**（片净边与引擎 Ω_facing 同构；用户口径「片内两弧：内部 = 袋口缝线、边线 = 袋贴弧」）——袋口弦定侧负侧游程 + 折角修剪定 A/C（换向角 ~85° vs 弧内 ≤4°，阈 25°）→ facing_width/side_w = 两直边袋贴段（引擎 P1→P_fw / P2→P_fs 同锚）、mode=bulge + 真弧高/弧顶位 = 大弧还原剖面（发射同袋口换算引擎单位；背离袋口**弦**为正——弧中点已内垂可能越过内边弦，禁用做定号参考）→ grade（逐码独立测量再差分，绕开顶点漂移；band↔差分对应按 sizerun"进入某码过渡取该码所在段"语义）→ emit/report。**结构开关 = 识别观测**（裁片在场即开：back_yoke/front_pocket+front_pocket_facing/fly_separate/belt_loop/thigh_limit；**front_pouch 显式 false**——袋布走里料不在工厂打版 DXF，不从前代一体片推断，用户 2026-08-29 口径），与形状拟合划清界限；表袋在场即开+件形/位置分道（用户口径：无具体位置就自设，只保证上部不被面板藏住；5015 表袋件是**自定义多边形**非袋贴相交）：净环丝缕贴轴定向还原 + 共线折叠 → **custom 净样原样**（5015 V 底五边形 5 锚点全 line 边；弧边弧高换算引擎单位 ÷2、dy 向下镜像取右手法向号；points/edges 是字符串+数字混型数组——TOML 1.0 允许、tomllib 接受，emit 直写勿"纠正"），锚位自设 = O 正交局部系解析重建引擎袋口弧取最深可见顶边（安全距 2.2 = 1.2 名义 + 框架倾斜余量：引擎真实框架腰倾 ~5°/侧缝内倾 ~17° 对正交模型吃掉 0.46 净距，reverse/ 禁 import 引擎只能余量吸收，回环实测 1.736 ≥1 进金标）；件形不可用（无丝缕/斜向/旋转/**光板矩形超宽 = 对折片两读**，5028 火机袋 11.1 > 0.9×8.80）回退 facing_intersect 保守默认（深 0.42×p2/外端 0.12×p1/宽 0.55×p1，可见性判据用**弧**不用弦，弧中段内垂 ~3cm 弦判据会误判）；金标 5015 custom+回环、5028 回退披露；**后贴袋在场即开 + custom 净样原样 + 位置自设三定则**（用户定则：机头下方/对齐后腰中点/袋底保持毗围线上方）：件形骨架同小表袋（丝缕定向还原+共线折叠，`_patch_shape`），发射 points（u 朝侧缝/v 下正/V0=袋口近后浪侧顶点）+ edges（**纯数值对** (弧高,弧顶位)，弧高 0=直线，非小表袋的 line/arc 混型）；**弧边外凸取负与小表袋相反**——引擎局部→全局 180° 旋转保定向（全局环 CCW、arc_through 正 bulge=内凹），小表袋 dy 镜像是反定向（全局顺时针、外凸取正），勿混；inset_x=(约克底线还原长−口宽)/2 居中、drop_y 默认 3.5、袋底距毗围线 ≥0.5（可用深 = 后片顶边弧长中点到毗围线 ×warp），放不下上提/钳 0.5 披露；铺版无手性观测——主形镜像对称即无歧义、非镜像角（袋口端小台阶）披露取向自设；件形不可用回退引擎默认 rectangle 14×16（披露），无机头不发射只告警；回环进金标（局部系逐位一致+负号外凸+三定则，5015 偏心 −0.62 = 引擎/工厂约克底线重建残差、宽断言）。金标：tests/test_reverse_{reader,geomops,identify,measure,grade,emit,cli}.py（合成件不依赖真件）+ test_reverse_gold_{5015,5028}.py（真件，out/ gitignored 缺文件整文件 skip）。回环已验证（reverse→TOML→draft 两款全出，袋口 bulge/polyline 两式与袋贴 bulge 族均过引擎）；**毗围闭环留残余 ΔW ≈ −2.7cm**（5028 逐码 −2.69→−4.02 随码线性、5015 同级、与口袋参数无关；红线钳制"尽可能靠近"）：工厂目标 = 毗围导线弦，引擎默认形状系数下重打版偏大——层 4 边界，文档/报告披露不阻塞。

照片参数提取已程序化（**`agent/extract/`** 12 模块 + `python -m agent extract` 子命令——**用户二次拍板边界：ylpattern = 纯引擎（零 LLM、零触网），全部大模型相关代码收敛 agent/**，依赖方向唯一 agent → ylpattern，探针要纯内存 (m,o)→ctx 故只 import `ylpattern.flows.closure + params(+validate)` 公开层；**口径权威 = [.doc/参数预测/](参数预测/)（知识库 4 篇收集文档 + 索引 参数推测知识库.md + 款式判据手册.md）**，本条只记工程定位）。照片 + 文字描述 → 尺寸单 TOML + 逐键核对报告（**半自动**：人工核对后再喂 draft）。架构基石「**模型是带眼睛的确认者，不是业务判断者**」：绝对 cm 照片永不贡献（无标尺），全部数值代码查表/派生（知识库 K1~K4 条目为唯一权威，代码函数注条目号）；描述缺 7 必填尺寸列清单退出码 2，**绝不编数值**。管线（两阶段调用，S1 补漏可免）：`parse_describe`（S1 纯代码：数字正则 + 同义词典 + 尺码换算 29码×2.54≈74 + 缩水率摘录）→ S1 补漏小调用（纯文本、带外 10<v<200 丢弃）→ `prejudge_axes`（B 表锚点：腰位=front_rise 放码归一化 ±0.75cm/码、体型=臀腰差、fit=hem/hip 比）→ S2 唯一主调用（`schema.build_prompt` 预填模板编辑确认；照片 override 需 conf>0.5+evidence，数字锚定轴免疫词典翻转；**22 键模板会淹没模型注意力**——模型只报整件级特征〔腰头/后袋形状〕，局部件键〔如 mouth_depth〕需判据量化锚〔弦长比例〕+ prompt「必看项」指令定向才报；**必看项须覆盖同族全部枚举键**——现行必看项：「先判形态 mouth_mode 三选一（平滑弯月=bulge/直线斜切=tangent/折点明显=polyline）、再量弧深 mouth_depth（仅 bulge 时）」〔发现过程见决策日志〕〕→ `merge`（词典>数字锚点>照片>惯例）→ `enforce_dependencies` → `derive_all`（K2 前中基准带+四维修正→ratio 记账 adjust 不发射、K3 后中 15:X 插值、K4 余量排除法定省/育克〔**约克省载体 = back_dart 三键**：有育克且 ⑤≥0.5 → back_dart=true/count=1/width=⑤ 全额（超带钳 5 披露）——整版后片含腰头、省口打在腰口，育克裁片提取绕省尖旋转闭口完成转省（yoke_flow §2.2 闭口仅 1 省）；cb/side 只是育克线位置不承载转省量，用户口径 2026-09-02；无育克缺额走真缝纫省 1.0~2.5 分省〕、DELTA_PRESETS 路由 + 部件族 families 全族发射）→ `validate_candidate` → `probe_loop`（L0 试跑 / L1 归因回喂 ≤2 轮〔归因=异常消息对候选键子串匹配，**引擎错误消息是中文常接不住**→直落 L2，根治靠 families 档位自适应而非归因兜底〕 / L2 回退数值键 / L3 关开关 / L4 披露拒直出；引擎默认开关全 False，回退=弹键即默认）→ `score_features`（打版后业务区间：袋口占比 0.45~0.55、袋口弧深/弦长 10%~32%〔工厂定标哨兵，tangent/polyline 不参与〕、侧缝斜度 ≤30°、直裆深自洽、内收落档）→ emit/report。`provider.py` 是**唯一触网文件**（OpenAI 兼容流式 SSE，glm-5.3-flash @ coding/paas/v4，max_tokens≥16384 防思维链截断、thinking 参数 400 自动摘参 sticky；踩坑清单在其 docstring）；配置 `vlm.toml`（gitignored，仓库只留 vlm.toml.example 占位）或 `YLP_VLM_*` 环境变量；无照片且无配置走纯描述路径（S1 全中零模型调用）。产物：`out/extracted.toml`（逐键行尾 `# 来源：source conf | evidence`，与 examples/ 同构直接喂 draft）+ `extract_report.md`（七段：判定轨迹/尺寸/派生/校验探针/评分/披露，conf<0.7 标 ⚠）+ `ExtractResult.to_web_payload()`（二期 webapp POST /api/extract 直用）。CLI 进度：`extract_from_input(progress=)` 可选阶段回调（描述解析/S1 补漏/S2 模型调用前后计时/派生键数/探针逐轮 attempt/评分/完成），CLI 注入 stderr 打印 `[agent] {累计秒数:.1f}s {消息}`（stdout 留给产物路径结论行），probe_loop 第 4 参透传；HTTP 服务（runner.run_extract）缺省 None 静默不受影响。**引擎事实（已进测试）**：**枚举判据须含「唯一分辨点」口诀**——盾形底曾被判 angular（其「五角硬朗轮廓」证据实为盾形本相：盾形就是五边形）；schema._CRITERIA 与判据手册的「数底部」口诀：斜线交底中一点=baker_shield / 底中留水平段=angular / 平直=rectangle，同源哨兵测试在 test_extract_schema。新枚举键判据入册时照此办理：给几何分辨点，勿只给风格形容词；`front_pocket_mouth_depth` 是 S2 伪轴（families 映射弧深用；**按工厂实测定标**：真弧高 浅1.5/标准2.5/深3.5cm，÷2 发射 bulge 0.75/1.25/1.75——工厂 5015 实测真弧高 3.36〔test_reverse_gold_5015 断言 bulge=1.68〕；判据手册 §二 弦长比锚 12%/20%/25%+、score 弧深带哨兵 10%~32%；定标过程见决策日志），不能随枚举透传发射（from_dict 拒未知键）；families `front_pocket_p1_dist=10.0`（金标值，引擎默认 8.5 在中高腰触发小表袋射线失配）+ `front_pocket_facing_side_w=3.5`（须满足 p2_drop+side_w < 外缝弧臀围端弧长守卫，G 表 5~7 是大码带）+ `front_pocket_p2_drop` 按腰位分档（低 5.5/中低 6.5/中+ 7.5——低腰外缝弧竖向空间仅 ~10.3，固定 7.5+3.5 必越守卫，低腰喇叭实测 5.0~6.5 全过取中偏浅）——小表袋相交缺口根因在引擎待修，修好后两值可回归带中值；`front_pouch`（袋布）不进先验表与模型面（prejudge/schema 白名单均无）——内部件照片看不到、描述侧无判据词，**未分析到不发射**走引擎默认 False（用户口径；判据手册/描述词典补袋布条目后再加回）。金标：tests/test_extract_{parse,prejudge,schema,derive,probe,score,emit,pipeline,eval,provider}.py（FakeVLM 全程不触网；emit 为回环金标：产物 from_file 回读经 run_with_thigh_closure 真跑出整版）。评测：`scripts/eval_extract.py --cases tests/_extract_golden/cases`（8 键召回/编造率、数值 MAE/超差、开关枚举命中、探针 stage 分布；判据/词典改动前后必须跑 `--baseline` 对比）；示例 case female_high_sk_29（快照真值，框架键手工核对）。尚未做：K5 部件档位/K6 男款/K7 弹力系数知识缺口补值（真实照片端到端已验通）。Web 服务化（agent/app.py，POST /api/extract、to_web_payload 契约）见 §10.9。

参数层校验结构：十个裁片缝份 dataclass（`Waistband/Yoke/FrontFacing/FrontPatch/Pouch/Fly/WatchPocket/BackPatch/Front/Back` SeamAllowances）在 `params/seam_allowances.py`（options.py 顶部 re-export、`params/__init__` 同步导入，旧 `from .options import XxxSeamAllowances` 引用兼容）。`__post_init__` 只做调度，校验在 **14 个分特征私有方法**（`_check_common` / `_waistband` / `_back_dart` / `_back_yoke` / `_thigh_closure` / `_front_pocket` / `_front_facing` / `_front_patch` / `_front_pouch` / `_watch_pocket` / `_fly` / `_front_piece` / `_back_piece` / `_back_patch`）+ **4 个模块级助手**：`_check_shrinkage`（缩水区间 [0,0.2)，none_ok=True 放行 None=回退全局，note 为文案口径注记）、`_check_sa`（缝份 dataclass 类型 + 语义边非负，label 为报错前缀、腰头空串）、`_normalize_edge_specs`（line/arc/bezier 边形态归一化：机头/小表袋弧顶分位开区间 (0,1)、袋布闭区间 [0.1,0.9]；边数与锚点/节点数匹配留在调用处）、`_normalize_custom_shape`（前/后贴袋 custom 角点/边形态，非 custom 仍归一化）；归一化 `object.__setattr__`（back_dart_width 广播、机头/袋布/小表袋边形态、前后贴袋 custom 点边、袋口折角）紧邻各特征校验。**新特征校验/缝份字段写进对应 `_check_*` 方法，勿再回填 `__post_init__`**；多字段同时非法时首报错顺序按特征分组（测试均为单错构造不受影响）。拆分沿革（460 行单体拆解、658 项等价验证）见决策日志。

死参数 `side_intake_k_waist` 已删除：定义后从未被消费。k_waist（前片侧缝内收推导.md §二.1 的前后腰围分配量，前减后加）唯一正解是 `waist_balance`——`formulas.waist.waist_front_finished` 的 balance 形参即 k_waist（docstring 已注明），`draw_front_waist_outseam_curves` 传 `o.waist_balance`。web schema「臀腰裆框架」参数组同步移除；旧尺寸单仍传该键会被 from_dict 以未知键 TypeError 拒绝（防呆）。

前浪裆弯形态三参数（取代旧单参数 `front_rise_handle_ratio`，演进见决策日志）：`front_rise_alpha`/`front_rise_beta`（k1=α·|BC|、k2=β·|BC|，默认各 1/3，前浪绘制.md §3.1）+ `front_rise_exit_angle`（裆底出口角 θ 度，终点切线自水平向下倾；0=教科书水平收尾留裆尖，10~25 紧身/弹力裆底圆角化、裆底夹角=90°+θ，上限 30，§3.3），由 `draw_front_rise` 传入 `curves.front_rise`；起端切线恒沿前中斜线不参数化。默认 (1/3, 1/3, 0°) 与旧 k1=k2 口径逐字节等价（控制点金标 tests/test_steps.py::test_front_rise_control_points_golden）；θ>0 时 C 仍为弧线端点，浪长闭合与 cutter 裆尖角部处理（读实际端切线）自动跟随。与后浪 `back_rise_alpha`/`back_rise_beta` 口径对齐。

前口袋袋贴（facing）已程序化：`draw_front_pocket_facing`（`front_pocket_steps`，前口袋绘制.md §三.3.(1)）。
1. 定位两端点（支持非等距独立宽度）：腰头顶点 P_fw（有省自 P1′、无省自 P1 沿腰弧量取 w_waist=front_pocket_facing_width，默认 3.5）；侧缝顶点 P_fs（自 P2 沿外缝弧向下量取 w_side=front_pocket_facing_side_w or w_waist，推荐 6.0 防露白；但须满足 p2_drop + w_side < 外缝弧总长，否则步骤报"侧缝顶点越出外缝弧"——测试金标 M（H=96）含吃省 ΔW=2.0 时外缝弧 ≈12.32（腰长不变量：侧缝收量被吃省分走）、夹具 p2_drop 7.0，w_side 上限 <5.32，故取 5.0）。
2. 内边 L_inner 支持三模式（front_pocket_facing_mode）：
   - "tangent"（打版推荐，默认）：两端垂直切线贝塞尔（P_fw 端 ⟂ 腰弧、P_fs 端 ⟂ 外缝弧），由切线柄长 front_pocket_facing_h1/h2 控制下垂与向内进深（h1/h2 为控制柄距离/拉力，而非直线下垂长度）；
   - "offset"：基准线 C_ref 控制点域法向偏置（折角链沿弦法向平移），端点锁 P_fw/P_fs；
   - "bulge"：浅弧式，由 bulge/bulge_at 控制。
3. 闭合边为腰弧/外缝弧子段（先画后裁，不作布尔裁减）。
选项字段：front_pocket_facing / front_pocket_facing_mode / front_pocket_facing_width / front_pocket_facing_side_w / front_pocket_facing_h1 / front_pocket_facing_h2 / front_pocket_facing_bulge / front_pocket_facing_bulge_at（新增字段须同步 api.run() 的参数与 PatternOptions 构造透传）。

前小表袋（watch pocket）已程序化：`draw_front_watch_pocket`（`front_pocket_steps`，小表袋绘制.md §2~§4）。
1. 两种生成模式（watch_pocket_mode）：
   - "facing_intersect"（袋贴相交延伸模式，默认）：袋口按 watch_pocket_width 定宽，左右侧边向下延伸（结合 watch_pocket_taper 内收倾斜），调 `curves.ray_intersect_bezier` 求得与袋贴内边 `front.pocket_facing_inner` 的两个交点及参数 [t1, t2]；底边取袋贴内边精确子段（`curves.bezier_subrange`）顺接闭合；强制依赖 `front_pocket_facing=True`；
   - "custom"（独立全自定义模式）：自定义净形锚点列表 watch_pocket_points（≥3 个）+ 逐边形态列表 watch_pocket_edges（line / arc / bezier），支持 watch_pocket_rotate_deg 绕参考点旋转。
2. 基准点 O = 前口袋侧缝腰点（弯腰头取下侧缝腰点 B'，直腰头取腰外缝顶点 B，经 effective_waist 同步）。
选项字段：watch_pocket / watch_pocket_mode / watch_pocket_width / watch_pocket_taper / watch_pocket_offset_from_top / watch_pocket_offset_from_side / watch_pocket_rotate_deg / watch_pocket_points / watch_pocket_edges。`watch_pocket_offset_from_top` 默认 3.0（4.0 在吃省默认改 0 后临界不相交：袋贴内边上端左移 ~2cm，3.0 在 dw=0/有省下均可行）。

已知口径（用户定标）：facing_intersect 深度被袋贴内边锁死是**口径特征非缺陷**——实照只能看到小表袋顶部（贴腰口位置 + 袋口宽），下半段延伸入袋藏住不可见，深度无需管控，**顶部对齐即可**。extract G 表小表袋族据此定标：`offset_from_top` 1.0（贴腰头下缘）、`width` 5.5（浅小兜带 5~6.5）；调小 offset_from_top 只会加长射线，与袋贴内边相交更稳（不相交缺口反而缓解）。金标 truth.toml（female_high_sk_29）与 eval 全绿。

腰头裁片已程序化：`build_waistband(main_ctx)`（`flows/waistband_flow`，腰头裁片.md §三~§五；自含裁片，非 FlowRunner 编排，同 closure.py 口径）。
1. 净长提取（§三 v0.9 双轨）：**直腰头维持「代数求和」**——`extract_waistband_spec` 读上腰弧 `front.waistline_arc`（t=0 侧缝->t=1 前中）/ `back.waistline_arc`（t=0 后中->t=1 侧缝）减省宽求和（后省 = `back.dart{i}_leg_inner` 对应省宽、前省 = `front_pocket_dart_width` 需 front_pocket 开）。**弯腰头 = 上腰弧真拷贝 + 省道真闭口 + 整根均匀圆弧**（`front/back_waist_curve_sag` 经总转角全量传递、无上限；v0.5~v0.8 演进见决策日志）：闭省（后省 = 省腿线∩腰弧求交后绕省尖旋转远侧子链、多省共轭复合同步变换后续省腿/尖，省口弧段略窄于省宽是弦口定义+sag 的二阶效应即物理闭省口径；口袋省 = 切点取上腰头线法足 `front.pocket_p1_top`/`pocket_p1_transfer_top`〔P1/P1′ 本体在下腰头线上距上腰弧约一个腰头宽，法足才是裁片省位〕，C1 闭口对齐切向）→ 拼合放置（前弧绕侧缝腰点旋转前后**真实侧缝线**夹角后**跨后片侧缝线反射**——物理平摊缝拼合）→ 局部系（origin=后弧后中端、X̂=后弧起切向〔90° 法则保证 ⟂ 后中斜线 ⇒ 镜像轴 ∥ 后中缝〕、Ŷ 取垂向朝下者）→ **整根均匀圆弧**（`curves.uniform_arc_cubic` 封闭解：弧长 = 链净长精确、总转角 = 链末切向角〔弯曲总量，sag/裆深经它传入〕、起端切向恒水平〔后中镜像 C2〕，曲率恒 1/R 全弧均匀；端点位置派生——独立带状裁片端点无装配语义）。`l_front/l_back/l_half` = 闭省后链实长（报表/丝缕用；均匀弧弧长 = l_half 精确）。`WaistbandSpec` 增 `bottom_arc`（整根均匀圆弧）、删 `computed_drop`；`curves.waistband_curve` 已删（无消费者）。
2. 净样绘制（`steps/waistband_steps`，独立 DraftSheet 局部坐标 Y 向下）：直腰头 = 矩形 L_half×W（零改动）。**弯腰头下口线 = 整根均匀圆弧**（`spec.bottom_arc` 单条三次贝塞尔，口径「保持拼合的弯曲、整个腰头一条顺滑的弧（类似抛物线）」：三锁 = 弧长锁净长（精确）、总转角 = 链末切向角、起端切向恒沿 X̂（后中镜像 C1/C2）；一匀 = 曲率恒 1/R 全弧均匀；`curves.fit_fair_cubic`/`g2_blend` 已删）。上口线 = 均匀弧端法向偏移 W（端控制点各用端法向——端切向与下口严格平行为平移性质），`right_end`/`left_end` 与端切向严格直角。边名与直腰头同构单名（`wb.bottom_right`/`bottom_left`/`top_right`/`top_left`，无分段后缀）；镜像/搭门/封边/刀口复用 `_mirror_x`/`_reverse`/`_end_tangent`/`_up_normal`。**弯/直边数同构恒 8**（fly=0 为 6）——省数只改弧形不改拓扑，同 options 跨码恒定，推码跨码对应前提（§六）。
3. 裁切三段（`cutter`）：`apply_shrinkage`（按裁片局部 X/Y 轴缩水率仿射缩放，保持贝塞尔性；**除法口径 1/(1-率)**——缩水率以缩水前毛坯为基准，净样先放大、洗水缩回恰为净样（2026-08 弃乘法 x·(1+率) 口径，洗后偏小率²量级）；因子统一走 `cutter.shrink_scale(rate)`，pinned 刀口/切向方向/缝边交点等 flow 自叠因子处一律调它、勿手写 1.0+rate；参数语义=沿轴率，**面料经/纬率映射到 X/Y 由 `waistband_grain` 决定**：LENGTH 长向(X)=经→x/(1-warp)、y/(1-weft)，WIDTH 宽向(Y)=经（默认）→x/(1-weft)、y/(1-warp)，映射在 `build_waistband` 调用处完成、cutter 本身按轴几何纯）-> `add_seam_allowance`（四边独立缝份沿**外法向**偏移：曲线**公差驱动自适应**真法向 offset（`_offset_edge_points` → `_offset_points_adaptive`，弦高公差 `cutter.SEAM_OFFSET_TOL_CM` = 0.01cm = 0.1mm、与出口层 `_dxf_base.FLATTEN_TOL_CM` 同口径——紧弧自动加密、平缓微段塌缩为 2~3 点；核心层不能 import exporters，两常量注释锚定、改公差须两处同步）、直线整体平移；相邻异名边角点取两偏移边切线延伸交点 miter 连接（`_miter_point`），切线平行回退阶梯角，普通 miter 角另有尖角限长 `miter_limit=1.5`（`add_seam_allowance` 形参可调：锐角交点距角点超 max(sa)×本值回退阶梯角，见 §10.10），同名边平滑相接、后中折线不外扩；缝份不叠加缩水；**缝份 ≥ 内凹曲率半径（sa·κ ≥ 1，`CubicBezier.curvature_at` 判据）的偏移尖点自交由 `_trim_offset_loops` 兜底**——闭合毛样折线非邻接段扫掠求交、裁两交段间**短弧**（环长 ≤ 16cm 才裁，防误裁大段拓扑；超界只告警），裁剪/告警均写入 notes）。零长退化边（`fly_extension=0` 致 `wb.top_fly`/`wb.bottom_fly` 首尾重合、无切线）在 `build_waistband` 装配 net_edges 时即按 `cutter.edge_length`（`LineSegment.length` 属性 / `CubicBezier.length()` 方法，API 不一）滤除，cutter `_offset_edge_points` 另对零长直线防御性返回空，避免外法向归一化触发「零向量无法归一化」）。`PatternPiece` 三态：net_edges / shrunk_edges / gross_polygon。
4. 刀口（§四.2 v0.4：后中对位 + 左右两端上下顶点，**上下口线中段不打省位/侧缝对位刀口**；毛样刀口打在净线延长线与缝边的交点上）：`draw_wb_notches` 上版净样位 5 点——`wb.notch_back_center`=O(0,0)、`wb.notch_left_bottom`/`right_bottom`=下口线端点（含搭门量）、`wb.notch_left_top`/`right_top`=上口线端点；`_collect_notches` 收进 `PatternPiece.notches`（净样位）。缩水+缝边后 `flows/waistband_flow._project_corner_notches` **整体替换 gross_notches**（flow 私有工艺策略，同前/后片 `_project_notches` 先例，但方向非外法向投影）：后中沿**原点垂线**（后中宽度方向=下口线起端法向）**∩ 下口缝边线**（§四.2.1 括注）；四角换缝边交点（`_sa_crossing` 两线真交点——**下顶点沿腰头宽线**=端封边走向 **∩ 下口缝边线**、**上顶点沿腰头线**=上口切向 **∩ 端头缝边线**；两线先按缩水比例仿射变换再求交〔缩水先于缝边、缝份不叠加缩水，各向异性缩水后垂直角点两线不再正交，故取真交点而非法向平移〕；外法向口径同 `cutter._offset_edge_points` 存储走向切线逆时针 90°。fly=0 搭门段零长切向退化，左端退回 bottom_left 起端/top_left 末端取切向）。丝缕线方向随 `waistband_grain`（默认 WIDTH 宽向=经→竖向沿裤长；LENGTH 长向=经→水平）。
选项字段：waistband_fly_extension（门襟搭门量/宝剑头长，左片前中端外延；**默认 0=不外延净样**——有些款的搭门量加在 left_end 缝份上而非外延净样（默认由 3.5 改 0，见决策日志）；>0 时沿左前中端切向外延，弯腰头随弧端斜出〔约 40° 转角时 3.5cm 搭门使左端比右端低 ~2.3cm，属设计非 bug〕；fly=0 退化为 6 边、fly>0 为 8 边）/ waistband_full_piece / waistband_grain（WaistbandGrain：WIDTH 宽向=经〔默认，横裁，=裤长方向〕/ LENGTH 长向=经〔直裁〕；决定丝缕线方向与缩水经/纬率到局部 X/Y 轴的映射，§五.2。经向是面料属性、全局统一——前后片丝缕线=裤中线沿裤长，即经向=裤长，腰头横裁时宽向与之同向）/ shrinkage_warp / shrinkage_weft（面料经/纬向缩水率，到腰头 X/Y 轴的映射由 waistband_grain 决定）/ waistband_shrinkage_warp / waistband_shrinkage_weft（腰头裁片专用缩水率，None=用全局；走 `o.shrinkage_rates` 含总开关收缩，2026-08 新增）/ waistband_seam_allowances（WaistbandSeamAllowances：top/bottom/left_end/right_end，TOML `[options.waistband_seam_allowances]` 子表，须置 [options] 末尾避免吸收后续键）。输出：`--waistband-svg` 旗标 / `api.run(waistband_svg=...)`。已删参数 `waistband_blend_cb/side` 与 `waistband_front_drop` 走 `from_dict` 一次性垫片（stderr 告警后丢弃，兼容旧尺寸单）；下口线形状由整版 `front/back_waist_curve_sag` 全量传递、无圆顺手感参数；**勿与 `fc_drop` 混淆**（`fc_drop` 是裤身前腰头绘制的前中下落量 d〔`formulas.waist.waistline_horizontal_span`，前腰头绘制推导.md〕，塑造裤身腰围线）。金标：tests/test_waistband_piece.py（v0.9：sag 响应/均匀弧〔后段弧度显形 ≥2.5cm@侧缝位 + κ 比 ≤1.05〕/切向步进<5°/镜像无 W/κ 峰值界/推码边数恒 8/后省+口袋省闭口 + 直腰头全回归）+ tests/test_curves.py（uniform_arc_cubic 四测）。

后机头/育克裁片已程序化：`build_yoke(main_ctx)`（`flows/yoke_flow`，机头裁片.md §2~§5；自含裁片，非 FlowRunner 编排，同 `build_waistband`/`closure.py` 口径）。
1. 四边界提取（主版坐标 Y 向上，均从已上版元素读，不重画）：上口 top=弯腰头 `back.lower_waistline_arc` / 直腰头 `back.waistline_arc`（t=0 后中 O→t=1 侧缝 X）；下口 bottom=`back.yoke_bottom_seg{i}` 链 P0→PN（line/arc/bezier；空 anchors+edges 时 `back_yoke_steps` 不存该段，回退直线 `LineSegment(P0,PN)`）；后中 cb=`LineSegment(origin,P0)`（P0 落后中斜线、直线精确）；侧缝 side=`back.outseam_hip_waist` 子弧 PN→X/X'（`t_pn=t_at_length(L−D_side_total)`，D_side_total=直 side_dist / 弯 W+side_dist；弯腰头侧上端到 X'=下腰头侧点 `t_at_length(L−W)`）。origin=弯 `back.lower_waist_center_point`(O') / 直 `back.rise_top_point`(O)。cutter 序 P0→PN→X→O（**负面积约定**，与腰头同向，外法向外扩正确）。
2. 有省（仅 1 省，§2.2）：`_detect_dart` 读 `back.dart{i}_apex`/`_leg_inner`/`_leg_outer`；省腿 ∩ 上下边界求交点（`_line_line_intersect` / `_line_bezier_intersect` 采样定位符号变号段+二分、校核落线段内；后者 2026-08-29 已提升为 `curves.line_bezier_intersect` 公开原语、腰头闭省共用，yoke_flow 内薄委托）切开左右子轮廓 → 右片绕省尖 apex 旋转 θ=`degrees(atan2(叉,点))`（把 (p_out−apex) 转到 (p_in−apex) 的有向角；等腰省+直下口时 C_out 精确落 C_in）闭合 → 端点 snap（`_snap_geom_start/end` 仅动该端点+同步邻柄保切向方向、不传至下游连接）对齐拼合顶点 → 拼合处上下折角 G1 倒圆（`_g1_fillet`：入/出边各沿弧长退 δ、插三次贝塞尔，端切向与两侧边一致；同族边内部所有衔接点切向共线）。2 省或省腿未穿越上下边界 → 回退无省提取（stderr 告警）。
3. 裁切三段：`_to_local_geom` 关于 origin 180° 旋转变换（`local=(origin.x−x, origin.y−y)`，**保向** det=+1、符号面积符号不变；局部 +Y 朝下，同 `piece_svg` 不翻转口径）-> `apply_shrinkage`（经向=局部 Y=后片裤长向，§3.1 关联布纹 → Y 吃 warp、X 吃 weft，同腰头 WIDTH 映射；`apply_shrinkage` 形参 1 控 X、2 控 Y；warp/weft 取机头裁片专用 `back_yoke_shrinkage_warp/weft`，None 回退全局 `shrinkage_warp/weft`）-> `add_seam_allowance`（**边名→缝份 dict** `{top,bottom,cb,side}`：`cutter._sa_amount` 鸭子类型化 dict|`WaistbandSeamAllowances`，机头底边埋夹 1.2、腰口/后中/侧缝 1.0，§4.1；后中为左右对称片拼合线仍外扩〔非折线〕，与腰头后中折线不同）。**底边两端斜角 (bottom,side)=PN / (bottom,cb)=P0 用镜像折角**：`add_seam_allowance(corner_treatments={("bottom","side"):"mirror",("bottom","cb"):"mirror"})` → `cutter._mirror_point`（**真反折角构造**：被镜像边缝份边界**整条线**（锚点+方向）关于折线边净缝线轴对称后交折线边缝份边界，翻折后角点像恰落被镜像边毛缝边界上、缝份边缘与裁片轮廓严丝合缝，§4.2.1；直角角点锚点不动退化即 miter，仅斜角相异，详见后片裁片 §10.6 第 3 条。键=(折线边,被镜像边)首元素恒 bottom；cutter 序 PN 角正序 (bottom,side)、P0 角逆序 (cb,bottom)，两种顺序键都查、逆序命中时 _mirror_point 形参交换。镜像退化平行→回退 miter→阶梯）。
4. 刀口（§5.1，净样位 + 毛样缝边位双层）：净样位 = 后中拼合中心点（对称片 Cut 2；有省另加拼合线两端 C_in 底边侧/St_in 腰口侧）。毛样位 = `_project_notches_to_sa` 在缩水->缝边后**整体替换 gross_notches**（flow 私有工艺策略，同腰头/前片先例，不动 cutter 公开 API）：**净样角点刀口每角 2 刀**——沿 cutter 序行走找相邻异名边角点（PN/X/O/P0 共 4 角，同名边平滑续接无角点），入边净线延长线（`_edge_tangent` 末端切向）交出边缝份边界 + 出边净线反向延长线交入边缝份边界，共 8 刀完整标出相邻两缝真实起止；净样刀口（后中/省位）沿所在边外法向（`_nearest_edge_tangent` 最近边切向的 perpendicular，cutter 外扩同约定）交缝份边界——后中同腰头 §四.2.1「垂线交缝边」口径。交点用 `_ray_hit_poly`（射线 ∩ 毛样折线取最近命中）在毛样折线上求取，自动兼容镜像折角；射线无命中回退沿射线平移一个缝份（缝份 0 退化为净点）。SVG/DXF 取 gross_notches 优先，缝合线位净刀口保留在 shrunk_notches。丝缕线竖向（经向=局部 Y）。吃势对位刀口（底边弧长比例 1/2、1/4 + 后片上口对应位）仍未程序化（back_yoke_steps 声明留工艺层）。
选项字段：back_yoke_seam_allowances（YokeSeamAllowances：top/bottom/cb/side，TOML `[options.back_yoke_seam_allowances]` 子表）/ back_yoke_join_fillet（拼合折角 G1 倒圆量 cm，默认 0.4；0=不倒圆直接顺接）/ back_yoke_side_corner_mirror（内缝顶点 bottom×side 缝份镜像折角开关，默认 True；False=纯 miter）/ back_yoke_cb_corner_mirror（后中底角 bottom×cb 缝份镜像折角开关，默认 True；False=纯 miter。两角独立）/ back_yoke_shrinkage_warp / back_yoke_shrinkage_weft（机头裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft，§3/§5；非 None 须在 [0,0.2)；TOML 尺寸单里属 options 主表字段，须置于所有 [options.*] 子表之前，否则被吸入前一个子表、主表读不到而静默回退全局）。输出：`--yoke-svg` 旗标 / `api.run(yoke_svg=...)`（需完整整版且 back_yoke 开启）。

前口袋独立裁片（袋贴/贴袋）已程序化：`build_front_pocket(main_ctx)`（`flows/front_pocket_flow`，前口袋裁片.md §一~§三；自含裁片，非 FlowRunner 编排，同 `build_waistband`/`build_yoke`/`closure.py` 口径）。按口袋类型派发（front_pocket_facing 优先，否则 front_patch，都没开 raise ValueError）：
1. 挖削嵌入式（INSET，front_pocket_facing 开）→ `build_front_facing` 袋贴裁片（§1.1）：**外边界 1:1 完美复制前大片**——腰弧段 waist=`front.pocket_facing_waist_edge`（O→P_fw）+ 外缝弧段 side=`front.pocket_facing_outseam_edge`（P_fs→O），内边 inner=`front.pocket_facing_inner`（单曲线）或 polyline 模式 `front.pocket_facing_inner_seg{i}` 折角链（P_fw→P_fs）闭合截取。**先画后裁**：袋贴边界已由 `draw_front_pocket_facing`（front_pocket_steps）上版，本流程只提取、不重画。内部标记 marks（§1.1 必须保留）：袋口切削线 `front.pocket_mouth`（有省）/ 净线 `front.pocket_mouth_baseline`（无省）/ polyline 的 `_seg{i}`；有省另加吃省边 `front.pocket_cut_start`（P1→P1′）。刀口（§2.2）= 袋口净线起止端点 [P1′（有省）或 P1、P2]，延伸方向顺着袋口弧线切线延长线（`_mouth_extension_dirs`：bezier 单曲线 / polyline 链首末段端切线——首端取反向越过 P1′/P1 延入腰头缝份、末端取正向越过 P2 延入侧缝缝份）投至缝边，**净样线位 + 缝边位成对**入 gross_notches（I/V 型刀口，"同时打在净样线与外侧缝边上"）。
2. 表面外贴式（PATCH，front_patch 开）→ `build_front_patch` 贴袋裁片（§1.2）：前大片保持 100% 完整，直接拷贝净样母线 `front.patch_net_seg{i}` 闭合链；seg1 命名 top（袋口内折边）、seg2..N 命名 side（四周缝边）。净刀口 = 各净角点 `front.patch_net_pt{i}`；毛样刀口 = 各净角点沿相邻净边延长线交缝边、每角 2 刀折边指示（入边延长线交出边缝份 = 顶部内折线两端、出边反向延长线交入边缝份 = 四周缝边折角；**贴袋除袋口外全命名 side，几何折角 side×side 相接仍上刀、不按边名跳过**——异于机头 `_project_notches_to_sa` 的同名平滑跳过规则）。无内部标记。
3. 共享收尾 `_finish_piece`：主版坐标 **Y 轴反射**到局部（`local=(x−origin.x, origin.y−y)`：X 不翻保侧缝在左/前浪在右、Y 翻让腰头在上袋身向下，同 `piece_svg` 不翻转口径）→ **自定向**（反射 det=−1 翻转绕向，闭合多边形 shoelace > 0 则反转边序 + 每条 geom 反向，目标 < 0 保 cutter 外法向外扩，同机头负面积约定）→ 竖向丝缕线（经向 = 大片裤中线垂直方向 = 局部 Y，bbox 中心 x，上下各留 15%）→ 先缩水后缝边（§2.1）→ 刀口投影（§2.2，flow 私有 `_project_notches` 整体替换 gross_notches，同机头/前片先例不动 cutter 公开 API；`_finish_piece` 形参 `notch_dirs_main` 给出即袋贴切线方向投影、None 走贴袋角点投影）→ 装配 PatternPiece + 局部 ctx。**坑：刀口延伸方向向量必须与刀口点走同一仿射链（Y 反射翻 dy → 缩水 dx/(1-weft) / dy/(1-warp)）——各向异性缩放会转动方向向量，直接复用主版切线方向再投影就不再是缩水后袋口弧线的切线**（交点在缩水->缝边后的毛样折线上以 `_ray_hit_poly` 射线求取取最近命中，无命中回退沿射线平移一个缝份/净点）。
4. 缩水/缝边：`apply_shrinkage(weft, warp)`（经向 = 局部 Y → Y 吃 warp、X 吃 weft，同机头 WIDTH 映射；**warp/weft 取前口袋专用 `front_pocket_shrinkage_warp/weft`，None 回退全局 `shrinkage_warp/weft`**，换布/不同批次可单独控制）；缝份 dataclass 直传 `add_seam_allowance`（边名 = 字段名：袋贴 `FrontFacingSeamAllowances` waist/inner/side、贴袋 `FrontPatchSeamAllowances` top〔袋口内折边〕/ side〔四周缝边〕）。
选项字段：front_pocket_facing_seam_allowances（FrontFacingSeamAllowances：waist/inner/side，默认均 1.0）/ front_patch_seam_allowances（FrontPatchSeamAllowances：top 默认 3.0 / side 默认 1.2，TOML `[options.*]` 子表）/ front_pocket_shrinkage_warp / front_pocket_shrinkage_weft（前口袋裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft，§2.1；非 None 须在 [0,0.2)；TOML 尺寸单里属 options 主表字段，须置于所有 [options.*] 子表之前——否则被吸入前一个子表、主表读不到而静默回退全局）。输出：`--front-pocket-svg` 旗标 / `api.run(front_pocket_svg=...)`（需完整整版且 front_pocket_facing 或 front_patch 开启）。

袋布独立裁片（一片式对折）已程序化：`build_front_pouch(main_ctx)`（`flows/front_pouch_flow`，口袋布裁片.md §2~§6；自含裁片，非 FlowRunner 编排，同 `build_front_pocket`/`build_yoke`/`closure.py` 口径）。
1. 一片式对折构造（§2）：底层 = 大片原样复制（节点链 seg2..segN→bottom + 侧缝链→side + 腰弧 b→P_w0→waist，跳 seg1 折叠边）；面层 = 小片（上版时已挖袋口）沿袋布内边 P_w0→K1（`front.pouch_waist_anchor`→`front.pouch_node1` 连线）轴对称后反转拼合。小片上沿已走袋口切削线（有省 C_cut=`front.pocket_mouth` / 无省净线=`front.pocket_mouth_baseline`），镜像即得挖削，免布尔运算。对折边 P_w0-K1 为内部折叠线不入周界，进 `marks` 折叠指示。
2. 省口闭合：面层腰弧边必须取 P1′→P_w0——小片腰弧边起于 P1，省口 P1′→P1 张开会致轮廓 GAP；`_build_top_waist` 沿有效腰弧按弧长细分重建 `bezier_subrange(w_arc, t_at_length(p1_dist+dart_width), t_at_length(p1_dist+waist_safe))`。**勿用 `t_at_y`**（腰弧近水平，区分不了 P1/P1′）；与 `draw_front_pocket` 的 P1′=point_at_length 口径一致保证严合。勿复用 `front.pouch_small_waist_edge`（起于 P1，带张开省口）。
3. 镜像边命名：面层镜像反转边加 `_m` 后缀（bottom_m/side_m/waist_m）——折叠点 P_w0/K1 处异名边（waist/waist_m、bottom_m/bottom）强制 cutter miter，防折叠角缝份缺量；**mouth 仅面层独有、无底层对边，不加 `_m`**（SA dict 只有 mouth 键，加了后缀查不到→0 缝份）。SA 走 dict：`{bottom,bottom_m,side,side_m,waist,waist_m,mouth}`，`_m` 同值；缝边调用传 `miter_limit=float("inf")` 不限长（锐角保留标准 miter 交点，见 §10.10）。
4. 坐标/对称性检验/刀口/丝缕：局部 = Y 反射 origin=P_w0（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向。局部 Y 反射与主版 P_w0-K1 镜像共轭 → **面层 = 底层关于局部折叠轴 (0,0)→local_K1 的镜像**（test_pouch_piece 对称性断言据此，免在主版坐标重算）。**辅助线 marks（§5 画稿对位，2026-08 增）**：折叠线之外另上版前口袋弧线（设计净线，`_collect_mouth_chain(cut=False)`，恒有）+ 口袋省弧线（切削线 C_cut，`cut=True`，有省才有——无省与净线重合免重复），主版坐标 `_to_local_geom` 直转局部，SVG markline / DXF 层 8 内部画线。**刀口（§5 新规范，2026-08 重做）**= **底层未挖削完整侧**袋口弧线端点 P1 / P1′（有省）/ P2，各沿所属弧线切线延长线（首端取链首切线反向、末端取链末切线正向，同袋贴 `_mouth_extension_dirs` 口径）经 `_ray_hit_poly` 交毛样折线**只打在缝边上**（§5.1，整体替换 gross_notches）；面层挖削侧免打口（§5.3）；旧折叠角 P_w0/K1 + 镜像点 P1″/P2′ 净位刀口已废（折叠指示由折叠线 mark 承担）。方向向量与刀口点同一仿射链（Y 反射翻 dy → 缩水 dx/(1-weft)/dy/(1-warp)，同袋贴坑）。丝缕竖向 = 局部 Y（§6 继承大片经向）。
5. 缩水（§3）：**默认强制 0** 绝对隔离大身面料——与机头/前口袋的 None 回退全局不同，袋布是默认 0 数值、无回退语义；非 0 才走 apply_shrinkage。
选项字段：front_pouch_seam_allowances（PouchSeamAllowances：fold=0 对折线 / mouth=1.0 袋口 / waist=1.0 / side=1.0 / bottom=1.2，TOML `[options.front_pouch_seam_allowances]` 子表）/ front_pouch_shrinkage_warp / front_pouch_shrinkage_weft（默认 0.0，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同前口袋/机头缩水口径）。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）均已录入。输出：`--front-pouch-svg` 旗标 / `api.run(front_pouch_svg=...)`（需完整整版且 front_pouch 开启）。另注：`front_pocket_dart_width` 默认 0 不吃省（用户口径；需要吃省时显式录入 1.5~2.5，测试有省场景须显式置值，反解析层 2 不发射该键即走此默认）。

门襟独立裁片（单排/双排）已程序化：`build_front_fly(main_ctx)`（`flows/front_fly_flow`，门襟裁片.md §1~§4；自含裁片，非 FlowRunner 编排，同 `build_front_pouch` 等口径）。步骤层 `_draw_separate_fly` 已把独立门襟净样叠画在前片上（先画后裁），本流程只提取、不重画；`fly_separate` 未开 raise ValueError。返回 `(单排片, 双排片|None, 局部调试 ctx)`：
1. 单排（单层，§2）：原样提取 5 边——top=reverse(腰头线子弧 O→T)、outer×3（外缘直线 h−R → 底角 90° 圆角贝塞尔 → 底边，**精确 G1 链必须同名 outer**，见 §10.10）、inner=内边（与前浪缝合线重合）。刀口 1 = 内边自 O 开深 L 处（拉链止口/前浪对位）。
2. 双排（对折，§4）：去底角弧——外缘重构直线 `LineSegment(T, E)`（E = T + 前浪方向·h 重算，**e_bot 未上版勿从圆角反推**；与内边严格平行绝对等长，O/T/E/S 平行四边形）、底端 E→S 直线闭合（顶保留腰弧）；半边沿对折轴 O→S 镜像展开（`_reflect_geom` 贝塞尔控制点同步），**镜像边加 `_m` 后缀异名**（SA dict 按 top/top_m 等各键取基边同值）——对折接缝 O/S 交 cutter 正常 miter：O 为反射角（内角 >180°，两腰弧谷底对接切线突变），miter 交点落在两边偏移链**途中**，`add_seam_allowance` 反射角裁剪把越交点的采样尾/头部点裁去（不裁则两偏移链角部自交 = 顶部缝边三线交错；曾改同名边跳过角点即死于此——同名桥接段 + 两段越轴尾段三线互穿）；S 为凸角（bottom ∥ chord(T,O)，与镜像底边折 ≈20°）miter ≈1.02·sa 正常生成不回退阶梯。对折线 O→S 不入周界、进 marks 折叠指示。刀口 3 = 对折线两端 O/S（文档强制，**沿对折轴线向外投影**、与中心对称线绝对共线供车间直线对折——主边外法向带前浪斜度必然歪斜，用户口径；打口方向沿轴写入 `PatternPiece.gross_notch_dirs`〔与 gross_notches 索引对齐、指向内部〕，piece_dxf 组码 50 与 piece_svg 刀口短线优先消费该方向；轴向取缩水后 O→S 刀口对。落点 = 轴线∩毛样外沿：无缩水时镜像对称、轴线恰过缝边顶点〔上端反射角裁剪交点、下端凸角 miter 顶点〕属工艺指定落点，有缩水〔各向异性缩放破坏镜像〕时落顶点旁侧段中共线顶点，切线均可判）+ 外缘 T+前浪方向·L。`fly_sep_double=False` 时双排片返回 None。
3. 共享收尾 `_finish_fly_piece`：局部 = Y 反射 origin=O（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（经向=局部 Y，与前/后片一致）→ 缩水（`fly_shrinkage_warp/weft`，**None 回退全局**主面料口径，同机头/前口袋，异于袋布默认 0）→ 缝边（`FlySeamAllowances`：top/outer/bottom/inner；bottom 仅双排消费；**miter_limit 显式传 2.0**——门襟拐角〔腰口×外缘 T、底边×内边 S 等〕内角 ≈82°，miter ≈1.52·sa 恰超默认限 1.5 **静默回退阶梯角**，缝边拐角凸一个缝份量台阶（目检症状"前浪线外侧缝边不直"）；与前片尖裆 75°/≈1.64·缝宽 同属限长坑，但此处拐角是常规形态、抬高限值即可〔2.0=内角 60° 以下才回退〕，勿用 `"miter"` 自然尖角处理）→ **刀口法向投影至毛样外沿**（`_project_notches` 同前/后片 flow 私有实现：净样刀口沿所在边外法向射线交毛样折线；净样位刀口〔shrunk_notches〕保留为对位锚点，gross_notches 整体替换——净样位刀口不在折线上不显示、也非打口位置。**落点须在段中或共线顶点**：ET 按裁切折线顶点吸附挂刀口符号，刀口恰落 miter/裁剪交点等角顶点（两侧折线不共线）时切线方向无法判定、渲染成十字孤立点（同 §10.3.1）。故 `_notch_normal` 角点命中多条边时**一律不取法向均值（角平分）**——均值恰把刀口投到缝边角顶点上（凸角 = miter 顶点、反射角 = 裁剪交点）；改按斜率取 |dy| 最大主边（沿前浪方向的内边/外缘）外法向，刀口 ⊥ 主边恰 1·sa 量级落该边缝边线上（`fly_sep_extra=0` 时单排 S 角/双排外缘 E 角即此路径；双排对折端点 O/S 不走法向投影——`_project_notches(axis_pair=(0,1))` 沿对折轴线向外投影并与中心线共线，见上 2）→ 局部 ctx 落 `front_fly_single/ double.edge{i}`。
金标注意（test_fly_piece）：底角圆角弧长**无闭式**——外缝顶点 T 取在弧形腰头线上（弧长 W 处），前浪与底边实际夹角 ≈82° 而步骤层 `_QUARTER_K` 手柄常数按 90° 圆弧调定，贝塞尔外凸（实测 ≈4.92 vs 90° 圆弧 4.71）；断言改用构造不变量（径向两侧距 e_bot = R + 弧长界于圆弧 R·θ 下界与控制多边形上界）。闭环断言用 `distance_to < 1e-9` 容差（贝塞尔接缝有 ~1e-14 浮点噪声，勿用精确相等）。刀口/拐角金标：毛样刀口到毛样折线垂距 <1e-9 且 = 净位刀口 + 外法向·sa（⊥ 边）；拐角用**解析 miter 交点命中**断言（测试内独立复算两偏移切线交点，非硬编坐标）。刀口落点回归（十字孤立点报障）：`_on_corner_vertex` 断言毛样刀口不落角顶点（顶点两侧折线不共线）；角点刀口（fly_sep_extra=0）⊥ 主边恰 1·sa；双排对折端点 O：解析 miter 交点命中 + 两腰弧自然垂足（O+切向法向·sa）被反射角裁剪、均不在毛样折线（三线交错回归），S：miter 命中且无阶梯尖刺；O/S 刀口**沿轴线**断言位移与 gross_notch_dirs 均与轴共线（cross<1e-9），无缩水时恰落缝边顶点（工艺指定落点，`_on_corner_vertex` 豁免）。
选项字段：fly_sep_double（双排裁片开关，默认 True）/ fly_seam_allowances（FlySeamAllowances：top/outer/bottom/inner 默认均 1.0，TOML `[options.fly_seam_allowances]` 子表）/ fly_shrinkage_warp / fly_shrinkage_weft（门襟裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft；非 None 须 [0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同前口袋/机头/袋布缩水口径）。两示例尺寸单均已录入。输出：`--front-fly-single-svg` / `--front-fly-double-svg` 旗标 / `api.run(front_fly_single_svg=..., front_fly_double_svg=...)`（需完整整版且 fly_separate 开启；双排开关未开时双排输出跳过并警告）。

小表袋独立裁片已程序化：`build_watch_pocket(main_ctx)`（`flows/watch_pocket_flow`，小表袋裁片.md §一~§四；自含裁片，非 FlowRunner 编排，同 `build_front_fly` 等口径）。步骤层 `draw_front_watch_pocket` 已上版净样（先画后裁），本流程只提取、不重画；watch_pocket 未开或 `front.watch_pocket_seg1` 不存在 raise ValueError。按 watch_pocket_mode 派发，返回 `(PatternPiece, 局部调试 ctx)`：
1. 模式 A（facing_intersect，§2.1）：四边界闭合拓扑 pt1→pt2→pt3→pt4→pt1 = top 袋口直线 + side 内侧边 + bottom 底边（袋贴内边贝塞尔子段）+ side 外侧边。**底边方向归一**：`curves.bezier_subrange` 恒从参数小端跑向大端、方向随袋形不定，按角点距离归一到 p0≈pt3 / p3≈pt4（`_reverse_geom` 弧长不变），否则闭合链断裂。
2. 模式 B（custom，§2.2）：`while f"front.watch_pocket_seg{i}" in ctx.sheet` 经 `sheet.get(...).geom` 收集混合 line/curve 闭合链（同 `build_front_patch` 口径，line/curve 混合不能用 ctx.line/ctx.curve 读）；N==4 同模式 A 三类边名（top/side/bottom/side）、N≠4 时 seg1=top 其余 side（任意多边形无法可靠识别底边，bottom 字段不生效）。
3. 共享收尾 `_finish_piece`：局部 = Y 反射 origin=pt1 袋口外上角（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（经向=局部 Y；局部变换仅平移+Y 翻转无旋转，主片裤长竖向映射后仍竖向，与小表袋摆放 rotate_deg 无关，§3.2）→ 缩水 → 缝边 → 刀口投影。刀口（§4.2 v1.2）4 个 = 袋口外上角/内上角各 2 刀：净样位 pt1/pt2（缝合线位；刀口为独立 Point 只转局部、不随边反转），毛样位经 `_project_hem_notches` **投影至毛样外沿缝边上**——每角顺着缝边延长线（入边末端切向越过角点）交袋口缝边一刀、顺着袋口顶部线延长线（出边首端切向反向）交侧缝缝边一刀，即入边延长线交出边缝份、出边反向延长线交入边缝份，**同前口袋 PATCH 每角 2 刀口径**，标袋口折边横纵基准（指引缝纫工位折叠袋口）。交点在缩水 -> 缝边后的权威毛样折线上求取（`_ray_hit_poly`），射线无命中回退角点沿射线平移一个缝份（退化防御）；`_geom_tangent`/`_sa_for`/`_ray_hit_poly` 均与前口袋 flow 同款私有实现（不动 cutter 公开 API）。v1.2 起中段装配对位刀口（模式 A 底边弧长中点 / 模式 B 最长非顶边中点）不打。金标（test_watch_pocket_piece）：模式 A 每角 2 交点独立复算（角点沿切向射线 ∩ 对侧偏移线，与射线求交同构不同径）1e-6 命中 + 刀口到毛样折线垂距 <1e-6（验「打在缝边上」）；模式 B 混合弧边验外沿 + 与角点沿切向延长线共线（弧切向倾斜时交点可远离角，距离无界勿设角域上界）。
4. 缩水（§3.1）：**里料默认 0** 绝对隔离大身面料，同袋布口径（异于机头/前口袋/门襟的 None 回退全局）；`if warp or weft` 条件式、默认跳过 apply_shrinkage。缝份 `WatchPocketSeamAllowances` 直传（top 袋口折边 2.5 双折边明线 2.0~2.5 取上限 / side 1.0 / bottom 1.0 默认恰与袋贴 inner 一致，§4.1）。
选项字段：watch_pocket_seam_allowances（WatchPocketSeamAllowances：top 2.5/side 1.0/bottom 1.0，TOML `[options.watch_pocket_seam_allowances]` 子表）/ watch_pocket_shrinkage_warp / watch_pocket_shrinkage_weft（默认 0.0，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同袋布缩水口径）。api.run() 形参含 watch_pocket_mode / watch_pocket_width / watch_pocket_taper（此三者属补齐既有透传缺口，绘制层选项此前 api 未透传）/ SA dict / 缩水率 / watch_pocket_svg。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）均已录入。输出：`--watch-pocket-svg` 旗标 / `api.run(watch_pocket_svg=...)`（需完整整版且 watch_pocket 开启）。

后贴袋独立裁片已程序化：`build_back_patch(main_ctx)`（`flows/back_patch_flow`，后贴袋裁片.md §1~§5；自含裁片，非 FlowRunner 编排，同 `build_watch_pocket` 等口径）。步骤层 `draw_back_patch_pocket` 已上版净样（先画后裁），本流程只提取、不重画；back_patch 未开或 `back.patch_net_seg1` 不存在（含 --until 中断、未开 back_yoke）raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`：
1. 净样 1:1 完整复制（§1）：`while f"back.patch_net_seg{i}" in ctx.sheet` 经 `sheet.get(...).geom` 收集闭合链（line/arc 混边不判类型，同 `build_watch_pocket` 模式 B 口径）；边名按 back_patch_shape 派发：rectangle `[top,side,bottom,side]` / baker_shield 5 边（底尖两斜边均 bottom）/ angular 6 边（两斜切均 bottom）/ custom：N==4 同 rectangle、N≠4 `[top]+[side]*(N−1)`（同小表袋口径，任意多边形无法可靠识别底边）；段数与形态模板不符抛 ValueError（防上游形态路由变更静默错位）。净角点仅收袋口两角 pt1/pt2 作折边指示刀口（**底部角点不打口**，§4）。
2. 共享收尾：局部 = Y 反射 origin=pt1 袋口近后浪侧顶点（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（§5：经向=局部 Y 与后大片裤长**绝对平行**；局部变换仅平移+Y 翻转无旋转，贴袋在主版上的摆放旋转角保真保留为袋与经向的夹角）→ 缩水 → 缝边。
3. 缩水（§2 大身面料全链路）：`back_patch_shrinkage_warp/weft` None 回退全局 `shrinkage_warp/weft`（同机头/前口袋/门襟口径，**异于袋布/小表袋的里料默认 0 隔离**）；竖向丝缕 → Y 吃 warp、X 吃 weft。
4. 袋口折边（§3，cutter `HemTreatment` 只产折边几何）：top 边为直线 → `add_seam_allowance(..., hem=HemTreatment("top", taper))`——**锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线**（折边自毛样外侧缝边线起翻、翻盖全宽 = 毛样在袋口层的全宽，翻折后恰与侧缝折边区重合），自 P_notch 沿镜像方向 `D=E−2(E·N)N`（E=角点处指向袋内的侧边切线）上行距袋口线 sa_top 得 M、沿袋口内收 |taper| 得 T（倒梯形防折后毛边外露）；毛样顶链 P_notch_a→T_a→T_b→P_notch_b **凸链**（P_notch 由角点 miter 折边侧 sa 传 0 自动得出，作毛样角点 + §4 顶部线延长刀口的落点）。**§4 袋口刀口（flow 层 `_top_hem_notches`，用户口径）**：净口两角（内上角 pt1/外上角 pt2）各两刀共 4 刀、**底部不打口**——角点沿**侧缝边延长线**（前侧边到达切向自 a 越角直行 / 后侧边出发切向取反）交毛样外沿一刀 + 沿**袋口顶部线延长线**（背离袋口段）交毛样外沿一刀（落点即 P_notch 毛样角点），两刀分别标折边线与侧缝折线在缝边上的穿越位；交点经 `_ray_hit_poly` 取射线与毛样折线**最近正距**命中（s≤1e-6 弃——side=0 时顶线延长交点退回净角即弃刀），**整体替换 gross_notches**（同门襟 `_project_notches` 口径，缝合线位刀口保留在 shrunk_notches）；打口方向 = 交点处缝边内法向（垂直缝边指向裁片内、按毛样质心定向；顶边刀口即经向竖直向下、P_notch 角刀口沿袋口线向内），显式写 `gross_notch_dirs`。custom 弧袋口（seg1 贝塞尔）无直线镜像轴 → hem=None 降级常规法向放缝 + flow notes 显式记录（无袋口刀口）。刀口类型/深度（默认 I、0.3cm）仅工艺标注进 notes、不改位置几何。缝份 `BackPatchSeamAllowances`（top 袋口折边 2.5 双折 / side 1.0 / bottom 1.0）。
选项字段：back_patch_seam_allowances（TOML `[options.back_patch_seam_allowances]` 子表）/ back_patch_top_hem_taper（默认 −0.15，≤0）/ back_patch_notch_type（默认 "I"=垂直一字刀口，§4 2026-08 定型；"V"/"I" 均合法）/ back_patch_notch_depth（默认 0.3）/ back_patch_shrinkage_warp / back_patch_shrinkage_weft（None=回退全局，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同机头缩水口径）。api.run() 形参同步透传 6 参数 + back_patch_svg。示例尺寸单 examples/size_female_zhitong.toml 已录注释键（其 custom 袋口为直线 → hem 生效，可作 CLI 手测）。输出：`--back-patch-svg` 旗标 / `api.run(back_patch_svg=...)`（需完整整版且 back_patch 开启〔依赖 back_yoke 定位〕）。

前片独立裁片已程序化：`build_front_piece(main_ctx)`（`flows/front_piece_flow`，前片裁片.md §1~§3；自含裁片，非 FlowRunner 编排，同 `build_back_patch` 等口径）。**无 bool 总开关**——前片净样元素整版必有，由输出旗标直接驱动；`front.hem` 不在版（--until 中断/空版）raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`。三大形态以**净边条件矩阵**装配（18 组合 = 腰头 2 × 口袋 3 × 门襟 3，主版自然序：前浪区 → 下裆缝 → 脚口 → 外缝上行 → 侧缝弧上段 → 袋口挖削 → 顶边腰弧）：
1. 弯腰头剥离（§1.1）：统一经 `steps.front_steps.effective_waist(ctx)`（返回 (B/B′, 腰弧, 侧缝弧长)，与口袋/门襟步骤同源同口径）；顶边 = 弯 `front.lower_waistline_arc` / 直 `front.waistline_arc`；前浪自 A′ 起按 rem = W − 斜线长三分支（斜线余段 / `bezier_subrange(rise_curve, t_at_length(rem), 1)` / rem==0 跳零长段）。
2. 口袋挖削（§1.2）：侧缝弧截到 P2（`t_at_length(s_side − p2_drop)`，与步骤层同式同源）；挖削边 mouth = 切削线反向（有省 `front.pocket_mouth` / polyline 链逆序；dw=0 切削线即净线同元素）；顶边腰弧自 P1′（有省）/P1（无省）起余段；`front.pocket_cut_start`（P1→P1′ 吃省撇削边）属挖除区**不进大片边界**。
3. 连裁门襟（§1.3）：fly 四元素（top/outer/bottom 底角弧/bottom 融合弧——后两段**同名** G1 平滑续接）+ 前浪自 fly_tangent 起余段（extend 与 front_fly_steps 同式重算：fly_blend_drop None 时 `max(fly_blend_extend, extend_min)`）；fly_separate 时叠画元素不进边界、与无门襟同形。**门襟底缘在臀围线之上**（fly 外线不与臀线相交）。
4. 局部化/自定向/丝缕：Y 轴反射 origin=B/B′（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 → **片上恒存反转链**：waist 自 A/A′ 起、rise/fly_top 环回 A/A′（测试断言端点方向须按此存向，勿按主版自然序）；竖向丝缕（X 不翻避镜像，经向 = 局部 Y）。
5. 缩水/缝边/折角：`front_piece_shrinkage_warp/weft` None 回退全局（主面料口径，同机头/门襟）→ `add_seam_allowance`（`FrontSeamAllowances`：waist/rise/inseam 1.0、side 1.5、hem 裤口卷边 2.5、mouth/fly_* 1.0）+ 裆尖角部两态（`front_piece_crotch_corner`）：**True（默认）= 镜像折角** `corner_treatments={("rise","inseam"):"mirror"}`——**折线边 = 前浪 rise**：前浪缝份翻折时折轴是前浪缝本身、非下裆缝，下裆缝侧缝份边界关于前浪折线镜像、翻折后与下裆缝缝份边平齐（键序判别法见 §10.10 mirror 键序条；cutter 双向查键，链序任一顺序命中）。**False = 切线直线延伸 miter** `("rise","inseam"):"miter_line"`（用户口径：前浪尖处的缝边 = 前浪缝边延长线与内缝缝边延长线相交）——两侧缝边各沿裆尖处端切线**直线延长**相交于单一顶点（经典打版作角；交点距角点 = sa/sin(θ/2)，直筒尖裆 ≈75° 时 ≈1.64·缝宽，实测 zhitong 缝份 1.0 顶点恰高裆尖 1.0）；不限长，两切线平行退化回退阶梯。cutter 尖角三取值现行口径：`"miter"` = 不限长自然尖角（`_natural_join_sharp`/`_extrapolate_offset` 贝塞尔多项式自然外延求交——point_at/tangent_at 对 t∉[0,1] 照公式求值、外延点法向 = 外延处导数法向，采样 0.5cm、搜索窗 4·max(sa)+20；多项式外推的摆钩发生在远端、首个交点落在钩回前的近角段，直线边沿轴向延伸即切线 miter，**后片 False 态在用**；无交回退切线 miter→阶梯）；`"miter_line"` = 切线直线延伸（前片 False 态）；`"round"` 等距圆弧能力保留（含放不下时回退级）但前片裆尖不用。**圆弧抹角（等距弧/大圆弧/浪尖相切圆角）已全部废除——净样裆尖是尖的，缝边只能是尖的**；**勿依赖默认限长 miter**——尖裆内角下 miter 长 >1.5 限长会静默回退阶梯角、留「竖一刀+斜一刀」台阶，凡工艺要求尖角跟随净样的角点必须显式不限长（§10.10 miter_limit 条）。四轮沿革（轮廓延伸态/内切圆/等曲率延续/钝角平顶等中间方案及死因）见决策日志。
6. 刀口法向投影（§2.3，flow 私有实现不动 cutter 公开 API）：净样刀口 [膝围×2 防扭脚、臀围、袋口 P2+P1′/P1、拉链止口（连裁，外缘链 `point_along_chain` 开深 L 处）、脚口×2、毗围点（thigh_line 存在时；d=0 内端 = 裆尖角点跳过）] 定位载体边（直线参数投影 clamp / 贝塞尔 64 采样最近点 / 角点命中多边取法向分量均值）沿外法向射线与 gross_polygon 折线求交取最小正 s，**整体替换 gross_notches**；shrunk_notches 保留缝合线位不丢信息——**gross=裁剪线位、shrunk=缝合线位**，对位断言用 shrunk。膝围双刀口按所在边缝宽外移（侧缝 1.5 / 下裆 1.0）。**脚口双刀口 = 内外侧缝 ∩ 净样脚口线角点（`front.hem_outseam/hem_inseam_point`），用户口径：与净脚线对齐、不与卷边宽关联，打在内外缝毛样缝边上**（两轮纠偏见决策日志）。角点刀口走 **pinned 限定载体边机制**：`_notches` 返回 (全部刀口, (点, 限定边名) 子集)，`_project_notches(pinned=...)` 坐标比对 <1e-9 命中则 `_notch_normal(only_name=...)` 限定在 side/inseam 边内取单边外法向、投影到该边毛样缝边——距净点 == 该边缝宽且 ⟂ 脚口端切线（同膝围绝对精准口径；默认角平分法向会把投影推到毛样外角点上）；pinned 点须随缩水同比例 ÷(1-weft, 1-warp) 后才与 shrunk_notches 可比坐标。
7. 内部辅助线 marks（§3.3）：臀/膝/毗围水平线以净边链折线求交取 min/max x 截断（连裁组臀线右端落门襟底角弧、口袋组左端落侧缝弧上段）；随缩水同比例变换（cutter `apply_shrinkage` 已同步缩放 marks）。
选项字段：front_piece_seam_allowances（TOML `[options.front_piece_seam_allowances]` 子表）/ front_piece_crotch_corner（默认 True=镜像折角；False=切线直线延伸 miter——前浪缝边与下裆缝缝边各沿端切线直线延长相交于单一顶点，用户口径 2026-08-24）/ front_piece_notch_type（"V"/"I"，仅 notes 工艺标注）/ front_piece_shrinkage_warp / front_piece_shrinkage_weft（None=回退全局，[0,0.2)；TOML 主表键须置于所有 [options.*] 子表之前，同机头缩水口径）。两示例尺寸单均已录入。api.run() 形参同步透传。输出：`--front-piece-svg` 旗标 / `api.run(front_piece_svg=...)`（需完整整版；无开关守卫分支）。金标 tests/test_front_piece.py：18 组合参数化闭合/定向/结构 + 边长独立复算 + 端点链向 + 折角/刀口/缩水/marks。

后片独立裁片已程序化：`build_back_piece(main_ctx)`（`flows/back_piece_flow`，后片裁片.md §1~§6；自含裁片，同 `build_front_piece` 口径，不在 FULL_FLOW 内）。**无 bool 总开关**--后片净样元素整版必有，由输出旗标直接驱动；`back.hem` 不在版或 back_yoke 开但 `back.yoke_cb_point` 未上版（--until 中断）均 raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`。上边界三形态以净边条件矩阵装配（腰头 2 × 机头 有/无 = 4 组合，主版自然 CCW 序：上边 -> 侧缝下行 -> 脚口 -> 内侧缝上行 -> 后浪上行，链首 = cb_top）：
1. 分离基准（§1）：后片独立裁片不含腰头与机头。有 yoke：上边 top = `back.yoke_bottom_seg{i}` 链（P0->PN 1:1 复制，空链回退直线 P0->PN 同 yoke 口径）；无 yoke 直腰头：waist = `back.waistline_arc`（A->B **弧原方向即 cb->side 侧，勿反向**）；无 yoke 弯腰头：waist = `back.lower_waistline_arc`（O'->X' 同向）。后浪/侧缝下行链 = `(rise_slant, rise_curve)` / `(反向髋腰弧, outseam_upper, outseam_lower)`，自链首顶点取**弧长后缀**（`_chain_suffix`：首个被部分消费段在 d 处切开、贝塞尔走 `bezier_subrange(t_at_length(d),1)` 保形）--d 与 `back_yoke_steps` 量取同式同源（有 yoke = D_端点 + 弯腰头下移 W；无 yoke = 弯 W / 直 0）。局部化：Y 轴反射 origin = cb_top（有 yoke P0 / 无 yoke A 或 O'）+ shoelace<0 自定向（主版 CCW 反射即 CW，正常不反转，链首恒 = (0,0)）。
2. 后省（back_dart 开）：省尖落在裁片区内（省穿越上边界）时**边界按图提取**（省量吸收主口径是 back_waist_dart 约克转移，与机头 §2.2 绕尖旋转不联动）+ stderr 告警一次 + 省腿裁片内子段（折线采样射线法 + 64 采样首末在内点）进 marks；省尖在上边界之上则全由机头吸收、无痕。
3. 缩水/缝边/折角（§2/§3 顺序：净样 -> 缩水 -> 缝边，缝份绝对值不乘缩水率）：`back_piece_shrinkage_warp/weft` None 回退全局（主面料口径）-> `add_seam_allowance`（`BackSeamAllowances`：top 拼机头 1.0 / waist 装腰 1.0 / cb 后浪 1.0 / inseam 1.0 / side 1.5 / hem 脚口卷边 2.5）+ 浪尖角部两态 `corner_treatments={("cb","inseam"):"mirror"|"miter"}`（`back_piece_crotch_corner` 默认 True=镜像折角〔折线边 = 后浪 cb，同前片裆尖 (rise,inseam) 先例〕；False=纯尖角跟随净样）。**镜像折角 = 真反折角构造**（`cutter._mirror_point` 全裁片共用）：被镜像边缝份边界**整条线**（锚点+方向）关于折线边净缝线轴对称后交折线边缝份边界——M 翻折后的像恰落被镜像边毛缝边界上（距 == 0，缝份翻折不缺角缺肉），直角退化仍 = miter（金标 test_back_piece 翻折像距线 == 0、test_yoke 60° 演算 (−√3,1)）。**轴穿越点 X**（`cutter._axis_cross`，全 mirror 角通用）：被镜像边缝份边界沿自身方向延伸至翻折轴（折线边净缝切线过角点）的穿越点 X 后再转 M——直接连偏移链自然端点到 M 的弦会让被镜像边缝边线到不了角点等高处、折像非全线贴合；经 X 中转后 X→M 段恰沿镜像线、翻折像与被镜像边毛缝边界全线重合（X 在轴上与角点等高，后片实测 X.y == 裆尖.y）。被镜像边为下边时 X 插在 M 后、头部裁剪基准改 X（按 M 裁会漏裁 X—M 间采样点成折返乱序）；为本边时 X 插在 M 前。演进见决策日志。
4. 刀口（§4 v1.1：**侧缝机头拼接有、浪尖对位无**，总原则=打在最外缝边轮廓上、不打内部净样线；法向投影同前片 flow 私有实现）：膝围×2、臀围×2（`back.hip_outseam_point`/`back.hip_inner_final`，cb 侧取最终线内缝端点与 §5 所画斜量线终点重合）、**横裆线 ∩ 缝边交点不打口**（用户口径：d=0 时与毗围刀口重复、后浪侧无对位用途）、脚口×2（**与净样脚口线对齐** = 内外侧缝 ∩ 净样脚口线角点，用户口径 2026-08：不与卷边宽关联）、毗围点（thigh 录入时；**d=0 内端未单独上版时回退裆尖角点，且回退角点 pinned 到 inseam 边**——角点命中 cb/inseam 两边，角平分法向会把浪尖刀口推斜，pin 后沿内缝外法向投影、垂直打在内缝缝边上（= 反折角起点，与 d>0 内端刀口同载体边、缝内缝时前后片对位；保 §5 基准点完整、有录入恒两刀）、口袋对位（贴袋顶线 `back.patch_net_seg1` 自侧端沿袋口方向延长 ∩ 侧缝链 `_chain_hit`）、**上边界两角各双射线刀口 + 贴袋对位顶部刀口（用户口径；角点十字标记已废——打在缝边顶点上无用）**：cb_top 沿后浪线延长线一刀（交顶缝边）+ 沿机头线延长线一刀（交后浪缝边）、side_top 沿侧缝线延长线一刀（交顶缝边）+ 沿机头线延长线一刀（交侧缝缝边），`_junction_rays`（到达边切向越角直行 + 出发边切向反向）+ `_ray_hit`（同 back_patch_flow 私有口径）交毛样外沿、打口方向取交点处缝边内法向；贴袋定位孔 drills 沿丝缕（局部 -Y 向上）`_pocket_top_notches` 交顶缝边。`_net_edges` 仍返第三值 side_top 作射线角点（有 yoke=PN / 直腰头=B / 弯腰头=X'，随缩水 ÷(1-weft,1-warp)，cb_top 原点缩放不动）。**脚口双刀口 pinned 限定载体边**（前后片统一口径）：`_notches` 返回 (全部刀口, (点, 边名) 子集)，`_notch_normal(only_name=)` 限定 side/inseam 单边外法向、投影至该边毛样缝边——距净点 == 该边缝宽且 ⟂ 端切线（同前片/膝围绝对精准口径；pinned 点随缩水 ÷(1-weft, 1-warp) 后才与 shrunk_notches 可比坐标）。**后中/侧缝角点刀口已废除**（原沿角平分外法向投影的角点十字标记打在缝边顶点上无用，由上边界双射线刀口取代；毛样刀口 = 法向投影集 + 双射线 4 + 贴袋顶 2，`with_gross` 追发、`notch_dirs` 前 N 个 None 出口层自推，shrunk_notches 不含角点——角点非缝合线位）。**勿据后片裁片.md §4"不外扩投影（角点刀口保留净样位）"回退**——该短语系 v1.0 遗留表述（与前片文档"卷边起折点"同为过期措辞），已被用户三轮目检定型口径（前后片统一 pinned 打缝边上）取代，代码注释与记忆均已标注。
5. 内部线/定位孔（§5/§6）：**臀围线 = 最终后臀围线 `back.hip_line_final` 1:1 拷贝**（用户口径：内高外低斜量线、弦长 = H/4+Δ，两端点本就在净边上——内缝顶点在后中斜线 cb 链、外缝点是髋腰外缝弧起点 side 链；基础水平线 `back.hip_line` 非测量基准、冗余不画，同毗围/横裆先例）；膝围水平线随净边截断为 marks；**毗围线 1:1 拷贝真实测量线**（外缝点->裆端**斜量线**，两端点本就在净边上——按水平 a.y 截断会在 d=0 时与横裆线同高重合叠影且丢斜量方向）；**横裆线不画**（用户口径：毗围线即其测量基准、横裆水平线冗余，横裆高度交点亦不打口；后片裁片.md §5 已同步改写）+ 后贴袋顶线 1:1 拷贝 mark；贴袋上端两顶点（`back.patch_net_pt1/pt2`）进 `PatternPiece.drills` 定位孔（新字段，随缩水同步变换，`piece_svg` 红空心圈渲染于定位图层）。
选项字段：back_piece_seam_allowances（TOML `[options.back_piece_seam_allowances]` 子表）/ back_piece_crotch_corner（默认 True）/ back_piece_notch_type（"V"/"I"）/ back_piece_shrinkage_warp / back_piece_shrinkage_weft（None=回退全局，[0,0.2)）。api.run() 形参同步透传。两示例尺寸单均已录入（165：注释缩水+mirror 折角+side 1.5；zhitong：缩水 0.1/0.06+前片裆尖切线 miter〔后片仍 mirror〕+side 1.0，跟随各自前片工艺口径）。输出：`--back-piece-svg` 旗标 / `api.run(back_piece_svg=...)`（需完整整版；无开关守卫分支）。金标 tests/test_back_piece.py：4 组合参数化闭合/定向/结构 + 边长独立复算 + 端点链向 + 浪尖两态折角（含翻折像距内侧缝毛边 == 0 真反折角金标）+ 刀口投影/计数矩阵（含角点双射线同式复算 + 贴袋顶部沿丝缕单刀）+ 贴袋引用 + 后省告警/子段 marks + 缩水含 drills 同变换。

贴袋预设形态角点已收敛到公式层：`formulas/patch.patch_net_vertices(shape, w, h, bottom_width, tip_depth, chamfer, chamfer_bottom_taper)` 返回 **v 向下正**规范局部系角点（V0=(0,0) 顺时针；rectangle/baker_shield/angular 三形态路由，"custom"/未知抛 ValueError）。消费方三处共用同一纯函数（单一事实来源，前端不复写公式）：`back_patch_steps`（v 即向下、直接仿射；`chamfer_bottom_taper=False`——angular 不消费底宽 bi）与 `front_pocket_steps` 前贴袋分支（映射 `Point(a.x+u, a.y−v)`，**dy 存储向上正**；`chamfer_bottom_taper=True`——angular 消费 bi）原来各自内联的预设角点改为调它，数值逐位不变；web 端「从形态导入」seed 通道（`webschema.seed_shape`，§10.8）同源。金标：tests/test_patch.py。前后贴袋 v/dy 轴向相反与 angular 消费差异是编辑器/seed 归一化的根口径（§10.7 custom 形态编辑器条目）。

袋布三袋型预设已收敛到公式层：`formulas/pouch.pouch_chain_preset(shape, waist_safe, side_safe)` 返回 (K 节点, 边形态 spec) 二元组（standard/round_bottom/deep_rect；节点相对 O 的 (dx, dy 向下正)，预设定义登记于 袋布绘制.md §4.1）。消费方唯一：web seed 通道（`webschema.seed_shape` kind="front_pouch"，边返回完整 spec 格式 `[["line"], ["arc",2.5,0.6], ...]`）——**steps 不改调**（`PatternOptions.front_pouch_nodes/edges` 默认链字面量不动；standard 在默认安全量 (4,8) 下与其逐位一致由金标钉死，双源防漂移）。金标：tests/test_pouch_formula.py。

3D 试穿 fitting 出口已程序化（`exporters/fitting.py` 的 `build_fitting_payload(ctx, m)`，纯 stdlib：整版全局系 cm Y-up 序列化前后片净边链/边名角色表/站点围度/腰头标量；`PatternPiece` 尾部新增 `origin/frame` 默认字段随片携带，pieces.py×2 + cutter.py 三处重建点透传，金标钉死）。双通道 `POST /api/draft/fitting` 与 `engine_glue._fitting` 同步（tests/test_engine_glue.py 全等）。金标：tests/test_fitting_payload.py。**坐标系/缝合配对/前端 PBD/体型分离口径权威 = §10.11**，演进见决策日志 §十一。

**裁切层与几何踩坑速查已独立为 §10.10（按主题分组）**；各口径的发现过程与纠偏轮次见 [决策日志.md](决策日志.md)。

### 10.7 Web 端（webapp/，一期 2026-08 落地）

一期范围：参数录入（两段式分组面板）-> 两步生成（整版生成/裁片生成，2026-08-25）-> 整版/裁片 SVG 预览 -> 门控 DXF 下载（裁片合集/整版，对应步骤已生成且未过期才可下）+ 尺寸单 toml 导出 + 模板载入。二期（2026-08-25）加**整版拖拽调版**：版上把手拖动 -> 反解参数 -> 回写参数面板并实时重生成（参数⇄几何双向绑定）。启动：`pip install -e ".[web]"` 后 `uvicorn webapp.backend.app:app`（前端 dist 已构建并由 FastAPI 托管；改前端走 `cd webapp/frontend && npm run dev`，Vite 代理 /api）。

- **架构定位**：webapp/ 是引擎外薄壳，全部计算走 flows + exporters 内存渲染（`svg.render_sheet`/`piece_svg.render_piece_svg`/`piece_dxf.render_pieces_dxf`，不落盘）；核心包零依赖承诺不变（fastapi 在 `[web]` 可选组）。裁片清单用 `flows/collect.collect_pieces(ctx)` 动态返回，前端不写死 11 片。
- **两步生成与下载门控（2026-08-25 用户口径，.claude/plans/webapp-phase3-two-step-generation.md）**：生成拆两步——`POST /api/draft/sheet`（整版 SVG+报表，不收集裁片）与 `POST /api/draft/pieces`（动态裁片清单+跳过说明；后端无状态，本端点自跑整版再提取）；旧 `/api/draft` 已移除（消费方仅前端+测试，CLI 不经 FastAPI）。先整版后裁片只是前端 UI 门控（先画后裁）：过期机制=参数版本号——任意参数修改 version+1，产物存 `{data, version}` 快照，版本不等即「已过期」（预览保留、Toolbar 按钮角标+Tooltip 提示——2026-09-07 起弃预览区横幅、对应 DXF 下载禁用）；裁片生成须整版已生成且未过期。互斥：sheetBusy/piecesBusy 互斥、单一 dlBusy 串行下载（DXF 下载重跑引擎）；localStorage 仍只存参数，刷新后生成状态清零。
- **params 新口子**：`Measurements.from_dict` / `PatternOptions.from_dict`（web/JSON 入口，枚举 + 缝份 dict 自动 coerce，`from_file` 重构为复用它）；`params/validate.py` 的 `build_issues(measurements_dict, options_dict)` 把构造期异常逐键归因为结构化 `Issue(param, message, group, level)`（error 阻断/warning 放行），`cross_issues` 显式报 FlowRunner 会静默跳过的跨选项前置条件（袋贴/袋布/小表袋依赖 front_pocket、facing_intersect 依赖袋贴、back_patch 依赖 back_yoke、thigh_limit 依赖 thigh>0；fly/fly_separate 双真曾报 warning、2026-08 移除——fly_type 虚拟下拉已强制互斥，双真仅模板 toml 载入出现且引擎 fly_separate 优先口径不变）。归因算法：Measurements 整体构造失败时逐键回退 `_FALLBACK_M`（165/68A）试探；PatternOptions 逐键累加、失败键回退默认值（**坑 2026-08 修复**：逐键累加对关系型参数对有键序依赖——shape=custom 键先于 custom_points 键入 dict 时，前缀构造里角点仍是默认空元组，即使角点已有效也误报"得到 0 个"；现整体先试全量构造，成功即无键级问题（键序无关），失败才逐键归因）；前端 JSON 编辑框失焦 parse 失败现红框提示（此前静默保留文本，用户误以为值已生效而 state 仍是旧值，是上述误报的常见触发入口）。`api.run` 仍走原异常口径，不强制接校验层（向后兼容）。
- **schema（2026-08-26 下沉至 src/ylpattern/webschema.py，webapp/backend/schema.py 薄再导出、app.py 的 _handles 一并下沉为 webschema.handles——Pyodide 本地引擎复用同源，见 §10.8）**：两段式分组（2026-08-25 用户口径，.claude/plans/webapp-phase2-param-sections.md）——build_schema 返回 sections：**整版绘制**（draft，15 组，画在整版 DraftSheet 上的参数：测量/开关/框架/腰头·口袋·袋布·小表袋·门襟·后机头·后贴袋绘制/腿部弧线/毗围/版面）/ **裁片**（pieces，11 组 craft_ 前缀：全局工艺 + 各独立裁片的缝份·缩水·刀口·裁片构造；裤耳整组归裁片——build_belt_loop 不依赖整版几何）。归属判定=影响整版几何归整版、只影响裁切链归裁片；**每个裁片自有工艺参数与其裁片同组不拆分**（前后片缝份/裆尖角/刀口/缩水率合并进 craft_front_piece/craft_back_piece，用户口径 2026-08-25；**坑 2026-08-27 修正**：waistband_front_drop 曾误归整版「腰头绘制」组——整版上腰口线/下腰头线弧度实由 front/back_waist_curve_sag 控制（下腰头线与上腰口线同 sag），front_drop 仅 build_waistband 裁切链消费，已移裁片段 craft_waistband；v0.7 front_drop 已删、v0.8 两圆顺窗长亦删——整根均匀圆弧无手感参数，craft_waistband 组现仅缝份/缩水/搭门/经向）；craft_front_pocket 组常显、全参数挂参数级 gate（挖削/贴袋/袋贴任一真即显示——组级 gate 是 AND 语义无法表达 OR）。白名单外参数仍兜底 misc（整版段末组，按 key 定位引用，缺失即 raise）。此前 18 组平铺时期演进记录：后省与后机头各自独立成组（**坑 2026-08 修复**：组级 visible_if 不得指向组内自己的开关——back_dart 开关曾随后省组显示，默认 False 成循环隐藏整组不可见，开关须归款式开关组常显）；袋贴独立成组；毗围限制独立成组；front/back_waist_curve_sag 与 side_rise 归腰头组；全局 seam_allowance/show_seam_allowance 归缩水与缝边组（2026-08 自裁片工艺移入，前后片专属缝份留在裁片工艺））；联动 gate 语义--组级 visible_if 数组=全真才显示（如袋布 [front_pouch, front_pocket]），参数级 visible_if 数组=任一真即显示（如口袋缩水率 [front_pocket, front_patch]，2026-08 修复：初版误用组级全真语义导致口袋缩水参数永不显示），参数级 gate 还支持 **{"param","values"} 枚举值匹配对象**（2026-08，后贴袋首用）：形态专属参数随形态下拉切换显隐——back_patch_bottom_width gate=[baker_shield]、tip_depth gate=[baker_shield]、chamfer gate=[angular]、custom_points/custom_edges gate=[custom]（对应关系源自形态路由，以步骤代码为准）；EnumGate 另支持 **requires**（布尔开关键数组，须同时全真）做复合门控——前贴袋形态专属参数（bottom_width/tip_depth/chamfer/custom_points/custom_edges）gate={"param":"front_patch_shape",values:[...],requires:["front_patch"]}（前口袋绘制.md §五）。**坑：前后贴袋 bottom_width 消费不同**——前贴袋 angular 消费底宽（六边形用 bi）、后贴袋 angular 不消费（顶点全用 w/c；options.py 注释写"baker_shield/angular"与代码不符，联动以代码为准，2026-08 修正过后贴袋误 gate 双形态）；前端 gateOn() 统一判定（字符串=布尔开关，对象=枚举值+requires 全真）。默认值从 `PatternOptions()`/`Measurements` 实例反射，中文标签用正则解析 options.py/measurements.py 行内注释（`    name: ... # 标签（说明）`）--**坑：依赖注释排版**，改源码注释格式可能掉标签（回退英文键名，不出错）；彻底稳需换显式标签表。缝份字段 type="sa" 按子字段网格编辑，tuple 复杂结构 type="json" 走 JSON 文本。`visible_if` 声明组级开关联动（口袋关->前口袋组隐藏）。
- **可调点配置表**（二期拖拽已消费，2026-08-25）：`webschema.ADJUSTABLES`（16 条 `Adjustable` dataclass：element/kind(point|curve)/t/param/axis/lo/hi/visible_if，随 schema 一起下沉在 src/ylpattern/webschema.py）是唯一绑定登记处，`build_schema` 的 adjustable_points 从它派生（一期字段名保留兼容）；`binding_for(element, param, axis)` 查表供 /api/adjust 校验；gate 判定 `gate_on`（str=布尔开关 / {param,values,requires}=枚举匹配）与前端 gateOn 同语义、两端各一份。**选参原则**：同一几何量有"系数/规律参数"与"_adjust 修正量"两入口时一律绑修正量（cm 1:1 拖感、跨尺寸/推码稳健、语义=调版旋钮，用户口径 2026-08-25），仅比例单入口时兜底绑比例（back_intake）；被浪长闭合锁死的点（前浪顶点类）不纳入——几何事实而非实现限制。**扩展=纯配置**：新绑定加一行 ADJUSTABLES，求解器与前端零改动。
- **二期拖拽调版链路（2026-08-25）**：`拖把手 -> POST /api/adjust {measurements, options, element, param, axis, target(cm)} -> flows/adjust.solve_param 反解 -> 前端 applyAdjust 回写参数+显式载荷重生成整版`，节流 100ms 单飞不堆积、seq 丢弃过期响应。分四层：
  - **svg.py 元素身份**：render_sheet 给每条线/曲线/点下发 `id="{name}"`（name 全局唯一）、文字标 data-name、根元素 `data-scale/data-ox/data-top` 全精度；`compute_view(sheet)->(width,height,top,ox)` 包围盒逻辑与 render_sheet 同源共用（web 端 px↔cm 逆变换权威源：x_cm=(px−ox)/scale、y_cm=(top−py)/scale）。
  - **flows/adjust.py 反解器**（与 closure.py 平级的"整版重跑"哲学）：`solve_param(m,o,element,param,axis,target,lo,hi,t, guess=None)`（guess 热启动 2026-08-26 加，语义与两点弦截外推见 §10.8，guess=None 逐位等价旧签名）对 f(v)=元素坐标(重跑(replace(o,**{param:v})))-target 在 [lo,hi] 上 bracketed secant-bisection（Illinois 阻尼）求根，每轮求值穿 run_with_thigh_closure（浪长闭合等不变量自动保持）；`element_coordinate(ctx,element,axis,t)` 定位器（点=轴向坐标，曲线=Bezier.point_at(t)，SVG 里曲线是采样 polyline 必须回本体）。护栏：解钳 [lo,hi]；目标超能力 range_clamped 返最近端；参数无位移 no_effect（覆盖 thigh_limit 闭环对抗）；绑定 range 端点超生成能力时**锚点向失败端二分自愈到能力边界**（如 p2_drop>外缝弧长 12.85）不误判 engine_error；仅基线（当前参数值）也不可生成才抛 ValueError（web 转 422）。本批绑定大多线性（sag 中点偏差=-sag、裆宽对修正量斜率±1、Bezier 对控制点线性），secant 2~4 轮收敛，单次 solve 数十 ms。
  - **webapp 后端**：`POST /api/adjust` stateless 同步 def（线程池）——_build 先校验当前参数（422）→ binding_for 未注册 422 → solve_param（t 由绑定表下发不取请求值）→ 求解器护栏内不抛（钳制/no_effect 也 200，拖拽中不弹错，前端按 reason 显示钳制态）。`/api/draft/sheet` 响应扩展 `transform`（compute_view 同源）与 `handles`（ADJUSTABLES 逐条**元素级自门控**：gate 满足且元素在版上才下发坐标——前端零重复判断开关/形态；口袋关时 16->13 条、tangent 模式袋口弧把手消失）。
  - **前端 SheetView**（PreviewPane 拆出）：把手 overlay 注入 SVG 内部 `<g id="yl-handles">`（styles.css 使 svg max-width:100% 响应式缩放，SVG 内坐标自动跟随；指针→cm 必走 getScreenCTM().inverse()）；把手半径/字号按屏幕像素恒定（screenScale 补偿 viewBox 缩放+CSS 缩放两级）；单向绑定画 axis-hint 轴向短线。**React 重注入坑**：dangerouslySetInnerHTML 每次刷新销毁整棵子树——pointer capture 设在持久容器 div、effect 每次刷新后重建 overlay 且拖拽中把被拖把手钉回指针投影位（ref 直改 DOM 不进 state，防把手与指针打架）；拖拽会话/节流/单飞全走 ref（100ms 级不重渲全树）。**useDraft.applyAdjust**：显式载荷（base+新参数值）直接 postSheet——闭包里的 measurements/options 必然滞后于高频拖拽；versionRef 镜像做快照竞态判定（旧响应 ver 不等于当前版本即丢弃）；值圆整 2 位。撤销=lastDrag{param,拖前值} 单步（双击复位同口径记录，复位也可撤销）；拖拽回写 adjustInfo 驱动 ParamPanel 高亮（受控 Collapse 展开目标组+scrollIntoView+flash 动画）。缩放平移=viewBox 方案（滚轮以指针为中心 0.3~8x、空白拖曳平移，getScreenCTM 链自动正确、指针换算无需特判——**方向坑**：getScreenCTM 是 user->屏幕 px 方向矩阵，平移把鼠标 px 位移换算成 user 须取倒数 1/hypot(a,b)，直接用 hypot(a,b) 则跟踪速率=(ctm.a)² 随缩放级漂移〔缩小时慢于鼠标、放大时快数倍，2026-08-25 修复〕）；拖拽中 stale 角标暂隐（每次回写都重生成，松手后必然同步）。**过期提示移按钮角标（2026-09-07 终版，两轮）**：初版 PreviewPane 横幅条件渲染——参数修改出现/拖拽把手暂隐都改变 flex 纵向高度，绘图区被顶上顶下（把手一按一松连跳两次）；二版改 Alert 恒挂载 + visibility:hidden 占位（nbsp 撑行高，普通空格被 HTML 折叠塌零）又被否——常驻空行突兀；终版弃横幅，Toolbar 的 StaleFlag 把警告角标挂到因过期被禁用/门控的按钮右上角（裁片生成/整版 DXF 用 sheetStaleTip、裁片 DXF/推板 DXF 用 piecesStaleTip），悬停 Tooltip 看原因；角标绝对定位不占宽、显隐不推动相邻按钮；禁用态 button 不触发鼠标事件，Tooltip 须包 span 宿主（antd 官方口径）；PreviewPane 相应删掉 sheetStale/piecesStale/dragging props（dragging 移交 Toolbar）。**把手到界即停（2026-08-26）**：range_clamped 响应的 achieved 即该方向可达极限坐标（achieved≥target 记下界、反之记上界，方向无关判法，y 轴反向绑定/能力自愈边界同样覆盖），moveTarget 把指针轴坐标夹进已学边界再钉把手/发求解——到界原地停住、拖回界内自动恢复；新拖拽会话清边界重学。附带 sentTarget 同值免重跑（停界处微动不重跑引擎，请求失败重置）。解出值按 **0.1 步进取整**（2026-08-26：拖到整数/0 才可行，打版精度即 0.1cm；气泡显示与写回同源，取整后值未变则 applyAdjust 自动跳过重生成；面板手输更细值不受影响）。
- 测试：tests/test_web_validate.py（归因+跨依赖金标）、tests/test_web_api.py（TestClient 全链路）、tests/test_svg_ids.py（元素 id/根 data-* 金标）、tests/test_adjust.py（求解器线性金标+可恢复性+护栏）、tests/test_web_adjust.py（/api/adjust 往返+handles 自门控计数+绑定 range ⊆ 硬校验金标；fastapi/httpx 缺失整文件跳过）。
- **虚拟参数与互斥开关（2026-08 用户口径）**：前口袋互斥形态在 UI 层收敛为 schema 虚拟参数 `pocket_type`（type="pocket_type"，选项 无/挖削前口袋/前贴袋，前端映射 front_pocket/front_patch 两开关），两个原始开关标 hidden 不渲染但仍参与校验/生成（引擎与 API 不感知）；两开关同 true 时下拉按「前贴袋」优先显示（与 collect_pieces 派发口径一致）。分组同步拆分：袋贴独立组（visible_if=front_pocket）、前贴袋独立组（visible_if=front_patch）、毗围限制独立组（visible_if=thigh_limit，thigh_* 全部移出臀腰裆框架）。组级 visible_if 支持**多键数组**（全真才显示，如袋布组 [front_pouch, front_pocket]、小表袋组 [watch_pocket, front_pocket]--口袋类型非挖削时附属组整组隐藏）；前端 pocket_type 切离挖削时自动置关 front_pocket_facing/front_pouch/watch_pocket（防残留开启触发依赖校验错误）。前口袋组最终形态（2026-08 用户口径）：前贴袋组**并入**前口袋组（挖削/贴袋参数同组互斥显示，贴袋参数挂参数级 visible_if=front_patch；口袋裁片缩水率双形态共用挂多键 [front_pocket, front_patch]），袋贴组维持独立（visible_if=front_pocket）。front/back_waist_curve_sag（前后腰弧下凹量）与 side_rise（侧缝腰头抬高量）归腰头组（用户口径 2026-08，自臀腰裆框架移入）。schema 白名单条目支持 (参数名, gate) **元组**显式指定参数级联动（可多键），优先于组级 param_visible_if。另支持**参数级 visible_if**（此前仅组级）：schema 组字段 param_visible_if/param_visible_except 给组内参数逐个挂开关联动（前口袋组常显承载类型下拉，但挖削参数逐个 visible_if=front_pocket，切贴袋时隐藏）；前端 ParamPanel 按 p.visible_if 过滤，搜索态不受联动限制。
- **虚拟形态下拉（2026-08 用户口径）**：互斥形态开关不直接显示，由组内置顶虚拟下拉驱动并隐藏原始开关（_HIDDEN）——pocket_type（无/挖削前口袋/前贴袋 -> front_pocket/front_patch；切走挖削时自动关 facing/pouch/watch_pocket 防依赖校验报错）、fly_type（无/连裁门襟/独立门襟 -> fly/fly_separate）。参数归属：口袋组内挖削参数 gate=front_pocket、贴袋参数 gate=front_patch、口袋缩水率 gate=[两者任一]；门襟组内宽/开深/底角 gate=[fly,fly_separate 任一]、turnback/stitch_inset gate=fly（连裁专属）、sep_*/缝份/缩水 gate=fly_separate（独立专属）。模板两开关同开时下拉按引擎口径取后者优先（front_patch / fly_separate）。
- **custom 形态结构化编辑器（2026-08-27，贴袋 custom 点/边原只有单行 JSON 文本框不可用）**：schema 新增虚拟参数类型 `custom_shape`（`back_patch_custom` / `front_patch_custom`，gate=shape 值 custom；spec 携带 kind/points_key/edges_key/v_positive/choices 元数据）——前端 `CustomShapeEditor`（点/边双表上下堆叠保输入框宽度 + 联动增删 + 内联 SVG 轮廓预览 + 从形态导入）直写 `*_custom_points/_custom_edges` 两真实键（pocket_type 写多开关同款先例）。**坑（2026-08-27 修复）**：build_schema 虚拟参数特判的 `continue` 早于通用 gate 挂接点，SECTIONS 里声明的参数级 gate 被静默丢弃（编辑器在非 custom 形态下也常显）——虚拟分支内须单独挂 `visible_if`。原 4 个 json 键入 `_HIDDEN`（不渲染不进搜索，但仍在 schema 全集：422 归因到这些键、由编辑器合并承接，toml 导出不受影响）。**口径**：编辑器内部统一 v 向下正显示（前贴袋存储 dy 向上正，读写换算取负）；边 i 连点 i→i+1 末边闭合、删点同步删边、加点同步加边 (0,0.5)（边数==点数是引擎硬校验）；**预览角点可直接拖拽**（pointer capture + getScreenCTM 映射用户系、0.1 圆整回写、命中半径随最近邻距自适应、表格行高亮联动——2026-08-27 二轮改版：上移/下移按钮无用以拖拽取代）；预览弧边与引擎 `curves.arc_through` **同式三次贝塞尔**（两控制点各沿法向偏移 bulge·8/3、放在弦上 at/2 与 (1+at)/2，实际弧高 ≈ 2·bulge；显示系法向 (dy,−dx) 为引擎 Y-up 左手法向 (−dy,dx) 经 v 向下镜像，凸向与整版一致）。**坑（2026-08-27 用户报障：预览弧线效果不明显、与整版形状不符）**：初版用二次贝塞尔 Q、控制点只偏移 bulge，画出的弧高仅 0.5·bulge，与引擎 8/3 三次的 2·bulge 差 4 倍——预览曲线必须复刻引擎控制点构造而非"顶点近似"。**gate 扩展**：bottom_width/tip_depth/chamfer 的 values 追加 custom——custom 态作为「从形态导入」的基准尺寸可见可调（引擎 custom 分支不消费）。预设角点收敛到 `formulas/patch.patch_net_vertices`（前后贴袋 steps 与 seed 共用单一来源，chamfer_bottom_taper 登记前侧 angular 消费底宽 bi 的行为差异）。
- **custom 编辑器通用化（2026-08-27 二轮，方案 .claude/plans/custom-chain-editor-plan.md）**：`CustomShapeEditor` 由贴袋扩展覆盖袋布/小表袋——三类对象 = **mode × edge_format 正交组合**：贴袋 closed+bulge（现状逐位不变）、小表袋 closed+spec、袋布 open+spec（链 P_w0→K1..Kn→P_s0，**边数 = 节点数 + 1**、节点 ≥2、弧顶分位闭区间 [0.1,0.9]；小表袋锚点 ≥3 闭合、开区间 (0,1)，删点 i 同删边 closed i / open i+1）。schema 侧改**表驱动**：`webschema._SHAPE_EDITOR_SPECS` 四条目（mode/edge_format/anchor_keys/choices），新增虚拟参数 `front_pouch_chain`（无 gate——链恒自定义）与 `watch_pocket_custom`（gate=watch_pocket_mode 值 custom），原始 4 键（front_pouch_nodes/edges、watch_pocket_points/edges）入 `_HIDDEN`。**spec 边表**：每行 = 模式 Select（line/arc/bezier）+ 4 参数位列复用（arc 用 弧高/位置、bezier 用 α°/κ1/β°/κ2、line 全禁），模式切换重置该边默认值（arc=(2,0.5)、bezier=(30,0.4,−30,0.4)），软校验口径同引擎 `_normalize_edge_specs`。**open 链近似锚点**：P_w0 ≈ (+（p1_dist+waist_safe), 0)（腰弧近似水平；**x 正向与 K 节点 dx 同系朝门襟**，初版误写负号致链形错乱、2026-08-27 修正）、P_s0 ≈ (0, p2_drop+side_safe)（侧缝近似竖直）——前端由 spec.anchor_keys 四参数直算、方块标记标「近似」不可拖（真值由整版几何实时定，预览仅示意）。**坑**：options state 初始为 {}、只有 touched 键有值，锚点参数未手输时须回落 schema 默认值（ParamPanel 建全参数 defaults 表兜底）否则双锚点坍缩在原点。**预览缩放（2026-08-27 用户需求）**：vp=null 自适应 bbox，用户缩放后接管为显式 viewBox（1~15x、重置回自适应）；滚轮以指针为焦点（须原生 addEventListener {passive:false}——React 合成 onWheel 是 passive，preventDefault 无效页面跟着滚）、按钮以中心为焦点；getScreenCTM 含当前 viewBox，拖拽/焦点换算在任意缩放级自动正确。**坑（2026-08-27 用户报障：袋布预览显示不全、底部节点被裁）**：自适应 bbox 的 pad 四方向里 maxY 误写成减号——盒底边向内推进 pad 量，最低的 K 节点正好出框（minY 是正确加号、顶部多留空白，视觉即「两个节点很下面看不见」）；四边必须同向外扩，最低点永远在框内。**bezier 预览镜像口径**：引擎 Y-up 系 rotate(+α) 经 v 向下镜像 = 显示系矩阵 [[cos,sin],[−sin,cos]]（等效角度取负），控制点按 `curves.edge_geom` 同式前端复算（显示层近似、引擎为准，与贴袋 arc apex 复算同类先例）。小表袋不做 seed 导入（choices 空、工具条隐藏；facing_intersect 几何依赖整版，纯预设意义不大），rotate_deg 只影响摆放不进预览。
- **折叠默认态（2026-08-25 两段式口径）**：参数面板两级嵌套 Collapse（外层 section/内层组），默认态全由 schema 的 collapsed 字段驱动（前端不再硬编码 defaultActiveKey）——整版绘制段展开且仅「基础测量」组开、裁片段整段收起（延续用户口径：默认仅展开基础测量）。非搜索态 section 内组全被 gate 隐藏则整段不渲染；搜索/错误 Badge/gate-hint 均不上卷 section 标题。含错误的组靠标题 Badge 计数提示，用户自行点开。
- **参数显示名口径（2026-08）**：前端参数名一律显示英文 key（用户口径），schema.py 顶部 `USE_CN_LABELS = False` 总开关，置 True 恢复源码注释解析的中文标签；分组标题/界面文案不受影响。
- **前端组件库（2026-08）**：Ant Design 5（zh_CN locale、主题色 #2c6e49），组件映射--分组面板=两级嵌套 Collapse（外层 section「整版绘制/裁片」+ 内层组，错误组挂 Badge 计数、misc 收起）、参数行=Switch/InputNumber/Select（缝份=小网格、tuple=JSON 文本 Input）、裁片预览=Tabs card 式（原 tab 裁片被关闭时回退首个 tab）、校验=Alert 横幅、下载失败=errors Alert（2026-08 改：下载收进 useDraft，错误入 errors 数组与生成失败同口径呈现）、模板=Select；AntApp 包裹供 useApp 取 message 实例。antd 全量引入 bundle ~694KB（gzip 228KB），内部工具可接受，未做按需分割。
- **启动坑**：webapp/backend/app.py 含包内相对导入，cd 进 backend 目录用 `python app.py` 直跑必报 "attempted relative import with no known parent package"；唯一正确姿势是项目根目录 `python -m uvicorn webapp.backend.app:app`（app.py 末尾 __main__ 守卫会拦截误用并给出指引）。另两条运维坑（2026-08-25 实测）：**长驻旧 uvicorn 不加载新代码**——改后端后必须重启进程（新起的 uvicorn 绑不上原端口会静默退出，浏览器仍连着旧进程看到旧路由；换端口或 `netstat` 查 PID 杀之）；**仓库跟踪了 `__pycache__/*.pyc`**——stash 往返后 `git stash pop` 会因 pyc 冲突中断（工作区停在 HEAD、全部改动滞留 stash），恢复：先 `git checkout HEAD -- <pyc 目录>` 再 pop。
- **前端高度链坑（2026-08-25 用户报障）**：antd `App` 组件包裹层 `.ant-app` 只设 color/font **不设高**（antd 源码可证）——`html/body/#root` 的 height:100% 链在此断裂，`.app` 的 100% 对 auto 父退化成内容高，整页被参数面板撑出 window 滚动条；拖拽回写高亮的 `scrollIntoView({block:'center'})` 会**沿祖先链连滚所有可滚容器**（含 window），把整版预览滚出视口。修法两处：styles.css 补 `.ant-app{height:100%}` 打通链路——左栏 param-panel（overflow-y:auto）与预览 tabs content-holder 各自内部滚动、页面级滚动条消失；ParamPanel 高亮弃用 scrollIntoView，改 rect 差算目标 scrollTop 后 `root.scrollTo` **只滚面板自身**（等价 block:'center' 居中；即便将来高度链再断在某处也只影响左栏，不再连带整版）。
- **整版 svg 固有宽度坑（2026-08-25 用户报障）**：render_sheet 的 svg 根带固有 `width/height`(px)+viewBox，`.svg-view svg{max-width:100%;height:auto}` **只缩不放**——容器宽于固有宽度时元素停在固有宽、右侧留白，viewBox 放大的内容在元素边缘被裁剪（右侧容器空白用不上）。修法：`.sheet-view svg{width:100%;height:100%;max-width:none}` 铺满面板，等比交给 viewBox+默认 preserveAspectRatio（xMidYMid meet 居中留边）；高度链需逐级打通 `.preview-tabs{flex:1;min-height:0}`（antd tabs 根原为 auto 高）+ `.ant-tabs-content/.ant-tabs-tabpane{height:100%}` + `.sheet-view{height:100%}`。附带改善：初始整版放大到填满面板（不再被固有 px 封顶）；裁片 tab 超高仍由 content-holder 滚动不受影响。
- **推板导出（多码 DXF + 尺寸单回写，v1 2026-08-27，交互四项经用户拍板）**：入口 = Toolbar「推板 DXF」按钮（门控同裁片 DXF：piecesReady 且未过期且无错误）+「推板设置」齿轮（常开）；未配置时点下载直接弹配置抽屉（首跑零摩擦），抽屉底部主按钮「导出推板 DXF」= 保存 + 下载一步完成。**档差口径 = 基码锚定（2026-08-27 二次拍板；首版「统一与上一码、空格恒在首码」在基码居中场景反直觉——基码前插码后首码格空、基码格反可录）**：码序小→大、正号=码增大；**基码行是锚**（档差格恒「—」，各码绝对值只读取参数面板——跨码唯一变量是 Measurements 的引擎口径）；基码**上方行录「与更大相邻码之差」、下方行录「与上一码之差」**（全表全正数，任何非基码行均可录入）；表格档差向量 d 与引擎行间差 gapAt(i)=v(i+1)−v(i)=band_of(行 i+1) **互为投影**：d[k]=k>base?gapAt(k−1):k<base?gapAt(k):0（锚位无信息、序列化永不被读），导出按行序+锚位解回 gapAt 再等值连段成 band（首码并入首段免疫孤儿校验）；**换基码 = `rebaseTable` 重投影**（先解回 gapAt 再按新锚投影，物理放码关系不变——直接改 baseIndex 会把差值错位解读），行插入/删除/换位则**档差跟行走**（码序重组、灰字所见即所得；删/移锚行后新锚位清 0 保持不变式）；灰字 = `sizeRun.ts absoluteValues` 自锚双向换算各码绝对值。**保存时序列化**：相同档差的相邻码自动合并为 band 段（等值连段；引擎只按 band_of(k) 查 k≥1 步进，等值段拆并展开不变），**首码并入首段 band**（sizerun._expand 孤儿校验会打回不在任何段的非基码，而 band_of(首码) 从不被查询、并入无语义差）；canonical `SizeRunSpec{enabled:true,base,style,order,band[]}` **永不带 sizes 逐码覆盖键**——v1 不支持，模板带覆盖在 normalizeSizeRun 丢弃并 message 提示；thigh 基码=0 时大腿围列禁用（引擎全码 0 特例）。**后端**：`DraftRequest.size_run: dict|None`（生成端点与 glue 均忽略此键）；`POST /api/dxf?kind=size_run` -> `_build`（基码校验）+ `api.size_run_from_dict`（内存入口，**enabled=false 自查报错**——from_spec 只校验开关类型，值仅在 load_size_run 探测生效，不自查则 web 误传 false 也能展开、与 CLI 口径分叉）+ `api.run_size_run_groups`（run_size_run 抽出的逐码重打版内存核心，返回 contexts/groups/残差行/基码 trace；run_size_run 重构为文件包装、CLI 行为逐位不变）-> `render_size_run_dxf`（内存 doc，逐码摆放带+AAMA 共层+块名 {片名}-{码}，Sample Size=基码）-> 文件流 `size_run.dxf`（固定名：base 可能非 ASCII 不进 header）；ValueError 一律 422 字符串（/api/adjust 同口径）。**toml 回写闭环**：`render_size_toml(measurements,options,size_run)` 尾部追加 `[size_run]`（enabled 恒 true）+ `[[size_run.band]]`（8 键全量显式、档差 round(2)），导出文件可直喂 `cli draft --size` 进多码模式复现同一份 DXF。**前端**：转换/校验纯函数收敛 `src/sizeRun.ts`（normalizeSizeRun/toGradeTable/fromGradeTable/absoluteValues/validateTable，vitest 金标 src/sizeRun.test.ts——前端首个测试设施，`npm test`）；useDraft 增 sizeRun state（localStorage 同键加可选 `size_run` 字段，旧存量无键兼容；**setSizeRun 不 bump version**——码表不影响整版/裁片快照新鲜度）；`download(kind,{sizeRun})` 显式覆盖参是硬要求（抽屉保存+下载同 tick，不用覆盖参必取闭包旧值）；sheetDxf/piecesDxf 载荷不带 size_run（与两步生成严格同构）；TemplatePicker 载入模板时透传 `[size_run]` 段（enabled=false 也预填——抽屉存在性即配置态）。**校验分工**：前端管可输入态（标签空/重复、style 可打印 ASCII），引擎是数值合法性唯一裁判（逐码展开交叉校验失败 422 带码标签）。glue 不加命令（DXF 恒 HTTP），engine zip 顺带打包新引擎函数但 worker 不调用。**web 与 CLI 产出的 DXF 字节不等但几何逐位等价**（已实测同一 toml 两路全量比对：CLI `saveas` CRLF 行尾 + `999 ANSI/AAMA` 注释头 + ezdxf 自动补的 `_archtick` 等标准箭头块；后端 StringIO `doc.write` 为 LF 且不补——此差异在单码 pieces 链路同样存在；比对须逐实体比 INSERT/TEXT 与裁片块几何而非比字节，且注意 CRLF 文件经 `ezdxf.read(io.StringIO(latin-1 解码))` 会静默得空 modelspace，要用 `readfile`）。二期预留：抽屉内逐码裁片 SVG 预览（复用 run_size_run_groups 返回的 contexts）、sizes.X 逐码覆盖编辑、DXF 下载的逐码毗围收敛/skips 回执。

### 10.8 本地引擎（Pyodide 浏览器内计算，2026-08-26）

拖拽调版 HTTP 化后每次微调 = 反解 4~6 次整版重算 + 全量 SVG 传输 + innerHTML 重建，端到端 1~3s「一卡一卡」。解法：**同一份引擎源码打进浏览器 Web Worker 跑 Pyodide（wasm CPython）**，整版/裁片/反解全本地零网络；HTTP 通道保留为回退 + DXF/下载出口。引擎核心零第三方依赖是前提（Pyodide 只需纯 stdlib 代码），不改成 TS 重写（保住「每一笔唯一对应生成函数」单源）。

- **打包链（内容寻址，引擎变更如何到达客户端）**：`scripts/build_engine_zip.py` 递归打 `src/ylpattern/` + `webapp/engine_glue.py` 为**确定性 zip**（固定 1980 时间戳、条目排序 → 同内容同字节流）→ sha256 前 8 位作文件名 `public/engine/ylpattern.<hash8>.zip` + `manifest.json`{zip, git rev, pyodide 版本}；`scripts/sync_pyodide.mjs` 从 node_modules/pyodide 拷 4 个非 JS 资产（pyodide.asm.mjs/.wasm、python_stdlib.zip、pyodide-lock.json，**在包根不在 dist/**）到 `public/pyodide/<版本>/` 自托管（无 CDN 依赖、离线可用）。两目录均 .gitignore。`npm run build:engine` 一键跑两个脚本，`predev`/`prebuild` 钩子自动执行；开发中途改引擎代码手动重跑 + 刷新（worker 内 Python 无 HMR；rev 角标可确认）。**缓存策略**：manifest.json 每次 worker 冷启动 fetch({cache:'no-store'})；zip 文件名即内容 hash → immutable 长缓存，引擎一变 zip 名就变、旧缓存自然作废。
- **worker 启动链（src/engine/worker.ts，module 型 Dedicated Worker）**：fetch manifest → `loadPyodide({indexURL:'/pyodide/<版本>/'})`（入口 JS 由 Vite 从 npm 打包，asm.mjs/wasm 运行时按 indexURL 拉自托管资产；pyodide.mjs 的 node:fs 等导入全在 IN_NODE 守卫的动态 import 内，Vite externalize 成浏览器桩但永不触碰）→ fetch zip → `unpackArchive(zip,'zip',{extractDir:'/ylengine'})`（目录解包不用 zipimport——webschema 的标签解析要读源文件）→ sys.path.insert → pyimport('engine_glue') → 上报 ready。**vite.config.ts 须 `worker:{format:'es'}`**：worker 动态 import 产生代码分割，默认 iife 报「UMD and IIFE not supported for code-splitting」。
- **RPC 协议（src/engine/protocol.ts）**：请求 `{id, cmd:'sheet'|'pieces'|'adjust'|'seed', payload}`；响应/进度共用 `type` 判别字段（response|progress）——**TS 坑**：判别式窄化要求判别属性在联合每员上都声明，EngineResponse 漏 type 时 `msg.type==='progress'` 直接编译错。worker 内调 `engine_glue.handle(cmd, payload_json) -> str`：**JSON 字符串往返不经 PyProxy**（无句柄泄漏、可结构化克隆）；glue 永不 raise（worker 对 parse 再兜一层）。错误两分法：`validation`（与 HTTP 422 同构 IssueDetail[]，参数问题换通道结果一样，直接抛上层不回退）/`engine`（worker 侧异常，回落 HTTP）。**坑（2026-08-26 用户报障：拖拽后 TypeError 读取 undefined 的 map、整版消失）**：glue「永不 raise」意味着失败也是**正常返回的 `{"ok":false,"error":{...}}` 信封**——worker 不得无条件 `ok:true, result:JSON.parse(out)` 回发，否则错误信封被当 SheetResult 流入 useDraft（`sheet_svg` undefined 整版被顶掉、`res.warnings.map` 抛 TypeError）；worker 必须拆信封：`out.ok===false` 时按 `out.error.kind` 转 `ok:false` 错误响应，让 client 侧 validation→EngineValidationError / engine→EngineFailure（回落 HTTP）的既有通道生效。此层为 TS，test_engine_glue 金标覆盖不到，改 worker 消息处理时须人工过一遍失败信封路径。
- **glue（webapp/engine_glue.py，CPython 下可测）**：`_build/_sheet/_adjust/_pieces/_seed` 逐字段复刻 app.py 端点（含 transform/handles/params/reason/evaluations 键名）。**金标 tests/test_engine_glue.py 钉死两份实现不漂移**：同输入下 sheet（SVG 逐字符）/pieces/adjust/seed 响应与 TestClient **全等**，validation detail 与 422 detail 全等；漂移即红——改任何一端必须同步另一端。
- **seed 命令（2026-08-27，custom 编辑器「从形态导入」；同日泛化袋布）**：`POST /api/seed {kind, shape, options}` / `cmd:'seed'` -> `webschema.seed_shape(kind, shape, options)`——kind="front_patch"/"back_patch" 走 `formulas.patch.patch_net_vertices`，返回 v 向下正规范系角点 + 全直线 (bulge, at) 边（前后侧统一；前侧编辑器写回时 dy 自行取负）；kind="front_pouch" 走 `formulas.pouch.pouch_chain_preset`（自 options 取 front_pouch_waist_safe/side_safe 两安全量，缺省回退 4/8——中间态可用），返回 K 节点 + **完整 spec 边格式**（["line"]/["arc",h,t]/…）。小表袋无 seed（编辑器 choices 恒空不可达）。**入参刻意不带 measurements、不走 _build**：seed 只依赖目标对象的尺寸子集（贴袋 5 尺寸参数 / 袋布 2 安全量），且其余参数处于中间态（可能暂时非法）时也要可用，避免无谓 422 耦合；非法 kind/shape/尺寸两通道同构（HTTP 422 字符串 / glue validation）。纯函数毫秒级，TIMEOUTS 5s；打版计算只在引擎做（前端不复写公式）。
- **路由层（src/api.ts，旧 api.ts 更名 apiHttp.ts 内容不动）**：`postSheet/postPieces/postAdjust` 走 `route(cmd,payload,httpFn)`——引擎单例优先（单命令超时 sheet/pieces 30s、adjust 60s），非 engine 类错误（validation）直接抛，engine 失败/超时回落 HTTP；`download/fetchSchema/fetchTemplates` 永远 HTTP re-export（ezdxf 不进浏览器、schema 首屏不等 worker）。上层 useDraft/SheetView 对通道零感知。
- **回退阶梯（src/engine/client.ts）**：`?engine=off` 不建 worker（验收对比用）→ init 超时 60s 或 boot 失败会话降级（sessionStorage 'yl-engine-degraded' 防抖动重试）→ 单次超时/引擎异常本次回落并计数，连续 3 次会话降级 → worker 崩溃自动重建一次、再败降级。StrictMode 双挂载安全：模块级单例 + init 记忆化。UI 呈现：Toolbar 角标「本地计算（绿）/服务端计算/本地引擎加载中」（useDraft 映射 client 的 unavailable→http）。
- **schema 下沉（src/ylpattern/webschema.py）**：backend/schema.py 整体搬进引擎包（ADJUSTABLES/binding_for/build_schema/gate_on + 从 app.py._handles 下沉的 `handles(ctx,o)`），后端 schema.py 薄再导出、app.py 改调——依赖方向 webschema→params/flows.adjust 合法（与 api 同层），tests/test_webschema.py 金标（sections 覆盖、handles 门控计数、再导出同一性）。
- **反解热启动（引擎层唯一计算改动）**：`flows/adjust.solve_param` 增 keyword-only `guess: float|None=None`——在 (lo,hi) 内先求值，|f|≤tol_coord 零迭代返回；否则**替换同号括号端**收紧初始区间（**坑：初版写反成替换异号侧，破坏 fa·fb<0 变号不变量**）；越界/静默失败与 guess=None 逐位等价（存量金标天然守护）。glue `_SOLVE_CACHE` 按 (element,param,axis) 留最近 2 个 (value,achieved)，**两点弦截外推** next guess（斜率=Δachieved/Δvalue）——实测连续拖同一把手第 3 步起 14 次求值降为 1（tol 命中即返）。tests/test_adjust_guess.py 按「远 guess 合同容差内一致 / 单点 ≤冷+1 / 两点 ≤2 / 越界逐位等价」分档断言（**坑：断言 1e-9 过严——求解器合同是坐标容差 0.01cm，不同迭代路径参数值差 ~1e-4 合法**）。
- **生产托管（app.py）**：dist/assets 之外挂 `/engine`、`/pyodide` 两个 StaticFiles；hash 资产加 `Cache-Control: public, max-age=31536000, immutable`（_ImmutableStatic 子类），`/engine/manifest.json` 专用 no-store 路由**先注册、目录挂载后注册**（Starlette 按注册顺序匹配，否则被挂载吞掉）。拖拽节流随本地化 100ms→50ms（单飞/pending/seq 机制不变）。
- 测试：tests/test_webschema.py（schema 下沉金标）、tests/test_engine_glue.py（双通道全等金标，fastapi/httpx 缺失整文件跳过）、tests/test_adjust_guess.py（热启动分档金标）。

### 10.9 agent 包：全部大模型代码（ylpattern 纯引擎边界，2026-09-03）

**定位口径（用户二次拍板 2026-09-03）**：`ylpattern` = 纯引擎（geometry→版型，零 LLM、零触网，源码里不出现模型概念）；`agent/` 顶层包（与 webapp/ 平级、同样不进 wheel、仓库根运行）= **全部大模型相关代码**：`agent/extract/`（照片参数提取管线 12 模块整体迁入，含 provider 唯一触网点）+ `agent/cli.py`（`python -m agent extract` 命令行，argparse 留 subparsers 为二期 serve/会话子命令留位）+ `agent/app.py`（FastAPI HTTP 服务）+ runner/config（编排与 vlm 配置）。演进史：本节初版（同日上午）是「agent 薄壳、extract 零搬移」+「五不变量论证物理搬移不可行」——其隐含前提是 `ylpattern.cli extract` 子命令必须留核心，由此才推出反向依赖；用户指出「ylpattern 就是单纯的引擎代码，所有大模型相关的都应该放到 agent 里」后前提崩塌（CLI extract 子命令本身就是大模型功能、随包迁走），反向依赖与 wheel ImportError 两论据同时消解，当日整体迁移。

- **目录与依赖方向**：`app`（FastAPI 实例 + 路由 + 错误映射）→ `runner`（编排纯函数：照片校验/落盘 → extract 门面调用）→ `config`（vlm.toml 路径解析 + 上传上限）；`cli.py`/`extract/` 与服务层平级共用门面。**依赖方向唯一 agent → ylpattern（绝对导入），引擎侧零反向引用**：extract 内部 4 处引擎引用全改绝对——`probe.py`（`from ylpattern.flows.closure import run_with_thigh_closure` + params.measurements/options）、`validate.py`（params.validate）、`emit.py`（params 两键）、`derive.py`（惰性 DELTA_PRESETS）；只许碰引擎公开层（params / flows.closure / exporters），不 import steps/formulas 内部。独立进程独立端口 8001：VLM 长请求（空闲超时默认 300s）与交互式打版服务互不干扰。
- **迁移清单（纯搬家，功能零变化）**：12 模块相对导入（`.provider` 等）原样；CLI 子命令 `_cmd_extract` + argparse 参数/退出码语义逐位迁至 `agent/cli.py`（`--draft` 分支显式 import ylpattern 的 Measurements/PatternOptions/run_with_thigh_closure + exporters.svg）；`ylpattern/cli.py` 干净移除 extract（头 docstring 注明大模型命令在 agent）；测试 10 文件 + eval 脚本 import 前缀重指 `ylpattern.extract` → `agent.extract`；**pyproject 加 `pythonpath = ["."]`**——agent 是仓库根顶层包，此前靠 `python -m pytest` 把 CWD 放 sys.path[0]，裸 pytest 会失败，extract 测试迁来后依赖面扩大故显式加固。
- **API 与错误映射**：`POST /api/extract`（multipart Form：describe/photos/thinking/run_probe/run_score/max_refeed，sync def——FastAPI 自动走 Starlette threadpool，不阻塞事件循环；一期同步等待，前端未接线且量小，**不做流式/轮询/job 表**，runner 收在纯函数、二期改 background task 只动 app.py）→ `{"ok", "model", "photo_count", **to_web_payload()}`（measurements/options/keys/issues/probe/score 六键契约原样透传）。错误两分：**422** = 参数问题（照片后缀/空文件/超限 ValueError 消息；缺 7 必填 ExtractError.missing 非空 = CLI exit 2 同语义，detail 为 `[{"param","message","level"}]` 对齐 webapp/backend 风格）；**503** = VLM 未配置或上游失败（VLMError 原消息，已核实不含 key）。`GET /healthz` → `{"status","vlm_configured"}`——**只回 bool 不回显配置**（健康检查是公开端点）。
- **配置解析与密钥纪律**：`config.resolve_config_path()` 优先级 `YLP_VLM_CONFIG` 环境变量（显式 toml 路径，部署推荐：systemd/docker 注入，key 只进服务环境）> 仓库根 `vlm.toml`（按 `Path(__file__).resolve().parents[1]` 绝对定位，**不依赖服务 cwd**）> None（交 `VLMConfig.load` 走 `YLP_VLM_*` 环境变量兜底；纯描述无照片时 provider=None 零模型调用）。照片校验白名单 `PHOTO_SUFFIXES` **再导出** `provider._MIME` 键集（_data_uri 按后缀判 MIME，两处同源勿另立清单）、`MAX_PHOTOS=4`、`MAX_PHOTO_BYTES=10MB`；上传照片落 `tempfile.TemporaryDirectory`（provider `_data_uri` 收路径不收 UploadFile，这是 agent 层唯一真实编排点），上下文退出即清理。
- **引擎 zip 无需排除特例**：extract 物理不在 src 树后，同日早间加的 `build_engine_zip.py _EXCLUDE_DIRS` 成死代码已删；src/ylpattern 打包即纯引擎（结构性保证，zip 内 0 条 extract）。
- **二期留位（本次不建）**：会话/记忆/存储（agent/sessions.py 空位）、流式/轮询/job 表、多轮照片追问、断言账本。前端接线一期已做（见下小节）。测试：tests/test_agent_api.py（TestClient + FakeVLM 全程离线，fastapi 缺失整文件跳过）；注入缝 = `monkeypatch(agent.runner, "_build_provider", lambda p: FakeVLM(...))`——真实路径恒返 None 交门面惰性构造。

### 10.9.1 提取服务前端接线（一期最小闭环，2026-09-03）

**范围（用户拍板）**：最小闭环——描述+照片 → 一次调用 `POST /api/extract` → 确认屏（清单+来源徽章+低置信标黄）→ 一键预填表单；照片随请求 multipart 直传；向导式弹层（现有页面不动）。多轮追问/客户端断言账本/照片 hash 缓存（两段式 `/api/photos`）留二期。**agent 侧唯一改动（端到端验证发现的契约缺口）**：`to_web_payload` 的 `keys` 原先只含 axes/switches/enums/derived，7 尺寸行拿不到徽章——尺寸逐键元信息并入 `keys`（`source="描述"`、`confidence=1.0`〔显式数字非模型判断〕、`evidence` 取管线 `measurement_evidence`〔parse 摘录/S1 补漏披露，emit 同源〕），`ExtractResult` 新增 `measurement_evidence` 字段承载；金标 test_agent_api/test_extract_pipeline 各补 waist 断言钉死。

- **连通：`/agent` 前缀统一**（dev/prod 同构、零 CORS 依赖、零硬编码端口）。dev：`vite.config.ts` proxy `'/agent'` → `http://localhost:8001`（rewrite 剥前缀）；prod（dist 由 webapp backend 8000 托管、无 Vite）：`webapp/backend/app.py` 加 `/agent/{path:path}` httpx 异步转发（字节原样透传、timeout 310s 对齐 agent uvicorn 空闲 300s、连接失败 502 中文提示；`YLP_AGENT_BASE` 环境变量覆盖；**httpx 进 `[web]` extra**、路由内懒加载同 ezdxf 先例）。前端唯一取 base 处 `src/agentConfig.ts`（`VITE_AGENT_BASE` 构建变量覆盖，绝对地址时自负 CORS）。回退方案（不动 backend）：agent CORS 放行生产 origin + `VITE_AGENT_BASE` 绝对地址。
- **API 层**：`apiHttp.postExtract(FormData)` **不走 `handle<T>`**——agent 422 detail 是双形态（字符串=照片非法 | `[{param,message,level}]`=缺必填清单），与 handle 硬编码的 IssueDetail[] 口径不同；归一化收在纯函数 `extractPayload.normalizeExtractError`。`fetchAgentHealth()` 失败返 null 不抛（agent 未启动禁提交但不禁输入）。`api.ts` re-export 两条——extract 是纯网络调用（VLM/照片不进 Pyodide 本地引擎），不进 route() 引擎通道。
- **照片前端处理**（`src/imageCompress.ts`）：常量与 `agent/config.py` **同源钉住**（六后缀 jpg/jpeg/png/webp/bmp/gif——**无 heic，前端即拒**；≤4 张；单张 ≤10MB），两端文件头注释互指"改动须同步"；agent 仍是唯一裁判（前端漏拦被 422 兜住）。压缩：`computeTargetSize` 纯函数长边 ≤2048 只缩不放大、`compressImage` createImageBitmap+canvas 输出 jpeg 0.85（款式判据要形态不要像素；VLM 按 blob 计费），解码失败降级原文件直传，压缩后仍 >10MB 抛错（护栏）。
- **状态机**（`src/hooks/useExtract.ts`）：input → submitting → confirm；等待态锁关（Modal closable=false）+ 秒表（同步等待可能数十秒）；确认屏「返回修改」保留输入。输入内容（describe/photos/thinking）归向导组件所有，hook 不持 draft——`confirmPrefill()` 返回载荷，App 层调 `loadValues`。
- **确认屏**（`ExtractConfirm.tsx`）：白话名单源 `/api/schema` 的 `ParamSpec.label`（`buildLabelMap`，custom_shape 背后 points/edges 隐藏键也收录），不另立中文清单；来源徽章按 derive.py 中文常量配色（描述=blue/照片=purple/预判=orange/查表=cyan/派生=geekblue/默认=灰）；**低置信阈值 0.7** 且 source≠'默认'（默认值不是模型判断，标黄无意义）标黄；evidence Popover 溯源；issues 置顶 Alert、款式选项/探针/评分折叠。
- **预填路径与两个坑**：确认 → `d.loadValues(m, o, d.sizeRun)`——**第三参必须显式传**（缺省 null 会清空推板码表，TemplatePicker 传 spec 是同款防坑）；options 含派生键全集直灌（与模板 detail 同语义，ParamPanel 按 schema 显示、引擎 from_dict 拒未知键由 emit 层保证不出现）；未来要按 schema 键过滤只改 `extractPayload.toPrefillPayload` 一处。
- **测试**（vitest 纯逻辑，照 sizeRun.test.ts 金标风格）：`extractPayload.test.ts`（422 双形态/labelMap/低置信/确认行序/预填隔离）+ `imageCompress.test.ts`（六后缀边界/heic 拒/大小边界/目标尺寸只缩不放大）；压缩管线（浏览器 API）不进单测。组件/hook 不测（无 jsdom 依赖，不为此引入）。

### 10.10 裁切层与几何踩坑速查（按主题分组）

> v0.5 自 §10.6 尾部踩坑块独立成节；条目只写现行口径与判别法，发现过程/纠偏轮次见 [决策日志.md](决策日志.md)。

**PatternPiece 重建与字段透传**

- `PatternPiece` 的 `apply_shrinkage`/`with_shrunk`/`with_gross` 均**按位置重建**——新增字段必须显式透传三者，否则被静默丢弃（marks 与 drills 均差点丢；drills 另须同步 `piece_svg._bounds`，画布范围不含内部点钻孔会被裁出画布）。
- 缝份 `cutter._sa_amount` 鸭子类型化（`getattr(name, 0.0)`，任意「字段名=边名」的 dataclass 或边名→量 dict 通用）；缝份记录串 `_sa_notes` 走 `vars(sa)` 列字段值（WSA 仍走专用分支列上/下口·左/右端），新增缝份 dataclass 无需再改。

**坐标变换与手性**

- **裁片坐标变换选错会镜像**：主版 → 裁片局部，机头/腰头用 **180° 旋转** `local=(origin.x−x, origin.y−y)`（det=+1 保向、绕向不变），前口袋若照搬则左右镜像——180° 把 X 也翻了。前口袋/袋布/门襟/小表袋/后贴袋/前后片用**关于过 origin 水平线的 Y 轴反射** `local=(x−origin.x, origin.y−y)`（det=−1，X 不翻保侧缝左/前浪右、Y 翻让腰头在上），反射反向由 `_finish_piece` 自定向补正（shoelace<0）。**新裁片选变换按「哪个轴该翻」决定**：翻 X=左右镜像、翻 Y=上下翻转、两轴都翻=180° 旋转（保向）；按 `piece_svg`「Y 向下不翻转」口径，通常只需翻 Y。

**缝边与角部构造**

- **镜像/对折拼合裁片的同语义边必须异名**：两层拼合轮廓（袋布底层+面层镜像）同语义边若同名，cutter 同名边跳过 miter 平滑相接，拼合点（折叠顶点）处缝份缺量；面层边加 `_m` 后缀异名即强制 miter。但**仅单层独有的边不能加后缀**——SA 按边名查量，`mouth_m` 查不到静默取 0 缝份（袋布 mouth 即此坑）。后缀边须在 SA 传入处显式给 `_m` 同值键。
- **精确 G1 连续链的分段边必须同名**（与上条相对）：一条轮廓边由多段几何拼成、接缝处切向严格共线时（如门襟外缘 = 直线→底角圆弧→底边）若异名，`_miter_point` 对平行切线（det≈0）回退阶梯角、接缝处缝份凸出 2·sa 尖刺；多段同名即按平滑相接处理。**该 miter 的真折角拼合点要异名、不该 miter 的 G1 光滑接缝要同名**，按接缝两侧是否真折角决定。
- **锐角 miter 尖刺与 miter_limit 双刃**：miter 交点距角点 = sa/sin(θ/2)，随内角变锐无界增长——`_miter_point` 默认 `miter_limit=1.5`（超 max(sa)×limit 回退阶梯角）是防尖刺兜底。但「尖角即目标形态」的角（前片裆尖 ≈75°、miter ≈1.64·sa）被限长**静默**回退成「竖一刀+斜一刀」台阶且无警告，金标用角度较缓的尺寸测不到。凡工艺要求尖角跟随净样：显式 `corner_treatments={(a,b): "miter"}` 或 `miter_limit=float("inf")`（袋布裁片即显式 inf，锐角取标准 miter 尖角）；判别法：角部放大目检台阶，或比对毛样顶点与 `_miter_point(..., float("inf"))` 复算点。
- **mirror 折角键序 = (折线边, 被镜像边)，选错折轴在直角处静默退化**：首元素是缝份翻折的折线边（折轴 = 该边缝线本身），物理上「谁的缝份被翻折、折轴就是谁的缝」。cutter 双向查键、链序任一顺序都命中，键序错不抛错；直角附近（裆尖 ≈87°）镜像退化 ≈miter、目检呈「向内平切」仅差 ~0.13cm。判别法：按翻折后边缘应与**相邻边缝份边**平齐独立推预影像线，与角点比对。
- **曲线过端点「自然延续」的选型**：①贝塞尔多项式外推（t∉[0,1]）越延越摆、遇拐点回摆成钩；②真密切弧在端部「减弯」曲线上朝远离角点侧卷曲、与对侧可能无交；③端切线直线延伸在近水平/垂直切线处拉出长直段。现行取值：`"miter_line"` 端切线直线求交（交点近而有界 = sa/sin(θ/2)）= 前片裆尖 False 态；`"miter"` 多项式自然外延求交（`_natural_join_sharp`，搜索窗 4·max(sa)+20 加大后首个交点落在钩回前的近角段）= 后片 False 态；无交均回退切线 miter→阶梯。
- **袋口折边 hem 的降级判据必须预扫描/主循环共用**：`add_seam_allowance(hem=...)` 在 `_hem_feasible`（判降级）与主循环（发折边顶点链）**两处调用同一函数**，各写一份即一处降级一处仍构造、毛样断链。降级条件：弧袋口（无直线镜像轴）/ 袋口零长 / 前后邻边同名 / sa_top=0 / 侧边与袋口近平行（|E·N|≤1e-6——造近平行测试用例需斜率 1e-7 级，1e-4 不触发、P_notch 会飞到 1e5 量级）。P_notch 勿另算交点：`_miter_point` 折边侧 sa 传 0 时自动 = 袋口净线延长线 ∩ 侧缝缝边线；hem 角 `miter_limit=inf`（规范指定构造非尖刺）、跳过 corner_treatments；撇势 taper 为绝对量不随缩水放大。流级金标勿硬编坐标——整版上贴袋带 rotate_deg 摆放角 + 约克底线倾斜，T/P_notch 须从 net_edges 公式级独立复算；`FlowRunner(M,o)` 自建 ctx，测试必须用 `run()` 的返回值（`DraftContext(M,o)` 是空版画不上元素）。
- **折边锚点必须取毛样上的 P_notch，勿自净角起算**：自净角起算折边翻盖比大货毛样窄 2×SA_side、翻折后盖不住侧缝折边区。正确：折边线自毛样外侧缝边线起翻，翻盖底宽 = 毛样在袋口层的全宽（金标 16 = 净口 14+2×sa_side）；毛样顶链 P_notch_a→T_a→T_b→P_notch_b 凸链无台阶——hem 边只发 `[T_a,T_b]`，两端 P_notch 由角点 miter（折边侧 sa=0）发射，`_hem_points` 内部复用 `_miter_point` 算锚点（近平行兜底回净角）。
- **袋口刀口 = 净口两角各两刀、打在缝边上（家族口径）**：内/外上角各顺着**侧缝边延长线**交缝边一刀 + 顺着**袋口顶部线延长线**交缝边一刀（后者落点即折边锚点 P_notch），共 4 刀全打在缝边上、**底部不打口**（后贴袋/小表袋/前口袋 PATCH 同族）。实现归 **flow 层**（如 `back_patch_flow._top_hem_notches` + `_ray_hit_poly`）而非 cutter——cutter 只产折边几何，刀口与方向由调用方生成并**整体替换 gross_notches**（缝合线位仍在 shrunk_notches）。方向 = 交点处**缝边内法向**而非全局竖直（袋口随约克底线倾斜 ≈2.9°，顶边刀口内法向即偏离经向该倾角）；`_ray_hit_poly` 取最近正距命中（s≤1e-6 弃——side=0 时顶线延长交点退回净角即弃刀）；角点延长方向取**链向越角切向**（到达切向直行 / 出发切向取反），勿用净角自身法向。

**几何与浮点**

- **直线升阶贝塞尔禁用端点重合控制点**：`CubicBezier(a,a,b,b)` 端点切线为零向量，`_offset_edge_points` 端点 `tangent_at(0).perpendicular().normalized()` 直接抛错（绘制层不崩、纯裁切层坑）。升阶取均匀控制点 `CubicBezier(a, a.lerp(b,1/3), a.lerp(b,2/3), b)`：路径仍为原直线段、切线处处非零。
- **弧长反推 t 的量化误差**：`t_at_length`/`bezier_subrange` 按 64 折线采样，提取子段实测长与公式精确值差 ~4e-5——金标断言「公式推导长 vs 提取子段实测长」容差放 1e-3；复算与实现同式同源（如同一 `t_at_length` 取段）则可 1e-6。
- **围度辅助线 ∩ 外轮廓交点勿预设载体边**：横裆线高度常高于臀围外缝点（后片立裆 73 > 臀 72），侧缝交点落在髋腰弧（非大腿弧）、内侧交点落在后浪弧（非内缝弧）——对预设曲线 `point_at_y(y)` 越界直接抛 ValueError。凡「水平线与轮廓交点」类定位（刀口/marks 截断）一律按净边链折线采样整链求交取 min/max x（`back_piece_flow._clip_h_line` 口径），不指定载体边。
- **两线段求交的 Cramer 参数 s/u 极易写反**：解 `seg.a + f·s = p + e·u` 时 `s = (e×r)/det、u = (f×r)/det`（r = p − seg.a、det = e×f），把 s 写成 `(r×f)/det` 实为 −u——不抛错、返回看似合理的错误交点（口袋对位刀口曾飞到轮廓外 140cm，靠逐点距离检查才暴露）。新写线段/折线求交先过单测（水平线 × 竖直线交点 (0.5,0) 手算例）。
- **斜量测量线勿按水平线截断复制**：毗围线是外缝点->裆端的**斜量线**（d=0 直量也斜），端点本就落在净边上——按水平截断在 d=0 时与横裆线同高完全叠影、且丢斜量方向。凡端点本就在净边上的参考线（毗围线、贴袋顶线）一律 1:1 拷贝原线段。连带测试教训：按「marks 是否水平」识别某类线的判据会被斜量线打破（省腿残段识别改按与源线段共线近距判）。

**几何 API 速查（补充 §10.2）**

- `DraftSheet` 无 `len()`：计数用 `sum(1 for _ in sheet)` 或 `sheet.points/lines/curves/of_type(...)`；判存在 `"name" in sheet`。
- `Vector` 无 `__add__`、`Point` 只支持 `+ Vector`（不支持 `− Vector`）：向量累加（如角点法向均值）按 dx/dy 分量累加后 `Vector(nx, ny).normalized()`；点减向量改写 `p + v.scale(-k)`（`p - v.scale(k)` 抛 AttributeError）；`perpendicular()` 返回已归一化的逆时针 90°。

### 10.11 3D 人台试穿（fitting 出口 + 前端 PBD，2026-09 一期）

**定位**：整版 2D 太抽象、看不到穿着效果——3D tab 把前后片当布料缝到参数化人台上，调参数看悬垂/松紧，满意后走既有导出链（导出本身不经 3D，stale 门控照旧）。引擎只多一个 JSON 出口，全部仿真在前端。

**引擎侧（exporters/fitting.py，纯 stdlib）**：`build_fitting_payload(ctx, m)` 自调 `build_front_piece`/`build_back_piece`/`build_waistband`，输出 schema v1：`body{stations, points, crotch_drop, waistband_width, waistband_type, outseam}` + `pieces[front_piece, back_piece, waistband]`（固定序）。要点：
- **坐标系**：前后片净边链/marks 反变换到**整版全局系**（cm、Y 向上）——`_to_global(p, origin) = (p.x+ox, oy−p.y)`；全局 Y 直接当身体高度用，站点高度取 `front.*_line.a.y`（前后片水平线显式等高，仅 crotch_drop 下落）。折线密度 `flatten_geom` 0.01cm 弦高，全 payload <40KB。
- **origin/frame 随 `PatternPiece` 携带**：`origin`（局部系原点的全局位置）+ `frame`（`"reflect_y"` = 上下翻转局部系，前后片；`"local"` = 旋转局部系，腰头——origin=None 只随标量导出 `scalars{top_length, bottom_length, width}`，3D 只作环带）。三处重建点透传：`pieces.py with_shrunk/with_gross`、`cutter.apply_shrinkage`（金标 `test_fitting_payload.py::test_origin_survives_cutter_chain` 钉死）。
- **边角色表**（缝合配对键）：`_EDGE_ROLES`——front `waist:top_chain, hem:hem, mouth/fly_*:free, rise/inseam/side:seam`；back `waist:top_chain, hem:hem, cb/inseam/side:seam`。`girth_finished` 均为成衣量（waist/hip 整圈、thigh/knee/hem 单腿），供前端松量读数；**人台围度不来自 payload**。
- **双通道**：`POST /api/draft/fitting`（app.py）与 `engine_glue._fitting`/`_COMMANDS["fitting"]` 逐字段复刻，`test_engine_glue.py` 钉全等；前端 `postFitting` 走 `route()` 引擎优先。改引擎后照常 `npm run build:engine`。

**前端（webapp/frontend/src/fitting3d/，新增依赖仅 three + delaunator）**：
- **体型与成衣分离（用户口径 2026-09-09）**：尺寸单围度是成衣量（含松量/调节量）不能当人体量。`BodyProfile`（腰/臀/大腿/膝围）是**纯前端态**（localStorage `ylpattern.body.v1`），不进引擎 Measurements/DraftPayload、不 bump 参数版本号、不影响打版；默认 `estimateBody = 成衣 − 先验松量`（clamp ≥0.85×成衣）标注「估计值」。体型管理三件套：内置预设 5 个 + 自定义保存管理 + JSON 导入导出（bodyProfileStore.ts）。
- **模块图**：`priors.ts`（唯一先验收敛点：松量/体型比例/截面形状/PBD/网格/蒙皮，全为非引擎数据）→ `bodyProfile(t)` → `mannequin.ts`（超椭圆截面放样：骨盆管（躯干延伸→腰→臀→裆分叉→裆下楔）+ 双腿管（外缘连续 emergence 头带→裆→大腿→膝→小腿肚→脚口→踝）；围度按站点 Catmull-Rom 采样、48 边折线周长标定 ±1.5%，腿环 cx 不进 CR——按外缘/内缘梯子逐环派生，见下文「人台人体化」节）→ `mesh.ts`（净边链弧长重采样成边界环 + 内部错排栅格 + delaunator 三角化，距离/弯曲约束与边名聚合段 runs）→ `seams.ts`（包裹摆位 + 缝合配对 + 腰口 pin + 环带）→ `pbd/{collide,constraints,solver}.ts` → `structureLines.ts`（marks 重心绑定随布料变形）/`heatmap.ts`（约束应变→红绿蓝）→ `useFittingSolver.ts`（生命周期：rAF 步进、settled 停、tab 隐藏暂停、热启动）→ `Fitting3DView.tsx`/`BodyProfileDrawer.tsx`（挂 PreviewPane「3D 试穿」tab，antd Tabs 惰性挂载；人台形体验收期 2026-09-10 曾以 Fitting3DView 顶部 `RENDER_GARMENT` 单开关临时屏蔽布料渲染（布料四半片/腰头环带/结构线与热力图/透明度/重新试穿等布料相关渲染和控件全部跳过、solver 照常解算，man/buildVersion 仍驱动人台随体型重建），人台视觉验收通过当日已改回 true 恢复全量渲染；开关保留备用）。渲染分支：`skin.ts`（mannequin 环参数 → SDF smin 场 + 自写 marching cubes 单张水密蒙皮，仅 Fitting3DView 消费，见下文 SDF 蒙皮节）。
- **3D 约定**：`position=(r·sinθ, y, r·cosθ)`，θ=0 前中(+Z)、90°=wearer 右(+X)；as-drafted 片=左半，右半镜像 θ→−θ。前左片 侧缝(t=0)θ=−90°→前浪(t=1)θ=0°；后左片 后中 θ=180°→侧缝 θ=270°。摆位半径 = 各覆盖管支撑半径最大值 + garmentGap（凸上界，初态不穿体）。
- **缝合配对**：`(f|b, L/R).side ↔ (b|f, 同侧).side`（脚口端起，长度差余量上移）、`inseam ↔ inseam`（脚口端起）、`(f,L).rise ↔ (f,R).rise`、`(b,L).cb ↔ (b,R).cb`（裆尖端起）；`free/hem` 不配对。缝合 = 零静止长度距离约束。**腰口不仿真腰头布片**：top_chain 粒子 pin 到自身 drafted 高度体表环（yoke 开启时 back 顶链天然 pin 在机头缝高度，与环带间缺口为一期已知简化），环带 = 静态深色圆筒（`buildWaistBand`）。
- **PBD**：verlet（dt=1/60、g=−980cm/s²、阻尼 0.985）+ Gauss-Seidel，3 substeps × 6 iterations；约束 = 三角形全边（结构+剪切 1.0）+ 相邻三角形对点（弯曲 0.3）+ 缝合（1.0）+ pin（w=0.9）；碰撞 = 解析投影（y 夹取→插值环→超椭圆半径→推到 R+skin 0.3 + 切向摩擦 0.5），骨盆/两腿取最深。热启动：新网格顶点在旧网格重心插值继承位置与 0.5×速度（边名签名变化才冷启动预松弛 200 迭代）。发散兜底：NaN/飞点 → 恢复上一好帧（阻尼×0.9、迭代×2）→ 连败 3 次冻结 + 「仿真已暂停」角标。settled（均速<0.8cm/s×30 帧）停解算只渲染。
- **辅助**：应变热力图（红紧/绿贴/蓝松，约束数据顺手算零成本）、视角快捷（正/侧/背/斜 45°，OrbitControls 自由拖不锁）、透明度滑杆（0~1 统一驱动布料四半片/结构线/腰头环带三材质，0=完全隐藏只看人台）+ 隐藏人台、截图 PNG（同步 render 后 toDataURL）、3D 内快捷参数滑杆（腰/臀/腿/膝/脚口/裤长，写回同一参数 state 照常 bump 版本 → debounce 800ms 自动重试穿；fitting 快照独立、不走「先画后裁」门控——试穿是探索视图，DXF 门控仍由整版把守）。three/OrbitControls 动态 import 独立 chunk，首屏主包零影响。
- **测试**：`fitting3d.test.ts`（环周长标定/estimateBody 金标/欧拉公式 V−E+F=1/摆位约定/碰撞投影/全 pin settled/应变单调/人体形状不变量/矢状 S·腰最窄·脚·脐金标）+ `skin.test.ts`（蒙皮金标 16 例：单原语站精确支配/围度容差/水密外向/解耦双测度/病理降级，见下文 SDF 蒙皮节）+ `fitting3d.integration.test.ts`（真实引擎 fixture `_fixture_fitting.json` 端到端：网格拓扑→缝合配对→150 帧 PBD 有限/缝合闭合<1cm/不穿透）。fixture 重生成命令见该测试文件头；fixture 用静态 `import fx from './_fixture_fitting.json'`（tsconfig 开 `resolveJsonModule`）——**勿用 `node:fs` 读**：tsc -b 浏览器 lib 无其类型，`npm run build` 的 tsc 阶段报 TS2307（2026-09-09 实测）。

**人台人体化（腿管外缘连续 emergence）**：三管互相嵌入消除骨盆/大腿分体感，腿管按人体剪影构造（**最宽点在臀带、大腿外缘与臀线连续、膝/踝按人体比例收窄、裆下 ~5cm 过零分离成明显缝隙、小腿肚微凸**），全部先验收敛在 `priors.ts BODY_RATIO/SECTION_PRIOR`（改先验不重打引擎 zip）：
- **骨盆管**：三段独立 sampleStations 拼接（前瞻锚手法，杜绝单表追加的 CR 过冲）。上段（躯干顶(腰+18, 围 0.88×腰)→**肋(腰+9, 围 1.06×腰——躯干上段腰以上双向展开，腰成下躯干全局最窄)**→腰→臀站，**step 2 采样**——臀峰/腰椎谷特征宽 ~4-6cm，4cm 环画不出连续曲率，亦是环棱线观感来源之一）+ 臀下填充带 `[hip,hip围]→[hip−5, hip×0.995]→[crotch, hip×0.83]` 滤 y<hip（`fillBelowHip/fillGirthRatio` 锚抬 (crotch,hip) 开区间围度治腰髋沟；`[hip,hip围]` 前瞻锚压平 CR 切向，防臀上鼓包破「带内 a ≤ aHip」不变量）+ 裆下楔段 `[hip,hip围]→[crotch,hip×0.83]→[crotch−3, hip×0.30]` 滤 y<crotch（前瞻锚保 crotch 切向连续；楔底穹顶止于缝隙过零锚上方——可见分离保持在裆下 ~5cm，后浪支撑带 (crotch−2.5, crotch) 仍被楔环+腿 bB 覆盖）。分叉围 = hip×`crotchGirthRatio`=0.83——腿管外缘接管外侧剪影后骨盆在两腿间收细。骨盆 24 环（上段 17 止于臀站 + 填充带 5 + 楔 2），楔底 (75, a≈4.4)。
- **腿环统一构造式**（围度站点 CR 采样机制不变：crotch/thigh/分离点/中腿/knee/calf/峰下收拢/hem/ankle 九站 ~4cm 一环，165/66A 下段 25 环 + 头带 5 环；**cx 不进样条**——gap 线性梯子逐环派生 + sectionAt 线性插值，剪影 Lipschitz 界由构造可证；外缘目标本身经 monoSplineAt 单调样条，见下文「形体塑形」节）：`cx = max(a+gap(y), min(outer(y)−a, 0.55×W_h))`，W_h=臀站半宽。**outerLadder**（外缘目标 ×W_h，单调样条插值 + calf 显式锚）：thigh 0.955 / knee 0.78 / calf 0.80（膝局部最窄 + 小腿肚局部最凸，峰谷锚平导数）/ hem 0.70 / ankle 0.62——「两根等粗柱子」+「直线锥腿」的对症药；**gapLadder**（内缘下限 cm，cx−a ≥ gap；负=允许越过中线贴腿；**维持线性**）：crotch −2.5 / 过零锚(crotch−5) 0 / 大腿中(crotch−12) 1.4 / knee 1.2 / calf 1.6 / hem 1.8 / ankle 2.4（X 站姿梯度）——可见缝从裆下 ~5cm 起、大腿中段缝宽 2×1.4 稳可辨（MC spacing 1.0 下缝 ≥2cm 才可辨），治「内缘跨中线大半段融合腿」。配套**围度联动锚**（站间围度自由、thigh 站点环 ±2% 金标不碰）：分离点围度 thigh×`gapOpenGirthRatio`=0.89 @crotch−5 钳位（[crotch,thigh] 平顶切向会使 CR 中段鼓出、outer 反超臀带成次峰，收口防之）+ 中腿围度 thigh×`midThighGirthRatio`=0.85 @crotch−12（开缝联动收腿管防 outer 超预算；真人大腿带 9cm 下收亦是解剖事实）。**下限优先于上限**：粗腿体型外缘超标 = 「腿确实比盆宽」的诚实降级（cx ≥ a−2.5 恒正，实测逐环 |cx| ≥5，双腿永不跨中线融合/翻转），无容纳预检降级路径。**calf 站**：膝下 5cm（解剖位）、围 knee×1.08（钳 ≤thigh×0.97 防短腿倒挂）+ **峰下收拢站**（calf 下 12cm、围 knee×0.93，短腿钳位防乱序；真小腿峰下快-慢凹降非近线性）——膝局部窄点 + 小腿肌腹纺锤微凸 + 峰下收拢均为解剖真实形态。
- **头带（外缘连续 emergence，y∈(crotch, yTop] 直接构造）**：yTop = min(crotch+7, hip−2)（165/66A→84），cx 恒取裆环值、半轴 a = outerHead(y)−cx；outerHead 三锚**凸坡**：yTop 处贴盆内壁（min(P.a, W_h)−0.3）→ 头 2cm 内陡降入盆 headSteepDepth=0.8（下限 ~0.5——再浅则头带外缘超盆 a 破「头带贴盆」金标）→ 放量至 outer(crotch)=cx(crotch)+a_thigh。凸坡保证与盆壁穿越角 ≥~40°（smin 融合外凸估 ~0.5 < garmentGap=1.2 预算；线性坡 23° 估 0.92 压线）。浅裆退化（yTop≤crotch+0.5）无头带，腿自 crotch 穹顶起、smin 融成分叉。
- **截面形状（`SECTION_PRIOR` 站点锚 + 形状参数 y 向连续梯子）**：腰/臀 e 2.3/2.15（>2.4 的方截面是「方盒子」观感来源）、腿 default e 2.2 depth 1.0 / knee e 2.3 depth 1.05 / calf e 2.3 depth 1.03（真大腿/小腿截面近圆形，深宽比 <1 会把同围度截面压宽、腿显柱状）；臀 backBias 1.12 表臀凸保留。环间 e/depth/backBias/frontBias 由 monoSplineAt 连续插值（kind 档位跳变整类删除，见「形体塑形」节）。
- **（史实存档）tubeMesh 绕向金标（对抗审查揪出的存量缺陷，一期分体感的渲染根源；tubeMesh 已于 2026-09-09 三轮被 SDF 蒙皮取代删除，金标整体迁移 skin.test.ts）**：原墙面/盖扇三角全管内翻——computeVertexNormals 得内向法线（明暗按内表面算），FrontSide 剔除近壁后任何机位看到的都是管内壁/远壁（一期「共面盖可见 z-fighting」即其症状）。**遮挡发生在三角绕向层，环参数层测试全绿不代表渲染正确**（内翻曾带 27/27 全绿溜过）——该教训由蒙皮「三角几何法线·∇F>0」金标继承。
- **入口守卫**：`yCrotch=min(payload, hip−2)`、`yThigh` clamp 进 [knee+2, crotch−0.5]（集成夹具 thigh@y==crotch 重复站即命中）、`yCalf` clamp 进 [hem+2, knee−1]（防短腿站点乱序触发降序断言 → 3D tab 静默空白）；浅裆退化 yTop≤crotch+0.5 时无头带（入口 clamp 后为防御分支）；两管拼接后逐环断言 y 严格降序（杜绝零面积面/NaN 法线）。
- **支撑口径（surfaceRadius 接合金标现行锚，165/66A）**：侧向 emergence 带 (crotch, yTop)：79 仍盆壁主导（SR(79)=P.a(79)=14.902 > 腿 |cx|+a 14.86）；82 头带贴盆内壁零漂移（SR(82)=P.a(82)=15.36——语义=腿从骨盆里「长出来」而非贴上去）；会阴被填带 (crotch−2.5, crotch)：后中支撑由腿 bB 决定（SR(76)=9.627，恰覆盖前后浪落脚/裆下布料塌陷区）；楔底以下 74 处支撑仍由腿管决定（bB(74)=9.07）；两带之外逐位 Δ=0（锚值为矢状塑形 fb/bb 偏置收窄骨盆壁后的现行值）。
- **collide 存量缺陷修复（随行）**：`radiusAt(s,dx,dz)` 只接受**单位方向向量**（docstring 改口），旧 collideOne 直灌未归一化 (dx,dz) 使其返回向量倍数语义、穿透判据退化为 dist≥R/dist+skin、均衡点 ≈√R≈3.8cm（布料可沉入体表 ~10cm，修复前单测/集成断言因同弱度量空转）；全仓唯一误用点即 collide.ts。三管共覆盖 y 段扩为两条（腿头带×骨盆 (crotch, yTop) + 裆下两腿互叠带 (crotch−5, crotch)——互叠止于缝隙过零锚 crotch−5，其下两腿壁分开成缝），collideOne 顺序投影非幂等，`SOLVER_PRIOR.collideSweeps=3` 多遍扫描为结构性守卫（2 遍最坏残差 0.13、3 遍 0.09）；接触带内缝焊合约束与碰撞推出互抗的力平衡残差由集成测试 −0.15 容差收纳（矢状塑形 ham/腘窝上沿锚使大腿接触带 bB 增 → a 重标定收细、两腿壁分开，实测最坏侵入 skin 余量带 0.283→0.082 @y66.0，粒子仍在真实表面外 ≥0.218cm，零可见穿模）——重构碰撞（并行化/单管早退）不得丢 sweep 循环。

**形体塑形（2026-09-10 第四轮人体化：矢状 S 曲线 + 单调样条梯子 + 脚盒/肚脐；先验收敛 `priors.ts SAGITTAL/SECTION_PRIOR/FOOT_PRIOR/NAVEL_PRIOR`，改先验不重打引擎 zip）**：emergence 后人台仍是「直筒背/等粗腿/无脚无脐」——环模型按围度站点放样只约束周长，矢状剖面形状（前后半深比）与环间过渡形状无控制。红线：seams/pbd/collide 零改动；cx 不进样条；解耦超预算只降 kPL/kLF 不抬 garmentGap（本轮 kPL/kLL/kLF 全程未调）：
- **单调样条原语 `monoSplineAt`（Fritsch–Carlson 型）**：结点导数 `monoSlope` 在局部极值锚（相邻割线变号）取 0——平滑峰/谷无过冲；否则钳 |m|≤3×min(相邻割线) 且 ≤均值——区间内无过冲、|v'|≤3×局部割线，外缘 Lipschitz 界仍由构造可证。消费方三处：outerLadder 外缘目标、形状参数梯子（e/depth/bias）、**sectionAt 环间插值（a/bF/bB/e 单调样条、cx 保持线性）**——Hermite 在站点环精确过点（±1e-6 单原语站金标不破）；环间线性插值的 ~2-4cm 折点被 MC spacing 1.0 如实画出成「水平环棱线」，样条化后整类消失（kind 档位跳变 ring map 二值切换同批删除）。**gapLadder/headLadder 维持线性**（cx 路径 Lipschitz 论证前提，勿顺手样条化）。
- **sectionShape bias 形参（周长自标定）**：周长标定用实际前后半深 (depth×frontBias, depth×backBias) → a 同步重算，**每环围度精确不变**（bias 只改形不改围）——改 SAGITTAL 锚不破围度金标；代价是改任一 bias 使 a 漂移、下游接合锚（SR(79)/SR(76)/lb74 等）需随校。
- **矢状 S 曲线（SAGITTAL 锚比率，bB 或 bF 对 a·depth 归一；「自然圆润」口径——浅腰谷/圆润臀峰/宽缓微凸小腹）**：骨盆后壁 腰 1.0 → 腰椎谷 0.77 @腰臀中点（≈0.95×腰深浅谷）→ 臀站 1.12 → 臀峰 1.22 @臀线下 50%（≈1.04×臀站、臀线下 ~4cm 真人位）→ 裆 0.88（与腿首锚 thighTopBackBias 对值，盆-腿后壁交接差 ≤0.6）→ 楔底 0.85（臀底褶收）；前壁 腰 1.0 → **臀站锚 1.0**（无此锚小腹凸吃臀站宽 ~0.5cm、大腿带外缘反超臀线破「最宽点≈臀」）→ 上沿 1.06 @臀线下 15% → 小腹峰 1.10 @臀线下 35% → 下沿 0.97 @臀线下 65%（双侧沿锚摊开曲率成 ~3cm 圆穹顶，见下文 monoSlope 平顶带教训）→ 裆 0.80 → 楔底 0.80（小腹-裆前后壁交接差 ≤0.32）。腿后壁 裆 1.20 → ham 1.12 @裆膝中点 → 腘窝上沿 0.97 @膝上 4 → 腘窝 0.84 @膝 → 小腿肚 1.12 @calf → 峰下收拢 1.11 @calf−12 → 脚口 1.0 → 跟腱 0.95 @踝；frontBias 恒 1。演进史（VLM 逐轮调参）见决策日志 §十一。
- **Fritsch–Carlson 双端零斜率教训**：两端局部极值段（monoSlope 钳 0）是**最平的** Hermite 插值——crotch→knee 相距 36cm 的长直段把曲率摊薄，腘窝 dip@膝上 2 仅 0.07cm 任何渲染分辨率不可见；解法 = 中间锚保一端斜率非零（ham 锚 + 腘窝上沿 rim 锚把「ham 饱满→陡降入谷」集中到膝上 4cm，dip 0.07→0.28→0.47cm）。**monoSlope 平顶带机制（五轮补充）**：峰锚与端锚均被钳 0 导数时，两段 Hermite 双端零斜率拼成「平台-升-平台-落」的水平棱线（小腹屋檐根因）——解法 = 峰两侧插**非极值沿锚**（斜率非零）摊开曲率 + 压峰幅；CR 平顶切向鼓包同源（站点表平顶段使插值中段鼓出、gap 绑定下外缘反超臀带成次峰）——解法 = 收口锚（gapOpenGirthRatio）或前瞻锚压切向。**渲染分辨率天花板**：dip(cm)×~4px/cm = 可见像素——0.283cm≈1.2px VLM 三轮判不可辨，0.471cm≈2px 判「有内凹·可通过」；<~0.3cm 的几何凹陷当前分辨率画不出，推形状而非改渲染。回归守卫：`lb(44)−lb(42) ≥ 0.2`（删任一锚回落 ~0.1 即红）。
- **腰最窄**：肋锚（腰+9、围 1.06×腰）+ torsoTopRatio 0.88——躯干上段腰以上双向展开，腰成下躯干全局最窄（argmin ∈ (waist−2, waist+2) 金标 + 肋环 a > 腰环 a）；骨盆上段采样步 4→2（臀峰/腰椎谷特征宽 4-6cm，4cm 环画不出连续曲率）。
- **脚盒（FOOT_PRIOR，SDF 场加原语——环模型表达不了水平前伸的脚；蒙皮/解耦参照专用不进碰撞：脚顶 y≈−8.6 < 裤口 y=0，布料永不可达）**：两段圆角盒（后段足跟/足弓 14×7.6×6.4 + 前段脚掌/脚趾 8.5×8.6×4.6，smin k=`blendKFoot`=1.2 融合；总长 22.5、跟后伸 5.5、圆角 1.2），**绝对 cm 标准脚不随围度缩放**（病理体型共用）；局部系原点=踝、+Z=脚尖、微外八 toeOut 7°/脚（右 + 左 −）；盒心 y 必须**局部系**（=地面+半高−踝高；skin.footField 以 origin 平移后求值，直接存世界 y 会把脚沉到地面下 |yAnkle|）；地面 groundY=−15 = bottomY。
- **肚脐（NAVEL_PRIOR，smax 紧支凹刻椭球挂前腹表面 x=0）**：y=腰−4.5、z=当环 bF 极值内移 0.2、半轴 (1.2, 1.4, 0.9) 凹深 ~0.45、blend 0.8 控唇缘；距站点环 >2cm 不碰单原语站金标。
- **金标与阈值**：fitting3d.test「第四轮人体化金标」（矢状 S：腰椎谷 ≤0.98×腰深且带内 / 臀峰 >1.01×臀站且带内偏下 / 臀底褶 ≤0.72×峰 / 小腹峰 > bF@86+0.3；腿节奏：腘窝局部极小 + dip 守卫 ≥0.2 / 小腿肚局部极大 + 峰下收拢单调 / 跟腱收 ≤0.65；腰最窄 argmin 带；脚盒局部系/落地/外八；脐挂面）+ worstLip 阈值 1.05（语义=台阶检测非斜率美学：实测最坏 1.016 @78.5 = 头带凸坡陡段+裆环 girth 增长的真实斜率，软化坡会压低骨盆×腿穿越角、威胁 kPL 外凸预算）+ 站点剪影锚现行值（腰 11.652 / 臀 15.703 / 裆腿外缘 14.996 / 膝 12.25 / 脚口 11.29 / 踝 10.685）+ **缝隙不变量**（裆下互叠带 ≤6cm 且止于过零锚：inner@crotch <0、@crotch−6 ≥0、@中腿 ≥1.3、@膝 ≥1.1、@脚口 ≥1.0；|cx| 逐环 ≥5）+ **盆-腿壁交接不变量**（@crotch 前后壁差 ≤0.6）+ **腰髋沟上限**（outer@crotch+4 ≥ W_h−2.2）+ **接合支撑金标**（SR(79)=14.902 / SR(82)=15.36 / SR(86)=15.703 / SR(76)=9.627 / bB(74)=9.07，附支撑===管半轴的 9 位恒等式）。

**SDF 蒙皮（2026-09-09 三轮：tubeMesh 三管装配体 -> 单张水密隐式蒙皮，`fitting3d/skin.ts`，先验收敛 `priors.ts SKIN_PRIOR`）**：用户反馈三管装配只做到几何连通——交线 C0 硬折痕、剪影髋-腿过渡凹角、明暗交线两侧突变，视觉仍是搭积木。渲染层换 SDF 隐式曲面，`tubeMesh` 删除（唯一消费者 Fitting3DView 与 1c 金标，绕向/水密金标迁移 `skin.test.ts`；`sectionAt/radiusAt/ringPoint/superellipsePerimeter/buildMannequin` 原样保留，seams/collide 仍消费）：
- **场构造（闭式，环参数单一事实源）**：单管伪距离 `d₂ = ρ − ρ·q^(−1/e)`（q 按未归一化 (x−cx,z) 计算，超椭圆齐次性 q(t·û)=t^e·q(û)——零点集精确落环轮廓、径向斜率 1、与 radiusAt 同不动点零迭代）；端部椭球穹顶：y 超出管范围 dy 时端环半轴乘 sD=√(1−(dy/L)²)、场取 **max(d₂, dy−L)**（两支都是真距离下界、各自 1-Lipschitz；dy=0 处 dsD/dy=0 与柱面 C1）。**规格原文「dy≥L 返回 dy−L」实现时证伪**：远侧向点会从 ρ 跳到 dy−L 产生断崖，且两踝下方两管各返 dy−L 相等、smin 再压 k/4 会凭空桥出「脚底幻影膜」——max 修正后连续且无幻影。穹顶长：躯干顶 5（116 平盘斜机位突兀）/楔底与双腿两端 2.5（**平端盖彻底消失**；腿顶头带环贴盆内壁深藏（outerHead 凸坡），165/66A 臀站 86 处腿穹顶场 ≈+0.5、两腿 smin ≈0.35，与骨盆壁场之差 ≥kPL 为精确 min——支配余量由臀站逐射线金标守卫）。远场短路：ρ−max(半轴) 或 cap >k 时直接返回下界跳过 pow（仅影响恒正远区；k 取 max(kPL,kLL)——恒 ≥ 各对窗口半宽，短路只作用于精确 min 区）。
- **smin 软并集（族锁死、融合半径分对）**：`F = smax(smin(F_骨盆, smin(smin(F_左腿, F_左脚, kLF), smin(F_右腿, F_右脚, kLF), kLL), kPL), −F_脐, k脐)`（脚先融进同侧踝穹顶、两脚相距≫kLL+kLF 窗口互不串扰；腿对先融、骨盆再加入腿群；脐 smax 紧支凹刻收尾——恒等式 smax(a,b,k)=−smin(−a,−b,k)，b>0 一侧挖除，脐带外零点集/围度零影响），**二次多项式紧支**（|a−b|≥k 严格 =min）：换指数式（全域支撑）则所有站点围度漂移不可证——单原语站「逐射线 R_skin==radiusAt ±1e-6」精确支配金标（skin.test.ts）兼作防回退守卫。smin 的带外原语跳过用 +Inf 哨兵——数学极限 smin(x,+Inf)=x 虽成立，多项式代数式在 h=1 处 = Inf−Inf = NaN，必须显式短路（未短路时带外层全 NaN、MC 出空网格，2026-09-10 脚原语引入后实测）；脐场对称地以 k0>3 早退（真距 ≥2×最小半轴 > 2·k脐，smax 恒等带外零影响——skinField(0,86,0) 逐位等于骨盆场，单侧性金标前提）。k 取值由解耦金标按解析并集双测度锁死（抬升即红）——**k/4 只是场值下压上界、不是表面位移上界**：近切向接触带（两壁梯度近对消，|∇F|≈0.3）凹陷被放大数倍成表面外凸，原单 k=2 实测 165/66A 腿心 y=75 射线外凸 +1.66 超 garmentGap（「k/4<garmentGap 故布料不可见」论证由此证伪）。分对校准（2026-09-10 人台人体化后按解耦金标重校）：kPL=`blendKPelvisLeg`=0.75（骨盆↔腿群，emergence 头带/裆区切向放大带所在——凸坡头带交角 ≥40°，外凸实测 ≤1.07 预算内）；kLL=`blendKLegLeg`=0.6（腿↔腿——裆下互叠带 (crotch−5, crotch) 与分离带浅沟：两内侧壁切向擦碰时 |∇F|≈0.14 放大 k/4，kLL=1 时出口法向外凸 1.774 超 garmentGap，0.6 时 1.065 预算内）；互叠带内腿贴腿桥接场负属预期（≈真人腿根形态），过零锚 crotch−5 下 smin 谷转正成内腿缝浅沟（@crotch−6/@中腿场已正、缝 2×1.4 可辨），thigh 站实测 +1.82%（≤2%）；kLF=`blendKLegFoot`=0.75（腿↔同侧脚，2026-09-10 第四轮脚原语新增——踝穹顶与脚跟盒融合；超解耦双测度预算时与 kPL 同步下调，勿动 garmentGap 阈值）。分叉拓扑（裆/大转子凸）由 smin 自动处理，粗腿病理体型的外缘超标是「腿确实比盆宽」的诚实降级（smin 自动融合分叉）。
- **MC 选型与三角预算**：自写查表 marching cubes（Bourke 公有领域表，经 three addon 逐值转录——**其源码负数排版为「- 1」，提取须剥空白**）；否决 three addon（单位立方体网格对 40×130×35cm 细长 bbox 浪费 ~10 倍节点 + 直出三角汤无法共享顶点做水密金标/光滑法线）与 marching tetrahedra（三角 ×1.7 烧穿预算）。两遍：逐 y 层预计算三管切片 + Float64 采样；活跃胞查表三角化，顶点懒分配在共享栅格边（Int32 边索引 init −1）保证跨胞一致去重 -> 水密。spacing=1cm（~22 万格、165/66A 实测 26320 三角/~200ms）；超 `maxTriangles`=30000 则 spacing 逐档 ×1.15 **循环**整管线重跑至回预算内（至多 5 档；单次重跑不闭合——滑杆上限 120/130/80/60 单档后仍 32780。确定性守卫，否决计时降档）。bbox 脚盒界取绕 Y 旋转的轴对齐外接保守界（|cos|+|sin| 组合）且 X/Z 含盒心偏移 |c|（前盒 ≈12.75）——漏偏移把脚尖切出 bbox ~2cm、悬挂边破水密（病理夹具实测「边恰共享 1」46~54 条，标准夹具靠粗骨盆侥幸盖住）。法线 = 每唯一顶点 skinField 六点中心差分（δ=0.5）归一化（隐函数真法线、融合带 C1 连续——「明暗交线两侧突变」的对症药；否决 computeVertexNormals 的长条三角面片噪声）；绕向 FLIP_WINDING 锁外向（金标：三角几何法线·∇F>0 抽样 ≥100）。
- **站点围度口径**：场级切片周长 vs **同 N(360) 射线折线在标定环上的现场派生参考**（radiusAt 射线折线；勿硬编码围度数、勿用「平滑周长 vs 48 边形」口径——内接折线仅低估 ~0.1%）。单原语站（腰/臀/膝/脚口）±0.5%（理论 0）；thigh 站 ±2%，**裆侧回退尺则**：从腿中心射线，首穿 r_exit ≤ ring+0.5（融合带真实表面）取 r_exit，深融向（穿到对侧，如骨盆楔/对侧腿壁，或切向放大首穿）回退取 ring——会阴属骨盆不属于大腿轮廓；若按 min(r_exit, ring+0.5) 回退会注入固定 +2% 假漂移使容差空转（评审手算 +0.57% 只计 smin 鼓包、漏了深融向贡献）。实测 +1.82%、回退 87/360 方向（断言 ≤120 钉住楔接管带弧宽）；**深融向回退不计入，融合单向外凸上界由解耦双测度金标把守**（原「单方向最大外凸 0.475 ≤ k/4」系恒真构造断言，已删）。
- **蒙皮-碰撞解耦（碰撞/摆位零改动的论证）**：`skinField` 与 seams/pbd 的 surfaceRadius/collideOne 共用同一组环参数，差异仅在 smin 融合带。**参照=解析并集场**（`unionField`=三管单管场严格 min，即碰撞/摆位解析路径的几何本体）**双测度**（2026-09-09 四轮：原 surfaceRadius 参照逐管凸支撑取 max 恒 ≥ 并集轮廓、系统性低估外凸，且轴心原点稀疏方向永不命中腿心尖峰）：①并集表面点法向位移 −F_skin/|∇F_skin|、②轴心/双腿心射线首穿−并集末次出射，均断言 ≤ garmentGap=1.2（现行作用域：①三夹具最坏 1.065（kLL=1 时 1.774 超 garmentGap，kLL 降 0.6 的直接动因）；②腿心原点全域实测 0.000、轴心原点 y≥70（会阴楔区+缝隙过零锚附近 smin 谷桥场仍近 0）——y<70 轴心场已转正、smin=严格 min 自动安全；smin≤min 单侧性保证蒙皮永不陷入并集内部、融合只向外鼓——布料初始摆位在 surfaceRadius+gap ≥ 并集轮廓+gap 上，蒙皮越并集 ≤gap 才不吞布料）。渲染蒙皮仅体型/围度变化时重建（effect deps 已含 buildVersion，非每帧；围度喂入解算经 200ms trailing debounce——默认估计体型下快捷滑杆与围度直连，逐 0.5cm tick 重建蒙皮+PBD 是 ~230-500ms 同步重活会卡主线程）；bodyMat 不透明 FrontSide+深度写入前提由蒙皮继承（单张水密外法向闭合面，transparent 会透视体内布料与腰头环带）。
- **金标（`skin.test.ts` 16 例；tubeMesh 原 1c「绕向恒外向/水密 V−E+F=2」金标的迁移承接地）**：helper 自校（射线二分周长 helper 先对解析球场断言 2πr ±0.1% 再上蒙皮）；场符号 + **smin≤min 单侧性**（采样点 skinField ≤ unionField 恒成立、精确 min 区非空即紧支性在位）；**单原语站精确支配**（腰 98/臀 86/膝 42/脚口 0 各 36 向 R_skin==radiusAt ±1e-6——smin 族/融合半径选型回归守卫，换指数式或抬 k 即红）；站点场级围度（单原语 ±0.5%、thigh ±2% 裆侧环回退 + 回退方向数 ≤120）；融合带 y=79 侧向 [14.902, +0.2] + 腿缝符号三连（(0,75,0) 楔内负、(0,72,0)/(0,66,0) 过零锚下转正）；MC 质量（无向边恰共享 2 次、标准夹具 V−E+F==2、外向几何法线·∇F>0 抽样 ≥100、三角 ≤maxTriangles、栅点 ≤45 万）；穹顶符号（骨盆顶/楔底/踝端内负端外正 + 脚平底贴地）；解耦双测度 ≤garmentGap（标准/hip75×thigh80/滑杆极值 + 瘦小夹具）；边界格恒正（bbox 闭合前提）；病理 6 夹具（胖腰粗腿 130/70/90、hip75×thigh80、hip130 缺 thigh、crotch=88、thigh@crotch、滑杆上限）不抛、有限、水密 + 预算循环收敛（病理不钉 Euler——粗腿 smin 融合分叉拓扑可能非球）。

**一期显式非目标**：自碰撞、小裁片独立缝合（口袋/门襟/贴袋等只画结构线随布面变形）、腰头布片仿真（近无弹性、只引入高刚度小步长稳定性代价）。二期候选见决策日志。
