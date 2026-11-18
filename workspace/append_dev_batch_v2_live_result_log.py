from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_DEV_BATCH_V2_LIVE_RESULT.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12｜修复版六题重跑：完整终答被正文硬上限拒绝'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended approved v2 batch result development log.')
else:
    print('Development log already contains this result; unchanged.')
