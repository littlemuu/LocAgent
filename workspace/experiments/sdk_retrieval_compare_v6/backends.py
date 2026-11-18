"""Arm-specific implementation selection; both have the identical tool interface."""
def select_retriever(base, snapshot, arm):
    if base.snapshot_id != snapshot.identity:
        raise ValueError('retriever_snapshot_mismatch')
    if arm == 'baseline':
        from experiments.path_retrieval_v4.retriever import PathAwareRetriever
        return PathAwareRetriever(base)
    if arm == 'retrieval':
        from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever
        return EvidenceRetriever(base, snapshot)
    raise PermissionError('unknown_retriever_arm')
