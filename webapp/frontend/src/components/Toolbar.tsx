import { Button, Space, Alert, App as AntApp } from 'antd'
import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons'
import type { DraftPayload, IssueDetail } from '../types'
import { download } from '../api'

export default function Toolbar({
  payload, busy, errors, warnings, onGenerate,
}: {
  payload: DraftPayload
  busy: boolean
  errors: IssueDetail[]
  warnings: { param: string | null; message: string }[]
  onGenerate: () => void
}) {
  const { message } = AntApp.useApp()
  const blocked = errors.length > 0

  async function dl(endpoint: string, filename: string) {
    try {
      await download(endpoint, payload, filename)
    } catch (e) {
      void message.error(`下载失败：${e}`)
    }
  }

  return (
    <div className="toolbar">
      <Space wrap>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={busy}
          onClick={onGenerate}
        >
          生成
        </Button>
        <Button
          icon={<DownloadOutlined />}
          disabled={busy || blocked}
          onClick={() => void dl('/api/dxf?kind=pieces', 'pieces.dxf')}
        >
          裁片 DXF
        </Button>
        <Button
          icon={<DownloadOutlined />}
          disabled={busy || blocked}
          onClick={() => void dl('/api/dxf?kind=sheet', 'sheet.dxf')}
        >
          整版 DXF
        </Button>
        <Button
          icon={<DownloadOutlined />}
          disabled={busy}
          onClick={() => void dl('/api/toml', 'size_draft.toml')}
        >
          尺寸单 toml
        </Button>
      </Space>
      {errors.length > 0 && (
        <Alert
          className="issue-banner"
          type="error"
          showIcon
          message="参数校验未通过"
          description={
            <ul className="issue-list">
              {errors.map((e, i) => (
                <li key={i}>
                  {e.param ? <code>[{e.param}]</code> : null} {e.message}
                </li>
              ))}
            </ul>
          }
        />
      )}
      {errors.length === 0 && warnings.length > 0 && (
        <Alert
          className="issue-banner"
          type="warning"
          showIcon
          message={
            <ul className="issue-list">
              {warnings.map((w, i) => (
                <li key={i}>
                  {w.param ? <code>[{w.param}]</code> : null} {w.message}
                </li>
              ))}
            </ul>
          }
        />
      )}
    </div>
  )
}
