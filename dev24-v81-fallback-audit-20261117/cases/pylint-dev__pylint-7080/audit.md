# pylint-dev__pylint-7080

原结果：回退；实际源码计量 14285/14336，余 51 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pylint-dev__pylint-7080/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pylint-dev__pylint-7080/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pylint-dev__pylint-7080/locator-wire/response-27.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pylint-dev__pylint-7080/tool-output.txt)

C完整行账本：pylint/lint/pylinter.py:580-714; pylint/lint/pylinter.py:760-800

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 07-01 R4_citation_not_delivered:pylint/lint/pylinter.py:1014

**误判：搜索证据遗漏**。事实明确标为“搜索命中，未读正文”，所引1014行赋值原文确已由 search_text 返回；这里没有声称读完整函数。

原回答片段：
```text
L6：- pylint/lint/pylinter.py:1014（搜索命中，未读正文）：`self._ignore_paths = self.linter.config.ignore_paths`。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "pylint/lint/pylinter.py:1014",
  "path": "pylint/lint/pylinter.py",
  "start": 1014,
  "end": 1014
}
```

校验器按字面路径记账：pylint/lint/pylinter.py:580-714; pylint/lint/pylinter.py:760-800；另有实际搜索行：1014

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 700,
      "path": "pylint/lint/pylinter.py",
      "start_line": 580
    },
    "delivered_metadata": {
      "end_column": 80,
      "end_line": 661,
      "next_cursor": "rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2",
      "start_column": 0,
      "start_line": 580,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 9328
  },
  {
    "tool_index": 4,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 800,
      "path": "pylint/lint/pylinter.py",
      "start_line": 760
    },
    "delivered_metadata": {
      "end_column": 26,
      "end_line": 800,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 760,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 11438
  },
  {
    "tool_index": 5,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 760,
      "path": "pylint/lint/pylinter.py",
      "start_line": 661
    },
    "delivered_metadata": {
      "end_column": 32,
      "end_line": 714,
      "next_cursor": "rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161",
      "start_column": 0,
      "start_line": 661,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 14285
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "pylint/lint/pylinter.py",
    "line": 1014,
    "text": "        self._ignore_paths = self.linter.config.ignore_paths"
  }
]
```

## 07-02 R1_body_incomplete_unmarked:pylint/lint/pylinter.py:PyLinter._iterate_file_descrs

**真违规：缺少函数特定缺口标注**。候选 _iterate_file_descrs 只收到760-770的签名尾部/docstring/实现；函数定义头不在已读区间。未核验点没有逐项说明该函数缺头，泛指两个分页且第二处范围描述有误，不能确定覆盖此缺口。

原回答片段：
```text
entities 候选：pylint/lint/pylinter.py:PyLinter._iterate_file_descrs
L4：- pylint/lint/pylinter.py:767-770：`_iterate_file_descrs` 对 `_expand_files` 的每个描述符再调用 `should_analyze_file` 过滤。
```

校验器匹配依据：
```json
{
  "entity": "pylint/lint/pylinter.py:PyLinter._iterate_file_descrs",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：pylint/lint/pylinter.py:580-714; pylint/lint/pylinter.py:760-800；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：604,778,1014,634

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 700,
      "path": "pylint/lint/pylinter.py",
      "start_line": 580
    },
    "delivered_metadata": {
      "end_column": 80,
      "end_line": 661,
      "next_cursor": "rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2",
      "start_column": 0,
      "start_line": 580,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 9328
  },
  {
    "tool_index": 4,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 800,
      "path": "pylint/lint/pylinter.py",
      "start_line": 760
    },
    "delivered_metadata": {
      "end_column": 26,
      "end_line": 800,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 760,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 11438
  },
  {
    "tool_index": 5,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 760,
      "path": "pylint/lint/pylinter.py",
      "start_line": 661
    },
    "delivered_metadata": {
      "end_column": 32,
      "end_line": 714,
      "next_cursor": "rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161",
      "start_column": 0,
      "start_line": 661,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 14285
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "pylint/lint/pylinter.py",
    "line": 604,
    "text": "                        self.config.ignore_paths,"
  },
  {
    "tool_index": 1,
    "path": "pylint/lint/pylinter.py",
    "line": 778,
    "text": "            self._ignore_paths,"
  },
  {
    "tool_index": 1,
    "path": "pylint/lint/pylinter.py",
    "line": 1014,
    "text": "        self._ignore_paths = self.linter.config.ignore_paths"
  },
  {
    "tool_index": 2,
    "path": "pylint/lint/pylinter.py",
    "line": 634,
    "text": "        if self.config.recursive:"
  }
]
```

原答中的未读/未核验相关上下文：
```text
L6: - pylint/lint/pylinter.py:1014（搜索命中，未读正文）：`self._ignore_paths = self.linter.config.ignore_paths`。
L10: - 待验证假设：`_is_ignored_file` 对 `ignore_paths` 的匹配语义（是否用 `re.match` 于绝对路径、是否对文件路径也生效）决定该假设成立与否；其函数体未读到。
L13: 未核验点
L14: - `_is_ignored_file` 函数体未读（仅见调用点）。
L15: - `expand_modules`（pylint/lint/expand_modules.py）未读。
L16: - `should_analyze_file` 函数体未读。
L17: - pylinter.py 两处分页未续读：cursor=rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2（661-714 之后）与 cursor=rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161（760-800 之后）。
```

函数长度："未知"

预算归因：总字节预算耗尽对继续读取头部缺口有直接限制（最后余51字节）；最初读取又从签名尾部760开始。不是唯一原因。

## 07-03 R1_cursor_unfinished_unmarked

**误判：关键词格式**。明确写“两处分页未续读”并列出两个实际 pending cursor；仅缺“未读完”字样。范围描述不精确不等于未声明分页未读。

原回答片段：
```text
L17：- pylinter.py 两处分页未续读：cursor=rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2（661-714 之后）与 cursor=rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161（760-800 之后）。
```

校验器匹配依据：
```json
{
  "condition": "pending非空且未核验段缺少字面“未读完”或“分页”",
  "pending": {
    "rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161": "pylint/lint/pylinter.py",
    "rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2": "pylint/lint/pylinter.py"
  }
}
```

相关文件账本：pylint/lint/pylinter.py:580-714; pylint/lint/pylinter.py:760-800

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 700,
      "path": "pylint/lint/pylinter.py",
      "start_line": 580
    },
    "delivered_metadata": {
      "end_column": 80,
      "end_line": 661,
      "next_cursor": "rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2",
      "start_column": 0,
      "start_line": 580,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 9328
  },
  {
    "tool_index": 4,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 800,
      "path": "pylint/lint/pylinter.py",
      "start_line": 760
    },
    "delivered_metadata": {
      "end_column": 26,
      "end_line": 800,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 760,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 11438
  },
  {
    "tool_index": 5,
    "path": "pylint/lint/pylinter.py",
    "requested": {
      "cursor": null,
      "end_line": 760,
      "path": "pylint/lint/pylinter.py",
      "start_line": 661
    },
    "delivered_metadata": {
      "end_column": 32,
      "end_line": 714,
      "next_cursor": "rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161",
      "start_column": 0,
      "start_line": 661,
      "total_lines": 1253
    },
    "cumulative_source_bytes": 14285
  }
]
```

原答中的未读/未核验相关上下文：
```text
L6: - pylint/lint/pylinter.py:1014（搜索命中，未读正文）：`self._ignore_paths = self.linter.config.ignore_paths`。
L10: - 待验证假设：`_is_ignored_file` 对 `ignore_paths` 的匹配语义（是否用 `re.match` 于绝对路径、是否对文件路径也生效）决定该假设成立与否；其函数体未读到。
L13: 未核验点
L14: - `_is_ignored_file` 函数体未读（仅见调用点）。
L15: - `expand_modules`（pylint/lint/expand_modules.py）未读。
L16: - `should_analyze_file` 函数体未读。
L17: - pylinter.py 两处分页未续读：cursor=rf1_63bf19ad360819c9be417057f231785f9d672e34a3ca51579058d25cad07e9e2（661-714 之后）与 cursor=rf1_1b099d8eee39f638d9981f25ca1ed18d40cbbd1d9f42b6bfd0ef39c9617f3161（760-800 之后）。
```

函数长度："不适用：分页规则"

预算归因：题级预算耗尽，两个cursor未续读；原答已披露分页未续读，触发本条却是词面标注误判。
