# sympy__sympy-13480

原结果：回退；实际源码计量 4751/14336，余 9585 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-13480/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-13480/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-13480/locator-wire/response-90.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-13480/tool-output.txt)

C完整行账本：sympy/functions/elementary/hyperbolic.py:557-607; sympy/functions/elementary/trigonometric.py:1295-1320

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 23-01 R4_citation_not_delivered:hyperbolic.py:590

**边界：路径缩写**。完整hyperbolic.py:590源行确已在C read_file交付；原答用唯一可对应的basename。不过冻结提示明确要求完整相对路径，接受缩写属格式契约放宽，不计为确定误判。

原回答片段：
```text
L6：- 搜索命中：cotm 仅出现在 hyperbolic.py:590 与 trigonometric.py:1307-1310。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "hyperbolic.py:590",
  "path": "hyperbolic.py",
  "start": 590,
  "end": 590
}
```

校验器按字面路径记账：无；按唯一后缀候选对应：sympy/functions/elementary/hyperbolic.py:557-607；另有实际搜索行：590

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "sympy/functions/elementary/hyperbolic.py",
    "requested": {
      "cursor": null,
      "end_line": 607,
      "path": "sympy/functions/elementary/hyperbolic.py",
      "start_line": 557
    },
    "delivered_metadata": {
      "end_column": 34,
      "end_line": 607,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 557,
      "total_lines": 1403
    },
    "cumulative_source_bytes": 3632
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/hyperbolic.py",
    "line": 590,
    "text": "                    if cotm is S.ComplexInfinity:"
  }
]
```

## 23-02 R4_citation_not_delivered:trigonometric.py:1307-1310

**边界：路径缩写**。完整trigonometric.py:1307-1310均已读；仅basename导致lookup失败。和上一条一样，证据真实但违反完整路径字面要求，归边界。

原回答片段：
```text
L6：- 搜索命中：cotm 仅出现在 hyperbolic.py:590 与 trigonometric.py:1307-1310。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "trigonometric.py:1307-1310",
  "path": "trigonometric.py",
  "start": 1307,
  "end": 1310
}
```

校验器按字面路径记账：无；按唯一后缀候选对应：sympy/functions/elementary/trigonometric.py:1295-1320；另有实际搜索行：1307,1308,1310

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "sympy/functions/elementary/trigonometric.py",
    "requested": {
      "cursor": null,
      "end_line": 1320,
      "path": "sympy/functions/elementary/trigonometric.py",
      "start_line": 1295
    },
    "delivered_metadata": {
      "end_column": 34,
      "end_line": 1320,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 1295,
      "total_lines": 2817
    },
    "cumulative_source_bytes": 4751
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1307,
    "text": "                cotm = cot(m)"
  },
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1308,
    "text": "                if cotm is S.ComplexInfinity:"
  },
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1310,
    "text": "                else: # cotm == 0"
  }
]
```

## 23-03 R1_body_incomplete_unmarked:sympy/functions/elementary/hyperbolic.py:coth.eval

**边界：装饰器/覆盖口径**。检索给出的coth.eval def范围557-607全部交付，仍被判不完整；可能漏装饰器，日志无原AST完整span。不能把正文完整和带装饰器的实体完整混为一谈。

原回答片段：
```text
entities 候选：sympy/functions/elementary/hyperbolic.py:coth.eval
L9：- 待验证假设：sympy/functions/elementary/hyperbolic.py:coth.eval 第 589-590 行变量名不一致（cothm 赋值、cotm 使用）导致 NameError，属复制自 sympy/functions/elementary/trigonometric.py:cot.eval 时未改名。
```

校验器匹配依据：
```json
{
  "entity": "sympy/functions/elementary/hyperbolic.py:coth.eval",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：sympy/functions/elementary/hyperbolic.py:557-607；该函数def区间内实际读到：[[557, 607]]；另有实际搜索行：590

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "sympy/functions/elementary/hyperbolic.py",
    "requested": {
      "cursor": null,
      "end_line": 607,
      "path": "sympy/functions/elementary/hyperbolic.py",
      "start_line": 557
    },
    "delivered_metadata": {
      "end_column": 34,
      "end_line": 607,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 557,
      "total_lines": 1403
    },
    "cumulative_source_bytes": 3632
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/hyperbolic.py",
    "line": 590,
    "text": "                    if cotm is S.ComplexInfinity:"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L13: 未核验点
L14: - 未读 _peeloff_ipi 实现，无法确认 m 的取值与 coth(m) 是否恒为 0 或 ComplexInfinity。
L15: - 未读 coth 类定义头部与 docstring 之外的上下文（如 _eval_* 方法），未验证其他分支。
```

函数长度：{"start": 557, "end": 607, "length": 51, "provenance": "C检索元数据；def至末行，不含装饰器", "definition_excludes_decorators": true}

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。

## 23-04 R1_body_incomplete_unmarked:sympy/functions/elementary/trigonometric.py:cot.eval

**真违规：只读中部且未标**。cot.eval只收到1295-1320中部，没有函数头；用其作为复制来源参与推断，却没有cot.eval未读完标注。关于coth类上下文未读的声明不是cot.eval标注。

原回答片段：
```text
entities 候选：sympy/functions/elementary/trigonometric.py:cot.eval
L9：- 待验证假设：sympy/functions/elementary/hyperbolic.py:coth.eval 第 589-590 行变量名不一致（cothm 赋值、cotm 使用）导致 NameError，属复制自 sympy/functions/elementary/trigonometric.py:cot.eval 时未改名。
```

校验器匹配依据：
```json
{
  "entity": "sympy/functions/elementary/trigonometric.py:cot.eval",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：sympy/functions/elementary/trigonometric.py:1295-1320；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：1307,1308,1310

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "sympy/functions/elementary/trigonometric.py",
    "requested": {
      "cursor": null,
      "end_line": 1320,
      "path": "sympy/functions/elementary/trigonometric.py",
      "start_line": 1295
    },
    "delivered_metadata": {
      "end_column": 34,
      "end_line": 1320,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 1295,
      "total_lines": 2817
    },
    "cumulative_source_bytes": 4751
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1307,
    "text": "                cotm = cot(m)"
  },
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1308,
    "text": "                if cotm is S.ComplexInfinity:"
  },
  {
    "tool_index": 1,
    "path": "sympy/functions/elementary/trigonometric.py",
    "line": 1310,
    "text": "                else: # cotm == 0"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L13: 未核验点
L14: - 未读 _peeloff_ipi 实现，无法确认 m 的取值与 coth(m) 是否恒为 0 或 ComplexInfinity。
L15: - 未读 coth 类定义头部与 docstring 之外的上下文（如 _eval_* 方法），未验证其他分支。
```

函数长度："未知"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。
