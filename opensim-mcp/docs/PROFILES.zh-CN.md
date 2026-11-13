# 标记点放置和辅助驱动（v0.6）

`place_model_markers` 在已经缩放的模型上执行原生 MarkerPlacer。指定静态 TRC、
movable_markers（唯一允许移动的模型标记）、marker_weights，以及移动上限。
可选 coordinate_targets 使用原生 rad/m 数值和权重。未指定的标记受保护；输出新模型、
MarkerSet、单帧静态姿态及设置 XML。max_static_motion_m 限制静态采样中的运动，
max_marker_movement_m 单独限制模型标记局部位置的改变量。移动上限并不证明拟合正确；
应继续用独立 IK 标记残差检查评估运动试验。该工具不替代受试者缩放。

`configure_model_actuators` 为指定坐标添加 CoordinateActuator。每项必须包含：

```json
{"name":"reserve_tx","coordinate":"slider_tx","role":"reserve","unit":"N",
 "optimal_force":1.0,"min_control":-100.0,"max_control":100.0}
```

旋转坐标必须使用 Nm，平移坐标使用 N。role=reserve/residual 是研究者分类，
不会自动猜测骨盆、添加驱动或修改接触力。控制量无量纲，实际力/力矩等于 optimal_force
乘控制量。拒绝重名、同坐标已有 CoordinateActuator、锁定/依赖坐标和错误单位。
输出新模型与 actuator_profile.json，并原生重载及读回参数。

`assess_actuator_usage` 输入模型与物理力/力矩表。definitions 的字段为 name、role、unit、
force_column，以及可选 reference_column。提供 reference_path 时每项都必须显式配对参考列；
例如 SO 的 reserve_tx 配 ID 的 slider_tx_force。两表时间采样必须一致。
工具返回 RMS、绝对峰值、RMS/参考RMS；接近零分母为不可评估。比值本身不代表生理合格。

三项均可作为异步工作流 marker_placement/configure_actuators/actuator_usage，
通过 submit_analysis 运行，也可放入项目阶段，沿用缓存、取消和续跑。

本机实测：单滑块 MarkerPlacer 移动 M2 0.1 m，其余两点完全不变；0.01 m 限制正确拒绝；
添加辅助驱动后的 SO/ID 与用量检查成功，RMS比值 0.000099981。
错误单位、重复驱动拒绝。仅合成算例；未据此验证真实人体的标记或辅助力配置。

依据：[OpenSim ScaleTool / MarkerPlacer](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53090015)，
实际可调用方法以安装的 API 发现为准。
