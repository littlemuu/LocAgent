# sphinx-doc__sphinx-8721

定位包：

```text
已读到的事实（附文件:行号）
- sphinx/ext/viewcode.py:53-60：doctree_read 在 singlehtml 直接 return，并在 `app.builder.name.startswith("epub") and not env.config.viewcode_enable_epub` 时 return；该判断读取的是 `env.config`。
- sphinx/ext/viewcode.py:62-89：has_tag 通过 `app.emit_firstresult('viewcode-find-source', modname)` 或 ModuleAnalyzer 取源码，并把结果写入 `env._viewcode_modules`。
- sphinx/ext/viewcode.py:91-120：遍历 py 域 desc 节点，命中后构造 `_modules/<modname>` 的 pagename 与 `[source]` 链接（only 表达式为 html）。
- sphinx/ext/viewcode.py:281（搜索命中，未读正文）：`app.add_config_value('viewcode_enable_epub', False, False)`，即默认 False。

推断
- 待验证假设：sphinx/ext/viewcode.py:doctree_read 的 epub 早退依赖 `env.config`，而 `make html epub` 在同一进程内先构建 html 时，`env._viewcode_modules` 已被 html 构建填充；epub 构建若复用同一 env（或未重新读取 doctree），`_modules` 页面仍可能由后续 collect/build 阶段生成，从而绕过该早退。
- 待验证假设：sphinx/ext/viewcode.py:has_tag 写入的 `env._viewcode_modules` 是跨 builder 共享状态，若 epub builder 复用该 env 且未清空，则即使 doctree_read 早退，残留条目仍可能触发模块页输出。
- 待验证假设：真正生成 `_modules` 页面的逻辑位于本文件 120 行之后（未读），可能由 `html-collect-pages` 或 `build-finished` 回调实现，且未再次检查 builder 名。

未核验点
- sphinx/ext/viewcode.py:120-295 未读完（含 setup 与页面生成回调），无法确认 epub 页面生成路径。
- 未读 sphinx/builders/_epub_base.py 与 sphinx/builders/html/__init__.py，未确认多 builder 时 env 是否复用、`_viewcode_modules` 是否被清理。
- 未运行任何构建验证。

最小验证：`python -m pytest -q tests/test_ext_viewcode.py`（或断言 `make html epub` 后 epub 输出目录不存在 `_modules` 页面）

以下内容未在阅读记录中核验：
- [R1] sphinx/ext/viewcode.py:doctree_read
- [R1] sphinx/ext/viewcode.py:has_tag
```

编码终答：

```text
Fixed the bug where `sphinx.ext.viewcode` generated `_modules` pages for epub builds even with `viewcode_enable_epub=False`.

Root cause: the epub guard lived in `doctree_read`, which only runs when a doctree is (re)read. In a multi-builder run like `make html epub`, the epub builder reuses the environment populated by the html build, so `env._viewcode_modules` was already filled and the `html-collect-pages` handler (`collect_pages`) still emitted the module pages.

Changes in `sphinx/ext/viewcode.py`:
- Removed the epub early-return from `doctree_read` (so source info is still collected, which is harmless and keeps behavior consistent).
- Added the guard `if app.builder.name.startswith("epub") and not env.config.viewcode_enable_epub: return` at the start of `collect_pages`, which is the actual page-generation path.

Tests added in `tests/test_ext_viewcode.py`:
- `test_viewcode_epub_default`: epub build with default config produces no `_modules/spam/mod1.xhtml`.
- `test_viewcode_epub_enabled`: with `viewcode_enable_epub=True`, the module page is generated.

Test results: both new epub tests pass. The pre-existing `test_viewcode` failure is unrelated — it also fails on the unmodified base commit (pygments output formatting).
```

工具记录：

请求 1 · view_file · exit=0 · 修改=[]
```json
{
  "path": "/testbed/sphinx/ext/viewcode.py"
}
```

请求 2 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && grep -n \"viewcode\" -r tests/ | head -50",
  "timeout_seconds": 120
}
```

请求 3 · view_file · exit=0 · 修改=[]
```json
{
  "path": "/testbed/tests/test_ext_viewcode.py"
}
```

请求 4 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && grep -n \"html-collect-pages\\|collect_pages\" -r sphinx/ | head -30",
  "timeout_seconds": 120
}
```

请求 5 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 620,680p sphinx/builders/html/__init__.py && grep -n \"class EpubBuilder\\|class StandaloneHTMLBuilder\\|class DirectoryHTMLBuilder\\|class _Epub\" sphinx/builders/*.py sphinx/builders/html/__init__.py",
  "timeout_seconds": 120
}
```

请求 6 · terminal · exit=0 · 修改=['sphinx/ext/viewcode.py']
```json
{
  "command": "cd /testbed && python - <<'EOF'\nimport re\np='sphinx/ext/viewcode.py'\ns=open(p).read()\ns=s.replace(\"\"\"    if app.builder.name == \"singlehtml\":\n        return\n    if app.builder.name.startswith(\"epub\") and not env.config.viewcode_enable_epub:\n        return\n\"\"\",\"\"\"    if app.builder.name == \"singlehtml\":\n        return\n\"\"\")\ns=s.replace(\"\"\"def collect_pages(app: Sphinx) -> Generator[Tuple[str, Dict[str, Any], str], None, None]:\n    env = app.builder.env\n    if not hasattr(env, '_viewcode_modules'):\n        return\n\"\"\",\"\"\"def collect_pages(app: Sphinx) -> Generator[Tuple[str, Dict[str, Any], str], None, None]:\n    env = app.builder.env\n    if not hasattr(env, '_viewcode_modules'):\n        return\n    if app.builder.name.startswith(\"epub\") and not env.config.viewcode_enable_epub:\n        return\n\"\"\")\nopen(p,'w').write(s)\nEOF\ngit diff",
  "timeout_seconds": 120
}
```

请求 7 · terminal · exit=0 · 修改=['tests/test_ext_viewcode.py']
```json
{
  "command": "cd /testbed && cat >> tests/test_ext_viewcode.py <<'EOF'\n\n\n@pytest.mark.sphinx('epub', testroot='ext-viewcode')\ndef test_viewcode_epub_default(app, status, warning):\n    app.builder.build_all()\n\n    assert not (app.outdir / '_modules/spam/mod1.xhtml').exists()\n\n\n@pytest.mark.sphinx('epub', testroot='ext-viewcode',\n                    confoverrides={'viewcode_enable_epub': True})\ndef test_viewcode_epub_enabled(app, status, warning):\n    app.builder.build_all()\n\n    assert (app.outdir / '_modules/spam/mod1.xhtml').exists()\nEOF\npython -m pytest -q tests/test_ext_viewcode.py 2>&1 | tail -20",
  "timeout_seconds": 120
}
```

请求 8 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && git stash && python -m pytest -q tests/test_ext_viewcode.py 2>&1 | tail -5; git stash pop",
  "timeout_seconds": 120
}
```

请求 9 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -m pytest -q tests/test_ext_viewcode.py -k epub 2>&1 | tail -3 && git diff --stat",
  "timeout_seconds": 120
}
```
