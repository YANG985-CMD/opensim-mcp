"""Non-executing Python checks and bounded, structured error locations."""
from __future__ import annotations

import ast
import re

from .core import InputError


def check_code(code:str,filename:str='<mcp>') -> dict:
    if not isinstance(code,str) or not code or len(code.encode('utf-8'))>1024*1024:
        raise InputError('Code must be nonempty and at most 1 MiB.')
    if len(filename)>500:raise InputError('Filename label is too long.')
    try:tree=ast.parse(code,filename)
    except SyntaxError as exc:
        return {'valid_syntax':False,'executed':False,'diagnostics':[{
            'severity':'error','kind':'syntax','message':exc.msg,'filename':filename,
            'line':exc.lineno,'column':exc.offset,'end_line':exc.end_lineno,
            'end_column':exc.end_offset,'source_line':(exc.text or '').rstrip()[:500]}], 'symbols':[]}
    aliases={'osim','opensim'};imported={};symbols=[];diagnostics=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for item in node.names:
                if item.name=='opensim':aliases.add(item.asname or 'opensim')
        if isinstance(node,ast.ImportFrom) and node.module=='opensim':
            for item in node.names:imported[item.asname or item.name]=item.name
    for node in ast.walk(tree):
        symbol=None
        if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in aliases:
            symbol=node.attr
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in imported:
            symbol=imported[node.func.id]
        if symbol and not symbol.startswith('_'):
            symbols.append({'symbol':symbol,'filename':filename,'line':node.lineno,'column':node.col_offset+1})
    return {'valid_syntax':True,'executed':False,'diagnostics':diagnostics,'symbols':symbols[:500],
            'scope':'Syntax and direct opensim symbols only; dynamic attributes, types and solver validity are not inferred.'}


def diagnose_error(error_text:str) -> dict:
    text=str(error_text)[-24000:]
    locations=[{'filename':m.group(1),'line':int(m.group(2))} for m in re.finditer(r'File "([^"]+)", line (\d+)',text)]
    hints=[]
    for pattern,hint in [
        (r'API_PYTHON|bindings not found','Check the separate API interpreter and its OpenSim/Python version.'),
        (r'DLL|WinError 126|ImportError','Keep wheel DLLs separate from the GUI SDK; verify x64 runtime dependencies.'),
        (r'socket|connectee|finalizeConnections','Inspect component socket paths and initialize the model before solving.'),
        (r'coordinate|inDegrees','Check complete coordinate labels, declared angle units and requested sample times.'),
        (r'converg|Infeasible|Restoration_Failed','Check model feasibility, bounds, scaling and actual solver diagnostics; increasing iterations alone is insufficient.'),
        (r'GUI bridge|heartbeat','Launch OpenSim with its startup plugin and check the configured bridge folder.'),
    ]:
        if re.search(pattern,text,re.I):hints.append(hint)
    return {'message':text,'locations':locations[-20:],'hints':hints,'executed':False}
