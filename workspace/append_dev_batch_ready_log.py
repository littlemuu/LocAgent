from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_DEV_BATCH_READY.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜六题真实批量执行适配与离线验收'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended six-case live adapter readiness and offline acceptance.')
else:
    print('Entry already present; unchanged.')
