import json
import pickle
from pathlib import Path

from dependency_graph import RepoEntitySearcher
from dependency_graph.build_graph import (
    NODE_TYPE_FILE, NODE_TYPE_CLASS, NODE_TYPE_FUNCTION,
)
from plugins.location_tools.repo_ops import repo_ops
from util.runtime.execute_ipython import execute_ipython


# 准备真实图和工具使用的搜索环境
graph_path = Path("outputs/day1/graphs/psf__requests-3362.pkl")
with graph_path.open("rb") as f:
    graph = pickle.load(f)

searcher = RepoEntitySearcher(graph)
repo_ops.DP_GRAPH = graph
repo_ops.DP_GRAPH_ENTITY_SEARCHER = searcher
repo_ops.ALL_FILE = searcher.get_all_nodes_by_type(NODE_TYPE_FILE)
repo_ops.ALL_CLASS = searcher.get_all_nodes_by_type(NODE_TYPE_CLASS)
repo_ops.ALL_FUNC = searcher.get_all_nodes_by_type(NODE_TYPE_FUNCTION)

entity = "requests/models.py:Response.iter_content"
assert entity in graph

search_code = f"print(search_code_snippets(search_terms=[{entity!r}]))"
read_code = f"print(get_entity_contents(entity_names=[{entity!r}]))"

# 不开启记录时，各自的输出作为对照
search_baseline = execute_ipython(search_code)
read_baseline = execute_ipython(read_code)

# 两个工具共用一本账，每次调用应该只增加一条记录
records = {}
search_output = execute_ipython(search_code, return_records=records)
assert len(records.get(entity, [])) == 1, "搜索没有恰好记录一次"

read_first = execute_ipython(read_code, return_records=records)
assert len(records[entity]) == 2, "第一次实体读取没有接入同一本账"

read_second = execute_ipython(read_code, return_records=records)
assert len(records[entity]) == 3, "第二次实体读取没有恰好记录一次"

assert search_output == search_baseline, "搜索输出发生变化"
assert read_first == read_second == read_baseline, "实体读取输出发生变化"

history = records[entity]
assert history[0]["repeated"] is False
assert history[1]["content"] == history[2]["content"]
assert history[2]["repeated"] is True, "未识别出重复的实体读取"

# 换一本空账，实体读取也应该从“没有返回过”开始
fresh_records = {}
execute_ipython(read_code, return_records=fresh_records)
assert len(fresh_records.get(entity, [])) == 1
assert fresh_records[entity][0]["repeated"] is False
assert len(records[entity]) == 3, "新调用污染了旧账"

assert json.loads(json.dumps(records)) == records

print("实体：", entity)
print("三次调用的重复标记：", [item["repeated"] for item in history])
print("通过：两个工具共用记录、输出不变、重复识别、新账隔离、JSON 转换")

# 用简短函数名查询，检查 preview 分支
preview_code = "print(search_code_snippets(search_terms=['iter_content']))"
preview_baseline = execute_ipython(preview_code)

preview_records = {}
preview_first = execute_ipython(
    preview_code, return_records=preview_records
)
preview_second = execute_ipython(
    preview_code, return_records=preview_records
)

preview_history = preview_records.get(entity, [])
modes = [item["mode"] for item in preview_history]
flags = [item["repeated"] for item in preview_history]

print("简短名称查询的展示模式：", modes)
print("简短名称查询的重复标记：", flags)

assert modes == ["preview", "preview"], "没有按预期记录两次 preview"
assert flags == [False, True], "preview 重复标记不符合预期"
assert preview_baseline == preview_first == preview_second, "preview 输出发生变化"

print("通过：preview 分支记录、重复识别、输出不变")

# 从真实图中选择一个有超过 3 个候选的函数名
all_paths = [item["name"] for item in repo_ops.ALL_FILE]

for name in sorted(searcher.global_name_dict):
    if repo_ops.is_test_file(name) or searcher.has_node(name):
        continue

    matches = repo_ops.search_entity_in_global_dict(
        name, include_files=all_paths
    )
    if (
        matches
        and set(matches) == {NODE_TYPE_FUNCTION}
        and len(matches[NODE_TYPE_FUNCTION]) > 3
    ):
        fold_term = name
        expected_entities = set(matches[NODE_TYPE_FUNCTION])
        break
else:
    raise AssertionError("没有找到适合验证 fold 的函数名")

print("fold 查询词：", fold_term)
print("预期候选数量：", len(expected_entities))

fold_code = (
    f"print(search_code_snippets("
    f"search_terms=[{fold_term!r}], file_path_or_pattern=None))"
)
fold_baseline = execute_ipython(fold_code)

fold_records = {}
fold_first = execute_ipython(fold_code, return_records=fold_records)
fold_second = execute_ipython(fold_code, return_records=fold_records)

assert set(fold_records) == expected_entities, "记录的实体有遗漏或多出"
assert fold_baseline == fold_first == fold_second, "fold 输出发生变化"

for nid, entries in fold_records.items():
    assert [item["mode"] for item in entries] == ["fold", "fold"], nid
    assert [item["repeated"] for item in entries] == [False, True], nid

print("通过：fold 所有候选均记录、重复识别、输出不变")

# 按行查询需要用到图中的包含关系
from dependency_graph import RepoDependencySearcher

repo_ops.DP_GRAPH_DEPENDENCY_SEARCHER = RepoDependencySearcher(graph)

snippet_file = "requests/models.py"
snippet_line = 1

assert repo_ops.get_module_name_by_line_num(
    snippet_file, snippet_line
) is None, "所选行位于类或函数内，需要换一行"

snippet_code = (
    f"print(search_code_snippets("
    f"file_path_or_pattern={snippet_file!r}, "
    f"line_nums=[{snippet_line}]))"
)
snippet_baseline = execute_ipython(snippet_code)

snippet_records = {}
snippet_first = execute_ipython(
    snippet_code, return_records=snippet_records
)
snippet_second = execute_ipython(
    snippet_code, return_records=snippet_records
)

# 这个按行查询分支使用文件路径作为 nid
assert set(snippet_records) == {snippet_file}, "代码片段的记录键不符合预期"
snippet_history = snippet_records[snippet_file]
modes = [item["mode"] for item in snippet_history]
flags = [item["repeated"] for item in snippet_history]

print("按行查询的展示模式：", modes)
print("按行查询的重复标记：", flags)

assert modes == ["code_snippet", "code_snippet"], "没有走到代码片段分支"
assert flags == [False, True], "代码片段重复标记不符合预期"
assert snippet_baseline == snippet_first == snippet_second, "代码片段输出发生变化"

print("通过：code_snippet 分支记录、重复识别、输出不变")