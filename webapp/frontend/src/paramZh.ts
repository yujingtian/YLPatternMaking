// 全部参数页签中文名（2026-09-24，暂时口径延续 CORE_PARAM_ZH）：键->中文名，
// 仅覆盖标签与枚举下拉的显示，值/校验不受影响；未收录键回落英文键原样
// （misc 兜底组/引擎新增参数不崩面板）。核心参数词条单源复用 CORE_PARAM_ZH。
// 悬停 title 显示「英文键 · 中文」双名可溯源（ParamInput）。
// 退役时删本表 + ParamPanel 的 zhMap 透传即可。
import { CORE_PARAM_ZH } from './coreParams'

export const PARAM_ZH: Record<string, string> = {
  ...CORE_PARAM_ZH,

  // —— 整版绘制 · 臀腰裆框架（options.py 注释口径）——
  delta: '臀围前后调节量',
  front_crotch_adjust: '前小裆修正',
  back_crotch_adjust: '后大裆修正',
  front_intake_ratio: '前中内收系数',
  front_intake_adjust: '前中内收修正',
  back_intake: '后中内收模数',
  waist_balance: '腰围前后调节量',
  front_waist_dart: '前片腰长调节量',
  back_waist_dart: '后片腰长调节量',
  outseam_bulge: '外侧缝外凸量',
  waist_rect_len: '腰弧直角修正段长',
  rise_ratio: '直裆深系数',
  rise_adjust: '直裆深修正量',
  crotch_drop_adjust: '后片落裆调节量',
  back_rise_alpha: '后浪上段柄系数',
  back_rise_beta: '后浪下段柄系数',
  front_rise_alpha: '前浪裆弯上柄系数',
  front_rise_beta: '前浪裆弯下柄系数',
  front_rise_exit_angle: '前浪裆底出口角',

  // —— 整版绘制 · 腰头绘制 ——
  waistband_width: '腰头宽',
  side_rise: '侧缝腰头抬高量',
  front_waist_curve_sag: '前腰弧下凹量',
  back_waist_curve_sag: '后腰弧下凹量',

  // —— 整版绘制 · 前口袋（挖削式）——
  front_pocket_p1_dist: '袋口腰端距离 P1',
  front_pocket_p2_drop: '袋口侧端深度 P2',
  front_pocket_dart_width: '腰头吃省宽',
  front_pocket_paring_n: '吃省衰减指数',
  front_pocket_mouth_mode: '袋口线模式',
  front_pocket_mouth_bulge: '袋口弧深',
  front_pocket_mouth_bulge_at: '袋口弧顶位置',
  front_pocket_mouth_h1: '袋口腰端柄长',
  front_pocket_mouth_h2: '袋口侧端柄长',
  front_pocket_mouth_corners: '袋口折角列表',

  // —— 整版绘制 · 前贴袋 ——
  front_patch_top_drop: '贴袋口下移量',
  front_patch_top_inset: '贴袋口内移量',
  front_patch_width: '贴袋口宽',
  front_patch_height: '贴袋身高',
  front_patch_shape: '贴袋净形',
  front_patch_bottom_width: '贴袋底宽',
  front_patch_rotate_deg: '贴袋旋转角',
  front_patch_tip_depth: '盾形底尖深',
  front_patch_chamfer: '底角斜切量',

  // —— 整版绘制 · 袋贴 ——
  front_pocket_facing: '袋贴开关',
  front_pocket_facing_width: '袋贴宽',
  front_pocket_facing_side_w: '袋贴侧端深',
  front_pocket_facing_mode: '袋贴内边模式',
  front_pocket_facing_h1: '袋贴腰端柄长',
  front_pocket_facing_h2: '袋贴侧端柄长',
  front_pocket_facing_bulge: '袋贴内边弧深',
  front_pocket_facing_bulge_at: '袋贴弧顶位置',

  // —— 整版绘制 · 袋布 ——
  front_pouch_waist_safe: '袋布腰缝安全量',
  front_pouch_side_safe: '袋布侧缝安全量',

  // —— 整版绘制 · 小表袋 ——
  watch_pocket_mode: '表袋模式',
  watch_pocket_width: '表袋口宽',
  watch_pocket_taper: '表袋侧收量',
  watch_pocket_offset_from_top: '表袋离袋顶距',
  watch_pocket_offset_from_side: '表袋离侧缝距',
  watch_pocket_rotate_deg: '表袋旋转角',

  // —— 整版绘制 · 门襟（连裁/独立共用 + 连裁专属）——
  fly_width: '门襟宽',
  fly_length_ratio: '门襟开深系数',
  fly_length_base: '门襟开深基值',
  fly_corner_inset: '门襟底角内收',
  fly_corner_turn: '门襟拐点弧位',
  fly_blend_drop: '门襟融合下移量',
  fly_turnback: '门襟折转退层量',
  fly_stitch_inset: '门襟明线内收',

  // —— 整版绘制 · 后省 ——
  back_dart_count: '后省数量',
  back_dart_width: '后省省量',
  back_dart_length: '后省长度',

  // —— 整版绘制 · 后机头 ——
  back_yoke_cb_dist: '机头后中深',
  back_yoke_side_dist: '机头侧缝深',
  back_yoke_mid_anchors: '机头下口锚点',
  back_yoke_edges: '机头下口边形态',

  // —— 整版绘制 · 后贴袋 ——
  back_patch_inset_x: '贴袋离后浪距',
  back_patch_drop_y: '贴袋离育克距',
  back_patch_width: '贴袋口宽',
  back_patch_height: '贴袋身高',
  back_patch_shape: '贴袋净形',
  back_patch_bottom_width: '贴袋底宽',
  back_patch_rotate_deg: '贴袋旋转角',
  back_patch_tip_depth: '盾形底尖深',
  back_patch_chamfer: '底角斜切量',

  // —— 整版绘制 · 腿部与弧线微调 ——
  front_crease_e: '前裤中线调节',
  back_crease_e: '后裤中线调节',
  knee_adjust: '膝围调整量',
  hem_adjust: '脚口调整量',
  calf_arc_alpha: '前小腿弧系数',
  inseam_arc_k1: '前内缝裆弯度',
  inseam_arc_ky: '前内缝纵向系数',
  inseam_arc_k2: '前内缝切柄系数',
  outseam_arc_dx: '前外缝外凸量',
  outseam_arc_m2: '前外缝切柄系数',
  back_calf_arc_alpha: '后小腿弧系数',
  back_inseam_arc_k1: '后内缝裆弯度',
  back_inseam_arc_ky: '后内缝纵向系数',
  back_inseam_arc_k2: '后内缝切柄系数',
  back_outseam_arc_dx: '后外缝外凸量',
  back_outseam_arc_m2: '后外缝切柄系数',
  back_hipwaist_arc_dx1: '臀侧凸出量',
  back_hipwaist_arc_k1: '臀侧凸感高度',
  back_hipwaist_arc_dx2: '腰角凸出量',
  back_hipwaist_arc_k2: '收腰快慢系数',
  front_hem_arc_sag: '前脚口弧高',
  back_hem_arc_sag: '后脚口弧高',

  // —— 整版绘制 · 毗围限制 ——
  thigh_limit: '启用毗围限制',
  thigh_measure_offset: '毗围量取下移量',
  thigh_piece_split_max: '片间平分阈值',
  thigh_front_share: '前片分配比',
  thigh_dual_track_min: '双轨分流阈值',
  thigh_front_crotch_coef: '前小裆调拨系数',
  thigh_back_crotch_coef: '后大裆调拨系数',
  thigh_front_crotch_max: '前小裆调整上限',
  thigh_back_crotch_max: '后大裆调整上限',
  thigh_max_iter: '最大迭代轮数',
  thigh_tol: '收敛容差',

  // —— 整版绘制 · 版面杂项 ——
  piece_gap: '前后片间距',
  fit: '版型宽松度',
  size_label: '尺码标签',
  show_labels: '显示标注',

  // —— 裁片 · 全局工艺 ——
  shrinkage_enabled: '缩水总开关',
  shrinkage_warp: '经向缩水率',
  shrinkage_weft: '纬向缩水率',
  seam_allowance: '默认缝份',
  show_seam_allowance: '显示缝边',

  // —— 裁片 · 腰头裁片 ——
  waistband_fly_extension: '腰头搭门量',
  waistband_full_piece: '腰头整条裁',
  waistband_grain: '腰头经向',
  waistband_seam_allowances: '腰头缝份',
  waistband_shrinkage_warp: '腰头经向缩水率',
  waistband_shrinkage_weft: '腰头纬向缩水率',

  // —— 裁片 · 前口袋裁片（贴袋/袋贴）——
  front_patch_seam_allowances: '贴袋缝份',
  front_pocket_facing_seam_allowances: '袋贴缝份',
  front_pocket_shrinkage_warp: '口袋裁片经向缩水',
  front_pocket_shrinkage_weft: '口袋裁片纬向缩水',

  // —— 裁片 · 袋布裁片 ——
  front_pouch_seam_allowances: '袋布缝份',
  front_pouch_shrinkage_warp: '袋布经向缩水',
  front_pouch_shrinkage_weft: '袋布纬向缩水',

  // —— 裁片 · 小表袋裁片 ——
  watch_pocket_seam_allowances: '表袋缝份',
  watch_pocket_shrinkage_warp: '表袋经向缩水',
  watch_pocket_shrinkage_weft: '表袋纬向缩水',

  // —— 裁片 · 门襟裁片（独立门襟专属）——
  fly_sep_extra: '门襟底部延展量',
  fly_sep_double: '门襟对折双排',
  fly_seam_allowances: '门襟缝份',
  fly_shrinkage_warp: '门襟经向缩水',
  fly_shrinkage_weft: '门襟纬向缩水',

  // —— 裁片 · 后机头裁片 ——
  back_yoke_join_fillet: '拼合处倒圆量',
  back_yoke_side_corner_mirror: '侧缝角镜像折角',
  back_yoke_cb_corner_mirror: '后中角镜像折角',
  back_yoke_seam_allowances: '机头缝份',
  back_yoke_shrinkage_warp: '机头经向缩水',
  back_yoke_shrinkage_weft: '机头纬向缩水',

  // —— 裁片 · 后贴袋裁片 ——
  back_patch_top_hem_taper: '袋口折边撇势',
  back_patch_notch_type: '刀口类型',
  back_patch_notch_depth: '刀口深度',
  back_patch_seam_allowances: '贴袋缝份',
  back_patch_shrinkage_warp: '贴袋经向缩水',
  back_patch_shrinkage_weft: '贴袋纬向缩水',

  // —— 裁片 · 裤耳裁片 ——
  belt_loop_width: '裤耳宽',
  belt_loop_unit_length: '裤耳单根长',
  belt_loop_count: '裤耳根数',
  belt_loop_waste: '裤耳损耗',

  // —— 裁片 · 前片 / 后片 ——
  front_piece_seam_allowances: '前片缝份',
  front_piece_crotch_corner: '裆尖镜像折角',
  front_piece_notch_type: '刀口类型',
  front_piece_shrinkage_warp: '前片经向缩水',
  front_piece_shrinkage_weft: '前片纬向缩水',
  back_piece_seam_allowances: '后片缝份',
  back_piece_crotch_corner: '裆尖镜像折角',
  back_piece_notch_type: '刀口类型',
  back_piece_shrinkage_warp: '后片经向缩水',
  back_piece_shrinkage_weft: '后片纬向缩水',

  // —— 枚举值显示名（值不动，仅下拉显示翻译）——
  bulge: '弧高式',
  tangent: '垂直式',
  polyline: '折角式',
  offset: '等距偏置',
  rectangle: '方底',
  baker_shield: '盾形',
  angular: '斜切',
  custom: '自定义',
  facing_intersect: '袋贴相交',
  width: '宽向（横裁）',
  length: '长向（直裁）',
  skinny: '紧身',
  slim: '修身',
  regular: '常规',
  loose: '宽松',
}
