# 肌肉路径查看

`export_model_animation` 现在默认导出肌肉路径，已有工具参数无需改变。模型必须先通过 `load_model` 加载；外形模型与动作数据仍须位于已经允许的目录。

例如，加载 `results/official-human-wearable-demo/human_wearable.osim`，再向 `export_model_animation` 传入相应 `walking.mot` 的绝对路径，以及同一模型的 `geometry_model_path`。返回结果提供 `html_file`、`scene_file` 和 `muscle_count`。打开 HTML 后可切换“肌肉路径”、调节显示粗细、播放及查看坐标曲线。

每帧从原生 OpenSim 的当前 GeometryPath 读取有效的肌肉路径，保留移动、条件附着点和绕行表面的采样位置。路径以地面坐标保存，与同帧骨骼姿态对应。红色管状粗细只用于显示，不代表真实肌肉体积、肌肉激活或肌肉力；没有进行新的动力学求解。当前示例的 54 条肌肉集中于下肢及腰部。

没有肌肉的模型仍可导出，相关显示控件会禁用。无法获得几何路径的 FunctionBasedPath 等肌肉会列入 `unavailable_muscles` 并给出警告，不会编造显示位置。动画最多 300 条肌肉、每条路径最多 2048 个点、所有显示帧合计最多 400000 个肌肉采样点；超限时减少显示帧或简化模型。原有文件大小和几何限制继续生效。

本机验证：Gait2354 加两件示例护具，73 帧各包含全部 54 条肌肉，21 个外形网格；新增单元检查覆盖绕行坐标变换、重合点、非有限坐标和采样上限。原生球面绕行样例另检查了旋转/平移身体上的端点位置和路径长度；网页检查了显示开关、粗细、时间轴和播放。验证记录见示例的 `validation.json`。

官方 API：[GeometryPath](https://opensim-org.github.io/opensim-moco-site/docs/1.1.0/html_user/classOpenSim_1_1GeometryPath.html)。

从 v1.2 起可绑定受力、激活和有来源的体积报告，详见 [外骨骼研究工作流](EXOSKELETON_STUDIES.zh-CN.md)。没有受力报告时仍采用统一颜色示意。
