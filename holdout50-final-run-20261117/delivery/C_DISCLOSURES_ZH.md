# C 组50题披露与工具错误

定位交付45/50。共44条披露，27题至少一条；R1=22、R2=0、R3=2、R4=20。交付45题中全回退0、validator_error非空0。5题定位首个请求HTTP 402，相关字段未观测，不记为0。read_file错误按单份locator tool_audit的记录去重计数，共20次、14题；未交付5题没有完整工具审计，标未观测。validator_error在已交付题中原值为null（无错误），在未交付题中null表示未观测，表内区分。

| 题号 / ID | 原评分 | 披露条数 | R1/R2/R3/R4 | 全回退 | validator_error | read_file错误 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 / astropy__astropy-14096 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 2 / astropy__astropy-7166 | False | 3 | 0/0/0/3 | 否 | null（无错误） | 0 |
| 3 / astropy__astropy-7336 | False | 2 | 1/0/1/0 | 否 | null（无错误） | 1 |
| 4 / astropy__astropy-8872 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 5 / django__django-13821 | True | 1 | 1/0/0/0 | 否 | null（无错误） | 1 |
| 6 / django__django-14539 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 7 / django__django-15380 | True | 2 | 1/0/1/0 | 否 | null（无错误） | 0 |
| 8 / django__django-15572 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 1 |
| 9 / django__django-15629 | False | 1 | 1/0/0/0 | 否 | null（无错误） | 2 |
| 10 / matplotlib__matplotlib-24177 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 11 / matplotlib__matplotlib-24637 | False | 2 | 2/0/0/0 | 否 | null（无错误） | 0 |
| 12 / matplotlib__matplotlib-26208 | False | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 13 / matplotlib__matplotlib-26291 | True | 1 | 1/0/0/0 | 否 | null（无错误） | 1 |
| 14 / matplotlib__matplotlib-26342 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 1 |
| 15 / mwaskom__seaborn-3069 | False | 1 | 0/0/0/1 | 否 | null（无错误） | 2 |
| 16 / mwaskom__seaborn-3187 | False | 1 | 0/0/0/1 | 否 | null（无错误） | 0 |
| 17 / pallets__flask-5014 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 18 / psf__requests-1142 | True | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 19 / psf__requests-1724 | False | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 20 / psf__requests-1766 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 21 / psf__requests-2931 | False | 4 | 1/0/0/3 | 否 | null（无错误） | 0 |
| 22 / psf__requests-5414 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 23 / pydata__xarray-4075 | True | 1 | 0/0/0/1 | 否 | null（无错误） | 0 |
| 24 / pydata__xarray-4695 | True | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 25 / pydata__xarray-6721 | True | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 26 / pydata__xarray-6938 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 27 / pylint-dev__pylint-4661 | False | 3 | 0/0/0/3 | 否 | null（无错误） | 2 |
| 28 / pylint-dev__pylint-4970 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 1 |
| 29 / pylint-dev__pylint-6903 | True | 2 | 2/0/0/0 | 否 | null（无错误） | 0 |
| 30 / pylint-dev__pylint-7277 | True | 2 | 0/0/0/2 | 否 | null（无错误） | 3 |
| 31 / pylint-dev__pylint-8898 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 32 / pytest-dev__pytest-10081 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 1 |
| 33 / pytest-dev__pytest-5631 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 34 / pytest-dev__pytest-5787 | False | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 35 / pytest-dev__pytest-7236 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 1 |
| 36 / pytest-dev__pytest-7521 | True | 3 | 2/0/0/1 | 否 | null（无错误） | 2 |
| 37 / scikit-learn__scikit-learn-11578 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 38 / scikit-learn__scikit-learn-12973 | True | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 39 / scikit-learn__scikit-learn-25973 | True | 2 | 2/0/0/0 | 否 | null（无错误） | 1 |
| 40 / scikit-learn__scikit-learn-26323 | False | 1 | 1/0/0/0 | 否 | null（无错误） | 0 |
| 41 / sphinx-doc__sphinx-8035 | False | 2 | 1/0/0/1 | 否 | null（无错误） | 0 |
| 42 / sphinx-doc__sphinx-8265 | False | 1 | 0/0/0/1 | 否 | null（无错误） | 0 |
| 43 / sphinx-doc__sphinx-8269 | False | 1 | 0/0/0/1 | 否 | null（无错误） | 0 |
| 44 / sphinx-doc__sphinx-8551 | False | 2 | 0/0/0/2 | 否 | null（无错误） | 0 |
| 45 / sphinx-doc__sphinx-9281 | False | 0 | 0/0/0/0 | 否 | null（无错误） | 0 |
| 46 / sympy__sympy-13091 | None | 未观测 | 未观测 | 未观测 | 未观测 | 0 |
| 47 / sympy__sympy-13757 | None | 未观测 | 未观测 | 未观测 | 未观测 | 0 |
| 48 / sympy__sympy-13877 | None | 未观测 | 未观测 | 未观测 | 未观测 | 0 |
| 49 / sympy__sympy-15809 | None | 未观测 | 未观测 | 未观测 | 未观测 | 0 |
| 50 / sympy__sympy-22914 | None | 未观测 | 未观测 | 未观测 | 未观测 | 0 |

逐项错误参数和原错误内容见 [C-disclosures-per-task.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/C-disclosures-per-task.json)；定位原文与披露审计位于 [原始证据目录](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/evidence/run/trial)。
