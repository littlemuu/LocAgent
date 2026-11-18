import json
import unittest
from locagent_service.bailian_response import validate_response,ResponseValidationError


def official_shape():
    # Official Flash native example envelope. Ellipsis vector replaced by a
    # synthetic finite 1024-D vector; not an actual provider response.
    return {'status_code':200,'request_id':'1ba94ac8-e058-99bc-9cc1-7fdb37940a46',
            'code':'','message':'','output':{'embeddings':[{'embedding':[1.]+[0.]*1023,'text_index':0}]},
            'usage':{'prompt_tokens':27,'total_tokens':27}}


class ResponseAuditTests(unittest.TestCase):
    def test_official_shape_without_model_and_http_envelope(self):
        data=official_shape()
        for strip in (False,True):
            if strip:
                for field in ('status_code','code','message'):data.pop(field)
            vectors,tokens,audit=validate_response(json.dumps(data).encode(),1)
            self.assertEqual(tokens,27);self.assertEqual(len(vectors[0]),1024)
            self.assertFalse(audit['model_present']);self.assertEqual(audit['request_id'],data['request_id'])

    def test_documented_string_status_only(self):
        data=official_shape();data['status_code']='200'
        self.assertEqual(validate_response(json.dumps(data).encode(),1)[1],27)
        for status in ('0200','200 OK',True,200.0,201):
            data['status_code']=status
            with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(data).encode(),1)
            self.assertEqual(caught.exception.audit['failure']['path'],'status_code')

    def test_missing_usage_still_rejected_with_metadata(self):
        data=official_shape();del data['usage']
        with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(data).encode(),1)
        audit=caught.exception.audit
        self.assertEqual(audit['failure']['path'],'usage');self.assertEqual(audit['failure']['actual_type'],'missing')
        self.assertFalse(audit['usage_present']);self.assertEqual(audit['dimension_distribution'],{'1024':1})

    def test_total_only_is_not_silently_accepted(self):
        data=official_shape();del data['usage']['prompt_tokens']
        with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(data).encode(),1)
        self.assertEqual(caught.exception.audit['failure']['path'],'usage.prompt_tokens')

    def test_wrong_model_dimension_and_index(self):
        for mutate,path in [(lambda d:d.update(model='wrong-secret-model'),'model'),
                            (lambda d:d['output']['embeddings'][0].update(embedding=[1.]*768),'output.embeddings[0].embedding'),
                            (lambda d:d['output']['embeddings'][0].update(text_index=2),'output.embeddings[0].text_index')]:
            data=official_shape();mutate(data)
            with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(data).encode(),1)
            self.assertEqual(caught.exception.audit['failure']['path'],path)
            self.assertNotIn('wrong-secret-model',json.dumps(caught.exception.audit))

    def test_redaction_unknown_strings_and_key_names(self):
        data=official_shape();data.update(code='synthetic-secret',message='synthetic-secret',request_id='sk-synthetic-secret',**{'synthetic-secret':{'Authorization':'synthetic-secret'}})
        with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(data).encode(),1)
        audit=caught.exception.audit
        self.assertIsNone(audit['request_id']);self.assertIsNotNone(audit['request_id_sha256'])
        self.assertNotIn('synthetic-secret',json.dumps(audit));self.assertNotIn('Authorization',json.dumps(audit))

    def test_http_error_metadata_without_body_echo(self):
        with self.assertRaises(ResponseValidationError) as caught:validate_response(json.dumps(official_shape()).encode(),1,401)
        self.assertEqual(caught.exception.audit['http_status'],401)

    def test_duplicate_key_does_not_leak_arbitrary_name(self):
        with self.assertRaises(ResponseValidationError) as caught:validate_response(b'{"secret-name":1,"secret-name":2}',1)
        self.assertEqual(caught.exception.audit['failure']['reason'],'duplicate_key')
        self.assertNotIn('secret-name',json.dumps(caught.exception.audit))

    def test_boolean_usage_nonfinite_and_zero_are_rejected(self):
        for mutate in [lambda d:d['usage'].update(total_tokens=True),lambda d:d['usage'].update(prompt_tokens='27'),
                       lambda d:d['output']['embeddings'][0].update(embedding=[float('nan')]*1024),
                       lambda d:d['output']['embeddings'][0].update(embedding=[0.]*1024)]:
            data=official_shape();mutate(data)
            with self.assertRaises(ResponseValidationError):validate_response(json.dumps(data).encode(),1)


if __name__=='__main__':unittest.main()
