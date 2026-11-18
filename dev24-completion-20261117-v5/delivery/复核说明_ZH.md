# 本轮证据与复核

本目录对应2026-11-17剩余16题单次A/B运行，以及与原8题合并的dev24结果。所有复核命令只读本地已产生的试跑证据，不调用模型。

## 核心文件

- `REPORT_ZH.md`：中文报告。
- `summary.json`、`逐题结果.csv`、`逐题配对差值.csv`：统计与逐题数据；B包含定位。
- `final-paired-audit.json`：48次运行的配置、输入、补丁、评分与统计验收。
- `final-cloud-audit.json`、`shutdown-receipt.json`、`关机最终状态.jpg`：密钥删除、容器结束与关机状态。
- `remaining16-authorization.json`：原始30元授权；`budget-amendment.json`：用户随后取消金额止损的追加记录。原授权保留，未覆盖。
- `remaining16-evidence-v5.tar.gz`：新增16题原始请求、响应、补丁、harness输出、费用账本及核心代码。
- `first8-evidence-v4.tar.gz`、`first8-summary.json`：原8题证据副本，未修改。旧归档SHA-256为`087d37e8f1b0028afae37161413970b4ce1dff10173e606af464e571d38d1bc5`。
- 新增证据归档SHA-256为`b0c7869fc806975f39f512b98fba4be1c1a90af396d954cd4652dd2dfec82c87`，本地与云端一致。
- `unchanged-core-runtime-v4.zip`：沿用的运行时；`run_remaining16.py`仅增加本轮范围控制。该入口是已完成运行的冻结证据，不代表授权重新执行。

## 离线重算

在本目录下使用Python 3.10及以上版本：

```sh
mkdir -p evidence-first8 evidence-remaining16 recomputed
tar -xzf first8-evidence-v4.tar.gz -C evidence-first8
tar -xzf remaining16-evidence-v5.tar.gz -C evidence-remaining16
python3 summarize_dev24.py --old first8-summary.json --old-run evidence-first8/verification/round-run --new evidence-remaining16/verification/remaining16-run --output recomputed
python3 audit_dev24.py --old evidence-first8/verification/round-run --new evidence-remaining16/verification/remaining16-run --output recomputed/final-paired-audit.json
```

费用是由服务端usage、缓存信息和请求发起时段折算，不是已核对的账户账单。额外两次重复、holdout和检索改进组均未运行。

Requests的A/B日志都含证书校验异常。原始评分保留，未改变容器、网络、证书或评分规则，也未补跑。监测期间两次本地SSH读连接超时，云端后台任务持续运行，没有重启任务或重试模型请求。
