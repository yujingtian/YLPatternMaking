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

`geometry/`（Point/Vector/LineSegment/CubicBezier）与 `draft/curves.py` 的签名、行为**以代码为准**，docstring 已标注易踩坑点（`LineSegment.length` 是属性、`CubicBezier.length()` 是方法、`Vector.perpendicular()` 逆时针 90° 归一化、`tangent_at` 未归一化、`t_at_y` 要求 y 单调）。文档不重复维护，避免代码-文档双线失步；需要时直接读对应模块。

### 10.3 role 与 SVG 渲染（exporters/svg.py）

- `NamedLine.role` / `NamedCurve.role`：`"struct"`（结构线，实线深色 #2c3e50）/ `"ref"`（参考线，灰虚线 #999 dasharray）。`NamedLine` 默认 `ref`，`NamedCurve` 默认 `struct`。
- SVG 图层顺序（后绘盖上）：`reference`(ref 线) → `struct`(struct 线) → `curves`(全部曲线，按 role 分 `.curve` 实线 / `.curveref` 虚线) → `elements`(点)。要让某条**曲线**画虚线，给 `add_curve(..., role="ref")`（曲线默认 struct 实线，现已支持 role 生效）。
- 注意：§5.7 的图层表（net/seam/annotation…）原为设计期设想；`cutter.py`/`pieces.py` 已为腰头裁片落地（独立 SVG），`validation.py`/`dxf.py` 仍尚未实现。
- 独立裁片 SVG（`exporters/piece_svg.py`）：裁片局部坐标 **Y 向下**，渲染时**不翻转**（仅缩放平移），区别于整版 `svg.py`（版坐标 Y 向上、渲染翻转）。图层：gross 毛样（实线）/ shrunk_net 含缩水净样（虚线）/ net 净样（淡虚线）/ notches（红）/ grain 丝缕线（蓝）。

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

### 10.6 当前实现状态（已程序化）

已实现：前片（`front_steps`）、后片（`back_steps`）、前口袋 + 袋贴（`front_pocket_steps`，含弯腰头+有省量时 P1/P1′ 延长至上腰头线；袋贴 `draw_front_pocket_facing` 详见下文）、袋布（`front_pouch_steps`）、前贴袋、小表袋、门襟（`front_fly_steps`，连裁/独立两形态）、后机头/育克（`back_yoke_steps`，弯/直腰头两端点弧长量取 + 下口线 N 点分段拓扑）、后贴袋（`back_patch_steps`，育克底线∩后浪线定位 + 局部 u-v 框四形态 + 仿射旋转）、毗围闭环（`flows/closure.py`）、腰头裁片（`steps/waistband_steps` + `flows/waistband_flow` + 裁切层 `pieces`/`cutter` + `exporters/piece_svg`，腰头裁片.md：直/弯腰头 × 有/无省，净样 -> 缩水 -> 缝边独立 SVG；`build_waistband(main_ctx)` 从整版提取前后腰弧净长代数求和）。裁切层（`pieces.PatternPiece` 三态净/缩水/毛 + `cutter.apply_shrinkage`/`add_seam_allowance`）已为腰头落地，前/后片裁切待后续。尚未实现：DXF 导出、结构校验器。

前浪裆弯弧度已可调：`PatternOptions.front_rise_handle_ratio`（默认 1/3，k1=k2=|BC|×本值，前浪绘制.md §4），由 `draw_front_rise` 传入 `curves.front_rise`；与后浪 `back_rise_alpha`/`back_rise_beta` 双参数不同--前浪按文档用单一对称比例，后浪因大裆弯更深需独立 α/β。

前口袋袋贴（facing）已程序化：`draw_front_pocket_facing`（`front_pocket_steps`，前口袋绘制.md §三.3.(1)）。
1. 定位两端点（支持非等距独立宽度）：腰头顶点 P_fw（有省自 P1′、无省自 P1 沿腰弧量取 w_waist=front_pocket_facing_width，默认 3.5）；侧缝顶点 P_fs（自 P2 沿外缝弧向下量取 w_side=front_pocket_facing_side_w or w_waist，推荐 6.0 防露白）。
2. 内边 L_inner 支持三模式（front_pocket_facing_mode）：
   - "tangent"（打版推荐，默认）：两端垂直切线贝塞尔（P_fw 端 ⟂ 腰弧、P_fs 端 ⟂ 外缝弧），由切线柄长 front_pocket_facing_h1/h2 控制下垂与向内进深（h1/h2 为控制柄距离/拉力，而非直线下垂长度）；
   - "offset"：基准线 C_ref 控制点域法向偏置（折角链沿弦法向平移），端点锁 P_fw/P_fs；
   - "bulge"：浅弧式，由 bulge/bulge_at 控制。
3. 闭合边为腰弧/外缝弧子段（先画后裁，不作布尔裁减）。
选项字段：front_pocket_facing / front_pocket_facing_mode / front_pocket_facing_width / front_pocket_facing_side_w / front_pocket_facing_h1 / front_pocket_facing_h2 / front_pocket_facing_bulge / front_pocket_facing_bulge_at（新增字段须同步 api.run() 的参数与 PatternOptions 构造透传）。

前小表袋（watch pocket）已程序化：`draw_front_watch_pocket`（`front_pocket_steps`，小表袋绘制.md §2~§4）。
1. 两种生成模式（watch_pocket_mode）：
   - "facing_intersect"（袋贴相交延伸模式）：袋口按 watch_pocket_width 定宽，左右侧边向下延伸（结合 watch_pocket_taper 内收倾斜），调 `curves.ray_intersect_bezier` 求得与袋贴内边 `front.pocket_facing_inner` 的两个交点及参数 [t1, t2]；底边取袋贴内边精确子段（`curves.bezier_subrange`）顺接闭合；强制依赖 `front_pocket_facing=True`；
   - "custom"（独立全自定义模式，默认）：自定义净形锚点列表 watch_pocket_points（≥3 个）+ 逐边形态列表 watch_pocket_edges（line / arc / bezier），支持 watch_pocket_rotate_deg 绕参考点旋转。
2. 基准点 O = 前口袋侧缝腰点（弯腰头取下侧缝腰点 B'，直腰头取腰外缝顶点 B，经 effective_waist 同步）。
选项字段：watch_pocket / watch_pocket_mode / watch_pocket_width / watch_pocket_taper / watch_pocket_offset_from_top / watch_pocket_offset_from_side / watch_pocket_rotate_deg / watch_pocket_points / watch_pocket_edges。

腰头裁片已程序化：`build_waistband(main_ctx)`（`flows/waistband_flow`，腰头裁片.md §三~§五；自含裁片，非 FlowRunner 编排，同 closure.py 口径）。
1. 净长代数求和（§三）：`extract_waistband_spec` 读上腰弧 `front.waistline_arc`（t=0 侧缝->t=1 前中）/ `back.waistline_arc`（t=0 后中->t=1 侧缝），减省宽：后省 = `back.dart{i}_leg_inner` 端点 p_in 投影到后腰弧的弧长（`_arc_length_of_point` 采样最近 t + 三分搜索）；前省 = `front_pocket_p1_dist`。直/弯腰头统一读上腰弧（弯腰头下腰弧为贴身边，差 <0.5cm，代数求和容忍）。
2. 净样绘制（`steps/waistband_steps`，独立 DraftSheet 局部坐标 Y 向下）：直腰头 = 矩形 L_half×W；弯腰头下口线 = `curves.waistband_curve(L_half, spec.computed_drop)`（P1=(X/3,0) 后中水平利镜像/P2=(2X/3,−drop/3)、P3=(X,−drop) 前中自然斜出成**向下凹 ∪** 抛物线弧（整片沿后中镜像后后中下凹、贴臀侧外凸、贴腰侧内收；早期向上凸 ∩ 致下口内收不合体，故翻向），消除两端皆水平所致 S 型畸变；二分求 X 闭环 length 精确），上口线 = 下口沿**端点法向**偏移 W（`_top_geom`：P0/P1 按后中法向、P2/P3 按前中法向偏移，端点切线 (P1−P0)/(P3−P2) 逐点保留 → 上下口两端切线严格平行；中段为真法向 offset 的贝塞尔近似。直腰头两端法向皆 (0,−1) 退化为整体竖直平移 W=原行为）。full_piece 时后中 x=0 镜像 + 左端搭门：搭门 `_end_tangent` 取左前中处下口切线、沿切线外延 fly_extension（与下口顺势顺滑 C1 相接、弯腰头随弧端斜出）；两端封边向量 = 上下口同侧端点之差，因上口沿法向偏移故天然落端点法向 → 与上下口切线/搭门成直角（四处端点为直角）。drop 来源：用户 `waistband_front_drop` 手动覆盖；否则 `extract_waistband_spec` 调 `_auto_drop(front_arc, back_arc, hip_front, hip_back)` 按真实侧缝线夹角自动推算（§四.分支B；读 `front/back.hip_outseam_point` 取侧缝腰点 B 至臀点 H 的真实侧缝线倾角，以 B 为圆心旋转前片使前后侧缝线重合，旋转后前中 A_front 相对后中 A_back 的纵向高度差即 drop。主版坐标系 Y 向上，A_back.y 减 A_front_joined.y 为正即前中更低；该正 drop 喂入 waistband_curve 的 −drop 公式得向下凹 ∪，凸向与测量正负号解耦。旧法取腰弧端点切线对齐、强制切线连续会向上过旋抵消落差，side_rise 与 curve_sag 同存时坍塌为约 0；真实侧缝线为结构稳定特征，不受腰弧塑形影响，实测两开关增删变化在 0.1cm 内）；直腰头=0。
3. 裁切三段（`cutter`）：`apply_shrinkage`（x·(1+warp)、y·(1+weft)，保持贝塞尔性）-> `add_seam_allowance`（四边独立缝份沿**外法向**偏移：曲线逐点真法向 offset（`_offset_edge_points`，tangent.perpendicular·amt）、直线整体平移；相邻异名边角点取两偏移边切线延伸交点 miter 连接（`_miter_point`），切线平行回退阶梯角，同名边平滑相接、后中折线不外扩；缝份不叠加缩水）。零长退化边（`fly_extension=0` 致 `wb.top_fly`/`wb.bottom_fly` 首尾重合、无切线）在 `build_waistband` 装配 net_edges 时即按 `cutter.edge_length`（`LineSegment.length` 属性 / `CubicBezier.length()` 方法，API 不一）滤除，cutter `_offset_edge_points` 另对零长直线防御性返回空，避免外法向归一化触发「零向量无法归一化」）。`PatternPiece` 三态：net_edges / shrunk_edges / gross_polygon。
4. 刀口（§三.2）：侧缝=L_back、后省/前省按弧长，full_piece 左右镜像各一；丝缕线沿长向（经向）。
选项字段：waistband_front_drop（None=按真实侧缝线夹角自动推算 `computed_drop`、填值手动覆盖；正数 drop=下口线向下凹 ∪，负数被 options 层与 curves 层双重校验拒绝、若强放行因公式为 −drop 反得 ∩，**勿传负**。§四.分支B。**勿与 `fc_drop` 混淆**：`fc_drop` 是裤身前腰头绘制的前中下落量 d（`formulas.waist.waistline_horizontal_span`，前腰头绘制推导.md），塑造裤身腰围线；`waistband_front_drop` 是腰头裁片自身下口线的弯曲度，二者几何来源不同，曾因混淆导致 auto_drop 取错基准）/ waistband_fly_extension / waistband_full_piece / shrinkage_warp / shrinkage_weft / waistband_seam_allowances（WaistbandSeamAllowances：top/bottom/left_end/right_end，TOML `[options.waistband_seam_allowances]` 子表，须置 [options] 末尾避免吸收后续键）。输出：`--waistband-svg` 旗标 / `api.run(waistband_svg=...)`。
