# Web 三期：生成拆两步（整版生成 / 裁片生成）+ DXF 下载门控

> 设计文档（2026-08-25 批准实施）。前序：[webapp-phase2-param-sections.md](webapp-phase2-param-sections.md)（两段式参数面板）。

## 需求与口径

生成从单一按钮拆为**整版生成**与**裁片生成**两步：有了整版（生成成功且未过期）才支持整版 DXF 下载，有了裁片才支持裁片 DXF 下载。

1. **裁片生成必须先完成整版生成**（先画后裁；仅 UI 门控，后端保持无状态各算各的）
2. **参数修改后保留预览但标"已过期"**：预览继续显示、两个 DXF 下载禁用；重新生成对应步骤后恢复（整版过期须先重跑整版才能跑裁片）
3. **不保留一键生成**；localStorage 仍只存参数，刷新后生成状态清零

## 设计决策

- **D1 后端**：`POST /api/draft/sheet` → `{ok, sheet_svg, report, warnings}`；`POST /api/draft/pieces` → `{ok, pieces, skips, warnings}`；**移除旧 `/api/draft`**（消费方仅前端+测试，CLI 不经 FastAPI）。`/api/dxf`、`/api/toml` 不动。
- **D2 过期机制**：参数版本号——`setMeasurement/setOption/loadValues` 使 `version+1`，产物线存 `{data, version}` 快照，`stale = snapshot.version !== version`（相等比较，虚拟下拉连发跳号无害）。
- **D3** `generatePieces` 开头防御式早退（按钮 disabled 为第一道门）。
- **D4** errors=最近一次操作、warnings=最近一次成功生成，维持单一数组。
- **D5** `sheetBusy`/`piecesBusy` 互斥 + 单一 `dlBusy` 串行下载（下载重跑引擎，须防重复点击）。
- **D6** 过期提示=预览区 Tabs 上方 warning Alert 横幅（不做 tab 标记）。
- **D7** report 随 sheet 快照、skips 随 pieces 快照。
- **D8** `download()` 不补 422 解析（门控后不可达）。
- **D9** 下载动作收进 hook，错误入 errors（与 schema 加载失败同款先例）。

## 改动面

后端 [app.py](../../webapp/backend/app.py)（端点拆分）；测试 [test_web_api.py](../../tests/test_web_api.py)（拆分测试+字段缺席断言）；前端 types/api/useDraft/Toolbar/PreviewPane/styles/App（版本号+双快照+门控矩阵+stale 横幅）。

## 门控矩阵

| 按钮 | disabled |
|---|---|
| 整版生成 | piecesBusy（loading=sheetBusy） |
| 裁片生成 | !sheetReady \|\| sheetStale \|\| sheetBusy（loading=piecesBusy） |
| 整版 DXF | sheetBusy \|\| piecesBusy \|\| dlBusy≠'' \|\| !sheetReady \|\| sheetStale \|\| blocked |
| 裁片 DXF | 同上换 pieces 条件 |
| toml | 仅 busy（不跑引擎不校验，维持现状） |

## 风险

裁片生成后端重跑整版闭环（毗围开启时两步合计约旧一键 2 倍引擎耗时）——口径已接受；移除 /api/draft 为 breaking，消费方全在同批改动内。
