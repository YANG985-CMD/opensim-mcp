# 项目流水线（v0.5 起）

`examples/project.json` 是可运行的七阶段例子：缩放、IK、独立标记误差检查、ID、
关节反力，以及肌肉模型的静态优化和几何分析。配置内的相对路径从项目 JSON 所在目录解析。
所有文件仍需位于管理员配置的允许目录或 results 下；JSON 不能增加访问权限。

在 Codex 中依次调用 `validate_project(project_path)`、`run_project(project_path)`，
然后用返回的 job_id 调用 `get_job_status`。也可以用 `create_project(config)` 保存配置，
该工具要求资产使用绝对路径。`get_project_schema` 返回当前严格 JSON Schema。

- 输入用 `${inputs.model}` 引用；阶段结果用 `${stages.scale.model}` 引用。
  只能引用较早的阶段；拒绝循环、错误类型、未跟踪的输入路径和未知字段。
- marker 数据必须声明 m/mm 并与 TRC 相符；测力数据须声明 N、m、Nm。
  坐标的 inDegrees 必须明确。工具不猜测测力台的受力身体或列前缀。
- 原文件与输入在提交时指纹化，开始执行后复制到独立工作区；排队期间发生改变会拒绝运行。
- 一个项目最多 32 个输入、24 个阶段、256 MiB 输入。单个异步任务上限 600 秒。
  更长研究应拆成多个项目。API 和 CLI 版本都写入来源记录。

缓存存放在 `results/pipelines/cache`。键包含输入内容、求解参数、运行时和实现源码指纹，
读取时重新校验全部产物。更改阈值、标题或绘图配置可复用计算；更改输入/求解参数会使
相关阶段重新计算。`resume=false` 强制运行。缓存、journal 是长期研究记录；占用空间由用户管理。
Windows 字节锁避免两个服务同时写相同阶段，进程被取消后锁会自动释放。
temp 与 results 应位于同一磁盘，以便原子提交阶段缓存。

`cancel_job` 会终止进程树。普通分析仍是整体提交；项目任务特意保留已经提交的完整阶段，
以便下一次运行续跑。正在计算的阶段不会作为缓存结果使用。`get_project_run` 可读取部分运行记录。

质量检查必须显式配置：metric 对应阶段 metrics 中的点分隔字段，comparison=max/min，
limit、unit、severity 都会出现在报告中。缺少指标为 not_assessed；没有阈值也不会显示已通过。
ID 残余力只能由 residuals 中明确指定的 XYZ 列计算，体重分母使用该阶段模型质量和重力。
无重力时体重比不可评估。单位标签和阈值是研究者提供的解释，软件不会认定其医学有效性。

报告包含自带图像的 HTML、带相对图片路径的 Markdown 和完整 JSON。
HTML 无脚本或外部资源；所有输入文字转义。曲线需要在 plots 中指定列和单位标签。
每个阶段还保留原生结果、量化指标、输入/运行时/源码指纹以及复用记录。
