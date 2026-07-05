# OpenTDX Stock Panel v0.1.68 发布记录

发布日期: 2026-07-05

## 发布目标

- 正式发布 Windows 桌面版，普通用户解压后双击 `OpenTDXStockPanel.exe` 即可使用。
- 统一版本到 `v0.1.68` / `0.1.68`。
- 保持远程仓库地址不变: `https://github.com/LisonEvf/tickflow-stock-panel.git`。

## 发布产物

- Portable zip: `packaging/Output/OpenTDXStockPanel-v0.1.68-win-x64-portable.zip`
- Zip size: 188.24 MB
- SHA256: `0FD610FC3C9703086EF36B2EFDC8337640A5A6D677BB9C833AE2CA4FB9FF704F`
- 展开后: 2181 files, 574.78 MB

说明:

- `packaging/Output/` 是本地构建产物目录，按 `.gitignore` 不入库。
- 当前机器未发现 Inno Setup `ISCC.exe`，因此本次产出为 portable zip；安装向导脚本 `packaging/opentdx.iss` 仍保留，可在安装 Inno Setup 后生成 setup exe。

## 变更摘要

- 桌面启动加固:
  - 写入 `data/logs/desktop.log`，便于普通用户启动失败时定位问题。
  - 后端线程崩溃记录完整异常。
  - Windows 启动失败时弹出错误框并提示日志位置。
  - 桌面后端启动等待时间从 60 秒提高到 180 秒。
  - `uvicorn` 保留桌面文件日志配置。
- 数据目录加固:
  - frozen 桌面版中相对 `DATA_DIR` 解析到 exe 所在目录，避免落到 PyInstaller 资源临时目录。
- 打包依赖:
  - 添加 `pysocks>=1.7`，覆盖 OpenKPH/OpenTDX SOCKS proxy 动态导入路径。
- 前端验证:
  - `pnpm lint` 改为 `tsc -b --pretty false`，避免调用未安装的 eslint。

## 验证证据

- `uv run --extra dev python -m pytest`
  - 结果: `47 passed in 5.90s`
- `uv run --extra dev python -m ruff check app/config.py app/desktop.py tests/test_config_desktop.py`
  - 结果: `All checks passed!`
- `uv run --extra dev python -m compileall -q app`
  - 结果: 通过，无输出。
- `pnpm lint`
  - 结果: 通过。
- `pnpm build`
  - 结果: 通过；保留现有 Vite chunk 体积和动态/静态混合导入警告。
- `python -m PyInstaller ../packaging/opentdx.spec --noconfirm --clean`
  - 结果: 通过，产物位于 `backend/dist/OpenTDXStockPanel`。
- 直接运行打包 exe smoke:
  - `/health`: `status=ok`, `version=0.1.68`, `mode=opentdx`
- 最终 zip 解压 smoke:
  - `/health`: `status=ok`, `version=0.1.68`, `mode=opentdx`
  - 日志路径: 解压目录下 `data/logs/desktop.log`

## 已知风险

- 该产物未进行代码签名，Windows 首次运行可能出现 SmartScreen 提示。
- 本机未安装 Inno Setup，本次未生成安装向导版 setup exe。
- Vite 构建存在既有 chunk size 警告，当前不阻塞桌面发布。
- PyInstaller 输出包含若干可选跨平台模块警告，例如 Android/iOS/Linux 平台模块、`hypothesis` 测试辅助模块缺失；最终 Windows exe smoke 已通过。

## 回滚方式

- 代码回滚: 回退本次提交后重新执行构建。
- 发布产物回滚: 删除 `packaging/Output/OpenTDXStockPanel-v0.1.68-win-x64-portable.zip`，重新分发上一版 zip。
- 用户数据回滚: 本版本使用应用目录下 `data/`；覆盖升级不要删除该目录。

