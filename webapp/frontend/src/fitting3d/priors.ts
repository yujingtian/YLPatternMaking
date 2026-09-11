// 3D 试穿先验常数表（唯一收敛点）。
// 全部为**非引擎数据**：前端体型估计/放样/解算的经验常数，按 165/66A
// 女体标定；改这里不需要重打引擎 zip（引擎零体型先验，§10.11）。

// ---- 体型默认估计（成衣围 -> 人体围的先验松量，cm） ----
// 用户口径 2026-09-09：成衣量含调节量不能当人体量；此表仅生成「估计值」
// 默认，用户可在体型设置中改成真实测量值
export const EASE_PRIOR = {
  waist: 1.5,
  hip: 5,
  thigh: 4,
  knee: 3,
} as const

// 估计下限：人体围 >= 0.85 × 成衣围（防负松量翻车出怪体型）
export const BODY_MIN_RATIO = 0.85

// ---- 体型比例（缺省站点补全 + 腿管人体化梯子） ----
export const BODY_RATIO = {
  // 体型缺大腿围：虚拟站点围 = hip × ratio、高度 = crotch − 3cm
  thighGirthRatio: 0.62,
  thighStationDrop: 3,
  // 脚口以下腿延伸（cm）：锥缩到 ankle = hem 围 × ratio（踝部无成衣对应）
  legExtendBelow: 8,
  ankleRatio: 0.72,
  // 骨盆管在分叉高（crotch）处的围 = hip × ratio（裆部分叉收细）。
  // 0.94→0.85（2026-09-10 人体化：骨盆不再近臀宽直到裆的直筒块）；
  // 五轮 0.85→0.83：新矢状偏置（crotch 前 0.80/后 0.88）使同围 a 反涨、
  // aHip−aCrotch 跌破 1.2 金标，0.83 保差 ≈1.5
  crotchGirthRatio: 0.83,
  // 腰上躯干延伸（cm）与顶围收细比。2026-09-10 第四轮 0.92→0.88 + 新增
  // 肋弓外扩锚 ribRiseAboveWaist/ribGirthRatio（下肋围 ≈1.06×腰围）——
  // 躯干上段腰以上不再单调收窄，腰成为全局最窄点（治「腰线弱」：旧两锚
  // [top 0.92, waist 1.0] 使腰=上段最宽点，真体下肋围≈1.06×腰围）
  torsoExtend: 18,
  torsoTopRatio: 0.88,
  ribRiseAboveWaist: 9,
  ribGirthRatio: 1.06,
  // ---- 腿管人体化（2026-09-10：外缘连续 emergence 替代 containment 藏头） ----
  // 腿环逐环派生 cx = max(a+gap, min(outer−a, cxMaxRatio·W_h))：
  //   · outer 外缘目标梯子是第一构造目标（最宽点在臀带、大腿外缘与臀线
  //     连续、膝/踝按人体比例收窄——治「两根等粗柱子」）；
  //   · gap 内缘下限梯子是物理可行性约束（治纯外缘反解的内缘跨中线 23cm
  //     融合腿与病理负 cx：cx ≥ a+gap 恒正，粗腿体型外缘超标=腿确实比盆宽
  //     的诚实降级）；
  //   · 下限优先于上限（腿不能窄过贴腿、不能宽过外缘目标太多）。
  // 外缘梯子锚点（×W_h=臀站半宽，2026-09-10 第四轮起逐环单调样条
  // monoSplineAt——分段线性直线锥是「柱状腿」根因之一；y 锚点在 mannequin
  // 按站点组装；calf 站新增显式锚：膝局部最窄 + 小腿肚局部最凸（结点导数
  // 取 0 的平滑峰谷；monoSplineAt 保单调无过冲、结点导数 ≤3×割线，外缘
  // Lipschitz 界仍由构造可证）：
  outerAtThigh: 0.955,  // 大腿站（其上 crotch~yThigh 段夹此值；五轮b
                        // 0.97→0.955：0.97×W_h≈15.23 与臀 15.70 夹 78-84
                        // 段谷成双峰，0.955→14.995 使大腿带沉到臀线下）
  outerAtKnee: 0.78,    // 膝（真人膝外缘 ≈0.75-0.82×臀半宽）
  outerAtCalf: 0.80,    // 小腿肚（结点局部极大）
  outerAtHem: 0.70,
  outerAtAnkle: 0.62,
  // 内缘下限梯子（cm，cx−a ≥ gap；负=允许越过中线贴腿）。2026-09-10 五轮
  // 「明显缝隙」重设（移除四轮的 y68~78 十厘米大腿接触带——其下 0.3~0.8cm
  // 微缝在 kLL 桥接窗与 MC ≥2cm 可辨阈之下，视觉焊死）：裆环 −2.5（五轮b
  // −1.8→−2.5：75 环 a+gap≈7.16 压过外缘目标差 6.76，gap 反绑外缘成 15.4
  // 微峰，−2.5 让 73~78 段外缘目标接管、大腿带整体沉回臀线下）→
  // gapOpenBelowCrotch 处过零（分离点=裆下 ~5cm）→ 大腿中段 1.4（缝宽
  // 2×gap=2.8cm 仍稳可辨，outer@66≈15.1=臀宽−0.6——真人大腿带即臀宽带）
  // → 膝 1.2 / 小腿 1.6 / 脚口 1.8 / 踝 2.4 X 站姿梯度；中腿锚
  // y=crotch−gapMidDrop（与 midThighGirthRatio 围度锚同 y）。维持线性
  // （cx 不进样条是碰撞路径 Lipschitz 论证前提，勿顺手样条化）
  gapAtCrotch: -2.5,
  gapOpenBelowCrotch: 5,
  gapMidDrop: 12,
  gapAtMidThigh: 1.4,
  gapAtKnee: 1.2,
  gapAtCalf: 1.6,
  gapAtHem: 1.8,
  gapAtAnkle: 2.4,
  // 中腿围度锚 = thigh × ratio @ crotch−gapMidDrop（站间围度自由、thigh 站
  // ±2% 金标不碰）：开缝联动收腿管——无它则 a@66≈7.45、outer=2a+2.0≈16.9
  // 超 maxOuter 预算；0.85 → a@66≈6.84、outer≈15.7。真人 54 大腿 9cm 下
  // 收 ~46 亦是解剖事实（兼治柱状腿）
  midThighGirthRatio: 0.85,
  // 分离点围度锚 = thigh × ratio @ yGapFill（= yGapOpen 钳入 (yMidGap+0.5,
  // yThigh−0.5)，五轮b）：[crotch,thigh] 平顶 54/54 切向使 CR 在 74 鼓出
  // girth≈53.5，gap 绑定下 outer@74≈15.9 成反超臀带的次峰（VLM 正面
  // 「下鼓包@大转子」）；0.89 → a@73≈7.3、73~75 外缘带压平 ~15.0（大腿
  // 围自裆下即缓收亦是解剖事实）
  gapOpenGirthRatio: 0.89,
  // cx 上限（×W_h）：防外缘目标把细腿腿心推到盆壁外
  cxMaxRatio: 0.55,
  // 小腿肚站：膝下 calfBelowKnee cm（真小腿肌腹在膝下 5-10cm）、围 =
  // knee × ratio（gCalf 另钳 ≤thigh×0.97 防短腿倒挂；CR 过膝时先微收再凸
  // ——膝局部窄点+小腿肚均为解剖真实形态）。五轮b VLM 放大复验：7cm 站的
  // 腘窝→峰陡升被读作膝延伸、峰下长缓降把肌腹视觉重心拉到膝下 ~20cm 且
  // 呈尖峰——三件套改回纺锤：站上提 5（解剖位）+ calfBackBias 1.18→1.15
  // + achillesBias 0.92→0.95（峰下折点由 hem 1.0 平坡切向而来，抬锚摊开）。
  // 五轮c VLM 复验「下降段太直、鼓起段太短」：峰下 ~12cm 新增收拢围度站
  // calfTaperGirthRatio（中段拉进 ~0.5，肌腹视觉重心上移）
  calfBelowKnee: 5,
  // 峰下收拢站：y = calf 站下 calfTaperBelow cm、围 = knee × ratio
  // （真小腿 37.8@膝下5 → ~32.5@膝下17 → 30@脚口上，快-慢凹降而非
  // 近线性；165/66A 参考值）
  calfTaperBelow: 12,
  calfTaperGirthRatio: 0.93,
  calfGirthRatio: 1.08,
  // 头带（emergence，y∈(crotch, yTop] 直接按 outerHead 凸坡构造，不走围度
  // 站点）：yTop = min(crotch+headRise, hip−headBelow)；外缘 = 贴盆内壁
  // (flushInset) → 头 headSteepDrop cm 内陡降入盆内 headSteepDepth → 放量
  // 至 outer(crotch)=cx(crotch)+a(crotch)。凸坡保证与盆壁穿越角 ≥~40°
  // （smin 融合外凸估 ~0.5 < garmentGap=1.2 预算；线性坡 23° 估 0.92 压线，
  // 见决策日志 2026-09-10）
  headRiseAboveCrotch: 7,
  headTopBelowHip: 2,
  headFlushInset: 0.3,
  headSteepDrop: 2,
  // 五轮 1.2→0.8：1.2 把腿头挖进盆壁过深，是正面腰髋沟槽共因之一；
  // 下限 ~0.5——再浅则头带 @80.5 外缘超盆 a 破「头带贴盆」金标
  // （0.8 全段贴盆余量 0.15-0.2）
  headSteepDepth: 0.8,
  // 骨盆楔下探深度：楔底 y = crotch − 此值。五轮 5→3：楔底穹顶止于 gap
  // 过零锚（crotch−5）上方，可见分离保持在裆下 ~5cm；后浪支撑带 (crotch−
  // 2.5, crotch) 仍被楔环+腿 bB 覆盖（fixture 后浪尖 77.04 落带内）
  wedgeDropBelowCrotch: 3,
  // 楔底围 = hip × 此值（165/66A → 27cm、a≈4.4，横前后向均退入两腿壁内）
  wedgeBottomGirthRatio: 0.30,
  // 臀下填充锚（五轮腰髋沟修复，独立前瞻表手法同楔表）：抬 (crotch, hip)
  // 开区间围度。五轮b VLM 复验谷仍 1.65（0.975@hip−3 锚够不着谷底）→
  // 锚下沉 5 + 0.995：a@82 14.05→~14.9、谷深 ~0.8 自然 hip dip 级；前瞻
  // 锚 [hip, hip] 压平 CR 切向，a@84.5 微凸不超臀宽（invariant「带内
  // a ≤ aHip」不破）。锚再低/ratio>0.995 则 CR 过冲破该不变量
  fillBelowHip: 5,
  fillGirthRatio: 0.995,
} as const

// ---- 截面形状（超椭圆 |x/a|^e + |z/b|^e = 1；bF 前 +Z / bB 后 −Z） ----
// **锚值表**（2026-09-10 第四轮）：站点环取锚值；环间形状参数（e/depth/
// backBias/frontBias）由 mannequin.ts 按 y 向连续梯子（monoSplineAt）插值
// ——kind 档位跳变（ring map 二值切换）整类消失（治「水平环棱线」）。
// 调圆史：腰/臀 e 2.6/2.3→2.3/2.15（>2.4 方截面是「方盒子」观感来源）；
// 腿 depth 0.85/0.92→1.0/1.05（真腿截面近圆，深宽比<1 压宽显柱状）
export const SECTION_PRIOR: Record<string, {
  e: number       // 超椭圆指数（2=椭圆，>2 更方）
  depth: number   // bF/a 前后平均深宽比
  backBias: number // bB/bF 后凸偏置（臀 1.12 表臀凸）
}> = {
  waist: { e: 2.3, depth: 0.75, backBias: 1.0 },
  hip: { e: 2.15, depth: 0.75, backBias: 1.12 },
  default: { e: 2.2, depth: 1.0, backBias: 1.0 },
  knee: { e: 2.3, depth: 1.05, backBias: 1.0 },
  calf: { e: 2.3, depth: 1.03, backBias: 1.0 },
}

// ---- 矢状塑形（2026-09-10 第四轮：前后半深偏置随 y 连续变化的锚比率） ----
// 绝对 y 锚（腰/臀/裆等站点）在 mannequin.ts 按体型组装（同 outerLadder
// 模式）；站点锚值 = SECTION_PRIOR 现值（腰 1.0/臀 1.12 不动 -> 单原语站
// 金标天然保住）。中间锚按真人解剖矢状 S 曲线：腰椎内收 → 臀峰外凸 →
// 臀底褶收；小腹微凸（用户拍板）；腿腘窝凹/小腿肚凸/跟腱收（治「臀部
// 矢状直线锥」：常数 backBias 从腰直用到楔底 = 直线背，无 S 曲线）。
// 数值口径：骨盆 depth 腰→裆恒 0.75，bB(y) = a(y)·0.75·bias(y)——锚比率
// 按 dump 实测 a(y) 标定（计划稿绝对目标按周长假设推得，偏差以比率吸收）
export const SAGITTAL = {
  // 骨盆 backBias 锚（bB/(a·depth)）：waist 1.0 → 腰椎谷 lumbarBias @
  //   (waist+hip)/2 → hip 1.12（SECTION_PRIOR 锚）→ 臀峰 glutealBias @
  //   hip − glutealBelowRatio×(hip−crotch)（真人臀峰在臀线下 ~4.5cm）
  //   → crotch crotchBackBias → 楔底 wedgeBackBias（臀底褶收）
  // 五轮「自然圆润」重校（用户否决 1.42/0.67 的架状臀与腰臀摆幅过大；
  // 四轮逐轮加深史 0.73→0.70→0.67 / 1.18→1.24→1.28 见决策日志）：
  // lumbar 0.67→0.77（谷≈0.97×腰 浅谷自然）、glute 1.42→1.30、峰锚
  // 下移 0.45→0.50（臀线下 4cm 真人位）、crotchBack 0.92→0.88 与腿首锚
  // thighTopBackBias 对值（盆-腿后壁交接差 1.21→~0.25 台阶消除）。
  // 五轮b：glute 1.30→1.22——填充锚抬 a@82（14.05→~14.9）后同 bias 峰
  // 会长到 ~1.09×臀站破「圆润」窗；bB@82 = a×0.75×bias，1.22 守峰比
  // ≈1.03×臀站。站点锚不动 -> 单原语站金标保住
  lumbarBias: 0.77,
  glutealBias: 1.22,
  glutealBelowRatio: 0.50,
  crotchBackBias: 0.88,
  wedgeBackBias: 0.85,
  // 骨盆 frontBias 锚（bF/(a·depth)）：waist 1.0 → 小腹 bellyBias @
  //   hip − bellyBelowRatio×(hip−crotch) → crotch crotchFrontBias → 楔底。
  //   五轮：belly 1.28→1.18（单锚尖峰=「孤立乳头状凸起」观感根因，降为
  //   宽缓微凸）、crotch 0.96→0.80 / 楔 0.90→0.80（盆 bF@78 10.08→8.5：
  //   小腹-裆台阶 1.63→0.32，微凸光滑曲线直落裆）。五轮b VLM 放大复验
  //   「屋檐状水平棱线+陡落」：monoSlope 把峰锚与端锚均钳 0 导数、两段
  //   Hermite 双端零斜率 = 平台-升-平台-落——插双侧沿锚 bellyUpperRim/
  //   bellyRim（非极值锚斜率非零）摊开曲率成 ~3cm 圆穹顶；belly 1.18→
  //   1.16 同步收峰（金标「峰 > bF(86)+0.3」余量足）。五轮c VLM 复验「屋檐
  //   感仍在（有缓和）」——峰锚 monoSlope 0 导数的平顶带 + 峰幅 1.17 使
  //   水平条仍可辨：belly 1.16→1.10 峰幅压半（~0.68，微凸量级）、上沿
  //   1.09→1.06 摊升段（金标余量 12.46 vs 12.08 仍足）
  bellyBias: 1.10,
  bellyUpperRimRatio: 0.15,   // 上沿锚 y = hip − ratio×(hip−crotch)
  bellyUpperRimBias: 1.06,
  bellyBelowRatio: 0.35,
  bellyRimRatio: 0.65,        // 下沿锚 y = hip − ratio×(hip−crotch)
  bellyRimBias: 0.97,
  crotchFrontBias: 0.80,
  wedgeFrontBias: 0.80,
  // 腿 backBias 锚：crotch 1.0 → 大腿中段 thighBackBias（ham 后凸，y=
  //   (crotch+knee)/2）→ 膝上 poplitealRimBias（腘窝上沿：ham 质量下落
  //   起点 y=knee+4——无它时中段锚与膝谷两端 monoSlope 均被钳 0、Hermite
  //   两端零斜率是最平插值，@膝上 2cm 已落至全程 96.5%、dip 仅 0.11cm
  //   不可见；加上沿锚后陡降集中进膝上 4cm，dip@膝上 2 ~0.3cm）→ 膝
  //   poplitealBias（腘窝谷）→ calf calfBackBias（小腿肚后凸）→ hem 1.0
  //   → ankle achillesBias（跟腱收）。y 由 mannequin 组装并防乱序钳位
  // 五轮：膝环缢减半（rim 1.00→0.97 / 谷 0.80→0.86，对比锚差 0.20→0.11，
  // dip@44 0.47→0.30 仍 ≥0.2 金标；四轮推深史见决策日志）、calf 小腿肚
  // 弧增强、新 thighTopBackBias 裆首锚（臀底过渡主锚，腿 bB@crotch ≈ 盆
  // bB@crotch——四轮前此位为硬编码 1.0）。五轮b（VLM 放大复验腘窝被填平
  // + 肌腹尖峰）：popliteal 0.86→0.84（dip@44 ~0.25→~0.30 回可辨阈上、
  // 仍远低于四轮 0.47 环缢位）、calf 1.18→1.15 + 站上提（见 BODY_RATIO
  // calfBelowKnee 注）纺锤化、achilles 0.92→0.95 摊开峰下折点。五轮c：
  // calf 1.15→1.12 + 新 calfTaperBias 峰下锚（后壁与围度站同步收拢）
  thighTopBackBias: 1.20,
  poplitealBias: 0.84,
  thighBackBias: 1.12,
  poplitealRimBias: 0.97,
  calfBackBias: 1.12,
  calfTaperBias: 1.11,
  achillesBias: 0.95,
} as const

// ---- 脚（SDF 场加原语，2026-09-10 第四轮：站立双脚、微外八） ----
// 圆角盒风格化脚：后段（足跟/足弓）+ 前段（脚掌/脚趾），**绝对 cm 标准
// 脚**——病理体型共用（脚不随围度缩放）；仅进蒙皮与解耦参照，不进碰撞
// （脚顶 ≈ y −8.6 < 裤口 y=0，布料永不可达）。局部系 +Z = 脚尖方向，
// 原点 = 踝关节；z 布局：跟后伸 heelBehind、总长 totalLength（脚整体
// 中心前移 ≈5.75 = (totalLength−heelBehind)/2 − heelBehind）
export const FOOT_PRIOR = {
  groundY: -15,          // 站立地面（= man.bottomY；踝 −8 下方）
  totalLength: 22.5,     // 总长（跟后伸端到脚尖）
  heelBehind: 5.5,       // 跟后伸（踝关节在脚后 ~1/4）
  rearLen: 14,           // 后段长（足跟+足弓）
  rearHalfW: 3.8,        // 后段半宽（宽 7.6）
  rearHalfH: 3.2,        // 后段半高（高 6.4，自地面）
  frontHalfW: 4.3,       // 前段半宽（宽 8.6）
  frontHalfH: 2.3,       // 前段半高（高 4.6，自地面）
  round: 1.2,            // 圆角半径
  blendKFoot: 1.2,       // 两段间 smin
  toeOutDeg: 7,          // 微外八（每脚绕 Y；右脚 +、左脚 −）
} as const

// ---- 肚脐（smax 凹刻椭球，挂前腹表面 x=0） ----
// y = waist − dropBelowWaist（165/66A ≈ 93.5，距站点环 98/86 均 >2cm，
// 不碰站点金标）；z 自当环前表面（radiusAt 系 bF 极值）内移 inset；半轴
// rx/ry/rz + inset 给凹深 ~0.45、blend 控光滑唇缘宽度
export const NAVEL_PRIOR = {
  dropBelowWaist: 4.5,
  radiusX: 1.2,
  radiusY: 1.4,
  radiusZ: 0.9,
  inset: 0.2,
  blend: 0.8,
} as const

// ---- 解算（PBD） ----
export const SOLVER_PRIOR = {
  gravity: -980,        // cm/s²
  damping: 0.985,       // 速度衰减/步
  dt: 1 / 60,           // 单步时长 s
  substeps: 3,          // rAF 帧内子步
  iterations: 6,        // 每子步约束迭代（Gauss-Seidel）
  collisionSkin: 0.3,   // cm：布料-人台皮肤厚度
  friction: 0.5,        // 碰撞切向摩擦（0~1）
  pinWeight: 0.9,       // 腰口 pin 权重（<1 防整裤刚度锁死）
  seamStiffness: 1.0,   // 缝合约束刚度
  stretchStiffness: 1.0,
  bendStiffness: 0.3,
  settleSpeed: 0.8,      // cm/s：均速低于此视为静止
  settleFrames: 30,      // 连续静止帧数 -> settled
  preRelaxIters: 200,    // 冷启动预松弛迭代
  garmentGap: 1.2,       // cm：初始摆位径向松量（贴终态，收敛快）
  collideSweeps: 3,      // 碰撞扫描遍数：交叠带（腿头带×骨盆 78~83 + 裆下
                         // 两腿互叠带 73~78）顺序投影非幂等。2026-09-10
                         // 人体化 2→3：交叠带变多，2 遍最坏残差 0.13、
                         // 3 遍 0.09（侵 skin 余量带、粒子仍在外面 ≥0.21cm
                         // 零可见穿模，集成测试 −0.1 容差收纳）
} as const

// ---- SDF 蒙皮（2026-09-09：tubeMesh 三管装配体 -> 单张水密隐式蒙皮） ----
// 渲染层专用；碰撞/摆位仍走 sectionAt/radiusAt 解析路径（seams/pbd 不动），
// 两者差异仅在 smin 融合带。外凸界由 skin.test.ts 解耦金标按**解析并集**
// 双测度断言 ≤ SOLVER_PRIOR.garmentGap（2026-09-10 人台人体化后重校：
// ①并集表面点法向外凸实测最坏 1.065 @大腿接触带出口；②腿心全域+轴心
// 楔区射线 0.53/0.67），布料不可见
export const SKIN_PRIOR = {
  // smin 融合半径 cm，**分对**（2026-09-09 四轮确立分对，2026-09-10 重校）。
  // **族锁死**：必须紧支多项式 smin（指数式全域支撑使站点围度漂移不可证，
  // 单原语站精确支配金标兼作防回退守卫——换 smin 族即红）；k 取值由解耦
  // 金标锁死（抬升即红——外凸随 k 线性、切向带 |∇F|≪1 再放大）
  blendKPelvisLeg: 0.75,  // 骨盆↔腿群（emergence 头带/裆区）：切向放大带
                          // 所在，主校准对象；2026-09-10 人体化后凸坡头带
                          // 交角 ≥40°，外凸实测 ≤1.07 预算内
  blendKLegLeg: 0.6,      // 腿↔腿（裆下互叠带 + 分离带浅沟 + 病理粗腿重叠
                          // 带）。2026-09-10 人体化 1.0→0.6：两内侧壁切向
                          // 擦碰时 |∇F|≈0.14 放大 k/4（旧接触带出口实测
                          // 1.774 超 garmentGap=1.2），0.6 后预算内；五轮
                          // 开缝互叠带止于裆下 ~5cm，过零锚附近两壁仍贴
                          // 近故维持；缝带内 smin 谷 > 0 不桥接、缝成浅沟
  blendKLegFoot: 0.75,    // 腿↔同侧脚（2026-09-10 第四轮新增脚原语）：
                          // 踝穹顶与脚跟盒 smin 融合；超解耦双测度预算时
                          // 与 kPL 同步下调，勿动 garmentGap 阈值
  // 躯干顶穹顶长 cm：116 顶环（围 60.7）平盘在斜 45° 机位显突兀；只影响
  // y>topY，站点围度零漂移
  capDomePelvisTop: 5,
  // 骨盆楔底穹顶长 cm：藏两腿间防平底幅从腿缝透出
  capDomePelvisBottom: 2.5,
  // 腿管两端穹顶长 cm：踝圆头断茬替代平切；腿顶头带环（yTop 下 1cm 内）
  // 深藏骨盆壁内（outerHead 贴盆凸坡），穹顶不可见；浅裆退化（无头带）
  // 腿自 crotch 穹顶起、smin 融成分叉
  capDomeLeg: 2.5,
  // MC 栅格 cm：内腿缝/接触带浅沟 ≥2 格可分辨；~22 万格、名义三角
  // 2.6~3.3 万
  spacing: 1.0,
  // 三角预算守卫：超出即 spacing 逐档 ×budgetSpacingGrow（至多
  // budgetMaxRetries 次）整管线重跑（确定性守卫，替代不可测的计时降档；
  // 165/66A 首跑即达标，病理/滑杆极值 1~2 档收敛，循环保证恒回预算内）
  maxTriangles: 30000,
  budgetSpacingGrow: 1.15,
  budgetMaxRetries: 5,
  // 单原语站（腰/臀/膝/脚口）场级周长容差：理论漂移 0，纯护栏带
  girthTolStation: 0.005,
  // thigh 站容差：裆侧回退尺则实测总漂移 +1.82%（回退带边界 2~4 个切向
  // 放大方向主导），留余量
  girthTolThigh: 0.02,
} as const

// ---- 网格 ----
export const MESH_PRIOR = {
  spacing: 1.5,          // cm：内部栅格间距
  boundaryStep: 1.5,     // cm：边界弧长重采样步长
  seamStep: 1.0,         // cm：缝合配对重采样步长
  markStep: 1.0,         // cm：结构线重采样步长
  ringSegments: 48,      // 人台截面环离散段数
} as const
