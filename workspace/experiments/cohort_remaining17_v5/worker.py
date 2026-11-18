"""Native engine/query subprocess, with explicit frozen ticket via stdin only."""
import contextlib, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'engine_adaptation/v4/engine')]
from experiments.cohort_remaining17_v5.guard import CohortAuthority, RehearsalAuthority, CohortWire, verify
from experiments.cohort_remaining17_v5.guard import RehearsalAdmission
from experiments.cohort_remaining17_v5.fixtures import mock_transport
from experiments.cohort_preflight.entry import read
from experiments.cohort_preflight import body
from experiments.cohort_remaining17_v5.body_backend import backend as positive_body_backend
from experiments.cohort_preflight.entry import load_graph
from readonly_agent.authority import Admission
from readonly_agent.core import encoded
from readonly_agent.journal import Ledger
from locagent_service.offline import offline_engine

def main():
    req = json.load(sys.stdin)
    def parent_alive():
        os.kill(req['batch_parent_pid'], 0)
        if os.getppid() != req['parent_pid']:
            raise RuntimeError('parent_process_lost')
    parent_alive()
    with contextlib.redirect_stdout(sys.stderr), offline_engine():
        plan = read(req['plan'])
        value, snapshot, status = verify(plan, plan['cohort_execution'])
        graph, retriever, module = load_graph(value, snapshot)
        if req['operation'] == 'query':
            from experiments.path_retrieval_v4.retriever import PathAwareRetriever
            result = {'text':PathAwareRetriever(retriever).retrieve(req['query']), 'snapshot':snapshot.identity}
        elif req['operation'] == 'native':
            from experiments.cohort_remaining17_v5.native_adapter import adapted_protocol
            from util.localizer import GraphLocalizer
            from util.localization_contract import LocalizationRequest, LocalizationOptions
            from plugins.location_tools.repo_ops import repo_ops as ops
            from unittest.mock import patch
            from litellm import ModelResponse
            rehearsal = plan['cohort_execution'] == 'rehearsal'
            auth = (RehearsalAuthority if rehearsal else CohortAuthority)(req['authority_root'])
            admission = (RehearsalAdmission if rehearsal else Admission)(auth, req['plan_hash'], req['token'])
            ledger = Ledger(req['ledger'], req['plan_hash'])
            wire = CohortWire(ledger, 'baseline', admission, req.get('key'), snapshot=snapshot,
                              transport=mock_transport('baseline',snapshot,value['issue']) if rehearsal else None,
                              parent_alive=parent_alive)
            br, _ = body.load(snapshot, status['body_directory'], status['body_attestation_sha256'])
            queries = []
            def provider(**kw):
                raw, _, _ = wire.exchange(kw['messages'], kw['tools'], kw.get('tool_choice') is not None)
                return ModelResponse(**raw)
            engine = GraphLocalizer.from_graph(graph, provider=provider, model_name=plan['model'], module_retriever=module,
                bm25_index_dir=str(Path(status['body_directory']).parent),
                options=LocalizationOptions(max_iterations=4, search_protocol='bounded-v1'))
            try:
                with patch.object(ops, 'bm25_content_retrieve', positive_body_backend(br,queries)), adapted_protocol(snapshot):
                    answer = engine.localize(LocalizationRequest(value['case_id'],value['repo'],value['base_commit'],value['issue']))
                if answer.diagnostics['termination_reason'] != 'finished':
                    raise RuntimeError('native_not_finished')
                wire.finish()
            except BaseException:
                wire.fail('native_failed')
                raise
            finally:
                wire.forget_key()
            from experiments.cohort_remaining17_v5.finish_policy import audit_predictions
            audit = audit_predictions({'files':answer.to_dict()['found_files'],'entities':answer.to_dict()['found_entities'],'answer':''},snapshot)
            result = {'prediction_audit':audit,'status':'completed','mode':'simulation' if rehearsal else 'live','result':answer.to_dict(),
                      'requests':wire.requests,'body_queries':queries,'tool_calls':wire.calls}
        else:
            raise ValueError('unknown_operation')
    sys.stdout.buffer.write(encoded(result))

if __name__ == '__main__':
    main()
