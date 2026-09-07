// 照片校验/压缩纯逻辑金标（vitest）。口径：与 agent/config.py 同源——
// 六后缀白名单（无 heic）、≤4 张、单张 ≤10MB（> 拒）；压缩只缩不放大。
// 压缩管线（createImageBitmap/canvas）为浏览器 API，不进单测（注入缝
// 仅供将来组件测试复用）。

import { describe, expect, it } from 'vitest'
import {
  computeTargetSize, MAX_PHOTOS, MAX_PHOTO_BYTES, PHOTO_SUFFIXES,
  validatePhotoFile,
} from './imageCompress'

describe('常量与 agent/config.py 同源', () => {
  it('六后缀 / 4 张 / 10MB', () => {
    expect(PHOTO_SUFFIXES).toEqual(
      ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'])
    expect(MAX_PHOTOS).toBe(4)
    expect(MAX_PHOTO_BYTES).toBe(10 * 1024 * 1024)
  })
})

describe('validatePhotoFile', () => {
  const ok = (name: string, size = 1024) =>
    expect(validatePhotoFile({ name, size })).toBeNull()

  it('六后缀全通过（大小写不敏感）', () => {
    for (const s of PHOTO_SUFFIXES) ok(`p${s}`)
    ok('P.JPG')            // 手机常见大写后缀
    ok('照片.JPEG'.normalize())
  })

  it('heic / tiff / txt 拒绝（消息含文件名）', () => {
    // iPhone 默认 heic 不在 agent 白名单，前端就该拒
    expect(validatePhotoFile({ name: 'IMG_0001.heic', size: 100 }))
      .toContain('IMG_0001.heic')
    expect(validatePhotoFile({ name: 'a.tiff', size: 100 })).toContain('不支持')
    expect(validatePhotoFile({ name: 'a.txt', size: 100 })).toContain('不支持')
  })

  it('大小边界：恰好 10MB 通过、超出拒绝', () => {
    ok('a.jpg', MAX_PHOTO_BYTES)
    expect(validatePhotoFile({ name: 'a.jpg', size: MAX_PHOTO_BYTES + 1 }))
      .toContain('10MB')
  })
})

describe('computeTargetSize（只缩不放大）', () => {
  const t = (w: number, h: number) => computeTargetSize(w, h, 2048)

  it('横图：长边钉 2048、短边等比圆整', () => {
    expect(t(4000, 3000)).toEqual({ width: 2048, height: 1536 })
    expect(t(4096, 4096 * 2 / 3)).toEqual({ width: 2048, height: 1365 }) // 2:3
  })

  it('竖图：高为长边', () => {
    expect(t(3000, 4000)).toEqual({ width: 1536, height: 2048 })
  })

  it('方图与小于上限：原样（永不放大）', () => {
    expect(t(3000, 3000)).toEqual({ width: 2048, height: 2048 })
    expect(t(800, 600)).toEqual({ width: 800, height: 600 })
    expect(t(2048, 1024)).toEqual({ width: 2048, height: 1024 })
  })
})
