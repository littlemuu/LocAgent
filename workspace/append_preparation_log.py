from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_PREPARATION.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 UTC｜OpenHands + DeepSeek 真实调用准备与前后端复用审查'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended preparation and integration review entry.')
else:
    print('Entry already present; unchanged.')
