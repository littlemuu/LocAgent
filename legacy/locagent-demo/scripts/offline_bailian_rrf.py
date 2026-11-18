"""Independent offline reconstruction; never imports the live execution modules."""
from pathlib import Path
from importlib.metadata import version
import collections
import csv
import hashlib
import json
import math
import socket
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'docs/BAILIAN_RRF_OFFLINE_PLAN.json'
SOURCE=ROOT/'outputs/bailian-retrieval-20261016'
OUT=ROOT/'outputs/bailian-rrf-offline-20261016'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()


def entity_ranking(docs,scores,positive_only=False):
    if len(docs)!=len(scores):raise ValueError('Score membership mismatch')
    best={}
    for doc,score in zip(docs,scores):
        score=float(score)
        if not math.isfinite(score):raise ValueError('Nonfinite score')
        if positive_only and score<=0:continue
        entity=doc['entity'];best[entity]=max(best.get(entity,-math.inf),score)
    return sorted(best,key=lambda e:(-best[e],e)),best


def rrf(lexical,dense,k,bm25_weight=1,dense_weight=1,top_n_per_arm=None):
    if len(lexical)!=len(set(lexical)) or len(dense)!=len(set(dense)):raise ValueError('Entity lists must already be deduplicated')
    if k<=0 or min(bm25_weight,dense_weight)<=0 or (top_n_per_arm is not None and top_n_per_arm<1):raise ValueError('Invalid fixed configuration')
    scores={}
    for ranking,weight in ((lexical,bm25_weight),(dense,dense_weight)):
        for rank,entity in enumerate(ranking[:top_n_per_arm],1):scores[entity]=scores.get(entity,0)+weight/(k+rank)
    return sorted(scores,key=lambda e:(-scores[e],e)),scores


def measure(questions,rankings):
    per={};totals={k:0 for k in (1,3,5)}
    for q in questions:
        if len(q['relevant_entities'])!=1:raise ValueError('This frozen development set has one gold per query')
        seq=rankings[q['id']];gold=q['relevant_entities'][0]
        rank=seq.index(gold)+1 if gold in seq else None
        per[q['id']]={'gold_rank':rank,'candidates':len(seq)}
        for k in totals:
            hit=int(rank is not None and rank<=k);totals[k]+=hit
            per[q['id']][str(k)]={'hit':hit,'recall':hit}
    return {'per_query':per,'macro':{str(k):{'hit':n/len(questions),'recall':n/len(questions)} for k,n in totals.items()}}


def load_vectors(m,result):
    expected={('document',d['id']):d for d in m['documents']}|{('query',q['id']):q for q in m['questions']};vectors={};sources=[]
    for source in result['source_inventory']:
        folder=Path(source['source_folder']);index=source['request_index'];role=source['role'];ids=source['ids']
        if folder not in (SOURCE,ROOT/'outputs/bailian-mapping-controls-20261015') or folder.is_symlink():raise ValueError('Unexpected source')
        sm=json.loads((folder/'manifest.json').read_bytes());binding=json.loads((folder/f'response-{index:03d}.binding.json').read_bytes());raw=(folder/f'response-{index:03d}.body.bin').read_bytes()
        payload={'model':m['model'],'input':{'texts':[expected[(role,i)]['text'] for i in ids]},'parameters':m['document_parameters'] if role=='document' else m['parameters']}
        assert binding==source['binding'] and sha(canonical(sm))==binding['manifest_sha256'] and sha(raw)==binding['response_sha256'] and sha(canonical(payload))==binding['request_sha256']
        assert sm['endpoint']==m['endpoint'] and sm['model']==m['model'] and sm['dimensions']==1024
        with sqlite3.connect('file:'+str(folder/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
            row=db.execute('SELECT state,n,request_hash,response_hash,vectors FROM calls WHERE id=?',(index,)).fetchone()
        assert row[:4]==('settled',len(ids),binding['request_sha256'],binding['response_sha256'])
        entries=json.loads(raw)['output']['embeddings'];byindex={}
        assert len(entries)==len(ids)
        for entry in entries:
            indices=[entry[k] for k in ('index','text_index') if k in entry]
            assert indices and all(type(i) is int for i in indices) and len(set(indices))==1
            i=indices[0];assert i not in byindex and 0<=i<len(ids)
            value=entry['embedding'];assert len(value)==1024 and all(type(v) in (int,float) and math.isfinite(v) for v in value)
            norm=math.hypot(*value);assert norm>0;byindex[i]=[v/norm for v in value]
        assert json.loads(row[4])==[byindex[i] for i in range(len(ids))]
        for i,ident in enumerate(ids):
            key=(role,ident);assert key not in vectors;vectors[key]=byindex[i]
        sources.append({'role':role,'items':len(ids),'binding':binding})
    assert set(vectors)==set(expected)
    return vectors,sources


def main():
    def blocked(*a,**k):raise RuntimeError('Offline RRF analysis prohibits network')
    socket.socket.connect=blocked;socket.create_connection=blocked
    plan_raw=PLAN.read_bytes();plan=json.loads(plan_raw)
    expected=[('rrf60_equal',60,1,1,None),('rrf60_dense2',60,1,2,None),('rrf10_equal',10,1,1,None),('rrf60_top10',60,1,1,10)]
    assert [tuple(c[k] for k in ('name','k','bm25_weight','dense_weight','top_n_per_arm')) for c in plan['configurations']]==expected
    m=json.loads((SOURCE/'manifest.json').read_bytes());saved=json.loads((SOURCE/'results.json').read_bytes())
    assert sha(canonical(m))==plan['source_manifest_sha256']==saved['manifest_sha256']
    assert all(sha(Path(p).read_bytes())==digest for p,digest in m['protected_hashes'].items())
    assert all(sha((ROOT/p).read_bytes())==digest for p,digest in m['engine_files'].items())
    protected=[p for directory in (ROOT/'outputs').glob('bailian*') if directory!=OUT for p in ([directory] if directory.is_file() else directory.rglob('*')) if p.is_file()]
    protected+=[ROOT/p for p in m['engine_files']]+[Path('/home/lenovo/projects/LocAgent/README.md')]
    before={str(p):sha(p.read_bytes()) for p in protected}
    values,sources=load_vectors(m,saved)
    import bm25s
    import Stemmer
    assert m['package_versions']=={name:version(name) for name in m['package_versions']}
    docs=m['documents'];qs=m['questions'];stemmer=Stemmer.Stemmer('english')
    bm=bm25s.BM25(k1=1.5,b=.75,method='lucene')
    bm.index(bm25s.tokenize([d['text'] for d in docs],stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
    names=['bm25','dense']+[c['name'] for c in plan['configurations']];rankings={n:{} for n in names};scores={n:{} for n in names}
    for q in qs:
        ids,raw_scores=bm.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        ordered_scores=[0.]*len(docs)
        for i,score in zip(ids[0],raw_scores[0]):ordered_scores[int(i)]=float(score)
        lexical,ls=entity_ranking(docs,ordered_scores,True)
        dense,ds=entity_ranking(docs,[math.fsum(a*b for a,b in zip(values[('document',d['id'])],values[('query',q['id'])])) for d in docs])
        assert lexical==saved['retrieval']['rankings']['bm25'][q['id']]
        assert dense==saved['retrieval']['rankings']['dense'][q['id']]
        for name,ranking,score in [('bm25',lexical,ls),('dense',dense,ds)]:rankings[name][q['id']]=ranking;scores[name][q['id']]=score
        for config in plan['configurations']:
            opts={k:v for k,v in config.items() if k!='name'};ranking,score=rrf(lexical,dense,**opts)
            rankings[config['name']][q['id']]=ranking;scores[config['name']][q['id']]=score
        assert rankings['rrf60_equal'][q['id']]==saved['retrieval']['rankings']['hybrid'][q['id']]
    reports={name:measure(qs,rankings[name]) for name in names}
    assert before=={p:sha(Path(p).read_bytes()) for p in before}
    OUT.mkdir(mode=0o700)
    result={'plan':plan,'plan_sha256':sha(plan_raw),'analysis_script_sha256':sha(Path(__file__).read_bytes()),'sources':sources,
            'baseline_bm25_dense_rrf_rankings_match':True,'rankings':rankings,'scores':scores,'reports':reports,
            'protected_hashes':before,'original_evidence_unchanged':True,'network_requests':0,'development_set_exploration':True}
    (OUT/'comparison.json').write_bytes(canonical(result))
    (OUT/'plan.json').write_bytes(plan_raw)
    with (OUT/'per-query.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['query','configuration','gold_rank','candidates','hit_recall@1','hit_recall@3','hit_recall@5'])
        for q in qs:
            for name in names:
                row=reports[name]['per_query'][q['id']];writer.writerow([q['id'],name,row['gold_rank'],row['candidates'],*[row[str(k)]['hit'] for k in (1,3,5)]])
    print(json.dumps({'plan_sha256':result['plan_sha256'],'baseline_reconstruction':'all three arms match','metrics':{n:v['macro'] for n,v in reports.items()},'ranks':{q['id']:{n:reports[n]['per_query'][q['id']]['gold_rank'] for n in names} for q in qs},'top10_candidates':{q['id']:reports['rrf60_top10']['per_query'][q['id']]['candidates'] for q in qs},'protected_files':len(before)},indent=2))


if __name__=='__main__':main()
