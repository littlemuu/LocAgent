"""Scoped integration: trusted renderer metadata only, no graph or query changes."""
from contextlib import contextmanager
from unittest.mock import patch
from .pages import CommonPages

@contextmanager
def adapted_protocol(snapshot):
    from experiments.cohort_five_paths_v2 import native_adapter as base
    from util.candidate_evidence import capture_evidence
    import util.localization_protocol as protocol
    original=protocol.run_bounded_search
    def run(**kwargs):
        execute=kwargs['execute_tool']
        def captured(*args,**kw):
            with capture_evidence() as capture:
                raw=execute(*args,**kw)
            return capture.unwrap(raw)
        kwargs['execute_tool']=captured
        result=original(**kwargs)
        result.trajectory['diagnostics']['evidence_presentation']='provenance-path-index-v3; 8 paths/1024 bytes within 4096-byte pages'
        return result
    with patch.object(protocol,'run_bounded_search',run),patch.object(base,'CommonPages',CommonPages),base.adapted_protocol(snapshot):
        yield
