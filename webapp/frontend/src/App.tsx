import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import TemplatePicker from './components/TemplatePicker'
import ParamPanel from './components/ParamPanel'
import PreviewPane from './components/PreviewPane'
import Toolbar from './components/Toolbar'
import { useDraft } from './hooks/useDraft'
import './styles.css'

function DraftApp() {
  const d = useDraft()

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
          />
        ) : (
          <div className="preview-empty">schema 加载中…</div>
        )}
        <PreviewPane
          sheet={d.sheet}
          pieces={d.pieces}
          sheetStale={d.sheetStale}
          piecesStale={d.piecesStale}
        />
      </main>
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
