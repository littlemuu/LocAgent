"""Strict native response validation with bounded, allowlisted audit metadata.

Never retains headers, error messages, unknown field names or arbitrary strings.
Official API examples abbreviate vector arrays; tests use synthetic 1024-D data.
"""
import hashlib
import json
import math
import re

from locagent_service.bailian_contract import DIMENSIONS, MODEL, RESERVED_TOKENS_PER_INPUT


class ResponseValidationError(ValueError):
    def __init__(self, audit):
        self.audit = audit
        super().__init__('Invalid embedding response; reservation must remain held')


def safe_response_json(body):
    """Allowlisted JSON projection, not byte-identical raw body; hash raw separately.

    Preserve original numeric vectors (before normalization) and bounded usage,
    even if the full contract fails. Never turn this projection into a settled
    response without validation. No raw headers/error strings/unknown fields.
    """
    result={'audit_projection':'allowlisted-provider-json-v1'}
    if not isinstance(body,bytes) or len(body)>4*1024*1024:return result
    try:data=json.loads(body)
    except (ValueError,UnicodeError,RecursionError):return result
    if not isinstance(data,dict):return result
    if data.get('model')==MODEL:result['model']=MODEL
    ident=data.get('request_id')
    if isinstance(ident,str) and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',ident):result['request_id']=ident
    status=data.get('status_code')
    if (type(status) is int and 100<=status<=599) or status=='200':result['status_code']=status
    usage=data.get('usage')
    if isinstance(usage,dict):
        result['usage']={field:usage[field] for field in ('prompt_tokens','total_tokens')
                         if type(usage.get(field)) is int and 0<=usage[field]<=20*RESERVED_TOKENS_PER_INPUT}
    output=data.get('output');entries=output.get('embeddings') if isinstance(output,dict) else None
    if isinstance(entries,list) and len(entries)<=20:
        clean=[]
        for entry in entries:
            if not isinstance(entry,dict):continue
            row={};values=entry.get('embedding')
            for field in ('text_index','index'):
                index=entry.get(field)
                if type(index) is int and 0<=index<=20:row[field]=index
            try:
                if isinstance(values,list) and len(values)<=4096 and all(type(x) in (int,float) and math.isfinite(x) for x in values):row['embedding']=values
            except OverflowError:pass
            clean.append(row)
        result['output']={'embeddings':clean}
    return result


def typename(value):
    return {dict:'object',list:'array',str:'string',int:'integer',float:'number',bool:'boolean',type(None):'null'}.get(type(value),'unsupported')


def validate_response(body, count, http_status=200):
    audit={'version':1,'http_status':http_status if type(http_status) is int else None,
           'request_id':None,'request_id_present':False,'request_id_sha256':None,
           'model_present':False,'model_matches':None,'usage_present':False,
           'usage_fields':{},'vector_count':None,'dimension_distribution':{},
           'dimension_scan_truncated':False,'validation':'failed'}
    def fail(path, expected, value=None, *, missing=False, reason='invalid_field'):
        audit['failure']={'path':path,'expected':expected,
                          'actual_type':'missing' if missing else typename(value),'reason':reason}
        raise ResponseValidationError(audit)
    if type(count) is not int or not 1<=count<=20:
        fail('$expected_count','integer 1..20',count)
    if not isinstance(body,bytes) or len(body)>4*1024*1024:
        fail('$body','bytes <= 4 MiB',body,reason='body_limit_or_type')
    audit['response_sha256']=hashlib.sha256(body).hexdigest()
    def unique(pairs):
        result={}
        for name,value in pairs:
            if name in result:
                fail('$json','unique object keys',reason='duplicate_key')
            result[name]=value
        return result
    try:data=json.loads(body,object_pairs_hook=unique)
    except ResponseValidationError:raise
    except (ValueError,UnicodeError,RecursionError):fail('$json','valid bounded JSON',reason='invalid_json')
    if not isinstance(data,dict):fail('$','object',data)
    audit['request_id_present']='request_id' in data
    ident=data.get('request_id')
    if isinstance(ident,str):
        audit['request_id_sha256']=hashlib.sha256(ident.encode('utf-8',errors='replace')).hexdigest()
        # Only canonical UUID-shaped IDs are logged verbatim; unknown forms hashed.
        if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',ident):
            audit['request_id']=ident
    audit['model_present']='model' in data
    if audit['model_present']:audit['model_matches']=data['model']==MODEL
    audit['usage_present']='usage' in data
    usage=data.get('usage')
    if isinstance(usage,dict):
        for field in ('prompt_tokens','total_tokens'):
            audit['usage_fields'][field]={'present':field in usage,'type':typename(usage[field]) if field in usage else 'missing'}
    output=data.get('output')
    entries=output.get('embeddings') if isinstance(output,dict) else None
    if isinstance(entries,list):
        audit['vector_count']=len(entries)
        audit['dimension_scan_truncated']=len(entries)>20
        for entry in entries[:20]:
            values=entry.get('embedding') if isinstance(entry,dict) else None
            dimension=str(len(values)) if isinstance(values,list) else 'non_array'
            audit['dimension_distribution'][dimension]=audit['dimension_distribution'].get(dimension,0)+1
    if type(http_status) is not int or http_status!=200:fail('$http_status','integer 200',http_status)
    if data.get('code') not in (None,''):fail('code','empty or absent',data.get('code'))
    status=data.get('status_code',200)
    # Official field table says string; examples say integer. Permit only exact 200.
    if not ((type(status) is int and status==200) or (type(status) is str and status=='200')):
        fail('status_code','200 or "200" or absent',status)
    if 'model' in data and data['model']!=MODEL:fail('model','exact requested model or absent',data['model'])
    if not isinstance(usage,dict):fail('usage','object',usage,missing='usage' not in data)
    tokens=usage.get('total_tokens')
    if type(tokens) is not int or not 0<tokens<=count*RESERVED_TOKENS_PER_INPUT:
        fail('usage.total_tokens','positive bounded integer',tokens,missing='total_tokens' not in usage)
    prompt=usage.get('prompt_tokens')
    if type(prompt) is not int or prompt!=tokens:
        fail('usage.prompt_tokens','integer equal to total_tokens',prompt,missing='prompt_tokens' not in usage)
    if not isinstance(output,dict):fail('output','object',output,missing='output' not in data)
    if not isinstance(entries,list) or len(entries)!=count:
        fail('output.embeddings','array with expected count',entries,missing='embeddings' not in output)
    vectors={}
    for row,entry in enumerate(entries):
        prefix=f'output.embeddings[{row}]'
        if not isinstance(entry,dict):fail(prefix,'object',entry)
        # Explicit native response variants only; never infer index from row order.
        fields=[field for field in ('text_index','index') if field in entry]
        if not fields:
            fail(prefix+'.text_index','text_index or index integer',missing=True)
        for field in fields:
            if type(entry[field]) is not int or not 0<=entry[field]<count:
                fail(prefix+'.'+field,'in-range integer',entry[field])
        if len(fields)==2 and entry['text_index']!=entry['index']:
            fail(prefix+'.index','equal to text_index',entry['index'],reason='conflicting_indices')
        index=entry[fields[0]];values=entry.get('embedding')
        if index in vectors:
            fail(prefix+'.'+fields[0],'unique in-range integer',index,reason='duplicate_index')
        if not isinstance(values,list) or len(values)!=DIMENSIONS:
            fail(prefix+'.embedding','1024 numeric elements',values,missing='embedding' not in entry)
        try:
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in values):
                fail(prefix+'.embedding[]','finite numeric elements',reason='nonfinite_or_nonnumeric')
            norm=math.hypot(*values)
            if not math.isfinite(norm) or norm<=0:
                fail(prefix+'.embedding','finite nonzero norm',values,reason='invalid_norm')
        except OverflowError:fail(prefix+'.embedding[]','finite numeric elements',reason='numeric_overflow')
        vectors[index]=tuple(x/norm for x in values)
    if set(vectors)!=set(range(count)):
        fail('output.embeddings','complete explicit index coverage',reason='incomplete_indices')
    audit['index_adapter']='native-explicit-index-v1'
    audit['validation']='passed'
    audit['usage']={'prompt_tokens':prompt,'total_tokens':tokens}
    return tuple(vectors[i] for i in range(count)),tokens,audit
