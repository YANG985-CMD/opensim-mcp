# Windows 11 复现与故障检查

v1.1 已在当前 Win11 x64 build 26200 的新目录中验证中文/空格路径、一键安装、真实
MCP/IK 和微型 Moco/IPOPT 求解。并非干净 OS/虚拟机；本机未找到 Windows Sandbox
或 Hyper-V 模块。当前为 Home 版本，不能声称执行了 Sandbox 测试。
官方说明：[Windows Sandbox 支持范围](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)。

## 安装与离线缓存

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-runtime' -WithTests
```

TempRoot/dependency-cache 保留下载的锁定依赖缓存；项目 runtimes 保留解释器。
首次联网安装后，可在同一项目和缓存根下：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-runtime' -Offline -Repair -SkipCodexRegistration
# 或
.\doctor.cmd -TempRoot 'E:\simulink\_codex_tmp\opensim-runtime' -Offline -Repair
```

- Offline 设置 uv 禁用网络及解释器下载；缓存/解释器不足会失败，不会悄悄联网。
- 这不是可携带的完整离线安装包。新机器无缓存时仍需首次联网，或未来独立制作离线包。
- 缓存有实际用途，清理 TempRoot 时需与正在使用的 GUI 队列/配置区分。
- 自检实际运行一个微型 CasADi/IPOPT 求解，不再仅以存在类名推断求解器可用。
- Windows wheel 的求解器查找固定到该 wheel 目录，避免其他 CAD/MATLAB 的 CasADi 路径干扰。
- 注册 Codex 和安装 GUI 插件安排在原生自检之后。失败保留现有 Codex 注册；手动
  SkipNativeSmoke 会跳过这些检查，应只用于明知原因的诊断。

## 已执行故障矩阵

| 情况 | 实测结果 |
| --- | --- |
| 新中文/空格目录 | 固定 Python/两环境安装、MCP/IK 和实际 Moco 求解通过 |
| 空缓存、离线首次安装 | 按预期失败，未改 Codex 配置 |
| 已缓存、Offline + Repair | 重装和原生检查通过 |
| 隔离环境缺 IPOPT 插件 DLL | doctor 报错；普通安装在注册前的求解器自检失败，旧配置逐字节保留 |
| 隔离环境移除 ezc3d | doctor 报错；离线修复后依赖/原生/源码检查通过 |

未故意卸载主机 Visual C++ 运行库或改系统 DLL。缺运行库的干净系统场景仍需独立虚拟机；
检测到无法导入/求解会报错，不冒充自动安装了系统运行库。

## 自动重现当前机器上的故障矩阵

已安装适配器的终端中，给出可信 ZIP 的明确 SHA256 与新的任务目录：

```powershell
.\.venv\Scripts\python.exe -B scripts\regression_installation.py `
  --archive 'E:\Downloads\opensim-mcp-v1.1.0-windows11.zip' `
  --sha256 '<可信发布页中的64位SHA256>' `
  --workdir 'E:\simulink\_codex_tmp\opensim-install-v11-new'
```

脚本只破坏/修复自己新建的环境，用假的 CODEX_HOME 检查配置保留，不触及真实 Codex。
任务目录必须不存在，含下载缓存、解释器和证据，完成后自行核对并清理。运行前保存
必要日志，不要把正在使用的生产环境作为测试目的地。

## 干净 Win11 虚拟机入口（本机未执行）

准备有明确来源与授权的 Win11 x64 虚拟机，恢复到新系统快照；不要通过修改主机版本
或绕过系统支持来冒充测试。在虚拟机里解压新的源码包，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-clean-win11.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-clean-win11'
```

没有 E 盘的虚拟机使用自己的独立测试盘符/目录。本机操作始终遵守本机 E 盘临时目录规范。
脚本记录系统/Python/uv 基线，拒绝已有 .venv，执行安装、适配器、原生 v1.0/v1.1、装配
和 doctor。它不能凭自身证明主机干净，需操作者保留 VM 快照来源和运行证据。
实际跑过之前，该项在验证记录中保持 false/未执行。
