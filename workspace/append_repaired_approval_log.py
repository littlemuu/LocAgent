from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_REPAIRED_APPROVAL.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜修复版获准试跑，等待本地密钥输入'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended repaired-pilot approval and local terminal handoff.')
else:
    print('Entry already present; unchanged.')
