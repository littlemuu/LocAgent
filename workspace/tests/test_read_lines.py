import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from readonly_agent.core import Snapshot,FileTools,encoded
from readonly_agent.read_lines import source_lines


class ReadLinesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.make('a.py','first\n你好😀 second\nlast')
        self.make('empty.py','');self.make('blank.py','\n\n')
        self.snapshot=Snapshot(self.root,['a.py','empty.py','blank.py']);self.tools=FileTools(self.snapshot)
    def make(self,name,text):(self.root/name).write_text(text)
    def read(self,args,capacity=4096):return self.tools.respond('read_file',args,capacity)
    def test_first_last_and_inclusive_range(self):
        for n,text in [(1,'first'),(2,'你好😀 second'),(3,'last')]:
            r=self.read({'path':'a.py','start_line':n,'end_line':n})
            self.assertEqual(r['text'],f'{n}: {text}\n');self.assertEqual((r['start_line'],r['end_line']),(n,n))
            self.assertEqual((r['start_column'],r['end_column']),(0,len(text)));self.assertIsNone(r['next_cursor'])
        self.assertEqual(self.read({'path':'a.py','start_line':2})['text'],'2: 你好😀 second\n3: last\n')
    def test_default_whole_file_and_empty_file(self):
        r=self.read({'path':'empty.py'});self.assertEqual(r['text'],'');self.assertEqual(r['total_lines'],0)
        self.assertIsNone(r['start_line']);self.assertIsNone(r['end_line']);self.assertIsNone(r['next_cursor'])
        self.assertEqual(self.read({'path':'a.py'})['total_lines'],3)
    def test_empty_lines_and_final_newline(self):
        r=self.read({'path':'blank.py'});self.assertEqual(r['text'],'1: \n2: \n');self.assertEqual(r['end_line'],2)
        self.assertEqual(source_lines('a\n'),['a']);self.assertEqual(source_lines('a\n\n'),['a',''])
        self.assertEqual(source_lines('a'),['a'])
    def test_physical_lines_crlf_cr_and_unicode_separators(self):
        self.assertEqual(source_lines('a\r\nb\rc\n'),['a','b','c'])
        self.assertEqual(source_lines('a\u2028b\u0085c\n'),['a\u2028b\u0085c'])
    def test_bounds_and_types_fail_without_clamping(self):
        for bounds in ({'start_line':0},{'start_line':-1},{'start_line':True},{'start_line':'2'},
                       {'start_line':1.5},{'start_line':4},{'end_line':4},{'start_line':3,'end_line':2},
                       {'end_line':False},{'end_line':0}):
            with self.subTest(bounds=bounds),self.assertRaises(ValueError):self.read(dict(path='a.py',**bounds))
        with self.assertRaises(ValueError):self.read({'path':'empty.py','start_line':2})
        with self.assertRaises(ValueError):self.read({'path':'empty.py','end_line':1})
    def test_old_offsets_unknown_fields_and_forged_cursors_refused(self):
        for extra in ({'offset':0},{'offset':5969},{'cursor':5969},{'cursor':'5969'},
                      {'cursor':'rf1_'+'0'*64},{'unknown':None}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.read(dict(path='a.py',**extra))
    def test_path_safety_and_frozen_snapshot(self):
        for path in ('../a.py','/etc/passwd','.env','absent.py'):
            with self.assertRaises(ValueError):self.read({'path':path})
        (self.root/'a.py').write_text('changed')
        self.assertIn('first',self.read({'path':'a.py'})['text'])
    def large(self):
        self.make('long.py','你好😀"\\\t'*300+'\n'+'second\n'*20)
        return FileTools(Snapshot(self.root,['long.py']))
    def test_pagination_reconstructs_unicode_without_loss(self):
        tools=self.large();args={'path':'long.py'};parts={};previous=None;calls=0
        while True:
            r=tools.respond('read_file',args,300);self.assertIsNotNone(r)
            self.assertLessEqual(len(encoded(r)),300);calls+=1
            for i,line in enumerate(r['text'].split('\n')[:-1] if r['text'].endswith('\n') else r['text'].split('\n')):
                number,text=line.split(': ',1);number=int(number)
                expected_column=r['start_column'] if i==0 else 0
                self.assertEqual(len(parts.get(number,'')),expected_column)
                parts[number]=parts.get(number,'')+text
            if previous:self.assertEqual((r['start_line'],r['start_column']),previous)
            if r['next_cursor'] is None:break
            if r['text'].endswith('\n'):previous=(r['end_line']+1,0)
            else:previous=(r['end_line'],r['end_column'])
            args={'path':'long.py','cursor':r['next_cursor']}
            self.assertLess(calls,200)
        self.assertEqual([parts[i] for i in sorted(parts)],source_lines(tools.snapshot.files['long.py']))
    def test_cursor_repeat_is_stable_and_changing_range_is_rejected(self):
        tools=self.large();first=tools.respond('read_file',{'path':'long.py','start_line':1,'end_line':2},300)
        args={'path':'long.py','cursor':first['next_cursor']}
        a=tools.respond('read_file',args,300);b=tools.respond('read_file',args,300);self.assertEqual(a,b)
        with self.assertRaises(ValueError):tools.respond('read_file',dict(args,start_line=2),300)
        with self.assertRaises(ValueError):tools.respond('read_file',dict(args,end_line=3),300)
        with self.assertRaises(ValueError):self.read({'path':'a.py','cursor':first['next_cursor']})
        with self.assertRaises(ValueError):FileTools(tools.snapshot).respond('read_file',args,300)
    def test_cursor_is_bound_to_path(self):
        self.make('long.py','x'*1000);snapshot=Snapshot(self.root,['a.py','long.py']);tools=FileTools(snapshot)
        cursor=tools.respond('read_file',{'path':'long.py'},300)['next_cursor']
        with self.assertRaises(ValueError):tools.respond('read_file',{'path':'a.py','cursor':cursor},300)
    def test_complete_lines_preferred(self):
        self.make('many.py','abcdefgh\n'*100);tools=FileTools(Snapshot(self.root,['many.py']))
        r=tools.respond('read_file',{'path':'many.py'},300)
        self.assertTrue(r['text'].endswith('\n'));self.assertEqual(r['end_column'],8)
        next_page=tools.respond('read_file',{'path':'many.py','cursor':r['next_cursor']},300)
        self.assertEqual(next_page['start_line'],r['end_line']+1)
    def test_long_line_has_explicit_fragment_columns(self):
        tools=self.large();a=tools.respond('read_file',{'path':'long.py'},300)
        self.assertEqual((a['start_line'],a['end_line']),(1,1));self.assertEqual(a['start_column'],0)
        self.assertGreater(a['end_column'],0);self.assertFalse(a['text'].endswith('\n'))
        b=tools.respond('read_file',{'path':'long.py','cursor':a['next_cursor']},300)
        self.assertEqual(b['start_column'],a['end_column'])
    def test_budget_accounts_for_json_metadata_utf8_escaping(self):
        for capacity in range(1,500,7):
            r=self.read({'path':'a.py'},capacity)
            if r is not None:self.assertLessEqual(len(encoded(r)),capacity)
        whole=self.read({'path':'a.py'});size=len(encoded(whole))
        self.assertEqual(self.read({'path':'a.py'},size),whole)
        self.assertIsNone(self.read({'path':'empty.py'},1))
    def test_terminal_packet_can_fit_when_cursor_overhead_would_not(self):
        r=self.read({'path':'a.py','start_line':3});size=len(encoded(r))
        self.assertEqual(self.read({'path':'a.py','start_line':3},size),r)
    def test_search_line_numbers_agree_with_unicode_line_reader(self):
        self.make('unicode.py','x="a\u2028b"\nneedle\r\nlast')
        tools=FileTools(Snapshot(self.root,['unicode.py']))
        result=tools.respond('search_text',{'query':'needle','offset':0},4096)
        self.assertIn('unicode.py:2:',result['text'])
        self.assertEqual(tools.respond('read_file',{'path':'unicode.py','start_line':2,'end_line':2},4096)['text'],'2: needle\n')

if __name__=='__main__':unittest.main()
