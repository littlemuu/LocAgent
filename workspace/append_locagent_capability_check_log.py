from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_LOCAGENT_CAPABILITY_CHECK.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜原题与真实已见线索的 LocAgent 免费能力检查'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended offline LocAgent capability check log.')
else:print('Entry already present; unchanged.')
