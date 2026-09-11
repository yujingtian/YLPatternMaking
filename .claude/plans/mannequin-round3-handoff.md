# 交接文档：3D 人台形体第三轮（矢状 S 曲线 + 腿节奏样条化 + 环棱线消隐 + 脚/肚脐）

> 交接时间：2026-09-10。前一窗口已完成全部诊断、方案设计与两轮用户拍板，**方案已定稿但尚未获 ExitPlanMode 正式批准、尚未动一行代码**。新窗口从「实施」接起。
> 同名正式计划文件：`C:\Users\MI\.claude\plans\enchanted-splashing-engelbart.md`（内容与本档 §五 一致，自包含可不看）。

---

## 一、任务一句话

3D 试穿 tab 的人台（webapp/frontend/src/fitting3d/）数字金标全绿但**观感不像真人**——本轮按已定稿方案做第四轮形体修复：**C 矢状 S 曲线塑形 + A 腿节奏样条化/X 站姿 + B 环棱线消隐 + D 脚和肚脐**，然后视觉验收（VLM 逐项解剖核对 + 用户目检），最后把 `RENDER_GARMENT` 改回 true 恢复裤子渲染。

## 二、背景演进（已发生的事，勿重做）

1. **一期（2026-09-09 前）**：三管 tubeMesh 装配体（骨盆 + 双腿环模型）——分体感严重。
2. **SDF 蒙皮轮（2026-09-09）**：tubeMesh 删除，改 `skin.ts` 单张水密 SDF 蒙皮（三管 smin 软并集 + 自写 marching cubes），融合半径分对 kPL=0.75 / kLL=0.6 由解耦金标锁死。规格见 .doc/python工程设计.md §10.11「SDF 蒙皮」节。
3. **emergence 轮（2026-09-10）**：buildMannequin 重写「外缘连续 emergence」——删 containment、腿环统一构造式 `cx = max(a+gap(y), min(outer(y)−a, 0.55×W_h))`、外缘/内缘双梯子、calf 站、crotchGirthRatio 0.85。**78/78 测试全绿**。规格 §10.11「人台人体化」节。
4. **视觉验收两轮截图（正/侧）**：数字全绿但用户否决观感 → 引出本轮。

当前 `RENDER_GARMENT = false`（Fitting3DView.tsx 顶部常量，~L46）：人台验收期 3D 场景只显示人台、布料/腰头/热力图/透明度等全部跳过（solver 照常解算）。**人台验收通过后改回 true 是收尾步骤**。

## 三、用户反馈与拍板记录（时间序，新窗口别再问已拍板的事）

1. 正面截图反馈：**「这是目前生成的效果，你看看符合正常人体形态么」** → VLM 识图结论「形对神不够」三缺陷：柱状腿 / 水平环棱线 / 腰线弱。
2. 侧面截图反馈：**「这是侧面图，臀部也不自然，人的屁股是曲线」** → 臀部矢状 S 曲线缺失（腰椎内收→臀峰外凸→臀底褶）。
3. AskUserQuestion 拍板①：三处改动（矢状塑形 C / 腿节奏样条化 A / 环棱线消隐 B）→ **「C+A+B 全做」**。
4. AskUserQuestion 拍板②：腹部前侧小腹要不要微凸 → **「微凸」**（bellyBias 1.10）。
5. ExitPlanMode 否决①：**「你再仔细检查下改动方案，能不能生成一个符合人体形态的人台」** → 方案补了肋弓外扩站（腰=全局最窄）、popliteal 腘窝 0.93、Achilles 跟腱 0.92、dress form 级保真度框架、矢状目标剖面表。
6. ExitPlanMode 否决②：**「还得把脚，肚脐眼也生成出来」** → 方案补 D 节（脚 + 肚脐），计划文件已更新。
7. 之后一次 ExitPlanMode 被打断（用户切模型 + 要交接文档），**非内容否决**；plan mode 现已退出。新窗口开工前建议把 §五 方案给用户过目一眼或直接按用户指示实施。

## 四、代码级根因（mannequin.ts / priors.ts 已读实，改前重读这两文件）

- **④ 臀部矢状直线锥**：骨盆每环 bB = 围度标定 a × **常数** backBias（hip 档 1.12 从 y=86 直用到楔底）→ bB 峰钉死在臀站、向下单调递减 = 直线背。腰椎内收（~0.85）/臀峰下移（真人臀峰在臀线下 ~4.5cm ≈ y82，bias 需 ~1.30）/臀底褶三段全无。
- **③ 腰线弱**：躯干上段腰以上**单调收窄**（66→60.7@+18），腰是上段最宽点；真体下肋围 ≈1.06×腰围，**腰须为全局最窄点**才读得出腰线。
- **① 腿柱感**：outerLadder 分段线性 = 直线渐缩、无小腿肚外缘锚；膝下两腿平行 ~3cm 无 X 站姿；矢状缺腘窝/跟腱。
- **② 水平环棱线**：sectionAt 环间**线性插值**（~4cm 折点）+ 形状参数（e/depth/bias）**kind 档位跳变**（ring map `y > yHip−1 ? ... : 'hip'`）被 MC spacing 1.0 如实画出。
- **脚/脐缺失**：腿在踝下穹顶截断（bottomY=−8），GridHelper 在脚口高度 y=0 → 人悬空；前腹无脐。

**关键架构结论**：脚是水平前伸形状，环模型（y 降序超椭圆放样）表达不了 → 必须走 SDF 场加原语；肚脐是 θ 局部凹坑，环参数也表达不了 → 同走 SDF 凹刻。碰撞/摆位路径（collide.ts/seams.ts 只走三管环）**零改动**——脚顶 ≤ −8.8 全低于脚口 y=0，布料永不可达。

## 五、定稿方案（C+A+B+D，改动落 priors.ts + mannequin.ts + skin.ts + Fitting3DView.tsx；seams.ts/pbd/ 零改动）

**保真度目标**：dress form 级解剖保真——矢状 S 曲线（腰凹/臀峰/臀底褶/腘窝/小腿肚/跟腱）、正面腰-肋-臀对比、腿 X 节奏、双脚（站立微外八）、肚脐凹刻。**非目标**：臀沟（破左右对称）、膝盖骨/肌肉刻线、足弓/趾形细节（圆角盒风格化脚）。

### C 矢状塑形（前后深随 y 连续变化）

- priors.ts 新段 `SAGITTAL`（存比率/偏置；绝对 y 锚在 mannequin 按站点组装，同 outerLadder 模式）：
  - backBias 梯子：waist 1.0 → 腰椎谷 `lumbarBias 0.85` @ (waist+hip)/2 → hip 1.12 → 臀峰 `gluteBias 1.30` @ hip − 0.45×(hip−crotch) → crotch 0.95 → 楔底 0.85
  - frontBias 梯子：waist 1.0 → 小腹 `bellyBias 1.10` @ hip − 0.35×(hip−crotch) → crotch 0.96 → 楔底 0.90
  - 腿 backBias 梯子：crotch 1.0 → knee 0.93（腘窝）→ calf 1.12（小腿肚后凸）→ hem 1.0 → ankle 0.92（跟腱）
- `sectionShape`（mannequin.ts L44-53）增 bias 形参：周长标定用实际 (depth, depth×backBias) → a 同步重算，**每环围度精确不变**；站点环 bias 锚 = 现值 → 单原语站金标天然保住。
- **肋弓外扩**：躯干延伸段站点表 [top, waist] 两点改三点 [torsoTop(+18, 0.88×waist), **rib(+9, 1.06×waist)**, waist]。新常数 ribRiseAboveWaist 9 / ribGirthRatio 1.06 / torsoTopRatio 0.92→**0.88**。

### A 腿节奏（样条化 + X 站姿）

- mannequin.ts 新增 `monoSplineAt`（Fritsch–Carlson 单调三次 Hermite，~30 行）：保单调、无过冲、结点导数 ≤3×局部割线 → 外缘最陡割线 0.102×3=0.31 ≪ Lipschitz 不变量界 0.7。
- outerLadder ladderAt→monoSplineAt，加 `outerAtCalf 0.80`（thigh 0.97 / knee 0.78 / **calf 0.80** / hem 0.70 / ankle 0.62，calf 为结点局部极大）。
- gapLadder **维持线性**，X 站姿重调：gapAtKnee 1.5→**0.8**、新锚 gapAtCalf 1.6、gapAtHem 1.3→**1.8**、gapAtAnkle 1.2→**2.2**（膝靠拢、小腿/踝微外展；踝处下限绑定 → 外缘比 0.636 仍在金标带 [0.55,0.70]）。
- cx 构造式/下限优先不变；「cx 不进样条」注释口径更新。

### B 环棱线消隐

- sectionAt（mannequin.ts L273-292）：a/bF/bB/e 线性→monoSplineAt（C1；站点环 y 处 Hermite 精确过点 → ±1e-6 金标不破）；**cx 保持线性**（碰撞 Lipschitz 论证依据）。
- 骨盆 sampleStations step 4→**2**（臀峰特征宽 ~4-6cm；环数 13→~25）；腿维持 4cm。
- 形状参数（e/depth/bias）kind 档位 → **y 向连续梯子**（pelvis：top 2.2→waist 2.3→hip 2.15→楔 2.15；legs：crotch 2.2→knee 2.3→calf 2.3→hem/ankle 2.2，depth 同构 + calf 1.03）——SECTION_PRIOR 退化为锚值表，ring map 的 kind 档位跳变整类消失。
- 头带 headLadder 维持线性三锚（贴盆凸坡、深藏盆内）。

### D 脚 + 肚脐（SDF 场加原语）

- **脚**：每脚两个**绕 Y 微外八 7° 的圆角盒** SDF——后段（足跟/足弓，宽 7.6 高 6.4）+ 前段（脚掌/脚趾，宽 8.6 高 4.6，总长 22.5cm、跟后伸 5.5cm）——相互 smin（k~1.2）再与腿管踝穹顶 smin（新分对 blendKLegFoot 0.75）。站立地面 y=−15（踝 −8 下方）；脚盒中心 x 取踝环 cx、z 前移 ~5.75（踝关节在脚后 1/3）。priors 新段 `FOOT_PRIOR`（绝对 cm，病理夹具共用标准脚）。Mannequin 增 `feet: [FootParams, FootParams]`（构建期算好盒心/半轴/旋转）+ bottomY 扩至 −15。
- **肚脐**：小椭球 **smax 凹刻**（smax(a,b,k) = −smin(−a,−b,k) 恒等式，紧支族不变）：中心挂前腹表面（y = waist − navelDrop 4.5，z 由 radiusAt 当环求出再内移 ~0.2，半轴 ~1.2/1.4/0.9 → 凹深 ~0.45、光滑唇缘）。priors 新段 `NAVEL_PRIOR`。注意 y≈93.5 距站点环 98/86 均 >2cm，不碰站点金标。
- **skin.ts**：skinField 末段接 smax(…脚…, navel)；MC bbox 扩（z 至 +22/−14、y 至 −15）；法线走场梯度自动光滑。
- **解耦金标两处定点改动**：①「smin≤min 单侧性」加**脐区豁免**（脐半径带内 skinField − unionField ≤ 0.5，注释布料最小间距 1.2 ≫ 凹深；带外原样）；②参照 unionField **收编脚盒**（脚是向外新几何，不收编则双测度对脚全红）。collide/seams 代码零改动。
- **Fitting3DView.tsx**：GridHelper 从 y=0 挪到 `man.bottomY`（脚踩地面不再悬浮）；其余零改动。

### 矢状目标剖面（165/66A，dump 验收标准，实施轮微调常数逼近）

后侧 bB（cm）：8.7@腰98 → ~7.8@92 腰椎谷 → 13.35@86 臀线（金标钉死不动）→ **~14.7@82.4 臀峰** → ~9.6@78 臀底褶 → ~8.6 大腿后侧 → ~8.0@42 腘窝 → 小腿肚峰@35 → 踝跟腱收。
前侧 bF：8.7@98 → 11.92@86（金标钉死）→ **~12.3@83 小腹峰** → 裆收。

已验算参考数：W_h=15.889；臀站 bF=11.92/bB=13.35、腰站 a=11.65/bB=8.74；y82 处腿环下限绑定（cx≈7.45、腿外缘 16.1 > 盆 a 15.1）；臀峰 bias 使头带 outerTop 缩 ~2.5%（可接受）。

## 六、金标/不变量约束（实施时必须存活，重校 ≠ 放松）

1. **单原语站精确支配**：腰 98/臀 86/膝 42/脚口 0 逐射线 R_skin==radiusAt ±1e-6（站点锚值不动即天然保住）。
2. **站点围度**：单原语 ±0.5%、thigh ±2% + 裆侧回退 ≤120 方向（sectionShape 重标定后围度精确不变）。
3. **解耦双测度 ≤ garmentGap 1.2**（蒙皮外凸上界；超限时**先降 kPL 0.75→0.65 / blendKLegFoot，绝不动 garmentGap 阈值与 girthTolThigh**）。
4. **外缘 Lipschitz ≤0.7 @0.5cm**（monoSplineAt 导数界 0.31 有余量）。
5. 接触带符号：(0,68,0) 负 / (0,66,0) 正 / y79 侧向精确 min（y=66 gap 锚 0.3 不动，预期保绿）。
6. 集成穿透容差 −0.1（后浪布料跨更凸臀部需复验）。
7. 「最宽点在臀」argmax ∈ [80,82] 且 ≤ a_hip+0.5（臀峰下移后此不变量可能要随目标剖面重校——是有意变更，重校不是回归）。
8. MC：栅点 ≤45 万（bbox 扩后复测）、三角 ≤30000 预算循环、标准夹具 V−E+F=2、外向绕向。
9. **新增不变量**（写进 fitting3d.test.ts）：矢状（bB 臀峰位 ~82/腰椎谷/小腹峰/腘窝）、**腰最窄**（argmin(a) ∈ (waist−2, waist+2) 且 a(rib) > a(waist)）、脚/脐参数断言（feet 盒在 bbox 内、y < 裤口−20、navel 在前表面法向带内）。

## 七、环境与命令速查（Windows 坑，前窗口踩过的）

- 全部前端命令**必须** `cd /d/work/YLPatternMaking/webapp/frontend &&` 前缀（裸 npm/tsc 报 ENOENT）。
- 检查/验收：`npx tsc -b && npm test && npm run build`（**78 测试为基线**，本轮会加新不变量）。
- 后端：**用户自己的 uvicorn 已驻 8000**（勿再起；新起会 10048 静默退出）。StaticFiles 每请求读 dist → `npm run build` 后浏览器刷新即可看到新效果，无需重启后端。
- 视觉验收用 **mcp__4_5v_mcp__analyze_image**（只收远程 URL，不收本地路径——截图需先传可访问地址；prompt 里要写明已知简化/截断防误报缺陷）。前窗口流程：3D tab 截图 → VLM 解剖特征逐项核对 → 不达标回 dump 调常数。
- Edit old_string 含全角 Unicode（→ ′ − ×）易失配 → 改用纯中文/ASCII 子串锚点。
- `python3 <<EOF` heredoc 在 Git Bash 挂起 → 写临时脚本文件再 `python` 跑。
- 集成测试（fitting3d.integration.test.ts）33-36s，vitest 需 60s 超时。

## 八、当前工作树状态

git status 已改（上一轮 emergence 工作的未提交存量）：`fitting3d/Fitting3DView.tsx / fitting3d.integration.test.ts / fitting3d.test.ts / mannequin.ts / priors.ts / skin.test.ts` + 两篇 .doc 文档——**全部是已完成已测（78/78 绿）的上一轮改动，非本轮**。本轮直接在其上继续改（用户未要求分批提交，沿用单线演进）。

## 九、实施顺序（定稿）

1. priors.ts 常数（SAGITTAL / FOOT_PRIOR / NAVEL_PRIOR / outerAtCalf / gap 重调 / rib 锚 / torsoTopRatio 0.88 / blendKLegFoot；SECTION_PRIOR 注释改「锚值表」）。
2. mannequin.ts（monoSplineAt + sectionShape bias 形参 + pelvis 肋锚/step 2 + 形状梯子化 + feet/navel/bottomY + sectionAt 样条化；头注更新）。
3. skin.ts（脚盒场 + smax 脐凹刻 + bbox 扩展）。
4. **dump 调参**：临时脚本打 bB/bF vs y（0.5cm 步）对照目标剖面、剪影 outer 复核、脚盒前/侧视截面 → 微调 SAGITTAL/FOOT 常数。
5. fitting3d.test.ts 重校 + 新增矢状/腰最窄/脚脐不变量 → skin.test.ts 重校（解耦双测度裁决，超 1.2 按第六节 3 降融合半径）→ integration 复跑。
6. 全量 `npx tsc -b && npm test && npm run build`；Fitting3DView GridHelper 落地。
7. **视觉验收循环**：刷新 http://127.0.0.1:8000（3D tab）→ 正/侧/斜 + 低角度截图 → VLM 逐项核对（腰凹/臀峰位/臀底褶/小腹+脐/腘窝/小腿肚/跟腱/腰最窄/双脚落地）→ 用户目检；体型抽屉切 1-2 个病理预设看不炸（脚用标准常数不随病理缩放）。
8. 文档同步：.doc/python工程设计.md §10.11「人台人体化」补现行规格（矢状塑形/样条化/脚/脐/保真度口径）；决策日志 §十一 新条目（口径演进过程全归日志）；记忆 `mannequin-shape-root-cause.md` 更新。
9. **收尾另一步**：人台验收通过后 RENDER_GARMENT 改回 true + rebuild + 裤子恢复目检。

## 十、口径提醒（写文档/测试时别踩）

- 规格文档只写现行规格；日期/废弃方案/纠偏过程归决策日志 §十一。
- kPL/kLL/blendK 由解耦金标锁死，「抬 k 让融合更软」类提议必须先过双测度。
- cx 不进样条是碰撞路径 Lipschitz 论证的前提，别顺手样条化。
- 布料（seams/pbd/collide）与蒙皮（skin）解耦是设计前提：布料永远走解析三管；本轮脚/脐只进蒙皮与解耦参照，不进碰撞。
