"""ylpattern —— 牛仔裤数字化打版系统。

核心理念（见 .doc/python工程设计.md）：
  1. 每个点、每条线 = 一个具名生成函数（steps/）
  2. 流程编排驱动绘制（flows/）
  3. 先画后裁（cutter）：整版绘制完成后再逐个裁出独立裁片
"""

__version__ = "0.1.0"

from .api import run  # noqa: E402,F401  顶层便捷入口
