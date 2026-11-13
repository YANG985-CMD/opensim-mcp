# v1.4 可视化工作台

一个页面查看一组或两组原生场景。三维视图居中，底部只有一条时间轴；右侧保留当前选择和
曲线，组件列表、测量、显示设置与备注按需展开。无需 MATLAB/SolidWorks 在后台运行。

## 日常操作

- 点击“播放”或拖动时间轴，同时查看两边姿态。
- 拖动任一三维视图旋转，滚轮缩放；另一侧同步方向和相对缩放。点击“重置视角”回到默认。
- 点击表面或肌肉路径选择；也可展开组件列表搜索。对应标识或明确映射的组件在另一侧高亮。
- 选择曲线，查看两边数值及“右 − 左”差值。支持坐标、已绑定外部信号、已有肌肉力/激活。
- 展开“距离与角度”，选择两个标记点/坐标架原点测距离，添加第三点测中间点夹角。
- 点击“保存查看状态”下载 JSON；重新打开同一场景后用“恢复状态”载入。

保存内容包括时间、相机、所选组件、隐藏部件、透明度、图层、曲线、测量点及备注。
状态绑定原始场景字节哈希、偏移、容差和映射。输入或时间设置变化会拒绝恢复，
避免误把旧状态应用到不同模型。浏览器不静默写回本地文件，也不要求云端存储。

测量来自原生 ground 坐标中的标记/坐标架原点，距离显示 mm、三点夹角显示度。
它不等于解剖关节角、表面间隙或碰撞检测；同名组件也不证明两个模型物理等价。
两边分别按自己的尺寸居中显示，不会自动做刚体/人体配准。

## MCP 创建

先用 `export_model_animation` 得到 `animation.json`。每个模型可有独立几何和结果。
需要 MATLAB 外部曲线时先调用 `attach_visualization_signals`。然后：

```json
{
  "scenes": [
    {"path":"E:/study/baseline/animation.json","label":"原始方案","time_offset_s":0},
    {"path":"E:/study/updated/animation.json","label":"修改方案","time_offset_s":0}
  ],
  "max_time_delta_s":0.002
}
```

把该对象交给 `create_visualization_workbench`，打开返回的 `html_file`。
一个 scene 即为单视图。每个输入必须在允许访问的目录，几何单位为 m，坐标约定一致；
每场景最多300帧/50网格，两个输入总计不超过32 MiB。

`time_offset_s` 明确加到各场景时间上；只取共有时间范围内的左侧原生采样作为主时间轴。
另一侧选择最近原生采样，平局选较早一帧。超出 `max_time_delta_s`（0–60秒）时显示
“无匹配采样”，隐藏该姿态并留空差值；不插值、不外推、不跨设备自动校时。
标题显示各场景实际原生时刻，底部显示共同时间轴。

不同组件名称可加一一对应的 `component_mapping`：

```json
[
  {"left":{"kind":"coordinate","name":"q_left"},
   "right":{"kind":"coordinate","name":"q_right"}}
]
```

支持 body/frame/muscle/coordinate/marker，映射两边类型一致，坐标单位必须相同。
缺少对应或单位不一致不计算差值。外部信号须有同名标签、同单位和一致组件映射。
肌肉力结果保留“需复核”标识；数值检查不能替代模型/实验验证。

曲线 CSV 保留共同时间、实际原生时间、值/差值/单位、场景哈希与结果质量标识。
测量 CSV 记录时间、单位、场景及点的标识。保存的状态可通过 `view_state_path` 交给
`create_visualization_workbench` 生成带初始查看状态的新页面。
`inspect_visualization_workspace` 可校验所有导出资产哈希。

## 本机复现

```powershell
Set-Location 'E:\opensim-mcp'
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime'
.\.venv\Scripts\python.exe -B .\scripts\smoke_v14.py `
  --report 'E:\simulink\_codex_tmp\opensim-mcp-runtime\v14.json'
```

源码回归测试采用真实 MCP 与原生场景，验证双场景精确匹配、状态恢复、过期状态和篡改拒绝。
浏览器检查覆盖直接网格点选、视角、同步、测量数值、曲线、导出、重新打开恢复及窄屏布局。
示例 `examples/workbench-demo.html` 使用原创下肢示意模型；0.05 rad 坐标差是合成比较条件。
官方上肢模型的本机示例保存在 results，遵循原模型许可，不随公开安装包发布。
