# 源码与安装包发布

从 2026-11-13 起，OpenSim MCP 与 SolidWorks MCP 的源码统一在
[公开仓库](https://github.com/YANG985-CMD/opensim-mcp) 发布。
两套源码分别位于 `opensim-mcp/` 和 `solidworks-mcp/`。

核心项目采用 MIT 许可，第三方声明保留各项目原文件。
MATLAB MCP 与 Agentic Toolkit 从 MathWorks 官方仓库获取，官方许可适用于这些组件。

安装包保存在同一仓库的 Releases。编译安装包便于安装，源码可直接浏览和下载。
`scripts/build_installer.py` 从 OpenSim 子目录构建编译包，`scripts/package_source.py`
从该子目录构建源码包。各命令的临时输出应指定到独立任务目录。

仓库包含既有测试与发布验证记录。以各记录的执行日期、平台和范围为准。
原有 OpenSim GitHub Actions 模板保存在子项目 `.github/` 中。
