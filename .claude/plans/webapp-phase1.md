# 一期 Web 端设计方案（参数录入 -> SVG 预览 -> DXF 下载）

## 范围（做）

- 版师向参数面板：全量参数**分组折叠**展示（约 180 个），加载款式模板（examples/*.toml 预设）一键填充
- 生成：整版 SVG + **动态裁片清单**（本次实际生成的裁片，含名称/张数，非固定 11 个）各自 SVG 预览
- 下载：裁片合集 DXF、整版 DXF、当前参数导出为尺寸单 toml（打版报表不做下载按钮，仅保留在 /api/draft 响应字段中供详情查看）
- 引擎侧补一层**参数校验**（范围 + 联动规则），错误结构化返回、前端定位到具体参数高亮
- localStorage 自动暂存参数草稿（无账号体系）
- 预留"可调点配置表"下发（一期只定义格式与 3~5 个示例点，不做拖拽交互）

## 不做（二期+）

拖拽微调、Pyodide 客户端引擎、账号/云端保存、多码推码 UI、大模型入口、计费

## 目录结构

```
webapp/
  backend/
    app.py          # FastAPI 入口 + 路由
    schema.py       # 参数分组 schema（分组/类型/默认值/范围/中文标签），手工维护的白名单结构
    pieces.py       # 调 flows + exporters 内存渲染，产出动态裁片清单
  frontend/         # React + TypeScript + Vite
    src/
      App.tsx
      api.ts           # fetch 封装 + 类型定义（与 /api/schema 对齐）
      components/
        ParamPanel.tsx       # 分组折叠参数面板（含搜索/校验高亮）
        PreviewPane.tsx      # 整版 SVG + 裁片 tab 预览
        TemplatePicker.tsx   # 款式模板载入
        Toolbar.tsx          # 生成/下载（DXF/报表/toml）
      hooks/
        useDraft.ts          # 生成请求 + 状态 + localStorage 暂存
    package.json / vite.config.ts / tsconfig.json
tests/
  test_web_validate.py  # 校验规则金标
  test_web_api.py       # FastAPI TestClient
pyproject.toml          # 新增 [project.optional-dependencies] web = fastapi+uvicorn
```

核心包 `ylpattern` 不引入任何新依赖；web 相关代码全部隔离在 `webapp/` + 可选依赖组。

## API 设计

- `GET /api/schema`
  返回：参数分组树（组名/参数：key、类型、默认、枚举、范围、中文标签、提示）、模板列表、可调点配置表（一期占位）。
  schema 为**手工白名单维护**（schema.py 中声明分组与标签，默认值从 `PatternOptions` 实际默认反射，避免两处漂移）。

- `POST /api/draft`
  body: `{ measurements: {...}, options: {...覆盖项} }`（未传字段用默认值，与 toml 加载同构）
  200: `{ ok: true, sheet_svg, report, pieces: [{key, name, count, svg}], warnings: [...] }`
  422: `{ ok: false, errors: [{param, group, message}] }`（结构化，前端逐参数高亮）
  实现：`measurements+options` -> 校验 -> 构造 `PatternOptions` -> 直接调 flows（整版）+ 各 piece flow -> exporters 的 **render 内存函数**（`svg.render_sheet` / `piece_svg.render_piece_svg`），不落盘。

- `POST /api/dxf`（同 body，`?kind=pieces|sheet`）
  用同一参数重新打版 -> `piece_dxf.render_pieces_dxf` / `dxf.render_sheet_dxf` -> DXF bytes 流式下载。

- `GET /api/templates` / `GET /api/templates/{name}`
  返回 examples/*.toml 内容（作为预设模板载入前端表单）。

## 参数分组（schema.py，折叠面板，默认只展开前两组）

1. 基础测量（必填 8 项 + thigh）
2. 款式开关（口袋/袋贴/贴袋/袋布/小表袋/门襟/后省/后机头/后贴袋/裤耳/毗围限制…）
3. 腰头（类型/宽/缝份…）
4. 前口袋（主切口 p1/p2/省/袋口形态…）
5. 前贴袋与袋贴（front_patch / front_pocket_facing）
6. 袋布（front_pouch 净样与缝份）
7. 小表袋（watch_pocket 定位与形态）
8. 门襟（fly 尺寸/折转/分离/双排/缝份）
9. 后省与后机头（back_dart / back_yoke）
10. 后贴袋（back_patch 尺寸/形态/刀口）
11. 裤耳（belt_loop 宽/单长/根数/损耗）
12. 臀腰裆框架（Δ、balance、省道…）
13. 腿部与弧线微调
14. 缩水与缝边（总开关/全局率/逐裁片覆写）
15. 裁片工艺（刀口/缝边逐片…）
16. 版面杂项（piece_gap 等，默认收起）

## 引擎侧改动（ylpattern 内）

- `params/validate.py` 新增：`validate(measurements, options) -> list[Issue]`
  - 数值范围（如 waist 40-150、各放松量合理区间）
  - 联动/前置条件（front_pouch 依赖 front_pocket；facing_intersect 依赖 front_pocket_facing；弯腰头相关约束……）--与 FlowRunner 跳过逻辑不同，这是**硬校验**（报错而非静默跳过），规则来源 = CLAUDE.md 可选步骤前置条件 + 各 toml 注释推荐范围
  - `api.run()` 入口不强制走它（保持向后兼容），仅 web 层调用；二期评估并入 api
- 不改任何公式/步骤/flow

## 前端（React 18 + TypeScript + Vite）

- 左侧参数面板（分组折叠 + 模板选择 + 搜索参数名），右侧预览区
- 组件化：`ParamPanel`（含按组渲染、布尔开关联动显隐子参数、错误红框高亮）、`PreviewPane`（整版 SVG 内联渲染，**Y 翻转**适配浏览器坐标系；裁片 tab）
- 类型安全：`api.ts` 从后端 schema 生成/对齐 TS 类型（一期手写 interface，二期可上 openapi-typescript 自动生成）
- 校验错误 -> 自动展开所在组并高亮 + 顶部错误列表
- DXF/报表/toml 导出按钮；输入防抖自动 localStorage 暂存（useDraft hook）
- 开发期 Vite proxy 到 FastAPI（localhost:8000），生产构建产物由 FastAPI 静态托管（frontend/dist），单进程部署
- Node 仅前端构建需要，引擎与后端不受影响

## 测试

- 校验层金标：矛盾参数组合 -> 预期 Issue 列表（沿用项目金标测试风格）
- API 测试：TestClient 全链路（合法参数 200 且 pieces 动态清单正确反映开关、非法参数 422、DXF 非空）

## 实施顺序

1. `params/validate.py` + 测试（引擎侧，独立可验）
2. webapp/backend schema.py（分组白名单 + 反射默认值）
3. FastAPI 路由 + pieces 动态清单 + 测试
4. 前端 React+TS+Vite 工程（脚手架、组件、预览、导出、暂存）
5. pyproject web 可选依赖组 + README 补充启动方式（`pip install -e ".[web]"` 后 `uvicorn webapp.backend.app:app`；前端 `cd webapp/frontend && npm i && npm run dev`，构建后 `npm run build` 产物由 FastAPI 托管）
