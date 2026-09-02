# 照片+描述 → 大模型提取参数 → 版图（一期：extract 包 + CLI）

## 本次执行范围（2026-09-02 调整：吸收用户收集的 4 篇业务知识）

**只动文档、不写代码**：
1. `.doc/参数预测/` 4 篇收集文档（直裆深/前中内收/后中内收/前口袋和育克转移省预测）**就地补固定字段头**：输入依赖 → 推导规则（原文已有）→ 区间内定位规则 → 边界反例；并加「对应引擎键」标注（如 back_intake=15:X 的 X、front_intake_ratio=绝对值÷(H−W)/4、front_pocket_dart_width=袋口转省）。正文保留原文不动。
2. 新建索引 `.doc/参数预测/参数推测知识库.md`：参数→输入依赖总表 + 条目索引 + **冲突裁定记录**（前中内收高腰档 2026-09-02 用户裁定「新表为准」）。
3. 旧 [.doc/前中内收量推导.md](.doc/前中内收量推导.md) §三 加注：预测口径已被 参数预测/前中内收预测.md 取代（引擎公式与默认 ratio 0.2 不变，只影响 extract 发射值）。
4. 同步项目内计划副本 `.claude/plans/iridescent-discovering-tide.md`。

随后仍**暂停**：等用户补 H 表剩余缺口（部件尺寸档位/男款系统性差异等）或指令开工实施顺序 ②。

## Context

打版引擎已完备（8 键 measurements + 190 键全默认 options，尺寸单 TOML 是全系统统一中间表示）。本任务新增一条输入通道：**用户拍几张牛仔裤照片 + 一段文字描述（说明核心参数）→ 提取/推断 → 尺寸单 TOML + 逐键核对报告 → 人工核对 → 生成版图**。

背景与已确认决策：
- 此前一轮 PoC（agent 包 + scripts 驱动 + 40+ 测试）源码已删且从未入 git。用户选择**推倒全新设计、不复刻**；但其实测事实必须吸收（见「provider 踩坑清单」）。
- **一期**：引擎侧 + CLI，webapp 不动只留接缝；**二期**：webapp 上传页预填现有参数表单。
- **半自动**：产出参数单 + 逐键置信度/依据报告，人工核对后再出图；低置信标黄、缺失回退默认并标注。
- 用户明确要求：**不能依赖大模型自身的业务能力（不稳定），业务知识必须沉淀在系统里辅助它**——见下节，这是本方案的架构基石。

## 核心设计原则：模型是「带眼睛的确认者」，不是「业务判断者」

| 判据 | 归属 | 实例 |
|---|---|---|
| 描述里的显式数字 | **代码确定性解析**（正则+同义词典+尺码换算，不走模型） | 8 键尺寸、「29码」→腰围 74、缩水率 |
| 可计算映射（档位表/公式/预判） | **代码查表/插值**（区间→定值三级定位） | 各轴预判（按锚点表从尺寸算）、delta/内收/rise_adjust 派生、curvy 联动 |
| 部件存在性 | **惯例先验表 + 模型报告偏离** | 牛仔裤默认有前口袋/门襟/裤耳/后机头/后贴袋；模型只需说「看见的反例」 |
| 需要看照片的定性确认 | **模型 confirm/override**（推翻必须给 evidence） | 轴确认、弯/直腰头、盾形袋底、袋口形状 |
| 约束反例 | 代码硬校验 + prompt 提示各一份 | 依赖链、枚举值域、已知引擎缺口 |
| 绝对 cm | **照片永不贡献**（无标尺） | 8 键只从描述来，缺失即 null，不编数值 |
| 合理性 | **引擎是最强判据**（进程内试跑 + 打版后特征评分） | 探针 L0~L4 + 袋口占比/侧缝斜度等业务区间评分 |

## 管线（两阶段调用，业务知识三级注入）

```
描述 ─→ S1 描述解析【纯代码】：数字正则 + 同义词典 + 尺码换算
│        漏键 → 一次纯文本小调用补漏（仍缺 → 列清单 exit 2，不编数值）
│        产出：8 键 + 描述侧轴/开关倾向 hints
▼
S2 视觉确认调用【唯一主调用】：prompt 注入——
         ①已知 8 键数值 ②各轴代码预判（按锚点表算好）③部件惯例先验表 ④加厚判据手册段落
         模型任务 = 逐项 confirm / 带证据 override / 报告照片可见的款式特征
▼ parse：JSON 容错 → 白名单/枚举归一 → Observation
▼ merge+derive：override 需 evidence，无照片视角/低置信 → 采代码预判/先验；
         轴+尺寸 → 查表派生全部数值键（每键 KeyMeta：来源/置信度/依据）
▼ validate：复用 params.validate.build_issues + 派生区间复核
▼ probe 回喂（≤2 轮）：flows.closure.run_with_thigh_closure 进程内试跑
         失败→归因到键→回喂修键→重试；耗尽→回退默认→降级关开关→披露
▼ score：打版成功后量派生特征按业务区间评分（出界→报告警告，一期不改参）
▼ emit：out/extracted.toml（构造回验）+ out/extract_report.md + web payload
▼ 人工核对（CLI --draft 可确认后直出）
```

## 业务知识库（专门知识资产：每个参数声明「需要什么信息 → 判定/推导规则 → 数值区间 → 出处 → 边界反例」）

载体 `.doc/参数预测/` **文件夹即知识库本体**（2026-09 用户已收集 4 篇，一参数组一文件的自然形态保留；推测规则的唯一权威，与「款式判据手册」并列：知识库管*怎么推*，手册管*怎么看*）；另建索引 `参数推测知识库.md`＝参数→输入依赖总表 + 条目索引 + 冲突裁定记录。代码 `prejudge/derive/families` 的每个函数与知识库条目一一对应（文档先行，代码抄录注条目号）；prompt 生成也从知识库抽取「该参数需要模型提供什么视觉信息」。**参数 → 输入依赖总表**（吸收 4 篇收集知识后）：

| 参数组 | 推测它需要的信息（输入依赖） |
|---|---|
| back_dart / 育克（省道组） | **全局余量排除法**（参数预测/前口袋和育克转移省预测.md）：总单侧余量 (H−W)/2 ＝ 前中 + 后中(15:X) + 前口袋转省(0.5~1.0 极限1.5) + 侧缝(3~4) + 育克兜底(2.0~5.0)；**有育克时育克即巨型转移省、经典牛仔裤默认无后腰省**；无育克缺额→强制腰省 |
| front_intake（前中内收） | 腰位基准带（5 档）+ 四维修正：体态/面料/性别/廓形（前中内收预测.md，硬上限 3.5） |
| waist_position | front_rise（**先按 size_label 放码归一化**，每码 0.5~1cm）+ 性别（男女双表，直裆深预测.md） |
| delta | 体型 × fit × 弹力（DELTA_PRESETS）+ 大差侧缝前移技巧（≈delta 调整） |
| rise_adjust / 机头宽 | 腰位档（直裆深推导 §三；臀围线推导 §三约克建议） |
| waist_balance / back_intake | back_intake 主锚改**臀腰差 15:X 表**（后中内收预测.md）+ 腰位/弹力偏移；waist_balance 含 curvy 联动防倒挂 |
| p1/p2 + 袋口族 | 腰位 + fit + **前片宽**（弦长/片宽占比联检 0.45~0.55） |
| 贴袋族 | 形状枚举（模型）+ 性别码 + 后片宽占比联检 |
| watch_pocket | front_pocket 开 + 袋口弦长容量（宽/弦长 ≤0.55 放得下才配） |
| waistband_type / 形态枚举 | 仅照片视觉判据（模型唯一不可替代处） |
| 款式开关其余 | 依赖链 + 上下文规则（见 D） |
| knee/hem_adjust、crotch_drop | 弹力档 |

### A. 描述侧（S1 纯代码，`parse.py`）
- **数字正则**：腰围/W 74、臀围/H 91、前浪/前裆 28…（中英别名+全半角）；只认显式数字。
- **同义词典 → 轴/开关倾向**（词典命中优先于照片）：小脚/铅笔→skinny；直筒→regular；妈妈裤→高腰+loose；老爹裤→mid+loose；喇叭→hem≥knee 特例；阔腿→wide；弹力/氨纶→stretch high；无弹/原浆→none。
- **尺码标签换算**：「29码/W29/尺码29」→ 腰围 = 29×2.54 ≈ 73.7→圆整 74（evidence 注换算式）；描述无显式腰围有码号时用。

### B. 轴判据锚点表（代码预判 + 交叉验证，`derive.py`）
| 轴 | 判据锚点（女款基准；gender 轴给男款偏移） | 出处 |
|---|---|---|
| waist_position | 锚=front_rise（前裆弧长，**先放码归一化**：norm = front_rise − (码−基准)×0.75，女基准 26/27 码、男 31/32 码；每码 0.5~1cm）。女：**低 ≤20 / 中低 20~23 / 中 23~26 / 中高 26~29 / 高 ≥29**；男：低 <23 / 中低 23~25 / 中 26~28 / 中高 28~30 / 高 ≥31（男比女长 2~3）。物理交叉：低腰=卡胯骨、中腰=脐下 1~2cm、高腰=盖过脐至自然腰线 | **参数预测/直裆深预测.md（2026-09 收集，取代初版 4 带口径）**；与直裆深推导.md §三垂直量兼容（前裆弧长≥直裆深） |
| gender | 锚=size_label（W30+/31 码以上倾向男）/ 描述词（男款/女款/men/women）；驱动腰型男表、前中性别修正（男 −0.5~1.0）、DELTA men_straight | 尺码惯例 + 直裆深预测.md §2 |
| body_shape | 锚=臀腰差 H−W：**curvy ≥25（或 W/H≤0.75）/ standard 18~24 / straight <18**；体态细分（沙漏/挺腹/平腹）进前中内收修正 | 前中内收量推导.md §三 + 2026-09 实测口径 + 前中内收预测.md 体态修正 |
| fit_level | 锚=hem/hip 比例 + 描述词：**skinny 0.40~0.45 / slim 0.45~0.50 / regular 0.50~0.56 / loose 0.56~0.65 / wide ≥0.65 或 hem≥knee**；knee/hip 同向辅助。锚例：examples/size_female_165 hem47/hip100=0.47 | 初版比例带，金标校准 |
| stretch | 锚=描述面料词：high（弹力/氨纶）/ low（常规微弹，默认）/ none（无弹/原浆/硬挺） | options.py 注释惯例 |

### C. 轴→键联动方向表（`derive.py`，初版取带中值）
| 轴/档 | 联动键与方向 | 出处 |
|---|---|---|
| waist_position | `rise_adjust`：低腰 −2.0~−3.5 / 中腰 0~+1.5 / 高腰 +3.0~+4.5（引擎默认 4.0≈高腰档）；自洽校验：H×0.25+rise_adjust 与 front_rise 应同腰位带，跨带→warning | 直裆深推导.md §三 Δ 矩阵 |
| waist_position+四维 | `front_intake` ＝ **基准带 + 四维修正**（2026-09-02 用户裁定新表为准，取代旧 k=0.2 系数口径）：基准 低 0~0.5 / 中低 0.5~1.0 / 中 1.0~1.5 / 中高 1.5~2.5 / 高 2.5~3.5；修正 体态（沙漏 +0.5~1.0、挺腹 −0.5~1.0、平腹 +0.5）+ 面料（高弹 −0.5~1.0、无弹 +0.2）+ 性别（男 −0.5~1.0）+ 廓形（skinny +0.2、wide −0.2）；**硬上限 3.5（拉链刚性）**；发射 `front_intake_ratio = 绝对值÷((H−W)/4)`（ratio 记账层、adjust 不动；高腰款 ratio 可至 ~0.4+ 属预期） | 参数预测/前中内收预测.md（基准+修正公式+实战案例 2.2） |
| body_shape×fit×stretch | `delta`：DELTA_PRESETS 五档路由（women_standard 1.0 / women_curvy 1.35 / men_straight 0.6 / high_stretch 0.4 / loose_wide 0.25） | options.py:42 / 前后片臀围推导.md §四 |
| body_shape=curvy | `waist_balance`=0（skinny/slim 再 −0.5）+ front_intake 档上限 clamp（防前后侧缝收量倒挂） | 牛仔裤前后片腰围推导.md + 实测 |
| 臀腰差（主）+腰位/fit/弹力（偏移） | `back_intake`（15:X 模数，引擎即此口径 options.py:138）：**臀腰差 <15→2~2.5 / 15~20→3~3.5 / 20~25+→4~4.5，极限 5**（超限余量移交育克，后中内收预测.md §3）；偏移：低/中低腰靠下带、高腰/紧身提臀靠上带、有弹降半档（15:3.5→15:3）；绝对值参考带 低 2~3 / 中 3.5~4.5 / 高 4.5~5.5（经臀腰高 H_v 自然放大，定 X 即得）。`front_crotch_adjust`：紧身 −0.5~−1.0、常规 −0.4~0；fit 发射 wide→loose（引擎 Fit 枚举仅 4 值） | **参数预测/后中内收预测.md（15:X 表+实战案例）**；fit 偏移带与 options.py 键注释相容 |
| stretch | `crotch_drop_adjust`：高弹 −0.4~−0.3 / 标准 0 / 宽松重磅 +0.2~+0.3；`knee_adjust`/`hem_adjust`：高弹 0.75 / 标准无弹 1.0 | 落裆推导.md §2.2 / options.py 键注释 |
| watch_pocket=True | 强制 `front_pocket_facing=True` + `watch_pocket_offset_from_side=2.0`（引擎已知缺口绕行，66–84 码实测全过）；waist<64 极小码降 invalid 交人工 | 引擎缺口实测 |
| （无轴） | `p1_dist/p2_drop/back_patch` 尺寸档位表：初版值进知识库部件条目，代码抄录注条目号；thigh>0→`thigh_limit=True`；缩水率仅描述显式提到才摘录 | 待金标校准 |

**区间→定值的定位机制**（业务知识给的是范围，C/H 表查出的也是区间；定值由三级机制在区间内定位，逐级兜底，规则随条目入知识库）：
1. **连续锚点插值**（主，能插则插）：区间端点绑连续量——back_intake 的 X 按臀腰差在 15:X 表带内连续插（15→3 / 20→3.5 / 25→4.5）；前中基准带按放码归一化后 front_rise 在带内插值、体态修正量按臀腰差超 20 的幅度插 0~+1.0；rise_adjust 同法按 front_rise 在腰位带内插（越低于 23 越靠 −3.5）；省宽=余量排除法缺额**连续算出**再 clamp 进 [1.0, 2.5]（算式本身就是定位器，区间只做上下限）。
2. **多轴偏移规则**（无独立连续锚点时）：其余轴把取值推向区间端点——紧身/无弹靠上限、宽松/高弹靠下限等**方向规则**进知识库条目。
3. **中值兜底 + 评分步进**：无锚点也无偏移依据的键（如 paring_n 1.5~2.0）初版取中值；打版后特征评分出界→在区间内步进修正（一期只警示、二期回喂改参）。

模型在此的角色：**不口算绝对 cm**（无标尺不可靠）；一期连「视觉偏向」（偏大/偏小→区间内偏移方向）也不采，代码定位优先求稳，模型只做分类与确认。

### D. 部件先验与「合理想象」原则（`schema.py`，模型只报偏离）
照片看不到、描述也没提的部件（如小表袋）：**按牛仔裤工业惯例 + 当前版型上下文拍板，合理即可**，报告标注「惯例推断」。

**先验表是规则表 f(轴/关联开关/核心尺寸)，不是常数表**。示例 `back_dart` ——「要不要省」由**全局余量排除法**决定（知识库条目，前口袋和育克转移省预测.md）：

```
总单侧收缩余量 R = (H−W)/2（人体半边，前+后片渠道合计）
分配次序（余量排除法，参数预测/前口袋和育克转移省预测.md「终极公式」）：
  ① 前中内收（基准带+四维修正，C 表）
  ② 后中内收（15:X 定 X，C 表；超 15:5 的余量不进后中）
  ③ 前口袋转省 0.5~1.0（极限 1.5，超限袋口外翻「咧嘴」手难插）
  ④ 侧缝撇势：目标带 3~4；大差款 4.5~5 + 侧缝整体前移 1.5cm（≈delta 调整）
  ⑤ 育克兜底：育克转省量 = R − ①−②−③−④，常规 2.0~5.0
back_dart 判定：有育克时育克即「巨型转移省」，**经典牛仔裤默认无后腰省**
  （旧「装饰性省」先验降级为可选风格项，需照片证据才开）；
  育克容量不足或无育克且余量 > 0 → 强制腰省：count=1，width=缺额 clamp[1.0,2.5]，
  缺额 > 2.5 → count=2，width=缺额/2（curvy 大差体型）
引擎映射口径：侧缝收量是**结果量**（腰长闭合硬约束 |AB|=W/4±δ），④ 的目标带
  用于前向校核（各渠道之和应 = R）与评分观测（F 节侧缝斜度），逆向调参杠杆 =
  waist_balance / 育克深度（yoke 起翘差 ↔ cb/side 参数，实现时核对几何口径）；
  弹力款弹力吸收：余量 ×(1−0.25) 后再进 ⑤
```

模型 override 仅当照片可见后片省道有无（通常被机头缝掩盖、可靠度低），须 evidence；兜底=探针 + formulas/waist.py 腰长不变量守卫。**前片同构一张余量分配表**（前中 + 前口袋转省 + 侧缝前片份额，缺额反馈到 front_pocket_dart_width/waist_balance），进知识库同条目。

同类规则：`watch_pocket/front_pouch/front_pocket_facing` 跟随 `front_pocket`（依赖链+惯例全配）；`fly_separate=true`（现代主流），`fly` 连裁需证据；`front_patch` 默认 false（罕见，开启才出族）；极简时装 skinny → `back_patch` 提级为「需证据」。门襟形态判据（独立 vs 连裁：门襟明线形状/缝线走线）进判据手册。prompt 注明「以下为惯例默认（已按你的版型上下文算好），只在你明确看到不同时报偏离」；模型低置信/无证据 → 采先验并标注。

### E. 加厚视觉判据手册（`.doc/参数预测/款式判据手册.md`，prompt ②类知识唯一来源）
每键判据成体系：**看哪个部位 / 形状特征 / 正反例 / 易混对比 / 照片角度约定（正面看什么、背面看什么、遮挡时惯例推断）**。例：弯腰头=「腰头上口在侧缝处下凹弧线、腰头与裤身一体顺接」vs 直腰头=「等宽直条、侧缝处上口平」；盾形袋底=「底中点尖出、底边明显窄于袋口」vs 方袋；袋口弧深三档=「微弯近直 / 经典五袋弯月 / 明显深月牙」。`schema.py` 从手册生成 prompt 段落（同源）；**每批判据入 prompt 后必须跑 eval 对比才算数**（防整段塞入稀释弱模型注意力）。

### F. 打版后特征合理性评分（`score.py`，输出侧兜底）
探针只判「炸不炸」，评分判「合不合理」（一期只警示不改参，回喂改参留二期）。打版成功后从 DraftContext 量派生特征，按业务区间打分，出界进报告「合理性警告」清单：
- 袋口弦长 / 前片宽占比 0.45~0.55（评审实证：13.35/59% 失调配例）；
- 侧缝上段斜度（腰端 >~30° 或均值 >~20° 警告，实证元凶 W69+H94 极限臀腰差）；
- 前/后侧缝腰部收量比（前 > 后即倒挂警告）；
- 直裆深与 front_rise 跨腰位带（与 B 表自洽校验同源）；
- 前中内收落档（低于腰位档下限警告）。

### G. 部件参数族模板（`families.py`：部件有体现 → **全族参数一次出齐、内部高度一致**）
部件开关确认存在后，该部件整族几何参数按模板发射；模型只出「形态枚举」（袋口形状/贴袋形状/腰头类型），数值全部模板+档位，杜绝族内比例失调（如弦长 13.35 占片宽 59% 的配例）。模板数值权威在知识库各部件条目，初版值出处标注：

| 部件族 | 发射键（初版值/联动规则） |
|---|---|
| 前口袋主切口 | p1_dist/p2_drop（B 表档位）；dart_width 0.8（**0.5~1.0，极限 1.5**——余量排除法 ③，弯腰头款可至 2.0 待核）；paring_n 1.5~2.0；mouth_mode=袋口形状轴映射（arc→bulge / 直口→tangent / 折角→polyline）；**弧深三档视觉分类：浅 0.3 / 标准 0.4 / 深 0.5（判据手册：微弯 / 经典五袋弯月 / 深月牙）**·bulge_at 0.6（bulge 式）；h1 8 / h2 3（tangent 式）；corners=[[0.3,2],[0.6,3]] 按弦长缩放（polyline 式） |
| 袋贴 facing | mode=tangent；width 3.5；side_w 5~7 档（与 p2_drop 联动）；h1 14、h2 1 |
| 袋布 pouch | waist_safe 6 / side_safe 10；nodes/edges 默认底弧（与袋口形状同风格） |
| 小表袋 watch | width 7（6.5~8.5）；taper 0.2；offset_from_top 3；offset_from_side 2（配套包）；rotate 8；points/edges 默认梯形按宽缩放（底 7.2/高 7.5 基准） |
| 后贴袋 back_patch | inset_x 4.5（4~5.5）/ drop_y 3.5（3~4.5）/ rotate 3.5（平行约克线）；width/height 档位（女 13~14/12~15、男放大 1.5~2）；按 shape 分模板：rectangle（bottom=width）/ baker_shield（bottom=0.85w、tip_depth 2~2.5、默认盾形角点）/ angular（chamfer 1.5~2） |
| 后机头 yoke | cb_dist 6 / side_dist 3.5；**腰位联动**：高腰加宽 5~7 / 低腰收窄 3~4（臀围线推导.md §三约克建议） |
| 后腰省 dart | count/width 由 D 节余量排除法定（有育克默认无省）；length 10.5 |
| 门襟 fly | 独立主流：fly_separate + fly_sep_double；width 4.0（YKK 5# 3.5~4.2）、length_ratio 0.35、base 2.0、corner_inset 0.5；连裁另加 turnback 0/corner_turn 0.5/blend_drop 自动 |
| 裤耳 belt_loop | width 1.2、unit_length 6、count 5、waste 3 |
| 腰头 waistband | waistband_type（模型：弯=上口下凹一体顺接 / 直=等宽直条平上口）；width 4.0 默认（照片明显宽窄 → 3.5/4.5 档，低置信回默认） |

**部件内一致性联检**（进 validate + score）：袋口弦长/前片宽 0.45~0.55、小表袋宽/袋口弦长 ≤~0.55、贴袋宽/后片宽比例带、facing_side_w ≥ p2_drop、盾形 bottom<width——出界回退模板中值并警告。

### H. 业务参考数据收集清单（知识库初版数据从哪来：.doc 已有值先抄录，缺口标【待补】）

**数据价值的实现机制**：进 `derive.py` 查表层产出**区间 + 区间内定位规则**（见 C 表后三级定位机制），插值出定值（模型不需要知道省量多少——代码算）；模型侧只受益两处：视觉判据（怎么看）+ 轴锚点带（多高算高腰）。用户点名的数据表与现状：

| 数据表 | 现有来源 | 缺口【待补】 |
|---|---|---|
| 前口袋省量 dart_width（袋口吃省） | **✓ 已补（2026-09-02 收集）**：常规分担 0.5~1.0、极限 1.5（超限袋口外翻），前口袋和育克转移省预测.md | 直/弯腰头分档（examples 弯腰头款 2.0 与新表关系）+ 单侧/总宽引擎口径核对 |
| 后腰省量（省数/省宽/省长） | **✓ 结构已定**：余量排除法兜底公式 + 育克替代原则（有育克默认无后腰省） | 渠道系数细校（侧缝 3~4 / 育克 2.0~5.0 初值已有） |
| 前中内收范围（按腰位） | **✓ 已补 + 裁定新表为准**：5 带基准 + 四维修正 + 硬上限 3.5，前中内收预测.md；实战案例 2.2 可转金标 | 带内定位细化（一期带中值+修正中值） |
| 后中内收范围（按臀腰差） | **✓ 已补**：15:X 表（<15→2~2.5 / 15~20→3~3.5 / 20~25+→4~4.5，极限 5）+ 腰位/弹力偏移 + 实战案例，后中内收预测.md | — |
| 腰型分档（前裆长） | **✓ 已补**：女 5 带（≤20/20~23/23~26/26~29/≥29）+ 男 5 带（<23/23~25/26~28/28~30/≥31）+ **放码归一化 0.5~1cm/码**，直裆深预测.md | — |
| 立裆深程度 rise_adjust | 直裆深推导.md §三 ✓ Δ 矩阵（低 −2.0~−3.5 / 中 0~+1.5 / 高 +3.0~+4.5） | 男款 Δ 偏移落点（男表腰型已有） |
| 男裤女裤差异总表 | **部分已补**：腰型男表 ✓、前中性别修正（男 −0.5~1.0）✓、DELTA_PRESETS men_straight 0.6 ✓ | 前后浪差/裆弯斜度/口袋位/机头形——二期男款支持前先攒 |
| 部件尺寸档位（袋口/贴袋/小表袋/门襟） | examples 金标值 + G 表初版 | **未补**：按 fit/性别分档细化 |
| 弹力影响系数 | **部分已补**：前中高弹 −0.5~1.0 ✓、后中降半档 ✓、落裆推导.md §2.2（crotch_drop/knee/hem_adjust）✓ | 弹力对内收/侧缝分配比例 |

**口径优先级**：项目 .doc 推导文档（与引擎同源）> 打版师（用户）补充 > 通用工业惯例（YKK 5# 等）。实施步骤 ① 即完成「.doc 已有值抄录入库 + 缺口标【待补：打版师口径】」；用户核对补值是持续过程、不阻塞管线落地——缺口的键暂用引擎默认并在报告低置信标注，补值后重跑 eval 对比即可见提升。

## 推测依据汇总（每个发射键强制带 来源/置信度/依据 三元组，evidence 必须落到下列五类之一，报告逐键可溯）

| 参数类别 | 推测依据（evidence 写什么） |
|---|---|
| 8 键尺寸 | **用户描述原文摘录**（正则命中句，如「腰围74」）或**尺码换算式**（29码→29×2.54≈74）——是摘录不是推测 |
| 款式开关 11 | 三级：①照片视觉判据（判据手册文案，evidence=看见的特征）②描述词（同义词典命中词）③**上下文惯例**（牛仔裤工业惯例+版型上下文，evidence=「惯例推断」并标低权重） |
| 形态枚举（腰头/袋口/贴袋形状） | 照片视觉判据（手册判据，evidence=形状特征描述） |
| 分类轴 4（腰位/体型/版型/弹力） | **双依据交叉**：代码锚点表从核心尺寸算预判（evidence=「front_rise 28.5 ≥28.5 → 超高腰，直裆深推导.md §三」）+ 照片/描述确认；冲突数字优先 |
| 轴联动数值 9 | **.doc 对照表**：参数预测/ 4 篇收集文档（预测口径优先：前中内收/后中内收/腰型分档/余量排除法）+ 直裆深推导 §三 Δ 矩阵、前后片臀围推导 §四（DELTA_PRESETS）、落裆推导 §2.2——evidence 必须写文档章节+所取档位 |
| 部件参数族 49 | 部件参数族模板（知识库部件条目唯一权威，设计文档 §4 只做索引）：初版值=examples 金标值 / 工业惯例（如 YKK 5# 门襟宽 4.0）/ 档位中值 + 核心尺寸联动（机头宽随腰位）；evidence=「知识库条目号 + 联动规则」 |
| 配套/条件键 | 引擎缺口实测（watch_pocket 配套包 66-84 码实测全过）/ 规则（thigh>0）/ 描述摘录（缩水率） |
| 全部键的兜底 | **引擎本身**：探针试跑（构造校验+打版成败）+ 特征评分（业务区间合理性）——不合理即回退/警告 |

溯源载体：`KeyMeta{source, confidence, evidence}` → extracted.toml 每键行尾 `# 来源：…` 注释 + 报告逐键表；查表类无文档章节的表值**禁止入档**（派生表必须先落知识库对应条目才能进代码）。

## 参数覆盖面（发射键清单，共 87 键 = 8 尺寸 + 79 选项；190 键 options 的 ~42%，其余走引擎默认并在报告标注；部件族键随该部件开关开启才发射）

| 类别 | 键 | 来源 |
|---|---|---|
| 尺寸 8 | waist/hip/knee/hem/front_rise/back_rise/outseam (+thigh 可选) | S1 描述解析（正则/词典/码号换算，不过模型） |
| 款式开关 11 | front_pocket、front_pocket_facing、front_pouch、front_patch、watch_pocket、back_patch、back_yoke、back_dart、belt_loop、fly、fly_separate | 上下文先验 + 模型报偏离（含门襟独立/连裁判断） |
| 枚举 6 | waistband_type、fit（wide→loose）、back_patch_shape、front_pocket_mouth_mode（袋口形状轴）、front_pocket_facing_mode、watch_pocket_mode | 模型形态判断（视觉判据）+ 轴映射 |
| 弯曲框架数值 9 | **front_intake_ratio（front_rise 查表→绝对内收→ratio 记账，adjust 保持 0 微调位）、back_intake（fit 档）**、delta、waist_balance、rise_adjust、front_crotch_adjust、crotch_drop_adjust、knee_adjust、hem_adjust | 全查表（C 表；参考核心尺寸 H−W/front_rise/fit 推测） |
| 部件参数族 49 | 前口袋 9、袋贴 4、袋布 4、小表袋 8、后贴袋 9、机头+腰省 5、门襟 5、裤耳+腰头宽 5 | 模板全查表（G 表），族内联检保一致 |
| 条件 4 | thigh_limit（thigh>0）、shrinkage_warp/weft（描述显式提及）、size_label | 规则/摘录 |

**模型直接经手的仅 ~20 键**（11 开关 + 6 形态枚举 + 轴 override），其余全部代码产出。**扩展路径**：custom 形态自由角点（模型出归一化角点坐标）等更深键，按「判据手册加厚 + eval 对比通过」逐批加入（二期）。

<details><summary>完整发射键逐个清单（87 键）</summary>

① 尺寸 8：waist/hip/knee/hem/front_rise/back_rise/outseam + thigh(可选)
② 开关 11：front_pocket/front_pocket_facing/front_pouch/front_patch/watch_pocket/back_patch/back_yoke/back_dart/belt_loop/fly/fly_separate
③ 形态枚举 6：waistband_type、fit、back_patch_shape、front_pocket_mouth_mode、front_pocket_facing_mode、watch_pocket_mode
④ 弯曲框架 9：front_intake_ratio、back_intake、delta、waist_balance、rise_adjust、front_crotch_adjust、crotch_drop_adjust、knee_adjust、hem_adjust
⑤ 前口袋族 9：front_pocket_p1_dist、p2_drop、dart_width、paring_n、mouth_bulge、mouth_bulge_at、mouth_h1、mouth_h2、mouth_corners
⑥ 袋贴族 4：facing_width、facing_side_w、facing_h1、facing_h2
⑦ 袋布族 4：front_pouch_waist_safe、side_safe、nodes、edges
⑧ 小表袋族 8：watch_pocket_width、taper、offset_from_top、offset_from_side、rotate_deg、points、edges、mode
⑨ 后贴袋族 9：back_patch_inset_x、drop_y、width、height、bottom_width、tip_depth、chamfer、rotate_deg、custom_points/edges
⑩ 机头+腰省 5：back_yoke_cb_dist、side_dist、back_dart_count、width、length
⑪ 门襟族 5：fly_width、fly_length_ratio、fly_length_base、fly_corner_inset、fly_sep_double
⑫ 裤耳+腰头 5：belt_loop_width、unit_length、count、waste、waistband_width
⑬ 条件 4：thigh_limit、shrinkage_warp、shrinkage_weft、size_label

</details>

## 新增文件

包：`src/ylpattern/extract/`（与 reverse/ 对称的输入侧平行包；依赖 `flows.closure + params(+validate) + stdlib`，与 cli 同层，不 import reverse、不走 api.run——探针要纯内存 (m,o)→ctx，与 `_cmd_draft` 同一入口）：

| 文件 | 职责 / 关键接口 |
|---|---|
| [src/ylpattern/extract/\_\_init\_\_.py](src/ylpattern/extract/__init__.py) | `KeyMeta(key,value,source,confidence,evidence)`（source: 描述/照片/预判/查表/派生/默认/回退/回喂）、`ExtractResult(...,to_web_payload())`、`extract_from_input(*, describe, photos, provider=None, thinking, run_probe=True, run_score=True, max_refeed=2, config_path)` 一条龙 |
| `provider.py` | `VLMConfig.load()`（优先级 显式 path > ./vlm.toml > 环境变量 YLP_VLM_*，均缺 raise）、`OpenAICompatibleVLM.complete(prompt, images, thinking)`（**唯一触网文件**，urllib stdlib）、`FakeVLM(responses)`（队列重放+calls 记录） |
| `parse.py` | S1 描述解析：`parse_describe(text) -> ParsedDescribe{measurements, hints, size_label}`（正则+同义词典+尺码换算）；S2 响应解析：`parse_model_json(text)`（围栏/散文/花括号容错）、`sanitize(raw) -> Observation` |
| `prejudge.py` | `prejudge_axes(measurements, hints) -> dict[轴, (档, 依据)]`（按 B 表锚点算预判）；`prior_switches() -> dict`（D 表先验） |
| `schema.py` | 白名单/枚举值域 + `build_prompt(describe, prejudged, priors, photo_count)`——注入已知尺寸/预判/先验/手册判据段落，与手册同源 |
| `derive.py` | 档位表集中地：`merge(observation, prejudged, priors)`（override 需 evidence，低置信采预判/先验）、`derive_all()`、`front_intake`（基准带+四维修正）、`resolve_delta`、`curvy_rules`、`dart_balance()`（全局余量排除法→育克/省道组，前口袋和育克转移省预测.md 对应）、`watch_pocket_companion`；每函数注知识库条目号 |
| `families.py` | 部件参数族模板（G 表）：`part_family(part, axes, measurements) -> dict`——部件开关开启即全族发射，族内联检；腰位联动机头宽、形状分模板 |
| `validate.py` | `validate_candidate()`＝包一层 `params.validate.build_issues`（零复制复用）；`issue_keys()` 归因到候选键 |
| `probe.py` | `run_probe(m,o) -> ProbeOutcome(ok,message,error_keys,trace_tail)`、`probe_loop()`（L0~L4 状态机）、`fallback_value(key)`＝dataclasses.fields 默认值 |
| `score.py` | `score_features(ctx) -> list[ScoreItem(特征,实测值,区间,verdict)]`（F 表业务区间） |
| `emit.py` | `build_size_file()`（发射前 `Measurements.from_dict`+`PatternOptions.from_dict` 回验；口径同 reverse/emit.py：圆整 0.1/0.01、`_` 备注行、子表后置）、`write_outputs()` |
| `report.py` | `render_extract_report()`：款式摘要（预判 vs 照片 override 轨迹）+ 逐键表 `键|值|来源|置信度|依据`，**conf<0.7 ⚠ 标黄**；合理性警告/默认回退/丢弃未知键/探针 trace/降级披露各一节 |

配套：`vlm.toml.example`（项目根，入 git）、`.gitignore` 追加 `vlm.toml`、`scripts/eval_extract.py`、`tests/_extract_golden/cases/<case>/{describe.txt,truth.toml,photos/}`（photos gitignore，一期 1 个示例 case）、`.doc/参数预测/参数推测知识库.md` + `款式判据手册.md`。

## 关键实现要点

### 1. provider 踩坑清单（全部已实测，必须落实）
- 端点默认 `https://open.bigmodel.cn/api/coding/paas/v4`（Coding Plan 套餐 key）、模型默认 `glm-5.3-flash`；glm-4v-flash 失明不可用（docstring 黑名单注明）。
- 恒**流式 SSE 按行 read**，idle 超时按「两次有数据行间隔」计（默认 300s），不设整包短超时。
- `max_tokens ≥ 16384`（推理模型思维链计入 completion，8192 会掐断 JSON）。
- `thinking` 参数默认**不发送**（服务端默认）；CLI `--thinking on|off` > vlm.toml > 环境变量；HTTP 400 自动摘参重发一次并 sticky。
- 照片读文件 + base64 data URI 只存在于 provider 层；`extract/__init__` 顶层不 import urllib，cli 的 import 放 `_cmd_extract` 函数体内（对齐 `_cmd_reverse` 惰性先例）——无配置环境跑测试零影响。

### 2. 模型调用：S1 补漏小调用（纯文本，可免）+ S2 视觉确认主调用（≤2 次回喂）
S1 正则全中则零调用；漏键才发一次纯文本「只从描述提取这些数字键，找不到给 null」。S2 prompt 给**预填模板**（已知值/预判档/先验默认都填在 JSON 里），模型任务变成「编辑确认」——认知负荷最低、最稳。每键输出 value/confidence/evidence；推翻预判必须写照片判据，判据不足 conf≤0.5 且会被 merge 拒绝。

### 3. validate + probe（L0~L4）
静态：`build_issues`（含跨选项前置）+ 派生区间复核。探针状态机：L0 试跑通过→产出；L1 错误归因（①构造期异常→Issue.param；②引擎期异常消息对候选键子串匹配）→回喂只重出被归因键，≤2 轮；L2 逐键回退引擎默认再探；L3 降级关触发开关再探、报告披露；L4 仍失败（如 waist<64）→ 不阻断产出，header 注明「探针未通过」+ 报告人工处理段，`--draft` 拒绝直出（退出码 2）。

### 4. 产物
- `out/extracted.toml`：与 examples/ 同构直接可喂 `ylpattern draft --size`；header 注来源（描述摘要/照片数/模型/探针结论）；每键行尾 `# 来源：…`。
- `out/extract_report.md`：见 report.py 职责。
- `ExtractResult.to_web_payload()`：`{measurements, options, keys:{k:{value,source,confidence,evidence}}, issues, probe_log, score}`——二期 `POST /api/extract` 直接 JSON 化，前端预填现有表单走现有确认出图流。

### 5. CLI（挂 [src/ylpattern/cli.py](src/ylpattern/cli.py) main()，对齐 reverse 先例）
```
python -m ylpattern.cli extract --photo front.jpg --photo back.jpg \
    --describe "女款高腰微弹小脚牛仔裤，腰围74 臀围91 …" \
    --out-dir out [--draft] [--thinking on|off] [--no-geometry] [--no-score] \
    [--config vlm.toml] [--max-refeed 2] [--report PATH]
```
必填 7 键尺寸最终缺失 → 列缺失键清单退出码 2，**不编数值**；`--no-geometry` 跳探针、`--no-score` 跳评分（快路径，报告注明）；配置/输入错误 → stderr + 退出码 2。

### 6. 测试（金标风格，FakeVLM 全程不触网）
- `test_extract_parse.py`：正则解析（全半角/别名/码号换算 29→74）、同义词典命中、JSON 容错/白名单/枚举归一。
- `test_extract_prejudge.py`（**金标**）：B 表锚点逐带断言（front_rise 28.5/26/22.5 边界）、hem/hip 比例分档、curvy 判定。
- `test_extract_derive.py`（**金标**）：C 表联动（rise_adjust 档、前中基准带+四维修正含实战案例 2.2 断言、15:X 臀腰差插值、放码归一化、ratio 记账精确断言、DELTA 路由、curvy 联动）、**余量排除法**（手工演算 R=(H−W)/2：H−W=12 有育克余量尽归育克无后省 / 无育克 H−W=22 缺额 2.0 单省 / 无育克 H−W=28 缺额>2.5 双省 / 宽松差小渠道溢余无省）、watch_pocket 配套包。
- `test_extract_merge.py`：override 无 evidence 拒绝采预判；低置信采先验；词典 hint 优先于照片。
- `test_extract_pipeline.py`：FakeVLM 端到端（S1 全中零调用/漏键补漏调用/S2 编辑确认）；缺必填尺寸退出码 2。
- `test_extract_probe.py`：必炸组合归因→回喂→耗尽回退→降级，逐层单测。
- `test_extract_score.py`：构造失衡组合（袋口占比 59% 配例）出警告。
- `test_extract_emit.py`（**回环金标**）：write_outputs → load_size_file → from_dict → run_with_thigh_closure 真跑通过。
- `test_extract_cli.py` / `test_extract_provider.py`：CLI monkeypatch、无配置报错；SSE 假 socket 解析、thinking 400 摘参、vlm.toml/env 优先级。
- `scripts/eval_extract.py`：金标集评测（数值键 MAE/超差比例、开关与轴命中率、8 键召回与**编造率**、探针通过率/回喂轮数/评分警告率），markdown 输出 + `--baseline` 两轮 diff——**每批判据/词典知识入系统前后必须跑 eval 对比**。

### 7. 文档先行（第一批交付物）
- `.doc/参数预测/照片提取设计.md`：§0 范围分期 / §1 职责边界表 / §2 输入约定（建议正/背面平铺照、描述含 7 必填尺寸+面料弹力）/ §3 提取面 schema 与注入协议 / §4 派生口径索引（指向知识库条目号）/ §5 校验回喂与评分协议 / §6 产物格式 / §7 provider 与配置 / §8 金标集与评测口径 / §9 风险对策。
- `.doc/参数预测/`（**知识库本体=用户收集的参数组文件**，一参数组一文件，2026-09 已有 4 篇）+ 索引 `参数推测知识库.md`（参数→输入依赖总表 + 条目索引 + 冲突裁定记录）：每篇**固定字段头：输入依赖 → 判定/推导规则（正文原文）→ 区间内定位规则（锚点插值/轴向偏移/中值兜底）→ 对应引擎键 → 边界反例**——推测规则的唯一权威，代码函数一一对应抄录。
- `.doc/参数预测/款式判据手册.md`：视觉判据（怎么看），prompt 同源。

## 明确不做（一期）
webapp 端点与前端；照片预处理；self-consistency 多数表决；多码 size_run 推断；评分出界自动回喂改参（一期只警示）；金标集批量采集。

## 实施顺序
① 设计文档 + 知识库（**4 篇收集文档就地补固定字段头 + 建索引**，见「本次执行范围」；旧前中内收量推导 §三 加注取代）+ 判据手册 → ② provider + vlm.toml.example + .gitignore → ③ parse（S1）+ prejudge（+金标测试）→ ④ schema + S2 注入协议 → ⑤ merge + derive + families（+金标测试，含族内一致性联检）→ ⑥ validate + probe（+测试）→ ⑦ score → ⑧ emit + report（+回环金标）→ ⑨ `__init__` 管线缝合 + CLI（+测试）→ ⑩ eval 脚本 + 示例 case → ⑪ CLAUDE.md 补 extract 用法。

## 验证
1. `python -m pytest tests/ -q` 全绿（FakeVLM 注入，无 VLM 配置环境不受影响）。
2. 真实端到端：配好 vlm.toml 后 `python -m ylpattern.cli extract --photo out/front.jpg --photo out/back.jpg --describe "…腰围74 臀围91 …" --out-dir out`，检查 out/extracted.toml + extract_report.md（预判/override 轨迹、评分段）。
3. 回环：`python -m ylpattern.cli draft --size out/extracted.toml --svg out/sheet.svg --report out/report.txt` 出图；再跑 `extract --draft` 直出对照一致。
4. `python scripts/eval_extract.py --cases tests/_extract_golden --config vlm.toml` 出基线报告。

## 修改的既有文件
- [src/ylpattern/cli.py](src/ylpattern/cli.py)：main() 挂 extract 子命令 + `_cmd_extract`（惰性 import）+ 模块 docstring 用法。
- [.gitignore](.gitignore)：`vlm.toml`、金标 photos。
- [CLAUDE.md](CLAUDE.md)：常用命令段补 extract 用法一行。
- [.doc/前中内收量推导.md](.doc/前中内收量推导.md)：§三 加注「预测口径已被 参数预测/前中内收预测.md 取代（引擎公式与默认 ratio 0.2 不变）」。
- [.doc/参数预测/](.doc/参数预测/) 4 篇收集文档：补固定字段头 + 对应引擎键标注（本次执行范围 1）。
- 新建 `src/ylpattern/extract/`（12 个模块）、`tests/test_extract_*.py`（9 个）、`scripts/eval_extract.py`、`vlm.toml.example`、`.doc/参数预测/照片提取设计.md` + 索引 `参数推测知识库.md` + `款式判据手册.md`。
