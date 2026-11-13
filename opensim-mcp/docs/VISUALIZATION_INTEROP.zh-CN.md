# 通用三维与跨软件数据联动 — v1.3

适用于上肢、下肢及其他 OpenSim 模型。保留现有肌肉受力视图，新增“外部数据”页：
在同一时间轴显示三维姿态和外部信号，点击曲线定位姿态，显示组件绑定，导出原始采样
CSV 和当前选择上下文。数字开关可明确选择前值保持，连续信号可明确选择线性插值。

本版本采用文件交换。修改 SolidWorks 零件或 MATLAB 数据后重新导出、绑定，生成新工作区；
没有后台实时共仿真、自动回写 CAD 配合或自动对齐人体。API 与 GUI 仍需显式同步。

## MATLAB → 三维曲线

将 `integrations/matlab` 加入 MATLAB 路径，准备带 duration 行时间的 timetable。
每列必须是一列有限数值，明确设置 `VariableUnits`，无量纲使用 `1`。
通过 API/场景查询得到真实组件标识，不要猜测坐标名。示例：

```matlab
addpath('E:\opensim-mcp\integrations\matlab');
t = (0:0.01:2)';
TT = timetable(seconds(t), sin(t), VariableNames={'reference'});
TT.Properties.VariableUnits = {'rad'};
bindings.reference = struct('kind','coordinate','name','r_elbow_flex');
manifestPath = opensim_export_signals(TT, 'E:\study\arm-signals', ...
    Source="MATLAB synthetic example", Components=bindings, ...
    Interpolation="linear", MaxGapSeconds=0.011);
source = readstruct(manifestPath);
```

这是合成信号示例。实际研究应使用实验或仿真数据，并记录来源、单位及时间起点。
MATLAB 帮助函数使用 `writestruct` JSON，要求 R2023b+；本机实测 R2024b。
MATLAB/Simulink MCP 与 skills 独立安装，不作为 OpenSim Python 依赖或打包进发行版。

在 Codex 中依次调用：

1. `load_model(model_path=...)`，再 `export_model_animation(motion_path=...)`。
2. 将 `signals.json` 解码为 JSON 对象；不要仅传入文件名字符串。
3. `attach_visualization_signals(scene_path=<animation.json>, signal_sources=[<对象>])`。
4. `inspect_visualization_workspace(project_path=<返回的 visualization.json>)` 核对资产哈希。
5. 打开返回的 `html_file`。可携带整个工作区文件夹离线查看。

信号源示例（`path` 必须改为已有、已允许访问的绝对路径）：

```json
{
  "schema": "opensim_signal_source_v1",
  "path": "E:/study/arm-signals/signals.csv",
  "label": "MATLAB synthetic example",
  "time_column": "time_s",
  "time_unit": "s",
  "time_offset_s": 0,
  "interpolation": "linear",
  "max_gap_s": 0.011,
  "channels": [{
    "column": "reference", "label": "Reference angle", "unit": "rad",
    "component": {"kind": "coordinate", "name": "r_elbow_flex"}
  }]
}
```

CSV 为 UTF-8，可有 BOM，显式分隔符支持逗号、分号、Tab。也可读取 MOT/STO。
时间单位只接受 `s`/`ms`，先换算为秒再加 `time_offset_s`。信号值保留声明单位，
不会自动把度转弧度。组件可选 `coordinate`、`muscle`、`body`、`frame`、`marker`；
body/frame 使用场景中的绝对组件路径。未绑定组件的通用传感器信号也可显示。

`interpolation` 必须明确为 `none`、`linear` 或 `previous`。禁止外推、重复时间、
非有限数据和跨越 `max_gap_s` 的插值。曲线保留源采样，三维姿态只使用原生导出的帧。
可选 `model_physics_signature` 必须与场景精确匹配；省略时仅验证显式组件标识，
不能据此确认两个实验/模型的物理等价性。已有外部信号的场景不能再次绑定，需使用原始场景。

当前限额：8 个源、总计 32 个信号、每源 2–20000 样本/16 MiB；场景最多 300 帧、
50 个网格，合并数据最多 32 MiB。该功能不会执行导入脚本。

## SolidWorks → 人体三维场景

使用现有 SolidWorks MCP：连接后新建或打开用户指定文档，读取当前几何和状态，
导出 STL。STEP、SLDPRT 先由 SolidWorks 转为 STL/OBJ；OpenSim 不直接解析 CAD 原生格式。
STL 无单位，必须根据 CAD 导出设置和已知尺寸明确 `mm`、`cm` 或 `m`。

将导出文件放入已允许访问的数据目录，调用 `assemble_wearable_model`：

```json
{
  "model_path": "E:/study/arm26.osim",
  "physical": false,
  "links": [{
    "name": "device_mesh", "parent_frame": "/bodyset/r_ulna_radius_hand",
    "mesh_path": "E:/study/device.stl", "mesh_units": "mm",
    "translation_m": [0.04,-0.12,0],
    "orientation_xyz_rad": [0,0,0], "color": [0.1,0.7,0.85]
  }]
}
```

示例变换仅用于测试块显示，不代表实际装置贴合。上肢/下肢共用同一接口，换成模型真实
父坐标架即可。可改用至少 3 对 CAD/人体坐标架对应点做刚性配准，并明确误差上限。
读取返回的模型副本，导出动画时将它同时作为 `geometry_model_path`，然后绑定 MATLAB 信号。

`physical=false` 只加显示坐标架与网格。需要动力学时使用现有 `physical=true` 接口，
明确提供质量、质心、完整中心惯量与受支持关节/轴线，再单独检查运动和外力。
可视化贴合不会计算绑带压力，也不能替代模型参数标定。

网页导出的 `selection.json` 包含组件、姿态时间、当前信号值/单位、来源哈希与模型签名。
它可交给 MATLAB/SolidWorks MCP 继续处理，但不会自己修改其他软件。CAD 文档句柄随会话失效，
后续修改必须重新查询当前文档和状态，不能把历史状态当作当前编辑授权。

## 复现验证

普通 Windows 11 用户无需 MATLAB/SolidWorks 许可证即可运行基础回归：

```powershell
Set-Location 'E:\opensim-mcp'
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime'
.\.venv\Scripts\python.exe -B .\scripts\smoke_v13.py `
  --report 'E:\simulink\_codex_tmp\opensim-mcp-runtime\v13.json'
```

该检查通过真实 stdio MCP 导出原生三维场景、绑定精确采样、验证哈希并故意篡改文件确认拒绝。
依赖、GUI 和安装方式见主 README。本机额外实际启动 SolidWorks 2025、新建测试块导出 STL，
并由 MATLAB R2024b 导出 121 点合成数据，在官方 Arm26 和原创下肢模型上检查显示。
官方人体/几何数据不随源码包发布，需用户独立安装并遵循原始许可。

后续可沿通用可视化继续扩展：双场景/多结果对比、可编辑注释与相机预设、分层几何拾取、
大网格优化、明确坐标系的 CAD 更新映射，以及带握手和时钟校验的实时数据通道。
