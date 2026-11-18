"""One admitted arm; all paid traffic goes through durable tickets."""
import json

from .authority import Admission
from .core import digest
from .deepseek_wire import WireProtocolError, normalize, payload
from .live_transport import exchange_live


class LiveSession:
    def __init__(self, ledger, arm, admission, key, parent_alive=lambda: None):
        if type(admission) is not Admission or ledger.summary()['simulation']:
            raise PermissionError('live_admission_required')
        record = admission.validate(ledger.path)
        if digest(record['plan']) != ledger.plan_hash:
            raise PermissionError('plan_mismatch')
        self.ledger, self.arm, self.admission = ledger, arm, admission
        self._key, self.parent_alive = key, parent_alive
        self.token = ledger.claim(arm)
        self.last_id = None
        self.last_normalization_events = []

    def generate(self, messages, tools, closing):
        self.last_normalization_events = []
        self.parent_alive()
        self.admission.validate(self.ledger.path)
        data = payload(messages, tools, closing=closing)
        identifier = self.ledger.reserve(self.arm, self.token, data)
        self.last_id = identifier
        try:
            response = exchange_live(data, self._key, admission=self.admission,
                ledger=self.ledger, reservation=identifier, enabled=True)
            self.ledger.received(identifier, response)
            raw = self.ledger.settle(identifier)
            available = {t['function']['name'] for t in json.loads(data)['tools']}
            response = normalize(raw, available, closing=closing,
                                 normalization_events=self.last_normalization_events)
            for event in self.last_normalization_events:
                event['ledger_call_id'] = identifier
            return response
        except BaseException as error:
            self.fail(error.code if isinstance(error, WireProtocolError) else type(error).__name__)
            raise RuntimeError('live_exchange_stopped') from None

    def fail(self, reason):
        # Even settled-but-invalid answers stop the entire paired run.
        self.ledger.halt(self.last_id, reason)

    def finish(self):
        self.ledger.finish(self.arm, self.token)

    def forget_key(self):
        self._key = None
