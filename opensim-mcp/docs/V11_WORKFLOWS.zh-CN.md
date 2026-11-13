# v1.1：完整步态检查、GUI 多会话和下肢装置

注册名仍为 opensim_mcp。新增七个结构化工具，普通使用无需启用任意脚本。
完整参数以客户端工具 schema 为准；输入全部使用已允许目录下的绝对路径。

## SolidWorks 装置穿到人体上

现在支持将装置网格装配到 OpenSim 模型副本，加入明确质量和惯量、连接关节，准备
随人体运动的坐标，并调用 ID/JointReaction 等分析。自有演示
[wearable-demo.html](../examples/wearable-demo.html) 可直接用 Edge 打开。
演示是七体下肢示意模型加两件原创护具，不是解剖验证或用户实际装置。

数据流程：SolidWorks 零件/装配体 → 分段网格与审核后的物理参数 → 人体部位/关节映射 →
原生初始化 → 运动预览 → 同条件动力学比较。

原生 SLDPRT/SLDASM 不由 OpenSim 读取。若同时配置 SolidWorks MCP，可由 Codex 调用
它的只读打开、几何/单位/质量查询与 STL 导出，再调用本服务装配。
没有该服务时，在 SolidWorks 手动导出 STL，或提供 OBJ/VTP。STEP 需先用受信任 CAD
软件转为网格；本包不内置 SolidWorks/STEP 转换器，也不加载任意宏。

SLDASM 需同时提供其引用零件（可用 Pack and Go）；跨关节部件要分开导出并明确
各自局部坐标系。一个整体 STL 只能作为一个刚体，不能自动恢复关节或正确弯曲。
SolidWorks 已打开文档的状态需保留；本轮其文档数量已达服务预算，未关闭其他任务文档，
未把原生文件导出入口写成已执行成功。实际装配/受力验证用原创 OBJ，以及官方人体模型。

每个物理部件必须提供：

| 参数 | 含义 |
| --- | --- |
| name / parent_frame | 部件名、明确的父物理框架，例如 /bodyset/femur_r 或先前装置体 |
| mesh_path / mesh_units | STL/OBJ/VTP 文件；明确 m/mm/cm，STL 本身不可靠地声明单位 |
| translation_m / orientation_xyz_rad | CAD 体框架在父框架中的零关节坐标姿态，米和体固定 XYZ 弧度 |
| mass_kg / mass_center_m | 质量与 CAD/装置体局部框架中的质心，kg/m |
| inertia_kg_m2 | 质心处、装置体轴下的 [Ixx,Iyy,Izz,Ixy,Ixz,Iyz] 惯量，kg·m²；不能直接套用未核对符号/坐标的 CAD 积惯量 |
| joint_type | WeldJoint、PinJoint 或 SliderJoint |
| joint_location_in_child_m / joint_orientation_in_child_xyz_rad | Pin/Slider 必须明确 CAD 框架内的关节中心和关节框架轴向；Pin 绕该关节框架 Z 轴，Slider 沿 X 轴 |
| coordinate / coupling | Pin/Slider 的坐标名、范围和默认值；可选理想线性耦合到已有同单位坐标 |

CAD 材料/密度、装配配置、被抑制部件会影响质量。缺材料时不根据外观猜质量。
质量、质心和惯量都应在同一个 CAD 体框架里核对；网格单位转换不会自动改写输入惯量。

本机 1.4.1 可先用 `convert_body_mass_properties` 校验并转换单位、中心/原点惯量、非对角项约定及明确的体框架变换。仅把返回的 `body_parameters` 三个字段放入 link；网格与关节坐标仍须在同一体框架，工具不替你修改它们。全部物理 link 的惯量在原生计算前校验，并在保存重开后回读。详见[质量参数交接](MASS_PROPERTIES.zh-CN.md)。

先调用 `assemble_wearable_model`，例如一件刚性固定的大腿护具：

```json
{
  "model_path":"E:/data/person.osim",
  "physical":true,
  "links":[{
    "name":"thigh_cuff",
    "parent_frame":"/bodyset/femur_r",
    "mesh_path":"E:/data/thigh_cuff.stl",
    "mesh_units":"mm",
    "translation_m":[0,-0.16,0],
    "orientation_xyz_rad":[0,0,0],
    "mass_kg":0.35,
    "mass_center_m":[0,0,0],
    "inertia_kg_m2":[0.0005,0.0008,0.0005,0,0,0],
    "joint_type":"WeldJoint"
  }]
}
```

上面数字仅说明格式，实际使用必须换成装置测量值。工具输出新模型、归一化几何、
质量平衡、原生初始化结果及装配报告，保留输入/API/GUI 模型。可选 open_in_gui=true
打开副本；失败会单独报告。旧模型先由原生 OpenSim 升级并重开，再添加几何，避免混合
不同 XML 版本。几何只读取已允许的文件，不自动扩大访问权限或下载依赖。

也可用 landmarks 代替手工平移/旋转：至少三对非共线的 cad_points 和
parent_points_m。CAD 点按 mesh_units 解释，目标点在父物理框架里以米表示。
工具求保持右手性的刚体拟合，报告 RMS/最大误差；可明确给 max_landmark_error_m。
物理装置禁止拟合时自动缩放，因为这会使原质量/惯量失效。
非零默认或耦合关节值会改变零坐标拟合姿态，需在预览里核对。

`physical=false` 仅生成无质量的显示框架，不接受质量/关节参数。它不能用于证明装置
改变了人体动力学。Pin/Slider 是机械连接；要建立真实膝/踝外骨骼，必须提供父子部件、
关节中心/轴、活动范围，以及人体接口的约束或力模型，不能把任意网格贴合当作完整连接。

`prepare_wearable_motion` 保留人体原采样并加入明确线性耦合的装置坐标；角度正确处理
inDegrees。缺少独立装置坐标、超范围、耦合不一致或模型哈希改变都会拒绝。
无独立坐标的 Weld 装置直接跟随绑定体；独立关节运动需要另行测量/规定。
用 load_model 加载组合模型后，以组合模型作 geometry_model_path 调用
export_model_animation，即可预览网格随运动变化。

## 受力与助力怎么计算

已有 run_inverse_dynamics / run_joint_reaction 可用于组合模型，外力与执行器历史仍须
明确。关节反力需要与实际驱动一致的肌肉/执行器力；不能把缺驱动时的结果当作负载下
的真实绑带力。本轮解析测试给了明确驱动，核对 0.5 kg 护具的 0.5 N 惯性力与 4.903325 N
重力支撑；不是仅检查文件生成。

`compare_wearable_inverse_dynamics` 对基线与已核对的**全 Weld 装置**运行同一运动、
外力和滤波，报告装置质量带来的需求增量。可提供 assistance_path，以及明确的
coordinate/column/unit 映射。助力表必须对应每一个 ID 时间点：

```json
"assistance_mapping":[
  {"coordinate":"knee_angle_r","column":"right_knee_assist","unit":"Nm"}
]
```

剩余广义需求 = 组合模型 ID − 明确给定的理想广义助力。该工具不自动分配肌肉力，
不推断绑带压力、滑移、软组织或接触刚度。有关节/耦合的装置需要专门的力映射，工具
会拒绝套用这个简化减法；可在核对完整装置模型后用原生分析研究。
真实绑带/接触分析还需额外接触几何、刚度、阻尼、摩擦和实验校准，本版本未自动建立。

## 完整步态与数值质量

`inspect_gait_cycles` 使用明确的向上力列、N 单位、符号和开/关阈值，查找同一只脚
两次完整触地。开始就承重、但未观察到起点的片段不会被当成一次已知着地。
它不猜左右脚或轴向；阈值和最短站立/摆动时长写入报告，不插值事件时间。

本地官方 Gait2354 原参考坐标仅 0.4–1.6 s，未覆盖所选周期；新增流程从 TRC 重新 IK，
覆盖右脚测力事件 **0.6183–1.8533 s**。RRA 滤波前显式 resample_coordinate_motion
到 60 Hz；原 TRC 时间列保留三位小数，不能把 0.016/0.017 s 间隔声称为严格均匀。
重采样不外推、不补点、不平滑，并保留原哈希、频率和实际时间范围。

两组肌肉 MocoInverse 已完整求解：100 个状态、77 个控制，网格 0.04/0.02 s。
`assess_moco_mesh_study` 要求给每一列明确 RMS 阈值，列不全会拒绝；目标与轨迹分别判断。
该人体例的目标值变化约 **2.75%**，且若干状态/控制超限，结论为 **needs_review**。
不是全轨迹收敛或生理验证。合成例则通过了全部状态/控制阈值。

`audit_moco_trajectory` 在同样模型、外力和肌腱假设下，逐个检查完整输出节点，报告
肌肉激活、实际执行器力 N/Nm、控制边界及位置/速度约束误差。
人体细网格 125 个节点均已计算；这不是节点间缺陷估计、前向重放或接触压力验证。
原生 RRA 对仅因输出精度产生的重复末端时间点作严格检查，只在数值一致的有限容差内
去重并记录；冲突数据拒绝。不会静默平均或放宽对真实不均匀采样的滤波检查。

复现完整步态，需单独安装官方资源：

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-human-v11' `
  -ResultsRoot 'E:\simulink\_codex_tmp\opensim-human-v11-results'
.\.venv\Scripts\python.exe -B scripts\regression_human_cycle.py `
  --resources 'E:\OpenSimResources\4.6\Models\Gait2354_Simbody' `
  --report 'E:\simulink\_codex_tmp\opensim-human-v11\cycle.json'
```

长任务最多每次原生运算 1800 s。相同输入可加 --resume，核对脚本/输入/输出哈希后
复用已完成阶段。完整周期时长由数据事件确定，不能通过更换短窗口使检查更容易通过。

## 多聊天操作 GUI

所有连接同一桥接目录的 v1.1 服务共用 Windows 文件锁；进程结束后操作系统释放锁。
GUI 自身在 Swing 线程中比较上次观察到的 state_token，模型定义/姿态/时间或修改版本
变了则返回 GUI_CONFLICT。此时重新读取 get_current_model，核对修改后再决定操作。
工具不会自动刷新后重试写入。超时也必须先读状态，因为 GUI 可能已完成该操作。

姿态撤销有会话归属，不能撤销另一个 MCP 会话的最后编辑。真实双进程回归已验证过期
写入和跨会话撤销被拒绝；两个测试 GUI 的重启、身份重建和目录迁移也通过。
旧 v1.0 桥接可读取状态，但 v1.1 写操作要求重开 GUI 加载新的原子检查；先保存工作。
文件锁协调的是本服务，不限制有 Windows 用户权限的外部程序/任意脚本。

安装复现、离线缓存和干净系统验证边界见 [WIN11_REPRO.zh-CN.md](WIN11_REPRO.zh-CN.md)。
