---
dataset_info:
  features:
  - name: repo
    dtype: string
  - name: instance_id
    dtype: string
  - name: base_commit
    dtype: string
  - name: patch
    dtype: string
  - name: test_patch
    dtype: string
  - name: problem_statement
    dtype: string
  - name: hints_text
    dtype: string
  - name: created_at
    dtype: int64
  - name: labels
    sequence: string
  - name: category
    dtype: string
  - name: edit_functions
    sequence: string
  - name: added_functions
    sequence: string
  - name: edit_functions_length
    dtype: int64
  - name: __index_level_0__
    dtype: int64
  splits:
  - name: test
    num_bytes: 8489578
    num_examples: 560
  download_size: 3084430
  dataset_size: 8489578
configs:
- config_name: default
  data_files:
  - split: test
    path: data/test-*
---

# LOC-BENCH: A Benchmark for Code Localization

LOC-BENCH is a dataset specifically designed to evaluate code localization methods in software repositories. LOC-BENCH provides diverse issues, including bug reports, feature requests, security vulnerabilities, and performance optimizations.

Code: https://github.com/gersteinlab/LocAgent

## 📊 Details
[`Loc-Bench_V1`](https://huggingface.co/datasets/czlll/Loc-Bench_V1) is our **official** dataset for comparison with our approach.

The table below shows the distribution of categories in the dataset.
| category | count |
|:---------|:---------|
| Bug Report  | 242  |
| Feature Request  | 150  |
| Performance Issue  | 139  |
| Security Vulnerability  | 29  |
<details>
  <summary>Previous Versions</summary>

  - [`Loc-Bench_V0.1`](https://huggingface.co/datasets/czlll/Loc-Bench_V0.1): The dataset used in [the early version of our paper](https://arxiv.org/abs/2503.09089).
  Some examples in this dataset do not involve function-level code modifications but instead focus on modifying classes.
  V1 filters out 100 examples without function-level code modifications, creating a cleaner subset of the dataset.
  - [`Loc-Bench_V0.2`](https://huggingface.co/datasets/czlll/Loc-Bench_V0.2): Filtering out examples that do not involve function-level code modifications and then supplementing the dataset to restore it to the original size of 660 examples.
</details>

## 🔧 How to Use
You can easily load LOC-BENCH using Hugging Face's datasets library:
```
from datasets import load_dataset

dataset = load_dataset("czlll/Loc-Bench_V1", split="test")

```

## 📄 Citation
If you use LOC-BENCH in your research, please cite our paper:
```
@article{chen2025locagent,
title={LocAgent: Graph-Guided LLM Agents for Code Localization},
author={Chen, Zhaoling and Tang,Xiangru and Deng,Gangda and Wu,Fang and Wu,Jialong and Jiang,Zhiwei and Prasanna,Viktor and Cohan,Arman and Wang,Xingyao},
journal={arXiv preprint arXiv:2503.09089},
year={2025}
}
```