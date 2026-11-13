# SolidWorks MCP v0.5.3 Windows 11 分享版

目标为 SOLIDWORKS 2025 和 64 位 CPython 3.12。通过本机官方 COM API 提供 53 个 MCP 工具。分享包自带离线 Python 依赖、MCP 字节码、安装脚本和诊断工具。

## 安装到新电脑

将 ZIP 解压到新电脑上长期保留的可写目录。用 PowerShell 在该目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器会定位本机 SOLIDWORKS 2025、核对类型库版本、安装依赖，并进行 MCP 握手和工具自检。自定义安装路径可加 `-TypeLibrary 'D:\实际安装目录\SOLIDWORKS\sldworks.tlb'`。可用 `-Python` 指定 Python 3.12 的完整路径，或用 `-OutputRoot` 和 `-RuntimeRoot` 指定文件和运行目录。

自检显示 `MCP_READY` 后，用本机新生成的 `mcp-codex.toml` 替换 Codex 配置中的 `solidworks-mcp` 一节。升级旧版时，该服务旧的 `[mcp_servers.solidworks-mcp.env]` 一节也要一并清除，或把仍要保留的路径改为本机实际值。其他服务配置保持原样。DeepSeek Harness 可使用本机生成的 `mcp-harness.json`。换电脑或移动安装目录后，在新位置重新安装并生成客户端配置。

在 Codex 的 MCP 设置中重新连接。在对话框输入 `/mcp` 看服务是否连接，再让它调用 `sw_health`，应返回 `0.5.3`。打开 SOLIDWORKS 2025，调用 `sw_connect` 连接。

## Codex 转到 Computer Use 时

在解压目录用同一个 Python 检查实际导入的 Codex 配置：

```powershell
.\.venv\Scripts\python.exe -B .\diagnose.py --config (Join-Path $env:USERPROFILE '.codex\config.toml') --connect
```

指定其他项目配置时，将 `--config` 改成该文件的路径。去掉 `--connect` 可单独检查 MCP 启动、工具清单和类型库。连接诊断尝试连接已经运行的 SOLIDWORKS，默认不会启动软件。

| 输出 | 含义 |
| --- | --- |
| `MCP_CHECK_FAILED` | 核对错误行。常见原因有没导入条目、旧路径、服务禁用或工具被过滤。 |
| `MCP_READY` | 握手、工具清单和健康查询已通过，CAD 连接仍需另查。 |
| `TYPELIB_MISSING` | 安装设置中的 `sldworks.tlb` 无效，重新运行安装器。 |
| `ATTACH_FAILED` | 查看连接错误和 `recovery`，核对 SOLIDWORKS 是否已启动、版本是否为 2025、Codex 与 SOLIDWORKS 是否使用相同账户和权限级别。 |
| `ATTACHED` | 通过 COM 连接到已运行的 SOLIDWORKS，可继续用 `sw_documents` 检查文档。 |

如果当前任务只允许 MCP，可以在项目说明里写：**SolidWorks 任务只调用 `solidworks-mcp`。先检查 `sw_health`，再连接或查找工具。遇到失败或无对应工具时，报告错误码并停下。**

工具选择由 Codex 决定。MCP 的初始化说明和错误回复提供恢复路径。若希望 Codex 在 MCP 未就绪时直接报错，可在支持该设置的 CAD 专用项目配置中为此服务设置 `required = true`，代价是服务启动失败时该项目的 Codex 会话也会启动失败。配置说明见 [Codex MCP 文档](https://learn.chatgpt.com/docs/extend/mcp)。
