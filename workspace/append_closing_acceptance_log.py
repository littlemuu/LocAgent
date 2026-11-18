from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_CLOSING_ACCEPTANCE.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜收尾修复版真实试跑验收完成'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended closing repair live acceptance.')
else:
    print('Entry already present; unchanged.')
