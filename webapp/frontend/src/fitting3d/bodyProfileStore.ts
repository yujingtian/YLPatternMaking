// 体型管理三件套（2026-09-09 用户口径全选）：
//   1) 内置预设库（标准三档身高 + 沙漏/直筒体型，选中后可微调）
//   2) 自定义保存/列表/删除/设默认（localStorage 持久化）
//   3) JSON 导入导出（分享/换电脑）
// 纯浏览器态：不进引擎、不进打版参数版本号（改体型不触发整版 stale）。
import type { BodyProfile } from './bodyProfile'
import { validateGirths } from './bodyProfile'

// ---- 内置预设库（165/66A 系列女体标定，围度单位 cm） ----
export const BODY_PRESETS: BodyProfile[] = [
  { id: 'std-160-64', name: '标准 160/64A',
    waist: 64, hip: 88, thigh: 52, knee: 34 },
  { id: 'std-165-66', name: '标准 165/66A',
    waist: 66, hip: 90, thigh: 54, knee: 35, height: 165 },
  { id: 'std-170-70', name: '标准 170/70A',
    waist: 70, hip: 94, thigh: 56, knee: 37, height: 170 },
  { id: 'hourglass-165', name: '沙漏 165',
    waist: 62, hip: 94, thigh: 56, knee: 35, height: 165 },
  { id: 'straight-165', name: '直筒 165',
    waist: 70, hip: 88, thigh: 50, knee: 34, height: 165 },
]

const STORE_KEY = 'ylpattern.body.v1'

export interface StoreShape {
  version: 1
  activeId: string          // 当前生效体型 id（预设 id 或自定义 id 或 'estimated'）
  estimated?: BodyProfile   // 首次有效尺寸时的估计快照（人台固定口径：不随成衣参数联动）
  customs: BodyProfile[]
}

export function loadStore(): StoreShape {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (raw) {
      const s = JSON.parse(raw) as StoreShape
      if (s && Array.isArray(s.customs) && typeof s.activeId === 'string') {
        return { version: 1, activeId: s.activeId,
                 estimated: s.estimated ?? undefined, customs: s.customs }
      }
    }
  } catch { /* 损坏即重置 */ }
  // 默认激活「估计体型」：首次有效尺寸时按成衣快照（Fitting3DView 落本字段），
  // 之后不随成衣参数联动；显式刷新走抽屉「按成衣尺寸重估」
  return { version: 1, activeId: 'estimated', customs: [] }
}

export function saveStore(s: StoreShape): void {
  localStorage.setItem(STORE_KEY, JSON.stringify(s))
}

export function findProfile(s: StoreShape, id: string): BodyProfile | null {
  return [...BODY_PRESETS, ...(s.estimated ? [s.estimated] : []),
          ...s.customs].find((p) => p.id === id) ?? null
}

// 保存自定义（新建或覆盖同名 id）；返回新 store（不可变更新）
export function upsertCustom(s: StoreShape, p: BodyProfile): StoreShape {
  const customs = [...s.customs.filter((c) => c.id !== p.id), p]
  return { ...s, customs, activeId: p.id }
}

export function removeCustom(s: StoreShape, id: string): StoreShape {
  const customs = s.customs.filter((c) => c.id !== id)
  return { ...s, customs,
           activeId: s.activeId === id ? 'estimated' : s.activeId }
}

export function setActive(s: StoreShape, id: string): StoreShape {
  return { ...s, activeId: id }
}

// ---- JSON 导入导出 ----

export function exportProfiles(profiles: BodyProfile[]): string {
  return JSON.stringify({ ylpattern_body: 1, profiles }, null, 2)
}

// 宽容导入：单对象或数组均可；逐条校验围度范围，非法条目跳过并计数
export function importProfiles(
  text: string,
): { ok: BodyProfile[]; skipped: number } {
  const parsed = JSON.parse(text) as unknown
  const list = Array.isArray(parsed)
    ? parsed
    : ((parsed as { profiles?: unknown[] })?.profiles ?? [parsed])
  const ok: BodyProfile[] = []
  let skipped = 0
  for (const item of list) {
    const b = item as BodyProfile
    if (typeof b?.waist === 'number' && typeof b?.hip === 'number'
        && typeof b?.knee === 'number' && !validateGirths(b)) {
      ok.push({ ...b, id: b.id || `imported-${ok.length}` })
    } else {
      skipped += 1
    }
  }
  if (!ok.length) throw new Error('未找到合法体型（需含 waist/hip/knee）')
  return { ok, skipped }
}
