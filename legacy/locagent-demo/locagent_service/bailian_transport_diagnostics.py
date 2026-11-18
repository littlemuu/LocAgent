"""Fixed transport diagnostics; never stringify exceptions or retain headers."""
import http.client
import socket
import ssl
from locagent_service.bailian_raw_artifact import CaptureUnavailable

STAGES=frozenset(('setup','dns','tcp_connect','tls','request_send','response_headers','response_body','body_check','cleanup','unknown'))


class OverallTimeout(TimeoutError):
    pass


def category(exc):
    if isinstance(exc,OverallTimeout):return 'overall_timeout'
    if isinstance(exc,TimeoutError):return 'operation_timeout'
    if isinstance(exc,socket.gaierror):return 'dns_error'
    if isinstance(exc,ssl.SSLCertVerificationError):return 'tls_certificate_error'
    if isinstance(exc,ssl.SSLError):return 'tls_error'
    if isinstance(exc,ConnectionError):return 'connection_error'
    if isinstance(exc,http.client.HTTPException):return 'http_protocol_error'
    if isinstance(exc,KeyboardInterrupt):return 'interrupted'
    if isinstance(exc,CaptureUnavailable) and exc.code=='credential_echo':return 'credential_echo'
    return 'unknown'


class TransportFailure(CaptureUnavailable):
    def __init__(self,diagnostic,body=None):
        super().__init__('credential_echo' if diagnostic['category']=='credential_echo' else 'transport_failure')
        self.diagnostic=diagnostic
        self.body=body


def exchange_once(body,config,*,connection_factory,host,origin,path,workspace,endpoint):
    import signal
    conn=None;raw=None;status=None;primary=None;cleanup=[];old_handler=None
    stage='setup';send_started=False;headers=False;complete=False;timer_touched=False
    try:
        if endpoint(config.get('DASHSCOPE_WORKSPACE_ID'),config.get('DASHSCOPE_API_HOST'))!=origin+path:
            raise ValueError('Configured endpoint mismatch')
        secret=config.get('DASHSCOPE_API_KEY','')
        if not isinstance(secret,str) or not 1<=len(secret)<=4096 or any(ord(x)<33 or ord(x)>126 for x in secret):
            raise ValueError('Credential invalid')
        conn=connection_factory(host,timeout=15,context=ssl.create_default_context())
        old_handler=signal.getsignal(signal.SIGALRM)
        def timeout(signum,frame):raise OverallTimeout()
        timer_touched=True
        signal.signal(signal.SIGALRM,timeout)
        signal.setitimer(signal.ITIMER_REAL,60)
        stage='request_send';send_started=True
        conn.request('POST',path,body=body,headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json',
                     'Accept-Encoding':'identity','User-Agent':'LocAgent-approved-embedding'})
        stage='response_headers'
        response=conn.getresponse();headers=True
        if type(response.status) is int and 100<=response.status<=599:status=response.status
        if int(response.getheader('Content-Length','0'))>4*1024*1024:raise ValueError('Response limit')
        stage='response_body'
        received=response.read(4*1024*1024+1)
        stage='body_check'
        if len(received)>4*1024*1024:raise ValueError('Response limit')
        if secret.encode('ascii') in received:raise CaptureUnavailable('credential_echo')
        raw=received;complete=True
    except BaseException as exc:
        if stage=='request_send' and conn is not None:
            connection_stage=getattr(conn,'download_stage',None)
            if isinstance(connection_stage,str) and connection_stage in STAGES:stage=connection_stage
        primary={'stage':stage if stage in STAGES else 'unknown','category':category(exc)}
    finally:
        if conn is not None:
            if getattr(conn,'download_cleanup_failed',False) is True:cleanup.append('unknown')
            try:conn.close()
            except BaseException as exc:cleanup.append(category(exc))
        if timer_touched:
            try:signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as exc:cleanup.append(category(exc))
            if old_handler is not None:
                try:signal.signal(signal.SIGALRM,old_handler)
                except BaseException as exc:cleanup.append(category(exc))
    if primary is not None or cleanup:
        diagnostic={'version':1,**(primary or {'stage':'cleanup','category':cleanup[0]}),
                    'http_status':status,'request_method_entered':send_started,
                    'response_headers_received':headers,'complete_body_available':complete,
                    'cleanup_failed':bool(cleanup),'cleanup_categories':cleanup}
        raise TransportFailure(diagnostic,raw) from None
    return status,raw
