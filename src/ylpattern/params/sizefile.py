"""尺寸单文件加载：按扩展名支持 TOML（推荐，可写注释）与 JSON。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 环境
    import tomli as tomllib


def load_size_file(path: str) -> dict:
    """读取尺寸单文件，返回原始 dict。

    .toml 用 TOML 解析（支持 # 注释）；.json 用 JSON 解析。
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".toml":
        with open(path, "rb") as fp:
            return tomllib.load(fp)
    if suffix == ".json":
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    raise ValueError(f"不支持的尺寸单格式 '{suffix}'，请使用 .toml 或 .json")
