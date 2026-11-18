"""Behavior binding regressions mutate isolated source copies, never the checkout."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from phased_test_support import synthetic_cohorts
from locagent_service import phased
from locagent_service.engine_binding import behavior_hashes, PACKAGE_ROOTS
from locagent_service.sources import canonical, digest


class BehaviorBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original_root = phased.ROOT
        for name in set(behavior_hashes(phased.ROOT)):
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(phased.ROOT/name, target)
        (self.root/'locagent_service/phased_cohorts.json').write_bytes(canonical(synthetic_cohorts(self.root)))
        self.context = patch.object(phased, 'ROOT', self.root)
        self.context.start()
        self.addCleanup(self.context.stop)
        self.plan = phased.expected_plan('new20', 'binding-test')

    def assert_changed_rejected(self):
        self.assertNotEqual(digest(canonical(self.plan)),
                            digest(canonical(phased.expected_plan('new20', 'binding-test'))))
        with self.assertRaises(ValueError):
            phased.validate_plan(self.plan)
        with self.assertRaises(ValueError):
            phased.verify_sources(self.plan)

    def test_behavior_changes_across_execution_tools_output_index_and_scoring(self):
        cases = {
            'execution': 'util/localization_engine.py',
            'tool_schema': 'util/runtime/function_calling.py',
            'tool_parser': 'util/actions/action_parser.py',
            'output': 'plugins/location_tools/utils/result_format.py',
            'output_postprocess': 'util/process_output.py',
            'retrieval': 'plugins/location_tools/retriever/bm25_retriever.py',
            'index_split': 'repo_index/index/epic_split.py',
            'parser': 'repo_index/codeblocks/parser/python.py',
            'parser_query': 'repo_index/codeblocks/parser/queries/python.scm',
            'prompt': 'util/prompts/system_prompt.j2',
            'package_init': 'plugins/location_tools/__init__.py',
            'offline_guard': 'locagent_service/offline.py',
            'scoring': 'locagent_service/evaluate.py',
            'labels': 'locagent_service/label_mapping.py',
            'accounting': 'locagent_service/followup.py',
            'source_validation': 'locagent_service/sources.py',
            'source_preparation': 'locagent_service/prepare.py',
            'binding_policy': 'locagent_service/engine_binding.py',
            'dependency_declaration': 'requirements-runtime.txt',
        }
        for category, name in cases.items():
            with self.subTest(category=category):
                target = self.root/name
                original = target.read_bytes()
                target.write_bytes(b"raise RuntimeError('changed behavior')\n")
                self.assert_changed_rejected()
                target.write_bytes(original)

    def test_behavior_file_additions_deletions_and_resource_additions_rejected(self):
        for name in ['plugins/location_tools/new_tool.py',
                     'util/prompts/new_prompt.j2',
                     'repo_index/codeblocks/parser/queries/new.scm']:
            with self.subTest(added=name):
                target = self.root/name
                target.write_text('new behavior')
                self.assert_changed_rejected()
                target.unlink()
        target = self.root/'plugins/location_tools/utils/result_format.py'
        target.unlink()
        self.assert_changed_rejected()

    def test_links_in_behavior_packages_fail_closed(self):
        target = self.root/'plugins/alias.py'
        target.symlink_to(self.root/'util/localizer.py')
        with self.assertRaises(ValueError):
            phased.expected_plan('new20', 'binding-test')

    def test_credentials_caches_outputs_and_tests_are_excluded(self):
        before = phased.expected_plan('new20', 'binding-test')
        for name in ['.env', 'outputs/result.json', 'evaluation/loc_output/private.jsonl',
                     'tests/test_other.py', 'plugins/__pycache__/other.pyc',
                     'locagent_service/credential.json']:
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('SECRET_SENTINEL')
        self.assertEqual(before, phased.expected_plan('new20', 'binding-test'))
        self.assertNotIn('SECRET_SENTINEL', canonical(before).decode())

    def test_partial_legacy_source_binding_cannot_admit_new_plan(self):
        spec = deepcopy(phased.specs())
        spec['new20']['engine_hashes'].pop('plugins/location_tools/utils/result_format.py')
        with patch.object(phased, 'specs', return_value=spec):
            plan = phased.expected_plan('new20', 'incomplete-source')
            phased.validate_plan(plan)
            with self.assertRaisesRegex(ValueError, 'complete current behavior'):
                phased.verify_sources(plan)

    def test_all_static_project_imports_and_initializers_are_covered(self):
        covered = behavior_hashes(self.original_root)
        missing = set()
        for name in covered:
            if not name.endswith('.py'):
                continue
            module = name[:-3].replace('/', '.')
            package = module.rsplit('.', 1)[0]
            if module.endswith('.__init__'):
                package = module[:-9]
            for node in ast.walk(ast.parse((self.original_root/name).read_text())):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    prefix = (importlib.util.resolve_name('.'*node.level+(node.module or ''), package)
                              if node.level else (node.module or ''))
                    modules = [prefix] + [prefix+'.'+alias.name for alias in node.names]
                for imported in modules:
                    parts = imported.split('.')
                    for i in range(1, len(parts)+1):
                        relative = '/'.join(parts[:i])
                        for candidate in [relative+'.py', relative+'/__init__.py']:
                            if (self.original_root/candidate).is_file() and candidate not in covered:
                                missing.add(candidate)
        self.assertEqual(missing, set(), 'New project dependency needs an explicit binding rule')
        self.assertTrue(all(root+'/__init__.py' in covered
                            for root in PACKAGE_ROOTS if (self.original_root/root/'__init__.py').exists()))
