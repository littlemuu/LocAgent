# 五题真实批次结果（2026-11-15）

批次在第二题的原生适配组终答校验失败后停止，没有重试或继续后三题。共15次请求、15个供应商回包，三组有效完成、一组失败、六组未启动。实验冻结版本未变；只修复了启动器进程列表的编码处理。

A：LocAgent图工具＋physical-line80正文BM25适配版。B：OpenHands基础文件工具＋实体BM25适配版。

|题目|组|结果|请求|输入token|输出token|费用上界/元|
|---|---|---|---:|---:|---:|---:|
|viztracer #528|A|有效终答，未命中|4|22,705|882|0.052466|
|viztracer #528|B|有效终答，未命中|4|12,831|838|0.032366|
|accelerate #3261|A|终答校验失败|3|16,872|768|0.039888|
|accelerate #3261|B|有效终答，首位命中|4|20,199|978|0.048222|
|supervision #1698|A/B|均未启动|0|0|0|0|
|luigi #3324|A/B|均未启动|0|0|0|0|
|SQLGlot #3436|A/B|均未启动|0|0|0|0|

## 失败与预算

accelerate A的finish写出 `examples/by_feature/megatron_1m_gpt_pretraining.py`（数字1），实际文件为 `megatron_lm_gpt_pretraining.py`（字母l）。同一验证器离线重放得到 `ValueError: prediction_outside_snapshot`。原包保留，没有替模型纠正答案或修改评分规则。这不是超时或输出截断。

该组前两轮四个调查工具已返回14,336字节证据，第三轮提前仅开放finish。viztracer A最终也达到14,336字节；viztracer B为8,968，accelerate B为14,167。三个完成组均在第四轮收尾。费用预算未耗尽，输出未超过2,048 token限制。

父账本第一题完成计8次；实际总调用须合并子账本，合计15次。失败题父级保留17元额度占用，它不是已花17元。15个回包全部结算，未知请求预留为0。一次性授权已消费，剩余25次不自动使用。

## 工具与定位

viztracer B使用列表、文本搜索和读文件，没有调用LocAgent；两组均未命中固定参考函数 `src/viztracer/main.py:VizUI.exit_routine`，主要输出 `viewer_main`。

accelerate B在第一轮自主并列调用 `search_text` 和 `locagent_retrieve`，随后读取例子、Accelerator及ProjectConfiguration源码。终答首位为 `examples/by_feature/megatron_lm_gpt_pretraining.py:main`，命中gold。没有强制检索或追加请求。A使用自身图和正文检索工具，不能称为“无检索组”。

## 费用与评分

输入合计72,607、输出3,466 token；输入缓存命中33,536、未命中39,071。按输入2元、输出8元/百万token计算，保守费用上界为 **0.172942元**。

供应商回包创建时间为北京时间2026-11-15 16:53:16至16:54:07，周日。按官方空闲价及缓存用量估算 **0.05360572元**，不是账单实扣。账户实扣未独立取得；有效计费仍依据此前用户确认。[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

固定strict Acc/Recall/Hit @1/3/5：本批每题单gold，各指标在同一k等价。完成题分母A为0/1，B为1/2；固定每组5题且失败/未启动计零时为A 0/5、B 1/5。必须同时报告完成、失败和未启动数。只有viztracer这一对双方有效完成，不能作五题完整配对性能结论。

这五题已有开发曝光，前四题提示较强，标签只有单人初查。两套系统的提示、工具和检索后端均不同，不能将差异归因于检索或宣称泛化优势。正文分块后端是适配实现，非上游原版。

## 证据

- `verification/five-batch-live-v2/analysis.json`：逐轮工具、请求、token、费用、评分。
- `finish-failure-diagnosis.json`：失败终答和离线复现。
- `authority/run/result.json`：批次停止及父子预算。
- `authority/run/children/<case>/<hash>/run/ledger.sqlite`：原始请求、回包和预留；同目录保留完成组的原生/SDK轨迹。
- `confirmation.json`、`invocation-lock.json`、`launch-claimed.json`及父授权：用户批准、冻结版本和一次性启动记录。

未修改终答规则，未补跑。后续可以离线审视不存在的普通源码路径应归为定位错误还是协议失败；任何新规则都须留版本记录，不能覆盖本轮结果。
