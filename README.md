# OpenSim & SolidWorks MCP

**在 Windows 11 上，把 CAD 设计、人体分析和 MATLAB 数据处理连起来。**

[配置主页](https://yang985-cmd.github.io/opensim-mcp/) ·
[下载安装包](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) ·
[三个 MCP 配置指南](docs/SETUP_WINDOWS11.zh-CN.md) ·
[联动功能](docs/INTEROP.zh-CN.md)

本仓库公开两套 MCP 的完整源码和安装包，按 MIT 许可发布。
MATLAB 使用 MathWorks 官方 MCP，通过下方官方入口安装。

## 先选你要做的事

| MCP | 能帮你做什么 | 版本与获取 |
| --- | --- | --- |
| **SolidWorks MCP** | 建模、改尺寸、装配配合、检查干涉与间隙、读取质量参数、导出、版本对比和 HTML 报告 | v0.5.3，53 工具 · [源码](solidworks-mcp/) · [安装包](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) |
| **OpenSim MCP** | 人体模型检查与编辑、IK/ID、肌肉与关节反力、Moco、装置穿戴、三维动画及曲线工作台 | v1.4.1，94 工具 · [源码](opensim-mcp/) · [安装包](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) |
| **官方 MATLAB MCP** | 执行 MATLAB、检查代码、处理数据和复核结果；配合官方工具包接入 Simulink 与 Skills | [官方 MCP](https://github.com/matlab/matlab-mcp-server) · [官方安装器](https://github.com/matlab/agentic-toolkit-installer) |

两套本地适配器是独立项目。MATLAB、SOLIDWORKS 及 OpenSim 本体按各自许可安装。

## 三步开始

1. 准备 Windows 11 x64、SOLIDWORKS 2025、64 位 Python 3.12 和可用的 MATLAB。OpenSim API 由安装器准备，GUI 可选。
2. 在同一个 [Releases 页面](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) 获取两个安装包及 `.sha256`，核对后安装。MATLAB MCP 用 [官方安装器](https://github.com/matlab/agentic-toolkit-installer) 配置。
3. 按 [详细指南](docs/SETUP_WINDOWS11.zh-CN.md) 合并三个服务到 Codex，或在 [配置主页](https://yang985-cmd.github.io/opensim-mcp/#configure) 填写本机路径并下载配置片段。

| 安装包 | 使用方式 |
| --- | --- |
| `opensim-mcp-v1.4.1-win11-installer.zip` | 解压后进入内层 `opensim-mcp`，运行 `install.cmd`，或按指南指定 E 盘运行目录 |
| `solidworks-mcp-v0.5.3-win11-installer.zip` | 解压到最终目录，运行 `install.ps1`，根据生成的 `mcp-codex.toml` 注册 |

网站生成的是配置文件片段，安装与自检在使用者自己的 Windows 电脑上完成。
安装后的服务注册名依次为 `opensim_mcp`、`solidworks-mcp` 和 `matlab`。

## 怎样联动

```mermaid
flowchart LR
    A[同一个 AI 客户端] <--> S[SolidWorks MCP]
    A <--> O[OpenSim MCP]
    A <--> M[官方 MATLAB MCP]
    S -->|网格和质量参数| O
    M -->|动作和载荷| O
    O -->|运动与受力结果| M
    O --> H[HTML 三维结果]
    M -->|带单位曲线| H
```

- **CAD 穿到人体上**。从 SolidWorks 导出装置网格与质量、质心、惯量，明确单位、坐标和关节映射后挂载到 OpenSim。上肢、下肢共用接口。
- **比较两版方案**。保持人体、动作与外载荷一致，比较更换结构后的受力与力矩，再由 MATLAB 复核差值和机械功。
- **曲线与三维动作一起看**。HTML 使用共同时间轴，点选曲线查看对应姿态和组件，也可保存查看状态、导出结果。

联动采用明确的离线文件交换。完整流程、输入约定和算例范围见 [联动说明](docs/INTEROP.zh-CN.md)。

## MATLAB 与 Simulink 官方入口

- [MATLAB MCP Server](https://github.com/matlab/matlab-mcp-server)
- [Agentic Toolkit Installer](https://github.com/matlab/agentic-toolkit-installer)
- [MATLAB Agentic Toolkit](https://github.com/matlab/matlab-agentic-toolkit)
- [Simulink Agentic Toolkit](https://github.com/matlab/simulink-agentic-toolkit)

官方 MCP 的旧地址 `matlab/matlab-mcp-core-server` 已跳转到上面的新地址。
这里提供官方链接和配置说明，具体官方版本、许可证与要求以其发布页面为准。

## 源码与验证

```text
opensim-mcp/       OpenSim 服务、安装器、示例、测试与 GUI 桥接
solidworks-mcp/    SolidWorks 服务、安装集成、测试与许可声明
config/           三个 MCP 的 Codex 配置示例
docs/             配置网页、安装指南、联动说明及发布核验
```

2026-11-13 已在本机 Windows 11 验证 OpenSim 262 项、SolidWorks 91 项现有回归，
以及安装包的真实 MCP 连接。详情见 [OpenSim 发布记录](docs/RELEASE-v1.4.1.json)
和 [SolidWorks 发布记录](docs/RELEASE-v0.5.3.json)。各记录明确执行平台和验证范围。

原生模块的源码迁移记录见 [SOURCE_IMPORT.json](docs/SOURCE_IMPORT.json)。
项目代码的 [MIT 许可](LICENSE) 和各子项目第三方许可声明一并保留。
人体有效性、具体装置贴合及硬件结果需结合实际模型和实验验证。
