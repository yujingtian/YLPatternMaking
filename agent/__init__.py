"""agent 包：全部大模型相关代码（ylpattern = 纯引擎，2026-09-03 边界）。

构成：extract/（照片参数提取管线 12 模块，含 provider 唯一触网点）+
cli.py（`python -m agent extract` 命令行入口）+ app.py（FastAPI HTTP
服务，POST /api/extract）+ runner/config（服务编排与 vlm 配置）。
未来的会话/记忆也落在本包（sessions.py 等，二期）。

依赖约定（方向唯一：agent → ylpattern，引擎侧零反向引用）：
- 只 import ylpattern 引擎公开层（params、flows.closure、exporters），
  extract 内部模块间相对导入，不 import ylpattern.extract（已不存在）；
- vlm.toml / YLP_VLM_* 密钥只存在于服务端环境，不进响应、不进日志。
"""
