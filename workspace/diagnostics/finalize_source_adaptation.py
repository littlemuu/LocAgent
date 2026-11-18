"""Finalize offline attestations without changing previous plans or results."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'engine_adaptation/v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def save(p,x):
 with p.open('xb') as f:f.write(enc(x))
def main():
 result=json.loads((OUT/'full-validation-results.json').read_text())
 manifest=json.loads((OUT/'manifest.json').read_text())
 assert len(result['rows'])==130
 assert {r['id'] for r in result['rows']}=={r['id'] for r in manifest['plans']}
 assert all(sha(OUT/'engine'/n)==h for n,h in manifest['engine']['files'].items())
 assert all(sha(ROOT/n)==h for n,h in manifest['harness_files'].items())
 rows=[]
 for r in result['rows']:
  plan=json.loads((OUT/'plans'/(r['id']+'.json')).read_text())
  ph=plan.pop('plan_hash')
  assert hashlib.sha256(enc(plan)).hexdigest()==ph
  if r['exit_code']==0:
   assert r['result']['snapshot']==hashlib.sha256(enc(plan['sources'])).hexdigest()
   assert r['result']['status']=='ready'
   assert sorted(r['result']['hidden_queries_verified'])==sorted(plan['hidden_python_paths'])
  for name,h in r['artifacts'].items():assert sha(OUT/'indexes'/r['id']/name)==h
  stderr=(OUT/'indexes'/(r['id']+'.stderr')).read_text(errors='replace')
  error=next((line for line in reversed(stderr.splitlines()) if line.startswith(('ValueError:','AssertionError:','RuntimeError:'))),None)
  rows.append({'id':r['id'],'technical_status':'ready' if r['exit_code']==0 else 'blocked',
   'plan_hash':ph,
   'failure':error or ('timeout' if r['exit_code']=='timeout' else None),
   'attestation':str(OUT/'indexes'/(r['id']+'.attestation.json')),
   'semantic_review':'pending','exposure_review':'pending','scoring_review':'pending'})
 prior=json.loads((ROOT/'verification/engine-compatibility-v1/preflight.json').read_text())
 changed=[p for p,h in prior['protected_before'].items() if sha(Path(p))!=h]
 expected={'core.py','locagent.py','bridge.py','locagent_worker.py','preparation.py','openhands_replay.py'}
 assert {Path(p).name for p in changed}==expected
 assert all(Path(p).parent==ROOT/'readonly_agent' for p in changed)
 save(OUT/'adapted-manifest.json',{'engine_hash':manifest['engine']['hash'],
  'harness_files':manifest['harness_files'],'cases':rows,'live_authorization':False,
  'model_calls':0,'cache_in_live_runner':False})
 acceptance={'status':'completed_with_blocked_cases' if result['failed'] else 'passed',
  'ready':result['ready'],'blocked':result['failed'],'model_calls':0,
  'expected_modified_harness_files':changed,
  'unchanged_historical_files':len(prior['protected_before'])-len(changed),
  'engine_hash':manifest['engine']['hash'],'all_new_artifact_hashes_verified':True}
 save(OUT/'acceptance.json',acceptance)
 fail='\n'.join('- '+r['id']+'：'+str(r['failure']) for r in rows if r['technical_status']=='blocked') or '无。'
 report=f'''# LocAgent 130 题源码适配与索引技术验收

2026-11-14。已完成三个修复方向，并在新目录构建当前接口适配产物。最终 v3 对 130 题逐题执行离线技术检查：**{result['ready']} 题通过，{len(result['failed'])} 题阻塞**。没有模型请求、费用、题目质量评分或独立评测结论。

## 实际变更

- 新引擎副本：`engine_adaptation/v3/engine`，146 个冻结文件，哈希 `{manifest['engine']['hash']}`。原引擎与 batch134 都未改。只有图构建器和 repo_ops 两个文件不同于原当前引擎，未搬入旧 Agent 循环。
- 构造函数：旧实现显式跳过同步 `__init__`，属于旧建图取舍，但不满足精确函数定位的覆盖要求。移植 batch134 的构造函数/嵌套实体覆盖与目录组件判断，保留避免错误模糊构造调用边的保护。
- 换行：图文件读取统一 UTF-8 且 `newline=''`，IPC 写入使用原始 UTF-8 字节；Snapshot/AST 正文精确校验保留。CRLF、Unicode 与证据行号已通过真实 IPC 回测。
- 隐藏源码：Snapshot 新增独立逐文件 `hidden_python_paths` 白名单，默认仍拒绝隐藏路径；仅允许已列入源码清单的 `.py`，继续拒绝管理/凭据目录、越界和软链接。白名单进入计划和 IPC。7 题的 14 个隐藏路径均已逐一精确读取成功。
- 查询：保留实体 ID 开头的点；明确指定的已入图实体允许读取名称像测试文件的路径。**关键词 BM25 仍沿用测试文件过滤规则**，未声称这些文件都能被模糊检索发现。
- 完整性：拒绝漏建 Python 文件或可解析 AST 实体，拒绝不支持的源码语法，仍拒绝正文、名称和行号伪造。未用跳过异常或关闭哈希校验让任务“通过”。

## 迭代与验证

v1 建图成功后，端到端查询暴露 `.ci` 被去掉开头点；v2 修点后，真实隐藏文件查询暴露 test 文件过滤；两版及失败记录全部保留并标记 superseded，未启动全量扩展。v3 通过小样本门禁后才扩展其余 121 题。

41 个单元测试、4 个现有集成测试通过；组合边界回测覆盖构造函数及嵌套函数、普通带点目录、不产生跨类构造调用边、CRLF 精确正文、隐藏路径 IPC、伪造正文/漏建文件/漏建实体拒绝及行号。现有隔离测试原先手工构造只有文件节点的不完整图，已补全其函数节点以维持该测试的跨题隔离目的；拒绝不完整图另有负向测试。

小样本包括人工组合样例、SQLGlot/Loguru 两道已曝光题、7 道包含隐藏 Python 的题。SQLGlot 新图 4,389 节点，Loguru 1,686 节点；同源同环境下恢复此前缺少的 48/38 个构造函数相关实体。生成的实体 BM25 索引在人工样例和这两题加载回测通过。

全量每题使用独立临时源码副本和进程，最多 3 个并发工作进程，单题 CPU 90 秒/墙钟 120 秒；目标代码只读与静态解析，不执行。全部来源名与路径的 stat/包含关系检查共 22,897 个 Python 文件引用，无越界或软链接。未依赖题面、评分标签或参考补丁选择查询或改检索。

## 阻塞样本

{fail}

其中 MSAL 两题的追加静态探针都发现 `msal/exceptions.py`、`msal/mex.py`、`msal/token_cache.py`、`setup.py` 带 UTF-8 BOM，字符串 AST 解析报 U+FEFF。这是新揭示的编码适配缺口，不是源码必然无效；BOM 的解析视图与原始字节绑定仍未修复，记录在 `blocked-syntax-probe-2.json`。

这些是技术阻塞，不能算题目无效、定位失败或性能零分。未自动重跑失败样本；具体源码语法/覆盖问题应另行诊断，保持两组源码范围一致，不能静默删文件来过门禁。语义、曝光与评分映射仍待独立核验。

## 产物与边界

- `engine_adaptation/v3/manifest.json` / `plans/`：130 个不可变计划，绑定父 source_id、固定提交、源码 SHA256、隐藏白名单、新引擎及 harness 文件哈希；不含模型运行授权。
- `indexes/`：成功样本有 source-only `graph.json`、实体 ID BM25 的 JSON/JSONL 与数值数组、结果和哈希证明；失败目录及 stderr 原样保留。没有新增 pickle 读取。
- `adapted-manifest.json` / `full-validation-results.json`：逐题技术状态，语义/曝光/评分均 pending。计划初始 planned 状态不覆盖，最终状态独立记录。
- `boundary-results.json`、`unit-tests.txt`、`existing-integration.txt`、`index-roundtrip.json`、`source-path-audit.json`、`acceptance.json`：测试和完整性证据。

缓存索引尚未接入真实模型运行器；现有实时检索仍从源码构图。新实验应显式选择新引擎并重新冻结计划，不能让旧授权换绑到这些产物。旧计划因 harness 哈希变化会被拒绝，未放宽该检查。

最终核验：旧受保护材料中仅 6 个预期 harness 源文件改变，其余 {len(prior['protected_before'])-len(changed)} 个哈希未变；旧引擎、旧索引、账本、模型结果保留。未读取 `.env` 或密钥，未安装依赖、调用模型或外发数据。Python 层网络/模型防护不冒称 OS 沙箱。
'''
 (ROOT/'SOURCE_ADAPTATION_REPORT.md').write_text(report)
 print(json.dumps(acceptance,ensure_ascii=False))
if __name__=='__main__':main()
