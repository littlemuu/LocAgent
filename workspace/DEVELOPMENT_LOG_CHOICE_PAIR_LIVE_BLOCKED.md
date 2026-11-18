
## 2026-11-13｜真实工具说明配对准备完成，自动审核阻止启动

- 用户要求“调用模型跑一次”，按已准备的配对材料解释为控制/候选各1次，最多2请求/5元，deepseek-flash，固定原题与历史搜索证据，仅说明不同；不执行模型选出的工具、不追加回合。
- 新建独立入口experiments/choice_pair/run.py及choice_pair/v1冻结，hash 64dee9be8533dd47b3543e0d17b7e20c87ed5faf57e1a5c15a197c1c3f4f18b9。12项免费测试通过，覆盖最坏预留4.227072元、重复启动/票据、价格、过期、精确payload、首/次请求超时和错误参数。
- CNY账户/官方峰值价已复查，18份旧账本无待结，无重复模型进程；本地grant已创建但未claim。真实启动命令被自动审批审核在进程创建前拒绝，理由为用户未明确授权具体数据/DeepSeek目的地/两次配对。
- 未绕过、未重试；无claim、无run目录、Key未加载、真实请求0、费用0。等待用户明确确认具体两请求与数据范围，不能把助手解释当作用户逐项确认。报告CHOICE_PAIR_LIVE_BLOCKED.md，证据verification/choice-pair-live-v1/。
