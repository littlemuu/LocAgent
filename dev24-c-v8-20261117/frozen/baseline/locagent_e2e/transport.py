import json,time,stat,os
from pathlib import Path
from .common import CONFIG,encoded,write_json
class LiveTransport:
 def __init__(self,credential_file,ledger,output,context):
  from dotenv import dotenv_values
  p=Path(credential_file)
  if p.is_symlink() or stat.S_IMODE(p.stat().st_mode)!=0o600:raise PermissionError('credential_file_must_be_regular_mode0600')
  self.key=dotenv_values(p,interpolate=False).get('DEEPSEEK_API_KEY')
  if not self.key or any(c.isspace() for c in self.key):raise ValueError('invalid_credential')
  self.ledger=ledger;self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True);self.context=context;self.records=[]
 def exchange(self,payload):
  import httpx
  data=encoded(payload)
  if len(data)>CONFIG['max_serialized_request_bytes']:raise ValueError('serialized_request_budget')
  reservation=self.ledger.reserve(len(data),payload['max_tokens'],self.context);n=reservation['sequence']
  write_json(self.output/f'request-{n}.json',payload);start=time.monotonic()
  try:
   with httpx.Client(trust_env=False,follow_redirects=False,timeout=120) as client:
    with client.stream('POST',CONFIG['endpoint'],content=data,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key}) as response:
     body=bytearray()
     for part in response.iter_bytes():
      body.extend(part)
      if len(body)>131072:raise ValueError('response_size_exceeded')
     (self.output/f'response-{n}.json').write_bytes(body)
     if response.status_code!=200:raise RuntimeError('provider_http_'+str(response.status_code))
   raw=json.loads(body);receipt=self.ledger.settle(n,raw,time.monotonic()-start);self.records.append(receipt)
   write_json(self.output/f'receipt-{n}.json',receipt)
   if self.ledger.read()['stopped']:raise RuntimeError(self.ledger.read()['stopped'])
   return raw
  except Exception as e:
   self.ledger.stop('request_exception_'+type(e).__name__);raise
class ScriptedTransport:
 def __init__(self,responses):self.responses=iter(responses);self.records=[]
 def exchange(self,payload):
  raw=next(self.responses);self.records.append({'usage':raw.get('usage',{}),'actual_model':'scripted-not-live','charged_upper_microcny':0});return raw
