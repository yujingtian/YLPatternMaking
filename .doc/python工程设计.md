# 牛仔裤打版系统 —— Python 工程设计文档

> 版本：v0.3
> 日期：2026-07-31
> 关联文档：[打版流程.md](../打版流程.md)、[前后片臀围推导.md](前后片臀围推导.md)
>
> v0.2 修订：明确"**函数即绘制步骤 + 流程编排 + 先画后裁**"的核心架构。
> v0.3 修订：补充曲线绘制策略 —— 弧线由参数化公共函数生成，但共用不强制，裁片特有曲线允许步骤自行构造。

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

- 3D 试衣 / 面料物理仿真
- 自动放码推板（预留，二期）
- GUI 交互界面（一期为 CLI + 脚本 API）

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

目录结构以 `src/ylpattern/` 实际代码为准。步骤层按部件分文件：`front_steps` / `back_steps` / `front_pocket_steps` / `front_pouch_steps` / `front_fly_steps` / `back_yoke_steps` / `back_patch_steps`；`draft/curves.py` 为公共弧线库。未实现模块（cutter/pieces/validation/dxf）见 §10.6。

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

前后片绘制完成后，Cutter 按声明式裁片定义（元素名列表）从版上逐个圈取轮廓 → 闭合 Polygon（净样）→ 平移到局部坐标 → 偏移生成毛样 → 收集记号，产出独立 `PatternPiece`。弯腰头沿分割线裁成两片，直腰头绘制时已扣宽直接裁。**尚未实现**（见 §10.6），细节待实现时细化。

### 5.6 裁片 `pieces.py`

`PatternPiece`：净样轮廓 + 对位记号 + 丝缕线 + 标注，`with_seam_allowance(width)` 生成毛样。**尚未实现**。

### 5.7 输出层 `exporters/`

SVG（调版预览，分图层）+ DXF（生产，每裁片一个 BLOCK）+ 报表（中间尺寸 + trace 记录）。实际已实现的图层与 role 渲染见 §10.3；net/seam/annotation 等图层为设计期设想，尚未实现。

### 5.8 校验器 `validation.py`

裁片裁出后做结构校验：臀围闭合（2×(H前+H后) = H ± 0.05）、前后侧缝/内缝等长（差 ≤ 0.3 cm）、裆弯拼接顺滑（切线夹角 ≥ 170°）、轮廓闭合无自交。失败告警不中断，结果附报表。**尚未实现**，规则容差待实现时细化。

---

## 六、典型使用流程

命令行用法见 [CLAUDE.md](../CLAUDE.md)「常用命令」（`ylpattern draft --size ... --svg/--trace/--report`，支持 `--until` 中断调版；`ylpattern cut` 尚未实现）。尺寸单 `size.toml`（TOML，支持 `#` 注释）格式：

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

> v0.4 补充（2026-08-10）：本节由 [CLAUDE.md](../CLAUDE.md) 的"工程速查"迁入，记录已实现代码的实操约定。上文 §一~九为目标设计态，遇不一致以本节与实际代码为准。

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
- 独立裁片 SVG（`exporters/piece_svg.py`）：裁片局部坐标 **Y 向下**，渲染时**不翻转**（仅缩放平移），区别于整版 `svg.py`（版坐标 Y 向上、渲染翻转）。图层：gross 毛样（实线）/ shrunk_net 含缩水净样（虚线；缩水时唯一内轮廓基准）/ net 净样（淡虚线；**仅在未缩水时绘制**，已缩水省略——两条内轮廓虚线并存易误读，曾致用户把未缩水净样认成多余轮廓）/ notches（红）/ grain 丝缕线（蓝）/ marks 内部标记弧线（绿虚线 `.markline`，袋贴的袋口净线/吃省边、前片的臀/膝/毗围辅助线等，净样坐标、随缩水同比例变换）。

### 10.3.1 DXF 输出（exporters/_dxf_base.py + dxf.py + piece_dxf.py）

裁床切割/服装 CAD（富怡/ET/格柏）口径，CLI `--dxf`（整版一张）+ `--pieces-dxf`（全部裁片平铺合一张），api.run 同名参数。依赖 ezdxf（可选 extra `dxf`，exporters 内 lazy import，未装且传参时 RuntimeError 带安装指引；核心零依赖不变）。

- **版本 R12（AC1009）+ 折线**：实体白名单仅 LINE/CIRCLE/2D POLYLINE/TEXT（LWPOLYLINE/SPLINE/MTEXT 均 R13+，R12 下 ezdxf 抛错）；闭合用 `close=True` 不追加重复尾点；R12 无线宽/true color（CAD 端按颜色打印样式）。
- **单位 mm**：坐标 cm×10；R12 无 $INSUNITS（R2000+），以 TEXT "UNITS=MM (DXF R12)" 兜底声明。
- **曲线离散**：`_dxf_base.flatten_bezier` 弦高公差递归（判据=控制点到弦垂直距离上界，de Casteljau split 精确细分），默认公差 0.01cm=0.1mm（裁床典型精度），max_depth=12 防病态输入；共线控制点直接两端点。
- **全 ASCII**：层名与 TEXT 均 ASCII（R12 单行 TEXT + cp1252/SHX 跨软件易乱码），元素标注取 name、裁片标注取 piece.name + 净长宽数字，中文 label 只留在 SVG。 TEXT 字高 TEXT_HEIGHT_MM=10mm（2.5mm 在 ET 08 下几乎不可见）。
- **图层映射**：整版 REF(8,DASHED)/STRUCT(7)/CURVE(7)/POINT(1)/TEXT(7)，role->层与 SVG 同口径（ref 虚线入 REF）；**裁片合集用 AAMA 数字图层**（服装 CAD 不识别 CUT/NET 等自定义英文层名，是老软件解析失败黑屏的主因之一）：`piece_dxf._LAYER_MAP 语义->AAMA 法定数字层：1=裁切轮廓+片名文本 / 8=净样+缝合线（NET 与含缩水净样 SHRUNK 同落 8，AAMA 法定缝合线层）及内部画线（臀/膝/毗围围度辅助线、袋口净线、省弧--MARK 也落 8）/ 3=普通轮廓顶点/放码点（**非刀口层**，勿放刀口）/ 4=刀口专属层：POINT 必附组码 30（Z 深度，NOTCH_Z_MM=1.524）与组码 50（开口角度，取 `_notch_segment` 内法向在 mm 输出系方向 atan2(-dy,dx)，局部系 Y 向下、输出 Y 翻转；缺角度 CAD 不知开口朝向、不显示）/ 13=定位孔专属层：单纯 POINT（CAD 读 AAMA 见层 13 POINT 自动渲染标准、不受缩放影响的钻孔十字/圆圈符号）/ 7=纱向线。**坑**：刀口/定位孔的表示历经四轮实测修订，现行口径：刀口=层 4 POINT+组码 30/50、定位孔=层 13 单纯 POINT；历史方案均废弃--「POINT+TEXT 成对」会把定位孔误渲染成放码刀口（_add_mark_text 已删）、「层 3 纯 POINT」混淆了顶点层与刀口层、「层 8 真实 CIRCLE」r=0.5mm 过小完全不可见；ezdxf 对 height=0 有创建期钳制（回默认 2.5），若再需字高 0 只能文件级后处理，落错层（如辅助线落层 2）会被默认隐藏--围度辅助线曾因 MARK 落层 2 在 ET 里不可见；实测 ET 08 层 8 显示最稳，内部线归 8 恢复；层 "0" 为 DXF 保留层不可重建，文本并入层 1；三态/回退规则同 piece_svg。
- **AAMA 块结构（裁片合集）**：每片一个 BLOCK（块名=piece.name ASCII 大写化/去非法字符/截 31 字符/唯一化，块内为片局部 mm 坐标），Model Space 仅放 INSERT（插入点=平铺偏移）+ 全局声明 TEXT--服装 CAD 按块识别"一个裁片"，散线无法归组。块与块引用必须显式落层 1（block.block.dxf.layer 与 add_blockref(dxfattribs={"layer": ...})）：默认层 0 会被 ET 08 直接过滤丢弃（解析为空白）。`set_extents` 的 bbox 收集相应支持 INSERT 展开（`_collect_bbox`，块内容按块缓存、插入点+缩放+旋转变换；本工程恒等变换）。块中央另有 AAMA 信息三行 TEXT（PIECE/SIZE/QTY，`render_pieces_dxf(size=, qty=)` 由调用方传入，默认 "-" / 1，PatternPiece 不携带尺码数量）。
- **999 注释组**：`_dxf_base.save_doc(doc, path, comment=)` 写盘后在文件最前手动前置 999 标识（AAMA_NOTE = "ANSI/AAMA"，老版软件对长字符串强校验失败，必须短标识）--ezdxf 的 `Drawing.comments` 在 R12 导出时**不落盘**（实测无 999 组码），999 允许出现在任意记录间、解析器按注释跳过；换行风格跟随原文件。
- **裁片坐标**：局部系 Y 向下，块内变换 X=(x-x0)*10、Y=(y1-y)*10，平铺偏移全落在 INSERT 插入点上 -- 翻转后 DXF 显示与 SVG 屏幕视觉逐点重合、手性不变（不镜像）；shelf 行装箱平铺（行宽上限 200cm、片间距 3cm）。
- **刀口/定位孔画法**：刀口=毛样轮廓上该点垂直轮廓向内的 0.5cm LINE（POINT 实体裁床难识别）；drills=r0.5mm CIRCLE；丝缕线 LINE+TEXT "GRAIN"（省略箭头）。
- **范围变量（老 CAD 黑屏坑）**：`saveas -> update_all()` 会用 **modelspace 布局属性** `msp.dxf.extmin/extmax/limmin/limmax` 覆写同名 header 变量，布局属性默认是 (±1e20) 哨兵值/A3 图幅——只写 header 会在写盘时被冲掉。`_dxf_base.set_extents(doc)` 在渲染完成后按实体 bbox 把值设到 **msp.dxf 上**（header 同步直写供保存前内存读取）；老服装 CAD（ET 2008 等）直接拿 $EXTMIN/$EXTMAX 做初始视图/全图缩放，哨兵值导致打开黑屏，AutoCAD 自行重算无碍。回归断言在**回读文件**上（内存断言抓不住 save 时覆写）。
- **R12 兼容清洗（ET 08 打不开/解析空白）：**ezdxf 写出的 R12 带大量老服装CAD 兼容性差的可选特性。_dxf_base.save_doc 写盘后经 _strip_r12_compat 把文件裁成「最小 HEADER + BLOCKS + ENTITIES」AAMA 骨架（对照实测 ET 能直开的大货DXF：999 ANSI/AAMA + BLOCKS，无 TABLES、无一个 group 5）：① TABLES 等 BLOCKS/ENTITIES 以外的 section 整段剔除；② HEADER 只留白名单 $ACADVER/$DWGCODEPAGE/$EXTMIN/$EXTMAX（完全无 HEADER ezdxf 回读直接 IndexError，$EXTMIN/$EXTMAX 是 ET 初始视图依据不能丢）；③ 块名 $/_ 开头的 ezdxf 骨架块（$Model_Space/$Paper_Space/_ARCHTICK）连实体到 ENDBLK 整块剔除；④ 全部 handle 对（group 5）与 1001 XDATA 块剔除。按组码-值严格成对解析过滤，不碰坐标值。**坑**：组码右对齐带空格（'  0'），字符串比较前必须 strip；section 名在SECTION 对的**下一对**（2 码），别误取 "SECTION" 自身。另外 AAMA 块与块引用必须显式落层 1（默认层 0 被 ET 08 直接过滤丢弃、解析为空白），AAMA_NOTE 用短标识 "ANSI/AAMA"（长字符串老版强校验失败），TEXT_HEIGHT_MM=10mm（2.5mm 在 ET 08 下几乎不可见）。
### 10.4 架构约束细节

- 依赖链 `cli/api → exporters → flows → steps → draft → formulas → geometry → params`：**禁止反向**。尤其 `params/`（最底层）**不能 import `formulas/`**（formulas 在其上方）——需公式参与的跨字段校验放**步骤层**（步骤可调 formulas），`PatternOptions.__post_init__` 只做单字段范围校验。
- `formulas/` **只依赖标准库**（`math`），输入输出纯 float，不碰 geometry/params。
- `steps/` 只做定位与上版：数值调 `formulas/`，几何构造调 `geometry/` 与 `draft/curves.py`，经验常数读 `PatternOptions`。

### 10.5 排版与 Unicode 编码踩坑指南

代码与文档的中文标点是**全角 Unicode**，不是 ASCII。用 Edit 工具替换时 `old_string` 必须用对应字符，否则不匹配：
- 箭头 `→` = U+2192（注释"A → B"用它，**不是** ASCII `->`；只有类型注解 `-> float` 才是 ASCII）。
- 破折号 `—` = U+2014（不是 `--`）；减号 `−` = U+2212（不是 `-`）。
- `°`(度)、`×`(乘)、`§`(节)、`≈`(约) 均为 Unicode。
- 替换含这些字符的段落若不匹配，改用**按 ASCII 标记截取**（Python 脚本 `s[s.index(start):s.index(end)]`）或只替换纯 ASCII 子串；heredoc `python3 <<EOF` 在 Windows Git Bash 会挂起，写脚本文件再 `python` 运行。
- 纯中文注释行（如段头 `# -- 袋布（pouch）：…§一~§五）--`，无 ASCII 子串）连单行整配也失配时：改用 Python 脚本按附近 ASCII 行（如字段声明 `front_pouch: bool = False`）的 `line.startswith(...)` 定位行号、按行号 insert，彻底避开中文匹配。
- **Windows 环境两个反复出现的坑**：① `git stash pop` 会被已跟踪的 `__pycache__/*.pyc` 冲突卡住（error: would be overwritten by merge，stash 保留但工作树退回 HEAD）——先 `find src -name '__pycache__' -type d -exec rm -rf {} +` 再重新 pop（已连续两次踩中）；② Windows 控制台默认 GBK，CLI 不带 `--svg/--report` 直接打印全量报表时，报表文本含的全角减号 `−`(U+2212) 触发 `UnicodeEncodeError`——加 `PYTHONIOENCODING=utf-8` 环境变量或输出到 `--report` 文件即可，非代码缺陷。

### 10.6 当前实现状态（已程序化）

已实现：前片（`front_steps`）、后片（`back_steps`）、前口袋 + 袋贴（`front_pocket_steps`，含弯腰头+有省量时 P1/P1′ 延长至上腰头线；袋贴 `draw_front_pocket_facing` 详见下文）、袋布（`front_pouch_steps`）、前贴袋、小表袋、门襟（`front_fly_steps`，连裁/独立两形态）、后机头/育克（`back_yoke_steps`，弯/直腰头两端点弧长量取 + 下口线 N 点分段拓扑）、后贴袋（`back_patch_steps`，育克底线∩后浪线定位 + 局部 u-v 框四形态 + 仿射旋转）、毗围闭环（`flows/closure.py`）、腰头裁片（`steps/waistband_steps` + `flows/waistband_flow` + 裁切层 `pieces`/`cutter` + `exporters/piece_svg`，腰头裁片.md：直/弯腰头 × 有/无省，净样 -> 缩水 -> 缝边独立 SVG；`build_waistband(main_ctx)` 从整版提取前后腰弧净长代数求和）。裁切层（`pieces.PatternPiece` 三态净/缩水/毛 + 可选 `marks` 内部标记弧线〔净样坐标、随缩水同比例变换、不随缝边，前片裁片.md §3.3〕+ `cutter.apply_shrinkage`/`add_seam_allowance`〔含 `hem=` 袋口折边参数，`HemTreatment`〕）已为腰头、后机头、前口袋（袋贴/贴袋）、袋布（一片式对折）、门襟（单排/双排）、小表袋、后贴袋、前片大片落地（`add_seam_allowance` 的缝份参数鸭子类型化：任意字段名=边名的缝份 dataclass〔`WaistbandSeamAllowances`/`FrontFacingSeamAllowances`/`FrontPatchSeamAllowances`/`FlySeamAllowances`/`WatchPocketSeamAllowances`/`BackPatchSeamAllowances`/`FrontSeamAllowances`，cutter `_sa_amount` 走 `getattr`〕 或 边名→量 dict，机头用 `{top,bottom,cb,side}`），后片大片已随后片裁片落地（见下文）。尚未实现：结构校验器。

DXF 导出已程序化（`exporters/_dxf_base.py` + `dxf.py` + `piece_dxf.py`，图层/坐标/编码约定详见 §10.3.1；裁床/服装 CAD 口径 R12/mm）：整版 `--dxf`（DraftSheet → REF/STRUCT/CURVE/POINT/TEXT 五层，role 分层同 SVG 口径）与裁片合集 `--pieces-dxf`（全部开启开关的裁片 shelf 行装箱平铺合一张，AAMA 口径：数字图层 1/8/3/2/7（裁切/净样/缩水+刀口/标记+孔/纱向）+ 每片一个 BLOCK 经 INSERT 摆放 + 块中央 PIECE/SIZE/QTY 信息文本 + 文件头 999 AAMA 注释（详见 §10.3.1），刀口=毛样轮廓法向向内 0.5cm LINE、裁片局部 Y 翻转不镜像、多片共用功能层靠 TEXT 片名区分）。入口：api.run 同名参数 `dxf`/`pieces_dxf` 与 cli `--dxf`/`--pieces-dxf` 平行实现已同步——裁片分支由 (xxx_svg or pieces_dxf) 触发、build 一次按需写 SVG 并收进合集末尾一并出 DXF，未开开关时打印跳过提示。ezdxf 为可选 extra `dxf`（exporters 内 lazy import，缺依赖 RuntimeError 带安装指引；dev extra 已含 ezdxf 供 22 个 DXF 测试用例跑，含 $EXTMIN/$EXTMAX 回读文件级回归断言——防老 CAD（ET 08）黑屏的 set_extents 坑，详见 §10.3.1 范围变量条目）。

前浪裆弯弧度已可调：`PatternOptions.front_rise_handle_ratio`（默认 1/3，k1=k2=|BC|×本值，前浪绘制.md §4），由 `draw_front_rise` 传入 `curves.front_rise`；与后浪 `back_rise_alpha`/`back_rise_beta` 双参数不同--前浪按文档用单一对称比例，后浪因大裆弯更深需独立 α/β。

前口袋袋贴（facing）已程序化：`draw_front_pocket_facing`（`front_pocket_steps`，前口袋绘制.md §三.3.(1)）。
1. 定位两端点（支持非等距独立宽度）：腰头顶点 P_fw（有省自 P1′、无省自 P1 沿腰弧量取 w_waist=front_pocket_facing_width，默认 3.5）；侧缝顶点 P_fs（自 P2 沿外缝弧向下量取 w_side=front_pocket_facing_side_w or w_waist，推荐 6.0 防露白；但须满足 p2_drop + w_side < 外缝弧总长，否则步骤报"侧缝顶点越出外缝弧"——测试金标 M（H=96）外缝弧 ≈12.85、p2_drop 7.5，w_side 上限 <5.35，故测试夹具取 5.0）。
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
选项字段：watch_pocket / watch_pocket_mode / watch_pocket_width / watch_pocket_taper / watch_pocket_offset_from_top / watch_pocket_offset_from_side / watch_pocket_rotate_deg / watch_pocket_points / watch_pocket_edges。

腰头裁片已程序化：`build_waistband(main_ctx)`（`flows/waistband_flow`，腰头裁片.md §三~§五；自含裁片，非 FlowRunner 编排，同 closure.py 口径）。
1. 净长代数求和（§三）：`extract_waistband_spec` 读上腰弧 `front.waistline_arc`（t=0 侧缝->t=1 前中）/ `back.waistline_arc`（t=0 后中->t=1 侧缝），减省宽：后省 = `back.dart{i}_leg_inner` 端点 p_in 投影到后腰弧的弧长（`_arc_length_of_point` 采样最近 t + 三分搜索）；前省 = `front_pocket_p1_dist`。直/弯腰头统一读上腰弧（弯腰头下腰弧为贴身边，差 <0.5cm，代数求和容忍）。
2. 净样绘制（`steps/waistband_steps`，独立 DraftSheet 局部坐标 Y 向下）：直腰头 = 矩形 L_half×W；弯腰头下口线 = `curves.waistband_curve(L_half, spec.computed_drop)`（P1=(X/3,0) 后中水平利镜像/P2=(2X/3,−drop/3)、P3=(X,−drop) 前中自然斜出成**向下凹 ∪** 抛物线弧（整片沿后中镜像后后中下凹、贴臀侧外凸、贴腰侧内收；早期向上凸 ∩ 致下口内收不合体，故翻向），消除两端皆水平所致 S 型畸变；二分求 X 闭环 length 精确），上口线 = 下口沿**端点法向**偏移 W（`_top_geom`：P0/P1 按后中法向、P2/P3 按前中法向偏移，端点切线 (P1−P0)/(P3−P2) 逐点保留 → 上下口两端切线严格平行；中段为真法向 offset 的贝塞尔近似。直腰头两端法向皆 (0,−1) 退化为整体竖直平移 W=原行为）。full_piece 时后中 x=0 镜像 + 左端搭门：搭门 `_end_tangent` 取左前中处下口切线、沿切线外延 fly_extension（与下口顺势顺滑 C1 相接、弯腰头随弧端斜出）；两端封边向量 = 上下口同侧端点之差，因上口沿法向偏移故天然落端点法向 → 与上下口切线/搭门成直角（四处端点为直角）。drop 来源：用户 `waistband_front_drop` 手动覆盖；否则 `extract_waistband_spec` 调 `_auto_drop(front_arc, back_arc, hip_front, hip_back)` 按真实侧缝线夹角自动推算（§四.分支B；读 `front/back.hip_outseam_point` 取侧缝腰点 B 至臀点 H 的真实侧缝线倾角，以 B 为圆心旋转前片使前后侧缝线重合，旋转后前中 A_front 相对后中 A_back 的纵向高度差即 drop。主版坐标系 Y 向上，A_back.y 减 A_front_joined.y 为正即前中更低；该正 drop 喂入 waistband_curve 的 −drop 公式得向下凹 ∪，凸向与测量正负号解耦。旧法取腰弧端点切线对齐、强制切线连续会向上过旋抵消落差，side_rise 与 curve_sag 同存时坍塌为约 0；真实侧缝线为结构稳定特征，不受腰弧塑形影响，实测两开关增删变化在 0.1cm 内）；直腰头=0。
3. 裁切三段（`cutter`）：`apply_shrinkage`（按裁片局部 X/Y 轴缩水率仿射缩放，保持贝塞尔性；参数语义=沿轴率，**面料经/纬率映射到 X/Y 由 `waistband_grain` 决定**：LENGTH 长向(X)=经→x·(1+warp)/y·(1+weft)，WIDTH 宽向(Y)=经（默认）→x·(1+weft)/y·(1+warp)，映射在 `build_waistband` 调用处完成、cutter 本身按轴几何纯）-> `add_seam_allowance`（四边独立缝份沿**外法向**偏移：曲线逐点真法向 offset（`_offset_edge_points`，tangent.perpendicular·amt）、直线整体平移；相邻异名边角点取两偏移边切线延伸交点 miter 连接（`_miter_point`），切线平行回退阶梯角，普通 miter 角另有尖角限长 `miter_limit=1.5`（`add_seam_allowance` 形参可调：锐角交点距角点超 max(sa)×本值回退阶梯角，见文末踩坑），同名边平滑相接、后中折线不外扩；缝份不叠加缩水）。零长退化边（`fly_extension=0` 致 `wb.top_fly`/`wb.bottom_fly` 首尾重合、无切线）在 `build_waistband` 装配 net_edges 时即按 `cutter.edge_length`（`LineSegment.length` 属性 / `CubicBezier.length()` 方法，API 不一）滤除，cutter `_offset_edge_points` 另对零长直线防御性返回空，避免外法向归一化触发「零向量无法归一化」）。`PatternPiece` 三态：net_edges / shrunk_edges / gross_polygon。
4. 刀口（§三.2）：侧缝=L_back、后省/前省按弧长，full_piece 左右镜像各一；丝缕线方向随 `waistband_grain`（默认 WIDTH 宽向=经→竖向沿裤长；LENGTH 长向=经→水平）。
选项字段：waistband_front_drop（None=按真实侧缝线夹角自动推算 `computed_drop`、填值手动覆盖；正数 drop=下口线向下凹 ∪，负数被 options 层与 curves 层双重校验拒绝、若强放行因公式为 −drop 反得 ∩，**勿传负**。§四.分支B。**勿与 `fc_drop` 混淆**：`fc_drop` 是裤身前腰头绘制的前中下落量 d（`formulas.waist.waistline_horizontal_span`，前腰头绘制推导.md），塑造裤身腰围线；`waistband_front_drop` 是腰头裁片自身下口线的弯曲度，二者几何来源不同，曾因混淆导致 auto_drop 取错基准）/ waistband_fly_extension / waistband_full_piece / waistband_grain（WaistbandGrain：WIDTH 宽向=经〔默认，横裁，=裤长方向〕/ LENGTH 长向=经〔直裁〕；决定丝缕线方向与缩水经/纬率到局部 X/Y 轴的映射，§五.2。经向是面料属性、全局统一——前后片丝缕线=裤中线沿裤长，即经向=裤长，腰头横裁时宽向与之同向）/ shrinkage_warp / shrinkage_weft（面料经/纬向缩水率，到腰头 X/Y 轴的映射由 waistband_grain 决定）/ waistband_seam_allowances（WaistbandSeamAllowances：top/bottom/left_end/right_end，TOML `[options.waistband_seam_allowances]` 子表，须置 [options] 末尾避免吸收后续键）。输出：`--waistband-svg` 旗标 / `api.run(waistband_svg=...)`。

后机头/育克裁片已程序化：`build_yoke(main_ctx)`（`flows/yoke_flow`，机头裁片.md §2~§5；自含裁片，非 FlowRunner 编排，同 `build_waistband`/`closure.py` 口径）。
1. 四边界提取（主版坐标 Y 向上，均从已上版元素读，不重画）：上口 top=弯腰头 `back.lower_waistline_arc` / 直腰头 `back.waistline_arc`（t=0 后中 O→t=1 侧缝 X）；下口 bottom=`back.yoke_bottom_seg{i}` 链 P0→PN（line/arc/bezier；空 anchors+edges 时 `back_yoke_steps` 不存该段，回退直线 `LineSegment(P0,PN)`）；后中 cb=`LineSegment(origin,P0)`（P0 落后中斜线、直线精确）；侧缝 side=`back.outseam_hip_waist` 子弧 PN→X/X'（`t_pn=t_at_length(L−D_side_total)`，D_side_total=直 side_dist / 弯 W+side_dist；弯腰头侧上端到 X'=下腰头侧点 `t_at_length(L−W)`）。origin=弯 `back.lower_waist_center_point`(O') / 直 `back.rise_top_point`(O)。cutter 序 P0→PN→X→O（**负面积约定**，与腰头同向，外法向外扩正确）。
2. 有省（仅 1 省，§2.2）：`_detect_dart` 读 `back.dart{i}_apex`/`_leg_inner`/`_leg_outer`；省腿 ∩ 上下边界求交点（`_line_line_intersect` / `_line_bezier_intersect` 采样定位符号变号段+二分、校核落线段内）切开左右子轮廓 → 右片绕省尖 apex 旋转 θ=`degrees(atan2(叉,点))`（把 (p_out−apex) 转到 (p_in−apex) 的有向角；等腰省+直下口时 C_out 精确落 C_in）闭合 → 端点 snap（`_snap_geom_start/end` 仅动该端点+同步邻柄保切向方向、不传至下游连接）对齐拼合顶点 → 拼合处上下折角 G1 倒圆（`_g1_fillet`：入/出边各沿弧长退 δ、插三次贝塞尔，端切向与两侧边一致；同族边内部所有衔接点切向共线）。2 省或省腿未穿越上下边界 → 回退无省提取（stderr 告警）。
3. 裁切三段：`_to_local_geom` 关于 origin 180° 旋转变换（`local=(origin.x−x, origin.y−y)`，**保向** det=+1、符号面积符号不变；局部 +Y 朝下，同 `piece_svg` 不翻转口径）-> `apply_shrinkage`（经向=局部 Y=后片裤长向，§3.1 关联布纹 → Y 吃 warp、X 吃 weft，同腰头 WIDTH 映射；`apply_shrinkage` 形参 1 控 X、2 控 Y；warp/weft 取机头裁片专用 `back_yoke_shrinkage_warp/weft`，None 回退全局 `shrinkage_warp/weft`）-> `add_seam_allowance`（**边名→缝份 dict** `{top,bottom,cb,side}`：`cutter._sa_amount` 鸭子类型化 dict|`WaistbandSeamAllowances`，机头底边埋夹 1.2、腰口/后中/侧缝 1.0，§4.1；后中为左右对称片拼合线仍外扩〔非折线〕，与腰头后中折线不同）。**底边两端斜角 (bottom,side)=PN / (bottom,cb)=P0 用镜像折角**：`add_seam_allowance(corner_treatments={("bottom","side"):"mirror",("bottom","cb"):"mirror"})` → `cutter._mirror_point`（相邻缝份边界方向 = 原切线 t_b 关于底边缝折线垂线 n_a 的轴对称镜像 t_b′=2(t_b·n_a)n_a−t_b，翻折后缝份边缘与裁片重合，§4.2.1；直角角点 t_b′=t_b 退化即 miter，仅斜角相异。键=(折线边,被镜像边)首元素恒 bottom；cutter 序 PN 角正序 (bottom,side)、P0 角逆序 (cb,bottom)，两种顺序键都查、逆序命中时 _mirror_point 形参交换。镜像退化平行→回退 miter→阶梯）。
4. 刀口（§5）：后中拼合中心点（对称片 Cut 2）；有省另加拼合线两端（C_in 底边侧、St_in 腰口侧）。丝缕线竖向（经向=局部 Y）。
选项字段：back_yoke_seam_allowances（YokeSeamAllowances：top/bottom/cb/side，TOML `[options.back_yoke_seam_allowances]` 子表）/ back_yoke_join_fillet（拼合折角 G1 倒圆量 cm，默认 0.4；0=不倒圆直接顺接）/ back_yoke_side_corner_mirror（内缝顶点 bottom×side 缝份镜像折角开关，默认 True；False=纯 miter）/ back_yoke_cb_corner_mirror（后中底角 bottom×cb 缝份镜像折角开关，默认 True；False=纯 miter。两角独立）/ back_yoke_shrinkage_warp / back_yoke_shrinkage_weft（机头裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft，§3/§5；非 None 须在 [0,0.2)；TOML 尺寸单里属 options 主表字段，须置于所有 [options.*] 子表之前，否则被吸入前一个子表、主表读不到而静默回退全局）。输出：`--yoke-svg` 旗标 / `api.run(yoke_svg=...)`（需完整整版且 back_yoke 开启）。

前口袋独立裁片（袋贴/贴袋）已程序化：`build_front_pocket(main_ctx)`（`flows/front_pocket_flow`，前口袋裁片.md §一~§三；自含裁片，非 FlowRunner 编排，同 `build_waistband`/`build_yoke`/`closure.py` 口径）。按口袋类型派发（front_pocket_facing 优先，否则 front_patch，都没开 raise ValueError）：
1. 挖削嵌入式（INSET，front_pocket_facing 开）→ `build_front_facing` 袋贴裁片（§1.1）：**外边界 1:1 完美复制前大片**——腰弧段 waist=`front.pocket_facing_waist_edge`（O→P_fw）+ 外缝弧段 side=`front.pocket_facing_outseam_edge`（P_fs→O），内边 inner=`front.pocket_facing_inner`（单曲线）或 polyline 模式 `front.pocket_facing_inner_seg{i}` 折角链（P_fw→P_fs）闭合截取。**先画后裁**：袋贴边界已由 `draw_front_pocket_facing`（front_pocket_steps）上版，本流程只提取、不重画。内部标记 marks（§1.1 必须保留）：袋口切削线 `front.pocket_mouth`（有省）/ 净线 `front.pocket_mouth_baseline`（无省）/ polyline 的 `_seg{i}`；有省另加吃省边 `front.pocket_cut_start`（P1→P1′）。刀口（§2.2）= 袋口净线起止端点 [P1′（有省）或 P1、P2]。
2. 表面外贴式（PATCH，front_patch 开）→ `build_front_patch` 贴袋裁片（§1.2）：前大片保持 100% 完整，直接拷贝净样母线 `front.patch_net_seg{i}` 闭合链；seg1 命名 top（袋口内折边）、seg2..N 命名 side（四周缝边）。刀口 = 各净角点 `front.patch_net_pt{i}`（四周折边指示）。无内部标记。
3. 共享收尾 `_finish_piece`：主版坐标 **Y 轴反射**到局部（`local=(x−origin.x, origin.y−y)`：X 不翻保侧缝在左/前浪在右、Y 翻让腰头在上袋身向下，同 `piece_svg` 不翻转口径）→ **自定向**（反射 det=−1 翻转绕向，闭合多边形 shoelace > 0 则反转边序 + 每条 geom 反向，目标 < 0 保 cutter 外法向外扩，同机头负面积约定）→ 竖向丝缕线（经向 = 大片裤中线垂直方向 = 局部 Y，bbox 中心 x，上下各留 15%）→ 先缩水后缝边（§2.1）→ 装配 PatternPiece + 局部 ctx。
4. 缩水/缝边：`apply_shrinkage(weft, warp)`（经向 = 局部 Y → Y 吃 warp、X 吃 weft，同机头 WIDTH 映射；**warp/weft 取前口袋专用 `front_pocket_shrinkage_warp/weft`，None 回退全局 `shrinkage_warp/weft`**，换布/不同批次可单独控制）；缝份 dataclass 直传 `add_seam_allowance`（边名 = 字段名：袋贴 `FrontFacingSeamAllowances` waist/inner/side、贴袋 `FrontPatchSeamAllowances` top〔袋口内折边〕/ side〔四周缝边〕）。
选项字段：front_pocket_facing_seam_allowances（FrontFacingSeamAllowances：waist/inner/side，默认均 1.0）/ front_patch_seam_allowances（FrontPatchSeamAllowances：top 默认 3.0 / side 默认 1.2，TOML `[options.*]` 子表）/ front_pocket_shrinkage_warp / front_pocket_shrinkage_weft（前口袋裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft，§2.1；非 None 须在 [0,0.2)；TOML 尺寸单里属 options 主表字段，须置于所有 [options.*] 子表之前——否则被吸入前一个子表、主表读不到而静默回退全局）。输出：`--front-pocket-svg` 旗标 / `api.run(front_pocket_svg=...)`（需完整整版且 front_pocket_facing 或 front_patch 开启）。

袋布独立裁片（一片式对折）已程序化：`build_front_pouch(main_ctx)`（`flows/front_pouch_flow`，口袋布裁片.md §2~§6；自含裁片，非 FlowRunner 编排，同 `build_front_pocket`/`build_yoke`/`closure.py` 口径）。
1. 一片式对折构造（§2）：底层 = 大片原样复制（节点链 seg2..segN→bottom + 侧缝链→side + 腰弧 b→P_w0→waist，跳 seg1 折叠边）；面层 = 小片（上版时已挖袋口）沿袋布内边 P_w0→K1（`front.pouch_waist_anchor`→`front.pouch_node1` 连线）轴对称后反转拼合。小片上沿已走袋口切削线（有省 C_cut=`front.pocket_mouth` / 无省净线=`front.pocket_mouth_baseline`），镜像即得挖削，免布尔运算。对折边 P_w0-K1 为内部折叠线不入周界，进 `marks` 折叠指示。
2. 省口闭合：面层腰弧边必须取 P1′→P_w0——小片腰弧边起于 P1，省口 P1′→P1 张开会致轮廓 GAP；`_build_top_waist` 沿有效腰弧按弧长细分重建 `bezier_subrange(w_arc, t_at_length(p1_dist+dart_width), t_at_length(p1_dist+waist_safe))`。**勿用 `t_at_y`**（腰弧近水平，区分不了 P1/P1′）；与 `draw_front_pocket` 的 P1′=point_at_length 口径一致保证严合。勿复用 `front.pouch_small_waist_edge`（起于 P1，带张开省口）。
3. 镜像边命名：面层镜像反转边加 `_m` 后缀（bottom_m/side_m/waist_m）——折叠点 P_w0/K1 处异名边（waist/waist_m、bottom_m/bottom）强制 cutter miter，防折叠角缝份缺量；**mouth 仅面层独有、无底层对边，不加 `_m`**（SA dict 只有 mouth 键，加了后缀查不到→0 缝份）。SA 走 dict：`{bottom,bottom_m,side,side_m,waist,waist_m,mouth}`，`_m` 同值；缝边调用传 `miter_limit=float("inf")` 不限长（锐角保留标准 miter 交点，见文末踩坑条目）。
4. 坐标/对称性检验/刀口/丝缕：局部 = Y 反射 origin=P_w0（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向。局部 Y 反射与主版 P_w0-K1 镜像共轭 → **面层 = 底层关于局部折叠轴 (0,0)→local_K1 的镜像**（test_pouch_piece 对称性断言据此，免在主版坐标重算）。刀口（§5）= 折叠两端 P_w0/K1 + 袋口起止镜像点 P1″/P2′（有省取 `front.pocket_p1_transfer`、无省 `front.pocket_p1`）。丝缕竖向 = 局部 Y（§6 继承大片经向）。
5. 缩水（§3）：**默认强制 0** 绝对隔离大身面料——与机头/前口袋的 None 回退全局不同，袋布是默认 0 数值、无回退语义；非 0 才走 apply_shrinkage。
选项字段：front_pouch_seam_allowances（PouchSeamAllowances：fold=0 对折线 / mouth=1.0 袋口 / waist=1.0 / side=1.0 / bottom=1.2，TOML `[options.front_pouch_seam_allowances]` 子表）/ front_pouch_shrinkage_warp / front_pouch_shrinkage_weft（默认 0.0，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同前口袋/机头缩水口径）。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）均已录入。输出：`--front-pouch-svg` 旗标 / `api.run(front_pouch_svg=...)`（需完整整版且 front_pouch 开启）。另注：`front_pocket_dart_width` 默认 2.0 非 0，测试无省场景须显式置 0。

门襟独立裁片（单排/双排）已程序化：`build_front_fly(main_ctx)`（`flows/front_fly_flow`，门襟裁片.md §1~§4；自含裁片，非 FlowRunner 编排，同 `build_front_pouch` 等口径）。步骤层 `_draw_separate_fly` 已把独立门襟净样叠画在前片上（先画后裁），本流程只提取、不重画；`fly_separate` 未开 raise ValueError。返回 `(单排片, 双排片|None, 局部调试 ctx)`：
1. 单排（单层，§2）：原样提取 5 边——top=reverse(腰头线子弧 O→T)、outer×3（外缘直线 h−R → 底角 90° 圆角贝塞尔 → 底边，**精确 G1 链必须同名 outer**，见文末踩坑）、inner=内边（与前浪缝合线重合）。刀口 1 = 内边自 O 开深 L 处（拉链止口/前浪对位）。
2. 双排（对折，§4）：去底角弧——外缘重构直线 `LineSegment(T, E)`（E = T + 前浪方向·h 重算，**e_bot 未上版勿从圆角反推**；与内边严格平行绝对等长，O/T/E/S 平行四边形）、底端 E→S 直线闭合（顶保留腰弧）；半边沿对折轴 O→S 镜像展开（`_reflect_geom` 贝塞尔控制点同步），镜像边 `_m` 后缀（SA dict 给 `_m` 同值键）。对折线 O→S 不入周界、进 marks 折叠指示。刀口 3 = 对折线两端 O/S（文档强制）+ 外缘 T+前浪方向·L。`fly_sep_double=False` 时双排片返回 None。
3. 共享收尾 `_finish_fly_piece`：局部 = Y 反射 origin=O（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（经向=局部 Y，与前/后片一致）→ 缩水（`fly_shrinkage_warp/weft`，**None 回退全局**主面料口径，同机头/前口袋，异于袋布默认 0）→ 缝边（`FlySeamAllowances`：top/outer/bottom/inner；bottom 仅双排消费）→ 局部 ctx 落 `front_fly_single/ double.edge{i}`。
金标注意（test_fly_piece）：底角圆角弧长**无闭式**——外缝顶点 T 取在弧形腰头线上（弧长 W 处），前浪与底边实际夹角 ≈82° 而步骤层 `_QUARTER_K` 手柄常数按 90° 圆弧调定，贝塞尔外凸（实测 ≈4.92 vs 90° 圆弧 4.71）；断言改用构造不变量（径向两侧距 e_bot = R + 弧长界于圆弧 R·θ 下界与控制多边形上界）。闭环断言用 `distance_to < 1e-9` 容差（贝塞尔接缝有 ~1e-14 浮点噪声，勿用精确相等）。
选项字段：fly_sep_double（双排裁片开关，默认 True）/ fly_seam_allowances（FlySeamAllowances：top/outer/bottom/inner 默认均 1.0，TOML `[options.fly_seam_allowances]` 子表）/ fly_shrinkage_warp / fly_shrinkage_weft（门襟裁片专用经/纬向缩水率，None=回退全局 shrinkage_warp/weft；非 None 须 [0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同前口袋/机头/袋布缩水口径）。两示例尺寸单均已录入。输出：`--front-fly-single-svg` / `--front-fly-double-svg` 旗标 / `api.run(front_fly_single_svg=..., front_fly_double_svg=...)`（需完整整版且 fly_separate 开启；双排开关未开时双排输出跳过并警告）。

小表袋独立裁片已程序化：`build_watch_pocket(main_ctx)`（`flows/watch_pocket_flow`，小表袋裁片.md §一~§四；自含裁片，非 FlowRunner 编排，同 `build_front_fly` 等口径）。步骤层 `draw_front_watch_pocket` 已上版净样（先画后裁），本流程只提取、不重画；watch_pocket 未开或 `front.watch_pocket_seg1` 不存在 raise ValueError。按 watch_pocket_mode 派发，返回 `(PatternPiece, 局部调试 ctx)`：
1. 模式 A（facing_intersect，§2.1）：四边界闭合拓扑 pt1→pt2→pt3→pt4→pt1 = top 袋口直线 + side 内侧边 + bottom 底边（袋贴内边贝塞尔子段）+ side 外侧边。**底边方向归一**：`curves.bezier_subrange` 恒从参数小端跑向大端、方向随袋形不定，按角点距离归一到 p0≈pt3 / p3≈pt4（`_reverse_geom` 弧长不变），否则闭合链断裂；归一另保证装配刀口弧长中点从固定端起量（金标独立复算可 1e-6 命中）。
2. 模式 B（custom，§2.2）：`while f"front.watch_pocket_seg{i}" in ctx.sheet` 经 `sheet.get(...).geom` 收集混合 line/curve 闭合链（同 `build_front_patch` 口径，line/curve 混合不能用 ctx.line/ctx.curve 读）；N==4 同模式 A 三类边名（top/side/bottom/side）、N≠4 时 seg1=top 其余 side（任意多边形无法可靠识别底边，bottom 字段不生效）。
3. 共享收尾 `_finish_piece`：局部 = Y 反射 origin=pt1 袋口外上角（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（经向=局部 Y；局部变换仅平移+Y 翻转无旋转，主片裤长竖向映射后仍竖向，与小表袋摆放 rotate_deg 无关，§3.2）→ 缩水 → 缝边。刀口（§4.2）3 个 = 袋口两角折边刀口 pt1/pt2 + 装配对位刀口 1 个（模式 A=底边弧长中点；模式 B=最长非顶边中点，直线参数中点 `point_at(0.5)`、曲线弧长中点 `point_at_length(len/2)`，边长比较用 `cutter.edge_length`；刀口为独立 Point 只转局部、不随边反转）。
4. 缩水（§3.1）：**里料默认 0** 绝对隔离大身面料，同袋布口径（异于机头/前口袋/门襟的 None 回退全局）；`if warp or weft` 条件式、默认跳过 apply_shrinkage。缝份 `WatchPocketSeamAllowances` 直传（top 袋口折边 2.5 双折边明线 2.0~2.5 取上限 / side 1.0 / bottom 1.0 默认恰与袋贴 inner 一致，§4.1）。
选项字段：watch_pocket_seam_allowances（WatchPocketSeamAllowances：top 2.5/side 1.0/bottom 1.0，TOML `[options.watch_pocket_seam_allowances]` 子表）/ watch_pocket_shrinkage_warp / watch_pocket_shrinkage_weft（默认 0.0，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同袋布缩水口径）。api.run() 形参含 watch_pocket_mode / watch_pocket_width / watch_pocket_taper（此三者属补齐既有透传缺口，绘制层选项此前 api 未透传）/ SA dict / 缩水率 / watch_pocket_svg。两示例尺寸单（examples/size_female_165.toml / size_female_zhitong.toml）均已录入。输出：`--watch-pocket-svg` 旗标 / `api.run(watch_pocket_svg=...)`（需完整整版且 watch_pocket 开启）。

后贴袋独立裁片已程序化：`build_back_patch(main_ctx)`（`flows/back_patch_flow`，后贴袋裁片.md §1~§5；自含裁片，非 FlowRunner 编排，同 `build_watch_pocket` 等口径）。步骤层 `draw_back_patch_pocket` 已上版净样（先画后裁），本流程只提取、不重画；back_patch 未开或 `back.patch_net_seg1` 不存在（含 --until 中断、未开 back_yoke）raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`：
1. 净样 1:1 完整复制（§1）：`while f"back.patch_net_seg{i}" in ctx.sheet` 经 `sheet.get(...).geom` 收集闭合链（line/arc 混边不判类型，同 `build_watch_pocket` 模式 B 口径）；边名按 back_patch_shape 派发：rectangle `[top,side,bottom,side]` / baker_shield 5 边（底尖两斜边均 bottom）/ angular 6 边（两斜切均 bottom）/ custom：N==4 同 rectangle、N≠4 `[top]+[side]*(N−1)`（同小表袋口径，任意多边形无法可靠识别底边）；段数与形态模板不符抛 ValueError（防上游形态路由变更静默错位）。净角点 `back.patch_net_pt{i}` 全部收集作折边指示刀口。
2. 共享收尾：局部 = Y 反射 origin=pt1 袋口近后浪侧顶点（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 + 竖向丝缕（§5：经向=局部 Y 与后大片裤长**绝对平行**；局部变换仅平移+Y 翻转无旋转，贴袋在主版上的摆放旋转角保真保留为袋与经向的夹角）→ 缩水 → 缝边。
3. 缩水（§2 大身面料全链路）：`back_patch_shrinkage_warp/weft` None 回退全局 `shrinkage_warp/weft`（同机头/前口袋/门襟口径，**异于袋布/小表袋的里料默认 0 隔离**）；竖向丝缕 → Y 吃 warp、X 吃 weft。
4. 袋口折边（§3/§4，cutter `HemTreatment`）：top 边为直线 → `add_seam_allowance(..., hem=HemTreatment("top", taper))`——**锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线**（折边自毛样外侧缝边线起翻、翻盖全宽 = 毛样在袋口层的全宽，翻折后恰与侧缝折边区重合），自 P_notch 沿镜像方向 `D=E−2(E·N)N`（E=角点处指向袋内的侧边切线）上行距袋口线 sa_top 得 M、沿袋口内收 |taper| 得 T（倒梯形防折后毛边外露）；毛样顶链 P_notch_a→T_a→T_b→P_notch_b **凸链**（P_notch 由角点 miter 折边侧 sa 传 0 自动得出，即 §4 对位刀口位，×2 记入毛样刀口）。custom 弧袋口（seg1 贝塞尔）无直线镜像轴 → hem=None 降级常规法向放缝 + flow notes 显式记录。刀口类型/深度（V/I、3mm）仅工艺标注进 notes、不改位置几何。缝份 `BackPatchSeamAllowances`（top 袋口折边 2.5 双折 / side 1.0 / bottom 1.0）。
选项字段：back_patch_seam_allowances（TOML `[options.back_patch_seam_allowances]` 子表）/ back_patch_top_hem_taper（默认 −0.15，≤0）/ back_patch_notch_type（"V"/"I"）/ back_patch_notch_depth（默认 0.3）/ back_patch_shrinkage_warp / back_patch_shrinkage_weft（None=回退全局，[0,0.2)；TOML 主表键，须置于所有 [options.*] 子表之前，同机头缩水口径）。api.run() 形参同步透传 6 参数 + back_patch_svg。示例尺寸单 examples/size_female_zhitong.toml 已录注释键（其 custom 袋口为直线 → hem 生效，可作 CLI 手测）。输出：`--back-patch-svg` 旗标 / `api.run(back_patch_svg=...)`（需完整整版且 back_patch 开启〔依赖 back_yoke 定位〕）。

前片独立裁片已程序化：`build_front_piece(main_ctx)`（`flows/front_piece_flow`，前片裁片.md §1~§3；自含裁片，非 FlowRunner 编排，同 `build_back_patch` 等口径）。**无 bool 总开关**——前片净样元素整版必有，由输出旗标直接驱动；`front.hem` 不在版（--until 中断/空版）raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`。三大形态以**净边条件矩阵**装配（18 组合 = 腰头 2 × 口袋 3 × 门襟 3，主版自然序：前浪区 → 下裆缝 → 脚口 → 外缝上行 → 侧缝弧上段 → 袋口挖削 → 顶边腰弧）：
1. 弯腰头剥离（§1.1）：统一经 `steps.front_steps.effective_waist(ctx)`（返回 (B/B′, 腰弧, 侧缝弧长)，与口袋/门襟步骤同源同口径）；顶边 = 弯 `front.lower_waistline_arc` / 直 `front.waistline_arc`；前浪自 A′ 起按 rem = W − 斜线长三分支（斜线余段 / `bezier_subrange(rise_curve, t_at_length(rem), 1)` / rem==0 跳零长段）。
2. 口袋挖削（§1.2）：侧缝弧截到 P2（`t_at_length(s_side − p2_drop)`，与步骤层同式同源）；挖削边 mouth = 切削线反向（有省 `front.pocket_mouth` / polyline 链逆序；dw=0 切削线即净线同元素）；顶边腰弧自 P1′（有省）/P1（无省）起余段；`front.pocket_cut_start`（P1→P1′ 吃省撇削边）属挖除区**不进大片边界**。
3. 连裁门襟（§1.3）：fly 四元素（top/outer/bottom 底角弧/bottom 融合弧——后两段**同名** G1 平滑续接）+ 前浪自 fly_tangent 起余段（extend 与 front_fly_steps 同式重算：fly_blend_drop None 时 `max(fly_blend_extend, extend_min)`）；fly_separate 时叠画元素不进边界、与无门襟同形。**门襟底缘在臀围线之上**（fly 外线不与臀线相交）。
4. 局部化/自定向/丝缕：Y 轴反射 origin=B/B′（同 `front_pocket_flow._finish_piece` 口径）+ shoelace<0 自定向 → **片上恒存反转链**：waist 自 A/A′ 起、rise/fly_top 环回 A/A′（测试断言端点方向须按此存向，勿按主版自然序）；竖向丝缕（X 不翻避镜像，经向 = 局部 Y）。
5. 缩水/缝边/折角：`front_piece_shrinkage_warp/weft` None 回退全局（主面料口径，同机头/门襟）→ `add_seam_allowance`（`FrontSeamAllowances`：waist/rise/inseam 1.0、side 1.5、hem 裤口卷边 2.5、mouth/fly_* 1.0）+ 裆尖镜像折角 `corner_treatments={("rise","inseam"):"mirror"}`（`front_piece_crotch_corner` 默认开。**折线边 = 前浪 rise**：前浪缝份翻折时折轴是前浪缝本身、非下裆缝，下裆缝侧缝份边界关于前浪折线镜像、翻折后与下裆缝缝份边平齐。键序曾误置 ("inseam","rise")——折轴成下裆缝，且裆尖内角 ≈87° 近直角时镜像退化 ≈miter，角点呈"向内平切"〔用户目检发现〕；cutter 双向查键，链序 (inseam,rise) 逆序命中时 `_mirror_point` 形参自动交换，故仅调键序即可）。**角部两态**（`front_piece_crotch_corner` 默认 True=mirror 折角；False=**纯尖角跟随净样**）——False 走 `"miter"` 不限长纯尖角**自然外延相交**（`_natural_join_sharp`/`_extrapolate_offset`：两侧缝边按**贝塞尔多项式自然外延**——point_at/tangent_at 对 t∉[0,1] 照公式求值、外延点法向 = 外延处导数法向，延续曲线自身张力与曲率，采样 0.5cm、搜索 4·max(sa)+20——求首个交点成尖；直线边沿轴向延伸即切线 miter；无交回退切线 miter→阶梯。**多项式外推在此成立的原因**：外推的摆钩发生在远端，首个交点落在钩回前的近角段〔此前 4×4 延续模型矩阵实验中多项式×多项式在 6cm 短程内无交被判不行，加大搜索窗 + 粗采样后近角段近似平伸、可交〕；**不做任何圆弧抹角**——2026-08 用户三轮目检定稿：等距弧/大圆弧/浪尖相切圆角全部废除，cutter 的 `"round"`/数值半径/`("tip",ρ)` 处理及 `_round_join_points`/`_circle_seg_cross`/`_arc_points`/`_tip_round_points` 已整体删除，圆弧抹角不符合工艺——「净样裆尖就是尖的」）；**勿依赖默认限长 miter**——直筒等尖裆内角 ≈75°、miter 长 ≈1.64·缝宽 > 1.5 限长会静默回退阶梯角，角部留「竖一刀+斜一刀」台阶断点不圆顺〔用户目检发现，金标 M 尺寸角度较缓未暴露〕；尖角是该角工艺目标形态而非偶发尖刺，故 cutter 增 `"miter"` 取值显式绕过 miter_limit，键序对称、平行退化仍回退阶梯）；False+fillet>0 走 cutter corner_treatments 数值半径大圆弧（默认 2）。cutter `"round"` 等距弧能力保留（含大圆弧放不下时的回退级），但前片裆尖不再使用。**数值半径=大圆弧抹角**：以裆尖为心、半径=数值的圆弧（等距圆弧的半径推广）——两侧偏移链落入圆内的点裁掉、以圆弧桥接（`_circle_seg_cross` 交点在偏移折线上插值；`_arc_points` 两候选弧取 miter 点近侧即外侧弧——**勿用有向短弧选侧**：R=缝宽时短弧恰为外侧弧，R 增大后两交点方向转过对跖点、短弧翻到内侧），弧上各点距净边 ≥ 缝宽（**缝份不塌**；半径>缝宽时弧比折角更凸、视觉抹圆无尖角）。半径 < 缝宽（弧会切进缝份）或圆吞没整条邻边时还原裁剪点、回退 `"round"`。**"round"=严格等距圆弧**：`_round_join_points` 以裆尖为心、缝宽为半径的**等距圆弧**连接两偏移边端点（c+n_a·sa_a → c+n_b·sa_b，sa 不等时半径沿弧线性渐变，自 n_a 向 n_b 取有向短弧即外侧弧），缝边**处处与净边严格等距**、无折角切线。两算法均对键序对称（fold_is_edge 不参与），法向平行（Δθ≈0）返回 None 回退 miter。曾试"轮廓延伸态"（前浪净边 C2 延续越出裆尖、偏移链交下裆缝缝份边界线，独立开关 front_piece_crotch_contour）——弯腰头形态下前浪曲率大，C2 延续越摆越远，缝边翘成高尖角且非真等距〔用户目检发现〕；亦试"两偏移切线内切圆"相切圆角——75° 尖角处内切圆深嵌角内、弧顶距净尖仅 ≈0.3cm（缝份 1 塌至 0.3，缝份不塌不变量破坏）；均已删除归并为三态；其后等距圆弧态亦被取消——False+fillet=0 改为尖角跟随净样（用户目检确认角部须与净样轮廓一致），且尖角须显式 `"miter"` 不限长（默认限长会把尖裆切成阶梯角）；圆弧抹角各形态（含浪尖相切圆角）后被用户全部废除删除——裆尖净样是尖的，缝边只能是尖的；再后切线直段亦被否（「前浪缝边弧线和内缝缝边弧线自然相交」），其间曾上线「等曲率延续弯向角点转向 + G1 单曲率弧重建过渡链」方案（解决拉直与鼓包），最终用户手改为纯贝塞尔多项式自然外延求交并目检通过（`_natural_join_sharp`，2026-08 定稿）。
6. 刀口法向投影（§2.3，flow 私有实现不动 cutter 公开 API）：净样刀口 [膝围×2 防扭脚、臀围、袋口 P2+P1′/P1、拉链止口（连裁，外缘链 `point_along_chain` 开深 L 处）、卷边起折×2、毗围点（thigh_line 存在时；d=0 内端 = 裆尖角点跳过）] 定位载体边（直线参数投影 clamp / 贝塞尔 64 采样最近点 / 角点命中多边取法向分量均值）沿外法向射线与 gross_polygon 折线求交取最小正 s，**整体替换 gross_notches**；shrunk_notches 保留缝合线位不丢信息——**gross=裁剪线位、shrunk=缝合线位**，对位断言用 shrunk。膝围双刀口按所在边缝宽外移（侧缝 1.5 / 下裆 1.0）。
7. 内部辅助线 marks（§3.3）：臀/膝/毗围水平线以净边链折线求交取 min/max x 截断（连裁组臀线右端落门襟底角弧、口袋组左端落侧缝弧上段）；随缩水同比例变换（cutter `apply_shrinkage` 已同步缩放 marks）。
选项字段：front_piece_seam_allowances（TOML `[options.front_piece_seam_allowances]` 子表）/ front_piece_crotch_corner（默认 True=镜像折角；False=纯尖角跟随净样——贝塞尔多项式自然外延求交成尖，不抹圆）/ front_piece_notch_type（"V"/"I"，仅 notes 工艺标注）/ front_piece_shrinkage_warp / front_piece_shrinkage_weft（None=回退全局，[0,0.2)；TOML 主表键须置于所有 [options.*] 子表之前，同机头缩水口径）。两示例尺寸单均已录入。api.run() 形参同步透传。输出：`--front-piece-svg` 旗标 / `api.run(front_piece_svg=...)`（需完整整版；无开关守卫分支）。金标 tests/test_front_piece.py：18 组合参数化闭合/定向/结构 + 边长独立复算 + 端点链向 + 折角/刀口/缩水/marks。

后片独立裁片已程序化：`build_back_piece(main_ctx)`（`flows/back_piece_flow`，后片裁片.md §1~§6；自含裁片，同 `build_front_piece` 口径，不在 FULL_FLOW 内）。**无 bool 总开关**--后片净样元素整版必有，由输出旗标直接驱动；`back.hem` 不在版或 back_yoke 开但 `back.yoke_cb_point` 未上版（--until 中断）均 raise ValueError。返回 `(PatternPiece, 局部调试 ctx)`。上边界三形态以净边条件矩阵装配（腰头 2 × 机头 有/无 = 4 组合，主版自然 CCW 序：上边 -> 侧缝下行 -> 脚口 -> 内侧缝上行 -> 后浪上行，链首 = cb_top）：
1. 分离基准（§1）：后片独立裁片不含腰头与机头。有 yoke：上边 top = `back.yoke_bottom_seg{i}` 链（P0->PN 1:1 复制，空链回退直线 P0->PN 同 yoke 口径）；无 yoke 直腰头：waist = `back.waistline_arc`（A->B **弧原方向即 cb->side 侧，勿反向**）；无 yoke 弯腰头：waist = `back.lower_waistline_arc`（O'->X' 同向）。后浪/侧缝下行链 = `(rise_slant, rise_curve)` / `(反向髋腰弧, outseam_upper, outseam_lower)`，自链首顶点取**弧长后缀**（`_chain_suffix`：首个被部分消费段在 d 处切开、贝塞尔走 `bezier_subrange(t_at_length(d),1)` 保形）--d 与 `back_yoke_steps` 量取同式同源（有 yoke = D_端点 + 弯腰头下移 W；无 yoke = 弯 W / 直 0）。局部化：Y 轴反射 origin = cb_top（有 yoke P0 / 无 yoke A 或 O'）+ shoelace<0 自定向（主版 CCW 反射即 CW，正常不反转，链首恒 = (0,0)）。
2. 后省（back_dart 开）：省尖落在裁片区内（省穿越上边界）时**边界按图提取**（省量吸收主口径是 back_waist_dart 约克转移，与机头 §2.2 绕尖旋转不联动）+ stderr 告警一次 + 省腿裁片内子段（折线采样射线法 + 64 采样首末在内点）进 marks；省尖在上边界之上则全由机头吸收、无痕。
3. 缩水/缝边/折角（§2/§3 顺序：净样 -> 缩水 -> 缝边，缝份绝对值不乘缩水率）：`back_piece_shrinkage_warp/weft` None 回退全局（主面料口径）-> `add_seam_allowance`（`BackSeamAllowances`：top 拼机头 1.0 / waist 装腰 1.0 / cb 后浪 1.0 / inseam 1.0 / side 1.5 / hem 脚口卷边 2.5）+ 浪尖角部两态 `corner_treatments={("cb","inseam"):"mirror"|"miter"}`（`back_piece_crotch_corner` 默认 True=镜像折角〔折线边 = 后浪 cb，同前片裆尖 (rise,inseam) 先例〕；False=纯尖角跟随净样）。
4. 刀口（§4，法向投影同前片 flow 私有实现）：膝围×2、臀围×2（`back.hip_outseam_point`/`back.hip_inner_point`）、横裆线交点×2（**按净边链整链求交 `_h_cross_points`，勿预设载体边**）、浪尖、脚口×2（**与净样脚口线对齐** = 内外侧缝 ∩ 净样脚口线角点，用户口径 2026-08：不与卷边宽关联）、毗围点（thigh 录入时）、口袋对位（贴袋顶线 `back.patch_net_seg1` 自侧端沿袋口方向延长 ∩ 侧缝链 `_chain_hit`）、后中拼接 cb_top。**角点刀口（脚口×2/浪尖/后中拼接）不外扩投影、保留净样位**——角点本身是净边顶点，若按角平分法向投影会落到毛样外角点上（用户目检判定错位；`_project_notches(..., keep=)` 按 1e-9 坐标匹配跳过投影；**有缩水时 keep 集须同步按 (1+weft, 1+warp) 缩放**，载体刀口是 shrunk_notches、净坐标 keep 会失配，直筒 0.1/0.06 缩水场景实测暴露）。d=0 时毗围线与横裆线共高，外缝刀口几何重合属固有（非 bug）。
5. 内部线/定位孔（§5/§6）：臀/膝围水平线随净边截断为 marks；**毗围线 1:1 拷贝真实测量线**（外缝点->裆端**斜量线**，两端点本就在净边上--按水平 a.y 截断会在 d=0 时与横裆线同高重合叠影且丢斜量方向，用户目检发现缺线即此坑）；**横裆线不画**（用户口径 2026-08：毗围线即其测量基准、横裆水平线冗余，横裆高度交点仍进 §4 刀口；后片裁片.md §5 已同步改写）+ 后贴袋顶线 1:1 拷贝 mark；贴袋上端两顶点（`back.patch_net_pt1/pt2`）进 `PatternPiece.drills` 定位孔（新字段，随缩水同步变换，`piece_svg` 红空心圈渲染于定位图层）。
选项字段：back_piece_seam_allowances（TOML `[options.back_piece_seam_allowances]` 子表）/ back_piece_crotch_corner（默认 True）/ back_piece_notch_type（"V"/"I"）/ back_piece_shrinkage_warp / back_piece_shrinkage_weft（None=回退全局，[0,0.2)）。api.run() 形参同步透传。两示例尺寸单均已录入（165：注释缩水+mirror 折角+side 1.5；zhitong：缩水 0.1/0.06+尖角跟随净样+side 1.0，跟随各自前片工艺口径）。输出：`--back-piece-svg` 旗标 / `api.run(back_piece_svg=...)`（需完整整版；无开关守卫分支）。金标 tests/test_back_piece.py：4 组合参数化闭合/定向/结构 + 边长独立复算 + 端点链向 + 浪尖两态折角 + 刀口投影/计数矩阵 + 贴袋引用 + 后省告警/子段 marks + 缩水含 drills 同变换。

**踩坑（裁切层，§10.4/10.6 通用）**：
- `PatternPiece` 新增可选 `marks` 后，`apply_shrinkage`/`with_shrunk`/`with_gross` 均**按位置重建** PatternPiece——新增字段必须显式透传三者，否则被静默丢弃（marks 即差点丢，已在三者末位补 `out.marks`）。
- 缝份 `cutter._sa_amount` 已鸭子类型化（`getattr(name,0.0)`，任意"字段名=边名"的 dataclass 或边名→量 dict 通用），但缝份记录串 `_sa_notes` 曾硬编 `WaistbandSeamAllowances` 字段名（top/bottom/left_end/right_end）——现已泛化为 `vars(sa)` 列字段值（WSA 仍走专用分支列上/下口·左/右端），新增缝份 dataclass 无需再改 `_sa_notes`。
- **裁片坐标变换选错会镜像**：主版坐标 → 裁片局部坐标，机头/腰头用 **180° 旋转** `local=(origin.x−x, origin.y−y)`（det=+1 保向、绕向不变），前口袋曾照搬却**左右镜像**——180° 把 X 也翻了，前浪侧（主版右侧 P_fw）被翻到裁片左边。改用**关于过 origin 水平线的 Y 轴反射** `local=(x−origin.x, origin.y−y)`（det=−1，X 不翻保侧缝左/前浪右、Y 翻让腰头在上），反射反向由 `_finish_piece` 自定向补正（shoelace<0）。**新裁片选变换按"哪个轴该翻"决定**：翻 X=左右镜像、翻 Y=上下翻转、两轴都翻=180° 旋转（保向）；按 `piece_svg`「Y 向下不翻转」口径，通常只需翻 Y。
- **镜像/对折拼合裁片的同语义边必须异名**：两层拼合轮廓（袋布底层+面层镜像）同语义边若同名（bottom 对 bottom），cutter 同名边跳过 miter 平滑相接，拼合点（折叠顶点）处缝份缺量；面层边加 `_m` 后缀异名即强制 miter。但**仅单层独有的边不能加后缀**——SA 按边名查量，`mouth_m` 在 SA dict/字段里查不到静默取 0 缝份（袋布 mouth 即此坑）。后缀边须在 SA 传入处显式给 `_m` 同值键。
- **锐角 miter 会长成尖刺**：miter 交点距角点 = sa/sin(θ/2)，随轮廓内角 θ 变锐**无界增长**——袋布袋底×侧缝约 71° 角在 side/bottom 缝份调大后突出 1.67×sa 的长尖。`_miter_point` 有尖角限长 `miter_limit`（默认 1.5，`add_seam_allowance` 形参可调）：普通 miter 角超 max(sa)×limit 回退阶梯角；直角角点 1.414×sa 不受影响；mirror 角（工艺翻折重合）不受限。**袋布裁片不走默认限长**：`build_front_pouch` 显式传 `miter_limit=float("inf")`——锐角处取两偏移线交点的标准 miter 尖角（底部缝边延长线与侧边缝边线自然斜出），阶梯角在该裁片上反成多余折角。
- **精确 G1 连续链的分段边必须同名**：一条轮廓边由多段几何拼成、接缝处切向严格共线（如独立门襟外缘 = 外缘直线 → 底角圆弧 → 底边，圆弧手柄沿两侧直线方向构造）时，若异名，`_miter_point` 对平行切线（det≈0）回退阶梯角，接缝处缝份凸出 2·sa 尖刺；多段同名 outer 即按平滑相接处理、缝份连续外扩（单排片实测四向外扩恰 = sa）。与「镜像拼合同语义边必须异名」相对：**该 miter 的真折角拼合点要异名、不该 miter 的 G1 光滑接缝要同名**，按接缝两侧边是否真折角决定。
- **袋口折边 hem 的降级判据必须预扫描/主循环共用**：`add_seam_allowance(hem=...)` 在预扫描（`_hem_feasible` 判是否降级常规放缝）与主循环（发折边顶点链）**两处调用同一函数**，若各写一份判据，一处降级一处仍构造即毛样断链。降级条件：弧袋口（无直线镜像轴）/ 袋口零长 / 前后邻边同名 / sa_top=0 / 侧边与袋口**近平行**（|E·N|≤1e-6——测试造近平行用例需斜率 1e-7 级，1e-4 不触发、P_notch 会飞到 1e5 量级）。P_notch 勿另算交点：`_miter_point` 折边侧 sa 传 0 时 off_b 落袋口净线，交点自动 = 袋口净线延长线 ∩ 侧缝缝边线；hem 角 `miter_limit=inf`（规范指定构造非尖刺）、跳过 corner_treatments。撇势 taper 为绝对量不随缩水放大（先缩水后折边，折边距缩水后袋口线 sa_top）。流级金标勿硬编坐标——整版上贴袋带 rotate_deg 摆放角 + 约克底线倾斜，T/P_notch 须从 net_edges 公式级独立复算（`tests/test_back_patch_piece._hem_golden`）；另 `FlowRunner(M,o)` 自建 ctx，测试必须用 `run()` 的返回值（另 `DraftContext(M,o)` 是空版，画不上元素）。
- **折边锚点必须取毛样上的 P_notch，勿自净角起算**：曾以净角点 a/b 为锚上行 sa_top 生成折边，折边翻盖比大货毛样窄 2×SA_side（用户目检 SVG 发现），翻折后盖不住侧缝折边区。正确口径：锚点 = P_notch（袋口净线延长线 ∩ 侧缝缝边线），折边线自毛样外侧缝边线起翻，翻盖底宽 = 毛样在袋口层的全宽（金标 16 = 净口 14+2×sa_side）；毛样顶链 P_notch_a→T_a→T_b→P_notch_b 凸链无台阶——hem 边只发 `[T_a,T_b]`，两端 P_notch 由角点 miter（折边侧 sa=0）发射，`_hem_points` 内部复用 `_miter_point` 算锚点（近平行兜底回净角）。
- **弧长反推 t 的量化误差**：`t_at_length`/`bezier_subrange` 按 64 折线采样，提取子段实测长度与公式精确值差 ~4e-5——金标断言"公式推导长 vs 提取子段实测长"时容差放 1e-3；复算与实现同式同源（如同一 `t_at_length` 取段）则可 1e-6。
- **`DraftSheet` 无 `len()`**：计数用 `sum(1 for _ in sheet)` 或 `sheet.points/lines/curves/of_type(...)`；判存在 `"name" in sheet`。
- **`Vector` 无 `__add__`、`Point` 只支持 `+ Vector`（不支持 `− Vector`）**：向量累加（如角点法向均值）按 dx/dy 分量累加后 `Vector(nx, ny).normalized()`；点减向量改写 `p + v.scale(-k)`（`p - v.scale(k)` 抛 AttributeError——`Point.__sub__` 只接受 Point）；`perpendicular()` 返回已归一化的逆时针 90°。
- **mirror 折角键序 = (折线边, 被镜像边)，选错折轴在直角处静默退化**：`corner_treatments` 首元素是缝份翻折的折线边（翻折轴 = 该边缝线本身），物理上"谁的缝份被翻折、折轴就是谁的缝"——前片裆尖曾误置 ("inseam","rise")（折轴成下裆缝），且裆尖内角 ≈87° 近直角时 `_mirror_point` 镜像退化 ≈miter，角点与 miter 仅差 0.13cm、目检呈"向内平切"，反转角完全没生效却不报错。判别法：按翻折后边缘应与**相邻边缝份边**平齐独立推预影像线，与角点比对（前片正确键 ("rise","inseam") 角点 24.376 vs 预影像 24.383）。cutter 双向查键、链序任一顺序都能命中，键序错不抛错只能靠几何判别。
- **曲线过端点"自然延续"的选型坑**：缝边/轮廓需越过角点延伸相交时，三种直觉做法都可能翻车——①贝塞尔多项式外推（point_at(t)，t∉[0,1]）越延越摆、遇拐点回摆成钩；②真密切弧（保持端点自身曲率方向）在端部"减弯"的曲线上朝远离角点转向的一侧卷曲、与对侧摆离无交点；③端切线延伸在近水平/近垂直端切线处拉出长直段（目检"被拉直"）。定稿解（裆尖案例，用户手改验收）：**贝塞尔多项式自然外延求交**（cutter `_natural_join_sharp`/`_extrapolate_offset`——外延点法向 = 外延处导数法向，采样 0.5cm、搜索窗 4·max(sa)+20）——①的摆钩发生在远端，加大搜索窗后首个交点落在钩回前的近角段，故①在此成立（短窗 6cm 内无交的结论被长窗推翻）；无交回退切线 miter -> 阶梯。中间方案备查：「等曲率延续弯向角点转向 + 过定点 G1 单曲率弧重建过渡链」（圆心在起点切线法线上、ρ = |d|²/(2·d·n0)，绕行方向与行进切线点积判号）曾解决拉直/鼓包，后被纯多项式外延替换。
- **miter_limit 会把工艺指定尖角静默切成阶梯角**：默认 `miter_limit=1.5` 是防偶发尖刺的兜底（锐角 miter 长 = sa/sin(θ/2) 无界增长），但对「尖角即目标形态」的角（如前片裆尖内角 ≈75°、miter ≈1.64·sa）限长会静默回退阶梯角——毛样角部多出 outer = c+n_a·sa_a+n_b·sa_b 台阶点，呈「竖一刀+斜一刀」断点、不圆顺，且不报任何警告；金标若只用角度较缓的尺寸（miter <1.5·sa）根本测不到。凡工艺要求尖角跟随净样的角点，必须显式 `corner_treatments={(a,b): "miter"}` 绕过限长（键序对称；平行退化仍回退阶梯）；判别法：角部放大目检台阶，或比对毛样顶点与 `_miter_point(..., float("inf"))` 复算点。
- **围度辅助线 ∩ 外轮廓交点勿预设载体边（后片横裆刀口坑）**：横裆线高度常高于臀围外缝点（后片立裆 73 > 臀 72），侧缝交点落在髋腰弧（非大腿弧）、内侧交点落在后浪弧（非内缝弧）--对预设曲线 `point_at_y(y)` 越界直接抛 ValueError。凡"水平线与轮廓交点"类定位（刀口/marks 截断），一律按净边链折线采样整链求交取 min/max x（`back_piece_flow._h_cross_points`/`_clip_h_line` 口径），不指定载体边。
- **两线段求交的 Cramer 参数 s/u 极易写反（后片口袋刀口坑）**：解 `seg.a + f·s = p + e·u` 时 `s = (e×r)/det、u = (f×r)/det`（r = p − seg.a、det = e×f），把 s 写成 `(r×f)/det` 实为 −u--不抛错、返回一个看似合理的错误交点（口袋对位刀口曾飞到轮廓外 140cm，靠"刀口到毛样边最大距离"逐点检查才暴露）。新写线段/折线求交先过单测（水平线 × 竖直线交点 (0.5,0) 这类手算例）。
- **`PatternPiece` 按位置重建的坑再添一员 `drills`**：新增 `drills` 定位孔字段时同步透传了 `with_shrunk`/`with_gross`/`apply_shrinkage` 三处 + `piece_svg._bounds`（画布范围须含内部点，否则钻孔被裁出画布）--与 marks 同坑（见上），后续再加字段仍须逐处排查。
- **斜量测量线勿按水平线截断复制（后片毗围线坑）**：毗围线是外缝点->裆端的**斜量线**（d=0 直量也斜、d>0 下移更斜），内部线若按 `_clip_h_line(thigh_line.a.y)` 水平截断，d=0 时与横裆线同高**完全叠影**（用户目检"毗围线没画出来"即此，实为两线重合），且丢掉斜量方向。凡端点本就落在净边上的参考线（毗围线、贴袋顶线），一律 1:1 拷贝原线段、不走水平截断。连带测试教训：按"marks 是否水平"识别某类线的判据会被斜量线打破（省腿残段识别改按与源线段共线近距判）。
