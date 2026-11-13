# 来源与许可

本项目的协议包装、工作进程、文档句柄、状态检查、显式 COM 接口转换、几何描述、方向判断及工具接口在本地编写。

草图完全定义的“选择原点、FullyDefineSketch、回读约束状态”配方参考并改写自 MIT 项目 [SolidWorks Automation Skill](https://github.com/wzyn20051216/solidworks-automation-skill)，基于已下载提交 `6e20f6c065ba1c398c1f2a46d11b53355bc0189e` 的 `scripts/sw_sketch_quality.py`。完整 MIT 版权和许可声明保存在 `LICENSES/SolidWorks-Automation-Skill-MIT.txt`。

同时参考以下项目公开描述的架构思路，未直接复制其代码：

- [hjbaard/SolidWorks-MCP](https://github.com/hjbaard/SolidWorks-MCP)：单一 COM 线程、原生几何读回。
- [soheil-mp/solidworks-mcp](https://github.com/soheil-mp/solidworks-mcp)：按操作验证结果、区分离线和真机测试。

0.2.0 的配合、位置求解、干涉及材料/质量接口在本地编写。接口依据优先为本机 SOLIDWORKS 2025 官方 `sldworks.tlb`、`swconst.tlb`、`api/HelpViewer/sldworksapi/apihelpviewer.cab` 内的 API 帮助及官方在线文档：

- [2025 API 总览](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_solidworks_api.htm?format=P)
- [COM 接口层次与 QueryInterface](https://help.solidworks.com/2025/english/api/sldworksapiprogguide/GettingStarted/Understanding_the_SolidWorks_API_Class_Hierarchy.htm?id=1.3.1)
- [ICurve.GetLength3](https://help.solidworks.com/2025/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ICurve~GetLength3.html)
- [2025 文件加载错误位定义](https://help.solidworks.com/2025/english/api/swconst/SOLIDWORKS.Interop.swconst~SOLIDWORKS.Interop.swconst.swFileLoadError_e.html)
- [官方 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)

MCP SDK、pywin32、comtypes 等依赖的许可随各自安装包保留。SOLIDWORKS 本体、API 运行环境与商标属于其权利人，本项目不包含或分发其程序、接口二进制、类型库、许可证或安装文件。
