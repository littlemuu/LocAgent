from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_CROSSFILE_RESULT.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜跨文件试跑收尾失败，检索组未运行'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended cross-file live failure inspection.')
else:
    print('Entry already present; unchanged.')
