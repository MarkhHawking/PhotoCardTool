# PhotoCard Tool 代码结构（v21 起）

入口只有两个文件：`photocard_gui.py`（GUI + 命令行入口）与 `bsa.py`（BSA 名字表读取）。
其余逻辑都在 `pct/` 包里，按“一层一职责”拆开：

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `pct/paths.py` | `BASE/APP_DIR/MAT/TEXCONV/BASE_CARD`、`settings.json` 读写、MO2/游戏目录自动搜索、BSA 索引缓存（`bsa_index.json.gz`） | `bsa` |
| `pct/scene.py` | `load_scene()` / `render_view()`：NIF 几何 + 双视角光栅化 | `photocard_core`、`render_blend`、numpy |
| `pct/imaging.py` | `panel()`、`to_bc7()`、`compose_card()`、`build_card()`、`run_card()`、`square_crop()`、`dds_size()` | `paths`、`scene`、Pillow |
| `pct/mods.py` | `scan_mods()`、`find_in_mod()`、`scan_assets()`（含 `_index_cache`）、`clean_tex_path()`、`rel_to_root()` | 无 |
| `pct/pack.py` | `make_pack()`：复制/改写 NIF+DDS+XML、盒子、ESP（含 TXST/MO2S、BSA 跳过、缺图预检） | `boxesp`、`nifpatch`、`bsa`、`mods` |
| `pct/ui.py` | `FuzzyCombo`（自绘弹层：选中浅色 / 悬停深色）、`ToolTip`、`_fuzzy_*`、`log_trim` | tkinter |
| `pct/screenshots.py` | `shoot_screen()`：全屏遮罩 + 框选 + 自动方形裁切 | tkinter、Pillow |
| `bsa.py` | BSA（SSE v105）文件名表解析 | 无 |

`photocard_gui.py` 只保留：常量与预设、三个页签的界面搭建、事件回调、`main_gui()` / `main_cli()`。
所有逻辑函数通过 `from pct.xxx import ...` 顶层导入，**改逻辑不需要进 GUI 文件**。

## 加功能时改哪里

- 新的渲染参数 / 预设 → `PRESETS`（GUI 常量）+ `render_blend.py`
- 新的贴图/路径处理规则 → `pct/mods.py`（`find_in_mod` / `clean_tex_path`）
- 复制、改写、ESP 记录 → `pct/pack.py`
- 路径、设置、BSA 缓存 → `pct/paths.py`
- 新控件、提示、下拉 → `pct/ui.py`
- 页面布局 → `photocard_gui.py` 里对应的 `# ==== 页签 x ====` 段

## 打包

```
PYTHONPATH=D:\\DSH_SKY_CTD\\pylibs TEMP/TMP=D:/DSH_SKY_CTD/work/tmp \
python -m PyInstaller --onefile --console --name PhotoCardTool \
  --add-data "<abs>\res\Texconv.exe;." --add-data "<abs>\res\02.png;." \
  --hidden-import bsa --hidden-import pct --hidden-import pct.paths \
  --hidden-import pct.imaging --hidden-import pct.scene --hidden-import pct.mods \
  --hidden-import pct.ui --hidden-import pct.pack --hidden-import pct.screenshots \
  photocard_gui.py
```
