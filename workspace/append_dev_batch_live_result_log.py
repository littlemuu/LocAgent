from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_DEV_BATCH_LIVE_RESULT.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12｜六题批准试跑：首题 finish 输出截断后停止'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended approved batch stopped-result development log.')
else:
    print('Development log already contains this result; unchanged.')
