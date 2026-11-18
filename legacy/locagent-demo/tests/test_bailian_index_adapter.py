import json
import unittest
from locagent_service.bailian_response import validate_response, ResponseValidationError, safe_response_json


def payload(rows):
    return json.dumps({'output':{'embeddings':rows},'usage':{'prompt_tokens':10,'total_tokens':10}}).encode()


def entry(i, field='index'):
    v=[0.]*1024;v[i]=1.
    return {field:i,'embedding':v}


class IndexAdapterTests(unittest.TestCase):
    def test_both_formats_reorder_by_explicit_index(self):
        for field in ('index','text_index'):
            vectors,_,_=validate_response(payload([entry(2,field),entry(0,field),entry(1,field)]),3)
            self.assertEqual([v.index(1.) for v in vectors],[0,1,2])

    def test_mixed_formats_and_consistent_dual_fields(self):
        rows=[entry(2),entry(0,'text_index'),dict(entry(1),text_index=1)]
        vectors,_,_=validate_response(payload(rows),3)
        self.assertEqual([v.index(1.) for v in vectors],[0,1,2])

    def test_reject_noninteger_and_out_of_range_in_either_field(self):
        for field in ('index','text_index'):
            for invalid in (True,False,0.0,'0',None,[],{},-1,1,2**100):
                with self.subTest(field=field,value=invalid):
                    row=entry(0,field);row[field]=invalid
                    with self.assertRaises(ResponseValidationError):validate_response(payload([row]),1)

    def test_dual_fields_never_mask_invalid_or_conflicting_field(self):
        for field in ('index','text_index'):
            for invalid in (True,False,0.0,'0',None,-1,1):
                with self.subTest(field=field,value=invalid):
                    row=dict(entry(0),text_index=0);row[field]=invalid
                    with self.assertRaises(ResponseValidationError):validate_response(payload([row]),1)
        with self.assertRaises(ResponseValidationError) as caught:
            validate_response(payload([dict(entry(0),text_index=1),entry(1)]),2)
        self.assertEqual(caught.exception.audit['failure']['reason'],'conflicting_indices')

    def test_missing_duplicate_or_incomplete_coverage_rejected(self):
        missing=entry(0);del missing['index']
        for rows,count in [([missing],1),([entry(0),entry(0)],2),
                           ([entry(0),entry(0,'text_index')],2),([entry(0)],2),
                           ([entry(0),entry(2)],2),([entry(0),entry(1)],1)]:
            with self.subTest(count=count):
                with self.assertRaises(ResponseValidationError):validate_response(payload(rows),count)

    def test_index_format_preserves_vector_and_usage_guards(self):
        for vector in ([1.]*768,[0.]*1024,[float('nan')]*1024,[float('inf')]*1024,[True]*1024):
            row=entry(0);row['embedding']=vector
            with self.assertRaises(ResponseValidationError):validate_response(payload([row]),1)
        for usage in ({},{'prompt_tokens':10,'total_tokens':True},{'prompt_tokens':9,'total_tokens':10}):
            data=json.loads(payload([entry(0)]));data['usage']=usage
            with self.assertRaises(ResponseValidationError):validate_response(json.dumps(data).encode(),1)

    def test_projection_preserves_both_explicit_indices(self):
        row=safe_response_json(payload([dict(entry(0),text_index=0)]))['output']['embeddings'][0]
        self.assertEqual(row['index'],0);self.assertEqual(row['text_index'],0)


if __name__=='__main__':unittest.main()
