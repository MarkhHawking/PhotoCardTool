import os, shutil, subprocess, zipfile

ROOT = r'D:\DSH_SKY_CTD'
OUT = os.path.join(ROOT, 'work', 'out')
PKG = os.path.join(OUT, 'YunDao_Tiantian_GND')
STYLE = 'tiantianblack'
NAME = 'YunDao Tiantian GND'

def cp(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

# clean
if os.path.isdir(PKG):
    shutil.rmtree(PKG)

# meshes
cp(os.path.join(OUT, 'gnd', STYLE + '.nif'), os.path.join(PKG, 'Meshes', 'YunDao_Hdt', 'GND', STYLE + '.nif'))
# plugin
cp(os.path.join(OUT, 'YunDao_Tiantian_GND.esp'), os.path.join(PKG, 'YunDao_Tiantian_GND.esp'))
# textures (own copies so the GND renders even if YunDao textures change)
for fn in ['tiantian.dds', 'tiantian_n.dds']:
    cp(os.path.join(ROOT, 'work', 'yundao', 'Textures', 'YunDao_Hdt', 'Hair', fn),
       os.path.join(PKG, 'Textures', 'YunDao_Hdt', 'Hair', fn))
# BodySlide data
cp(os.path.join(OUT, 'gnd', STYLE + '.nif'),
   os.path.join(PKG, 'CalienteTools', 'BodySlide', 'ShapeData', NAME, STYLE + '.nif'))

osp = '''\ufeff<?xml version="1.0" encoding="UTF-8"?>\r
<SliderSetInfo version="1">\r
    <SliderSet name="YunDao Tiantian GND">\r
        <DataFolder>YunDao Tiantian GND</DataFolder>\r
        <SourceFile>tiantianblack.nif</SourceFile>\r
        <OutputPath>meshes\\YunDao_Hdt\\GND</OutputPath>\r
        <OutputFile GenWeights="false" PreventMorphFile="false" KeepZappedShapes="false">tiantianblack</OutputFile>\r
        <Shape target="tiantianblack">tiantianblack</Shape>\r
    </SliderSet>\r
</SliderSetInfo>\r
'''
os.makedirs(os.path.join(PKG, 'CalienteTools', 'BodySlide', 'SliderSets'), exist_ok=True)
open(os.path.join(PKG, 'CalienteTools', 'BodySlide', 'SliderSets', NAME + '.osp'), 'w', encoding='utf-8', newline='').write(osp)

readme = '''# YunDao Tiantian（Black）地面模型 — Aerith 风格

把 YunDao 假发 **YD Tiantian [Black]**（`YunDaoA_tiantian_black`，FormID `0x01001DE2`）的地面/掉落模型换成“该发型自身几何 + 实体碰撞”的静态网格，效果与 `[Cloud] Aerith Hair` 的地面模型一致：丢到地上会正常落地、可被准星选中、可拾取。

## 为什么之前会消失/悬空

假发是 `ARMO`+`ARMA` 装备。`ARMO` 的 **MOD4** 是“女性地面/物品栏模型”（MOD2 是男性）。原版 YunDao 的 MOD4 直接指向**带头部蒙皮和 HDT 物理的头发 nif**（NiSkinInstance/NiSkinPartition + XML，没有 BSFadeNode 根、没有碰撞体），所以丢在地上时引擎拿不到可站立的碰撞体 → 悬空、沉底或干脆不可选。Aerith 的 MOD4 是专用静态网格（BSFadeNode 根 + `bhkRigidBody` + `bhkConvexVerticesShape` 凸包），所以正常。

本包做的事：把该假发自身的顶点/三角形从 `NiSkinPartition` 里取出，转成静态 `BSTriShape`，用 `BSFadeNode` 作根，配 `bhkRigidBody` + `bhkConvexVerticesShape`（按该发型包围盒生成的凸包），只覆盖这一条 `ARMO` 的 MOD4；穿着模型（ARMA MOD3）完全不动。

## 包内容

```
YunDao_Tiantian_GND.esp                    覆盖用插件（仅 1 条 ARMO 记录）
Meshes\\YunDao_Hdt\\GND\\tiantianblack.nif   新的地面模型（BSFadeNode + 凸包碰撞）
Textures\\YunDao_Hdt\\Hair\\tiantian*.dds    该发型的贴图副本
CalienteTools\\BodySlide\\ShapeData\\...      供 BodySlide / Outfit Studio 编辑的源文件副本
CalienteTools\\BodySlide\\SliderSets\\...     对应的 BodySlide 项目
```

## 安装（MO2）

1. 先确保 `YunDao HDT Wigs and RM Hair` 已安装并启用（本插件以 `YunDao_Hdt_Hair.esp` 为 master）。
2. 把本包压缩成 zip 用 MO2 安装，或直接放进 `mods\\YunDao Tiantian GND\\`。
3. 插件顺序：**放在 `YunDao_Hdt_Hair.esp` 之后**（覆盖它）。
4. 进游戏，`player.additem 01001DE2 1`（或用 Modex/AddItemMenu 取），丢到地上测试。

## 验证

- 丢在地上应能落地、准星可选中、可再拾取。
- 物品栏图标/预览仍由原 MOD4 决定（现在是静态网格缩略图）。
- 穿着外观（戴在头上）完全没变，仍是原版 HDT-SMP 头发。

## 在 Outfit Studio / BodySlide 里编辑

- **Outfit Studio**：`File → Open` 直接打开 `Meshes\\YunDao_Hdt\\GND\\tiantianblack.nif`，可改几何、换贴图、重新生成碰撞；改完 `File → Export → To NIF` 覆盖同名文件即可。
- **BodySlide**：项目已放在 `CalienteTools\\BodySlide\\SliderSets\\YunDao Tiantian GND.osp`，源文件在 `ShapeData\\YunDao Tiantian GND\\tiantianblack.nif`。打开 BodySlide → Outfit/Body 选 `YunDao Tiantian GND` → Build 即输出到 `Meshes\\YunDao_Hdt\\GND\\tiantianblack.nif`。
- 注意：这是**静态地面模型**，没有骨骼/蒙皮，不要勾 Build Morphs。

## 扩展到其它款式/颜色

同一套流程可复用到 YunDao 的 105 个发型文件：取该发型 nif 里所有 `NiSkinPartition` 的顶点/三角形 → 生成静态 `BSTriShape` → 以本包的 10 块结构重写 → 插件里把对应 `ARMO` 的 MOD4 指过去。若需要，我可以再生成其它款式/颜色的补丁。

## 已知限制

- 本插件是**覆盖补丁**，依赖 `YunDao_Hdt_Hair.esp`；如果你把 YunDao 整个卸载，本插件会让游戏缺 master。
- FormID 与记录内容保持不变，只改 MOD4，因此对存档是安全的（可随时移除）。
'''
open(os.path.join(PKG, 'README.md'), 'w', encoding='utf-8').write(readme)

# zip
zip_path = os.path.join(ROOT, 'YunDao_Tiantian_GND.zip')
if os.path.exists(zip_path):
    os.remove(zip_path)
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for base, dirs, files in os.walk(PKG):
        for f in files:
            full = os.path.join(base, f)
            rel = os.path.relpath(full, PKG)
            z.write(full, rel)
print('zip', zip_path, os.path.getsize(zip_path))
for base, dirs, files in os.walk(PKG):
    for f in files:
        full = os.path.join(base, f)
        print(os.path.getsize(full), os.path.relpath(full, PKG))
