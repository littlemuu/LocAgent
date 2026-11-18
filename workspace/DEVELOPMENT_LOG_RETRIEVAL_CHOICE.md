
## 2026-11-12 北京时间｜自主检索未选择的离线分析与说明修订

- 审阅原始真实请求/回包：LocAgent 在前三轮均开放且 tool_choice=auto；模型选正文搜索 webhook、列出 10 路径后批量读取 7 文件，第 4 轮正常 finish。无检索失败记录、无公开放弃检索理由；不能强行归因。
- 五个人工选择查询通过现有离线 LocAgent 接口验证：webhook 在正文命中但实体索引为空；retry、delivery_key、完整实体 ID 返回源码，随机不存在词为空。工具能力区别得到验证，但模型当时未看过这些检索输出，不能用它们解释模型内部选择。
- 仅补清 RETRIEVE 工具描述：标识符词法检索、精确 ID、最多五候选、源码片段与正文搜索的区别，明确无语义检索/调用图遍历。无题目专属提示、不强制检索；题面、预算、工具顺序、协议和算法未改。
- SDK 7/7 测试通过；双组离线回放各 3 次模拟响应正常 finish；一次脚本指定检索的 1642 字节观察结果进入下一次模拟请求，分类仍为 scripted_fixture。五个查询探针网络尝试 0。真实模型调用 0，未读取 Key、未创建新 grant。
- 新首轮出站请求与旧真实请求仅检索描述不同；新方案 hash `fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f`。未来试跑拟同样两组各最多 4 次、总 8 次/17 元，未授权；启动前核价，异常停止，不补跑。
- 四个真实账本 SHA256 均未变。详见工作区 `RETRIEVAL_CHOICE_ANALYSIS.md`、`verification/RETRIEVAL_CHOICE_OFFLINE_REVIEW.json` 及 `verification/retrieval-choice-query-probes.json`。未证明模型会自主选择或存在检索收益。
