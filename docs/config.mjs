export function windowsPath(value) {
  const path = String(value).trim().replaceAll('\\', '/').replace(/\/+$/, '');
  if (!/^[A-Za-z]:\/[^<>:"|?*\u0000-\u001f]+$/.test(path)) {
    throw new Error('请填写完整的 Windows 路径，例如 E:/MCP/opensim-mcp。');
  }
  return path;
}

export function createConfig(values) {
  const opensim = windowsPath(values.opensim);
  const solidworks = windowsPath(values.solidworks);
  const matlab = windowsPath(values.matlab);
  const project = windowsPath(values.project);
  const runtime = windowsPath(values.runtime);
  if (!matlab.toLowerCase().endsWith('.exe')) {
    throw new Error('MATLAB MCP 路径需要指向官方服务的 .exe 文件。');
  }
  const quote = value => JSON.stringify(value);
  const roots = JSON.stringify([`${opensim}/examples`, project]);
  return `# 根据本机安装目录生成。合并前核对路径，每个服务块保留一份。
# 官方安装器生成的 MATLAB 扩展参数可继续保留在 matlab 条目中。
[mcp_servers.opensim_mcp]
command = ${quote(`${opensim}/.venv/Scripts/python.exe`)}
args = ["-B", "-m", "opensim_mcp.server"]
startup_timeout_sec = 120
tool_timeout_sec = 180

[mcp_servers.opensim_mcp.env]
OPENSIM_MCP_ALLOWED_ROOTS = ${quote(roots)}
OPENSIM_MCP_RESULTS_ROOT = ${quote(`${project}/results`)}
OPENSIM_MCP_TEMP_ROOT = ${quote(`${runtime}/opensim`)}
OPENSIM_MCP_API_PYTHON = ${quote(`${opensim}/.api46-venv/Scripts/python.exe`)}
OPENSIM_MCP_TOOL_BACKEND = "api"
OPENSIM_MCP_ENABLE_SCRIPTS = "0"
PYTHONDONTWRITEBYTECODE = "1"
TEMP = ${quote(`${runtime}/opensim`)}
TMP = ${quote(`${runtime}/opensim`)}

[mcp_servers.solidworks-mcp]
command = ${quote(`${solidworks}/.venv/Scripts/python.exe`)}
args = ["-B", "-u", ${quote(`${solidworks}/launch.py`)}]
cwd = ${quote(solidworks)}
enabled = true
startup_timeout_sec = 120
tool_timeout_sec = 150

[mcp_servers.matlab]
command = ${quote(matlab)}
args = ["--matlab-session-mode=auto", ${quote(`--log-folder=${runtime}/matlab`)}]
env_vars = ["WINDIR"]
startup_timeout_sec = 120
tool_timeout_sec = 180
`;
}

if (typeof document !== 'undefined') {
  const form = document.getElementById('config-form');
  const output = document.getElementById('config-output');
  const status = document.getElementById('config-status');
  const copy = document.getElementById('copy-config');
  const download = document.getElementById('download-config');

  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      output.value = createConfig(Object.fromEntries(new FormData(form)));
      copy.disabled = false;
      download.disabled = false;
      status.classList.remove('error');
      status.textContent = '已生成三个服务。核对路径并合并到 Codex config.toml，随后重新连接并自检。';
    } catch (error) {
      output.value = '';
      copy.disabled = true;
      download.disabled = true;
      status.classList.add('error');
      status.textContent = error.message;
    }
  });

  form.addEventListener('input', () => {
    copy.disabled = true;
    download.disabled = true;
    output.value = '';
    status.classList.remove('error');
    status.textContent = '路径已变化，请重新生成配置。';
  });

  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(output.value);
      status.textContent = '已复制配置。';
    } catch {
      output.focus();
      output.select();
      status.textContent = '请在已选中的文本上按 Ctrl+C，或下载配置片段。';
    }
  });

  download.addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([output.value], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'codex-three-mcp.toml';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = '已下载配置片段。将三个服务块合并到现有 Codex 配置。';
  });
}
