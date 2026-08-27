# 整版测量工具方案（Web SheetView 交互测量）

> 状态：方案已确认，待实现（2026-08-26）
> 范围已与用户确认：仅 Web 整版交互测量；不改后端/引擎、不改报表、不加 CLI 静态标注。

## 背景与目标

整版生成后无法得知线/弧的具体长度：SVG 无长度标注、report.txt 无长度数值（连曲线都不列出）。需要一个**交互式测量工具**：

- **悬停显示**：鼠标移到任意直线/弧线上 → 高亮该元素 + 气泡显示元素名和长度（cm）
- **点击钉住**：点击元素 → 长度标注固定钉在线旁，可同时钉多条，随整版刷新重算（拖把手时实时更新）
- **自由测距**：点两个任意点量直线距离（不限于已有元素，如量对角线），吸附端点/关键点
- 测量开关是**纯前端视图态**（本地 useState，不进 PatternOptions、不触发 stale/重生成）
- **默认关闭**：点击右上角「测量」按钮后才开启，再点一次或 Esc 关闭并清空全部

长度在前端从 SVG DOM 计算：直线端点精确；曲线是 32 点采样 polyline，折线求和 ÷ scale（=10 px/cm），误差 ~0.002cm，远小于 0.1cm 打版精度。

## 已核实的代码事实（实现必须遵守）

- SVG 由 `src/ylpattern/exporters/svg.py render_sheet` 生成：图层 `<g id="reference|struct|curves|elements">`；每个 line/polyline/circle 带 `id="{元素名}"`；文字标注带 `data-name`；根元素 `data-scale` 等全精度变换常量。
- **首子元素是全幅白色 `<rect>`**：空白区所有事件 target 恒为它 → 悬停命中**必须几何搜索**，不能依赖 e.target。
- **元素 id 含点号**（如 `front.crotch_point`）→ `querySelector('#front.xxx')` 静默失配，必须用 `[id="..."]` 属性选择器或遍历建 Map。
- SVG 坐标序列化精度 `.1f`（=0.01cm），满足显示需求。
- `webapp/frontend/src/components/SheetView.tsx`：把手的 handle-hit `pointerdown → startDrag` 内有 `e.stopPropagation()` → host 的 `onPointerDown`（平移入口）不触发 → **测量点击与把手拖拽天然互斥，无需改 startDrag**。
- overlay 注入 effect（约 404-470 行，deps 含 `svg/handles/transform/viewBox`）：每次整版刷新销毁重建 SVG 子树后重建把手层；**viewBox-only 重跑（缩放平移）时旧 DOM 存活**，effect 开头有防御性 `#yl-handles` 删除——测量层必须同模式。
- `transform.ox/top` 随内容包围盒变化（拖把手重生成后会漂移）→ **跨刷新只存 cm 坐标或元素 id**，不能存 user px。
- 气泡模式可复用：`makeBubble/updateBubble`（getBBox 包裹 rect+text，`/k` 屏幕恒定）；坐标换算 `pointerCm/cmToUser/screenScale` 现成。
- React 限制：**`dangerouslySetInnerHTML` 节点不能再有 React 子元素** → 浮动工具条不能塞进 host div，需包一层 wrapper。

## 改动清单

| 文件 | 改动 |
|---|---|
| `webapp/frontend/src/components/measure.ts` | **新建**：几何索引 + 命中/吸附/长度纯函数（只读 DOM、只算几何，无 React 依赖） |
| `webapp/frontend/src/components/SheetView.tsx` | 主要改动（约 +200 行） |
| `webapp/frontend/src/styles.css` | +约 30 行 |
| PreviewPane / Toolbar / App / types.ts / 后端 | **零改动** |

## 1. 新建 measure.ts（纯函数）

```ts
export interface GeomEntry {
  id: string; kind: 'line' | 'polyline'
  pts: number[]          // user px 平铺 [x0,y0,x1,y1,...]
  bbox: {x0,y0,x1,y1}    // bbox 预剔除
  lengthUser: number     // 折线段长和（user px）；cm = ÷ scale
  label: string          // 显示名：[data-name] textContent ?? id
}
export interface SnapPoint { id: string; x: number; y: number }  // user px
export interface GeomIndex {
  entries: GeomEntry[]; byId: Map<string, GeomEntry>
  snaps: SnapPoint[]     // circle.pt 圆心 + line 两端 + polyline 首末点
  scale: number          // 根 data-scale
}
export function buildGeomIndex(svgEl: SVGSVGElement): GeomIndex
  // 遍历 '#reference line, #struct line, #curves polyline'（circle.pt 只进 snaps）
  // points 按 /[\s,]+/ 切分；所有 DOM 读取集中在此函数
export function nearestEntry(idx, x, y, tolUser): GeomEntry | null
  // bbox+tol 预剔除 → 逐段点-线段距离（segDist2），< tol 的最近者
export function nearestSnap(idx, x, y, tolUser): SnapPoint | null
export function elementLengthCm(e: GeomEntry, scale: number): number  // lengthUser / scale
export function entryMidpoint(e: GeomEntry): {x, y, nx, ny}
  // 累计弧长中点所在段 + 该处单位法向（钉住标签锚定用）
export function distLabelPos(ax, ay, bx, by): {x, y, nx, ny}
```

量级：整版数百 line + 百条级 polyline×33 段，单次全扫 <1ms，rAF 合帧后无压力。

## 2. SheetView.tsx 改动

### 2.1 state / ref

```
state（仅 3 个低频值）: measureOn / distArmed / pinnedCount
ref: measureOnRef, distArmedRef（高频回调读最新值，照 dragRef 模式）
     geomRef（GeomIndex）+ geomKeyRef（svg+transform 指纹，viewBox 变化不重建）
     pinnedRef: string[]（钉住元素 id，只存 id）
     distsRef: {ax,ay,bx,by}[]（cm 坐标 + 可选 snapA/snapB 元素 id）
     distPending（测距 A 点 cm + snap id 或 null）
     hoverIdRef / mDomRef（测量层各常驻节点引用）/ rafRef / lastMoveRef
```

钉住/测距**用 ref 不用 state**：钉住层重建挂在现有 overlay effect（deps 不含 pinned）里，ref 恒读最新值；与既有"拖拽会话全走 ref 避免全树重渲"哲学一致。

### 2.2 新增 `pointerUser` callback

与 `pointerCm` 并列：`getScreenCTM().inverse()` 后直接返回 **user px**（不转 cm）。测量全程在 user 空间做几何，仅存储（测距 A/B）与显示换算时进出 cm。`pointerCm` 保持不动。

### 2.3 JSX 结构（wrapper + 浮动工具条）

```tsx
return (
  <div className="sheet-wrap">                       {/* 新增 position:relative; height:100% */}
    <div ref={hostRef} className={...原样+measuring} onPointerDown={...}
         dangerouslySetInnerHTML={{ __html: svg }} />
    {measureOn && (
      <div className="measure-bar" onPointerDown={e => e.stopPropagation()}>
        [测距 Button(armed 时 primary)] [清除 Button 显示计数] 提示文字
      </div>
    )}
  </div>
)
```

- **开关行为（默认关闭）**：工具条常驻首按钮 `[测量]`（antd Button size="small"，点击开启、激活态 type="primary"）；**未开启时悬停/点击/测距一律不生效，整版交互与现状完全一致**；开启后才展开 `[测距]`、`[清除]` 与提示文字；再点 `[测量]`（或 Esc 链走到底）→ 关闭并清空全部钉住/测距标注。
- 工具条 `onPointerDown` 必须 stopPropagation，否则点按钮会触发 host 平移。
- 提示文字两态即可：`!distArmed → "悬停查看长度，点击钉住；空白拖动平移"`；`distArmed → "依次点击两点测距（Esc 取消）"`。
- `measureOn` 时 host 加 class `measuring`（cursor: crosshair；panning 时 grabbing 照旧覆盖）。

### 2.4 平移 vs 点击歧义（armed 阈值，最小侵入）

- `panRef` 结构增加 `armed: boolean; downX: number; downY: number`。
- `onHostPointerDown`：非测量模式 `armed=true` + `setPanning(true)`（与现状完全一致，零回归）；测量模式 `armed=false`，仍 setPointerCapture。
- `doPan`：`!armed` 且移动 ≤4px（屏幕）直接 return；超 4px → `armed=true` + `setPanning(true)` 后按原逻辑平移。
- 容器事件 effect 的 `onUp`：`panRef` 存在且 `measureOnRef.current && !armed` → 判定为测量点击，调 `measureClick(e)`。**只在 pointerup 分支判定点击，pointercancel 忽略**（现两事件共用 onUp，需拆开或传标志）。

### 2.5 onMove 优先级链 + rAF 帧

`onMove`：`dragRef`（不变）> `panRef`（doPan，见 2.4）> `measureOn && 无拖拽无平移` → 存 `lastMoveRef` + 调度 rAF（pending 则跳过）。

`processMeasureFrame`（rAF 内一次）：
- `pointerUser(lastMove)` → `k = screenScale(svgEl)`
- hover：`nearestEntry(8/k)` → 命中变化时重画高亮克隆 + 更新气泡（`{label} {len.toFixed(2)} cm`，气泡定位照 updateBubble 的 getBBox 模式）；未命中 → 隐藏
- `distPending` 存在：`nearestSnap(10/k)` → 吸附环；橡皮筋 B 端 = 吸附点或指针 + 实时距离标签

挂起条件：`dragRef.current`（把手拖拽中）或 `panRef.current?.armed`（平移中）不做 hover。

### 2.6 overlay effect 扩展（核心存活机制）

在现有 effect（deps `[svg, handles, transform, viewBox, ...]`）内追加：

1. 开头与 `#yl-handles` 删除并列：`svgEl.querySelectorAll('#yl-measure').forEach(n => n.remove())`。
2. 索引门控：`key = svg + '|' + scale,ox,top`；变化才 `buildGeomIndex`。viewBox 变化不重建（user 空间几何不变，只有 `/k` 尺寸需重算）。
3. `measureOnRef.current` 时建 `g#yl-measure`，按序填充：已完成测距项（橙色虚线+两端十字+距离标签；snap 元素仍在则从 byId 重解析端点——测距跟随版型变形，否则回退存的 cm 经 cmToUser 重定位）→ 钉住元素标注（byId 查新几何重算长度+entryMidpoint 定位；**查不到的（元素已消失）直接从 pinnedRef 移除**）→ distPending 的 A 标记 → hover 高亮/气泡/吸附环/橡皮筋的常驻占位节点（display:none，帧内直改属性）。
4. `svgEl.appendChild(measureG)` 放在 `appendChild(handlesG)` **之前**（把手层在上，命中永远优先）；`#yl-measure` 整层 `pointer-events: none`。
5. 末尾 `setPinnedCount(pinnedRef.current.length + distsRef.current.length)`（同值 React bail out，高频跑无渲染开销）。
6. 建议抽 `rebuildMeasureLayer(svgEl)` 内部函数：effect 调它、点击 toggle 后也直接调（不绕道 setState）。

**实时更新即由此免费获得**：拖把手每 50ms 重生成 → effect 重建测量层 → 钉住项从新 DOM 重算长度。

### 2.7 measureClick(e) 优先级

```
1. distArmed：pending? 设 B（吸附优先）→ distsRef.push → 清 pending（armed 保持，连续测距）
              : 设 A（吸附优先，存 cm + snap id）
2. !distArmed：命中已有测距线段（点到 AB 线段 <8/k）或其标签锚（<15/k）→ 删除该条
3. !distArmed：nearestEntry(8/k) 命中 → pinnedRef 已含则移除（unpin），未含则 push（pin）
4. 无命中 → 无操作（空白轻点不误触）
```

### 2.8 高亮方式

overlay 克隆双描边：白底 `5/k` + 绿 `3/k` 两条重叠 line/polyline（白底保证深色 structline 上也清晰）。不改原元素（每次刷新被 innerHTML 销毁重建，改 class 会丢且需重放）。

### 2.9 Esc 与关闭

- `measureOn` 为 true 时挂 window keydown（一次性 effect）：`distPending → 取消` > `distArmed → 退` > `关测量（全清）`；过滤 `e.target` 为 INPUT/TEXTAREA。
- 关闭清理函数：清 pinnedRef/distsRef/distPending、setDistArmed(false)、取消 rAF、删 `#yl-measure`、setPinnedCount(0)、setMeasureOn(false)。

### 2.10 显示格式

`{label} {len.toFixed(2)} cm`；测距标签 `{dist.toFixed(2)} cm`（与拖拽气泡 toFixed(2) 约定一致）。label 取 `[data-name="{id}"]` textContent，无（show_labels=False）回退 id。

## 3. styles.css 增补

```css
.sheet-wrap { position: relative; height: 100%; }
.measure-bar { position:absolute; top:8px; right:8px; z-index:5; display:flex;
  gap:6px; align-items:center; background:#fff; border:1px solid #e8e8e8;
  border-radius:4px; padding:4px 8px; box-shadow:0 1px 4px rgba(0,0,0,.12); }
.measure-hint { font-size:12px; color:#888; }
.sheet-view.measuring svg { cursor: crosshair; }
#yl-measure { pointer-events: none; }
#yl-measure .m-hl-under { stroke:#fff; fill:none; stroke-linecap:round; }
#yl-measure .m-hl { stroke:#2c6e49; fill:none; stroke-linecap:round; }
#yl-measure .m-label rect { fill:rgba(44,110,73,.92); }
#yl-measure .m-label text { fill:#fff; font:11px monospace; dominant-baseline:hanging; }
#yl-measure .m-dist { stroke:#d46b08; stroke-dasharray:5 3; fill:none; }
#yl-measure .m-dist rect { fill:rgba(212,107,8,.92); }
#yl-measure .m-dist text { fill:#fff; font:11px monospace; dominant-baseline:hanging; }
#yl-measure .m-cross { stroke:#d46b08; }
#yl-measure .m-snap { fill:none; stroke:#2c6e49; }
```

线宽/半径/字号在 JS 侧按 `/k` 设定（照 handle-dot `4.5/k` 模式），CSS 只管颜色。主题色沿用 #2c6e49（绿）/ #d46b08（橙）。

## 交互状态机摘要

```
普通模式：行为与现状完全一致（平移/缩放/把手拖拽/双击复位）
测量模式（点击「测量」开启）：hover 高亮+气泡；按下→armed=false，
  移动>4px→平移 | 轻点抬起→measureClick（测距删除/pin-unpin）；Esc→关测量（全清）
测距中（点击「测距」）：点击设 A（吸附）→ 橡皮筋+实时距离 → 点击设 B 钉住；
  保持 armed 连续测距；Esc 链：取消进行中→退测距→关测量
```

## 边界情况

- SVG 刷新（参数修改/把手拖拽）：innerHTML 重注入销毁测量层 → effect 重建，钉住项重算（值实时更新）；viewBox-only 重跑 → 防御性删除再重建。
- 把手拖拽期间：dragRef 非空挂起 hover/点击；A 标记由 effect 重建存活（存 cm）。
- transform 漂移：测距存 cm、钉住只存 id → 重建时全部重推导。
- 元素消失：pin 项移除；测距 snap 元素消失回退 cm 坐标。
- 缩放平移：几何在 user 空间，层随 viewBox 变换自动正确；effect deps 含 viewBox → `/k` 尺寸重算。
- show_labels=False：名称回退 id。

## 实现顺序（建议 commit 粒度）

1. `measure.ts` 纯函数（可独立 review）
2. styles.css + wrapper 结构 + 工具条 + armed 平移改造（回归验证普通模式不变）
3. overlay 扩展：索引 + 空层重建 + hover 高亮气泡
4. 点击 pin/unpin + 计数
5. 测距：吸附 + 橡皮筋 + 钉住 + Esc 链
6. 跑验证清单

## 验证

1. **构建**：`cd webapp/frontend && npm run build`（tsc 类型检查通过；无需重跑 build:engine，未动引擎）。
2. **手动清单**（`npm run dev` → http://localhost:5173，或 uvicorn :8000）：
   - 默认关闭时交互与现状完全一致；点「测量」开启 → 悬停结构线：高亮 + 气泡（名称+长度）；悬停弧线（polyline）同样
   - 点击钉 3 条 → 3 个标注；再点其中一条 → 消失（toggle）；清除计数正确
   - 滚轮放大 8x / 缩小 0.3x：命中仍灵敏、标签字号视觉恒定
   - 测量模式空白按下拖动 → 平移正常；按下 5px 内抬起 → 不平移、判定为点击
   - 拖把手（如立裆深）→ 钉住数值实时变化；双击把手复位 → 数值回默认
   - 测距：点 A（悬停关键点出现吸附环）→ 橡皮筋 + 实时距离 → 点 B → 橙色虚线钉住；可连续测多条
   - Esc×3 链：取消进行中 → 退测距 → 关测量（全清）；[清除] 按钮全清
   - 关测量后回归：把手拖拽/双击复位/平移/缩放全部原状、无层残留
   - 测量开关反复切换 → 参数面板无变化、无"已过期"横幅（纯视图态）
   - 切裁片 tab 再回整版 → 行为一致
3. **长度交叉核对**：
   - 直线：展开打版报表，该线两端点坐标 `(x,y)~(x,y)` 勾股值 vs 悬停显示值（报表含直线端点，一致）
   - 弧线：Python 侧独立计算对比（`api.run` 返回 ctx）：
     ```bash
     python -c "from ylpattern.api import run; from ylpattern.cutter import edge_length; \
       ctx = run(waist=..., hip=..., ...);  # 参数照 examples/size_female_165.toml
       [print(c.name, round(edge_length(c.geom), 2)) for c in ctx.sheet.curves]"
     ```
     与 UI 悬停值抽样比对，差 <0.01cm（前端 32 点 vs 引擎 64 点采样，一致即收敛）
