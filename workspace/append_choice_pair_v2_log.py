from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_CHOICE_PAIR_V2.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜工具说明入口 summary 适配修复及授权复跑'
if marker not in target.read_text():
 with target.open('a') as stream:stream.write(entry)
 print('Appended summary adapter fix and paired rerun results.')
else:print('Already recorded; unchanged.')
