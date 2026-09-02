"""agent 编排纯函数：照片落盘 -> extract 门面 -> HTTP 异常映射。

`_build_provider` 是测试注入缝（monkeypatch 它注入 FakeVLM 即可让 HTTP
层全程离线）；真实路径返回 None，交 extract 门面按 config_path 惰性构造。
编排逻辑收在 `run_extract` 纯函数：一期同步等待，二期若改流式/后台任务
只动 app.py 不动这里。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent.extract import ExtractError, extract_from_input
from agent.extract.provider import VLMError

from .config import MAX_PHOTOS, MAX_PHOTO_BYTES, PHOTO_SUFFIXES


def _build_provider(config_path: str | None):
    """provider 注入缝：真实路径恒 None（门面惰性构造），测试替换。"""
    return None


def _validate_photo(name: str, size: int) -> str:
    """单张照片合法性：返回保留的后缀；非法抛 ValueError（-> 422）。"""
    suffix = Path(name).suffix.lower()
    if suffix not in PHOTO_SUFFIXES:
        raise ValueError(f"照片 {name!r} 后缀 {suffix or '(无)'} 不在支持清单"
                         f"（{', '.join(sorted(PHOTO_SUFFIXES))}）")
    if size <= 0:
        raise ValueError(f"照片 {name!r} 是空文件")
    if size > MAX_PHOTO_BYTES:
        raise ValueError(f"照片 {name!r} 超过单张上限 "
                         f"{MAX_PHOTO_BYTES // (1024 * 1024)}MB")
    return suffix


def _save_photos(photo_files) -> tuple[tuple[str, ...], object]:
    """UploadFile 序列 -> (临时路径元组, TemporaryDirectory 上下文)。

    provider._data_uri 只收文件路径（读盘转 base64 data URI），故上传的
    照片必须先落盘；原后缀保留（MIME 按后缀判）。调用方 with 上下文结束
    即清理。
    """
    if len(photo_files) > MAX_PHOTOS:
        raise ValueError(f"照片最多 {MAX_PHOTOS} 张，收到 {len(photo_files)} 张")
    tmp = tempfile.TemporaryDirectory(prefix="ylagent_photos_")
    paths: list[str] = []
    try:
        for i, uf in enumerate(photo_files):
            name = uf.filename or f"photo{i}"
            suffix = _validate_photo(name, uf.size or 0)
            p = Path(tmp.name) / f"photo{i}{suffix}"
            p.write_bytes(uf.file.read())
            paths.append(str(p))
    except BaseException:
        tmp.cleanup()
        raise
    return tuple(paths), tmp


def run_extract(describe: str, photo_files, *, thinking: str | None = None,
                run_probe: bool = True, run_score: bool = True,
                max_refeed: int = 2,
                config_path: str | None = None) -> dict:
    """一次提取编排：校验/落盘照片 -> extract_from_input -> 响应 dict。

    异常向上抛（app.py 映射 HTTP）：
      ValueError      照片非法（422）；
      ExtractError    缺必填尺寸（missing 非空 -> 422 清单）或配置缺失
                      （无 missing -> 503）；
      VLMError        VLM 调用失败（503，消息不含 key）。
    """
    paths, tmp = _save_photos(photo_files)
    try:
        result = extract_from_input(
            describe=describe, photos=paths,
            provider=_build_provider(config_path), thinking=thinking,
            run_probe=run_probe, run_score=run_score,
            max_refeed=max_refeed, config_path=config_path)
    except BaseException:
        tmp.cleanup()
        raise
    return {"ok": True, "model": result.model_name,
            "photo_count": result.photo_count,
            **result.to_web_payload()}
