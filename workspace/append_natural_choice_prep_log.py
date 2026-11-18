from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_NATURAL_CHOICE_PREP.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-14｜SQLGlot 自然检查点工具选择方案准备（未授权启动）'
if marker not in target.read_text():
 with target.open('a') as stream:stream.write(entry)
 print('Appended unapproved natural checkpoint experiment preparation.')
else:print('Already recorded; unchanged.')
