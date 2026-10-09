## 最新真实评估状态

审批和独立review已通过，指定plan已执行一次：13次真实调用，保守结算¥0.161684，未知调用0，无重试。四组iteration_limit，2317 off因输入门槛失败后停止，五组未执行；两组固定分母5，有效定位得分均为0。

完整结果见 [LIVE_REPORT.md](outputs/stage4/followup5-live-20261008/LIVE_REPORT.md)。下方为原离线准备与审查请求的历史记录，其中待审查/待执行状态已被本节更新。真实授权已使用，不得自动续跑或重放。

---

# 五样本后续评估：离线验收与独立审查请求

基线：work/locagent-baseline，54fcb660d4a886e7f0675ed419b3a4ed21aa3fb6。
本轮没有 commit/push，没有读取或复制真实 .env 内容，没有真实模型调用。
用户已另行同意这五个公开 requests 问题/片段发往官方 DeepSeek Flash、费用上限 ¥5；这不是复用首次 pilot 的 ¥20 授权。独立 review 尚未完成，live gate 仍为 APPROVED_PLAN_HASH=None。

## 冻结样本与输入

数据集为本地 SWE-bench_Lite test 300 条，revision 6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2；其中 requests 共六条，排除已用的 3362，保留其余全部五条，不按预期效果替换样本。

顺序按 SHA256("locagent-followup5-v1\n" + instance_id) 升序：

| 顺序 | 样本 | base_commit | 图节点 / 边 | 组顺序 |
| --- | --- | --- | --- | --- |
| 1 | psf__requests-1963 | 110048f9837f8441ea536804115e80b69f400277 | 752 / 2414 | off → on |
| 2 | psf__requests-2148 | fe693c492242ae532211e0c173324f09ca8cf227 | 812 / 2664 | on → off |
| 3 | psf__requests-2317 | 091991be0da19de9108dbe5e3752917fea3d7fdc | 832 / 2741 | off → on |
| 4 | psf__requests-2674 | 0be38a0c37c59c4b66ce908731da15b401655113 | 892 / 3031 | on → off |
| 5 | psf__requests-863 | a0df2cbb10419037d11d04352b3175405ab52941 | 840 / 2890 | off → on |

每个 commit 都重新从本地 Git archive 静态构建图和 BM25，独立 bundle/manifest，不复用旧索引，不执行目标仓库代码。网络禁止的 offline_engine 包围索引构建与合成定位。逐来源身份见 sources.json，样本文件不包含 patch/评分答案。

labels.json 独立冻结：以 patch 的删除行/插入锚点映射到 base_commit 的外层函数或类方法；嵌套函数变更归入包围方法，模块 import 变更只贡献文件标签。命中实体逐个确认存在于相应图中，规则在任何模型结果之前确定，见 label-provenance.json。标签不会传给引擎/provider。

计划：outputs/stage4/followup5-20261008/plan.json。
计划 canonical SHA-256：c94baaa9a06d775d6022cf14a643b4962c440f8dd8d44d5f86eb80da15877660。

两组固定分母均为 5；每样本每组最多 3 次，总计最多 30 次。失败、预算耗尽及未执行条目都保留在分母内。此前 pilot 单列，不混入本次分母。交替顺序能减少单向顺序偏差，仍不是消除缓存影响或证明因果的充分条件。

## 最小实现范围

- locagent_service/followup.py：固定五样本计划、独立一次性授权、原始 HTTP payload 校验与预算结算。
- prepare.py：新增 --followup5，只为新构建 manifest 加固定预算政策标识。
- sources.py：按新 manifest 政策选择新 provider，旧预算/旧来源逻辑不变。
- evaluate.py：新增 version3 计划、交替组顺序及对应账本初始化，复用原独立子进程和固定分母评分。
- tests/test_stage4_followup.py：新增 21 项离线预算/故障/集成回归。
- 没有改变 API、store、worker、数据库迁移、GraphLocalizer 或旧 pilot 账本。

每一定位任务继续使用独立进程，避免 GraphLocalizer 全局状态交叉污染。预算账本加锁期间只允许一个 provider 请求，五样本评估按已冻结顺序串行执行。

## ¥5 预算不变量

采用用户指定的官方人民币峰时输入未命中 ¥2/M、输出 ¥8/M；忽略缓存优惠计算保守费用。每次预留整个 1,048,576 输入 token 加 512 输出 token：

(1,048,576 × 2 + 512 × 8) / 1,000,000 = ¥2.101248。

每次网络请求前必须满足：
已结算保守费用 + 未决完整预留 + 本次 ¥2.101248 ≤ ¥5。

不能把 30 次完整预留（¥63.037440）直接放行。代码也不承诺一定能跑完 30 次：金额不足时停止后续请求，保留全部五样本分母。完整上下文及官方价格是费用上界的前提；本地账本不是供应商账户侧消费闸。

时序：

1. 规范绝对路径和稳定锁下验证计划、价格、独立授权、每个 source/arm 的三次限额和历史状态。
2. 原子写入并 fsync 完整预留；持久化 inflight 标记。
3. 仅向 https://api.deepseek.com/chat/completions 发一次非流式请求；无重试、无重定向，temperature=0、thinking disabled、max_tokens=512。
4. 原始 HTTP JSON payload 以 UTF-8 文本及 SHA-256 保存并 fsync，预留仍不释放。
5. 直接检查原始 JSON 的 prompt_tokens、completion_tokens、total_tokens、prompt_cache_hit_tokens、prompt_cache_miss_tokens 均显式存在且为整数；验证输入=缓存命中+未命中，总量=输入+输出，输入/输出在预留范围内。拒绝布尔数、缺字段、重复 JSON key、负值、越界和不完整响应。
6. 原始校验通过后才构造 LiteLLM ModelResponse 给原引擎使用。绝不将 SDK 补零的 usage 当成结算依据。
7. 持久化结算：prompt×2/M + completion×8/M，之后才能清除 inflight。缓存字段只记录，不用其优惠释放更多额度。

超时、非200、缺失/不一致 usage、崩溃、原始响应或结算写入故障均保留完整预留并停止。inflight 标记防止“结算 rename 已可见但 fsync/后续写入失败”被另一个进程当作可继续的正常完成。没有自动恢复/重放入口。

独立授权固定位置：
outputs/stage4/authorizations/followup5-cny5.json。
原 first-pilot-cny20.json 及恢复审计不动。新授权绑定 plan hash、唯一账本规范路径、所有权 token、计价文件 hash；换输出目录或复制账本不能重新领取。测试使用临时 marker 或明显标注 synthetic 的 marker，真实 followup5 marker 尚未创建。

## 已完成的验收

完整回归 153 项通过（21.222 秒），其中原有 132 项与新 21 项全部通过；git diff --check 通过。证据 offline-tests-final.log。

新增测试覆盖：
- 原始 HTTP 缺 usage（在任何 SDK 转换之前拒绝）、字段缺失、类型/总量/缓存不一致；
- 原始响应先持久化后结算的顺序；
- 原始/结算写入故障、rename 可见而 fsync 失败、真实子进程预留后退出；
- 八进程竞争只完成同一 source/arm 的三次请求，路径别名共享额度、复制账本拒绝；
- 30 次小用量合成请求可以按已知费用逐次结算，但两次满额用量后第三次预留被 ¥5 上限拒绝；
- 五样本 off/on 交替顺序、失败即停、未执行条目仍计入每组分母5；
- 实际 httpx 序列化经 MockTransport 拦截，无重试/重定向或真实外发。

五份实际静态图上的离线配对闭环：10/10 completed，每组5，真实质量/token/费用字段均为 null。工具消息字符为 off 19,890 / on 11,235，只是 scripted provider 轨迹，不能宣称质量或真实成本提升。见 offline-paired/summary.json。

真实图与合成原始响应账本联合验证也已通过：10 个独立子进程、30 次合成响应全部结算，最大实际消息输入估算 22,970 字节，低于 65,536 门槛；消息内未出现本地主机路径。见 synthetic-budget-evidence.json。合成费用 ¥0.00030 只是测试算式输入的结果，不是实际收费或模型用量。

## 复现

~~~sh
cd /home/lenovo/projects/LocAgent
sh scripts/check_local.sh

# 新目录；不加载 .env，不需要费用
.venv/bin/python -B -m locagent_service.evaluate run \
  --plan outputs/stage4/followup5-20261008/plan.json \
  --labels outputs/stage4/followup5-20261008/labels.json \
  --output outputs/stage4/followup5-offline-new

# 重建单个来源的静态入口；不覆盖已冻结实验或改选样本
.venv/bin/python -B -m locagent_service.prepare \
  --repo outputs/day1/requests \
  --sample outputs/stage4/followup5-20261008/psf__requests-1963.sample.json \
  --followup5
~~~

重新构建会生成新的 bundle/source ID；不能在本轮 live 计划中擅自替换已冻结来源。

## 独立审查与执行前剩余条件

用户预算/公开数据外发已确认，不需重复询问。请独立审查原始 usage 的真实性、fsync/崩溃状态机、授权边界、固定来源/分母、标签隔离和 30 次限额。审查通过后，才将 APPROVED_PLAN_HASH 从 None 固定为上述计划 hash，并核对最终 diff；不得开放任意计划。另需生成与此 hash 绑定、24小时内有效的 CNY 2/8 全费用计价确认，然后才能经显式 --live --env-file .env 执行一次。

以下是审查通过后的待执行命令，当前未执行，真实确认文件目前不存在：

~~~sh
.venv/bin/python -B -m locagent_service.evaluate run --live --env-file .env \
  --pricing-confirmation outputs/stage4/followup5-20261008/pricing-confirmation.confirmed.json \
  --plan outputs/stage4/followup5-20261008/plan.json \
  --labels outputs/stage4/followup5-20261008/labels.json \
  --output outputs/stage4/followup5-live-20261008
~~~

未知结果不得重新运行；不能删除授权/账本/inflight 继续领取额度。实时费用是原始 usage 按已确认峰时费率的保守估算，不是读取账户账单。即使五样本全部完成，也只报告本队列观察结果，不能据此承诺泛化质量或稳定节省。

参考：[官方响应/usage 字段](https://api-docs.deepseek.com/api/create-chat-completion/)、[官方模型与别名](https://api-docs.deepseek.com/quick_start/pricing/)、[人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。本轮英文接口/模型页核验成功；中文价格页重取超时，2/8 为本轮明确指定费率，live 前应重新核验中文价格或账户适用费率。
