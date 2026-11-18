# 当前进度

开发方向是 OpenHands SDK 驱动的只读代码定位 Agent，LocAgent 提供静态源码检索。最近真实验证组合是 EvidenceRetriever v6 + 通用自检提示 v7。新开发版本 v8 已接入函数正文 BM25 + dense + 加权 RRF，在实际 SDK 上完成40项离线测试及端到端演示；向量与模型响应仍是合成/脚本夹具。详见 [v8 接入与复现](V8_OFFLINE_INTEGRATION_ZH.md)。

- v6 修复检索证据呈现；两组均可自主使用检索。
- v7 只增加系统层终答自检，不自动补实体、路径或分数。
- 六题十二组全部完成；46请求，无待结费用。Hit@1为5/6→5/6，Hit@3为5/6→6/6，Recall@5为73.61%→80.56%。
- #4369 `_combine`、#689 `_group_average` 各新增一次命中，但正文未读，排序/解释仍有张力。不要将开发集单次结果写成稳定因果收益。
- 本轮12份终答和模型工具输入均通过一致性检查，41个实体ID存在，12份评分复算一致。原始304文件、最终325文件已封存。

完整报告与账本在 [v7运行目录](../workspace/verification/sdk-finish-selfcheck-v7-live/)。优先阅读 REPORT_ZH.md、analysis.json、audit.json、finish-audit/audit.json、score-check.json 和 result-lock.json。

后续可做未曝光题/预先固定的重复验证，以及关键候选实现正文的获取。新测试或路径变更需单独冻结计划；本次整理没有新增付费任务。
