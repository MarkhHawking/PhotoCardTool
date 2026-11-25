# 把本地仓库推到 GitHub

本目录已经是 git 仓库（分支 `main`，1 个提交，39 个文件 / 4.8 MB）。
**推送需要你本机的 GitHub 凭据**——这台机器上的 git 是随 DSH 附带的精简版（niugit），
没有 credential manager，也没有 SSH key，所以最后一步要在你自己的终端/客户端里做。

## 方式 A：网页/桌面客户端（最省事）

1. 在 GitHub 新建一个空仓库（不要勾 README / .gitignore，名字随意，例如 `PhotoCardTool`）。
2. 在本目录打开终端，执行：

```bash
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

第一次 push 会弹浏览器登录（如果你用的是 Git for Windows / GitHub Desktop）。
用 GitHub Desktop 的话：`File → Add local repository` 选 `D:\DSH_SKY_CTD`，再 `Publish repository`。

## 方式 B：用我导出的 bundle（换台机器也能用）

`work/out/photocard_tool_v23.bundle` 里是完整的仓库历史：

```bash
git clone photocard_tool_v23.bundle PhotoCardTool
cd PhotoCardTool
git remote set-url origin https://github.com/<用户名>/<仓库>.git
git push -u origin main
```

## 方式 C：在这台机器上换用完整版 Git

装 Git for Windows（带 credential manager）后，在 Git Bash 里执行方式 A 的两条命令即可。

## 提交身份

当前提交作者是占位的 `Administrator <administrator@localhost>`，想换成自己的：

```bash
git config user.name  "你的名字"
git config user.email "你的邮箱"
git commit --amend --reset-author --no-edit
```

## 仓库里有什么

- 源码：`photocard_gui.py`、`pct/`（7 个模块）、`bsa.py`、`nifpatch.py`、`boxesp.py`、`render_blend.py` 等
- 运行所需的二进制：`materials/`、`res/`（Texconv.exe、02.png、1_go.nif、盒子贴图，共约 4.8 MB）
- 文档：`README.md`、`ARCHITECTURE.md`
- 已忽略：`work/`（3.3 GB 打包产物与测试）、`pylibs/`、`.dsh-pilot/`、`*.zip`、旧版本随包目录、临时 dds
