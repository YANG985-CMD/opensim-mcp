# v1.0：恢复、模型结构编辑和三维运动

完整工具参数见 [TOOLS.md](TOOLS.md)。以下是发给 MCP 工具的结构化参数示例，路径需
替换为配置允许的绝对路径。原生模型与网格必须可信，先预览再提交。

## 故障恢复与保存点

`get_model_state` 返回当前原生命名状态，可按 `state_paths` 选择，或用 offset/limit
分页（单页最多 200）。包括模型实际提供的位置、速度、激活等状态；不会执行 Python，
不会改变 revision 或撤销记录。锁定/耦合坐标等具体状态由 OpenSim 模型决定。

加载、结构化编辑、姿态改变及撤销/重做等成功后，服务保存模型定义、全部命名原生状态和
时间。任意脚本运行前也保存恢复点；脚本成功后尝试保存新点。快照在
`results/session-recovery`，按会话 owner 区分；每个 owner 最多保留十个成功快照，
旧会话不会自动替其他会话恢复。目录可能含个人模型和状态，不要上传 GitHub。

发生原生进程崩溃、脚本超时或 MCP 重启后：

1. 调用 `get_recovery_status`，核对 owner、模型及时间，选定 snapshot_id。
2. 调用 `recover_api_session`，传入该 snapshot_id。
3. 若当前已有模型，需明确 `discard_current=true`，它会先保存当前模型的恢复点。

恢复核对模型/状态文件哈希和原生运行时版本，不自动重放脚本。恢复范围是原生模型与状态，
不包含 Python 变量、GUI 工作区、外部文件修改或网络操作。依赖已有文件的任意脚本模型
可能无法生成完整快照；失败会明确报告，不能把此前旧保存点当作最新状态。
手动 checkpoint 与事务回滚也保留全部命名状态和时间。旧版只保存姿态的保存点仍按旧范围
恢复。原生工作进程重启后 revision 改变，之前的编辑请求应重新读取版本。

## 可撤销的模型结构编辑

`edit_model_topology` 默认 dry_run=true，必须传当前 expected_revision。候选结构在独立
原生进程中验证，初始化失败不会替换当前会话模型。已实现：

| 操作 | 范围 |
| --- | --- |
| add_body | 正质量、质心、六项惯量，可带 Brick/Sphere/Ellipsoid 显示几何 |
| add_joint | PinJoint、SliderJoint、WeldJoint，明确父框架、子体及偏置，转动/移动关节明确坐标 |
| add_marker / add_coordinate_actuator | 明确挂载路径或坐标及驱动边界 |
| remove_component / rename_component | 支持的顶层集合成员；名称/路径及状态映射会更新，悬空依赖会拒绝 |
| reconnect_joint | 支持关节的父框架与可选子体重连，保留已有偏置 |

例如加载合成 slider 后，先获取 get_api_session 的 revision，预览以下 operations：

```json
[
  {"op":"add_body","name":"extension","mass":1.0,
   "mass_center":[0,0,0],"inertia":[0.01,0.01,0.01,0,0,0],
   "geometry":{"type":"sphere","radius":0.06}},
  {"op":"add_joint","name":"extension_slide","joint_type":"SliderJoint",
   "parent_frame":"/bodyset/block","child_body":"extension",
   "location_in_parent":[0,0.2,0],
   "coordinate":{"name":"extension_tx","range":[-0.5,0.5],"default_value":0}}
]
```

审核后以相同 revision 和 dry_run=false 提交。每批是一个 undo 步骤，并返回持久
transaction_id；可通过 `undo_model_edit` / `redo_model_edit`，或
`rollback_edit_transaction` 恢复。共同状态保留，新增状态使用原生默认值，移除状态会列出。
拓扑支持有明确边界，不包含任意肌肉/接触/控制器/约束组件的通用编辑。

## GUI 生命周期与配置迁移

`ensure_gui_connection(launch_if_closed=false, wait_seconds=0)` 仅观察连接；明确设置
launch_if_closed=true 才会在没有其他 OpenSim GUI 时启动配置的 GUI。
已有未连接的 GUI 会返回需处理的提示，不会关闭它。桥接状态报告真实 GUI 核心版本。

身份保存在 `results/bridge-state/identity.json`，临时队列配置丢失时可用相同身份重建。
身份/令牌属于私有内容。改变允许输入目录或结果根后，MCP 会继续提供 API 和静态检查，
`get_environment` 会显示 GUI 配置错误；调用 `reconfigure_gui_bridge` 默认预览，
再用 dry_run=false 明确把**已有服务配置中的目录**同步到桥接。此工具不能额外授予新目录。
v1 桥接可原位重载，保留 GUI 进程和当前模型；旧桥接需要明确 allow_legacy_stop=true
停止桥接，保留 GUI 窗口，等保存工作后再重启 GUI。

自动桥接仍不等于自动同步：`sync_gui_model` 的 pull/push 才改变 API/GUI 模型内容。
本轮测试独立启动了两个 GUI，未关闭或编辑用户原有 GUI。

## 离线三维网格动画

先 load_model，然后调用 export_model_animation：

```json
{
  "motion_path":"E:/opensim-mcp/results/example/motion.mot",
  "geometry_model_path":"E:/opensim-mcp/examples/slider_mesh.osim",
  "geometry_roots":["E:/opensim-mcp/examples/Geometry"],
  "max_frames":200,
  "error_color_range_m":0.03
}
```

返回 html_file 与 scene_file。用 Edge/Chrome 打开 HTML 即可拖动视角、缩放、播放暂停、
拖动时间轴、查看与时间同步的关节曲线。`comparison_motion_path` 可叠加对比运动；
`marker_path` 可增加实验标记与误差颜色。包内 [viewer-demo.html](../examples/viewer-demo.html)
是自有合成双体/网格运动示例，直接双击可用。

原生 OpenSim 在模型副本上计算体/偏置框架变换及标记位置，保留当前 API 模型、状态和
revision。坐标需完整，使用短名或绝对坐标路径，角度必须明确，无法覆盖的时间不外推。
geometry_model_path 只提供显示几何，用户必须核对它与计算模型的尺寸/框架/比例相符。

支持 OBJ、STL、自包含 ASCII/base64 VTP 和 Brick/Sphere/Ellipsoid。VTK 在独立子进程
解析二进制网格，MCP 传输进程不导入 NumPy/VTK。几何文件必须已处于允许目录或结果目录；
geometry_roots 只是这些权限内的搜索目录，不扩大权限。拒绝外部 VTP 引用，不读取 OBJ
材质/纹理，不联网；HTML 使用内置脚本和 CSP，模型名称按文本显示。

最多 300 帧、每网格 10 万点/20 万三角形、全部网格 30 万点/50 万三角形；输入和
输出另有大小限制。大型人体网格可需先简化；不自动下载模型资源。不支持纹理、全部
OpenSim Geometry 类型或 GUI 相机实时同步。需浏览器 WebGL；不可用时会提示。
离线 HTML 包含模型/运动数据，分享前核对授权。抽样动画和标记着色不是全时段质量验收。

## 复现原生回归

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-checks' `
  -ResultsRoot 'E:\simulink\_codex_tmp\opensim-mcp-checks\results' -EnableScripts
.\.venv\Scripts\python.exe -B scripts\smoke_recovery.py --report 'E:\simulink\_codex_tmp\opensim-mcp-checks\recovery.json'
.\.venv\Scripts\python.exe -B scripts\smoke_topology.py --report 'E:\simulink\_codex_tmp\opensim-mcp-checks\topology.json'
.\.venv\Scripts\python.exe -B scripts\smoke_viewer.py --report 'E:\simulink\_codex_tmp\opensim-mcp-checks\viewer.json'
.\.venv\Scripts\python.exe -B scripts\smoke_v10.py --report 'E:\simulink\_codex_tmp\opensim-mcp-checks\stdio-v10.json'
```

smoke_v10 会自行关闭任意脚本权限，验证新增结构化工具及 MCP 重启恢复。
其他回归通过可信测试脚本设置完整速度/激活/时间并故意终止工作进程。
GUI 生命周期使用独立用户配置、临时队列与受控测试进程，命令见工程化说明。

播放器浏览器交互检查是可选开发测试，需要 Node.js 和本机 Edge；不属于普通安装依赖。
所有 npm 下载与浏览器配置均放在独立临时目录：

```powershell
$playerCheck='E:\simulink\_codex_tmp\opensim-player-check'
New-Item -ItemType Directory -Path $playerCheck -Force | Out-Null
$env:TEMP=$playerCheck; $env:TMP=$playerCheck
$env:npm_config_cache=Join-Path $playerCheck 'npm-cache'
npm install --prefix $playerCheck --no-audit --no-fund playwright-core@1.64.1
$env:NODE_PATH=Join-Path $playerCheck 'node_modules'
node .\scripts\check_player.cjs "$PWD\examples\viewer-demo.html" `
  'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' $playerCheck
```

检查实际网格像素、时间轴、误差颜色、旋转和播放暂停，并保存截图及 JSON。
浏览器路径按实际安装修改；WebGL 不可用会失败，不会把空白页面当作通过。
