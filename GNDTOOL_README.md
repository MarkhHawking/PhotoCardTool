# gndtool.py —— YunDao 假发 GND 批量构建工具

把 YunDao HDT 假发的一人称/头部件 nif 转成**可丢弃的地面模型**（GND），并生成配套 ESP。
输出结构与游戏里正常工作的 KS Hairdos 假发地面模型完全一致（9 块）：

```
0 BSFadeNode           4 bhkRigidBody         8 BSShaderTextureSet
1 BSInvMarker          5 bhkCollisionObject
2 BSXFlags             6 BSTriShape
3 碰撞形状             7 BSLightingShaderProperty
```

## 依赖
- Python 3（本机 `D:/conda/python.exe`）
- 工作目录里已有：`nif.py`、`esp.py`、`work/yundao/`（解包后的 YunDao mod）、
  `work/yundao/YunDao_Hdt_Hair.esp`
- 模板：`D:/Modding/MO2/mods/KS Hairdos - HDT SMP (Physics)/Meshes/Armor/KSWigsHDT/Ground/HarvestFeathers.nif`

## 命令

```bat
:: 列出所有发型风格（120 个 style / 121 条 ARMO）
python gndtool.py list

:: 构建单个 / 多个 / 全部
python gndtool.py build --styles tiantianblack --out work/out/mine
python gndtool.py build --styles skyblack,lilyblack --out work/out/mine
python gndtool.py build --all --out work/out/all

:: 碰撞：凸包（默认）或盒
python gndtool.py build --styles tiantianblack --collision convex
python gndtool.py build --styles tiantianblack --collision box

:: 碰撞体形态：pad=低矮底座（默认，丢地上不会倒）；fit=贴满包围盒（容易倒）
python gndtool.py build --styles tiantianblack --hull pad
python gndtool.py build --styles tiantianblack --hull fit

:: 方向微调（度）：如果丢出来朝向不对，换着试
python gndtool.py build --styles tiantianblack --pitch -90
python gndtool.py build --styles tiantianblack --pitch 90 --yaw 180
python gndtool.py build --styles tiantianblack --roll 30

:: 依赖处理三选一
python gndtool.py build --styles tiantianblack --plugin-mode patch
python gndtool.py build --styles tiantianblack --plugin-mode standalone
python gndtool.py build --styles tiantianblack --plugin-mode merge
```

## 输出目录

```
<out>/Meshes/YunDao_Hdt/GND/<style>.nif     地面模型
<out>/Textures/...                          自动复制用到的贴图
<out>/*.esp                                 插件（见下）
```

## 三种插件模式

| 模式 | 结果 | 依赖 | 适用 |
|---|---|---|---|
| `patch`（默认） | 新 ESP 覆盖目标 ARMO 的 MOD4 | 需要 `YunDao_Hdt_Hair.esp` | 最小改动、可随时删 |
| `standalone` | 克隆 ARMO+ARMA（新 FormID，EDID 加 `_GND`），masters 只有 Skyrim.esm | 不依赖 YunDao ESP（仍要用它的 nif/贴图） | 想"摆脱原包 ESP" |
| `merge` | 直接重写 `YunDao_Hdt_Hair.esp` 本体（其他记录原样保留） | 无额外插件 | 想"整合到一起"、最终只留一个 ESP |

`merge` 实测：ARMO 121 / ARMA 121 / HDPT 206 / CONT 1 全部保留，只改目标 MOD4；
**会覆盖原 ESP，请先备份**（工具输出到 `<out>/YunDao_Hdt_Hair.esp`，复制替换即可）。

`standalone` 会多出一套独立物品（原物品仍在），用控制台或物品菜单获取；
EDID 冲突时自行改 `--plugin-name` 与 EDID 后缀。

## 细节说明
- 自动只取形状名以 `hair` 开头的 BSTriShape（跳过 `unp` 人体参考、`head` 头部参考），
  并按几何去重（`hair`/`hairl` 常是重复副本）。
- 贴图路径从发型 nif 的 BSShaderTextureSet 自动读取，缺 `_n` 时只带漫反射。
- 顶点格式 28 B：pos + bitangentX + uv + normal/tangent bytes（desc `0x1B00000650407`）。
- 凸包 8 顶点 / 6 平面，平面距离 `d = -max(n·v)`（写反会导致 Havok 崩溃 —— 已修正）。
- 碰撞单位换算：`1 m = 70 游戏单位`。
- 生成后自查：`start + sum(sizes) + 8 = 文件大小`，`BSTriShape.consumed == sizes[6]`。

## 已知限制
- 只处理 YunDao 这套 nif 结构（蒙皮几何在 NiSkinPartition）。
- 不生成 BodySlide 的 .osd 滑块数据；要滑块请在 Outfit Studio 里打开工程另存。
- 工具基于"形状顺序 = 分区顺序"的启发式映射形状与 NiSkinPartition；跑 `--all` 时若某
  个发型报 `no hair shape`，把 nif 发我可以单独适配。
