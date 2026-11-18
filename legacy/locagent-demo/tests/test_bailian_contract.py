import json
import unittest
from decimal import Decimal
from locagent_service import bailian_contract as b


class ContractTests(unittest.TestCase):

    def test_supplied_workspace_native_endpoint(self):
        host = 'https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com'
        self.assertEqual(b.endpoint('ws-8t0i3jte6m9op4ad', host), host + b.PATH)
        with self.assertRaises(ValueError):
            b.endpoint('ws-8t0i3jte6m9op4ad', host + '/compatible-mode/v1')

    def test_native_request_never_uses_compatible_fields(self):
        payload = b.request(['code question'], 'query')
        self.assertEqual(set(payload), {'model', 'input', 'parameters'})
        self.assertEqual(set(payload['input']), {'texts'})
        self.assertNotIn('dimensions', payload)
        self.assertNotIn('instruct', payload)
        self.assertEqual(payload['parameters']['text_type'], 'query')

    def test_endpoint_accepts_explicit_workspace(self):
        self.assertEqual(b.endpoint('example', 'https://example.cn-beijing.maas.aliyuncs.com'),
                         'https://example.cn-beijing.maas.aliyuncs.com' + b.PATH)

    def test_endpoint_rejects_alternatives(self):
        hosts = ['http://example.cn-beijing.maas.aliyuncs.com', 'https://127.0.0.1',
                 'https://dashscope.aliyuncs.com', 'https://example.cn-beijing.maas.aliyuncs.com/',
                 'https://example.cn-beijing.maas.aliyuncs.com:443',
                 'https://example.cn-beijing.maas.aliyuncs.com@evil.example',
                 'https://other.cn-beijing.maas.aliyuncs.com',
                 'https://example.cn-beijing.maas.aliyuncs.com.evil.example']
        for host in hosts:
            with self.subTest(host=host), self.assertRaises(ValueError):
                b.endpoint('example', host)
        for workspace in ['../a', '', 'a.b', 'A', '-a', 'a-', None]:
            with self.subTest(workspace=workspace), self.assertRaises(ValueError):
                b.endpoint(workspace, '')

    def test_request_roles(self):
        self.assertNotIn('instruct', b.request(['x'], 'document')['parameters'])
        self.assertEqual(b.request(['x'], 'query')['parameters']['instruct'], b.INSTRUCTION)
        self.assertEqual(b.request(['x'] * 20, 'query')['parameters']['dimension'], 1024)

    def test_request_limits(self):
        for texts in [[], ['x'] * 21, [''], ['  '], [True], ['x' * 16001], ['\ud800']]:
            with self.subTest(texts_type=type(texts)), self.assertRaises(ValueError):
                b.request(texts, 'query')
        with self.assertRaises(ValueError):
            b.request(['x'], 'mixed')

    def test_cache_roles_and_configuration_separated(self):
        base = b.cache_key('x', 'query', 'endpoint', 'chunker')
        for args in [('x', 'document', 'endpoint', 'chunker'),
                     ('x', 'query', 'another', 'chunker'),
                     ('x', 'query', 'endpoint', 'another'),
                     ('y', 'query', 'endpoint', 'chunker')]:
            self.assertNotEqual(base, b.cache_key(*args))
        self.assertEqual(base, b.cache_key('x', 'query', 'endpoint', 'chunker'))

    def test_conservative_budget_boundary(self):
        self.assertEqual(b.planned_cost(41, 20), Decimal('0.999424'))
        for args in [(42, 20), (1, 21), (True, 1), (1, False), (0, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                b.planned_cost(*args)

    def payload(self):
        return {'usage': {'total_tokens': 7, 'prompt_tokens': 7}, 'output': {
            'embeddings': [{'text_index': 1, 'embedding': [0., 1.] + [0.] * 1022},
                           {'text_index': 0, 'embedding': [2.] + [0.] * 1023}]}}

    def test_response_order_and_normalization(self):
        vectors, tokens = b.response(json.dumps(self.payload()).encode(), 2)
        self.assertEqual(tokens, 7)
        self.assertEqual(vectors[0][0], 1)
        self.assertEqual(vectors[1][1], 1)

    def test_invalid_response_retains_reservation_message(self):
        changes = [lambda d: d['usage'].update(total_tokens=True),
                   lambda d: d['usage'].update(total_tokens=999999),
                   lambda d: d['usage'].pop('prompt_tokens'),
                   lambda d: d.update(code='secret-looking-error'),
                   lambda d: d.update(model='wrong-model'),
                   lambda d: d['output']['embeddings'][0].update(text_index=0),
                   lambda d: d['output']['embeddings'][0].update(text_index=True),
                   lambda d: d['output']['embeddings'][0].update(embedding=[0.] * 1024),
                   lambda d: d['output']['embeddings'][0].update(embedding=[1.] * 1023),
                   lambda d: d['output']['embeddings'][0]['embedding'].__setitem__(0, float('nan')),
                   lambda d: d['output']['embeddings'][0]['embedding'].__setitem__(0, True)]
        for mutate in changes:
            data = self.payload()
            mutate(data)
            with self.assertRaisesRegex(ValueError, '^Invalid embedding response; reservation must remain held$'):
                b.response(json.dumps(data).encode(), 2)

    def test_duplicate_json_keys_and_oversize(self):
        for body in [b'{"usage":{},"usage":{}}', b'x' * (4 * 1024 * 1024 + 1), b'null', b'[]']:
            with self.assertRaises(ValueError):
                b.response(body, 2)


if __name__ == '__main__':
    unittest.main()
