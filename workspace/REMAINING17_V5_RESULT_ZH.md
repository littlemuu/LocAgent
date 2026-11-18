# 剩余 17 题 v5 开发批次结果

状态：完成。完成配对 17/17；实际传输启动 124，回包 124，预留记录 124。

本批次只覆盖旧批次未启动的 17 题，使用通过 Sisyphus 验证的新终答协议。前 19 对 v4 与 Sisyphus 单题结果均保留、未混入本批分母。

|题目|原生状态 / 请求 / 首次参考实体名次|OpenHands 状态 / 请求 / 首次参考实体名次|SDK 检索调用|
|---|---|---|---|
|sgkit-dev__sgkit-447|completed / 4 / 1|completed / 4 / 1|0|
|spotify__luigi-3308|completed / 4 / 1|completed / 3 / 1|0|
|spotify__luigi-3324|completed / 4 / 1|completed / 4 / 1|1|
|tobymao__sqlglot-3167|completed / 3 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-3417|completed / 3 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-3436|completed / 4 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-3901|completed / 3 / 未命中|completed / 4 / 1|1|
|tobymao__sqlglot-4366|completed / 4 / 未命中|completed / 4 / 1|1|
|tobymao__sqlglot-4369|completed / 3 / 2|completed / 4 / 1|2|
|tobymao__sqlglot-4415|completed / 3 / 未命中|completed / 3 / 未命中|0|
|tobymao__sqlglot-4480|completed / 3 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-4515|completed / 3 / 2|completed / 4 / 2|0|
|tobymao__sqlglot-4519|completed / 3 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-4523|completed / 4 / 1|completed / 4 / 1|0|
|tobymao__sqlglot-4524|completed / 3 / 未命中|completed / 4 / 未命中|0|
|tobymao__sqlglot-4526|completed / 4 / 1|completed / 3 / 1|1|
|xCDAT__xcdat-689|completed / 4 / 未命中|completed / 4 / 3|1|

## 汇总口径

使用原冻结标签与 strict Acc/Recall/Hit@1/3/5；未知合法预测保留，不自动纠正。技术失败与定位未命中分开；未完成不作为成功回答评分。下面同时报告完成组分母与计划分母，非独立测试。

- 原生适配组：完成 17/17，技术失败 0，未启动 0；请求 59，输入/输出 token 379017/14076。
  - k=1：Hit 完成分母 10/17；计划分母 10/17；Acc 均值(完成分母) 0.5882352941176471；Recall 均值(完成分母) 0.5490196078431373。
  - k=3：Hit 完成分母 12/17；计划分母 12/17；Acc 均值(完成分母) 0.6470588235294118；Recall 均值(完成分母) 0.6764705882352942。
  - k=5：Hit 完成分母 12/17；计划分母 12/17；Acc 均值(完成分母) 0.6470588235294118；Recall 均值(完成分母) 0.6764705882352942。
- OpenHands 组：完成 17/17，技术失败 0，未启动 0；请求 65，输入/输出 token 299993/15178。
  - k=1：Hit 完成分母 13/17；计划分母 13/17；Acc 均值(完成分母) 0.7647058823529411；Recall 均值(完成分母) 0.6813725490196079。
  - k=3：Hit 完成分母 15/17；计划分母 15/17；Acc 均值(完成分母) 0.7647058823529411；Recall 均值(完成分母) 0.8039215686274509。
  - k=5：Hit 完成分母 15/17；计划分母 15/17；Acc 均值(完成分母) 0.7647058823529411；Recall 均值(完成分母) 0.8137254901960784。

SDK 有 6 道实际执行题调用 LocAgent，共 7 次，正常返回 7 次。工具返回不报错不等于证据有用；两套完整系统的结果不能归因于检索。

## 预算与费用

本次输入 679010、输出 29254 token；响应计量费用保守上界 ¥1.592052，未知预留 ¥0.000000。新额度最多 136 次/289 元；既有批次累计到本次 332 条请求预留记录，已计量费用上界 ¥3.946826（另计上列未知预留）。
依据 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 的峰谷/缓存费率，已知缓存用量部分估算 ¥0.431372–¥0.862744；缓存用量未知 0 次。未查询实际账单，不将估算、预留或保守记账视为真实扣款。

## 可追溯性与限制

计划在 verification/remaining17-v5-batch-v1/live.json；离线 21 项保护测试与全 17 对/136 次模拟请求先通过。10 个运行行为模块与 Sisyphus 版经包名归一化后相同，仅变更批次范围、原顺序及账本绑定。发送题面、提示、工具定义、相关源码证据和各组自身会话，运行不加载 gold 或参考补丁；评分仅在批次停止后离线完成。
问题是已用于项目开发的 development 集。结构核验不等于全部标签经过语义裁定，参考实体数量及既有标注风险逐题保留在 analysis.json。不能混合新旧版本声明统一 37 题性能，也不能仅凭这些结果说明检索因果效果。
原始请求/回包、模型调用及 SDK 工具轨迹均位于本批 authority/run/children；分析文件是 analysis.json。历史输出不覆盖，异常不重试。

## 原 37 题覆盖状态

全部 37 题现在都有完成的双组记录：前 19 题为 v4，Sisyphus 和本次 17 题为相同运行行为的 v5。仅汇总完成覆盖，不合并成统一版本成绩。逐题版本映射见 `verification/remaining17-v5-live-v1/coverage-37.json`。本次 17 题中 13 题来自 SQLGlot，仓库分布不均，不能据此推断广泛仓库表现。
