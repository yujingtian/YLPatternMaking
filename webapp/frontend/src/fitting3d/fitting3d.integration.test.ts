// 真实 payload 人台端到端烟囱（引擎产物 -> 真人网格人台整链）。
// 夹具 _fixture_fitting.json 由引擎侧生成（W=70 H=96 K=46 B=36 前浪25
// 后浪33 裤长102 大腿围58，默认选项；重生成命令见下）：
//   python -c "import json; from ylpattern.exporters.fitting import
//     build_fitting_payload; from ylpattern.flows.back_flow import FULL_FLOW;
//     from ylpattern.flows.runner import FlowRunner;
//     from ylpattern.params import Measurements, PatternOptions;
//     m = Measurements(waist=70, hip=96, knee=46, hem=36, front_rise=25,
//       back_rise=33, outseam=102, thigh=58);
//     ctx = FlowRunner(m, PatternOptions()).run(FULL_FLOW);
//     json.dump(build_fitting_payload(ctx, m),
//       open('webapp/frontend/src/fitting3d/_fixture_fitting.json','w'))"
// 断言口径：整链出口（有限性/顶底序/站点围度达标）——几何不变量，
// 不钉具体构型。payload 只消费 body 站点（人台纵向对齐锚 + 围度标定
// 测点换算）；2026-09-12 裁撤试穿后布料/缝合/PBD 断言随试穿链退役
//（演进史见决策日志）。
// 人台 = 真人网格唯一路径（2026-09-11 换轨）：node 无 fetch，fs 读
// public/bodymesh 真资产 -> parseBin -> buildMeshMannequin（与浏览器
// 运行时同一解析与出口，端到端含 morph/对齐/围度闭环）。
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { buildMeshMannequin } from './bodymesh/build'
import { parseBin } from './bodymesh/load'
import { stationGirth } from './bodymesh/slice'
import type { BodyMeshAsset, BodyMeshMeta } from './bodymesh/types'
import fixtureJson from './_fixture_fitting.json'

// node:fs 仅测试用（vitest 运行时 = node）；tsc 浏览器 lib 无其类型，
// 指令须紧贴 import 行才压得住 TS2307（勿隔注释行）
// @ts-expect-error
import { readFileSync } from 'node:fs'

// 静态 import（Vite JSON 导入）
const payload = fixtureJson as unknown as FittingResult
const GIRTHS: BodyGirths = { waist: 66, hip: 90, thigh: 54, knee: 35 }

// 真资产单例：morph 链路毫秒级、解析一次全 describe 复用
const assetDir = new URL('../../public/bodymesh/', import.meta.url)
const asset: BodyMeshAsset = (() => {
  const bin = readFileSync(new URL('base.bin', assetDir))
  const meta = JSON.parse(
    readFileSync(new URL('targets.json', assetDir), 'utf8')) as BodyMeshMeta
  return {
    ...parseBin(bin.buffer.slice(
      bin.byteOffset, bin.byteOffset + bin.byteLength) as ArrayBuffer),
    meta,
  }
})()

describe('真实 payload 端到端（引擎 -> 3D 人台）', () => {
  it('人台整链：顶底序、位置有限、站点围度达标', () => {
    const man = buildMeshMannequin(asset, payload.body, GIRTHS)
    expect(man.sourceMesh.positions.length)
      .toBe(asset.positions.length)
    // 顶底序（groundY = 对齐后脚底，topY = vendor 裁切面）
    expect(man.topY).toBeGreaterThan(man.bottomY)
    // 有限性（morph/对齐全程无 NaN/Inf）
    for (let i = 0; i < man.sourceMesh.positions.length; i++) {
      expect(Number.isFinite(man.sourceMesh.positions[i])).toBe(true)
    }
    // 站点围度达标：达标 = 目标 ±2%（calibTol 1.5% + 对齐插值离散余量）。
    // 只断言 waist/knee——均为对齐节点，payload 站 y 精确可逆映射回标定
    // 测点。thigh 不在此断言：payload thigh 站与裆线等高
    //（thigh_measure_offset=0，实测 fixture y=78=crotch），标定测点钳在
    // mesh 坐标裆叉下方（build.ts 口径），payload 侧重建该测点需复刻整条
    // 分段对齐——叉下切片含裆桥（此处实测 57.8 虚高）正是钳位的理由，
    // 钳位行为金标在 bodymesh.test.ts 合成网格（对齐恒等可直测）
    const yOf = (key: string) =>
      payload.body.stations.find((s) => s.key === key)!.y
    const perOf = (key: string) =>
      payload.body.stations.find((s) => s.key === key)!.per
    const assertGirth = (key: 'waist' | 'knee') => {
      const target = GIRTHS[key]!
      const g = stationGirth(man.sourceMesh.positions,
        man.sourceMesh.indices, yOf(key), perOf(key) as 'body' | 'leg')
      expect(g).not.toBeNull()
      expect(Math.abs(g! - target) / target).toBeLessThan(0.02)
    }
    assertGirth('waist')
    assertGirth('knee')
  })
})
