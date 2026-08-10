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

```
YLPatternMaking/
├── .doc/                        # 打版理论文档（已存在）
├── src/
│   └── ylpattern/
│       ├── __init__.py
│       ├── params/
│       │   ├── measurements.py  # 成品尺寸模型
│       │   └── options.py       # 版型选项（Δ 预设、腰头类型…）
│       ├── geometry/
│       │   ├── point.py         # Point / Vector
│       │   ├── line.py          # 直线段、参考线
│       │   ├── bezier.py        # 三次贝塞尔（采样、求长、切线）
│       │   └── polygon.py       # 闭合轮廓、周长、面积、偏移
│       ├── formulas/            # 纯函数公式库（与文档章节对应）
│       │   ├── hip.py           # 臀围前后片分配、裆宽
│       │   ├── crotch.py        # 前后浪、立裆深、裆弯控制点
│       │   ├── waist.py         # 腰围分配、省道/吃势
│       │   └── leg.py           # 膝围、脚口、侧缝收放
│       ├── draft/               # 绘制基础设施
│       │   ├── elements.py      # NamedPoint / NamedLine / NamedCurve
│       │   ├── context.py       # DraftContext（步骤间元素存取）
│       │   ├── sheet.py         # DraftSheet（整张版的元素容器）
│       │   └── curves.py        # 公共弧线库（参数化，见 §5.3.1）
│       ├── steps/               # ★ 绘制步骤函数（核心）
│       │   ├── front_steps.py   #   前片：每个点/线一个函数
│       │   ├── back_steps.py    #   后片
│       │   └── waistband_steps.py
│       ├── flows/               # 流程编排
│       │   ├── runner.py        #   FlowRunner（按序执行/中断/单步）
│       │   ├── front_flow.py    #   前片步骤列表
│       │   └── back_flow.py     #   后片步骤列表
│       ├── cutter.py            # 裁切器：版 → 独立裁片
│       ├── pieces.py            # PatternPiece（净样/毛样/记号/局部坐标）
│       ├── exporters/
│       │   ├── svg.py           # SVG 分层输出
│       │   ├── dxf.py           # DXF（可选依赖 ezdxf）
│       │   └── report.py        # 尺寸报表
│       ├── validation.py        # 结构校验器
│       └── cli.py
├── examples/                    # 示例尺寸单 JSON
├── tests/
├── pyproject.toml
└── 打版流程.md
```

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

打版中的弧线（裆弯、腰口弧、侧缝臀段、脚口弧等）由**参数化的公共曲线函数**生成，集中在 `draft/curves.py`：

```python
# draft/curves.py —— 公共弧线库，全部以参数控制形状

def arc_through(end_a: Point, end_b: Point, *,
                bulge: float,        # 弧高（弦的垂直方向凸起量，cm）
                bulge_at: float = 0.5  # 弧顶位置（弦长比例 0~1）
                ) -> CubicBezier:
    """过两端点、按弧高控制的通用弧线 —— 适用于脚口弧、膝围过渡等浅弧。"""

def crotch_curve(start: Point, end: Point, *,
                 tangent_angle: float,  # 起点切线角（贴立裆线/斜线方向）
                 depth: float,          # 裆弯凹入深度（由 H/20、H/10 等推出）
                 tension: float = 1.0   # 曲率松紧
                 ) -> CubicBezier:
    """裆弯弧：一端切线约束 + 凹深控制。前后裆弯共用机制，
    但凹深、切线角参数各自独立传入。"""

def hip_side_curve(...) -> CubicBezier:
    """侧缝臀段弧：过腰点/臀点/膝点，弧度可调。"""
```

使用规则：

- **能用公共函数就用**：形状仅由参数区分（弧高、切线角、凹深、曲率）的弧线，一律调用公共库，保证同类弧线画法统一、调版时只调参数；
- **共用不强制**：裁片特有、参数化公共函数表达不了的曲线（如后片配合后翘的复合裆弯、Yoke 分割线弧），允许步骤函数**自行构造贝塞尔控制点**并上版，只需在 docstring 写明控制点的确定依据；
- **判断标准**：一条弧线的画法被两处以上使用，或预期会在调版中反复调参 → 收进公共库；只出现一次且形状特殊 → 留在步骤函数里。后续若出现第二处使用，再重构上提；
- 公共曲线函数的每个参数都必须是**有物理意义的量**（cm、角度、弦长比例），禁止不可解释的纯形状魔法数。

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

前后片全部绘制完成后，Cutter 把每个裁片从版上独立裁出：

```
DraftSheet（所有元素）
     │  按裁片定义表逐一圈取
     ▼
裁片定义："前片" = [腰点→臀点→裆点→脚口内点→脚口外点] 元素名列表 + 曲线段
     │
     ▼
① 提取轮廓点列 → 闭合 Polygon（净样）
② 校验闭合性与自相交
③ 平移到裁片局部坐标系（左下角为原点）
④ 平行偏移生成毛样（缝份）
⑤ 收集落在轮廓内部/边界上的记号（对位点、丝缕线）
     ▼
PatternPiece × N（前片、后片、腰头……各自独立）
```

- 裁片定义也是**声明式**的（元素名列表），新增裁片 = 加一条定义，不改机制；
- 弯腰头按打版流程"注意点"处理：与前片一体绘制，裁切阶段沿分割线裁成两个独立裁片；直腰头则绘制时已扣除腰头宽，直接裁出。

### 5.6 裁片 `pieces.py`

```python
@dataclass
class PatternPiece:
    name: str                    # "front" / "back" / "waistband"
    outline: Polygon             # 净样轮廓（局部坐标）
    notches: list[Notch]         # 对位记号（膝围、臀围对位点）
    grainline: LineSegment       # 丝缕线
    annotations: list[Annotation]
    def with_seam_allowance(self, width: float) -> Polygon: ...
```

### 5.7 输出层 `exporters/`

**SVG**（调版预览）—— 分图层，可用开关控制显示：

| 图层 | 内容 |
| :--- | :--- |
| `reference` | 参考线（灰虚线）—— 整张版的绘制痕迹 |
| `elements` | 关键点与控制点（可选显示名称标注） |
| `net` | 净样轮廓（黑实线） |
| `seam` | 毛样轮廓（蓝实线） |
| `annotation` | 尺寸标注、裁片名 |

两种模式：**版式输出**（整张 DraftSheet，带全部绘制过程）和**裁片输出**（每个裁片独立排列，生产视角）。

**DXF**（生产）：每裁片一个 BLOCK，净样/毛样分 LAYER，记号转 POINT/线。

**报表**：全部中间计算尺寸 + trace 记录（即 `ylpattern draft --report` 输出），供打版师核对。

### 5.8 校验器 `validation.py`

对应 [前后片臀围推导.md](前后片臀围推导.md) §五，转为程序化校验：

| 校验项 | 规则 | 级别 |
| :--- | :--- | :--- |
| 臀围闭合 | `2×(H前+H后) = H ± 0.05` | ERROR |
| 前后侧缝等长 | 长度差 ≤ 0.3 cm | WARNING |
| 前后内缝等长 | 长度差 ≤ 0.3 cm | WARNING |
| 裆弯拼接顺滑 | 前后裆弯裆点处切线夹角 ≥ 170° | WARNING |
| 非负性 | 所有宽度尺寸 > 0 | ERROR |
| 轮廓闭合 | 裁片轮廓首尾闭合、无自交 | ERROR |

校验失败**告警不中断**（打版师可能故意违反某条规则），结果附在报表中。

---

## 六、典型使用流程

```bash
# 1. 调版：只画到基础框架，看五条参考线和大矩形
ylpattern draft --size size.toml --until draw_inner_seam_refline --svg out/frame.svg

# 2. 全流程绘制，输出整张版（带绘制痕迹）+ 追踪记录
ylpattern draft --size size.toml --svg out/sheet.svg --trace out/trace.txt

# 3. 裁片输出（M3+）：逐个裁出，SVG 预览 + DXF 生产文件
ylpattern cut --size size.toml --svg out/pieces.svg --dxf out/pieces.dxf \
    --report out/report.txt
```

尺寸单 `size.toml`（TOML 格式，支持 `#` 注释）：

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

局部 → 全局：`o_pt + x_dir.scale(x) + y_dir.scale(y)`（`x_dir = y_dir.perpendicular()`）。**看步骤代码先认局部框**，否则坐标会读反。

### 10.2 几何 API 速查（geometry/）

- `Point(x,y)` 不可变：`+Vector`、`-Point → Vector`、`distance_to`、`lerp`、`midpoint`。
- `Vector(dx,dy)`：`length`、`normalized()`、`perpendicular()`（**逆时针 90° 并归一化**，法向方向以此为准）、`scale(k)`、`rotate(deg)`。
- `LineSegment(a,b)`：`length` 是**属性**（不是方法！）、`direction`（a→b 单位向量）、`horizontal`/`vertical` 工厂。
- `CubicBezier(p0,p1,p2,p3)`：`point_at(t)`、`tangent_at(t)`（未归一化）、`length()`（折线近似，**是方法**）、`t_at_length(s)`/`point_at_length(s)`（按弧长定位）、`t_at_y(y)`/`point_at_y(y)`（按高度定位，要求 y 单调）、`split(t)`（de Casteljau，返回两段）、`angle_with(other)`（拼接切线夹角，180°=顺滑）。
- 90° 圆角贝塞尔逼近常数 `4/3×tan(§rad)≈0.5523`（`front_fly_steps._QUARTER_K`），柄长 = 常数 × R。
- `draft/curves.py` 公共弧线库：`arc_through`（弧高式）、`sag_curve`（弧顶精确 sag）、`crotch_curve`（切线+凹深）、`front_rise`/`back_rise`（前/后浪复合线按总浪长闭合反推顶点）、`point_along_chain`（沿"直线+曲线"复合链量取弧长，量腰头宽/开深等）、`bezier_subrange`（取曲线参数子段）、`foot_on_bezier`（点在曲线上的法足/正交投影，垂直投射定位——弯腰头省位延长至上腰头线等）、`edge_geom`（按 spec 分派 line/arc/bezier 边形态，袋布节点链/小表袋净样逐边共用）。

### 10.3 role 与 SVG 渲染（exporters/svg.py）

- `NamedLine.role` / `NamedCurve.role`：`"struct"`（结构线，实线深色 #2c3e50）/ `"ref"`（参考线，灰虚线 #999 dasharray）。`NamedLine` 默认 `ref`，`NamedCurve` 默认 `struct`。
- SVG 图层顺序（后绘盖上）：`reference`(ref 线) → `struct`(struct 线) → `curves`(全部曲线，按 role 分 `.curve` 实线 / `.curveref` 虚线) → `elements`(点)。要让某条**曲线**画虚线，给 `add_curve(..., role="ref")`（曲线默认 struct 实线，现已支持 role 生效）。
- 注意：§5.7 的图层表（net/seam/annotation…）与目录里的 `cutter.py`/`pieces.py`/`validation.py`/`dxf.py` 是**设计期设想，尚未实现**；实际图层与已实现模块见上。

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

### 10.6 当前实现状态（已程序化）

已实现：前片（`front_steps`）、后片（`back_steps`）、前口袋（`front_pocket_steps`，含弯腰头+有省量时 P1/P1′ 延长至上腰头线）、袋布（`front_pouch_steps`）、前贴袋、小表袋、门襟（`front_fly_steps`，连裁/独立两形态）、后机头/育克（`back_yoke_steps`，弯/直腰头两端点弧长量取 + 下口线 N 点分段拓扑）、毗围闭环（`flows/closure.py`）。只有 `.doc/` 推导文档、尚未程序化：后贴袋等（在建）。尚未实现：裁切层（cutter/pieces）、DXF 导出、结构校验器。
