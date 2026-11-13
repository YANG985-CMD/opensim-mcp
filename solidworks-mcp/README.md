# solidworks-mcp · SOLIDWORKS 2025

本地 stdio MCP，版本 **0.5.3**，共 **53 个结构化工具**，通过本机官方 COM API 和类型库操作原生零件与装配。Codex 配置项及 MCP 握手名称为 `solidworks-mcp`，沿用既有启动路径。

入口：`.venv/Scripts/python.exe -B -u launch.py`。仅本地 stdio，不开放网络端口。Python MCP SDK 为 1.30.0，依赖锁定见 `requirements-lock.txt`。已验证范围见 [VERIFICATION.md](VERIFICATION.md)。

## 0.5.3 移植与连接诊断

分享版安装器从本机 SOLIDWORKS 2025 注册表定位类型库，也支持显式路径。安装后用真实 stdio 握手、工具清单和 `sw_health` 自检，再把本机生成的条目导入 Codex。客户端启动项直接读取安装目录里的设置，无需逐项复制环境变量。

`sw_health` 区分服务已响应、类型库缺失和待连接。原生错误返回 `recovery` 与可用的 `next_tool`。服务会提示客户端沿 MCP 路径排查，受阻时报告原始错误。工具选择由客户端负责，服务无法强制禁用客户端的 Computer Use。

## 0.5.2 界面名称

服务注册名统一为 `solidworks-mcp`，对外显示品牌为 **SolidWorks MCP**。53 个工具都提供独立的人类可读标题，格式为 `SolidWorks MCP · 操作名称`，例如“SolidWorks MCP · 文档列表”和“SolidWorks MCP · 关闭文档”。工具顶层 title 和 annotations.title 一致，供客户端选用。协议工具名沿用 sw_ 前缀。客户端需要重新加载工具清单；已保存的历史操作名称由客户端管理。

## 0.5.1 尺寸对比修复

原生特征树可能在草图及拉伸特征中重复列出同一尺寸。本版按原生全名与相同数值/类型去重，仍拒绝身份、数值或类型冲突。已通过滑块与转轴真机验收，详细量化结果见 VERIFICATION.md 和 verification/20261106-v051-native.json。

## 0.5.0 装配交付工作流

- `sw_compare_assemblies` 比较两个显式装配句柄。默认按精确名称匹配，改名时传旧名到新名的一对一映射。报告组件与配合增删、位姿偏差、限位、指定组件的尺寸及原生质量差。顶层未解析、配置不一致、未赋材料或质量覆盖会保留相应限制。名称、几何摘要或位姿吻合无法证明完整表面等价。
- `sw_capture_joint_recipe` 从新鲜组件几何捕获转动关节或两平面导向滑动关节，返回可保存的 JSON。通过 `sw_apply_joint_recipe` 在目标副本上先预览，再显式传 `preview=false` 建立原生配合。旧面 ID 不复用。签名不匹配或找到多个匹配面时会拒绝。可在 JSON 中调整位置与上下限，单位为转动 deg、滑动 mm。
- `sw_run_assembly_steps` 执行不超过 16 步的显式计划。每行格式为 `{action,parameters}`，可用动作是 `apply_joint_recipe`、`set_mate_positions`、`scan_motion`、`audit_assembly`。收到失败后用 `sw_assembly_task_status` 查看任务。步骤、已完成样本和失败码保存在配置运行目录的 `assembly-tasks`，重连保留。任务记录可能包含机构名称和尺寸，清理运行目录会删除这些记录。
- `sw_verify_package_references` 在保存的输出副本关闭后新开只读文档，对照显式零件清单检查引用。检查后保留该只读窗口。检查范围为已解析的顶层 SLDPRT。
- `sw_write_acceptance_report` 从当前对比、原生体检、可选交付基线和任务记录生成自包含 HTML。输出必须是输出目录中的新文件。可选重开证据只有在同一候选句柄、状态和文件哈希一致时才沿用。跨文档/状态的历史姿态会标为未绑定；当前间隙和离散姿态采样的证据分别展示。

建议顺序：显式打开两个版本 → 记录输出文件基线 → 在副本上改动及记录步骤 → 保存导出 → 关闭已保存副本并核对重开引用 → 生成 HTML。没有设置的检查会留空或待复核。查看 [验证记录](VERIFICATION.md) 了解覆盖范围。


## 0.4.0 增量记录

- 使用 `sw_find_tools` 按中文或英文关键词查找本服务已注册工具。已有工具仍直接可用。
- 导出前使用 `sw_delivery_baseline` 对明确指定的输出文件记录哈希。输出后使用 `sw_verify_delivery` 区分新增、改动、原样、缺失和空文件。只有全部为非空新增或内容改变才返回 `fresh`。
- 只检查配置输出目录下的 STEP、STL 和 SOLIDWORKS 原生零件/装配。每次最多 256 文件、合计 2 GiB。基线保留在同一 MCP 进程，重连后需重建。哈希证据不判定文件作者、几何或设计是否合格。

## 0.3.5 增量记录

0.3.5 将“零件完成就关窗”写入 MCP 初始化流程，并为原有 `sw_save` 增加 `close_when_finished=True`，工具总数仍为43。阶段保存默认不关；完工时先保存核对，再关闭这个零件窗口。被总成引用时保留数据，核对父装配引用、位姿、配合和未保存标志不变；未知隐藏未保存内容会阻止关窗并返回原因，不丢弃、不自动重启。未引用零件卸载后句柄失效，需重开。详见 [完工关窗流程](WORKFLOW.md)。

0.3.4 增加 `sw_import_step(path)`：仅导入已放在项目输出目录内的本地 STEP（100 字节至 64 MiB），使用官方 STEP 导入设置，不自动运行 FeatureWorks、不重复导入已打开的文件。核对导入后实体体积及输入文件哈希；原生部分失败返回文档句柄，要求先检查，不自动重试。导入几何不代表材料、完整硬件质量或真实机构自由度。

`sw_package_assembly` 增加 `include_unsaved_assembly=True`，用于明确复制当前未保存的总装姿态。默认仍拒绝未保存总装；任何未保存引用零件仍拒绝。使用原生高级保存副本，核对源文件字节、几何状态与未保存标记，保留原文档待保存状态。

更新后需重新连接 MCP 才会在客户端显示新工具；源码更新不会替用户重启 SOLIDWORKS 或关闭文档。RS03 专用组件替换及连接板建模使用任务内受控官方 API 脚本，尚未扩展成通用替换/任意建模工具。

| 能力 | 工具 |
|---|---|
| 当前姿态体检：配合错误、基座引用连通、限位、全部重叠及指定零件间隙 | `sw_audit_assembly` |
| 空装配批量插入，逐件核对刚性变换和固定状态 | `sw_add_components` |
| 原生锁定配合组成刚体组，保留组锚点的运动 | `sw_connect_rigid_group` |
| 转动、两平面导向滑动、球面中心关节模板 | `sw_create_joint` |
| 多个原生位置尺寸一起驱动，先核对全部限位 | `sw_set_mate_positions` |
| 一次修改一个零件的多个 SI 尺寸，再重建核对 | `sw_set_dimensions` |
| 分段运动采样、连接检查和逐姿态实体干涉 | `sw_scan_motion` |
| 按确切名称抑制/恢复单个配合 | `sw_set_mate_suppressed` |
| 模块文件夹整理并默认折叠，核对几何与配合不变 | `sw_organize_assembly` |
| 高级保存的引用感知副本及规范改名 | `sw_package_assembly` |
| 距离/角度配合方向批量反转，核对镜像侧位置 | `sw_set_mate_flips` |
| 关节、滑座和肌肉显示尺寸在同一次调用中更新 | `sw_set_assembly_pose` |
| 分批释放已保存引用件窗口，保留总装中的零件和配合 | `sw_close_reference_views` |

每次批量操作前验证参数；原生失败可能留下部分修改，会返回已完成项目，不会自动重复写入。`sw_scan_motion` 每次至多 8 个姿态，覆盖的是离散样本，并非连续碰撞检测。它不修改源零件尺寸；柔性气动肌肉预览应使用 `sw_set_assembly_pose` 同时更新配合和显示尺寸，避免分次调用留下端头已移动而肌肉仍短缩的画面。该工具暂缓画面刷新，普通失败会尝试恢复捕获的参数并明确报告恢复是否通过；不是数据库事务，超时仍需重新检查几何。显示刷新标志有独立恢复记录。

默认采用模块文件夹与编号命名，详见 [NAMING.md](NAMING.md)。要求已写入 MCP 初始化说明；原生整理前后核对零件、配合与 STL，不靠合并或隐藏组件来缩短树。

0.2.0 已有能力：

| 能力 | 工具 |
|---|---|
| 组件固定/浮动切换 | `sw_set_component_fixed` |
| 同心、重合、平行、垂直、距离、角度、距离限位、角度限位、锁定配合 | `sw_add_mate` |
| 原生配合位置驱动，保留限位 | `sw_set_mate_position` |
| 配合、限位、错误和原生自由度状态读取 | `sw_assembly_status` |
| 原生配合求解的增量移动，分别回读目标和实际位置 | `sw_move_component` |
| 当前姿态的原生实体干涉和体积 | `sw_check_interference` |
| 本机材料库查询、原生材料赋值 | `sw_materials`、`sw_set_material` |
| 原生质量、质心、惯性与材料审计 | `sw_mass_properties` |

`sw_add_mate` 使用来自最新 `sw_component_geometry` 的 `{component, face_id}` 或 `{component, plane_name}`，锁定配合使用两个 `{component}`。同心支持圆柱面与圆柱面、球面与球面；球面连接不锁转。仅支持已解析的顶层原生零件，不代表任意复杂嵌套装配已验证。

## 如何连接可动机构

1. 显式新建装配或用 `sw_open_document(editable=True)` 打开指定文件。每次修改使用最新 `document_id` 和 `state`。
2. 固定基座，运动件设为浮动。属于同一刚体的零件用锁定配合连接，避免将全部零件固定到世界坐标系。
3. 转轴用同心配合定位轴线，再用重合/距离配合定位轴向位置，保留绕轴转动。
4. 滑座用锁定旋转的同心配合，或两个独立平面约束，限制侧移和转动。
5. 自由机构用 `sw_move_component` 在保留的方向上移动；需要可重复控制的限位机构，则添加原生角度/距离限位，用 `sw_set_mate_position` 改变位置，让 SOLIDWORKS 求解整个连接机构。
6. 核验实际位姿、越界拒绝、禁止方向、干涉及保存重开后的连接和运动。配合名称存在不足以证明机构可动。

### 限位与拖动

2026-11-02 源码补丁：当原生上限回读为 `175.99999999999997 mm`、调用输入为显示值 `176 mm` 时，在原有越界检查通过后，将舍入误差范围内的目标归一到原生边界，避免求解器保留旧位置。单个和批量位置入口均处理；真实越界仍在写入前拒绝，不修改限位。代码更新后，已运行的 stdio 进程需重新连接加载；不需重启 SOLIDWORKS。

本机 SOLIDWORKS 2025 SP0 的限位装配，通过普通变换求解或拖动后再强制重建，可能回到限位配合保存的当前位置。本版可靠的程序入口是 **`sw_set_mate_position`**：修改原生配合的当前位置尺寸、重建连接件，并回读位置和不变的上下限；不直接覆盖组件 `Transform2`。

`sw_move_component` 使用 `IComponent2.SetTransformAndSolve3` 求解；`native_solver_return=True` 不保证目标实现，必须检查 `request_achieved` 与 `achieved_transform`。操作后核对锁定/锁转连接的相对位姿，若原生求解使连接失效则明确报告部分修改。未声称所有限位组合都通过了手工鼠标拖动测试。原生配合位置驱动是 CAD 运动学，不是电机或受力仿真。

不要为获得拖动效果而将限位配合的驱动尺寸自动改为参考尺寸。本机试验中这种做法可能使锁转的从动件未跟随转轴，即使原生配合没有错误标志。本版不使用这种做法。

原生 `GetRemainingDOFs` 的返回整数是 `swRemainingDofs_e` 可用性枚举，**不是自由度数量**。保留返回码、方向和状态，无法可靠解释的数量返回 `null`。带限位的组件报告 `fully_constrained`，不能单凭这个标志判断是否能由配合位置驱动运动。

### 单位

- 通常长度使用 **mm**、角度使用 **deg**。
- `sw_set_dimension` 明确使用 SI：长度 **m**、角度 **rad**，仅允许读取到的确切已有尺寸名。
- 原生参考角/距离必须非负。有符号关节范围需偏置基准：例如中立参考角 90°，参考范围 69°～113° 对应关节 −21°～23°；必须按实际基准面和方向核对。
- `sw_set_mate_position` 越界在原生修改前拒绝，调用后回读当前位置及原有限位。
- 质量、质心、惯性使用 **kg、m、kg·m²**。未赋材料会明确标出，不能把默认密度或概念包络当作真实硬件质量。

## 保留的 20 项基础工具

连接及文件：`sw_health`、`sw_connect`、`sw_documents`、`sw_new_document`、`sw_open_document`、`sw_close`、`sw_save`、`sw_export`（STEP/STL）。

基础零件：`sw_box`、`sw_cylinder`、`sw_polygon`、`sw_through_hole`、`sw_fillet`、`sw_set_dimension`。

检查与原有装配：`sw_geometry`、`sw_features`、`sw_add_component`、`sw_component_geometry`、`sw_mate_cylinders`、`sw_api_lookup`。

## 尚未实现

任意复杂草图、扫掠、放样、曲面、钣金、自动工程图和标注、Motion 动力学及有限元分析仍未提供；也不提供任意代码或宏执行工具。当前姿态干涉检查不等于连续扫掠、最小间隙、接触或应力分析。

外骨骼连接案例位于 `E:\simulink\aanew\SolidWorks输出\双髋外骨骼_可动装配_R01_20261031`；当前实际验收范围和限制以该目录的交付说明、运动检查结果及下列 VERIFICATION.md 为准。关节模板不是任意装配自动识别器，也不代表实物承载、夹紧器和人体相容性已经通过验证。

## 配置与保护

| 变量 | 用途 |
|---|---|
| `SWLOCAL_OUTPUT` | 正式模型输出，本机 `E:\simulink\aanew\SolidWorks输出` |
| `SWLOCAL_TEMP` | E 盘临时运行目录 |
| `SWLOCAL_YEAR` | 目标年份，默认 2025 |
| `SWLOCAL_TYPELIB` | 本机 `D:\SW2025\SOLIDWORKS\sldworks.tlb` |
| `SWLOCAL_TIMEOUT` | 单次操作等待时间，默认 120 秒 |

COM 对象只在独立工作进程的 STA 线程中使用。显式指定文档并核对状态，不回退到另一个活动文件；拒绝只读修改、同名冲突、越界保存和默认覆盖。状态包含原生配合、材料标识和当前配置。超时可能已经部分修改模型，只停止本桥接进程，不结束 SOLIDWORKS，不自动重放写操作。

大装配状态读取使用原生文档身份、更新标记、配置及每次读取的材料身份保护几何摘要缓存；绝不缓存供选择的边/面编号或 COM 几何实体。操作后重新读取组件变换和配合。装配操作仅重建顶层；零件尺寸操作重建零件本身。原生 `CommandInProgress` 按调用设置并恢复，异常退出留有本桥接的恢复记录；不修改全局安全设置或启动另一实例来恢复标志。

改名脚本 `integration/configure_codex.py` 保留既有服务器的环境和超时设置，并语义核对其他配置。指定 `--apply` 才写入：

```powershell
.\.venv\Scripts\python.exe -B .\integration\configure_codex.py `
  --config "$env:USERPROFILE\.codex\config.toml" `
  --temp-root 'E:\simulink\_codex_tmp\solidworks_config' --apply
```

运行中的旧进程不会因源码写入自动更新。重新加载该 MCP 连接或重启 Codex 后，确认 `sw_health` 返回 `solidworks-mcp / 0.3.3`，且工具列表共 42 项，包含 `sw_audit_assembly`、`sw_create_joint`、`sw_scan_motion`、`sw_set_assembly_pose`、`sw_close_reference_views`。

`sw_documents` 将 MCP 写入许可 `editable` 与原生打开模式 `native_read_only` 分开报告。`sw_open_document(editable=False)` 对尚未打开的文件使用原生只读模式；对已经打开的可编辑文件只建立检查句柄，不改变其打开模式。对已打开的原生只读文档，明确调用 `sw_open_document(path, editable=True, state=最新状态)`，使用官方 `SetReadOnlyState(False)` 原地取得写入权限，核对几何状态及未保存标志不变。拒绝文件系统只读或其他写入者的锁，不自动重开、保存或丢弃。日常仅检查已经打开的用户装配时，优先从 `sw_documents` 取得现有句柄。

## 验证与依据

### 装配体检

`sw_audit_assembly(document_id, clearance_pairs=None)` 集中读取当前配置和姿态：启用配合错误、有效配合到固定基座/装配基准的引用连通性、原生限位余量、全部实体重叠。支持只读句柄，不修复、不保存、不抑制配合，也不会自动豁免历史重叠。

需要间隙时，明确提供最多 16 对 `{component_a, component_b, minimum_mm}`，名称必须来自最新装配检查；最小要求由实际设计指定。用官方 [IModelDoc2.ClosestDistance](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~ClosestDistance.html) 测量原生组件，回传毫米及装配坐标系最近点，并结合实体干涉判定，避免“完全包含但表面距离大于零”被误判为满足间隙。

结果为 `PASS`（本次范围通过）、`REVIEW`（需确认）、`FAIL`（配合/指定间隙等明确失败）或 `INCOMPLETE`（部分检查不可用）。引用连通不证明正确自由度、销轴轴向穿入或真实传力；当前姿态不代替全行程检查。未检查的间隙不会被说成通过。配置不一致、嵌套或未解析件明确标记不完整。

原生检查可能点亮未保存标记。体检分别回传前后标记；几何状态改变则报错，只有标记改变则保留报告并提示，绝不为了清除星号自动保存或丢弃。正式项目源文件哈希另行核对。

设置 E 盘 `SWLOCAL_TEMP`，执行 `.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*.py' -v`。实机测试 `tests/live_mechanisms.py` 通过真正的 MCP stdio 客户端检查转动、滑动、限位、保存重开、刚性连接及干涉正负例。`tests/live_linked_chain.py` 检查三个零件的连接传动；默认使用限位位置驱动，`--free` 使用两平面导向的自由机构。测试要求目标文件不存在，逐步记录资源，失败即停，不自动重复写操作。旧的基础建模验收脚本仍保留。

依据本机官方 `sldworks.tlb`、`swconst.tlb` 及 `api/HelpViewer/sldworksapi/apihelpviewer.cab` 的 API 文档；另见 [角度配合接口](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IAngleMateFeatureData.html?id=2.2.1.4)、[OpenAI 官方 MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp)。跨版本文档只用于理解接口，本机签名和验证结果另行核对。

第三方来源及许可见 `THIRD_PARTY_NOTICES.md` 和 `LICENSES/`。未修改 SOLIDWORKS 程序、许可证或全局安全设置。

### STL 导出约定

`sw_export` 的 STL 默认输出二进制、毫米、保留原点；总装为一个 STL，不再随用户原设置散成每个实例一份。只在该次导出期间设置相关选项，逐项回读并恢复原首选项；超时有按原生进程身份核对的恢复记录。整体 STL 保留各组件原几何，未将重叠体布尔合并，不代表可整体打印。依据[官方 STL 导出选项](https://help.solidworks.com/2019/English/api/swconst/FileSaveAsSTLOptions.htm)，枚举值已核对本机 2025 类型库。

完整姿态预览暂缓刷新使用官方 [IModelView.EnableGraphicsUpdate](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelView~EnableGraphicsUpdate.html)；它不是实物气动肌肉的动力学模型。

### 原生副本与规范改名

本机 `GetPackAndGo` 在返回对象之前报参数错误，未执行文件打包写入。`sw_package_assembly` 明确改用官方 `SaveAs3`、`IAdvancedSaveAsOptions`、`SaveAllAsCopy`：先验证全部引用清单，再指定逐文件名称和路径，回读计划后保存副本；检查全部源文件 SHA-256 不变。没有在保存失败后自动尝试另一种写入方式。依据[官方 SaveAs3](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~SaveAs3.html)和本机 2025 官方帮助包及类型库。

### 分件交付与窗口资源

要求分件/打印交付时，总装 STL 不能代替独立零件文件。按唯一原生零件各导出一次，附实例数量；明确排除不打印的气动肌肉占位件，结构件、外购件包络及柔性件参考分文件夹。项目入口 `设计源文件/export_parts_stl.py` 使用结构化 MCP，逐件核对毫米单位、源文件哈希及导出前后状态；中断后 `--resume` 先核对已完成文件，不重放未知结果或覆盖现有 STL。

仅“已加载”不等于用户打开了独立窗口。`sw_documents` 另返回 `visible` 与 `modified`。`sw_close_reference_views` 在明确的父装配和最新状态下，按确切组件名关闭已保存引用件窗口，保留加载在父装配中的模型数据，核对全部组件/配合及父装配未保存标志不变；跳过未保存零件，有隐藏未保存文档时在调用 CloseDoc 前拒绝。不给脏文档自动保存或丢弃修改。依据[官方 CloseDoc](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isldworks~closedoc.html)和[Visible 资源说明](https://help.solidworks.com/2022/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldoc2~visible.html)。
