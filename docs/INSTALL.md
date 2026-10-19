# 安装（已停用）

**桌面版已于 2026-10-19 停用**（决定 `docs/decisions/2026-10-19-desktop-retired.md`）。LACUNA Studio 现在只在云端运行：
**https://lacunastudio.app**，用浏览器打开、登录即可，不用安装任何东西。新版本测试通过后自动上线，没有“发版”也没有「设置 → 更新」。

- 不再有安装器（`install.sh` / `install.ps1` / `LACUNA-Setup.cmd`）、启动器和 GitHub Release；旧的说明在 git 历史里（本文件 2026-10-19 之前的版本）。
- 部署方式：PR → staging（https://preview.lacunastudio.app）→ 合并到 main 即上线，见 `deploy/README.md` 和 `docs/decisions/2026-10-19-staging-site.md`。
- 开发时从源码运行：见 `README.md`「Run from a source checkout」。
