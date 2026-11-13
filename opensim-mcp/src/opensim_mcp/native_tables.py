"""Normalize only round-off duplicate native output times, with explicit audit."""
import math
from pathlib import Path

def strict_native_times(filename,time_tolerance_s=5e-7,value_tolerance=1e-8):
    path=Path(filename);lines=path.read_text(encoding='utf-8-sig').splitlines()
    end=next(i for i,line in enumerate(lines) if line.strip().lower()=='endheader')
    body=[line for line in lines[end+1:] if line.strip()];labels=body[0].split();rows=[];removed=[]
    for index,line in enumerate(body[1:]):
        row=[float(x) for x in line.split()]
        if len(row)!=len(labels) or not all(math.isfinite(x) for x in row):raise ValueError('Invalid native time-series row.')
        if rows and row[0]<=rows[-1][0]:
            if abs(row[0]-rows[-1][0])>time_tolerance_s or max(abs(a-b) for a,b in zip(row[1:],rows[-1][1:]))>value_tolerance:
                raise ValueError('Conflicting/nonmonotonic native output cannot be silently repaired.')
            removed.append(dict(source_row_zero_based=index,time_s=row[0]));continue
        rows.append(row)
    if len(rows)<2:raise ValueError('Native output requires two distinct times.')
    if removed:
        header=[('nRows='+str(len(rows))) if line.lower().startswith('nrows=') else ('datarows '+str(len(rows))) if line.lower().startswith('datarows ') else line for line in lines[:end+1]]
        path.write_text('\n'.join(header)+'\n'+'\t'.join(labels)+'\n'+'\n'.join('\t'.join(format(v,'.17g') for v in row) for row in rows)+'\n',encoding='utf-8')
    return dict(file=path.name,removed_duplicate_rows=removed,time_tolerance_s=time_tolerance_s,value_tolerance=value_tolerance,
        policy='Only nonincreasing times within stated round-off tolerance with all numeric values matching within tolerance. No averaging, extrapolation or conflicting-row removal.')
