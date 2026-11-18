"""Attest v4 compatibility without rewriting the v3 build provenance."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'engine_adaptation/v4';OLD=ROOT/'engine_adaptation/v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def save(p,x):
 with p.open('xb') as f:f.write(enc(x))
def main():
 result=json.loads((OUT/'full-validation-results.json').read_text());manifest=json.loads((OUT/'manifest.json').read_text())
 previous=json.loads((OLD/'manifest.json').read_text())
 assert result['ready']==130 and not result['failed'] and len(result['rows'])==130
 assert {r['id'] for r in result['rows']}=={r['id'] for r in manifest['plans']}
 assert all(sha(OUT/'engine'/n)==h for n,h in manifest['engine']['files'].items())
 assert all(sha(ROOT/n)==h for n,h in manifest['harness_files'].items())
 assert sha(OUT/'previous-locagent.py.txt')==previous['harness_files']['readonly_agent/locagent.py']
 assert all(sha(OLD/'engine'/n)==h for n,h in previous['engine']['files'].items())
 changed=[n for n,h in previous['harness_files'].items() if sha(ROOT/n)!=h]
 assert changed==['readonly_agent/locagent.py'] or set(changed)=={'readonly_agent/locagent.py'}
 rows=[];old_artifacts=0
 for r in result['rows']:
  p=json.loads((OUT/'plans'/(r['id']+'.json')).read_text());h=p.pop('plan_hash')
  assert hashlib.sha256(enc(p)).hexdigest()==h==r['plan_hash']
  assert r['result']['snapshot']==hashlib.sha256(enc(p['sources'])).hexdigest()
  assert r['result']['persisted_corpus_and_query_equal']
  for n,hsh in r['artifacts'].items():assert sha(OUT/'validation'/r['id']/n)==hsh
  prior=json.loads((OLD/'indexes'/(r['id']+'.attestation.json')).read_text())
  for n,hsh in prior['artifacts'].items():assert sha(OLD/'indexes'/r['id']/n)==hsh;old_artifacts+=1
  reused=r['result']['mode']=='revalidated_v3_index'
  rows.append({'id':r['id'],'plan_hash':h,'technical_status':'ready','validation_mode':r['result']['mode'],
    'index_directory':r['result']['index_directory'],'index_build_engine_hash':previous['engine']['hash'] if reused else manifest['engine']['hash'],
    'validated_engine_hash':manifest['engine']['hash'],'source_snapshot':r['result']['snapshot'],
    'index_attestation':str(OLD/'indexes'/(r['id']+'.attestation.json')) if reused else str(OUT/'validation'/(r['id']+'.attestation.json')),
    'validation_attestation':str(OUT/'validation'/(r['id']+'.attestation.json')),
    'semantic_review':'pending','exposure_review':'pending','scoring_review':'pending'})
 assert sum(r['validation_mode']=='rebuilt_v4' for r in rows)==2
 assert json.loads((OUT/'boundary-results.json').read_text())['status']=='passed'
 for f in ['unit-tests.txt','existing-integration.txt']:assert '\nOK\n' in (OUT/f).read_text()
 save(OUT/'adapted-manifest.json',{'version':4,'engine':manifest['engine'],'harness_files':manifest['harness_files'],
  'cases':rows,'technical_ready':130,'rebuilt':2,'revalidated_previous_indexes':128,'model_calls':0,'live_authorization':False,'cache_in_live_runner':False})
 save(OUT/'acceptance.json',{'status':'passed','technical_ready':130,'fresh_builds':2,'revalidated_v3_indexes':128,
  'old_index_artifact_hashes_verified':old_artifacts,'changed_harness_files':changed,'unit_tests':45,'existing_integration_tests':4,
  'engine_hash':manifest['engine']['hash'],'model_calls':0,'semantic_exposure_scoring_review':'pending','live_authorization':False})
 report=f'''# UTF-8 BOM 修复及 130 题技术状态核对

2026-11-14。**两道 MSAL 题已通过，v4 清单的 130/130 题均通过本轮技术验收。** 其中 2 题重建，128 题复验已有 v3 索引；没有把复用说成重新构建，也没有正式模型评测。

## 修复与保真规则

根因：快照按 UTF-8 解码后保留 U+FEFF；`ast.parse(str)` 将开头的该字符视为非法语法，而不是文件编码签名。v3 因此明确拒绝两题。

v4 的图构建器在 AST 解析、import 解析和实体源码提取时使用解析视图：**只去掉字符串开头的一个 U+FEFF**。适配器 `source_entity_segments` 使用相同规则。原始 Snapshot、文件节点、文件 SHA256、IPC 字节和 read_file 内容均保留 BOM，不改写源文件。不移除字符串内部或非首位 U+FEFF，不使用全局 replace/lstrip；重复 BOM 仍拒绝。非 BOM 文本的解析视图为原字符串，CRLF 及行号不变。首行函数测试同时检查 AST 实体位置与 read_file 中原始 BOM 的呈现。

新引擎位于 `engine_adaptation/v4/engine`，哈希 `{manifest['engine']['hash']}`。相对 v3，仅图构建器改变；harness 仅 `readonly_agent/locagent.py` 改变，修改前原文备份在 `previous-locagent.py.txt`。其他读取、路径、预算与授权规则不变。

## 实测

| 题目 | Python 文件 | 新图节点 | BOM 文件 |
|---|---:|---:|---:|
| MSAL 407 | 43 | 508 | 4 |
| MSAL 454 | 43 | 525 | 4 |

两题均在新临时源码副本中静态构图，逐文件核对原 SHA256、文件节点全文、AST 名称/跨度/实体正文与覆盖。每题的 4 个 BOM 文件现在含 34 个类/函数实体。没有执行 setup.py、目标模块或仓库测试。

45 个单元测试、4 个既有集成测试通过。新增回归覆盖 BOM 首行定义、LF/CRLF、中文与非 ASCII 标识符、字符串内部 U+FEFF 保留、重复和非首位 BOM 拒绝、非 BOM AST 正文一致。隔离组合样例验证 BOM import 边、首行行号、原始文件内容及真实 IPC 检索往返。此前构造函数、隐藏路径、软链接/路径限制、正文伪造和漏实体拒绝的必要回归保持通过。

## 128 题的复验复用

128 题均确认源码不含开头 BOM，因此新增解析视图分支对它们为恒等变换。逐题核对 v3 原索引哈希、源码快照哈希，在 v4 适配器下重新验证安全 JSON 图的文件/实体完整性及精确正文；重建内存中的实体 BM25，比较它与旧持久化索引的全部 corpus 文本和固定 `__init__` 查询的返回 ID。隐藏 Python 路径再次逐项精确读取。没有重新计算这些题的图边；沿用 v3 图构建来源，非 BOM 分支保持原图构建行为。

所有 130 题结果为 ready，原始索引来源与当前兼容版本分别记录。旧 v3 的“128 通过、2 阻塞”材料及失败目录仍原样保留；本轮复核 {old_artifacts} 个旧索引产物哈希未变。

## 清单与结论边界

- 最新逐题清单：[adapted-manifest.json](engine_adaptation/v4/adapted-manifest.json)，区分 `index_build_engine_hash` 和 `validated_engine_hash`；计划与逐题复验记录在同目录。
- 汇总：[acceptance.json](engine_adaptation/v4/acceptance.json) 与 `full-validation-results.json`。两题新图/索引位于 `validation/`，其余引用受哈希保护的 v3 产物。
- **技术验收**：130 题的本次源码、图/实体、索引兼容检查通过。
- **语义、曝光、评分**：仍 pending，未据此宣称有效独立测试集或定位质量提升。
- **真实模型入口**：未运行、未创建授权、未切换旧授权；实时检索仍从源码构图，持久化缓存尚未接入真实运行器。未来运行须选择新版本并重新冻结方案。

真实模型调用和费用均为 0。未读取密钥/.env、安装依赖或外发数据；离线进程清空环境并启用 Python 网络/模型防护，不声称 OS 级沙箱。
'''
 with (ROOT/'BOM_ADAPTATION_REPORT.md').open('x') as f:f.write(report)
 print('130 ready: 2 rebuilt, 128 revalidated; historical index files verified:',old_artifacts)
if __name__=='__main__':main()
