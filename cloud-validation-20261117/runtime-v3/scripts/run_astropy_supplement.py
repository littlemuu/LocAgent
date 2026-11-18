from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import ROOT,CONFIG,write_json
from locagent_e2e.driver import smoke,config_binding
assert CONFIG['formal_trial_authorized'] is False and CONFIG['smoke_max_cny']==6.85
out=ROOT/'verification/astropy-supplement'
assert not out.exists(), 'No automatic retries permitted'
write_json(ROOT/'verification/supplement-start.json',{'code_binding':config_binding(),'ids':['astropy__astropy-14182'],'formal_trial':False})
try:
 smoke(out,'/home/ubuntu/.config/locagent/smoke.env','docker',selected_smoke_ids=['astropy__astropy-14182'])
finally:
 Path('/home/ubuntu/.config/locagent/smoke.env').unlink(missing_ok=True)
