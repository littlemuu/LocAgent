# sphinx-doc__sphinx-8595

定位包：

```text
已读到的事实（附文件:行号）
- sphinx/util/inspect.py:144-158：getall() 用 safe_getattr 取 __all__，为 None 时返回 None，否则校验为 list/tuple 且元素均为 str 后原样返回（空列表 [] 会原样返回，不报错）。
- sphinx/ext/autodoc/__init__.py:1015-1031：ModuleDocumenter.import_object 在未设置 ignore_module_all 时把 inspect.getall(self.object) 结果赋给 self.__all__；AttributeError/ValueError 仅告警。
- sphinx/ext/autodoc/__init__.py:989-992：__init__ 中 self.__all__ 初始为 None。
- sphinx/ext/autodoc/__init__.py:1074-1086：get_object_members 在 want_all 时用 `if not self.__all__:` 判断，空列表与 None 同为假值，于是走 `return True, list(members.values())` 分支，即把全部成员当作隐式成员返回；只有非空 __all__ 才把不在其中的成员标记 skipped。
- sphinx/ext/autodoc/__init__.py:1046-1072：get_module_members 用 dir(self.object) 收集全部成员，因此空 __all__ 时 foo/bar/baz 都会进入 members。
- sphinx/ext/autodoc/__init__.py:1100-1102：sort_members 同样以 `self.__all__` 真值判断是否按 __all__ 排序。

推断
- 待验证假设：根因在 sphinx/ext/autodoc/__init__.py:ModuleDocumenter.get_object_members 的 `if not self.__all__` 判断，它把“无 __all__（None）”与“空 __all__（[]）”混为一谈，导致空 __all__ 时返回 want_all=True 并输出全部成员。
- 待验证假设：修复方向是区分 None 与空序列（例如 `if self.__all__ is None:`），使空 __all__ 走 else 分支并把所有成员标记 skipped，从而不输出任何条目。
- 待验证假设：sphinx/ext/autodoc/__init__.py:ModuleDocumenter.sort_members 的 `self.__all__` 真值判断在空 __all__ 时退化为默认排序，但此时成员已全部 skipped，影响可能有限，需验证。

未核验点
- sphinx/ext/autodoc/__init__.py:ClassDocumenter.get_object_members 未读完（仅见 1621-1633），类级 __all__ 行为未核验。
- sphinx/ext/autodoc/importer.py:get_object_members 未读完（仅见 184-202、242-245），其成员收集细节未核验。
- sphinx/ext/autodoc/__init__.py 分页 cursor=rf1_71a3265cba1879f349994bc6e62a2736fb154626c3948fec04c9ac53499b6482 未续读（sort_members 之后）。
- 未追踪 Documenter.filter_members / document_members 调用链，未确认 skipped 成员是否确实被过滤。
- 未运行任何测试或构建验证。

最小验证：`python -m pytest -q tests/test_ext_autodoc.py -k module_all`（或断言：对含 `__all__ = []` 的模块调用 ModuleDocumenter.get_object_members(True) 返回的成员全部 skipped）。
```

编码终答：

```text
I fixed the bug and verified it.

**Root cause:** `ModuleDocumenter.get_object_members` used `if not self.__all__:`, which conflates "no `__all__`" (`None`) with "empty `__all__`" (`[]`). With an empty `__all__`, autodoc fell into the implicit-members branch and documented every module member.

**Changes:**
- `sphinx/ext/autodoc/__init__.py`
  - `get_object_members`: changed the check to `if self.__all__ is None:`, so an empty `__all__` now takes the explicit branch and marks all members as skipped (nothing is documented).
  - `sort_members`: changed `order == 'bysource' and self.__all__` to `... and self.__all__ is not None` for consistency (empty `__all__` is still a valid, explicit ordering).
- `tests/roots/test-ext-autodoc/target/empty_all.py`: new fixture module with `__all__ = []` and three documented functions.
- `tests/test_ext_autodoc.py`: added `test_autodoc_empty_module_all`, asserting no `function::` entries are emitted for that module.

**Tests:**
- New test plus `test_autodoc_ignore_module_all` and the `sort_by_all` tests pass.
- All other autodoc test modules (`autoattribute`, `autoclass`, `autodata`, `autofunction`, `configs`, `events`, `mock`, `private_members`) pass: 70 passed.
- `tests/test_ext_autodoc.py::test_autodoc` fails, but it fails identically on the unmodified base commit (pre-existing ANSI/terminal-related failure, unrelated to this change).
```

工具记录：

请求 1 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 980,1110p sphinx/ext/autodoc/__init__.py",
  "timeout_seconds": 120
}
```

请求 1 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && grep -n \"__all__\" -r sphinx/ext/autodoc/ sphinx/util/inspect.py",
  "timeout_seconds": 120
}
```

请求 2 · terminal · exit=0 · 修改=['sphinx/ext/autodoc/__init__.py']
```json
{
  "command": "cd /testbed && python - <<'EOF'\nimport re\np='sphinx/ext/autodoc/__init__.py'\ns=open(p).read()\ns=s.replace(\"\"\"            if not self.__all__:\n                # for implicit module members, check __module__ to avoid\"\"\",\"\"\"            if self.__all__ is None:\n                # for implicit module members, check __module__ to avoid\"\"\")\ns=s.replace(\"\"\"        if order == 'bysource' and self.__all__:\"\"\",\"\"\"        if order == 'bysource' and self.__all__ is not None:\"\"\")\nopen(p,'w').write(s)\nEOF\ngrep -n \"__all__ is\" sphinx/ext/autodoc/__init__.py",
  "timeout_seconds": 120
}
```

请求 3 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && grep -n \"module_all\\|__all__\" tests/test_ext_autodoc.py | head -40; ls tests/roots/test-ext-autodoc/target/ | head -50",
  "timeout_seconds": 120
}
```

请求 4 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 700,740p tests/test_ext_autodoc.py; cat tests/roots/test-ext-autodoc/target/sort_by_all.py",
  "timeout_seconds": 120
}
```

请求 5 · terminal · exit=0 · 修改=['tests/roots/test-ext-autodoc/target/empty_all.py', 'tests/test_ext_autodoc.py']
```json
{
  "command": "cd /testbed && cat > tests/roots/test-ext-autodoc/target/empty_all.py <<'EOF'\n__all__ = []\n\n\ndef foo():\n    \"\"\"docstring\"\"\"\n\n\ndef bar():\n    \"\"\"docstring\"\"\"\n\n\ndef baz():\n    \"\"\"docstring\"\"\"\nEOF\npython - <<'EOF'\np='tests/test_ext_autodoc.py'\ns=open(p).read()\nanchor=\"\"\"@pytest.mark.sphinx('html', testroot='ext-autodoc')\ndef test_autodoc_ignore_module_all(app):\"\"\"\nnew=\"\"\"@pytest.mark.sphinx('html', testroot='ext-autodoc')\ndef test_autodoc_empty_module_all(app):\n    options = {\"members\": None}\n    actual = do_autodoc(app, 'module', 'target.empty_all', options)\n    assert list(filter(lambda l: 'function::' in l, actual)) == []\n\n\n\"\"\" + anchor\ns=s.replace(anchor,new,1)\nopen(p,'w').write(s)\nEOF\npython -m pytest -q tests/test_ext_autodoc.py -k \"module_all or sort_by_all\" 2>&1 | tail -5",
  "timeout_seconds": 120
}
```

请求 6 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest -q tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py tests/test_ext_autodoc_autoclass.py tests/test_ext_autodoc_automodule.py 2>&1 | tail -3",
  "timeout_seconds": 120
}
```

请求 7 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest -q tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py tests/test_ext_autodoc_autoclass.py tests/test_ext_autodoc_automodule.py 2>&1 | tail -15",
  "timeout_seconds": 120
}
```

请求 8 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest -q tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py tests/test_ext_autodoc_autoclass.py tests/test_ext_autodoc_automodule.py 2>&1 | grep -E \"passed|failed|error\" | tail -5",
  "timeout_seconds": 120
}
```

请求 9 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest tests/test_ext_autodoc.py tests/test_ext_autodoc_configs.py tests/test_ext_autodoc_autoclass.py tests/test_ext_autodoc_automodule.py -p no:warnings 2>&1 | tail -5",
  "timeout_seconds": 120
}
```

请求 10 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && ls tests | grep autodoc; python -m pytest tests/test_ext_autodoc.py -p no:warnings 2>&1 | tail -3",
  "timeout_seconds": 120
}
```

请求 11 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && git stash -q && python -m pytest tests/test_ext_autodoc.py -p no:warnings -k \"test_autodoc and not \" 2>&1 | tail -3; git stash pop -q; git status --short",
  "timeout_seconds": 120
}
```

请求 12 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && git stash -q && python -m pytest tests/test_ext_autodoc.py -p no:warnings -k \"test_autodoc\" 2>&1 | tail -3; git stash pop -q; git status --short",
  "timeout_seconds": 120
}
```

请求 13 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest tests/test_ext_autodoc_autoattribute.py tests/test_ext_autodoc_autoclass.py tests/test_ext_autodoc_autodata.py tests/test_ext_autodoc_autofunction.py tests/test_ext_autodoc_configs.py tests/test_ext_autodoc_events.py tests/test_ext_autodoc_mock.py tests/test_ext_autodoc_private_members.py -p no:warnings 2>&1 | tail -3; git diff",
  "timeout_seconds": 120
}
```
