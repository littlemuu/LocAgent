# pgvector 并发领取修复：2026-10-17

## 请求时间线与真实调用上限

暂停消息到达前，用户已授权的单题真实补验完成全部 **3 次调用**，任务 `da3a7576-c848-4dc2-ae6c-21caca51e759` 成功；高峰usage核算0.030554元、reserved=0、服务已停止。暂停后新增模型请求 **0**。本次授权的3次配额已经用完，即使7元预算尚有余额，也不自动另建3次授权。

此次修复改变engine，先前真实验收仍对应修复前代码。已记录固定仓库/commit/问题/接收方不变的后续提案，但没有新建授权、重用旧清单或发送模型请求。下一次精确版本真实验收须先有新增调用授权，并重新静态准备与绑定计划；不能声称当前修复已获真实模型验收。

## 根因与最小改动

原始实际失败保存在 `outputs/closeout-pgvector-20261017/`：17项中16通过、1错误，两个连接同时begin触发 `rag_vector_builds_build_key_dimensions_key` 的UniqueViolation。原SQL只指定 `ON CONFLICT(build_key)`，另一个 `UNIQUE(build_key,dimensions)` 是复合外键所需约束；并发首次INSERT仍可能在非仲裁唯一索引上冲突。只检查行是否存在不能锁住尚未创建的键，不能解决此竞争。

`PgVectorStore.begin()` 在同一短事务的INSERT之前增加按schema+build identity的64位事务advisory lock。默认READ COMMITTED下，等到前一领取事务结束后，下一条INSERT使用新语句快照，已有active/ready行按原条件返回空并抛BuildConflict；失败或过期行仍按原规则领取。提交与回滚都会释放事务锁，不持有跨建图/embedding的长事务。

只增加5行实现，没有捕获IntegrityError，没有重试循环，没有改DDL、复合外键、维度/零向量约束或发布fencing。其他约束错误原样传播。锁沿用连接的有界lock_timeout；长时间等待仍可能明确报超时，不保证任意故障条件下一律BuildConflict。不同键独立；64位哈希碰撞最多导致额外串行等待。非合作的直接SQL写入、非默认隔离级别不在本次并发接口验收范围。

依据：[PostgreSQL INSERT冲突仲裁](https://www.postgresql.org/docs/16/sql-insert.html)、[事务级advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS)。

## 回归证据

| 执行 | 通过 | 失败/错误/跳过 |
|---|---:|---|
| 全部原17项 + 新2项真实数据库回归 | 19 | 0 / 0 / 0 |
| 三项并发/回滚测试各20轮 | 60 | 0 / 0 / 0 |
| 相关离线回归 | 77 | 0 / 0 / 0 |

两项新增数据库回归分别暂停第一连接于INSERT前、确认第二连接确实等待advisory lock，然后检查一胜一BuildConflict并能发布；在INSERT后注入数据库DivisionByZero，确认事务回滚、锁释放、下一连接可领取并发布。新增离线回归确认无关UniqueViolation不会被吞掉。原两连接同时领取测试也重复20轮。60次重复不算60个新增独立测试；77项包含既有单测，不能与历史674直接相加宣称全套重跑。

证据 `outputs/pgvector-claim-fix-20261017/`：`tests.log`、`concurrency-repeated.log`、`offline.log`、`result.json`。全部原失败证据保留，本次没有失败后覆盖日志或只选绿灯结果。相关离线pattern为test_rag_postgres、test_rag_offline、test_rag_graph_adapter、test_rag_review_regressions、test_engine_binding、test_public_authorization。没有重跑耗时全量discovery；此次适用回归均通过。

仍使用同一已验证隔离容器和既定DSN，PostgreSQL16.15/public.vector0.8.7。新增79个随机schema全部保留，旧schema不删；只终止测试自己创建的会话。容器结束exited，镜像、loopback端口、卷身份不变，无镜像拉取、扩展安装或配置改动。本阶段3199个保护文件哈希不变，包含冻结实验、原失败记录和刚完成真实模型请求/响应账本；前一真实补验阶段另外核验3205个保护文件。这些是不同保护集合，不相加。

## 新 engine 绑定

相对刚完成的真实单题清单，仅修改 `locagent_service/rag_postgres.py`，新增/删除均0：

- 文件旧SHA256：`991b395868020cff94366b56ef1703a889394868d00debc00056e85f462f2e49`
- 文件新SHA256：`93a6bce1ab9d7a53d47e4456cecfd7f94e2a57f0f74f44b7c2247a1c096c5bc8`
- 旧完整engine映射canonical SHA256：`773b26312d585c8e8ec4ec834a974650b52e0f454fd806a3fcc256dd41e99270`
- 新完整engine映射canonical SHA256：`92aa390920009ee7dcf8fba3835d877a6bd7fe5c4fff6bcb0387975acda1ee31`

完整比较保存于 `engine-binding-after.json`。旧源清单和已消费授权不得复用；`next-acceptance-proposal.json` 明确remaining_calls=0、new_grant_created=false。文档提交不改变此engine绑定。
