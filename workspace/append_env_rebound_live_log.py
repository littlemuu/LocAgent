from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_ENV_REBOUND_LIVE.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜.env 换绑授权与首次真实自主 LocAgent 检索'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended env rebind and verified live retrieval result.')
else:
    print('Entry already present; unchanged.')
