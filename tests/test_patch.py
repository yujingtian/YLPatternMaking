"""贴袋净形公式金标测试：patch_net_vertices（后贴袋绘制.md §二.1、
前口袋绘制.md §五）。

金标（w=14, h=16, bottom_width=12, tip_depth=2.5, chamfer=2，bi=(14−12)/2=1）：
  rectangle            (0,0) (14,0) (14,16) (0,16)
  baker_shield         (0,0) (14,0) (13,16) (7,18.5) (1,16)
  angular 后贴袋       (0,0) (14,0) (14,14) (12,16) (2,16) (0,14)
                       （不消费底宽 bi，顶点全用 w/c）
  angular 前贴袋       (0,0) (14,0) (13,14) (11,16) (3,16) (1,14)
                       （消费底宽 bi，底边随内收：w−bi=13、bi=1）
bottom_width=0 时 bi=0，baker 退化为同宽五边形、前 angular 与后 angular 一致。
"""

import pytest

from ylpattern.formulas import patch


def test_rectangle():
    assert patch.patch_net_vertices("rectangle", 14, 16) == \
        ((0.0, 0.0), (14.0, 0.0), (14.0, 16.0), (0.0, 16.0))


def test_baker_shield():
    assert patch.patch_net_vertices(
        "baker_shield", 14, 16, bottom_width=12, tip_depth=2.5) == \
        ((0.0, 0.0), (14.0, 0.0), (13.0, 16.0), (7.0, 18.5), (1.0, 16.0))


def test_baker_shield_same_width():
    # bottom_width=0 → bi=0，同宽五边形（尖底 (7,18.5)，底两点贴侧边）
    assert patch.patch_net_vertices(
        "baker_shield", 14, 16, tip_depth=2.5) == \
        ((0.0, 0.0), (14.0, 0.0), (14.0, 16.0), (7.0, 18.5), (0.0, 16.0))


def test_angular_back_no_taper():
    # 后贴袋：不消费底宽 bi，六边形顶点全用 w/c
    assert patch.patch_net_vertices(
        "angular", 14, 16, bottom_width=12, chamfer=2) == \
        ((0.0, 0.0), (14.0, 0.0), (14.0, 14.0),
         (12.0, 16.0), (2.0, 16.0), (0.0, 14.0))


def test_angular_front_taper():
    # 前贴袋：消费底宽 bi（w−bi=13、bi=1），斜切起点随内收
    assert patch.patch_net_vertices(
        "angular", 14, 16, bottom_width=12, chamfer=2,
        chamfer_bottom_taper=True) == \
        ((0.0, 0.0), (14.0, 0.0), (13.0, 14.0),
         (11.0, 16.0), (3.0, 16.0), (1.0, 14.0))


def test_angular_front_no_taper_degenerates_to_back():
    # bi=0 时前贴袋 angular 与后贴袋一致（底宽口径消失）
    front = patch.patch_net_vertices(
        "angular", 14, 16, chamfer=2, chamfer_bottom_taper=True)
    back = patch.patch_net_vertices("angular", 14, 16, chamfer=2)
    assert front == back


@pytest.mark.parametrize("shape", ["custom", "unknown", ""])
def test_invalid_shape_raises(shape):
    # custom 角点由 *_custom_points 直接给定，不经本函数
    with pytest.raises(ValueError):
        patch.patch_net_vertices(shape, 14, 16)
