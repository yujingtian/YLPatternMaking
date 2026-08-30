"""reverse 包异常（独立小模块，避免 __init__ 循环导入）。"""


class ReverseError(Exception):
    """反解析失败（无法识别款型 / 缺关键裁片角色 / 口径冲突）。"""
