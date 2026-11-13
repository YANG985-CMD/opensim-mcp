# 并排升级与回退

v0.8.1 起支持验证源码 ZIP、安装到新目录，再单独切换 Codex 的 opensim_mcp。
旧源码、旧解释器、结果、输入目录、GUI 安装和任意脚本设置保留。
首次从 v0.8.0 升级可先解压新版，用新版 manage_release.py 验证和切换。
升级功能需要已可信的源码和从可信渠道获得的 SHA256；哈希不能替代发布者身份。

```powershell
Set-Location 'E:\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\upgrade.ps1 `
  -Archive 'E:\Downloads\opensim-mcp-v1.1.0-windows11.zip' `
  -SHA256 '<从可信发布页取得的64位SHA256>' `
  -Destination 'E:\opensim-mcp-v1.1.0' `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -Activate
```

不加 -Activate 时只验证、解压并安装到新目录。检查通过后可再激活。
安装失败不改现有 Codex 注册；目标目录必须不存在。主验证路径为 wheel/API，
旧 SDK/CLI 配置拒绝自动切换，需要明确重新生成兼容配置。
v1.0 激活严格保留旧结果、临时和允许输入目录，不自动扩大文件访问权限。
如需使用新版 examples，请明确将新版 examples 路径加入配置。
新 API 使用新版隔离解释器；临时根保持原配置，因此 GUI 桥接入口可以继续使用。
服务启动后仍需显式进行 API/GUI 模型同步。

激活输出 record_file，持久记录保存在旧项目 state/updates，不随发布包分发。
关闭并重开 Codex 才会换到新版。回退时：

```powershell
.\scripts\rollback.ps1 -Record 'E:\opensim-mcp\state\updates\<id>.json'
```

回退只恢复本服务的配置，保留其他最新 Codex 设置。若激活后又手工改了本服务配置，
自动回退会拒绝覆盖；若旧解释器已删除也会拒绝。保留记录，按其中 previous_server
人工核对恢复。激活前日志已写好，突然断电可能需要用该日志核对配置；
不声称这是跨进程、文件和 GUI 的原子更新。

在没有目标 GitHub 仓库、干净 Win11 虚拟机或自托管运行器时，只记录本地真实测试。
已登录 GitHub 账号不等于已获准向任意仓库发布。

新版源码使用 Python 3.12，新增 ezc3d/VTK 锁定依赖。若旧版激活曾扩大输入目录，
或你主动改了目录，使用 reconfigure_gui_bridge 先预览再迁移桥接；v1 可原位重载，
旧桥接需保存工作后重启 GUI。GUI 配置不一致不会阻止 v1 的静态/API 工具启动。

v1.1 加入 GUI 原子状态检查，旧桥接写操作需要先保存工作再重开 GUI。计算 API 升级不要求升级 GUI 本体；当前 beta GUI 仍按实际核心报告。
