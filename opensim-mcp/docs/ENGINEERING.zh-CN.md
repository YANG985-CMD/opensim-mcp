# Windows 11 安装、修复、复现与发布（v1.1）

## 普通使用者：解压后双击

下载源码 ZIP 和对应 SHA256 文件，先用 `Get-FileHash` 对照校验。
解压到最终位置，例如 `E:\opensim-mcp`；此后不要直接移动已安装的虚拟环境。
双击 `install.cmd`。无需预装 Python；安装器在缺少 uv 时下载固定 0.11.26 官方 ZIP 并
核对内置 SHA256，然后下载 CPython 3.12.13，创建两套环境，按哈希锁安装服务依赖和
OpenSim 4.6 API，注册 Codex 并执行一次真实 MCP/IK 自检。需要联网；首次下载较大。
Windows 11 x64 是用户支持范围。脚本以当前用户运行；无须为了 API 计算安装 GUI。

本机已有 uv 时复用它。缺少 Visual C++ x64 运行库时原生导入会明确失败，按微软官方
[受支持的 VC++ 运行库](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)安装后重试。
不自动下载或升级 GUI。服务依赖与 API 分开，不把 GUI 的 DLL 加入官方 wheel。

有 GUI 时可在 PowerShell 使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -OpenSimRoot 'E:\OpenSim 4.6'
```

安装启动插件后重开一次 GUI；启动服务时会生成桥接脚本。可继续使用
`scripts/start-gui.ps1` 的持久配置目录，避免测试配置造成首次资源安装弹窗反复出现。
GUI 资源仍需正常安装一次；API 安装不会冒充 GUI 资源安装。

默认 Codex 注册名始终为 opensim_mcp，只合并该服务器配置，逐项核对其他 TOML 配置值
保持一致，并在项目 state/codex-config-backups 留私有备份。遇到无法安全解析的配置布局会
拒绝写入，提供 config/opensim_mcp.generated.toml 手工合并。可用 -SkipCodexRegistration
只安装环境。默认任意脚本关闭；可信本地用户可按 README 显式启用。
注册依据：[OpenAI MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

## 自检与有限自动修复

双击 `doctor.cmd`，检查依赖版本、原生 API/Python/NumPy、Moco/MarkerPlacer 能力和发行
源码清单，输出 JSON 诊断。也可在 Codex 调用 check_version_compatibility。
缺失原生库会报 error；未知/旧版组合标为 warning，不会显示通过。
主验证组合是 Windows 11 x64 + 主服务 Python 3.12 + API Python 3.12/OpenSim 4.6。
旧 4.3/3.8 只保留以往核心分析验证，不覆盖本次新增 Moco/MarkerPlacer 配置。
GUI 实际版本由桥接状态另行报告，不与 API 版本混为一谈。

```powershell
.\doctor.cmd -Repair
# 或指定临时目录
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -Repair
```

修复只重装锁定依赖/API、补缺失目录并重新执行自检，不替换用户模型、源码修改或 GUI，
也不改已有 Codex 配置。若服务正在占用包文件，应关闭 Codex 后执行修复。
环境中的 Python 主版本不匹配时建议解压到新的正式目录重装，保留原环境作回退。
源码哈希不一致可能是本地开发，报告列出差异；自动修复不会覆盖源码。
报告和下载/构建中间文件进入 TempRoot；E 盘存在时默认使用
E:\simulink\_codex_tmp\opensim-mcp-runtime，其他电脑可用 -TempRoot 指定本地目录。
安装器临时目录清理失败会报告路径，计算结果、历史、保存点与用户配置是持久内容。

## 项目包与模型编辑

export_project_bundle 把显式输入数据与项目配置打包，记录文件哈希、原生/服务运行时和来源。
模型规范化为原生计算所用的自包含 XML，移除外部显示几何并保留安全基础几何；源模型不被修改。
包不含 GUI 网格、任意脚本、Python/GUI 本体、凭据或服务全局权限。
分享包会分享其中输入数据，请先核对数据授权。verify_project_bundle 校验清单/文件哈希，
拒绝穿越路径、Windows 设备名、大小写冲突和额外文件；import_project_bundle 只导入新目录，
不执行原生模型或安装钩子。哈希证明完整性，不能证明来源可信或跨版本数值等价。

apply_model_edits 默认 dry_run=true，需当前 expected_revision，预览所有参数修改和原生初始化。
dry_run=false 时整体提交，任意一步失败则当前模型不变，整批构成一个撤销步骤。
提交前保存持久恢复点并写编辑日志，list_edit_transactions 跨服务重启可读；
rollback_edit_transaction 恢复之前模型/全部命名原生状态/时间，同时保留当前恢复点。
批量支持体参数、坐标、标记和肌肉的已有结构化属性，不覆盖任意拓扑或脚本的外部副作用。
export_model_scene 输出实际三维坐标 JSON、三个等比例正交 SVG 视图和自包含 HTML，
它是静态姿态工具；v1.0 另有 export_model_animation 提供离线网格动画、视角旋转和时间轴，见 V10_WORKFLOWS.zh-CN.md。

## GitHub 自动测试和按标签发布

把源码上传到自己的仓库并开启 Actions。工作流 .github/workflows/windows.yml 会在 push、PR
或手动运行时使用固定提交的官方 Actions，完成安装、全部适配器测试、原生配置、
项目缓存/取消/迁移及 MCP 回归，然后构建源码 ZIP + SHA256 和测试证据附件。
GitHub 的 windows-2025 是 Windows Server 运行器，不代表真实 Windows 11/GUI 已被测试；
本地 Win11 验证和 GUI 生命周期验证单独记录。

版本号与标签一致且全部检查成功时，推送 v1.1.0 之类标签会自动创建 GitHub Release，
附上经过测试的 ZIP/校验文件。无需另填个人令牌，发布任务才获得 contents:write 权限。
标签不匹配、测试失败、安装失败均不发布。首次仓库运行需在 Actions 页面查看真实结果。
本地编写/校验工作流不等于它已经在 GitHub 上执行。

```powershell
git tag v1.1.0
git push origin v1.1.0
```

本交付没有替你创建远程仓库或推送标签，避免猜测仓库地址。托管运行步骤参考
[GitHub Python 测试](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)及
[工作流权限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)。



## v1.0 可选桌面与人体回归

`.github/workflows/windows11-desktop.yml` 为手动触发的真实 Windows 11 自托管工作流。
专用运行器需标签 self-hosted / Windows / X64 / windows-11 / opensim-gui，已安装 GUI、
本项目启动插件及官方资源。先按插件说明安装一次插件；工作流通过独立用户配置和
启动参数覆盖测试桥接路径，不覆盖日常用户配置。不要在不可信 PR 上运行自托管任务。
工作流缺插件会明确失败；托管 Windows Server 主流程不执行 GUI 测试。

本机或专用测试机复现 GUI 生命周期：

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-gui-checks' `
  -ResultsRoot 'E:\simulink\_codex_tmp\opensim-gui-checks\results' -OpenSimRoot 'E:\OpenSim 4.6' -EnableScripts
.\.venv\Scripts\python.exe -B scripts\regression_gui_lifecycle.py `
  --opensim-root 'E:\OpenSim 4.6' --resources-root 'E:\OpenSimResources\4.6' `
  --examples "$PWD\examples" --report 'E:\simulink\_codex_tmp\opensim-gui-checks\gui.json'
```

需预先正常安装官方资源，测试会启动/结束自己拥有的两个 GUI，并验证重启、失效心跳、
临时队列配置重建和原位目录迁移。不会终止用户其他 GUI。

人体核心回归（另装官方 Gait2354_Simbody 资源）及新增短窗研究：

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-human-checks' `
  -ResultsRoot 'E:\simulink\_codex_tmp\opensim-human-checks\results'
.\.venv\Scripts\python.exe -B scripts\regression_human.py `
  --resources 'E:\OpenSimResources\4.6\Models\Gait2354_Simbody' `
  --report 'E:\simulink\_codex_tmp\opensim-human-checks\human.json'
.\.venv\Scripts\python.exe -B scripts\regression_human_studies.py `
  --resources 'E:\OpenSimResources\4.6\Models\Gait2354_Simbody' `
  --report 'E:\simulink\_codex_tmp\opensim-human-checks\studies.json'
```

路径需有 OutputReference/subject01_simbody.osim、subject01_walk1_ik.mot 及测力台文件；
不同资源版本可缺此样例，需提供匹配样例，不能把缺数据跳过写成通过。
studies 脚本仅对该示例的命名和轴向有效，显式使用 23 个驱动、54 肌肉转换、RRA
0.4–0.6 s 和肌肉 MocoInverse 0.4–0.5 s；输出标记 objective_only，未证明全轨迹收敛。
跨版本核心比较另加 --legacy-python 与 --legacy-root；不下载参与者数据到源码仓库。


v1.1 新增实际微型 Moco 求解检查与离线缓存修复；故障矩阵和干净系统入口见 [WIN11_REPRO.zh-CN.md](WIN11_REPRO.zh-CN.md)。
多会话 GUI 和物理装置参数范围见 [V11_WORKFLOWS.zh-CN.md](V11_WORKFLOWS.zh-CN.md)。
