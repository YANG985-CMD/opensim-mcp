# OpenSim MCP for Windows 11

Windows 11 x64 上供 Codex 使用的独立 OpenSim MCP，注册名 **opensim_mcp**。
当前版本 **v1.4.1**，**94 个工具**。这是独立项目，不是 OpenSim/MathWorks/OpenAI 官方产品。

支持模型检查和编辑、IK/ID/肌肉分析、缩放、关节反力、RRA/Moco、异步任务与保存点、
GUI 自动桥接、离线三维动画，以及通用 MATLAB/CAD 数据交换。上肢与下肢共用接口。
本仓库仅提供发行包和用户说明，完整源码另存于维护者私有仓库。

## 安装

1. 从 [Releases](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) 下载
   `opensim-mcp-v1.4.1-win11-installer.zip` 和对应 `.sha256`。
2. 用 PowerShell 的 `Get-FileHash <ZIP路径> -Algorithm SHA256` 对照校验和。
3. 解压到最终目录，例如 `E:\opensim-mcp`，双击 **install.cmd**。
4. 等待安装、自检和 Codex 配置完成，然后重启 Codex。

首次安装需联网；无需预装 Python。安装器下载并校验依赖，在项目内创建两套独立环境。
默认关闭任意脚本执行，合并本服务配置并保存原配置备份。安装路径可含空格或中文。
OpenSim GUI 可选，需要用户另行安装；本包不捆绑或升级 GUI。

指定已有 GUI 与 E 盘临时目录：

```powershell
Set-Location 'E:\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -OpenSimRoot 'E:\OpenSim 4.6'
```

省略 `-OpenSimRoot` 则使用独立 API。加 `-SkipCodexRegistration` 仅生成配置供手动合并。
双击 **doctor.cmd** 自检；关闭 Codex 后运行 `doctor.cmd -Repair` 可修复锁定依赖。
同一目录先完成一次联网安装和缓存后，修复可加 `-Offline`。不要移动已安装的虚拟环境。

手动启动命令（标准输入输出 MCP，需要客户端连接）：

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime'
.\.venv\Scripts\python.exe -B -m opensim_mcp.server
```

## v1.4.1 质量参数换算

新增质量、质心和惯量的单位、参考点及坐标架换算，供 CAD 装置刚体参数导入。
支持平行轴变换、惯性积符号约定、旋转矩阵与惯量物理约束检查。
用法见 [质量参数说明](docs/MASS_PROPERTIES.zh-CN.md)。

## v1.4 通用可视化工作台

新增单/双场景工作台：同步时间轴与视角、点击组件联动高亮、距离/三点夹角、
坐标/外部信号/肌肉力与激活曲线对比，以及查看状态保存/恢复。
常用操作保持简洁，测量与显示设置按需展开。详见 [工作台说明](docs/WORKBENCH.zh-CN.md)。

## v1.3 通用可视化

三维姿态和外部曲线共用时间轴，点击曲线定位姿态，支持组件绑定、原始采样 CSV 和选择
上下文导出。MATLAB 导出帮助函数位于 `integrations/matlab`，要求 R2023b+。
SolidWorks 通过 STL/OBJ 网格接入，必须明确单位、父坐标架和变换；动力学另需明确质量、
质心、惯量与关节。当前为文件交换，修改数据/CAD 后重新导出，尚无后台实时共仿真。
详见 [跨软件联动说明](docs/VISUALIZATION_INTEROP.zh-CN.md)。

`examples/visualization-interop-demo.html` 是原创下肢模型、CAD 测试块和合成信号演示，
可直接离线打开。它不是实际装置贴合、实验测量或生理有效性验证。

## 版本与发行形式

该安装包的核心 Python 模块为 CPython 3.12 编译字节码，主运行组合为 Python 3.12.13 +
OpenSim 4.6 API；不支持替换为 Python 3.8 的旧 API。GUI 使用独立 Jython 桥接。
必要的安装脚本、GUI 桥接、网页和 MATLAB 帮助函数可读。字节码可被逆向，不能视为加密。
依赖版本见随包 lock 文件。包内不含用户模型、账号配置、参与者数据、MATLAB/SolidWorks
软件或 OpenSim GUI。第三方组件独立安装，遵循各自许可；见 THIRD_PARTY_NOTICES.md。

源码与发行包的执行验证数量见随 Release 提供的验证记录。发行包另行验证真实 MCP/IK、原生 Moco 自检、
可视化接口和文件完整性；具体执行记录随 Release 提供。干净 Windows 虚拟机与 GUI
生命周期测试不等同于本机安装验证。

## 更新

将新包解压到新的最终目录并完成自检后，再切换 Codex 配置。保留旧目录以便回退。
`scripts/upgrade.ps1` 支持明确 SHA256 的并排校验、安装和可选激活；不自动下载陌生来源。
不要把旧目录中的 `.venv`、`.api46-venv`、`runtimes` 或私有 `state` 上传到 GitHub。
