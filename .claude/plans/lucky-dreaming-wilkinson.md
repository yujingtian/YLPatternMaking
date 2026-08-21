# 推码（多尺码放码）实现方案（v1 核心）

> 范围口径：v1 = 尺码表 + 逐码重打版 + 多码单文件 DXF；**层 3 放码点云与反测
> 读取器移二期**（已定设计存档见文末「二期预留」，均为纯增量、后补零改动）。
>
> 状态：**已实现**（2026-08-21，步 1~5 全部落地，651 测试全绿；8 码示例实跑
> 88 块 = 8×11 片、Sample Size: 30。剩余：ET08 人工开箱验收）。

## Context

系统已完成单码打版 → AAMA 裁片 DXF（ET08 可识码、底部尺码栏可显示 "30"）。工厂生产需要**推码**：一份订单录多个尺码（如 28~38），一次生成全部尺码裁片，导入 ET08 后版师可切换尺码查看。

架构路线（与用户多轮讨论已定，不再重议）：

- **尺码表进、逐码参数化重打版**——不做点位移生成几何；每码用该码 Measurements 完整重跑整版（毗围闭环逐码独立收敛），浪长闭合等结构不变量自动保持。
- **多码单文件 DXF，共 AAMA 数字图层**——绝不建每码图层（ET08 图层校验黑屏）。分码靠既有机制：块名 `{片名}-{尺码}` + 块内 `Size:` 标签 + 模型空间 `Sample Size:` 全局头（=基码）。

用户已拍板：①尺码表**两种形态都支持**（逐码显式 + 基码分段档差展开，显式条目覆盖展开值）；②范围**先做多码核心**——层 3 点云与反测读取器移二期（设计存档见文末）。

## 已核实关键事实

- api.py:798-902 / cli.py:43-186：裁片收集双份平行实现（顺序 waistband→yoke→front_pocket→front_pouch→front_fly 三元组→watch_pocket→back_patch→front_piece→back_piece；api 跳过提示仅 pieces_dxf 时打 stdout，cli 收集即打 stderr；cli 另有 8 组 `--until` elif 警告）。
- `run_with_thigh_closure(m, o, *, until, trace, ...)`（flows/closure.py:88-92）：毗围开启时迭代整版重跑至收敛，**不抛错中断**，最坏带残余 ΔW 出片。
- params 风格：frozen dataclass + `from_file`（load_size_file 返回原始 dict，`_` 前缀键忽略）+ `__post_init__` 中文 ValueError；Measurements 8 字段含交叉校验（hip>waist、back_rise>front_rise、outseam>front_rise）。
- piece_dxf.py：`_block_name(piece_name, size, used)` 已带尺码；`_add_doc_header` Sample Size 行；`_with_notch_vertices` 刀口点共线插顶点；`_strip_r12_compat` 剔 TABLES（层名类断言须按实体层名，非层表）。
- ET08 参考件（逆向两份大货件）：Category 码内序号 0 起；Sample Size=基码。
- 金标数据源：.doc/臀围线推导.md §四 W26~W34 表——腰 66/71/76/81/86（档差 2.5/码）、臀 88/92/96/100/104（档差 2.0/码）。
- .doc/python工程设计.md §1.3(:56) "自动放码推板（预留，二期）"需改；无 test_api/test_cli（测试直连 FlowRunner+build_*）。

## 实现步骤（测试先行，每步独立可验证）

### 步 1：`src/ylpattern/params/sizerun.py` + `tests/test_sizerun.py`

纯参数层（只 import 同层 measurements/options/sizefile，**不 import formulas**——档差累加是参数表展开非打版公式）。

```python
MEASURE_KEYS = ("waist", "hip", "knee", "hem", "front_rise",
                "back_rise", "outseam", "thigh")

@dataclass(frozen=True)
class SizeBand:          # 档差段：sizes=段内码序（TOML 声明序），8 字段=相邻码步进 cm
    sizes: tuple[str, ...]; waist: float = 0.0; ... thigh: float = 0.0

@dataclass(frozen=True)
class SizeEntry:  label: str; measurements: Measurements

@dataclass(frozen=True)
class SizeRun:
    base: str                       # 基码标签
    style_name: str = "noname"      # 订单号，须 ASCII
    entries: tuple[SizeEntry, ...] = ()   # 按码序
    # labels 属性 / measurements(label) / base_measurements()
    # options_for(label, o) = dataclasses.replace(o, size_label=label)
    @classmethod from_spec(cls, base_m: Measurements, raw: dict, *, fallback_base="-")
    @classmethod from_file(cls, path)

def load_size_run(path: str) -> SizeRun | None   # 无 [size_run] 段返回 None（cli/api 探测口）
```

展开算法：
- **码序 order**：显式 `size_run.order` > 自动（band.sizes 声明序串联 + 显式键序追加，去重保首现）。字母码/"36L" 无需数值解析，**永不做数值猜测**。
- **base**：`size_run.base` > fallback_base（options.size_label≠"-"）> order[0]；不在 order 抛错。
- **步进归属**：码 i→i+1 取 **i+1 所属 band** 档差（"32→33 跨段取 33 所在大码段"=工厂"33 码起放大档"）；无 band 覆盖区间步进 0（该码须显式补全）。
- **双向累加**：自基码向前 `v[i+1]=v[i]+step`、向后 `v[i-1]=v[i]-step`。
- **显式覆盖**：`[size_run.sizes.X]` 子集键覆盖展开值（单码特调）；全 8 键无 band = 纯显式形态。
- **thigh 特例**：基码 thigh=0 时忽略一切 thigh 步进（全码 0），显式 thigh>0 可单码启用。
- 每码构造 Measurements **复用其全部交叉校验**，失败消息带码标签。

校验（顺序 if + 中文 ValueError 含实际值）：band.sizes 非空/跨段不重复；order 覆盖全集；步进与显式键 ∈ MEASURE_KEYS；base ∈ order；style_name ASCII；无来源码报缺参清单。

TOML 示例（新文件 `examples/size_female_zhitong_run.toml` = 现有直筒尺寸单全文 + 文末追加）：

```toml
[size_run]
base  = "30"                  # 缺省回退 [options] size_label
style = "YL-A2708-F"          # 订单号（ASCII，进 DXF 头两行）
order = ["29", "30", "31", "32", "33", "34", "36", "38"]  # 可省略

[[size_run.band]]             # 29-32 小码段
sizes = ["29", "30", "31", "32"]
waist = 2.5; hip = 2.5; knee = 1.3; hem = 1.0
front_rise = 0.3; back_rise = 0.5; outseam = 1.2; thigh = 1.3

[[size_run.band]]             # 33-38 大码段（32→33 取本段）
sizes = ["33", "34", "36", "38"]
waist = 3.0; hip = 3.0; knee = 1.5; hem = 1.2
front_rise = 0.4; back_rise = 0.6; outseam = 1.5

[size_run.sizes.31]           # 逐码显式覆盖（可选，优先于展开）
waist = 80.2; front_rise = 29.4
```

（TOML 不支持行内多键分号——实现时逐键一行，示例为紧凑写法。）

测试：① 展开金标：基码 W30(76/96) 单段档差腰 2.5/臀 2.0 → W26~W34 五码与 §四表**逐一相等**；② 跨段步进取 i+1 所属段、反向累加一致；③ 显式覆盖优先；④ 纯显式形态；⑤ 字母码声明序；⑥ 错误族（重复码/order 缺码/base 不在码序/展开后 hip≤waist 含码标签/style 非 ASCII）；⑦ options_for 仅改 size_label；⑧ load_size_run 无段返回 None。

### 步 2：`src/ylpattern/flows/collect.py` + `tests/test_collect.py`；api/cli 换用

```python
def collect_pieces(ctx: DraftContext) -> tuple[list[PatternPiece], list[str]]:
    """按固定顺序构建全部已开启裁片，返回 (裁片列表, 跳过说明列表)。
    开关判定读 ctx.options（与原分支一致）；front_pocket 按 facing/patch 派发；
    门襟双排关闭只回单片。不写任何文件（不 import exporters）。"""
```

- api.py:798-902 替换：`pieces, skips = collect_pieces(ctx)`；skips 仅在 pieces_dxf 时打 stdout（现状口径）；SVG 按片名→路径映射 `{"waistband": waistband_svg, "back_yoke": yoke_svg, "front_facing"/"front_patch": front_pocket_svg, "front_pouch": front_pouch_svg, "front_fly_single"/"front_fly_double": 对应 svg, "watch_pocket": ..., "back_patch": ..., "front_piece": ..., "back_piece": ...}` 非空即写。
- cli.py:43-186 同样替换；skips 打 stderr；8 组 `--until` elif 警告收敛为外层一条。
- 接受的行为差异（记录于 docstring）：原"仅设某片 SVG 时只 build 该片"的惰性 → 全收集（开销相对整版可忽略，裁片集合一致）。
- **验证 = 现有全部测试（含 test_piece_dxf.py 341 行）不动全绿**，即重构等价性证明。

新测试：全开关矩阵下片名有序金标；关闭项进 skips 不构建；双排关闭只回单片。

### 步 3：`exporters/piece_dxf.py` 多码渲染 + `tests/test_size_run_dxf.py`

```python
BAND_GAP_CM = 8.0                     # 码带间距（大于片间距形成分带）

def render_size_run_dxf(groups, *, sample_size, tolerance_cm=...,
                        gap_cm=PIECE_GAP_CM, band_gap_cm=BAND_GAP_CM,
                        qty=1, style_name="noname"):
    """groups = [(码标签, 该码裁片列表), ...]（码序）。每码一条摆放带：
    带内 _layout shelf 装箱（行宽 200cm），带沿 Y 叠放、间距 band_gap_cm，
    首带贴原点。块名 _block_name(片名, 码) 全沿用；Category 码内 0 起；
    Size 标签 = 本码；len(groups)>1 时每带左上码标 TEXT（层 1，ASCII，
    如 "SIZE 30"，人读辅助）。_add_doc_header(msp, sample_size, ...)。"""

def write_size_run_dxf(groups, path, *, sample_size, **同参)

def render_pieces_dxf(pieces, *, size="-", qty=1, style_name="noname", ...):
    return render_size_run_dxf([(size, pieces)], sample_size=size, ...)  # 单码退化
```

- `set_extents` 已按 INSERT 展开（_dxf_base._collect_bbox 支持 INSERT），多带无需改。
- 块名长度核查：front_fly_double(17)+1+码(≤4)=22 ≤ 31 ✓。
- 测试：① 块数=Σ各码片数、块名 `{片名}-{码}` 全命中；② Sample Size=基码；③ Category 码内 0 起重置；④ 带间不重叠（码 A maxY+8cm ≤ 码 B minY）、首带贴原点；⑤ 每带一条码标 TEXT；⑥ **现有 test_piece_dxf.py 341 行原样全绿**（单码退化等价回归）；⑦ 写盘回读 + 999 头 + 无 group5 + $EXTMIN 覆盖全带。

### 步 4：`api.run_size_run` + cli 探测 + examples + 端到端测试

```python
# api.py 文末（文件驱动，不复制 180 kwargs）
def run_size_run(size_file: str, *, pieces_dxf: str,
                 svg: str | None = None, trace: str | None = None,
                 report: str | None = None) -> dict[str, DraftContext]:
    """load_size_run（None → ValueError 提示走 run）→ 按码序逐码：
    m_s=run.measurements(码)；o_s=replace(o, size_label=码)
    → run_with_thigh_closure（毗围逐码独立收敛）→ collect_pieces 收
    groups；末尾 write_size_run_dxf(groups, pieces_dxf,
    sample_size=run.base, style_name=run.style_name)。"""
```

- 输出口径 v1：svg/trace/report **只出基码**（整版是人工调版工具，版师只调基码；看任一单码细版 = 复制尺寸单删 [size_run] 段退化单码模式，无信息丢失）。
- 毗围不收敛：**报告而非失败**——汇总打印每码一行「码/毗围残余 ΔW/裁片数」（从 closure 返回 trace 文本解析末轮 ΔW，私有 `_last_residual(trace_text)`，零核心侵入）。
- cli `_cmd_draft` 开头 `run_spec = load_size_run(args.size)`：None 走现有单码路径；非 None → `--until` 与缺 `--pieces-dxf` 报错退出 2；其余逐片 --xxx-svg 忽略并 stderr 提示。`--size` 帮助文本补一句。
- 测试：examples 多码 TOML → run_size_run 出文件、返回码序 ctx；无 [size_run] 报错信息正确。
- **人工验收：命令行实跑，ET08 开箱验证分码/尺码栏。**

### 步 5：文档收尾

- `.doc/python工程设计.md`：§1.3 删"自动放码推板（预留，二期）"改为「多码推码已实现（逐码重打版），层 3 点云/反测读取器仍预留二期」；§10.6 增补（SizeRun schema 与展开算法要点、collect、多码 DXF 结构——原步 0 独立文档取消，内容并入此处，口径同现有 DXF 段落风格）。
- `CLAUDE.md`：常用命令加多码 draft 一行示例（无新分层节点）。

## 风险与规避

1. **分层红线**：sizerun 不 import formulas（展开是算术非公式）；collect 不 import exporters（不写文件）。
2. **单码回归**：render_pieces_dxf 变 wrapper 是最大回归面——341 行金标测试不动全绿即等价证明，断言有变即回退设计。
3. **毗围逐码不收敛**（极端档差触发裆尖钳制）：报告不中断；错误档差在 SizeRun 构造期被 Measurements 交叉校验提前拦截（消息带码标签）。
4. **R12 清洗剔层表**：层名类断言（码标 TEXT 层 1 等）按实体层名非层表（老 CAD 按数字层名直认）。
5. **DXF 体积**：无层 3 点云，10 码 × 9 片纯块实体数百 KB 量级，可接受。

## 验证

1. `python -m pytest tests/ -q` 全绿（步 2 后现有 341 行 DXF 金标不动全绿 = 重构等价；各步新增金标见上）。
2. 步 4 端到端：`python -m ylpattern.cli draft --size examples/size_female_zhitong_run.toml --pieces-dxf out/pieces_run.dxf --svg out/base.svg` → out/pieces_run.dxf 含 8 码 × 9 片块、Sample Size: 30。
3. **ET08 人工验收**：导入 pieces_run.dxf，底部尺码栏非 "*"、可切换各码。

---

## 二期预留（本次不做；设计已定，补回零改动）

### A. 层 3 放码点云（版师在 ET 选点调码）

- 口径（ET08 参考件逆向）：每片毛样 CUT 折线顶点逐点层 3 POINT（约 200 点/片），版师在 ET 选点位移调码的锚点。**只覆盖 CUT 顶点**（不覆盖层 8 内线顶点）；10 码×9 片×150~250 点 ≈ 1~2MB 可接受，`grade_points=False` 兜底超大订单；单码同样默认开（ET08 单码回调码场景）。
- 实现：`_LAYER_MAP` 增 `"GRADE": "3"`、`_LAYERS` 增 `"3": (3, "CONTINUOUS")`；共享 `_cut_vertex_ring(piece, to_mm)`（`_with_notch_vertices` 后 mm 域去重：连续重复+闭合首尾，eps 1e-6mm）——层 1 POLYLINE 与层 3 POINT 消费同一列表，点数==折线顶点数；每顶点 `add_point((x, y), layer="3")` 无组码 30/50（刀口层 4 专属）。
- **硬前置：cutter 毛样环跨码同构契约（原步 2.5，2026-08-20 双实测证实必须）**——"各码顶点同序对应"不自动成立：① 我们自己的毛样环顶点跨码漂移（front_piece [270,270,269,269,269]、back_piece [269,269,270,269,269]；漂移源=`_natural_join_sharp` 发射数 i+j+2 随外延交点落段变、miter_limit 84° 分支、mirror X 有无、反射角裁剪数；环上另有 0.0~0.05cm 微段，`poly[-1] != p` 精确浮点去重漏网）；② ET 自身放码每码重采样（同片 30/31/40 码层 1 顶点 87/81/45、层 3 点 1360→1376），重构即回弯曲/圆角 → **ET 端只逐点调码，禁自动放码/曲线重构**。修法原则：**位置在毛样、结构由净样**——发射数量/槽位由净样拓扑唯一决定（natural join 固定 N 发射、角部分支配置化、反射角裁剪槽位化、微段槽位规则消除），只动数量不动点位公式（基码毛样与现状逐点一致）；配 `test_gross_ring_structure` 金标（方案档差 5 码逐段计数相等、最小段 ≥0.1cm）+ 导出前跨码逐段计数断言（不等 ValueError 带片名与两码标签）。详见 memory「推码层3点云与cutter计数漂移」。
- 测试：层 3 计数=Σ各片 CUT 顶点数且与层 1 顶点集逐点相等（按实体层名断言）；跨码同构断言；grade_points=False 层 3 为空。

### B. 反测读取器（多码 DXF → 8 核心参数 → 尺码表 TOML 回流）

- 位置：新子包 `src/ylpattern/importers/`（与 exporters 平行的输入侧工具层，不进核心打版链；`cli → importers → geometry/params`；ezdxf lazy import + RuntimeError 指引，不跨包 import exporters 私有 _dxf_base）；落地时 CLAUDE.md 分层架构与 §10.6 需同步补节点。
- 识别三级回退（method 字段标注置信来源）：① 块内 5 行魔法标签（我们与 ET08 产物都带，跨软件存活率最高）→ ② 块名 `{片名}-{码}` 后缀切分（片名 ∈ 已知 11 片名集）→ ③ 启发式（INSERT 按 Y 聚类成带=码；带内层 1 闭合折线面积最大两块为前后片、大者 back；细长条长宽比>6 排除腰头）。
- 8 参数测量（量层 8 净样线，与缝份无关；高度线定位优先前片层 8 marks 辅助线 > 启发式比例 `HEURISTIC = {"hip_rise_ratio": 0.10, "knee_pos": 0.55, "thigh_offset": 2.54}`，裆上高 H/10 口径）：

  | 参数 | 算法 |
  |---|---|
  | waist | 有腰头片=净长；无=2×(前+后腰口弧长) |
  | hip/knee/hem/thigh | 对应高度截净轮廓 2×(前截宽+后截宽) |
  | front_rise/back_rise | 前后浪净弧长；直腰头件另加腰头宽（rise_on_pattern 口径镜像） |
  | outseam | 前片侧缝净弧长；直腰头 + 腰头宽 |

- 缩水差异源：已缩水件层 8 只剩缩水净样（毛坯口径）；`--shrinkage-*` 传率还原成品值；缺省 0=按毛坯口径报告，输出强制注明口径与来源。
- CLI：`ylpattern measure --dxf out/pieces_run.dxf [--out out/measured.toml] [--shrinkage-warp ..] [--shrinkage-weft ..]`；stdout 恒出对齐表（行=码、列=8 参数+识别方法）。
- 自洽金标：零缩水 SizeRun（W28/W30/W32，档差取 §四表）→ 逐码 build → write_size_run_dxf → measure 回读 ≈ 输入 Measurements；容差分级（首轮实测后收紧，断言旁注明实测值）：围度类 ≤0.15cm；outseam ≤0.5cm；rise ≤0.8cm。
