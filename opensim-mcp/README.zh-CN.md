# OpenSim MCP v1.4.1 — Windows 11

**94 个 MCP 工具**，在 Codex 中检查、修改和运行 OpenSim 模型。支持 GUI 自动连接、
可撤销编辑、异步分析、人体分析流水线、故障恢复及离线三维运动播放器。
注册名固定为 **opensim_mcp**，是独立适配器，不需要修改 OpenSim Core。

1.4.1 增加一个 CAD 质量参数转换工具：明确单位、惯量参考点、非对角项符号和坐标变换；已有穿戴装配增加惯量物理性预检与原生保存重开回读。详见[质量参数交接](docs/MASS_PROPERTIES.zh-CN.md)。适用于通用装置，不改变 HTML 工作台。v1.4.1 编译安装包见[公开下载页](https://github.com/YANG985-CMD/opensim-mcp/releases/tag/v1.4.1)。

[全部工具](docs/TOOLS.md) · [实测记录](VERIFIED.md) · [v1.1 使用说明](docs/V11_WORKFLOWS.zh-CN.md) ·
[三维演示](examples/viewer-demo.html) · [升级与回退](docs/UPGRADE.zh-CN.md) · [English](README.md)

## v1.4 简洁可视化工作台

新增双场景同步查看、组件点选与联动高亮、曲线差值、标记/坐标架原点测量及查看状态保存恢复。
播放与时间轴常驻，组件、测量和显示设置按需展开。详见[工作台说明](docs/WORKBENCH.zh-CN.md)。

## 通用可视化与 MATLAB / SolidWorks 联动

新增外部数据页：三维姿态与曲线共用时间轴、点击曲线定位姿态、显式组件绑定、CSV 与选择上下文导出，
以及带输入副本和哈希的离线工作区。适用于上肢、下肢及其他模型。包含 MATLAB 数据导出帮助函数，
SolidWorks 网格沿用明确单位与变换的装配接口。详见[三方联动说明](docs/VISUALIZATION_INTEROP.zh-CN.md)。
当前是文件交换；CAD 与数据变更后重新导出，不会后台实时回写。

## 下肢外骨骼研究

新增肌肉力与激活估计、装置质量负担对比、带来源的肌肉体积数据，以及网页受力着色、点选、对照曲线和 CSV 导出。数值检查与生理验证分别报告。详见 [外骨骼受力工作流](docs/EXOSKELETON_STUDIES.zh-CN.md)。

## 安装和运行

1. 下载源码 ZIP 和对应 SHA256，用 `Get-FileHash` 核对文件。
2. 解压到最终安装目录，例如 `E:\opensim-mcp`，双击 **install.cmd**。
3. 安装完成后重开 Codex，使用 **opensim_mcp**。仅计算时不需要 GUI。

支持 Windows 11 x64。首次安装需要联网；无需预装 Python。安装器下载固定解释器，
按哈希锁安装两套环境，默认关闭任意脚本，仅合并本服务的 Codex 配置并保存备份，
然后执行真实 MCP/IK 自检。不要直接移动已安装的虚拟环境，换位置应重新安装。

可选 GUI 安装路径和明确的临时目录：

```powershell
Set-Location 'E:\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -OpenSimRoot 'E:\OpenSim 4.6'
```

省略 `-OpenSimRoot` 即只安装计算 API；加 `-SkipCodexRegistration` 可只生成
`config/opensim_mcp.generated.toml`，供手工合并。[完整配置示例](config/codex.example.toml)
包含命令、环境变量和允许访问的数据目录。源码包不包含 OpenSim GUI，也不会自动升级它。

双击 **doctor.cmd** 检查依赖、版本、原生能力及源码完整性；缺依赖时关闭 Codex 后运行
**doctor.cmd -Repair**。修复会重装锁定依赖/API，保留用户模型、源码修改及 Codex 配置。
原生导入若缺 Visual C++ x64 运行库会明确报错。详见[工程化说明](docs/ENGINEERING.zh-CN.md)。

不经过 Codex 的真实安装自检：

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime'
.\.venv\Scripts\python.exe -B .\scripts\smoke_mcp.py --examples "$PWD\examples" --run-ik
```

## 可以做什么

| 范围 | 已实现 |
| --- | --- |
| 模型与 API | 安全 XML 摘要、常驻原生会话、组件/API 查询、代码检查及错误定位、结构化原生状态读取 |
| 编辑与恢复 | 参数事务及受限拓扑编辑预览、版本检查、整体撤销/重做、保存点、持久回滚日志；故障后显式恢复模型及全部命名原生状态/时间 |
| GUI | 启动插件自动桥接、当前选择、截图、加载模型/运动、姿态撤销、显式双向同步；配置目录变更可在 v1 桥接中原位迁移 |
| 计算 | IK、ID、MuscleAnalysis、SO、缩放、MarkerPlacer、JointReaction、RRA、Moco/Track/Inverse、网格比较与有限参数敏感性 |
| 数据与流程 | C3D 标记和测力台导入、单位/坐标轴/外力映射检查、完整肌肉分析项目模板、进度/取消/历史、缓存续跑、质量报告、项目包 |
| 可视化 | 返回客户端的图像/曲线，原生姿态图；离线 WebGL 三维网格动画、时间轴、旋转缩放、关节曲线、对比运动与标记误差着色 |
| 安装与发布 | 一键安装、自检和有限修复、并排升级/回退、锁定依赖、GitHub 测试及标签发布工作流、可选 Win11 自托管 GUI 工作流 |

给 Codex 的请求示例：

> 用 opensim_mcp 检查 examples/slider.osim，以 slider.trc 做 IK，绘制 slider_tx，
> 核对它与 0.1×时间的解析位移。

> 读取当前模型及 revision，先预览新增一个与现有模型连接的 SliderJoint 和体，
> 通过后提交，导出三维运动播放器，再整步撤销。

> 查看恢复记录，选定刚才会话的保存点，恢复模型、速度、肌肉激活和时间。

所有文件参数使用绝对路径，并位于配置的允许输入目录或结果目录中。合成样例随包提供；
真实人体样例从用户已安装的官方 Gait2354 资源读取，不随包分发。
[C3D/RRA/肌肉项目/Moco 研究](docs/V09_WORKFLOWS.zh-CN.md) ·
[流水线](docs/PROJECTS.zh-CN.md) · [Marker/辅助驱动](docs/PROFILES.zh-CN.md) ·
[Moco 参考轨迹](docs/MOCO_REFERENCE.zh-CN.md)。

## GUI 与使用边界

安装启动插件后重开一次 GUI，以后每次启动自动桥接。GUI 官方资源仍需正常安装一次；
使用持久用户配置启动可以避免反复出现首次资源安装窗口。见[插件说明](gui-autobridge/README.md)。
API 与 GUI 是两个模型会话，通过 `sync_gui_model` 的 pull/push 显式同步。
自动连接不会自动合并模型；已有 GUI 或未保存的工作不会被生命周期工具自动关闭。

拓扑工具支持体、Pin/Slider/Weld 关节、标记、坐标驱动等明确范围，并非全部 OpenSim
组件编辑器。恢复保存原生模型和全部命名状态/时间，不恢复 Python 变量、GUI 工作区，
也不撤销脚本已写出的文件或其他外部副作用。

原生模型、C3D 和网格解析都需要可信输入。任意 Python 默认关闭；设置
`OPENSIM_MCP_ENABLE_SCRIPTS='1'` 后，脚本拥有当前 Windows 用户权限。
外力需明确 N/m/Nm、轴向、正负号和足部映射；坐标需声明 inDegrees，API 内使用 rad/m。
MuscleAnalysis 是长度/力臂等分析，肌肉力/激活优化由 SO/Moco 等流程提供。
阈值由研究者设置；数值成功、目标函数相近或播放器显示正常都不等于生理有效。
详见 [SECURITY.md](SECURITY.md)。

## 兼容性与证据

主验证：Windows 11 x64、CPython **3.12.13**，独立官方 opensim **4.6 wheel build 2**，
实际核心 `4.6-2026-06-22-85aaf64`、NumPy **2.5.4**。
主服务严格使用 Python 3.12，锁定 mcp 1.29.1、pydantic 2.14.1、defusedxml 0.7.1、
matplotlib 3.11.2、ezc3d 1.7.2、vtk 9.7.1。MCP SDK v2 需要单独迁移。
GUI 保留本机官方 4.6_beta 包，内置实际核心为 **4.5.2**，并非已验证的正式 4.6 GUI；
旧 4.3/Python 3.8 仅保留核心与跨版本回归。不同环境不得混用 DLL。

175 项适配器测试、实际原生计算、GUI 重启/桥接迁移、Edge 播放器交互、安装及回退
的实测范围见 [VERIFIED.md](VERIFIED.md)。人体 Moco 已计算一个实测触地事件间的完整周期，逐列检查状态/控制及原生力输出；
当前网格差异标记 needs_review，未声称完整收敛或生理验证。未执行干净 Win11 虚拟机测试；GitHub 工作流已在本地检查，
远程 Actions/Release 需上传到实际仓库后执行。

MIT 许可证覆盖适配器及自有合成样例；依赖保留各自许可证。源码包不包含 GUI 本体、
私有配置、虚拟环境、计算结果或参与者试验数据。


## v1.1 新增与装置穿戴

新增七个工具：完整步态分段、显式坐标重采样、全列 Moco 网格质量判断、原生轨迹/执行器力检查，
以及下肢装置装配、装置运动准备、同条件质量/助力 ID 对照。GUI 增加跨进程锁、原子状态版本
检查与会话归属撤销，旧桥接写操作需保存工作后重开 GUI。

[下肢护具三维演示](examples/wearable-demo.html) · [CAD/动力学详细说明](docs/V11_WORKFLOWS.zh-CN.md) ·
[Win11 复现与离线缓存](docs/WIN11_REPRO.zh-CN.md)

装置可设置明确质量、质心、惯量及 Weld/Pin/Slider 关节，使用刚体标志点拟合或手工变换。
原生 SolidWorks 文件由可选 SolidWorks MCP 或 SolidWorks 软件导出 STL/OBJ/VTP 后接入；
本包不捆绑 CAD 转换器。跨关节装配需分件、明确人体对应、关节中心/轴及接口模型，
外形不能推断肌肉分配、绑带压力或真实接触力。

官方人体模型加两件原创护具的质量/ID 已验证；实际装置文件尚未提供。示意演示不是解剖模型。
安装器新增 Offline 缓存复用和实际 Moco/IPOPT 检查，原生检查成功后才注册 Codex。
已验证中文/空格路径、离线重装、缺依赖/求解器故障；干净 Win11 虚拟机入口已提供，未实际执行。
