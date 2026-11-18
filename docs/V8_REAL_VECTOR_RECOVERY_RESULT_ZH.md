# 真实向量恢复核验与37题复用结果

2026-11-16。**旧电脑真实向量已找回并通过本地来源一致性核验。当前37题与这些旧向量的完整输入匹配为0，因此旧资产适合历史复现和真实向量接线验证，不能直接替代37题的新编码。** 本轮新增模型/embedding调用0，费用0；没有修改任何历史账本、v8源码或已封存结果。

## 1. 接收和归档

在微信下载目录找到 `locagent-vector-evidence-20261116.zip`。ZIP SHA256与用户提供的一致：

`13633fbde3a41d30c7e096c12a3e3183d7ffbd70c4c76ddcdce689f75cac6f92`

ZIP共172,930,879字节；19,636个载荷文件，加1份TRANSFER_MANIFEST，共19,637成员。检查了重复成员、路径越界、符号链接/特殊文件、加密项、展开大小和每份文件的字节数/SHA256；全部通过。展开总字节数534,112,340。核心文件无缺失。完成核验后再次校验19,636个原件，内容未改变。

正式归档：

- ZIP及原始证据：`/Users/xiaomu/Projects/LocAgent-OpenHands/assets/embedding-evidence/20261016-recovered-20261116/`，原相对结构位于 `restored/`。
- 本轮核验结果：`/Users/xiaomu/Projects/LocAgent-OpenHands/workspace/verification/sdk-hybrid-v8-real-vectors-20261116/`。
- 只读核验脚本：`/Users/xiaomu/Projects/LocAgent-OpenHands/scripts/vector_assets_20261116/`。

微信中的原ZIP保留。原始文件被复制或按字节恢复，没有重写旧绝对路径、manifest、事件、账本或历史授权。

## 2. 已核验的真实向量

| 资产 | 文档向量 | 查询向量 | 核验结果 |
|---|---:|---:|---|
| expanded50 | 9,814 | 50 | manifest固定哈希、618个成功批次、原始响应/事件链、49个源码快照、完整排名全部核验通过 |
| itsdangerous小实验 | 32 | 10 | 5份来源响应、binding、只读SQLite settled状态、原源码与块输入核验通过 |
| **合计** | **9,846** | **60** | 完整文本哈希去重后数量仍为9,846/60；总计9,906个已核验向量 |

模型契约为历史 `qwen3.7-text-embedding-flash`，1024维，明确分离document/query角色，query携带冻结instruct。核验向量长度、元素数值类型/有限性、非零范数、显式index/text_index的范围/唯一性/完整性，重新归一化；不能用数组顺序猜输入映射。

### expanded50具体证据

- 冻结manifest SHA256匹配历史固定值 `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`。
- 619个物理attempt：618成功、1个保留unknown。成功向量分别来自原batch 0–489与continuation batch 490–617；原 `body-000490.bin` 的403不作为向量使用。
- 请求体由冻结输入/模型/角色参数独立重建，核对请求和原始响应哈希；验证原事件链、续跑事件链、HTTP状态与最终settled状态。
- 验证646份源JSON哈希；从49个固定commit归档重新解析，重建47,793个函数块成员，逐项匹配冻结快照、文档文本和9,814个去重输入；5份冻结引擎文件哈希均匹配。
- 只将id/text/repo/commit交给检索重算，没有向检索器提供gold。重新计算BM25、dense、加权RRF：**150份函数排名与150份文件排名逐项匹配历史结果**。本轮未开展新的模型质量实验。
- 历史unknown仍保留；检查历史费用状态不代表本轮产生费用，也没有向供应商在线查账或确认后端模型版本。

### 小实验及更早诊断

32/10实验manifest匹配历史固定值 `a6a0abb4f12cc6d45fce36a89a384ccd0d92175b94c0246abc9f9b3e14ebf39f`。四份源码的Git blob哈希与函数块重建一致；5个有效来源为A/B单文档响应各1份，加16文档、14文档、10查询响应各1份。A/B已计入32，不能重复相加。只读打开SQLite，重新归一化结果与账本向量逐项一致。

更早诊断目录也已恢复，但未全部纳入默认复用池：两轮早期16输入unknown的原始body仍缺失；mapping-probe的后一次1输入unknown无body；单输入诊断虽有body仍保留其原unknown状态。已有safe投影、报告或哈希不用于补造缺失原件，也不据后续成功释放旧占用。另一次2输入settled诊断保留为历史对照，没有额外计作新的唯一文档缓存。

## 3. 对当前37题的实际覆盖

从当前已冻结runtime-cases逐条核对entry与source plan哈希，再核对所有白名单源码文件哈希及Snapshot身份；没有下载新源码、运行仓库代码或读取标准答案做候选筛选。

| 项目 | 本轮实测 |
|---|---:|
| 开发题 / 仓库 / 快照 | 37 / 19 / 37 |
| 按v8输入规则预统计的函数块成员 | 67,404 |
| 完整输入文本去重数 | 24,146 |
| 与已验证旧document输入完全相同 | **0** |
| 当前37个完整题面与旧query输入相同 | **0** |
| 去重文档输入UTF-8字节总量 | 22,247,210 |
| 单文档输入最大字节 | 12,067 |
| 超过历史16,000字节输入限制的文档/题面 | 0 / 0 |

这里的文档输入严格包含 `path:QualifiedName + 换行 + 函数源码`，采用max_chars=12000的物理行分块；修改路径、名称、空白、代码或查询文本都不会被当作精确缓存命中。0匹配是本次逐输入哈希比较结果，不再只是“仓库不同”的推测。

**24,146是诊断性预统计，不是已经冻结可发送的编码计划。** 为完整列出输入覆盖，诊断提取器保留各个定义的文本；它没有绕过v8保护发布语料，也没有生成或发送向量。以下兼容问题仍必须先处理。

## 4. 编码前新发现的两个问题

### 重复限定名：29/37题目前被v8语料构建拒绝

实际调用当前v8 Corpus：8题可构建、29题报 `ambiguous_duplicate_entity_definition`。真实源码有property getter/setter、overload、条件分支定义或重复嵌套函数名，这些不一定是非法源码。旧expanded50的49个快照中也有29个快照存在重复函数限定名。

下一步应明确“定义/块身份”和“终答实体身份”：块用路径＋限定名＋源码范围/内容区分，排序再按目标实体聚合；预览保留匹配定义的范围或明确展示多个定义。不能静默覆盖其中一份、删除重载，或绕过保护先付费编码。原v8合成测试通过只证明所测范围，本次真实语料审查发现了需要扩展的兼容性。

### 固定题面查询：34/37题超过当前256字符工具查询上限

37个完整题面均小于历史16,000字节输入限额，最大5,574字节；但34题超过当前 `locagent_retrieve` 的256字符限制。若做“完整题面作为固定查询”的对照，应提供明确的离线固定查询入口或版本化调整限制；若选择标题/摘要，则提前冻结规则和最终文本。不能编码一种文本，却让SDK以另一种文本查询缓存，也不能静默截断题面。动态Agent查询仍需要单独受控编码，不会被37条固定查询自动覆盖。

## 5. 下一步建议

1. **先免费修复真实语料兼容**：定义重复限定名的块身份和预览策略，确定完整题面查询通道；用37题和恢复的历史样本做离线回归。
2. **用已有真实向量检验接线**：历史数据已足够做真实向量的离线桥接验证，无需再次请求embedding。当前v8仍是synthetic-only，没有在本轮改标签或直接导入真实缓存。
3. **再冻结37题的新编码清单**：记录最终文档/查询输入、去重映射、模型和角色契约、版本、字节量与预算。当前旧资产对37题无精确命中；若继续这套输入定义，需要为这些新输入准备新向量。
4. **付费调用继续关闭**：本轮没有取得或执行新的编码调用授权。先完成可审阅计划，再决定模型、请求数量和费用上限；原实验授权不因恢复而重用。

## 6. 核验材料与复现

本轮核验目录包含：`intake.json`、`recovery-receipt.json`、`older-ledger-inventory.json`、`provenance/verification-summary.json`、`provenance/expanded-verified-inputs.json`、`provenance/small-verified-inputs.json`、`dev37/dev37-coverage.json`及日志。已验证输入索引保留role、输入hash、response文件/hash和显式index，不包含gold，也没有把整个原始响应复制进用户报告。

重做检查时使用新的输出目录，例如：

```sh
cd /Users/xiaomu/Projects/LocAgent-OpenHands
legacy/locagent-demo/.venv/bin/python -B scripts/vector_assets_20261116/verify_assets.py \
  --evidence-root assets/embedding-evidence/20261016-recovered-20261116/restored \
  --output /private/tmp/locagent-vector-provenance-recheck

legacy/locagent-demo/.venv/bin/python -B scripts/vector_assets_20261116/compare_dev37.py \
  --verified-hashes /private/tmp/locagent-vector-provenance-recheck/verified-text-hashes.json \
  --output /private/tmp/locagent-dev37-input-recheck
```

脚本使用本地现有bm25s/PyStemmer环境，依赖项目当前本机路径；不是跨机器安装包。受检过程在Python层禁网上下文运行，正式验收网络尝试0。旧原件只读，输出目录已存在则拒绝覆盖。
