from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_BLIND_REVIEW_V3.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12｜六题回答盲化AI评审完成并解盲'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended completed masked AI review development log.')
else:
    print('Development log already contains this review; unchanged.')
