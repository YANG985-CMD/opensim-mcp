# 下肢外骨骼：肌肉力与体积工作流（v1.2）

新增 3 个结构化工具，继续使用 Windows 11 和现有 OpenSim 4.6 API 环境，无新增运行依赖。重启 Codex 后加载新工具；已有 GUI 自动桥接保持兼容。

## 肌肉受力

`run_muscle_force_study` 对同一份不可变输入快照运行逆动力学和静态优化，输出逐肌肉的力（N）、激活、峰值、时间均值、RMS 和受力时间积分（N·s）。要求明确给出模型、完整坐标动作、外力及其作用身体/坐标系，或者明确 `no_external_loads=true`。

原生优化器失败会中止，不发布失败帧的受力图。只给动作的 `run_muscle_analysis` 仍只输出几何/运动学结果，不会自动推断激活或肌肉力。

用户必须明确指定 `actuator_profile`，每项包含 `name`、`coordinate`、`role`（reserve/residual）、`unit`（N/Nm）、`optimal_force`、`min_control`、`max_control`。工具不会自动加强肌肉或偷偷添加大辅助力矩。输入模型应使用未重复添加这些辅助执行器的副本。

`quality_limits` 必须包含：

| 字段 | 含义 |
|---|---|
| max_reserve_peak_fraction | 辅助执行器峰值绝对力/矩与该坐标 ID 需求峰值的比例上限 |
| max_residual_actuator_force_N | 每个残余力执行器的峰值上限 N；不是三维合力 |
| max_residual_actuator_moment_Nm | 每个残余力矩执行器的峰值上限 Nm |

示例使用 0.10、20 N、75 Nm，只是显式演示阈值，须按研究目的和文献确定。近零 ID 需求不会被除以零，也不会把非零辅助需求误判为通过。激活范围、输入单位、全部肌肉/执行器列和时间对齐另行检查。报告中的质量状态会从数值重新计算，而非盲信文件里的 pass 标签。

`optimizer_max_iterations` 默认 2000，可显式设置为 1–5000。失败诊断保留首次失败附近的原因，避免末尾成功帧遮盖早先失败。求解完成不等于生理验证；需要检查缩放、肌肉参数、外力方向和作用点，并尽可能用 EMG 等实验量验证。

## 穿戴前后对比

`compare_wearable_muscle_forces` 要求 `assemble_wearable_model` 生成且哈希未变化的物理装配报告；当前支持 WeldJoint 连接的附加质量。两组使用完全相同的动作、外力、肌肉参数、执行器代价设置和数值阈值，输出峰值/均值/RMS/积分差异。

该对比衡量固定动作与外力条件下的装置质量负担。不是主动助力实验，也不能把一条肌肉的预测力下降解释为整体减负、代谢降低或患者疗效。铰接装置、主动助力、绑带力和接触压力需要另行明确模型与实验条件。已有的逆动力学对比仍支持明确给定的理想广义助力曲线，但不自动将其当作肌肉力改善。

两组都可能得到 `completed` 且 `quality.status=needs_review`；网页会显示待复核项。失败不会标为通过；更换输入或窗口必须记录并重新评估。

## 体积来源

`estimate_muscle_volumes` 接受：

- `measured_volumes_cm3`：按模型肌肉名提供的测量体积，并填写 `measurement_source`，例如 MRI 分割的来源。工具记录来源，不独立证明测量正确，也不自动分割医学影像。
- `specific_tension_Pa`：对未测量肌肉必须显式给出此假设，按 `V = Fmax × optimal_fiber_length / specific_tension` 估算，再转为 cm³。Fmax 是原生最大等长纤维力，不是当前受力；不额外乘羽状角余弦。

未提供完整测量或明确比张力时拒绝估算。通用模型参数、合并肌群和比张力假设会影响结果，不能直接称作个人实际肌肉体积。网页管状粗细仍是视觉示意，不代表重建出的真实肌腹外形。

## 网页显示

`export_model_animation` 增加可选参数：

- muscle_result_path：主模型肌肉力报告。
- comparison_muscle_result_path：对照报告；运动、外力、求解设置必须一致。
- muscle_volume_path：带来源的体积报告。
- muscle_data_interpolation：默认 none，只允许微小序列化时间误差；若明确设 linear，则只在覆盖区间内插值，拒绝外推和异常大间隙。

主报告必须与当前模型的原生物理定义一致，输入动作必须是同一份文件内容。外观颜色变化不会破坏匹配，但质量、肌肉和关节参数变化会拒绝旧结果。网页提供固定全时段色标的力/激活着色、肌肉点选、两组曲线、当前数值、体积来源、质量提示及 CSV 导出。CSV 带有质量状态和插值方式。

若受力计算另用了低通滤波，网页明确提示动画显示输入动作，受力来自滤波计算；优先使用经过验证的平滑动作并保持整条流程一致。当前人体示例使用提供的 RRA 参考动作，未再滤波。

## 异步、验证与示例

新增流程可通过 `submit_analysis` 的 `muscle_force_study`、`wearable_muscle_comparison`、`muscle_volumes` 执行。沿用历史记录、真实阶段进度和 Windows 子进程树取消；阶段进度不是预计百分比。

本机人体示例位于 `results/lower-limb-exoskeleton-study`，参考窗口 0.750–1.233333 s、30 帧，不是完整周期。两组各有 3 项足部辅助力矩比例超限，质量为 needs_review；只作为可复现流程演示。

没有人体数据也可运行原创解析校验：加载 scripts/env.ps1，明确指定 E 盘任务临时目录下互相独立的 TempRoot 和 ResultsRoot，再运行：

```powershell
.\.venv\Scripts\python.exe -B scripts\smoke_exoskeleton_muscles.py --report 'E:\simulink\_codex_tmp\exoskeleton-check\validation.json'
```

校验原模型 20 N、增加 0.6 kg 后 26 N 的力平衡，以及 200 cm³ 的体积换算，并验证两组数据可绑定到网页。人体示例与本机结果不打包进公共源码 ZIP；用户应另行安装官方模型资源。

官方参考：[静态优化与输入质量](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53085189/Working+with+Static+Optimization)、[辅助/残余执行器说明](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53114407/_reserves+and+residuals)。

模型物理身份依赖当前原生 OpenSim 的序列化；更换 OpenSim 版本后应重新计算和绑定受力报告。


安装了官方 Gait2354 参考数据后，可完整复现同一参考片段流程：

```powershell
.\.venv\Scripts\python.exe -B scripts\regression_exoskeleton_reference.py --resources 'E:\OpenSimResources\4.6\Models\Gait2354_Simbody' --geometry 'E:\OpenSim 4.6\Geometry' --specific-tension-pa 300000 --report 'E:\simulink\_codex_tmp\exoskeleton-check\reference.json'
```

先加载 env.ps1 并明确设置该任务的 TempRoot / ResultsRoot。`examples/gait2354_study_profile.json` 保存可审查的 23 个执行器、外力映射和数值阈值；它只适用于此官方模型。`--specific-tension-pa` 是显式估算假设，省略则不生成体积估计。输出 completed 与 quality_status 分开，needs_review 不表示生理验证通过。
