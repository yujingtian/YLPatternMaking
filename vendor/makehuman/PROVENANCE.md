# PROVENANCE — MakeHuman CC0 网格数据

## 来源

- 仓库：`makehumancommunity/makehuman`（GitHub）
- tag：`v1.3.0`，commit `1f508f60`
- 许可：捆绑资产 **CC0 1.0 通用**（见 [LICENSE.ASSETS.md](LICENSE.ASSETS.md)，§D 输出物无主张）
  ——本项目**只借用 CC0 数据，不移植任何 AGPL 代码**（商业化许可红线）。

## 文件清单与 sha256

| 文件 | sha256 |
|---|---|
| `base.obj` | `8e761e6624b8f54536409135d1636da63b32486a90d4897f84e121d144f6fb4c` |
| `LICENSE.ASSETS.md` | `f6089cba01cb570a24712b41ab8a586ccd3cc5ef53dc266ca50b95c288956d2c` |
| `rigs/default.mhskel` | `99f179bce0aa850b45d4191a1d0d234c5851f881c057439470ded3bddf729a24` |
| `rigs/default_weights.mhw` | `0f3641d651ae3d00ad6b4ccee43142edb109d3bd909d27d9e4139ef1beed8625` |
| `targets/macrodetails/caucasian-male-young.target` | `70e228ba7164737dae664454394536fc5935fa48d333c1a97d77e2dc6eacc5f5` |
| `targets/macrodetails/universal-female-young-averagemuscle-averageweight.target` | `4ba5396ddabda448ece15650a566fbebfbb10239256ccb201e8f883429e12249` |
| `targets/measure/measure-waist-circ-incr.target` | `4949212ec9a5e227b177a029ee42b0be3fd3b273a211bc91c6f4d4dbf0334856` |
| `targets/measure/measure-waist-circ-decr.target` | `6a976bd7819fa037a290b381bb3e04dfd04220dddeac194c476472295d2baba8` |
| `targets/measure/measure-hips-circ-incr.target` | `e4294db231dd3283680e6be4b9d3d8d81aa7c575a32f937f8d0751b1ec3d6512` |
| `targets/measure/measure-hips-circ-decr.target` | `8a98e80047ab89148d60067aad3b452ce715eadcaf7a1e28402140dd1ac8fb11` |
| `targets/measure/measure-thigh-circ-incr.target` | `5dca89b139df6f9b7c7641485dee18e9f0da10087359b9df5ca6a1e752ea0bcc` |
| `targets/measure/measure-thigh-circ-decr.target` | `fe5303874b0ffe26a69cefd3e213b6478eec4648f60b0b110a1e176ccf24eaa9` |
| `targets/measure/measure-knee-circ-incr.target` | `a3f57ce71ae6955ebca4b3927fa9adcf7d4718df7e0c8641adea37cb1e781ecb` |
| `targets/measure/measure-knee-circ-decr.target` | `fc8d4ff31694018587f32979183f2342ac2e4882b99ff9eac71050eac2bcca27` |
| `targets/measure/measure-calf-circ-incr.target` | `c6106ec484a875a8763a7e9b12a4891da8efcd5152efbc1c7061f40bdc4353a6` |
| `targets/measure/measure-calf-circ-decr.target` | `2914fc47781e23987607c6546f4535ae5d8b04e2e2bec908ab588ee94e74aa15` |
| `targets/measure/measure-ankle-circ-incr.target` | `01bbc7823b71199826e987227e22fc97ac88247467368414fd11309062d0fdcf` |
| `targets/measure/measure-ankle-circ-decr.target` | `0abb3c55b334b8508addf583a626f775ac45fa95eff773131dbd7ff48bf6d95d` |

原文件在源仓库中的路径：`base.obj` → 顶点级基础网格导出；
`targets/*` → `makehuman/data/targets/` 同名文件（v1.3.0 树）；
`rigs/*` → `makehuman/data/rigs/` 同名文件（骨架 `default.mhskel` 与蒙皮权重
`default_weights.mhw`，JSON 内嵌 `license: "CC0"`——站直姿势 clean-room LBS 的
数据源，权重顶点索引与 `base.obj` 全量顶点表严格对应；关节组顶点落在 helper
几何组、约四成权重项挂在 body 组外顶点上，消费时按索引过滤）。

## 派生物

`webapp/frontend/public/bodymesh/{base.bin, targets.json, LICENSE.ASSETS.md}`
由 `python scripts/vendor_makehuman.py` 从本目录确定性派生（切割+站直姿势链：
官方 rigs 蒙皮 clean-room LBS 站直（大腿/小腿/脚逐关节角度）+ 下半身
裁切 + 去臂连通域、官方 12 场顶点索引重映射与增量随帧旋转；口径权威
`.doc/python工程设计.md` §10.11）。派生不改变许可（CC0）。

## 再生与校验

```bash
python scripts/vendor_makehuman.py            # vendor/ -> public/bodymesh/
python -m pytest tests/test_vendor_bodymesh.py -q
sha256sum base.obj LICENSE.ASSETS.md $(find targets -type f | sort)
```
