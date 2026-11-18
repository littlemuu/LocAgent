from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_FINAL_LENGTH_REPAIR.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12｜六题终答长度修复与离线验收'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended final-length repair and offline verification development log.')
else:
    print('Development log already contains this repair; unchanged.')
