// 模特设置弹框（2026-09-24 用户口径：进 3D 试穿先自设模特）——原 3D 侧栏
// 「预设体型」「形体滑杆」两卡提出成独立 Modal（antd Modal 走 body 门户
// 渲染，f3d- 类名全局未作用域化、弹框内直接复用）。调整实时生效：拖杆即
// morph 人台随之变形（幕后隐约可见），弹框内围度/身高读数给数值反馈；
// 「确定」只是关弹框。开合由 App 持有——首次切入 3D 自动弹
// （Fitting3DView 首挂试穿等 setupOpen=false 才发），3D 侧栏「模特设置」
// 按钮随时重开改；体型状态（BodyModel）亦 App 持有，2D/3D 视图切换不丢。
import { Button, Modal, Slider } from 'antd'
import { UndoOutlined } from '@ant-design/icons'
import type { BodyMeshAsset } from './bodymesh/bin'
import { heightCm, weightFor } from './bodymesh/height'
import {
  HEIGHT_SLIDER, PRESET_CM, SITES, zeroBody,
  type BodyModel, type Site,
} from './bodyModel'

const fmt = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`

export default function BodySetupModal({
  open, onClose, asset, body, girths, onChange,
}: {
  open: boolean
  onClose: () => void
  /** base.bin 资产（人台加载中为 null：控件禁用，与原侧栏口径一致） */
  asset: BodyMeshAsset | null
  body: BodyModel
  /** 站点围度读数（Fitting3DView morph 效应同源算好传入，单一份数据） */
  girths: Record<Site, number | null>
  onChange: (b: BodyModel) => void
}) {
  const { sliders, heightW } = body
  // 当前身高（cm）：芯片高亮判据（换算回算精确，滑杆拖到同值同样命中）
  const curHeightCm = asset ? heightCm(asset.heightInfo, heightW) : null
  const presetActive = (cm: number) =>
    curHeightCm !== null && Math.abs(curHeightCm - cm) < 0.05

  return (
    <Modal
      open={open}
      title="设置模特（人台体型）"
      okText="确定"
      onOk={onClose}
      onCancel={onClose}
      cancelButtonProps={{ style: { display: 'none' } }}
      width={480}
      maskClosable={false}
    >
      <div className="f3d-card-title">预设体型</div>
      <div className="f3d-presets">
        {PRESET_CM.map((cm) => (
          <Button key={cm} size="small"
            type={presetActive(cm) ? 'primary' : 'default'}
            disabled={!asset}
            onClick={() => {
              onChange({ ...body, heightW: weightFor(asset!.heightInfo, cm) })
            }}>
            {cm}
          </Button>
        ))}
        <Button size="small"
          type={heightW === 0 ? 'primary' : 'default'}
          disabled={!asset}
          onClick={() => {
            onChange({ ...body, heightW: 0 })
          }}>
          默认
        </Button>
      </div>
      <div className="f3d-hint">
        芯片 = 快捷身高档（按实测 ΔH 换算权重）；身高连续可调见下方滑杆
      </div>

      <div className="f3d-card-title" style={{ marginTop: 12 }}>
        形体滑杆（MakeHuman targets）
      </div>
      {SITES.map(({ key, label }) => (
        <div key={key} className="f3d-slider">
          <div className="f3d-slider-head">
            <span>{label}</span>
            <span className="f3d-slider-val">
              {girths[key] !== null
                ? `${girths[key]!.toFixed(1)} cm` : ''}
              <code>{fmt(sliders[key])}</code>
            </span>
          </div>
          <Slider
            min={-1} max={1} step={0.05}
            value={sliders[key]}
            disabled={!asset}
            onChange={(v) => {
              onChange({ ...body, sliders: { ...body.sliders, [key]: v } })
            }}
          />
        </div>
      ))}
      <div className="f3d-slider">
        <div className="f3d-slider-head">
          <span>身高</span>
          <span className="f3d-slider-val">
            {curHeightCm !== null ? `${curHeightCm.toFixed(1)} cm` : ''}
          </span>
        </div>
        <Slider
          min={HEIGHT_SLIDER.min} max={HEIGHT_SLIDER.max}
          step={HEIGHT_SLIDER.step}
          value={curHeightCm ?? HEIGHT_SLIDER.min}
          disabled={!asset}
          onChange={(cm) => {
            onChange({ ...body, heightW: weightFor(asset!.heightInfo, cm) })
          }}
        />
      </div>
      <Button size="small" icon={<UndoOutlined />}
        disabled={!asset}
        onClick={() => {
          onChange(zeroBody())
        }}>
        全部归零
      </Button>
      <div className="f3d-hint">
        正/负 = 增/减场权重（w=1 为 MakeHuman 作者化上限）；身高滑杆 cm 连续。
        调整实时生效，「确定」后按新体型自动重新试穿
      </div>
    </Modal>
  )
}
