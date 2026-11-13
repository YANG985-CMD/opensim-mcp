# 在 Windows 11 配置三个 MCP

统一入口为 [项目主页](https://yang985-cmd.github.io/opensim-mcp/)。
页面可填写本机路径，生成包含三个服务的 Codex 配置片段。

## 准备软件

| 服务 | 本项目支持与前提 | 获取位置 |
| --- | --- | --- |
| OpenSim MCP v1.4.1 | Windows 11 x64，安装器准备 Python 3.12 与 OpenSim 4.6 API。GUI 可选 | [本仓库安装包](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) |
| SolidWorks MCP v0.5.3 | Windows 11 x64，已安装 SOLIDWORKS 2025 与 64 位 CPython 3.12 | [本仓库安装包](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) |
| MATLAB MCP | 已安装并许可的 MATLAB，使用 MathWorks 官方服务及安装说明 | [官方 MCP](https://github.com/matlab/matlab-mcp-server) |

建议使用一个独立项目目录交接数据。下文路径是示例，可改为本机实际目录。

```powershell
New-Item -ItemType Directory -Force -Path 'E:\MCP\projects','E:\MCP\runtime\opensim','E:\MCP\runtime\solidworks','E:\MCP\runtime\matlab'
```

## 1. 安装 OpenSim MCP

从同一 [Release](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) 下载
`opensim-mcp-v1.4.1-win11-installer.zip` 与同名 `.sha256`。
用 `Get-FileHash` 核对 ZIP，解压后将内层 `opensim-mcp` 文件夹放到最终安装目录。
示例最终位置为 `E:\MCP\opensim-mcp`，其内应直接包含 `install.cmd`。

```powershell
Set-Location 'E:\MCP\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -TempRoot 'E:\MCP\runtime\opensim' -SkipCodexRegistration
```

首次安装需要联网。安装后用以下命令生成包含项目数据目录的本机配置。

```powershell
.\scripts\print-codex-config.ps1 -TempRoot 'E:\MCP\runtime\opensim' -InputRoots @('E:\MCP\opensim-mcp\examples','E:\MCP\projects') -ResultsRoot 'E:\MCP\projects\results' -ApiPython 'E:\MCP\opensim-mcp\.api46-venv\Scripts\python.exe'
```

有 GUI 并需要桥接时，按 [OpenSim 安装说明](../opensim-mcp/README.zh-CN.md)
为安装器指定真实 `-OpenSimRoot`。API 计算与 GUI 会话分别管理。

## 2. 安装 SolidWorks MCP

下载 `solidworks-mcp-v0.5.3-win11-installer.zip` 与同名 `.sha256`，核对后解压到
`E:\MCP\solidworks-mcp`。该目录应直接包含 `install.ps1`，无需再套一层目录。

```powershell
Set-Location 'E:\MCP\solidworks-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -RuntimeRoot 'E:\MCP\runtime\solidworks' -OutputRoot 'E:\MCP\projects\cad'
```

安装器从本机查找 SOLIDWORKS 2025 类型库。查找失败时，加
`-TypeLibrary '你的安装目录\sldworks.tlb'`。Python 不在 PATH 时，用 `-Python`
指定 64 位 Python 3.12 可执行文件。

看到 `MCP_READY` 后，使用生成的 `mcp-codex.toml`。
`bridge-settings.json` 保存这次安装的类型库与运行目录，和安装目录一起保留。

## 3. 配置 MathWorks 官方 MATLAB MCP

推荐使用 [Agentic Toolkit Installer](https://github.com/matlab/agentic-toolkit-installer)，
从官方页面下载 `agenticToolkitInstaller.mltbx`，在 MATLAB 安装后运行
`setupAgenticToolkit("install")`，选择 Codex 和所需 MATLAB/Simulink 工具包。
官方安装器负责注册工具与 Skills。安装要求及升级方式以官方文档为准。

也可按 [官方手动配置](https://github.com/matlab/matlab-mcp-server#manual-setup)
下载 Windows x64 服务程序。配置示例假定其位置为
`E:/MCP/matlab/matlab-mcp-server-windows-x64.exe`。
Windows 的 Codex 条目需保留 `env_vars = ['WINDIR']`。需要指定 MATLAB 安装目录时，
按官方参数文档加入 `--matlab-root=你的MATLAB目录`。

需要 Simulink 结构化工具与 Skills 时，使用
[Simulink Agentic Toolkit](https://github.com/matlab/simulink-agentic-toolkit)。
其官方安装器可自动配置扩展。已有安装用户按官方迁移说明处理旧条目。

## 4. 在同一个 Codex 客户端中合并配置

打开 `%USERPROFILE%\.codex\config.toml`，将两套安装器生成的条目合并进去，
保留官方安装器生成的 `matlab` 条目。每个服务只保留一个同名配置块。
其他 MCP 配置照常保留。

可以参考 [三个服务的 TOML 示例](../config/codex-three-mcp.example.toml)，
或用 [配置页面](https://yang985-cmd.github.io/opensim-mcp/#configure) 根据本机路径生成片段。
页面生成的是安装包配置。源码开发环境请使用各子项目自己的配置说明。

## 5. 重新连接并自检

重启或重新连接 Codex 的 MCP，确认以下三项。

| 检查 | 期望结果 |
| --- | --- |
| OpenSim `get_environment` | 适配器 v1.4.1，94 工具，API 可用 |
| SolidWorks `sw_health` | v0.5.3，类型库有效；随后 `sw_connect` 连接已运行的 SOLIDWORKS |
| MATLAB `detect_matlab_toolboxes` | 返回这台电脑实际安装的 MATLAB 和工具箱 |

可直接发送给 AI 客户端。

> 请分别检查 OpenSim、SolidWorks 和 MATLAB MCP 的连接与版本。先进行环境检查，列出可用工具，然后说明项目输入目录和结果目录。

## 源码开发

OpenSim 源码在 `opensim-mcp/`。进入该目录运行其安装器，可加 `-WithTests` 安装开发测试依赖。
SolidWorks 源码在 `solidworks-mcp/`，可用 Python 3.12 创建环境后执行 `pip install -e .`，
再按该子项目 `integration/codex-server.toml` 明确配置本机路径、输出位置与类型库。
两套项目的测试、许可与验证记录均保留在各自目录。
