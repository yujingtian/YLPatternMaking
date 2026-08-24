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
  const payload = { measurements: d.measurements, options: d.options }

  return (
    <div className="app">
      <header className="app-header">
        <h1>YLPattern 牛仔裤打版</h1>
        <TemplatePicker onLoad={d.loadValues} />
      </header>
      <Toolbar
        payload={payload}
        busy={d.busy}
        errors={d.errors}
        warnings={d.warnings}
        onGenerate={() => void d.generate()}
      />
      <main className="app-main">
        {d.schema ? (
          <ParamPanel
            groups={d.schema.groups}
            measurements={d.measurements}
            options={d.options}
            errors={d.errors}
            onMeasurement={d.setMeasurement}
            onOption={d.setOption}
          />
        ) : (
          <div className="preview-empty">schema 加载中…</div>
        )}
        <PreviewPane result={d.result} />
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
