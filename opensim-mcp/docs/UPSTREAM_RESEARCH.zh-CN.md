# GitHub 项目调研与升级建议

核查日期：2026-10-28。核对了项目主页、仓库元数据和相关源码。
以下是可复用方向及工程判断，不表示已安装、合并或验证这些第三方项目。

## 最相关的参考

| 优先级 | 项目 / 许可证 | 对本 MCP 的价值 | 接入边界 |
| --- | --- | --- | --- |
| 高 | [waverlose/opensim-MCP](https://github.com/waverlose/opensim-MCP)，MIT | 真正面向肌骨仿真的同类 MCP；可参考 ScaleTool、JointReaction、结果绘图、Moco 配方与文档资源 | 2026-10-13 新建，核查时 1 star；需要代码评审和本机验证，不能据工具数量判断成熟度 |
| 高 | [opensim-org/opensim-core](https://github.com/opensim-org/opensim-core)，Apache-2.0 | 原生 API、Moco、模型组件与官方测试，适配版本的首要依据 | 使用公开 API；保留 API/GUI 各自运行版本，不跨版本换 DLL |
| 高 | [opensim-org/opensim-gui](https://github.com/opensim-org/opensim-gui)，Apache-2.0 | 原生启动插件、脚本控制台、选中对象和界面事件接口 | 本版启动插件已使用其现有 NetBeans/控制台 API；未来 GUI 改架构需重适配 |
| 中 | [opensim-org/opensim-viewer](https://github.com/opensim-org/opensim-viewer)，Apache-2.0 | 新的网页三维视图、动画和渲染交互参考 | 是前端工程；还需模型转换/状态/相机协议，不会自动变成可控 MCP |
| 中 | [opensim-org/opensim-viewer-backend](https://github.com/opensim-org/opensim-viewer-backend)，Apache-2.0 | 查看 OpenSim 模型与浏览器视图之间的数据转换路线 | 应与对应前端共同审查，不能直接替代本地 GUI 会话 |
| 中 | [ComputationalBiomechanicsLab/opensim-creator](https://github.com/ComputationalBiomechanicsLab/opensim-creator)，Apache-2.0 | 可视建模、组件编辑、撤销/重做的设计参考 | 独立 C++ 桌面应用；接入它意味着新增后端，开发量明显大于当前启动插件 |
| 按需 | [perfanalytics/pose2sim](https://github.com/perfanalytics/pose2sim)，BSD-3-Clause | 多相机无标记动作处理、标记增强、缩放及 IK 数据准备 | 应作为可选前处理环境；相机、姿态估计与科研验证是额外工作 |
| 按需 | [opencap-org/opencap-processing](https://github.com/opencap-org/opencap-processing)，Apache-2.0 | 人体运动数据处理与动力学流水线参考 | 不同模型、数据和学习权重须分别核查许可及输入假设 |
| 基础 | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)，MIT | 资源发现、进度、任务与客户端兼容 | 本版保留已验证的 v1.29.1；上游 v2 迁移需要单独做兼容测试 |
| 架构参考 | [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)，MIT | 桌面插件与外部 MCP 的分层、主线程调度、可视反馈思路 | Blender API 不能用于 OpenSim，不能直接安装成 OpenSim 插件 |

许可证名称来自当日 GitHub 仓库元数据；实际复用时仍需保留所用版本的完整许可证和通知。
本次没有把第三方源码或数据直接复制进本项目。

## 同类 OpenSim MCP 的代码核对

waverlose/opensim-MCP 与本项目属于同一类生物力学工具，不是虚拟世界 OpenSimulator。
已阅读其 README、MCP 服务定义和 runner/worker 源码，未运行其代码。
其 [runner](https://github.com/waverlose/opensim-MCP/blob/main/src/opensim_runner.py)
确实构造 ScaleTool、JointReaction 和 ForwardTool 工作流；
其 [服务](https://github.com/waverlose/opensim-MCP/blob/main/src/opensim_mcp_server.py)
把 Moco 作为常驻脚本会话的配方和文档资源提供，不能将其表述为所有 Moco 问题已被通用封装。
其公开工具列表没有本项目已实现的 GUI 启动桥接和模型姿态双向同步。

最适合下一阶段吸收的是：原生组件/API 查询、文档资源、缩放和关节反力的接口设计。
接入前仍须保留本项目已有的路径/XML限制、输入单位与外力显式约束、
独立进程超时控制、原始文件保护和解析基准验证，不能直接替换整个服务。

搜索结果里的 sanchorelaxo/opensim-mcp 和 opensim-stack/opensim-console2mcp
面向 OpenSimulator 虚拟世界，不能用于肌骨仿真；sonhoai27/opensim 面向移动设备模拟器。
名称相同并不代表兼容。

## 与 MATLAB MCP 的实际差距

[MathWorks 官方 MATLAB MCP](https://github.com/matlab/matlab-mcp-server)
提供 MATLAB 启停、代码运行和代码质量检查，并与其工具包/技能生态配合。
可参考产品交互；其具体许可须按仓库 LICENSE.md 核查，本次没有复用其代码。

当前本项目已具备常驻变量、任意可信脚本、模型修改、原生求解、
GUI 自动连接和显式双向模型/姿态同步。不能用“完成百分之多少”衡量两者：
MATLAB 和 OpenSim 的运行时及生态不同，工具数量也不代表能力相同。

优先补齐的具体项目是：

1. 异步任务进度、可靠取消、历史记录和保存点。
2. API/组件查询、代码检查和错误定位，减少依赖即兴脚本。
3. 可返回给客户端的图像、曲线、GUI 当前选择和可撤销编辑。
4. 缩放、关节反力、Moco 的结构化输入与量化质量检查。
5. 真实人体模型、测力台数据、跨版本保存和 GUI 生命周期的回归样例。

v0.3 已落地：启动插件、4.6 独立 API、API 批处理后端、重启自动连接验证。
后续 v0.4 已实现上述五方面的明确功能范围：异步原生任务/进程树取消、历史/模型保存点、
查询/诊断、图像/选择/结构化撤销、缩放/JR/固定时段 Moco，以及官方人体数据和跨版本回归。
实际范围、数值与剩余扩展以当前 VERIFIED.md、docs/V04_WORKFLOWS.zh-CN.md 和 ROADMAP.md 为准。

## 版本来源

- [官方 Python 安装文档](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53085346/Scripting+in+Python)列出 4.6 的 PyPI/Conda 接口。
- [官方 PyPI](https://pypi.org/project/opensim/4.6/)提供 CPython 3.11/3.12/3.13 wheel；本版锁定并实测 3.12 x64 build 2。
- [GitHub GUI 发布页](https://github.com/opensim-org/opensim-gui/releases/tag/4.6_beta)仍写明内部测试；
  安装后 CLI 版本实测为 4.5.2，已如实记录，未按文件名当作最终 4.6 核心。
- [官方 4.6 功能说明](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/1274118147/Whats+New+in+OpenSim+4.6)
  另指向 SimTK 下载。网页检索器返回 403，但本机正常访问成功，列表中有正式
  [OpenSim-4.6-win64.exe](https://simtk.org/frs/download_confirm.php/file/7165/OpenSim-4.6-win64.exe?group_id=91)。
  实际下载要求 SimTK 登录；本次未取得并验证该正式 GUI 包。用户选择暂时保留当前 GUI。
