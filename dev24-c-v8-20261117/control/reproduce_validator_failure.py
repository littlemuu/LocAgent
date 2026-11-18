"""Synthetic, zero-API reproduction of frozen v8 fallback self-validation failure.
This is NOT an additional benchmark trial, retry or patch.
"""
import json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'frozen'))
from calibration.policy import EvidenceLedger,calibrate
snapshot=SimpleNamespace(files={
 'sympy/core/basic.py':'def exposed():\n    return 1\n',
 'sympy/ntheory/factor_.py':'def core():\n    return 1\n'})
ledger=EvidenceLedger(snapshot)
ledger.observe(dict(tool='read_file',arguments=dict(path='sympy/core/basic.py',start_line=1,end_line=2),
 result=dict(text='1: def exposed():\n2:     return 1\n',start_line=1,end_line=2,start_column=0,end_column=12,next_cursor=None)))
packet=dict(files=['sympy/core/basic.py'],entities=['sympy/core/basic.py:exposed'],answer='需要核验。')
try:
 calibrate(packet,ledger)
except AssertionError as error:
 assert 'R1_body_incomplete_unmarked:sympy/ntheory/factor_.py:core' in str(error)
 result=dict(status='reproduced',mode='synthetic local defect reproduction; NOT C retry or effectiveness result',API_calls=0,
  error_type='AssertionError',error=str(error),mechanism='file path segment core is mistaken for the unrelated function core during fallback validation',frozen_code_modified=False)
else:raise AssertionError('expected frozen defect not reproduced')
(ROOT/'delivery/validator-defect-reproduction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
