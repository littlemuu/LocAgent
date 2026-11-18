import hashlib,json,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from readonly_agent.core import Snapshot
from experiments.eval_preflight.body_index import build,load,chunks
from locagent_service.offline import offline_engine

class BodyIndexTests(unittest.TestCase):
    def test_persist_load_fidelity_and_tamper_rejection(self):
        with TemporaryDirectory() as td,offline_engine():
            root=Path(td);(root/'x.py').write_bytes(('\ufeffdef alpha():\r\n    return "snowflake tag 中文"\r\n'*60).encode())
            snapshot=Snapshot(root,['x.py']);directory=root/'index'
            att=build(snapshot,directory)
            h=hashlib.sha256((directory/'attestation.json').read_bytes()).hexdigest()
            retriever,restored=load(snapshot,directory,h)
            self.assertEqual(restored['chunks'],2)
            self.assertEqual(''.join(r['text'] for r in chunks(snapshot)),snapshot.files['x.py'])
            self.assertTrue(retriever.retrieve('snowflake'))
            with self.assertRaises(AssertionError):load(snapshot,directory,'0'*64)
            corpus=directory/'corpus.jsonl';corpus.write_bytes(corpus.read_bytes()+b'\n')
            with self.assertRaises(AssertionError):load(snapshot,directory,h)

    def test_empty_and_unicode_line_metadata(self):
        with TemporaryDirectory() as td:
            root=Path(td);(root/'empty.py').write_bytes(b'');(root/'u.py').write_bytes('a=1\r\n# 中文\n'.encode())
            rows=chunks(Snapshot(root,['empty.py','u.py']),1)
            self.assertEqual([r['metadata']['start_line'] for r in rows],[1,2])
            self.assertEqual(rows[-1]['text'],'# 中文\n')

if __name__=='__main__':unittest.main()
