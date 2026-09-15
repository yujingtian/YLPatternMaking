# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

牛仔裤数字化打版系统（Python ≥3.10，核心层零第三方依赖）。把手工打版工程化：**打版师的每一笔（定一个点、画一条线）在程序中都有且仅有一个对应的生成函数**，按流程编排逐步绘制，先画后裁。

## 常用命令

```bash
pip install -e ".[dev]"        # 安装（含 pytest + ezdxf，DXF 测试可跑；生产装 .[dxf] 即可）
python -m pytest tests/ -q     # 全部测试
python -m pytest tests/test_steps.py -q              # 单文件
python -m pytest tests/ -k "waistline" -q            # 按名称过滤
# 出图：改 examples/ 下尺寸单参数即可，用 CLI 生成整版 + 各独立裁片 SVG
python -m ylpattern.cli draft --size examples/size_female_165.toml \
    --svg out/sheet.svg --trace out/trace.txt --report out/report.txt \
    --waistband-svg out/waistband.svg --yoke-svg out/yoke.svg \
    --front-pocket-svg out/front_pocket.svg \
    --front-pouch-svg out/front_pouch.svg \
    --front-fly-single-svg out/front_fly_single.svg \
    --front-fly-double-svg out/front_fly_double.svg \
    --watch-pocket-svg out/watch_pocket.svg \
    --back-patch-svg out/back_patch.svg \
    --belt-loop-svg out/belt_loop.svg \
    --front-piece-svg out/front_piece.svg \
    --back-piece-svg out/back_piece.svg
# DXF（裁床/服装 CAD，R12/mm 折线，需 pip install 'ylpattern[dxf]'）：
#   --dxf out/sheet.dxf 整版一张；--pieces-dxf out/pieces.dxf 全部裁片平铺合一张
# Web 端（主流程 2026-09-11 重构：左栏核心/全部参数两页签 + 右栏 3D 人台常驻；
#   「生成」按钮已随 3D payload 消费退役移除（2026-09-12），2D 进高级编辑/导出中心时
#   ensureSheet/ensurePieces 自动补算；需 pip install -e ".[web]"）：
#   uvicorn webapp.backend.app:app 后访问 http://127.0.0.1:8000
#   二期拖拽调版：整版把手拖动 -> 反解参数回写（flows/adjust.solve_param 数值求根，
#   绑定登记处 ylpattern/webschema.py 的 ADJUSTABLES；把手/缩放平移见 SheetView，口径 .doc/python工程设计.md §10.7）
#   推板 DXF（多码，v1 2026-08）：Toolbar「推板 DXF」+ 推板设置抽屉（相邻码档差表，
#   前端 sizeRun.ts 档差<->band 转换、首码并入首段免疫孤儿校验）-> /api/dxf?kind=size_run
#   （引擎 api.size_run_from_dict/run_size_run_groups 内存核心）与 /api/toml 带 [size_run]
#   段（直喂 CLI 复现）；转换金标 vitest：cd webapp/frontend && npm test（详见 §10.7）
#   本地引擎（2026-08）：整版/裁片/反解默认在浏览器内 Pyodide worker 跑同一份引擎源码
#   （前端 npm run build:engine 打内容 hash zip + manifest 到 public/engine，predev/prebuild
#    自动执行，改引擎代码后手动重跑；api.ts 引擎优先、失败透明回落 HTTP，DXF/下载仍走后端；
#    协议/回退阶梯/打包链详见 .doc/python工程设计.md §10.8）
#   口袋族默认口径（2026-09-16）：引擎 PatternOptions 默认最小裸版不动（extract 探针
#   守卫拒绝口袋特征+部分测量组合默认参数几何越界，改引擎默认已试已回滚），Web 初始
#   参数在产品层默认开 front_pocket/front_pocket_facing（useDraft 对 localStorage 缺键补 true）；
#   （前端已构建于 webapp/frontend/dist；改前端：cd webapp/frontend && npm run dev，
#    Vite 代理 /api；后端为薄壳，全部计算走引擎内存渲染，不落盘）
#   3D 人台（2026-09-13 定型 = MakeHuman 下半身切割+站直 target 滑杆试验场）：右栏 3D 主视图
#   常驻（进系统即有人台），three 惰性分包；fitting3d/ = Fitting3DView + bodymesh/
#   {bin,morph,types,slice,height}——loadBodyMesh 拉取 base.bin（vendor 切割+站直姿势链产物：
#   官方 rigs 骨架+蒙皮权重 clean-room LBS 站直〔大腿/小腿/脚逐关节角度，髋/膝/踝
#   铅垂；--pose apose 退回 A-pose〕、粗裁去臂、精裁腰+15、水密封盖；官方 14 场 =
#   12 measure〔腰/臀/大腿/膝/小腿/踝〕+ 身高 macro ±〔max/minheight，ΔH 切割前实测
#   写 meta.height；切缝/封盖合成顶点按边端点插值补增量〕已按切割后索引重映射+
#   增量随帧旋转，targets.json 带 baseSha256 指纹缓存击穿 + vendor 地标站），
#   六部位双极滑杆（−1..+1）+ 预设体型芯片（155/160/165/170，weightFor 按 meta.height
#   实测 ΔH 换算权重）+ 身高滑杆（cm 连续钳 150~185，可停任意身高）裸权重实时
#   morph（pos = base + Σwᵢ·Δᵢ；围度站 y × 身高因子）+ 站点围度
#   读数（站高 = vendor 地标检测值）；无围度闭环/对齐/钳位（自动调体型闭环仍退
#   役；裤子展示 2026-09-15 重建（一期静态 → 二期引力下垂 → 同日三期回落
#   全裁片平铺分色 + 机头后片/袋贴前片平面缝合）：整裤缝合解算链已删
#   （yoke 整裤 solver 不收敛，推倒逐步重建），当前展示 = 全部裁片行式
#   平铺人台旁侧地面（assemble.buildFlatLayout 逐片一行、成对片 L 原样 +
#   R 镜像并排、腰头单片，纸样 2D 逐点等距变换无弯折无解算，与 2D 裁片
#   SVG 一比一验证形状；STITCH_GROUPS 平面缝合拼合组〔带贴合守卫：缝合
#   依据线重合 <0.5cm 才拼〕——机头(back_yoke)下口线与后片上边整版坐标
#   重合拼成后身整体；袋贴(front_facing)袋口净线 marks 与前片 mouth 边
#   重合，补齐袋口月牙缺口拼成前身整体；组内 0.2cm 叠层防共面；有省款
#   yoke 省闭口错位被守卫拦下退独立行；整组 L/R 镜像）+ render.ts
#   PIECE_COLORS 逐片分色（前蓝/后绿/腰头橙/育克紫/袋贴青）+ 侧栏图例；
#   悬挂链〔core.ts 撑型芯 + buildFrontPair 前 90° 扇区摆位 + drape.ts
#   引力下垂/前中缝合〕暂停接线、代码保留待验证后回归；sim worker、
#   seams/band/ease/heatmap/align/useGarment 等整裤链 2026-09-15 删除，
#   mesh/placement/render/priors 为重建地基，显示层 Group 平移人台旁 +
#   FLAT_PRIOR.lift 抬离地面；引擎 payload schema v1 **零改动**
#   （照旧含第 4 片 back_yoke、第 5 片 front_facing，前端只消费
#   front_piece），独立原则——人台参数不改衣服，演进史 .doc/决策日志.md
#   §十一）；
#   引擎侧 exporters/fitting.py build_fitting_payload + POST /api/draft/fitting
#   schema v1 增育克片（2026-09-14）；三期平铺起前端消费全部片；人台数据 = vendor/makehuman/ CC0（PROVENANCE sha256，
#   .gitattributes -text），运行时只消费 public/bodymesh/{base.bin,targets.json}
#   两文件（raw.obj 全身链与 measure 拷贝已删，vendor 原件仍在 git 内）；
#   Python 金标 test_vendor_bodymesh.py（水密/地标/场方向/站直守卫）+ 前端金标
#   cd webapp/frontend && npm test（bodymesh.test.ts 含真产物冒烟）；
#   口径权威 .doc/python工程设计.md §10.11
# LLM agent（agent/ 独立目录与 webapp/ 平级，2026-09-03 边界：ylpattern 纯引擎、
#   全部大模型相关代码在此——extract/ 12 模块提取管线 + cli.py 命令行 + app.py HTTP 服务；
#   依赖方向唯一 agent → ylpattern；口径权威 .doc/python工程设计.md §10.9；
#   pip install -e ".[agent]" 后）：
#   python -m uvicorn agent.app:app --port 8001
#   POST /api/extract（multipart：describe/photos/thinking/...）-> to_web_payload 契约 + 信封；
#   缺必填尺寸/照片非法 422、VLM 未配置或失败 503；GET /healthz 查 vlm_configured（只回 bool）；
#   vlm.toml 路径解析 YLP_VLM_CONFIG > 仓库根 > YLP_VLM_* 环境变量；CLI 与 eval 仍直调 extract 门面
#   前端接线（一期 2026-09）：页面 header「从照片提取」向导弹层 -> 确认屏 -> 预填表单；
#   连通统一 /agent 前缀（dev Vite proxy / prod backend httpx 转发）；
#   契约/压缩口径/踩坑见 .doc/python工程设计.md §10.9.1
# 多码推码（尺寸单含 [size_run] 段且 enabled = true 时自动进入：逐码重打版 ->
#   多码单文件 DXF；整版 SVG/追踪/报表只出基码，enabled = false 或删段即退化单码模式）：
python -m ylpattern.cli draft --size examples/size_female_zhitong.toml \
    --pieces-dxf out/pieces_run.dxf --svg out/base.svg
# CLI 还支持 --until 步骤名：执行到该步停止，输出中间版调版
# 代码内调用：from ylpattern import run；run(waist=..., hip=..., svg=...)（详见 api.run docstring）
#             多码：from ylpattern.api import run_size_run（详见其 docstring）
# 工厂 DXF 反解析（reverse/ 包，布衣科技 R12/mm 方言 -> 尺寸单 TOML，层1 8键+层2 选项+层3 档差；
#   口径权威 .doc/工厂DXF逆向解析.md；还原换算 成衣cm = 净样mm×(1−率)÷10，与 cutter 除法口径互逆）：
python -m ylpattern.cli reverse --dxf "out/工厂款.dxf" --size out/rev.toml --report out/rev.txt
#   --style auto|5015|5028 显式档案；--probe 只出件清单报告（新款 bring-up）；
#   产物直接喂 draft 回环验证；仅特化已登记款号，未登记报错提示先 --probe
# 照片参数提取（agent/extract/ 包，2026-09-03 边界：ylpattern 纯引擎、全部大模型
#   代码在 agent/；半自动：模型是带眼睛的确认者不是业务判断者，
#   数值全部代码查表/派生，口径权威 .doc/参数预测/（知识库4篇+索引+款式判据手册）；
#   接入：复制 vlm.toml.example 为 vlm.toml 填 key（已 gitignore，key 不进仓库/报告）；
#   描述缺 7 必填尺寸 → 列清单退出码 2，绝不编数值；agent/ 顶层包不进 wheel，仓库根运行）：
python -m agent extract --photo out/front.jpg --photo out/back.jpg \
    --describe "女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 裤长102" \
    --out-dir out [--draft]
#   产物 out/extracted.toml（逐键 # 来源注释，直接喂 draft）+ extract_report.md
#   （预判vs照片轨迹/置信度/探针L0~L4/合理性评分/披露）；--draft 探针通过才直出
#   sheet.svg；无照片走纯描述路径（零模型调用可全中）；
#   Web 侧经 agent 服务（agent/app.py，POST /api/extract -> to_web_payload 契约，
#   见上文 agent 段与 §10.9）；CLI 与 eval 仍直调 extract 门面不走 HTTP；
#   金标评测（判据/词典改动前后必须跑对比）：python scripts/eval_extract.py
#   --cases tests/_extract_golden/cases --out out/eval_extract.md [--baseline 上一轮]
```

## 文档驱动的开发方式（本项目最重要的工作流）

- [打版流程.md](打版流程.md) 是步骤的唯一权威来源；[.doc/](.doc/) 下每篇推导文档对应一类公式（臀围、裆、腰、腿、腰头、口袋、袋布、门襟、贴袋、毗围……），[.doc/python工程设计.md](.doc/python工程设计.md) 是工程设计文档，[.doc/工厂DXF逆向解析.md](.doc/工厂DXF逆向解析.md) 是工厂 DXF 反解析（`ylpattern reverse`）的口径权威，[.doc/决策日志.md](.doc/决策日志.md) 是口径演进史归档（**规格文档只写现行规格**——日期/废弃方案/纠偏过程一律归日志，设计文档 §十 同此规则）。**文档先行**：部分特征先有推导文档、后程序化，属正常在建状态。
- 用户的典型操作：在打版流程.md 里新增/修改一个步骤 → 要求"程序化"。对应改动链条：**公式层（`formulas/`）→ 选项（`PatternOptions` 需同步 `api.run()` 显式参数透传）→ 步骤函数（`steps/*.py`，按部件分文件：`front_steps` / `back_steps` / `front_pocket_steps` / `front_pouch_steps` / `front_fly_steps` / `back_yoke_steps` / `back_patch_steps` / `waistband_steps`）→ 流程列表（`flows/*.py`）→ 金标测试**。腰头裁片另走裁切链：`steps/waistband_steps` + `flows/waistband_flow`（`build_waistband(main_ctx)`：直腰头代数求和净长；弯腰头前后腰弧真拼合+省道闭口+整根均匀圆弧，详见腰头裁片.md）-> `cutter`（缩水+缝边）-> `exporters/piece_svg`（独立 SVG），不在 FULL_FLOW 内。后机头裁片同走裁切链：`flows/yoke_flow`（`build_yoke(main_ctx)` 从整版提取机头四边界，有省时绕省尖旋转闭合 + 拼合处 G1 倒圆）-> `cutter` -> 刀口（净样角点沿净线延长线交缝边、净刀口沿外法向交缝边，§5.1）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。前口袋裁片同走裁切链：`flows/front_pocket_flow`（`build_front_pocket(main_ctx)` 从整版提取袋贴/贴袋净样边界，按 front_pocket_facing/front_patch 派发）-> `cutter` -> 刀口（袋贴袋口净线端点沿切线延长线交缝边、净样线+缝边成对；贴袋净角点沿相邻净线延长线交缝边，§2.2）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。袋布裁片同走裁切链：`flows/front_pouch_flow`（`build_front_pouch(main_ctx)` 从整版提取袋布大片/小片净样，小片沿内边 P_w0-K1 轴对称、按省/无省取袋口挖削线，拼成一片式对折轮廓）-> `cutter`（缩水默认 0 隔离大身面料 + 缝边）-> 刀口（底层完整侧袋口弧线端点沿切线延长线交缝边、挖削侧免打口 + 前口袋弧线/省弧线辅助线，§5）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。门襟裁片同走裁切链：`flows/front_fly_flow`（`build_front_fly(main_ctx)` 从整版提取独立门襟净样，单排原样提取、双排去底角 J 弧外缘平行化后沿内边轴镜像展开成对折片）-> `cutter`（缩水+缝边+刀口沿外法向投影至毛样外沿，§2/§4）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。小表袋裁片同走裁切链：`flows/watch_pocket_flow`（`build_watch_pocket(main_ctx)` 从整版提取小表袋净样，按 watch_pocket_mode 派发：袋贴相交延伸取底边袋贴内边子段、全自定义拷贝锚点闭合链）-> `cutter`（里料缩水默认 0 隔离大身面料 + 缝边）-> `exporters/piece_svg`，亦不在 FULL_FLOW 内。后贴袋裁片同走裁切链：`flows/back_patch_flow`（`build_back_patch(main_ctx)` 从整版 1:1 完整复制四形态净样，依赖 back_yoke 定位；大身面料缩水 None 回退全局 + 分区缝边 + 袋口镜像折边/撇势 + 袋口 4 刀（净口两角沿侧缝边/顶部线延长线交缝边、打在缝边上、底部不打口，§4））-> `cutter` -> `exporters/piece_svg`，亦不在 FULL_FLOW 内。裤耳裁片同走裁切链（例外：**不走 cutter**）：`flows/belt_loop_flow`（`build_belt_loop(main_ctx)` 不依赖整版几何，净尺寸长方形 宽×(单根长×根数+损耗) 整根连裁，净裁无缝份不折边）-> `exporters/piece_svg`/`piece_dxf`，亦不在 FULL_FLOW 内。前片裁片同走裁切链：`flows/front_piece_flow`（`build_front_piece(main_ctx)` 从整版提取前片大片净样，弯腰头剥离/口袋挖削/连裁门襟三形态条件矩阵装配净边 -> `cutter`（缩水+缝边+裆尖角部：镜像折角/切线 miter——False 态前浪缝边与下裆缝缝边各沿端切线直线延长相交于单一顶点，用户口径 2026-08-24）-> 刀口法向投影至毛样外沿 -> `exporters/piece_svg`，臀/膝/毗围辅助线随净边截断），亦不在 FULL_FLOW 内。后片裁片同走裁切链：`flows/back_piece_flow`（`build_back_piece(main_ctx)` 从整版提取后片主裁片净样（剥离腰头与机头），有 yoke 沿机头下口线截断/无机头取腰口弧三形态装配净边 -> `cutter`（缩水+缝边+后浪浪尖镜像折角/纯尖角）-> 刀口（法向投影 + 上边界两角净线延长线射线刀口/贴袋对位顶部刀口交毛样外沿）-> `exporters/piece_svg`，臀/横裆/膝围辅助线随净边截断 + 后贴袋顶线/定位孔 drills），亦不在 FULL_FLOW 内。步骤 docstring 和 `basis` 字段必须标注依据的文档章节。

## 分层架构（依赖方向自上而下，禁止反向）

`cli/api → exporters → flows → steps → draft → formulas → geometry → params`（**禁止反向**；尤其 `params/` 不能 import `formulas/`）。**agent/ 与 webapp/ 同为核心外薄壳层**（2026-09-03 边界：ylpattern = 纯引擎零 LLM，全部大模型代码在 agent/），依赖方向只许 `agent/webapp → ylpattern`，引擎侧零反向引用（详见 .doc/python工程设计.md §10.9）。

- **steps/**：核心层。每个函数对应手工打版的一笔，只做**定位与上版**；数值计算必须调 `formulas/`（纯 float 函数），经验常数一律收敛到 `PatternOptions`，步骤层不硬编码。
- **draft/**：`DraftContext` 是步骤间唯一协作通道——步骤只能 `ctx.point/line/curve("front.xxx")` 读取前面步骤的元素，禁止函数间直接传几何体；产物全程可溯源。
- **flows/**：声明式有序步骤列表；`FlowRunner` 按序执行，支持 `until` 中断与 `trace` 追踪。`FULL_FLOW = [*FRONT_FLOW, *BACK_FLOW]` 串联整版。**毗围闭环是唯一例外**（[flows/closure.py](src/ylpattern/flows/closure.py) 的 `run_with_thigh_closure`）：开 `thigh_limit` 后，整版绘制 → 测前后毗围实测 → ΔW = 目标 − 实测 → 按前后片毗围推导.md §三双轨分流把修正量换算为选项增量 → 整版重跑至收敛；api 与 cli 入口都走它。选择重跑而非版上补丁，是为了让浪长闭合、裤中线等不变量自动保持（"不破坏裤子原本的结构"，打版流程.md 后片步骤 8）。
- **先画后裁**：前后片在同一全局坐标系的一张 `DraftSheet` 上绘制（后片整体置于前片右侧、间距 `piece_gap`，五条水平线等高，后片直接读 `front.xxx` 基准线，故后片必须在前片之后执行）；裁切层（cutter/pieces）已为腰头、后机头等独立裁片落地（`build_waistband` / `build_yoke` 另建局部 sheet、经缩水+缝边出独立 SVG），但主版布尔裁除未实现，故口袋/贴袋等仍只上版边界线、不做布尔裁除。

## 关键约定

- **坐标系**（与打版流程.md 一致）：原点 = 外侧缝参考线 ∩ 脚口线；X 向右朝内侧缝（裤宽），Y 向上朝腰头（裤长）；单位 cm，内部 float。
- **腰头扣除口径**：`outseam`/`front_rise`/`back_rise` 均为**含腰头的成衣量**。直腰头打版时统一经 `PatternOptions.rise_on_pattern()` 换算（扣腰头宽）；弯腰头不扣。任何使用浪长/裤长的步骤都必须走这一个口子，不要自行扣减。
- **缩水口径（除法）**：净样 ÷ (1−率)——缩水率以**缩水前毛坯**为基准，洗水缩回后恰为净样（旧乘法 ×(1+率) 以净样为基准、洗后偏小，2026-08 弃用）。缩放因子统一走 `cutter.shrink_scale(rate)`（`apply_shrinkage` 内部同源）；flow 里任何要自叠缩放因子的地方（pinned 刀口/切向方向/缝边交点换算）都必须调它，禁止手写 `1.0+rate`。裁片缩水率解析（专用率 None 回退全局 + 总开关 `shrinkage_enabled=False` 收缩为 0）统一走 `o.shrinkage_rates(专用warp, 专用weft)`，勿在 flow 里手写回退。
- **前后片调节量方向**：一律**前减后加**（臀围 Δ、腰围 balance 同向）。前片 = H/4 − Δ、W/4 − balance。
- **腰长不变量**：纸样腰长 = 成品目标 + 该腰口边缘所有省口宽合计（前片含袋口吃省 ΔW、后片含 Σ腰省宽），省只改形、不改缝后长度；`front_waist_dart`/`back_waist_dart` 是纯腰长调节量，不含任何绘制省宽（守卫收口 `formulas/waist.py` 的 `pocket_dart_takeup`/`back_darts_takeup`）。
- **可选步骤（开关驱动）**：口袋 / 袋贴 / 贴袋 / 袋布 / 小表袋 / 后片腰省 / 后机头 / 毗围限制等都是 `PatternOptions` 上的 `bool` 开关；开关关闭或前置条件不满足（如**袋贴 `front_pocket_facing`、袋布 `front_pouch`、小表袋 `watch_pocket` 均依赖 `front_pocket` 主切口；小表袋相交模式 `facing_intersect` 额外强依赖 `front_pocket_facing`**；毗围依赖大腿围录入）时步骤返回 `None`，`FlowRunner` 标注"跳过"不上版。开关与几何参数同收敛于 `PatternOptions`。
- **测试风格**：金标测试——测试文件头部注释写明参数下的手工演算结果，断言精确值；推导文档里的案例直接转成公式层金标（见 tests/test_waist.py）。
- 复合线（如前浪 = 斜线 + 凹弧）作为同一步骤的多个元素上版，是"一函数一元素"原则的显式例外。

## 元素命名与 ctx 存取

- 元素名 `"front.xxx"` / `"back.xxx"`（部件前缀 + 语义名），全局唯一。上版：`ctx.add_point/line/curve(name, geom, step=_STEP, basis=..., label=..., role=...)`；读取：`ctx.point/line/curve(name)` 返回**几何体**（Point/LineSegment/CubicBezier），类型不符抛 TypeError。
- `_STEP = "draw_xxx"`（或 `__name__`）作步骤来源标记；`basis` 写依据文档章节+关键数值，供 trace/报表溯源。
- `DraftSheet` 是元素容器，`ctx.sheet.get(name)` 取元素本体（含 role/label），`ctx.sheet` 可 `"name" in sheet` 判存在。

## 实现前定向读（隐性规则，代码里看不出来）

写新步骤/特征前，按触发场景**定向读** [.doc/python工程设计.md](.doc/python工程设计.md) §十（按需，别全读）：

- 画局部特征框（口袋/袋布/门襟/贴袋等局部 u-v 系）-> §10.1（原点、轴正方向、旋转顺时针为正）
- role/SVG 图层与渲染 -> §10.3
- 架构依赖红线（params 禁 import formulas 等）-> §10.4（亦见本文「分层架构」）
- Edit 改中文代码/文档失配 -> §10.5（全角 Unicode 与 fallback）
- 不确定某特征是否已程序化 -> §10.6

**几何 API（`geometry/`、`draft/curves.py`）不查文档，直接读代码**，签名与易踩坑点已在代码 docstring 标注，文档不重复维护。
