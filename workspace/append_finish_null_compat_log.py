from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_FINISH_NULL_COMPAT.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜SQLGlot 已知空扩展字段最小兼容：仅离线'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended offline finish null compatibility development log.')
else:
    print('Development log already contains this entry; unchanged.')
