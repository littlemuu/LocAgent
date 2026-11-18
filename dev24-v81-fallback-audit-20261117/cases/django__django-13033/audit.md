# django__django-13033

原结果：回退；实际源码计量 5200/14336，余 9136 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13033/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13033/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13033/locator-wire/response-23.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13033/tool-output.txt)

C完整行账本：django/db/models/sql/compiler.py:700-767

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 06-01 R1_cursor_unfinished_unmarked

**误判：关键词格式**。已写“未读完：cursor=…未续读（实际完整行仅700-767）”；只因未含字面词“分页”而触发。cursor 使用错误确实存在，但已披露未续读。

原回答片段：
```text
L16：- django/db/models/sql/compiler.py 的 find_ordering_name 未读完：cursor=rf1_dd8acea62d3a87e1f94f5a755316a0926bec6e5119735df6515d77dfd4c23eca 未续读（实际完整行仅 700-767）。
```

校验器匹配依据：
```json
{
  "condition": "pending非空且未核验段缺少字面“未读完”或“分页”",
  "pending": {
    "rf1_dd8acea62d3a87e1f94f5a755316a0926bec6e5119735df6515d77dfd4c23eca": "django/db/models/sql/compiler.py"
  }
}
```

相关文件账本：django/db/models/sql/compiler.py:700-767

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "django/db/models/sql/compiler.py",
    "requested": {
      "cursor": null,
      "end_line": 800,
      "path": "django/db/models/sql/compiler.py",
      "start_line": 700
    },
    "delivered_metadata": {
      "end_column": 77,
      "end_line": 767,
      "next_cursor": "rf1_dd8acea62d3a87e1f94f5a755316a0926bec6e5119735df6515d77dfd4c23eca",
      "start_column": 0,
      "start_line": 700,
      "total_lines": 1604
    },
    "cumulative_source_bytes": 4924
  },
  {
    "tool_index": 5,
    "path": "django/db/models/sql/compiler.py",
    "requested": {
      "cursor": "rf1_dd8acea62d3a87e1f94f5a755316a0926bec6e5119735df6515d77dfd4c23eca",
      "end_line": 749,
      "path": "django/db/models/sql/compiler.py",
      "start_line": 715
    },
    "delivered_metadata": {
      "error": "tool_error",
      "error_type": "ValueError"
    },
    "cumulative_source_bytes": 5086
  }
]
```

原答中的未读/未核验相关上下文：
```text
L15: 未核验点
L16: - django/db/models/sql/compiler.py 的 find_ordering_name 未读完：cursor=rf1_dd8acea62d3a87e1f94f5a755316a0926bec6e5119735df6515d77dfd4c23eca 未续读（实际完整行仅 700-767）。
L17: - get_order_dir 定义未读到，其 DESC 解析与 default_order 语义未核验。
L18: - query.setup_joins / trim_joins 未读，别名复用与自引用 JOIN 生成逻辑未核验。
```

函数长度："不适用：分页规则"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。
