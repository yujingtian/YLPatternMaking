import { useState } from 'react'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import TemplatePicker from './components/TemplatePicker'
import ParamPanel from './components/ParamPanel'
import PreviewPane from './components/PreviewPane'
import SizeRunDrawer from './components/SizeRunDrawer'
import Toolbar from './components/Toolbar'
import { useDraft } from './hooks/useDraft'
import './styles.css'

function DraftApp() {
  const d = useDraft()
  // 拖拽进行中：暂隐"已过期"横幅（每次回写都重生成，松手后必然同步）
  const [dragging, setDragging] = useState(false)
  // 推板设置抽屉开合（未配置点「推板 DXF」也转到此处）
  const [sizeRunOpen, setSizeRunOpen] = useState(false)

  return (
    <div className="app">
      <header className="app-header">
        <h1>YLPattern 牛仔裤打版</h1>
        <TemplatePicker onLoad={d.loadValues} />
      </header>
      <Toolbar
        sheetBusy={d.sheetBusy}
        piecesBusy={d.piecesBusy}
        dlBusy={d.dlBusy}
        sheetReady={d.sheetReady}
        sheetStale={d.sheetStale}
        piecesReady={d.piecesReady}
        piecesStale={d.piecesStale}
        errors={d.errors}
        warnings={d.warnings}
        onGenerateSheet={() => void d.generateSheet()}
        onGeneratePieces={() => void d.generatePieces()}
        onDownload={(k) => void d.download(k)}
        canUndo={d.lastDrag !== null}
        onUndo={d.undoLastDrag}
        engineState={d.engineState}
        sizeRunConfigured={d.sizeRun !== null}
        onOpenSizeRun={() => setSizeRunOpen(true)}
      />
      <main className="app-main">
        {d.schema ? (
          <ParamPanel
            sections={d.schema.sections}
            measurements={d.measurements}
            options={d.options}
            errors={d.errors}
            onMeasurement={d.setMeasurement}
            onOption={d.setOption}
            onSeed={d.seedShape}
            highlight={d.adjustInfo}
          />
        ) : (
          <div className="preview-empty">schema 加载中…</div>
        )}
        <PreviewPane
          sheet={d.sheet}
          pieces={d.pieces}
          sheetStale={d.sheetStale}
          piecesStale={d.piecesStale}
          dragging={dragging}
          schema={d.schema}
          base={{ measurements: d.measurements, options: d.options }}
          onApplyAdjust={(p, v, b) => void d.applyAdjust(p, v, b)}
          onBeginDrag={d.beginDrag}
          onDragChange={setDragging}
        />
      </main>
      <SizeRunDrawer
        open={sizeRunOpen}
        onClose={() => setSizeRunOpen(false)}
        spec={d.sizeRun}
        measurements={d.measurements}
        defaultLabel={String(d.options.size_label ?? '-')}
        busy={d.dlBusy === 'sizeRunDxf'}
        onExport={(s) => {
          d.setSizeRun(s)
          // 显式覆盖参传 spec：保存与下载同 tick，规避闭包旧值竞态；
          // download 内部捕获异常（失败入全局 errors），结束即关抽屉
          void d.download('sizeRunDxf', { sizeRun: s })
            .then(() => setSizeRunOpen(false))
        }}
      />
    </div>
  )
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: '#2c6e49', borderRadius: 4 } }}
    >
      <AntApp>
        <DraftApp />
      </AntApp>
    </ConfigProvider>
  )
}
