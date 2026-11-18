"""Offline archive/admission/scoring regression; no paid provider or saved outputs."""
import io
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from locagent_service.source_archive import extract_snapshot
from locagent_service.sources import canonical, digest, file_hashes
from locagent_service.models import CreateTask, TaskRequest
from locagent_service.budget import LIVE_CONFIG
from locagent_service.evaluate import summarize

PNG = b'\x89PNG\r\n\x1a\n' + b'image fixture'
SOURCE = b'def render():\n    return 1\n'
SENTINEL = 'GOLD_ONLY_SENTINEL_981aaed6'


def archive(entries):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        for name,kind,payload in entries:
            item=tarfile.TarInfo(name);item.mode=0o644
            if kind=='file':
                item.size=len(payload);tar.addfile(item,io.BytesIO(payload))
            else:
                item.type={'link':tarfile.SYMTYPE,'hardlink':tarfile.LNKTYPE,
                           'fifo':tarfile.FIFOTYPE,'directory':tarfile.DIRTYPE}[kind]
                if kind in ('link','hardlink'):item.linkname=payload
                tar.addfile(item)
    return stream.getvalue()


def manifest_fixture(root, problem):
    root=Path(root);bundle=root/'bundle';bundle.mkdir(exist_ok=True)
    (bundle/'demo.py').write_bytes(SOURCE)
    value={'version':2,'bundle':'bundle','task':{'instance_id':'demo__demo-1',
           'repo':'demo/demo','base_commit':'a'*40,'problem_statement':problem},
           'config':dict(LIVE_CONFIG),'artifacts':file_hashes(bundle),'engine':{}}
    data=canonical(value);source='prepared-'+digest(data)
    (root/(source+'.json')).write_bytes(data)
    return source


class ArchiveTests(unittest.TestCase):
    def extract(self, entries, enabled=True):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'snapshot'
            audit=extract_snapshot(archive(entries),dest,exclude_verified_image_links=enabled)
            self.assertFalse(any(p.is_symlink() for p in dest.rglob('*')))
            self.assertEqual(audit['ordinary_python_files'],{
                n:digest(v) for n,k,v in entries if k=='file' and n.endswith('.py')})
            return audit

    def test_legal_parent_target_is_audited_and_python_preserved(self):
        audit=self.extract([('src/main.py','file',SOURCE),
                            ('theme/original/a.png','file',PNG),
                            ('theme/epub/static/a.png','link','../../original/a.png')])
        link=audit['excluded_links'][0]
        self.assertEqual(link['target'],'../../original/a.png')
        self.assertEqual(link['resolved_path'],'theme/original/a.png')
        self.assertEqual(link['git_mode'],'120000')
        self.assertEqual(link['target_sha256'],digest(PNG))
        self.assertTrue(audit['python_inventory_preserved'])

    def test_default_policy_still_rejects_links(self):
        with self.assertRaises(ValueError):
            self.extract([('a.png','file',PNG),('b.png','link','a.png')],False)

    def test_svg_is_inspected_without_xml_execution(self):
        svg=b'<?xml version="1.0"?><!DOCTYPE svg SYSTEM "https://no.invalid/a"><svg></svg>'
        audit=self.extract([('a.svg','file',svg),('b.svg','link','a.svg')])
        self.assertEqual(len(audit['excluded_links']),1)

    def test_escaping_absolute_and_windows_targets_rejected(self):
        for target in ['../../a.png','/a.png',r'..\a.png']:
            with self.subTest(target=target),self.assertRaises(ValueError):
                self.extract([('a.png','file',PNG),('dir/x.png','link',target)])

    def test_chain_cycle_and_dangling_links_rejected(self):
        cases=[[('a.png','link','b.png'),('b.png','link','c.png'),('c.png','file',PNG)],
               [('a.png','link','b.png'),('b.png','link','a.png')],
               [('a.png','link','absent.png')]]
        for entries in cases:
            with self.subTest(entries=entries),self.assertRaises(ValueError):self.extract(entries)

    def test_code_links_disguised_images_and_special_members_rejected(self):
        cases=[[('a.py','file',SOURCE),('b.py','link','a.py')],
               [('a.py','file',SOURCE),('b.png','link','a.py')],
               [('a.png','file',SOURCE),('b.png','link','a.png')],
               [('a.png','file',PNG),('b.png','hardlink','a.png')],
               [('a.png','fifo',None)]]
        for entries in cases:
            with self.subTest(entries=entries),self.assertRaises(ValueError):self.extract(entries)

    def test_member_paths_duplicates_and_non_directory_ancestors_rejected(self):
        cases=[[('../a.py','file',SOURCE)],[('/a.py','file',SOURCE)],
               [('a.py','file',SOURCE),('a.py','file',SOURCE)],
               [('folder','file',PNG),('folder/a.py','file',SOURCE)]]
        for entries in cases:
            with self.subTest(entries=entries),self.assertRaises(ValueError):self.extract(entries)

    def test_git_submodules_rejected_and_git_python_blobs_preserved(self):
        from locagent_service.source_archive import inspect_git_tree
        with self.assertRaises(ValueError):
            inspect_git_tree(b'160000 commit '+b'a'*40+b'\tmodule\0')
        oid=hashlib.sha1(b'blob '+str(len(SOURCE)).encode()+b'\0'+SOURCE).hexdigest()
        expected=inspect_git_tree(b'100644 blob '+oid.encode()+b'\tdemo.py\0')
        with tempfile.TemporaryDirectory() as tmp:
            audit=extract_snapshot(archive([('demo.py','file',SOURCE)]),Path(tmp)/'good',
                                   expected_python_blobs=expected)
            self.assertEqual(audit['git_python_blobs'],expected)
            with self.assertRaises(ValueError):
                extract_snapshot(archive([('demo.py','file',b'changed')]),Path(tmp)/'bad',
                                 expected_python_blobs=expected)
            with self.assertRaises(ValueError):
                extract_snapshot(archive([]),Path(tmp)/'missing',expected_python_blobs=expected)

    def test_nonempty_destination_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp);(dest/'keep').write_text('user')
            with self.assertRaises(ValueError):extract_snapshot(archive([('x.py','file',SOURCE)]),dest)
            self.assertEqual((dest/'keep').read_text(),'user')


class LongPreparedTests(unittest.TestCase):
    def request(self, source, problem):
        return CreateTask(source_id=source,problem_statement=problem,
                          options={'max_iterations':3},max_attempts=1)

    def test_ordinary_8000_and_8001_boundary(self):
        self.assertEqual(len(CreateTask(problem_statement='x'*8000).problem_statement),8000)
        with self.assertRaises(ValueError):CreateTask(problem_statement='x'*8001)

    def test_verified_prepared_8001_22778_32768_and_32769(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':tmp}):
            for n in [8001,22778,32768]:
                text='x'*n;source=manifest_fixture(tmp,text)
                self.assertEqual(self.request(source,text).problem_statement,text)
            text='x'*32769;source=manifest_fixture(tmp,text)
            with self.assertRaises(ValueError):self.request(source,text)

    def test_forged_prefix_manifest_tamper_and_artifact_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':tmp}):
            with self.assertRaises(ValueError):self.request('prepared-'+'f'*64,'x'*8001)
            text='x'*8001;source=manifest_fixture(tmp,text);path=Path(tmp)/(source+'.json')
            original=path.read_bytes();path.write_bytes(original+b' ')
            with self.assertRaises(ValueError):self.request(source,text)
            path.write_bytes(original);(Path(tmp)/'bundle/demo.py').write_bytes(b'changed')
            with self.assertRaises(ValueError):self.request(source,text)

    def test_exact_text_and_execution_policy_required(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':tmp}):
            text='x'*8001;source=manifest_fixture(tmp,text)
            with self.assertRaises(ValueError):self.request(source,text[:-1]+'y')
            with self.assertRaises(ValueError):
                CreateTask(source_id=source,problem_statement=text,options={'max_iterations':2},max_attempts=1)

    def test_storage_read_does_not_require_source_but_readmission_does(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':tmp}):
            text='x'*8001;source=manifest_fixture(tmp,text);payload=self.request(source,text).model_dump()
            (Path(tmp)/(source+'.json')).unlink()
            self.assertEqual(TaskRequest.model_validate(payload).problem_statement,text)
            with self.assertRaises(ValueError):CreateTask.model_validate(payload)


class ScoringTests(unittest.TestCase):
    def row(self, source, files, entities, reason='finished', status='completed'):
        return {'source_id':source,'suppress_repeats':False,'mode':'live','status':status,
                'result':{'found_files':files,'found_entities':entities,
                          'diagnostics':{'termination_reason':reason},'messages':[]}}

    def test_multitarget_recall_is_fraction_not_any_hit(self):
        plan={'sources':['a'],'arms':[False]}
        result=summarize(plan,[self.row('a',['one'],['one:f'])],
                         {'a':{'files':['one','two'],'entities':['one:f','two:g','two:h']}})
        m=result['arms']['false']['metrics']
        self.assertEqual(m['files_recall_at_1'],.5);self.assertAlmostEqual(m['entities_recall_at_1'],1/3)

    def test_fixed20_18_applicable_failures_missing_and_empty_truth(self):
        sources=[str(i) for i in range(20)]
        answers={s:{'files':['f'],'entities':['f:x'] if i<18 else []} for i,s in enumerate(sources)}
        plan={'sources':sources,'arms':[False,True],'function_applicable_sources':sources[:18]}
        records=[self.row('0',['f'],['f:x']),self.row('1',['f'],['f:x'],status='failed'),
                 self.row('18',['f'],[])]
        result=summarize(plan,records,answers)['arms']['false']
        self.assertEqual(result['metric_denominators'],{'files':20,'functions':18})
        self.assertEqual(result['metrics']['files_recall_at_1'],2/20)
        self.assertEqual(result['metrics']['entities_recall_at_1'],1/18)
        self.assertEqual(result['coverage_adjusted_metrics']['function_recall_at_1_full_cohort'],1/20)
        self.assertEqual(result['valid_finish_count'],2)
        self.assertEqual(result['valid_finish_rate'],2/20)
        self.assertEqual(result['function_not_applicable'],2)
        self.assertEqual(result['failed_or_missing'],18)

    def test_all_function_labels_empty_is_na_not_perfect_recall(self):
        result=summarize({'sources':['a'],'arms':[False]},[self.row('a',['f'],[])],
                         {'a':{'files':['f'],'entities':[]}})['arms']['false']
        self.assertIsNone(result['metrics']['entities_recall_at_3'])
        self.assertEqual(result['coverage_adjusted_metrics']['function_recall_at_3_full_cohort'],0)

    def test_declared_applicability_mismatch_and_empty_file_truth_fail(self):
        with self.assertRaises(ValueError):
            summarize({'sources':['a'],'arms':[False],'function_applicable_sources':[]},[],
                      {'a':{'files':['f'],'entities':['f:x']}})
        with self.assertRaises(ValueError):
            summarize({'sources':['a'],'arms':[False]},[],{'a':{'files':[],'entities':[]}})

    def test_constructor_target_is_not_removed_or_replaced_by_class(self):
        answer={'a':{'files':['f.py'],'entities':['f.py:A.__init__','f.py:A.method']}}
        result=summarize({'sources':['a'],'arms':[False]},
                         [self.row('a',['f.py'],['f.py:A','f.py:A.method'])],answer)['arms']['false']
        self.assertEqual(result['metrics']['entities_recall_at_3'],.5)
        self.assertEqual(answer['a']['entities'],['f.py:A.__init__','f.py:A.method'])

    def test_offline_results_never_expose_quality_metrics(self):
        row=self.row('a',['f'],[]);row['mode']='offline'
        result=summarize({'sources':['a'],'arms':[False]},[row],
                         {'a':{'files':['f'],'entities':[]}})['arms']['false']
        self.assertTrue(all(v is None for v in result['metrics'].values()))
        self.assertIsNone(result['valid_finish_rate'])


class LabelIsolationTests(unittest.TestCase):
    def test_prepare_and_provider_never_receive_scoring_fields(self):
        from contextlib import redirect_stdout
        from locagent_service.offline import offline_engine
        from locagent_service.prepare import prepare
        from locagent_service.sources import load_manifest,localize_prepared
        with offline_engine():
            import plugins.location_tools.retriever.bm25_retriever
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':str(Path(tmp)/'registry')}):
            root=Path(tmp);sample=root/'sample.json'
            sample.write_text(json.dumps({'instance_id':'demo__demo-1','repo':'demo/demo','base_commit':'a'*40,
                'problem_statement':'Locate rendering.','patch':SENTINEL,'test_patch':SENTINEL,
                'hints_text':SENTINEL,'FAIL_TO_PASS':[SENTINEL],'PASS_TO_PASS':[SENTINEL],'labels':SENTINEL}))
            (root/'scoring-only.json').write_text(SENTINEL)
            def local_git(cmd,**kw):
                if 'rev-parse' in cmd:return 'a'*40+'\n'
                if 'archive' in cmd:
                    self.assertEqual(cmd[-1], 'a'*40+'^{tree}')
                    return archive([('demo.py','file',SOURCE)])
                if 'ls-tree' in cmd:return b'100644 blob '+hashlib.sha1(b'blob '+str(len(SOURCE)).encode()+b'\0'+SOURCE).hexdigest().encode()+b'\tdemo.py\0'
                if 'freeze' in cmd:return b'local fixture environment\n'
                raise AssertionError(cmd)
            with offline_engine(),patch('locagent_service.prepare.subprocess.check_output',side_effect=local_git),redirect_stdout(io.StringIO()):
                source=prepare(root,sample,followup5=True,search_protocol='bounded-v1')
                manifest,bundle=load_manifest(source)
                self.assertNotIn(SENTINEL,json.dumps(manifest))
                for path in bundle.rglob('*'):
                    if path.is_file():self.assertNotIn(SENTINEL.encode(),path.read_bytes())
                from litellm import ModelResponse
                def provider(**kw):
                    self.assertNotIn(SENTINEL,json.dumps(kw))
                    return ModelResponse(model='offline',choices=[{'index':0,'finish_reason':'tool_calls',
                        'message':{'role':'assistant','content':None,'tool_calls':[{'id':'empty','type':'function',
                         'function':{'name':'finish','arguments':'{"files":[],"entities":[]}'}}]}}],
                        usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
                request=CreateTask(source_id=source,problem_statement='Locate rendering.',
                                   options={'max_iterations':3},max_attempts=1)
                self.assertNotIn(SENTINEL,json.dumps(request.model_dump(mode='json')))
                result=localize_prepared(request,provider)
                self.assertNotIn(SENTINEL,json.dumps(result.messages))
                self.assertEqual(result.diagnostics['termination_reason'],'finished')
