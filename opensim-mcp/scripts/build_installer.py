"""Build a CPython 3.12 bytecode distribution, separate from the open source checkout.

Bytecode is not encryption. The Jython GUI bridge, installation scripts, browser
assets and MATLAB integration helper remain readable runtime integration files.
No complete Python source tree, tests, private state or third-party models ship.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,py_compile,re,shutil,sys,tempfile,tomllib,zipfile
from pathlib import Path

def digest(data):return hashlib.sha256(data).hexdigest()

PUBLIC_README='''# OpenSim MCP for Windows 11

Windows 11 x64 上供 Codex 使用的独立 OpenSim MCP，注册名 **opensim_mcp**。
当前版本 **v{version}**，**94 个工具**。这是独立项目，不是 OpenSim/MathWorks/OpenAI 官方产品。

支持模型检查和编辑、IK/ID/肌肉分析、缩放、关节反力、RRA/Moco、异步任务与保存点、
GUI 自动桥接、离线三维动画，以及通用 MATLAB/CAD 数据交换。上肢与下肢共用接口。
两套 MCP 的完整源码见 https://github.com/YANG985-CMD/opensim-mcp 。

## 安装

1. 从 [Releases](https://github.com/YANG985-CMD/opensim-mcp/releases/latest) 下载
   `opensim-mcp-v{version}-win11-installer.zip` 和对应 `.sha256`。
2. 用 PowerShell 的 `Get-FileHash <ZIP路径> -Algorithm SHA256` 对照校验和。
3. 解压到最终目录，例如 `E:\\opensim-mcp`，双击 **install.cmd**。
4. 等待安装、自检和 Codex 配置完成，然后重启 Codex。

首次安装需联网；无需预装 Python。安装器下载并校验依赖，在项目内创建两套独立环境。
默认关闭任意脚本执行，合并本服务配置并保存原配置备份。安装路径可含空格或中文。
OpenSim GUI 可选，需要用户另行安装；本包不捆绑或升级 GUI。

指定已有 GUI 与 E 盘临时目录：

```powershell
Set-Location 'E:\\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\install.ps1 `
  -TempRoot 'E:\\simulink\\_codex_tmp\\opensim-mcp-runtime' -OpenSimRoot 'E:\\OpenSim 4.6'
```

省略 `-OpenSimRoot` 则使用独立 API。加 `-SkipCodexRegistration` 仅生成配置供手动合并。
双击 **doctor.cmd** 自检；关闭 Codex 后运行 `doctor.cmd -Repair` 可修复锁定依赖。
同一目录先完成一次联网安装和缓存后，修复可加 `-Offline`。不要移动已安装的虚拟环境。

手动启动命令（标准输入输出 MCP，需要客户端连接）：

```powershell
. .\\scripts\\env.ps1 -TempRoot 'E:\\simulink\\_codex_tmp\\opensim-mcp-runtime'
.\\.venv\\Scripts\\python.exe -B -m opensim_mcp.server
```

## v1.4.1 质量参数换算

新增质量、质心和惯量的单位、参考点及坐标架换算，供 CAD 装置刚体参数导入。
支持平行轴变换、惯性积符号约定、旋转矩阵与惯量物理约束检查。
用法见 [质量参数说明](docs/MASS_PROPERTIES.zh-CN.md)。

## v1.4 通用可视化工作台

新增单/双场景工作台：同步时间轴与视角、点击组件联动高亮、距离/三点夹角、
坐标/外部信号/肌肉力与激活曲线对比，以及查看状态保存/恢复。
常用操作保持简洁，测量与显示设置按需展开。详见 [工作台说明](docs/WORKBENCH.zh-CN.md)。

## v1.3 通用可视化

三维姿态和外部曲线共用时间轴，点击曲线定位姿态，支持组件绑定、原始采样 CSV 和选择
上下文导出。MATLAB 导出帮助函数位于 `integrations/matlab`，要求 R2023b+。
SolidWorks 通过 STL/OBJ 网格接入，必须明确单位、父坐标架和变换；动力学另需明确质量、
质心、惯量与关节。当前为文件交换，修改数据/CAD 后重新导出，尚无后台实时共仿真。
详见 [跨软件联动说明](docs/VISUALIZATION_INTEROP.zh-CN.md)。

`examples/visualization-interop-demo.html` 是原创下肢模型、CAD 测试块和合成信号演示，
可直接离线打开。它不是实际装置贴合、实验测量或生理有效性验证。

## 版本与发行形式

该安装包的核心 Python 模块为 CPython 3.12 编译字节码，主运行组合为 Python 3.12.13 +
OpenSim 4.6 API；不支持替换为 Python 3.8 的旧 API。GUI 使用独立 Jython 桥接。
必要的安装脚本、GUI 桥接、网页和 MATLAB 帮助函数可读。字节码可被逆向，不能视为加密。
依赖版本见随包 lock 文件。包内不含用户模型、账号配置、参与者数据、MATLAB/SolidWorks
软件或 OpenSim GUI。第三方组件独立安装，遵循各自许可；见 THIRD_PARTY_NOTICES.md。

源码与发行包的执行验证数量见随 Release 提供的验证记录。发行包另行验证真实 MCP/IK、原生 Moco 自检、
可视化接口和文件完整性；具体执行记录随 Release 提供。干净 Windows 虚拟机与 GUI
生命周期测试不等同于本机安装验证。

## 更新

将新包解压到新的最终目录并完成自检后，再切换 Codex 配置。保留旧目录以便回退。
`scripts/upgrade.ps1` 支持明确 SHA256 的并排校验、安装和可选激活；不自动下载陌生来源。
不要把旧目录中的 `.venv`、`.api46-venv`、`runtimes` 或私有 `state` 上传到 GitHub。
'''

def transform_module(name,text):
    if name=='core.py':
        assert text.count('with_name("tool_runner.py")')==1 and text.count("with_name('tool_runner.py')")==1
        text=text.replace('with_name("tool_runner.py")','with_name("tool_runner.pyc")').replace("with_name('tool_runner.py')","with_name('tool_runner.pyc')")
    elif name=='session.py':
        assert text.count('with_name("worker.py")')==1
        text=text.replace('with_name("worker.py")','with_name("worker.pyc")')
    elif name=='pipeline.py':
        assert "parent.glob('*.py')" in text
        text=text.replace("parent.glob('*.py')","parent.glob('*.pyc')")
    elif name=='releases.py':
        text=text.replace("project/'scripts/register_codex.py'","project/('scripts/register_codex.py' if (project/'scripts/register_codex.py').is_file() else 'scripts/register_codex.pyc')")
        # Preserve source-release verification and add an explicit binary metadata path.
        before="    required={'install.cmd','scripts/install.ps1','pyproject.toml','src/opensim_mcp/__init__.py','config/codex.example.toml'}"
        assert before in text
        addition='''    if 'distribution.json' in files:
        distribution=strict_json(files['distribution.json'])
        required={'install.cmd','scripts/install.ps1','pyproject.toml','src/opensim_mcp/__init__.pyc','config/codex.example.toml'}
        if not required<=files.keys() or distribution.get('schema')!='opensim_bytecode_distribution_v1' or distribution.get('python')!='3.12':raise InputError('Invalid compiled distribution metadata.')
        version=tomllib.loads(files['pyproject.toml'].decode('utf-8'))['project']['version']
        if distribution.get('version')!=version or not re.fullmatch(r'\\d+\\.\\d+\\.\\d+',version):raise InputError('Compiled release version mismatch.')
        return {'valid':True,'version':version,'sha256':digest(raw),'files':len(files),'format':'cpython312-bytecode'},files
'''
        text=text.replace(before,addition+before)
    return text

def build(project,output,scratch):
    assert sys.version_info[:2]==(3,12),'Build using the pinned CPython 3.12 runtime.'
    version=tomllib.loads((project/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    output.mkdir(parents=True,exist_ok=True);scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='installer-build-',dir=scratch) as temporary:
        root=Path(temporary)/'opensim-mcp';root.mkdir()
        def put(name,data):
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data.encode('utf-8') if isinstance(data,str) else data)
        def copy(name):put(name,(project/name).read_bytes())
        for name in ['install.cmd','doctor.cmd','LICENSE','THIRD_PARTY_NOTICES.md','SECURITY.md','requirements.lock.txt','requirements-api46.lock.txt','config/codex.example.toml','scripts/env.ps1','scripts/print-codex-config.ps1','scripts/doctor.ps1','scripts/upgrade.ps1','scripts/rollback.ps1','gui-autobridge/install-autobridge.ps1','gui-autobridge/dist/org-opensim-mcp-autobridge.jar','integrations/matlab/opensim_export_signals.m']:
            copy(name)
        put('README.md',PUBLIC_README.format(version=version));put('README.zh-CN.md',PUBLIC_README.format(version=version))
        copy('docs/MASS_PROPERTIES.zh-CN.md')
        doc=(project/'docs/VISUALIZATION_INTEROP.zh-CN.md').read_text(encoding='utf-8').replace('smoke_v13.py','smoke_v13.pyc')
        put('docs/VISUALIZATION_INTEROP.zh-CN.md',doc)
        put('docs/WORKBENCH.zh-CN.md',(project/'docs/WORKBENCH.zh-CN.md').read_text(encoding='utf-8').replace('smoke_v14.py','smoke_v14.pyc'))
        put('pyproject.toml',f'[project]\nname = "opensim-mcp"\nversion = "{version}"\nrequires-python = ">=3.12,<3.13"\n')
        for file in (project/'examples').rglob('*'):
            if file.is_file() and file.suffix.lower() in {'.osim','.mot','.sto','.trc','.obj','.stl','.json','.c3d','.html'}:put(file.relative_to(project),file.read_bytes())
        for file in (project/'src/opensim_mcp/viewer_assets').rglob('*'):
            if file.is_file():put(file.relative_to(project),file.read_bytes())
        transformed=[]
        def compile_file(source,relative,text=None):
            raw=source.read_text(encoding='utf-8') if text is None else text
            stage=Path(temporary)/'compile'/relative;stage.parent.mkdir(parents=True,exist_ok=True);stage.write_text(raw,encoding='utf-8')
            dest=root/relative.with_suffix('.pyc');dest.parent.mkdir(parents=True,exist_ok=True)
            py_compile.compile(str(stage),cfile=str(dest),dfile=relative.as_posix(),doraise=True,optimize=0,invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        for file in (project/'src/opensim_mcp').glob('*.py'):
            relative=file.relative_to(project)
            if file.name=='gui_bridge.py':copy(relative);continue
            original=file.read_text(encoding='utf-8');text=transform_module(file.name,original)
            if text!=original:transformed.append(relative.as_posix())
            compile_file(file,relative,text)
        for name in ('register_codex.py','manage_release.py','smoke_mcp.py','smoke_v13.py','smoke_v14.py'):
            compile_file(project/'scripts'/name,Path('scripts')/name)
        compile_file(project/'scripts/install_runtime.py',Path('scripts/install_runtime.py'),'''import pathlib,sys,sysconfig
if sys.version_info[:2]!=(3,12):raise RuntimeError('Compiled runtime requires CPython 3.12')
source=pathlib.Path(sys.argv[1]).resolve()
if not (source/'opensim_mcp/__init__.pyc').is_file():raise RuntimeError('Compiled module tree is missing')
site=pathlib.Path(sysconfig.get_paths()['purelib'])
(site/'opensim_mcp_distribution.pth').write_text(str(source)+'\\n',encoding='utf-8')
info=site/('opensim_mcp-'+sys.argv[2]+'.dist-info');info.mkdir(exist_ok=True)
(info/'METADATA').write_text('Metadata-Version: 2.1\\nName: opensim-mcp\\nVersion: '+sys.argv[2]+'\\n',encoding='utf-8')
(info/'INSTALLER').write_text('opensim-mcp-installer\\n',encoding='utf-8')
''')
        install=(project/'scripts/install.ps1').read_text(encoding='utf-8')
        begin=install.index('    # The editable install uses');end=install.index('    $apiDir=',begin)
        install=install[:begin]+'''    # Install the compiled application directory without a source build backend.
    $applicationSource=Join-Path $projectDir 'src'
    $distribution=Get-Content -LiteralPath (Join-Path $projectDir 'distribution.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    & $server -B (Join-Path $PSScriptRoot 'install_runtime.pyc') $applicationSource $distribution.version
    if ($LASTEXITCODE -ne 0) { throw 'Compiled adapter registration failed.' }
''' +install[end:]
        # The distributor intentionally does not include tests/source build tooling.
        install=install.replace("    $lock=if ($WithTests) {'requirements-test.lock.txt'} else {'requirements.lock.txt'}","    if ($WithTests) { throw 'Developer tests are maintained in the source checkout; use the included native self-checks.' }\n    $lock='requirements.lock.txt'")
        for old,new in [('smoke_mcp.py','smoke_mcp.pyc'),('tool_runner.py','tool_runner.pyc'),('register_codex.py','register_codex.pyc')]:install=install.replace(old,new)
        put('scripts/install.ps1',install.replace('\n','\r\n'))
        for name in ('upgrade.ps1','rollback.ps1'):
            value=(project/'scripts'/name).read_text(encoding='utf-8').replace('manage_release.py','manage_release.pyc');put('scripts/'+name,value.replace('\n','\r\n'))
        metadata=dict(schema='opensim_bytecode_distribution_v1',version=version,python='3.12',python_magic=importlib.util.MAGIC_NUMBER.hex(),platform='Windows 11 x64',format='CPython bytecode; not encryption',source_revision='source-sha256 manifest',packaging_transforms=transformed,readable_integration_files=['src/opensim_mcp/gui_bridge.py','scripts/*.ps1','viewer_assets','integrations/matlab/opensim_export_signals.m'],legacy_python38_supported=False)
        put('distribution.json',json.dumps(metadata,indent=2)+'\n')
        files=sorted(p for p in root.rglob('*') if p.is_file());assert [p.relative_to(root).as_posix() for p in files if p.suffix=='.py']==['src/opensim_mcp/gui_bridge.py']
        assert not any(p.name in {'config.toml','identity.json'} or '.local.' in p.name for p in files)
        for file in files:
            if file.suffix=='.pyc':assert file.read_bytes()[:4]==importlib.util.MAGIC_NUMBER
        hashes={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in files}
        put('validation/source-sha256.json',json.dumps(hashes,indent=2)+'\n');files.append(root/'validation/source-sha256.json')
        archive=output/f'opensim-mcp-v{version}-win11-installer.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for file in sorted(files):z.write(file,'opensim-mcp/'+file.relative_to(root).as_posix())
        with zipfile.ZipFile(archive) as z:assert z.testzip() is None
        sha=digest(archive.read_bytes());archive.with_suffix('.zip.sha256').write_text(sha+'  '+archive.name+'\n',encoding='utf-8')
        result=dict(version=version,archive=str(archive),sha256=sha,files=len(files),python_source_files=['src/opensim_mcp/gui_bridge.py'],compiled_modules=sum(p.suffix=='.pyc' for p in files),full_source_included=False,not_encryption=True)
        print(json.dumps(result));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--temp-root',type=Path,required=True);parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    build(args.project.resolve(),args.output.resolve(),args.temp_root.resolve())
