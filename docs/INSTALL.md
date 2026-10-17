# 安装、启动与更新（第 7 阶段，D48）

不用命令行装 Python / Node / ffmpeg，也不用 git。安装器会把 uv、Python 3.12、App 需要的组件和 ffmpeg 全部装进一个文件夹，不需要管理员权限；工作区（剧集、模型、导出）放在别处，安装、更新、卸载都不会碰它。

| | Windows | macOS |
|---|---|---|
| 装在哪 | `%LOCALAPPDATA%\LACUNA` | `~/Library/Application Support/LACUNA` |
| 工作区（默认） | `C:\Projects\LACUNA_Workspace`（有就用它），否则 `%USERPROFILE%\LACUNA_Workspace` | `~/LACUNA_Workspace` |
| 怎么打开 | 桌面和开始菜单里的 **LACUNA** | 「应用程序」（个人）里的 **LACUNA.app**，可以拖到程序坞 |
| API key 存在哪 | 用户环境变量（注册表，和 `setx` 一样） | 钥匙串（Keychain） |

打开后会出现一个黑色窗口（Windows 的命令行窗口 / Mac 的「终端」），浏览器自动打开 http://127.0.0.1:8765/ 。**关掉这个窗口就退出 LACUNA。** 已经开着时再点一次图标，只会打开浏览器页面。

## Pei：在 Mac 上第一次安装（Leon 转给 Pei）

1. 打开「终端」（启动台里搜 “终端” 或 “Terminal”）。
2. 把下面这一整行复制进去，按回车：
   ```
   curl -fsSL https://github.com/leon-qr-li/lacuna/releases/latest/download/install.sh | bash
   ```
3. 等它跑完（第一次要下载约 500 MB：Python、组件、ffmpeg，几分钟）。最后会显示「LACUNA … 装好了」，浏览器自动打开 LACUNA。这个终端窗口就是 LACUNA 本身，用的时候别关。
4. 以后打开：Finder → 前往 → 个人 → 应用程序 → **LACUNA**（建议拖到程序坞）。第一次打开如果问「要打开终端吗 / 允许控制终端吗」，点允许。
5. 要用 AI（第一刀、聊天修改、发布资料）：在 LACUNA 首页右上角点「设置」，在「Claude API key」里粘贴 Leon 给的 key，点保存，App 会自己重启。key 只存在这台 Mac 的钥匙串里。
6. 检查一下：「设置」页「这台电脑」一栏里 ffmpeg 显示「已就绪」。导入第一集时会自动下载语音识别模型（约 400 MB）。

不需要装 Xcode、Homebrew、Python 或 git。遇到问题把终端窗口里最后几行截图发给 Leon。

## Leon：Windows

- 新电脑第一次装：下载 Release 里的 `LACUNA-Setup.cmd` 双击（若提示 “Windows 已保护你的电脑”，点「更多信息 → 仍要运行」），或者在 PowerShell 里粘贴：
  `irm https://github.com/leon-qr-li/lacuna/releases/latest/download/install.ps1 | iex`
- Leon 现在这台电脑由 Claude 统一更新时迁移一次（见下面「迁移」），之后都点桌面上的 LACUNA。`C:\Projects\LACUNA_Start.bat` 会改成打开新装的 LACUNA，原来的习惯也照样能用。

## 更新

1. 有新版本时，首页右上角显示「设置 · 有新版本」。
2. 点进「设置」→ 看「更新内容」→「下载新版本」→「更新并重启」。导入、导出或生成发布资料还在跑时不能点，做完再更新。
3. 大约一两分钟后页面自己刷新，「版本」显示新号码。
4. 新版本起不来时会自动回到原来的版本，「设置」页写明「已自动回到 …」，这时告诉 Claude。

新版本什么时候出现由「统一发版」决定：一批改动都 merge、CI 全绿后，Claude 运行 GitHub Actions 里的 **Release**（填中文的更新内容），Leon 和 Pei 的 App 就能看到这次更新。

## 修复 / 重新安装 / 卸载

- 修复：再运行一次安装命令（会保留工作区和设置）。
- 卸载：删掉安装文件夹（上表）和快捷方式 / LACUNA.app。工作区不受影响；Mac 上的 key 在「钥匙串访问」里搜 LACUNA 删除。

## 给 Claude：迁移 Leon 的电脑（只做一次，随统一更新）

前提：Release 已经发布过一次；没有别的线程在更新、导入或导出。

1. 停掉正在运行的旧 LACUNA（端口 8765 上的 `python -m lacuna_app`）。
2. 在 Leon 电脑上（Remote Control，PowerShell）：`$env:LACUNA_NO_START='1'; irm https://github.com/leon-qr-li/lacuna/releases/latest/download/install.ps1 | iex`。工作区自动用 `C:\Projects\LACUNA_Workspace`，key 已在注册表，ASR 模型已在 `<workspace>\models`。
3. 把 `C:\Projects\LACUNA_Start.bat` 改成一行：`@call "%LOCALAPPDATA%\LACUNA\LACUNA.cmd"`（先备份成 `LACUNA_Start.old.bat`）。
4. 用新的启动方式启动（`start "" "%LOCALAPPDATA%\LACUNA\LACUNA.cmd"`），确认 `/api/app` 返回的版本号和 Release 一致、`ffmpeg` 指向 `%LOCALAPPDATA%\LACUNA\ffmpeg`。
5. `C:\Projects\lacuna`（git 开发副本）保留不动，只用于调试。

## 技术说明

- 发版包 `lacuna.zip`（代码 + 构建好的界面 + `VERSION`）、`version.json`（版本、更新内容、sha256）和安装脚本由 `.github/workflows/release.yml` 用 `installer/build_release.py` 生成。
- `installer/lacuna_launcher.py`（只用标准库）负责安装、启动和更新：App 下载并校验新版本到 `versions/<版本>/` 后以退出码 75 退出，启动器装新版本组件、启动它，180 秒内 `/api/app` 没报出新版本号就重装旧版本并启动。保留当前和上一个版本。退出码 76 = 普通重启（保存 API key 后）。
- ffmpeg 6.1.1 静态版（`eugeneware/ffmpeg-static`，sha256 写死在启动器里）放在安装目录的 `ffmpeg/`，启动时加到 PATH 最前面。
- CI：改到 `installer/`、`tests/installer/` 或 `pyproject.toml` 时，Windows / macOS / Linux 各自真跑一遍 `tests/installer/smoke_install.py`：安装脚本 → 启动 → App 内更新 → 坏版本自动回滚（不预装 ffmpeg、uv、Python）。
