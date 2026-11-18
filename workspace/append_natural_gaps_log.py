from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_NATURAL_GAPS.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-14｜自然符号位置与跨文件缺口的离线验证'
if marker not in target.read_text():
 with target.open('a') as stream:stream.write(entry)
 print('Appended natural-state evidence, round-budget findings and limitations.')
else:print('Already recorded; unchanged.')
