# 冻结50题预算门禁修复与二次复核

2026-10-16。范围：已批准的离线修复，不是新增真实请求授权。

## 结果与门禁状态

前次R1/R2已针对正式入口修复。**86项离线测试通过，冻结618请求全量假响应验证通过，恢复零重发。真实执行和真实transport仍禁用。** 无付费请求、无凭据读取或修改、无DB服务、无commit/push。

| 门禁 | 状态 |
|---|---|
| 固定manifest、完整计划来源 | 通过：正式入口内部加载固定文件，核对冻结SHA、原引擎、618批/9864成员及全部请求体 |
| 任意同形文本/自造binding进入正式执行 | 拒绝：公开execute不接受plan、binding或transport参数 |
| 唯一候选run与固定账本域 | 通过：固定r01、固定规范路径、固定cap2；r02、换目录、路径别名或更高cap拒绝 |
| 同run锁/账本复制到别域 | 通过：只打开规范路径上的同一锁；复制账本到别域时元数据绑定不匹配 |
| 预留、usage结算、unknown恢复 | 通过：原离线故障用例保留，新增门禁路径崩溃/恢复负向用例 |
| 固定HTTPS wire适配 | mock通过：固定host/path、TLS校验、原始请求字节hash、禁止redirect/重试、有限读取 |
| 真实授权与真实HTTP调用 | **关闭：公开入口固定拒绝；无批准凭证或真实run目录** |
| 真实服务兼容、实际usage/账单 | 未运行，不能由fake通过推断 |

## R1修复

`locagent_service/bailian_expanded_runner.py` 的公开 `execute(*, run_id, directory, cap, manifest)` 不再接收任意plan/binding/transport。它先调用 `_fixed_spec`，由内部固定 `FROZEN` 路径读取冻结manifest，经 `load_plan` 检查固定SHA和完整成员，再生成binding，之后因没有真实授权明确抛出 `real_execution_not_authorized`。

旧自由计划执行函数更名为私有 `_execute_journal`，仅供预算状态机小样本单测及内部固定计划路径调用。全量验收改走 `_offline_frozen_acceptance → _fixed_spec → load_plan → _execute_journal`，不再由测试代码自选计划直接冒充冻结数据。

私有测试函数允许临时假账本域，以便不污染真实域。它不是授权入口；可以任意执行Python/monkeypatch模块的人不在此门禁的防御模型内。正式入口未暴露这些注入点，也没有“切offline标记就可真实发送”的分支。

## R2修复

候选run ID固定为 `bailian-expanded50-78e24794-cap2-20261016-r01`；新cap固定字符串 `2`。

唯一正式账本目录预定为：

`/home/lenovo/projects/LocAgent-rag-preview/outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01`

该目录是候选定位，**本轮不创建**。正式入口没有ledger-root覆盖参数；传入目录只能与内部规范目录精确一致，拒绝相对路径、`./`/`../`别名、其他输出目录和符号链接路径。因别名被拒绝，不存在同一run通过两个别名建立两把锁的路径。

binding新增run_id、ledger_domain、ledger_directory、frozen_manifest_path；元数据恢复逐字节核对。复制已存在账本到新测试域也因身份不符拒绝。更高cap或r02在接触账本/transport前拒绝。旧unknown之后不能用正式参数换目录重跑。

这不声称可防止拥有同用户权限者修改代码常量、删除/回滚整个账本域或调用私有测试函数；那些不属于受控公开入口。未来用户明确批准真实run后，仍须经审查接通授权门禁，不能把离线binding当批准凭证。

## transport适配与限制

新增 `locagent_service/bailian_expanded_transport.py`。`PinnedHTTPS.__call__` 无条件抛 `real_transport_not_authorized`；不获取token、不创建连接。私有 `_exchange_for_review` 只由mock测试调用，使用dummy token，实际网络被阻断。

wire逻辑固定HTTPS host与443端口、固定POST path；默认TLS上下文验证证书和主机名，不继承环境代理。请求必须是冻结请求体hash集合成员，不允许改模型、维度、instruct或文本；凭据只作为Authorization头值且拒绝控制字符，不记录头或秘密异常字符串。

单次调用只有一次request/getresponse，没有重试、Location跟随、fallback或SDK响应重组。301/302/307/308、401/429/500由上层作为非200响应保留预留并停止。响应按原始bytes返回，最多读取4MiB+1字节以检测超限，不接受压缩正文。连接有20秒socket超时，finally关闭；**这是I/O超时，不宣称完整硬墙钟期限，慢速持续输入等仍需未来真实传输评估。**

mock工厂是私有测试接口；未来正式授权路径必须使用受审查的实际HTTPS连接，不允许任意外部工厂或任意transport注入。当前阶段刻意未接通这一真实调用分支。读取官方文档可以支持字段形状，不能认证未来服务端账单；raw SHA证明字节绑定，来源真实性仍依赖真实TLS链与固定传输。

## 离线验收证据

最终目录：`outputs/bailian-expanded-budget-gates-20261016-reviewed/`。

- 86通过、0失败/错误：25项预算测试 + 15项门禁/wire测试 + 46项原响应、契约、准备及RRF回归。
- 618个冻结body SHA全部匹配，文档9814+查询50=9864输入；假响应全量结算后同run重启零请求。
- 合成usage每输入10 tokens，合成spent0.0123300元只验证算法，**不是实际账单或价格估计**。
- 原258份历史证据+5份冻结文件共263份哈希未变；冻结manifest和原engine不变。
- 新负向测试覆盖任意参数注入、r02/更高cap、换目录/相对路径/别名/符号链接、复制账本换域、manifest损坏、同run锁冲突、门禁路径unknown恢复、模型/维度/instruct/host篡改零连接、redirect/错误无重试、异常脱敏、正文超限/压缩和头注入。
- 首次门禁验收的单测通过，但全量脚本因传相对输出域触发`noncanonical_domain`而中止。随后修正验收脚本先resolve输出路径，保留该失败目录。中间85项通过记录亦保留；本报告以最终86项和reviewed目录为准。

复现命令（第二条须用不存在的新目录）：

```sh
cd /home/lenovo/projects/LocAgent-rag-preview
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/preview_expanded_budget.py --proposed-cap 2
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/verify_expanded_budget.py --out outputs/bailian-gates-recheck-NEW
```

最终执行器SHA256：`1a08453708fe9c027c34669e0fc18b452d035023f699a0de80d2e7ea99c5d97a`。
transport SHA256：`00cf51340fe3663e639606ba0f731bbabf4a4604e777b21b164c847ef10e8d87`。
测试日志SHA256：`18a68317ce8db0dfae855000e1e7fa1f0a1a8a39a2487f4fb05184c5cb504d46`。

## 二次代码复核结论

对最终入口到固定计划生成、唯一目录绑定、内部账本恢复、wire调用路径重新检查：未发现前次R1/R2仍可通过公开参数触发；没有新增正常崩溃重发或unknown退款路径。正式execute和transport的无授权拒绝分支均在创建真实run/连接之前。此结论限定于当前禁用真实执行的交付，不是生产运行验收。

已实现离线门禁与wire规则；剩余真实运行阻塞是用户尚未明确授权，以及授权后受控接通/复核真实调用路径。不得通过调用私有review函数来绕过这个阻塞。无需为本次离线修复再向用户索取同类许可。

## 完整待确认摘要（不是本轮批准）

| 项目 | 固定建议 |
|---|---|
| 唯一run | `bailian-expanded50-78e24794-cap2-20261016-r01`，上述唯一规范账本域 |
| 文档/查询 | **9814**份公开函数文本（9仓库固定commit，含支持的tests/docs）+ **50**个公开issue标题 |
| 接收host | `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com` |
| 模型 | `qwen3.7-text-embedding-flash`，1024维 |
| 最大请求 | **618**，每批≤16，串行，无重定向/自动重试 |
| 新独立cap | **2元**；最大单批预留0.262144元，成功校验usage后释放差额，不保证全量完成 |
| 旧占用 | **1.277952元不变**，其中unknown **0.557056元**不释放；未来若批准新2元，合计上界3.277952元 |
| 失败 | 超时/错误/不可信或超限usage立即保留预留并停止；额度不足时零调用拒绝；unknown不重发 |
| 冻结manifest | `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b` |

instruct和候选/分块/评分不变，不发送issue正文/评论、补丁、gold或私有文件作为模型输入。目前CLI仍只有dry-run；没有用户真实请求授权或已批准凭证。
