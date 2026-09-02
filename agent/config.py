"""agent 服务配置：VLM 配置路径解析 + 照片上传上限。

配置解析顺序（resolve_config_path，**不依赖服务 cwd**）：
  1. 环境变量 ``YLP_VLM_CONFIG``——显式 toml 路径（部署推荐：systemd/
     docker 注入，key 只进服务环境）；
  2. 仓库根 ``vlm.toml``（按本文件位置绝对定位，开发场景「项目根启动
     uvicorn agent.app:app」时与 CLI 的 cwd 约定等价）；
  3. 均缺 -> None -> 交给 ``VLMConfig.load`` 走 ``YLP_VLM_*`` 环境变量
     兜底（纯描述无照片时 provider=None，走纯描述路径零模型调用）。
"""

from __future__ import annotations

import os
from pathlib import Path

from agent.extract.provider import _MIME

# 照片上传白名单（再导出 provider._MIME 键集——_data_uri 按 MIME 编码，
# 白名单与其同源，勿在此另立清单）
PHOTO_SUFFIXES: frozenset[str] = frozenset(_MIME)
MAX_PHOTOS = 4                # 与 CLI --photo 可多次的实用上限一致
MAX_PHOTO_BYTES = 10 * 1024 * 1024   # 单张 10MB（手机原图量级）

_REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_config_path() -> str | None:
    """vlm.toml 路径解析（见模块 docstring 优先级链）。"""
    env = os.environ.get("YLP_VLM_CONFIG")
    if env:
        return env
    repo_toml = _REPO_ROOT / "vlm.toml"
    if repo_toml.is_file():
        return str(repo_toml)
    return None
