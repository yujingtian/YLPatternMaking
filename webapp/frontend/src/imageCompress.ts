// 上传照片的前端校验 + 压缩（一期前端接线 §10.9）。
// !! 下列常量与 agent/config.py 同源（PHOTO_SUFFIXES 六后缀 / MAX_PHOTOS=4 /
// !! MAX_PHOTO_BYTES=10MB）——agent 是 frozenset(_MIME) 无法 import，两端
// !! 改动必须手工同步；agent 仍是唯一裁判（前端漏拦会被 422 兜住）。
// 压缩口径：长边 ≤2048 只缩不放大、jpeg quality 0.85（款式判据要形态
// 不要像素；VLM 按 blob 计费，原图 5-8MB 既慢又贵）。

export const PHOTO_SUFFIXES = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
export const MAX_PHOTOS = 4
export const MAX_PHOTO_BYTES = 10 * 1024 * 1024

// 返回错误消息（中文，可直接 message.error）或 null=通过；数量上限由调用处管
export function validatePhotoFile(file: { name: string; size: number }): string | null {
  const lower = file.name.toLowerCase()
  if (!PHOTO_SUFFIXES.some((s) => lower.endsWith(s))) {
    return `不支持的照片格式：${file.name}（支持 ${PHOTO_SUFFIXES.join(' / ')}）`
  }
  if (file.size > MAX_PHOTO_BYTES) {
    return `照片超过 10MB 上限：${file.name}（${(file.size / 1024 / 1024).toFixed(1)}MB）`
  }
  return null
}

// 目标尺寸（纯函数）：长边超 maxLong 才等比缩小、永不放大、另一边圆整
export function computeTargetSize(
  width: number, height: number, maxLong = 2048,
): { width: number; height: number } {
  if (width <= maxLong && height <= maxLong) return { width, height }
  const scale = maxLong / Math.max(width, height)
  return { width: Math.round(width * scale),
           height: Math.round(height * scale) }
}

export interface CompressDeps {
  maxLong?: number
  quality?: number
  // 测试注入缝（无 jsdom，浏览器 API 不进单测）
  loadBitmap?: (f: File) => Promise<{ width: number; height: number }>
  createCanvas?: () => {
    width: number; height: number
    getContext: (id: '2d') => {
      drawImage: (src: unknown, x: number, y: number, w: number, h: number) => void
    } | null
    toBlob: (cb: (b: Blob | null) => void, type: string, quality?: number) => void
  }
}

// 压缩为 jpeg（长边 2048 / quality 0.85）；解码失败降级原文件直传
// （≤10MB 已由 validate 把关）——异常照片（如 .txt 改名 .jpg）交给
// agent 422 兜底。压缩后仍 >10MB 抛错（理论上不会触发，护栏而已）。
export async function compressImage(file: File, deps: CompressDeps = {}): Promise<File> {
  const maxLong = deps.maxLong ?? 2048
  const quality = deps.quality ?? 0.85
  const loadBitmap = deps.loadBitmap ??
    ((f: File) => createImageBitmap(f))
  const createCanvas = deps.createCanvas ??
    (() => document.createElement('canvas') as unknown as HTMLCanvasElement)
  let bitmap: { width: number; height: number }
  try {
    bitmap = await loadBitmap(file)
  } catch {
    return file   // 解码失败：降级直传
  }
  const size = computeTargetSize(bitmap.width, bitmap.height, maxLong)
  const canvas = createCanvas()
  canvas.width = size.width
  canvas.height = size.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return file
  ctx.drawImage(bitmap as unknown as CanvasImageSource, 0, 0,
                size.width, size.height)
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', quality))
  if (!blob) return file
  if (blob.size > MAX_PHOTO_BYTES) {
    throw new Error(`压缩后仍超过 10MB 上限：${file.name}`)
  }
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg',
                  { type: 'image/jpeg' })
}
