# 参考运动驱动的 Moco（v0.7）

`run_moco_track`：参考运动参与目标函数，求解器可以改变运动。输入模型、全坐标
MOT/STO、起止时间、完整 state_bounds 和 control_bounds。坐标文件使用模型的短坐标名，
inDegrees 必须明确；工具转换旋转量为 rad、平移量为 m 和绝对状态路径。
track_reference_derivatives=true 会由参考位置样条生成速度目标。tracking_weight 和
control_effort_weight 控制跟踪与控制代价；可用 max_tracking_rms 为各坐标规定 rad/m RMS 上限。

`run_moco_inverse`：规定全坐标运动后求现有驱动行为，使用模型原有控制界限。
ignore_tendon_compliance 和 minimize_sum_squared_activations 均需显式指定。
不自动加入辅助驱动；需要时先调用 v0.6 的 configure_model_actuators。
原生 MocoInverse 可能为了约束一致性调整运动，质量输出报告逐坐标差异。

两种方法都要求 loads_path + external_forces，或明确 no_external_loads=true。
外力使用 N/m/Nm；全部身体与力/作用点/力矩列前缀都明确给出。原始输入不被覆盖。
mesh_interval 单位为秒，支持 5–200 网格区间，最多 2000 次迭代；单任务仍受 600 秒上限约束。
输出包含 solution.sto、states.sto、controls.sto、规范化参考、工具设置与量化质量 JSON。
状态/控制有限性、时间覆盖、求解状态、采样边界、逐坐标 RMS/最大误差都会检查或报告。
误差以原参考线性插值到求解节点比较，原生求解使用样条；并不假定两者完全相同。
本配置未自动执行网格收敛研究，mesh_stability_assessed=false；研究者应比较多种网格。

异步工作流名 moco_track/moco_inverse；可通过 submit_analysis 或项目流水线运行，
沿用进度、Windows 进程树取消、缓存与续跑。接触参数、EMG 跟踪、自定义目标函数和
任意 Moco XML 留给可信脚本接口；本结构化配置没有覆盖这些问题族。

本机实测：静态滑块 Track、驱动 Inverse、肌肉 Inverse 均 Solve_Succeeded；
肌肉逆问题无外力时目标 0.04，外加 5 N 支持力后目标 0.0225。
90° 旋转参考正确转为 π/2 rad，跟踪 RMS 约 4.50e-8 rad。
这些是解析合成模型回归，未执行人体 Moco 研究验证。

官方依据：[MocoTrack](https://github.com/opensim-org/opensim-moco/blob/master/Moco/doc/MocoTrack.dox)，
[MocoInverse](https://opensim-org.github.io/opensim-moco-site/docs/1.2.0/html_user/mocoinverse.html)。
方法签名还通过本机 4.6 API 查询核对；其他 API 构建缺少 Moco/CasADi 时会明确报错。
