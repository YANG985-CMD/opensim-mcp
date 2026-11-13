"""Read-only process classification for the single-instance startup guard.

Windows may retain a process object after its final thread exits while another
process holds a handle. Such a record must not indefinitely block CAD startup.
Unknown, young, memory-bearing and threaded processes always block launch.
"""
import json
import math
import subprocess


def classify_processes(rows):
    if not isinstance(rows,list):
        raise ValueError('Process inventory must be a list')
    active=[];retained=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('Invalid process inventory row')
        def number(key):
            value=row.get(key)
            if isinstance(value,bool) or value is None:
                return None
            try:value=float(value)
            except (TypeError,ValueError):return None
            return value if math.isfinite(value) and value>=0 else None
        threads=number('threads');age=number('age_s')
        private=number('private_bytes');working=number('working_bytes')
        stale=(threads==0 and age is not None and age>=60
               and private is not None and private<=1024*1024
               and working is not None and working<=1024*1024)
        (retained if stale else active).append(row)
    return {'active_or_unknown':active,'retained_zero_thread_records':retained}


def read_process_inventory():
    command=r'''$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$probeNow=[DateTime]::UtcNow
$probeRows=@(Get-CimInstance Win32_Process -Filter "Name='SLDWORKS.exe'" | ForEach-Object {
  [pscustomobject]@{
    pid=$_.ProcessId
    threads=$_.ThreadCount
    private_bytes=$_.PrivatePageCount
    working_bytes=$_.WorkingSetSize
    age_s=$(if ($null -eq $_.CreationDate) {$null} else {($probeNow-$_.CreationDate.ToUniversalTime()).TotalSeconds})
  }
})
ConvertTo-Json -InputObject $probeRows -Compress'''
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
    if result.returncode:
        raise RuntimeError('Read-only Windows process inventory unavailable')
    return classify_processes(json.loads(result.stdout.decode('utf-8-sig')))
