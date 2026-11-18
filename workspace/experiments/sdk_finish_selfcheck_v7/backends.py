"""Same frozen retrieval backend in both prompt comparison arms."""
def select_retriever(base, snapshot, arm):
    if arm not in ('baseline', 'retrieval'):
        raise PermissionError('unknown_retriever_arm')
    if base.snapshot_id != snapshot.identity:
        raise ValueError('retriever_snapshot_mismatch')
    from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever
    return EvidenceRetriever(base, snapshot)
