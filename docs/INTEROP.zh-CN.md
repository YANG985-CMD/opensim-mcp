# SolidWorks、OpenSim、MATLAB 怎样协作

同一个 AI 客户端分别连接三个 MCP。每一步产生明确的文件和结构化结果，交给下一步处理。
当前实现采用离线文件交换，修改 CAD 或输入后重新导出和计算。

## 三个软件各做什么

| 软件 | 工作 | 交给下一步的内容 |
| --- | --- | --- |
| SolidWorks | 建零件、修改尺寸、检查装配、读取材料和质量参数 | 分件网格、质量、质心、惯量、明确的坐标与连接关系 |
| OpenSim | 检查人体模型、挂载装置、计算运动和受力 | 关节角度、净力矩、肌肉与关节载荷估计、HTML 三维动画 |
| MATLAB / Simulink | 准备信号、处理数据、控制器仿真、复核结果 | 带单位曲线、比较指标、参考轨迹与离线控制信号 |

```mermaid
flowchart LR
    C[Codex 或其他 MCP 客户端] <--> S[SolidWorks MCP]
    C <--> O[OpenSim MCP]
    C <--> M[官方 MATLAB MCP]
    S -->|几何和刚体参数| O
    M -->|轨迹和外载荷| O
    O -->|运动与受力表| M
    O --> V[HTML 三维结果]
    M -->|曲线与指标| V
```

## 1. 从 CAD 到人体穿戴

SolidWorks 导出 STL 等受支持网格，并回读质量、质心及惯量。
在 OpenSim 中明确装置挂在哪个身体框架、网格单位、局部变换、连接关节及关节轴。
上肢和下肢可使用同一套通用交接方式。

`convert_body_mass_properties` 将明确的源参数换成 SI 单位、质心参考和目标体坐标轴。
支持平行轴换算、惯性积符号与正交旋转检查。
用法见 [质量参数交接](../opensim-mcp/docs/MASS_PROPERTIES.zh-CN.md)。

## 2. 同一动作下比较两版设计

分别导出两版几何与质量参数，在同一人体、同一动作和同一外载荷下计算。
MATLAB 回读力矩或受力表，比较峰值、出现时刻和机械功。
HTML 工作台把三维姿态、曲线与当前选择关联到共同时间轴。

输入需要记录单位、坐标框架、惯量参考点、时间列和数据来源。
实际装置还需要可信的材料、连接与外载荷信息。

## 3. MATLAB 曲线与三维姿态一起查看

将外部 CSV、MOT 或 STO 信号按时间与组件绑定到 OpenSim 场景，点击曲线定位姿态，
导出原始采样与选择上下文。Simulink 控制结果也可作为明确的离线输入或比较信号。
帮助函数位于 `opensim-mcp/integrations/matlab/opensim_export_signals.m`，要求 R2023b+。

## 已完成的基础验证

本机的解析滑块算例使用 SolidWorks 2025、MATLAB R2024b 和 OpenSim 4.6。
40 × 20 × 10 mm 的 6061 样件质量为 21.6 g。
在 1 m/s² 加速度下，原生逆动力学受力增量为 0.0216 N，MATLAB 回算新增机械功为 0.0108 J，
与解析动能增量一致。该算例验证参数与结果的交接。人体实验、真实助力和硬件闭环各需独立验证。

v1.4.1 另有质量参数换算、保存重开回读与原生动能的解析验证，
详见 [发布记录](RELEASE-v1.4.1.json)。各项记录给出执行日期和验证范围。

## 可以直接交给 AI 的任务

> 请先核对三个 MCP 的版本与项目目录。读取我指定的 SolidWorks 装配，在副本中导出分件网格与刚体参数。先列出坐标、单位和人体关节映射，确认输入完整后进行 OpenSim 穿戴和同动作对比。最后由 MATLAB 回读结果，输出带单位的曲线和指标，并生成带统一时间轴的 HTML。

## 官方 MATLAB 入口

- [MATLAB MCP Server](https://github.com/matlab/matlab-mcp-server)
- [统一安装器](https://github.com/matlab/agentic-toolkit-installer)
- [MATLAB Agentic Toolkit](https://github.com/matlab/matlab-agentic-toolkit)
- [Simulink Agentic Toolkit](https://github.com/matlab/simulink-agentic-toolkit)
