from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_CLOSING_APPROVED.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜收尾修复版试跑授权与启动检查'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended approved closing repair preflight.')
else:
    print('Entry already present; unchanged.')
