from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_DESCRIPTION_APPROVED.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜工具说明修订版试跑授权与启动检查'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended retrieval description approval preflight.')
else:
    print('Entry already present; unchanged.')
