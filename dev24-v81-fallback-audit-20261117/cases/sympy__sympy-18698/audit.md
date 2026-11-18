# sympy__sympy-18698

原结果：回退；实际源码计量 3195/14336，余 11141 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-18698/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-18698/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-18698/locator-wire/response-47.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-18698/tool-output.txt)

C完整行账本：sympy/polys/polytools.py:3210-3240; sympy/polys/polytools.py:6204-6218

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 12-01 R4_citation_not_delivered:sympy/polys/polyclasses.py:784

**误判：搜索证据遗漏**。784行 DMP.sqf_list 定义签名确在搜索结果；事实只报告“搜索命中，未读正文”，后文也标函数体未读完。

原回答片段：
```text
L4：- 搜索命中（未读正文）：sympy/polys/polyclasses.py:784 DMP.sqf_list、:789 sqf_list_include；sympy/polys/rings.py:2457 PolyElement.sqf_list。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "sympy/polys/polyclasses.py:784",
  "path": "sympy/polys/polyclasses.py",
  "start": 784,
  "end": 784
}
```

校验器按字面路径记账：无；另有实际搜索行：784

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 2,
    "path": "sympy/polys/polyclasses.py",
    "line": 784,
    "text": "    def sqf_list(f, all=False):"
  }
]
```

## 12-02 R4_citation_not_delivered:sympy/polys/rings.py:2457

**误判：搜索证据遗漏**。2457行 PolyElement.sqf_list 签名确在搜索结果；没有声称正文完整。

原回答片段：
```text
L4：- 搜索命中（未读正文）：sympy/polys/polyclasses.py:784 DMP.sqf_list、:789 sqf_list_include；sympy/polys/rings.py:2457 PolyElement.sqf_list。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "sympy/polys/rings.py:2457",
  "path": "sympy/polys/rings.py",
  "start": 2457,
  "end": 2457
}
```

校验器按字面路径记账：无；另有实际搜索行：2457

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 2,
    "path": "sympy/polys/rings.py",
    "line": 2457,
    "text": "    def sqf_list(f, all=False):"
  }
]
```

## 12-03 R1_body_incomplete_unmarked:sympy/polys/polytools.py:sqf_list

**边界：装饰器/覆盖口径**。C完整读完检索元数据所给6204-6218（15行），但 audit 仍判不完整。可能是检索器不含装饰器而校验器包含；AST实际span未持久化，不能确定只缺哪一行。

原回答片段：
```text
entities 候选：sympy/polys/polytools.py:sqf_list
L12：- sympy/polys/polytools.py:sqf_list 的 docstring 已读，但 _generic_factor_list 未读（搜索被预算拦截）。
```

校验器匹配依据：
```json
{
  "entity": "sympy/polys/polytools.py:sqf_list",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：sympy/polys/polytools.py:3210-3240; sympy/polys/polytools.py:6204-6218；该函数def区间内实际读到：[[6204, 6218]]；另有实际搜索行：3210,3239,6204

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "sympy/polys/polytools.py",
    "requested": {
      "cursor": null,
      "end_line": 6218,
      "path": "sympy/polys/polytools.py",
      "start_line": 6204
    },
    "delivered_metadata": {
      "end_column": 60,
      "end_line": 6218,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 6204,
      "total_lines": 7151
    },
    "cumulative_source_bytes": 1725
  },
  {
    "tool_index": 4,
    "path": "sympy/polys/polytools.py",
    "requested": {
      "cursor": null,
      "end_line": 3240,
      "path": "sympy/polys/polytools.py",
      "start_line": 3210
    },
    "delivered_metadata": {
      "end_column": 11,
      "end_line": 3240,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 3210,
      "total_lines": 7151
    },
    "cumulative_source_bytes": 2967
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 2,
    "path": "sympy/polys/polytools.py",
    "line": 3210,
    "text": "    def sqf_list(f, all=False):"
  },
  {
    "tool_index": 2,
    "path": "sympy/polys/polytools.py",
    "line": 3239,
    "text": "    def sqf_list_include(f, all=False):"
  },
  {
    "tool_index": 2,
    "path": "sympy/polys/polytools.py",
    "line": 6204,
    "text": "def sqf_list(f, *gens, **args):"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L4: - 搜索命中（未读正文）：sympy/polys/polyclasses.py:784 DMP.sqf_list、:789 sqf_list_include；sympy/polys/rings.py:2457 PolyElement.sqf_list。
L11: 未核验点
L12: - sympy/polys/polytools.py:sqf_list 的 docstring 已读，但 _generic_factor_list 未读（搜索被预算拦截）。
L13: - sympy/polys/polyclasses.py:DMP.sqf_list、sympy/polys/rings.py:PolyElement.sqf_list 仅见搜索命中，函数体未读完。
L14: - dup_sqf_list / dmp_sqf_list 未定位、未读；调用链未穷尽。
```

函数长度：{"start": 6204, "end": 6218, "length": 15, "provenance": "C检索元数据；def至末行，不含装饰器", "definition_excludes_decorators": true}

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。
