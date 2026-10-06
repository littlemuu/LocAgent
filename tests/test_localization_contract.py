import unittest
from dataclasses import asdict

from util.localization_contract import LocalizationRequest


class LocalizationRequestTests(unittest.TestCase):
    def setUp(self):
        self.valid_values = {
            'instance_id': 'demo__demo-1',
            'repo': 'demo/demo',
            'base_commit': 'a' * 40,
            'problem_statement': 'Locate the function that renders a response.',
        }

    def test_accepts_nonempty_fields(self):
        request = LocalizationRequest(**self.valid_values)
        self.assertEqual(asdict(request), self.valid_values)

    def test_preserves_original_nonempty_strings(self):
        for field, value in self.valid_values.items():
            with self.subTest(field=field):
                values = self.valid_values.copy()
                values[field] = f' \t{value}\n '
                request = LocalizationRequest(**values)
                self.assertEqual(asdict(request), values)

    def test_rejects_empty_string_for_each_field(self):
        for field in self.valid_values:
            with self.subTest(field=field):
                values = self.valid_values.copy()
                values[field] = ''
                with self.assertRaisesRegex(
                    ValueError, rf'^{field} cannot be empty$',
                ):
                    LocalizationRequest(**values)

    def test_rejects_whitespace_only_for_each_field(self):
        for field in self.valid_values:
            with self.subTest(field=field):
                values = self.valid_values.copy()
                values[field] = ' \t\r\n '
                with self.assertRaisesRegex(
                    ValueError, rf'^{field} cannot be empty$',
                ):
                    LocalizationRequest(**values)


if __name__ == '__main__':
    unittest.main()
