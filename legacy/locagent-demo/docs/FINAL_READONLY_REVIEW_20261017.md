# 最终只读复核：真实 smoke 与当前回归边界

日期2026-10-17。工作区 `/home/lenovo/projects/LocAgent-rag-preview`，分支 `work/rag-offline-preview`。本轮代码HEAD **`79e021224de91a8e3f94d3162fd4b6ea32e9a457`**；随后只提交本报告与交接文字，不改变engine。没有启动服务、连接数据库或新增真实模型请求，没有修改算法、冻结实验或旧账本。

## 精确真实验收版本、授权与时间

实际真实smoke代码commit **`eee52a4d1420c9bbea232f42b9bea615741559d9`**。逐一以Git对象核验保存清单的 **138 个engine文件**，全部与该commit完全一致，不能只因分支相同就将它等同当前版本。

| 绑定 | canonical engine映射SHA256 |
|---|---|
| 真实smoke | `773b26312d585c8e8ec4ec834a974650b52e0f454fd806a3fcc256dd41e99270` |
| 当前修复后代码 | `92aa390920009ee7dcf8fba3835d877a6bd7fe5c4fff6bcb0387975acda1ee31` |

唯一生产代码差异是 `locagent_service/rag_postgres.py` 的begin事务增加5行advisory lock；engine文件集合无新增/删除。README、测试、报告变更不计入这138个engine输入。

用户明确授权消息 `Sentinel_3baafe7156fc819180fbd12d59b0ba84`，父任务转交了同意记录，批准固定itsdangerous commit、问题、DeepSeek官方接收方/deepseek-flash、最多3次、单attempt、独立7元。执行器先验证当时HEAD与工作树，再固定计划，授权hash **`feabf75ac675c8add3fb910c012ecf70e37de563ccd77f7a9bb43b716b273e13`**。调用数 **3/3** 全部HTTP200且settled，高峰usage核算0.030554元，reserved=0；不是控制台账单核销。暂停消息前已完成，之后没有新增调用。

真实任务 `da3a7576-c848-4dc2-ae6c-21caca51e759` 的保存时间，均为UTC：

| 事件 | 时间 |
|---|---|
| API入库created_at | 2026-10-17T03:24:34.340061Z |
| task.started_at | 2026-10-17T03:24:34.610931Z |
| task.finished_at | 2026-10-17T03:24:44.800358Z |
| attempt.started_at | 2026-10-17T03:24:34.612178+00:00 |
| attempt.finished_at | 2026-10-17T03:24:44.804665+00:00 |
| 调用0供应商created | 2026-10-17T03:24:40Z |
| 调用1供应商created | 2026-10-17T03:24:41Z |
| 调用2供应商created | 2026-10-17T03:24:43Z |

**没有逐次HTTP客户端send/receive时间戳。** 不能把供应商created或文件mtime当请求起止时间，也不能据此计算精确网络耗时。任务和attempt时间来自保存的DB/API记录；供应商created是响应内的秒级字段，不保证与本机时钟完全同步。精确到每次请求的起止时间属于现有观测缺口。

## 真实任务是否经过pgvector

结论：**这次真实任务没有使用pgvector存储或build领取；它使用PostgreSQL任务存储和BM25/图检索。** 证据组合如下，并非只根据文件名猜测：

1. 保存的实际请求是 `source_id=github-v1` 且携带本次authorization_id。`public_pipeline.execute_pipeline` 的该分支直接调用 `public_authorization.localize_authorized`，后者调用 `sources.localize_prepared`。
2. 该实际源清单config是 `provider=public-single-task-budget-v1`、`model=deepseek-flash`、`search_protocol=bounded-v1`、`top_k=1`，且绑定本地graph/BM25产物。没有向量store、BuildSpec、embedding provider或dense/hybrid配置。
3. `sources.localize_prepared` 无条件调用 `build_module_retriever_from_graph`；该函数返回 `BM25Retriever.from_defaults`。GraphLocalizer调用的 `util.localizer._graph_session` 把这个预构造检索器注入repo_ops，后续module搜索调用它；content搜索读取本地BM25目录。这段源码在真实smoke与当前版本相同。
4. 实际保存的工具轨迹依次包含 `explore_tree_structure`、`search_code_snippets`、`get_entity_contents`、`finish`。返回目标和公开源码证据保留，未产生embedding请求。
5. `rag_postgres.module_retriever` 需要显式enabled/store/spec/provider；上述生产调用链没有调用它或构造PgVectorStore。静态阶段 `public_pipeline.index → prepare.build_indexes` 同样构建本地图与BM25，不调用vector begin。

因此此次5行修复不在该真实smoke所执行的存储/检索分支上。这个结论由实际配置、工具轨迹及确定性调用链支持；**没有保存逐函数运行时profiler**，不把代码分析描述成原始运行时覆盖率证明。完整engine采用保守包闭包绑定，仍然包含rag_postgres，所以旧授权仍对当前版本失效，不能绕过哈希检查。

## advisory lock复核及潜在问题

- key为 `hashtextextended(schema + ':vector-build:' + spec.identity, 0)`，schema由Settings限制为小写字母/数字/下划线标识，identity为版本、维度和成员集合的摘要。不同schema/build有不同原始key，SQL使用参数绑定。数据库级锁空间下，不跨数据库共享锁。
- 事务锁在INSERT之前取得，位于同一个connection context；提交或回滚后释放。正常连接非autocommit、默认READ COMMITTED时，后续INSERT在等待结束后读取新语句快照。一胜一BuildConflict保留原状态条件与fencing，DDL完全没改。
- 确定性回归暂停第一连接于INSERT前，查pg_locks确认第二连接在等待advisory锁，释放后验证一胜一败及成功发布。另在INSERT后注入DivisionByZero，确认回滚、无残留build，后续新连接能SELECT、领取、发布。
- **回滚测试验证的是后续新连接可用**。生产context会关闭已失败连接；并未证明一个外部连接池可直接复用尚未rollback的失败连接。
- begin没有广泛异常捕获；离线回归验证无关UniqueViolation原样传播。status/query已有异常归一化是另一路径，不参与领取修复。
- 潜在限制：64位hash碰撞会造成额外串行/超时；现有1秒lock_timeout可令长等待报错，不能保证任何负载都只返回BuildConflict。锁仅约束合作调用者，直接SQL可绕过。自定义connect若提供autocommit或非READ COMMITTED连接，串行化/快照前提不成立；当前接口未强制检查这些选项。没有跨schema锁独立性的专门并发实测，也没有压力/连接池/非默认隔离级别验收。本轮只读记录这些边界，未扩展算法。

## 当前HEAD全量离线回归与分开计数

本轮在上述HEAD通过既有CPU venv运行完整 `unittest discover -s tests -p 'test_*.py' -v`，命令环境关闭远程元数据下载，移除继承代理且额外阻断Python INET连接；没有设置vector测试DSN，不启动数据库。新独占证据目录为 `outputs/final-review-20261017/`。

| 运行 | 数量与结果 | 是否本轮重新执行 |
|---|---|---|
| 全量离线discovery | 694个：**675通过、19跳过、0失败、0错误** | 是 |
| 独立真实pgvector集成 | 19通过、0跳过/失败/错误 | 否，沿用修复阶段证据 |
| 三项并发/回滚各20轮 | 60次执行通过 | 否，属于上述用例的重复稳定性检查 |
| 修复阶段相关离线子集 | 77通过 | 否，与本轮全量重叠，不相加 |

19项跳过均为需要显式隔离DSN的数据库测试，已另有19项真实执行结果。不能把60次重复和77项子集加到全量数字里宣称更多独立测试。原17项实际补跑16通过1错误的日志仍保留，当前修复结果没有抹去历史失败。

全量测试前后 **3171个保护文件哈希不变**，当前engine映射也不变。该保护集合包含冻结评估和本次实际smoke/数据库验证证据，不声称扫描了所有文件。没有新增网络模型调用，没有新授权或账本。自有容器保持停止。

## 结论

**当前版本代码回归通过**：全量离线及同engine的独立数据库/并发验证分别有证据。**同一BM25服务链路在修复前版本真实smoke成功**：3次调用、语义目标正确。它们共同支持“本次pgvector修复未改变这条BM25链路”的代码影响判断，但不等于当前完整engine已重新真实smoke，也不代表总体定位准确率或公网安全验收。3次授权已耗尽，未为补齐版本标签重复付费调用。
