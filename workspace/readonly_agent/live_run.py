"""Explicit operator CLI. Preparing or viewing a proposal never reads a key."""
import argparse
import getpass
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

from .authority import Admission, Authority, save_new
from .bridge import LocAgentProcessRetriever
from .core import Limits, Snapshot, digest, encoded
from .journal import Ledger
from .preparation import make_plan

PROJECT = Path(__file__).resolve().parent.parent
CASE = PROJECT / 'examples/case.json'
CASES = {'greeting': CASE, 'crossfile': PROJECT / 'examples/crossfile/case.json'}
ENGINE = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
ENGINE_PYTHON = ENGINE / '.venv/bin/python'


class PairedRunStopped(RuntimeError):
    def __init__(self, summary):
        self.summary = summary
        super().__init__('paired_run_stopped_review_ledger_no_retry')


def stopped_report(summary):
    explanations = {
        'closing_tool_violation': '收尾轮仍请求调查工具；工具未执行，已停止，不自动重试。',
        'closing_finish_missing': '收尾轮未提交 finish；已停止，不自动重试。',
        'unavailable_tool_call': '模型请求未开放的工具；已停止，不自动重试。',
        'model_output_truncated': '模型输出被截断；已停止，不自动重试。',
        'finish_message_contract_error': '模型终答格式不符合工具声明；已停止，不自动重试。',
        'finish_source_validation_error': '模型终答包含不符合源码快照的定位；已停止，不自动重试。',
        'TimeoutError': '请求超时；保留未知费用预留，不自动重试。',
        'OSError': '本地存储或传输失败；检查账本，不自动重试。',
    }
    return {'status': 'stopped', 'explanation': explanations.get(summary.get('reason'),
                '运行未完成；检查分组结果和账本，不自动重试。'),
            'requests_reserved': len(summary['calls']),
            'spent_upper_cny': summary['spent_upper_micro_cny']/1000000,
            'pending_reservation_cny': summary['reserved_micro_cny']/1000000,
            'authorization_consumed': True}


def pilot(case_name='greeting'):
    if case_name not in CASES:
        raise PermissionError('unlisted_pilot_case')
    case_path = CASES[case_name]
    case = json.loads(case_path.read_text())
    snapshot = Snapshot(case_path.parent / case['root'], case['source_files'])
    return snapshot, case['issue'], make_plan(snapshot, case['issue'], ENGINE)


def parent_alive():
    # Parent retains the write end after initialization. EOF fences new calls.
    if select.select([sys.stdin.fileno()], [], [], 0)[0]:
        raise RuntimeError('parent_pipe_closed_or_unexpected_input')


def worker(plan_hash, arm, case_name='greeting'):
    # Worker receives credentials only on stdin, never from args/env/SDK config;
    # it does not read or persist the parent's optional local .env.
    line = sys.stdin.buffer.readline(80000)
    init = json.loads(line)
    if set(init) != {'token', 'key'}:
        raise PermissionError('invalid_parent_initialization')
    admission = Admission(Authority(), plan_hash, init['token'])
    record = admission.validate()
    snapshot, issue, plan = pilot(case_name)
    if plan != record['plan']:
        raise PermissionError('pilot_changed')
    run_dir = Path(record['run_dir'])
    ledger = Ledger(run_dir / 'ledger.sqlite', plan_hash)
    from .live_session import LiveSession
    from .openhands_replay import run_sdk_case
    session = LiveSession(ledger, arm, admission, init.pop('key'), parent_alive)
    retriever = LocAgentProcessRetriever(snapshot, python=ENGINE_PYTHON, engine_root=ENGINE) if arm == 'retrieval' else None
    try:
        result = run_sdk_case(snapshot=snapshot, issue=issue, script=None,
            output_dir=run_dir / arm, retriever=retriever, limits=Limits(max_requests=4), live=session)
        return 0 if result['status'] == 'completed' else 1
    finally:
        session.forget_key()


def run_pair(plan_hash, *, live=False, prompt_api_key=False, env_api_key=False, case_name='greeting'):
    if live is not True or (prompt_api_key is True) == (env_api_key is True):
        raise PermissionError('explicit_live_and_one_key_source_required')
    authority = Authority()
    record = authority.read(plan_hash)
    _, _, plan = pilot(case_name)
    if plan != record['plan'] or (authority.folder(plan_hash)/'claim.json').exists():
        raise PermissionError('changed_or_already_consumed_plan')
    if not sys.stdin.isatty():
        raise PermissionError('local_interactive_terminal_required')
    # Read the local secret only after current grant, plan and TTY checks.
    # Never export it to the environment or import legacy paid settings.
    if env_api_key:
        from .local_env import load_selected_key
        key = load_selected_key()
    else:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('DeepSeek API key (hidden, memory only): ')
    if not 12 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError('invalid_key_shape')
    admission = authority.claim(plan_hash)
    run_dir = Path(record['run_dir'])
    ledger = Ledger.create(run_dir/'ledger.sqlite', plan, admission=admission)
    try:
        for arm in plan['arms']:
            command = [sys.executable, '-B', '-m', 'readonly_agent.live_run',
                       '_worker', '--plan-hash', plan_hash, '--arm', arm, '--case', case_name]
            with (run_dir/f'{arm}.log').open('xb') as log:
                child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log,
                    stderr=subprocess.STDOUT, cwd=PROJECT, start_new_session=True,
                    env={'PATH': os.defpath, 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
                         'OH_PERSISTENCE_DIR': str(run_dir/f'{arm}-profiles'), 'DO_NOT_TRACK': '1'})
                try:
                    child.stdin.write(encoded({'token': admission.token, 'key': key})+b'\n')
                    child.stdin.flush()
                    status = child.wait(timeout=360)
                    if status:
                        raise RuntimeError('arm_failed_no_retry')
                finally:
                    # Includes transport/retrieval descendants in this process group.
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                    child.stdin.close()
        save_new(run_dir/'result.json', ledger.summary())
        return ledger.summary()
    except BaseException as error:
        ledger.halt(None, type(error).__name__)
        raise PairedRunStopped(ledger.summary()) from None
    finally:
        key = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['proposal', 'authorize', 'run', 'status', '_worker'])
    parser.add_argument('--plan-hash')
    parser.add_argument('--consent')
    parser.add_argument('--currency')
    parser.add_argument('--input-ceiling')
    parser.add_argument('--output-ceiling')
    parser.add_argument('--all-charges-included', action='store_true')
    parser.add_argument('--live', action='store_true')
    key_source = parser.add_mutually_exclusive_group()
    key_source.add_argument('--prompt-api-key', action='store_true')
    key_source.add_argument('--env-api-key', action='store_true',
                            help='Read the private local .env after authorization checks.')
    parser.add_argument('--arm', choices=['baseline', 'retrieval'])
    parser.add_argument('--case', choices=sorted(CASES), default='greeting')
    args = parser.parse_args()
    if args.action == 'proposal':
        _, _, plan = pilot(args.case)
        print(json.dumps({'plan_hash': digest(plan), 'plan': plan}, indent=2))
    elif args.action == 'authorize':
        _, _, plan = pilot(args.case)
        Authority().approve(plan, args.plan_hash, currency=args.currency,
            input_ceiling=args.input_ceiling, output_ceiling=args.output_ceiling,
            all_charges_included=args.all_charges_included, consent=args.consent)
        print('One-use grant recorded; no key read or request sent.')
    elif args.action == 'run':
        print(json.dumps(run_pair(args.plan_hash, live=args.live, prompt_api_key=args.prompt_api_key,
                                  env_api_key=args.env_api_key, case_name=args.case), indent=2))
    elif args.action == 'status':
        record = Authority().read(args.plan_hash, fresh=False)
        print(json.dumps(Ledger(Path(record['run_dir'])/'ledger.sqlite', args.plan_hash).summary(), indent=2))
    else:
        if not args.arm or not args.plan_hash:
            raise PermissionError('worker_arguments_required')
        raise SystemExit(worker(args.plan_hash, args.arm, args.case))


if __name__ == '__main__':
    # Never print exception bodies (a transport exception might contain a key).
    try:
        main()
    except PairedRunStopped as error:
        print(json.dumps(stopped_report(error.summary), indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        print('Stopped: '+type(error).__name__+'. No automatic retry.', file=sys.stderr)
        raise SystemExit(1)
