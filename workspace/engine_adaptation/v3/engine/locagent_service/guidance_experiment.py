"""Explicit candidate-guidance axis; suppression remains fixed off."""
import json
from pathlib import Path

COHORT = "candidate-guidance10"
CONFIG_NAME = "locagent_service/candidate_guidance_cohort.json"
IDS = [
    "matplotlib__matplotlib-22711", "django__django-11179",
    "pydata__xarray-4094", "sphinx-doc__sphinx-8435",
    "pytest-dev__pytest-5495", "django__django-16408",
    "matplotlib__matplotlib-23563", "sphinx-doc__sphinx-8273",
    "pytest-dev__pytest-8906", "django__django-16910",
]


def is_guidance(plan):
    return plan.get("comparison_axis") == "candidate_guidance"


def axis_fields(plan, arm):
    if type(arm) is not bool:
        raise ValueError("Boolean experimental arm required")
    if is_guidance(plan):
        if (plan.get("fixed_options") != {"suppress_repeats": False}
            or plan["fixed_options"]["suppress_repeats"] is not False):
            raise ValueError("Candidate guidance requires suppression fixed off")
        return {"comparison_axis": "candidate_guidance",
                "candidate_guidance": arm, "suppress_repeats": False}
    return {"suppress_repeats": arm}


def validate_fields(plan, record, arm):
    expected = axis_fields(plan, arm)
    if any(type(record.get(k)) is not type(v) or record.get(k) != v
           for k, v in expected.items()):
        raise ValueError("Comparison axis/options mismatch")


def load_spec(root):
    spec = json.loads((Path(root)/CONFIG_NAME).read_text())
    samples = spec["samples"]
    if (spec.get("comparison_axis") != "candidate_guidance"
        or (spec.get("fixed_options") != {"suppress_repeats": False}
            or spec["fixed_options"]["suppress_repeats"] is not False)
        or spec.get("limit_cny") != "5"
        or [s["instance_id"] for s in samples] != IDS
        or [s.get("role") for s in samples] != ["connectivity"]*2+["primary"]*8
        or [s["arm_order"] for s in samples] != [
            [False, True], [True, False], *([[False, True]]*4), *([[True, False]]*4)]
        or spec.get("phases") != [
            {"name": "connectivity", "start": 0, "end": 4},
            {"name": "primary", "start": 4, "end": 20}]
        or spec["config"].get("search_protocol") != "bounded-v1"):
        raise ValueError("Frozen guidance cohort/axis/order/budget changed")
    return spec
