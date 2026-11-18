from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_EVIDENCE_STATES.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜多种信息状态的离线工具证据与成本对照'
if marker not in target.read_text():
 with target.open('a') as stream:stream.write(entry)
 print('Appended evidence-state investigation and limitations.')
else:print('Already recorded; unchanged.')
