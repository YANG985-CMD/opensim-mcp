# v0.9：C3D、标准人体流程、RRA 和 Moco 研究

import_c3d_trial 在隔离进程使用 ezc3d 1.7.2。必须指定正交、右手的 3×3 源坐标→OpenSim
旋转矩阵。原生点单位 m/mm 转为 m，拒绝选中标记缺失、重名、无穷值；不擅自补点。
time_origin=zero 从零开始，acquisition 使用读取器的零基 first_frame / point_rate。
保留点/模拟信号的原采样率，不自动重采样。

测力台必须逐项指定零基 plate_index、body、name 和 force_sign=+1/-1。
ezc3d 力平台过滤器假设源数据 Z 向上，源 Y/X 向上时明确拒绝自动力转换。
力、COP、COP 处自由力矩按同一旋转转换，统一为 N/m/Nm；自由力矩使用 Tz，
不把平台原点力矩直接当作 COP 处力矩。未接触段按显式 contact_threshold_N 清零。
方向、符号和左右脚不会猜测。用户必须审核原采集设备与标定信息。
源码与算法限制：[ezc3d 官方项目](https://github.com/pyomeca/ezc3d)。

本项目的 slider.c3d / slider_forceplate.c3d 为自有合成样例。后者源 Z-up、100 Hz
测力、10 Hz 标记，平台原力 [-5,0,-100] N。使用
[[1,0,0],[0,0,1],[0,-1,0]] 和 force_sign=-1 转为 OpenSim +5 N X、+100 N Y。
原生 IK 解析位移 0.1×t、无噪声未滤波 ID=-5 N 已测试；真实数据必须另行选择滤波。

validate_trial_inputs 检查模型标记/坐标覆盖、外力身体与列、声明单位和共同时间窗。
它不证明采集轴向和外力符号正确。create_biomechanics_project 生成可审核项目，
串联 scale→MarkerPlacer→IK→拟合检查→ID→MuscleAnalysis→SO→JointReaction；
可加入显式 RRA 和 reserve 配置。缩放、标记权重、滤波和质量阈值均由调用者提供。
先 validate_project，再 run_project；未知参数、不匹配数据和原生失败会停止相应阶段。

run_residual_reduction 使用原生 RRATool。必须为每个独立未锁定坐标提供一个 actuator
和一个 task_weight。RRA 过程中暂用坐标执行器，保存模型恢复原始肌肉/执行器；
COM 调整必须显式指定身体，并提供 FX/FY/FZ/MX/MY/MZ 六个 residual。
分别对应 N 和 Nm；调用者负责它们的坐标/轴对应。已有控制器的模型会拒绝。
不自动采用原生工具的质量调整建议。记录 COM 改变量、rad/m 跟踪误差和 ID 前后残差。
原生控制器可能少输出边界约 1 ms，ID 比较把两轨迹在线性插值、无外推的同一原始
采样时间/滤波/窗口下评估。至少六个共同样本；残差下降不被预设为必然结果。
原生依据：[RRATool](https://github.com/opensim-org/opensim-core/blob/main/OpenSim/Tools/RRATool.cpp)。

prepare_moco_model 只修改新模型副本。可显式选择替换为 DeGrooteFregly2016 肌肉、
忽略肌腱顺应性或被动力，以及逐坐标 reserve/residual 定义。输出每条肌肉转换前后
类型；这些操作改变模型物理，不能称为与原模型生理等价。

run_moco_convergence 执行 2–4 组逐渐减小的 mesh_interval_values_s，比较目标值和
所有状态/控制轨迹。接近零目标使用绝对容差，不产生无意义的相对百分比。
未提供轨迹阈值时明确标记 objective_only；只有配置的量被判定，不声称数学收敛证明。
run_moco_sensitivity 对基线执行 1–5 组明确的物理参数或目标/肌肉选项扰动，
记录目标和状态差值，不等同统计不确定性或临床因果效应。模型参数修改不影响用户 API 会话。
长运算使用 submit_analysis 的 moco_convergence / moco_sensitivity / rra 工作流。

真实本地 Gait2354 数据：RRA、恢复 54 条肌肉，以及 0.4–0.5 s 的两组肌肉 MocoInverse
网格均完成原生计算。该短窗口不是完整步态周期验证；目标一致也不替代轨迹/生理验证。
真实参与者输入不随源码分发，机器验证中只保留数值、哈希和已说明的测试范围。
