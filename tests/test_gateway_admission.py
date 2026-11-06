"""Independent adapter parser -> actual registered native dispatcher -> plugin.
Final SDK transport and owning host scaffolding are synthetic; no listeners.
"""
import os,sys,json,asyncio,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),os.environ.get('HERMES_UPSTREAM',str(ROOT.parent))]
from test_native_gateways import route,forbid_real_network,Response
from dataclasses import replace
from types import SimpleNamespace
from gateway.run_inbound_hooks import GatewayInboundHooksMixin
from gateway.platforms.event import MessageEvent
from gateway.session_identity import resolve_identity
from gateway.config import GatewayConfig
from hermes_cli.plugins_manifest import parse_manifest_file
from hermes_cli.plugins import PluginContext
from email_steward.judgement import CONSENT
import pytest

class Host(GatewayInboundHooksMixin):
    def __init__(self):self.config=GatewayConfig();self.session_store=None;self._draining=False
    def _session_key_for_source(self,source):
        from gateway.session import build_session_key
        return build_session_key(source)
    @contextlib.contextmanager
    def _session_env_scope(self,c):yield
    async def _run_in_executor_with_context(self,call):return call()


def register(create,s,delivery,monkeypatch):
    import email_steward.plugin as product
    import hermes_cli.plugins as host
    from email_steward.worker import Worker
    monkeypatch.setattr(product,'service_from_host',lambda ctx:s)
    root=ROOT
    ctx=PluginContext(parse_manifest_file(root/'plugin.yaml',root,'project',''),create.manager)
    product.register(ctx)
    s._probe_effects = []
    def provider(account):
        s._probe_effects.append('gmail')
        raise AssertionError('No Gmail use authorised in this ingress test')
    class Model:
        def judge(self, message):
            s._probe_effects.append('model')
            raise AssertionError('No model use authorised in this ingress test')
    s.provider_factory, s.model = provider, Model()
    original_consent = s.consent
    def consent(*args, **kwargs):
        s._probe_effects.append('business-consent')
        return original_consent(*args, **kwargs)
    monkeypatch.setattr(s, 'consent', consent)
    from tools import send_message_tool as outbound
    original_send = outbound.send_message_tool
    def send(args):
        s._probe_effects.append('native-send')
        return original_send(args)
    monkeypatch.setattr(outbound, 'send_message_tool', send)
    monkeypatch.setattr(host,'_ensure_plugins_discovered',lambda **kw:create.manager)
    return Host()

def save(label,value):
    if os.environ.get('ES_REVIEW_ROOT'):
        (Path(os.environ['ES_REVIEW_ROOT'])/(label+'.json')).write_text(json.dumps(value,indent=2,default=str))

@pytest.mark.parametrize('spelling',['email-steward','email_steward','EMAIL_STEWARD@synthetic_bot'])
def test_real_event_parser_registered_dispatch_and_foreign_zero_calls(route,monkeypatch,spelling):
    create,calls,_=route
    s,adapter,module,delivery=create('discord','67890')
    runner=register(create,s,delivery,monkeypatch)
    import aiohttp
    async def request(self,method,url,**kwargs):
        calls.append((method,str(url),kwargs))
        return Response({'id':'67890','type':1} if method=='GET' else {'id':'999999'})
    monkeypatch.setattr(aiohttp.ClientSession,'_request',request)
    good=MessageEvent(text='/'+spelling+' consent '+CONSENT,source=create.source)
    handled,result,_=asyncio.run(runner._hm_dispatch_plugin_command(good,good.source,good.get_command()))
    assert handled and 'Reply accepted:' in result,(handled,result)
    assert s.store.meta('model_consent')==CONSENT
    from gateway.session_identity import replace_source
    before=len(calls);old=s.store.meta('model_consent')
    bad=MessageEvent(text='/'+spelling+' consent off owner=12345',source=replace_source(create.source,user_id='foreign'))
    handled,result,_=asyncio.run(runner._hm_dispatch_plugin_command(bad,bad.source,bad.get_command()))
    assert handled and 'forbidden' in result and len(calls)==before and s.store.meta('model_consent')==old
    save('dispatcher-'+spelling.replace('@','-'),{'positive':True,'negative':result,'native_calls':calls})


@pytest.mark.parametrize('actor_present',[False,True])
def test_photon_missing_actor_does_not_inherit_owner_from_space_phone(route,monkeypatch,actor_present):
    create,calls,_=route
    s,adapter,module,delivery=create('photon','iMessage;-;+15550001111',extra={'project_id':'synthetic-project'})
    s.settings=replace(s.settings,owner='+15550001111');s.current_settings()
    runner=register(create,s,delivery,monkeypatch)
    import httpx
    adapter._http_client=httpx.AsyncClient()
    adapter._sidecar_bind,adapter._sidecar_port,adapter._sidecar_token='127.0.0.1',1,'synthetic'
    async def handle(self,request):
        calls.append({'url':str(request.url),'payload':json.loads(request.content)})
        return httpx.Response(400,json={'ok':False,'error':'synthetic refused target','errorClass':'target_not_allowed','retryable':False})
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',handle)
    observations=[]
    async def ingress(event):
        from types import SimpleNamespace
        host=SimpleNamespace(config=SimpleNamespace(multiplex_profiles=False),_primary_profile_name='custom',_owning_profile=lambda adapter,platform:(True,'custom'))
        resolve_identity(event.source,runner=host,adapter=adapter,transport_profile='custom',primary_home=s.settings.home)
        result=await runner._hm_dispatch_plugin_command(event,event.source,event.get_command())
        observations.append({'source':event.source.to_dict(),'result':result,'raw':event.raw_message})
    monkeypatch.setattr(adapter,'handle_message',ingress)
    event={'messageId':'anonymous-event','space':{'id':s.settings.destination,'type':'dm','phone':s.settings.owner},'sender':({'id':s.settings.owner} if actor_present else {}),'content':{'type':'text','text':'/email_steward consent '+CONSENT}}
    asyncio.run(adapter._dispatch_inbound(event))
    save('photon-final-'+str(actor_present),{'events':observations,'model_consent':s.store.meta('model_consent'),'calls':calls,'effects':s._probe_effects,'outbox':s.store.rows('SELECT * FROM outbox')})
    asyncio.run(adapter._http_client.aclose())
    assert s.store.meta('model_consent') != CONSENT
    assert calls == [] and s.store.rows('SELECT * FROM outbox') == []
    assert s._probe_effects == []
    assert observations and 'principal_unavailable' in __import__('unicodedata').normalize('NFKC', observations[0]['result'][1])
    assert 'Notification-only' in observations[0]['result'][1]


@pytest.mark.parametrize('actor_present',[False,True])
def test_bluebubbles_missing_sender_does_not_borrow_chat_identifier(route,monkeypatch,actor_present):
    create,calls,_=route
    s,adapter,module,delivery=create('bluebubbles','iMessage;-;+15550001111',extra={'server_url':'https://blue.example.test','password':'synthetic'})
    s.settings=replace(s.settings,owner='+15550001111');s.current_settings()
    runner=register(create,s,delivery,monkeypatch)
    import httpx
    adapter.client=httpx.AsyncClient()
    async def handle(self,request):
        calls.append({'url':str(request.url),'payload':json.loads(request.content)})
        return httpx.Response(400,json={'status':400,'message':'synthetic refused target'})
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',handle)
    observations=[]
    async def ingress(event):
        host=SimpleNamespace(config=SimpleNamespace(multiplex_profiles=False),_primary_profile_name='custom',_owning_profile=lambda a,p:(True,'custom'))
        resolve_identity(event.source,runner=host,adapter=adapter,transport_profile='custom',primary_home=s.settings.home)
        result=await runner._hm_dispatch_plugin_command(event,event.source,event.get_command())
        observations.append({'source':event.source.to_dict(),'result':result,'raw':event.raw_message})
    monkeypatch.setattr(adapter,'handle_message',ingress)
    raw={'type':'new-message','data':{'chatGuid':s.settings.destination,'chatIdentifier':s.settings.owner,'text':'/email-steward consent '+CONSENT,'guid':'synthetic-anonymous-message'}}
    if actor_present:raw['data']['handle']={'address':s.settings.owner}
    class Request:
        query={'password':'synthetic'};headers={}
        async def read(self):return json.dumps(raw).encode()
    response=asyncio.run(adapter._handle_webhook(Request()))
    save('bluebubbles-final-'+str(actor_present),{'status':response.status,'events':observations,'model_consent':s.store.meta('model_consent'),'calls':calls,'effects':s._probe_effects,'outbox':s.store.rows('SELECT * FROM outbox')})
    asyncio.run(adapter.client.aclose())
    assert s.store.meta('model_consent') != CONSENT
    assert calls == [] and s.store.rows('SELECT * FROM outbox') == []
    assert s._probe_effects == []
    assert observations and 'principal_unavailable' in __import__('unicodedata').normalize('NFKC', observations[0]['result'][1])
    assert 'Notification-only' in observations[0]['result'][1]


@pytest.mark.parametrize('route_state', ['unchanged', 'new-grant-stale-live', 'no-live-adapter', 'change-after-first'])
def test_ntfy_selected_live_server_at_each_worker_effect(route, monkeypatch, route_state):
    create, calls, _ = route
    s, adapter, module, delivery = create('ntfy', 'synthetic-private', chat_type='topic')
    import httpx, yaml
    from email_steward.worker import Worker
    from tools import send_message_tool as host_send
    adapter._http_client = httpx.AsyncClient()
    native_calls = []
    original_send = host_send.send_message_tool
    def send(args):
        native_calls.append(args)
        return original_send(args)
    monkeypatch.setattr(host_send, 'send_message_tool', send)
    def regrant():
        path = s.settings.home / 'config.yaml'
        config = yaml.safe_load(path.read_text())
        config['platforms']['ntfy']['extra']['server'] = 'https://selected-new.example.test'
        path.write_text(yaml.safe_dump(config))
        s.settings = replace(s.settings, route_context=json.dumps({'server':'https://selected-new.example.test'}), grant_revision=2)
        s.current_settings()
    if route_state == 'new-grant-stale-live': regrant()
    if route_state == 'no-live-adapter': create.transports.pop('ntfy')
    async def handle(self, request):
        calls.append({'url':str(request.url), 'body':request.content.decode()})
        if route_state == 'change-after-first':
            regrant()
            s.store.outbox('fresh-new-grant', 1, 'ax1 new approved server work')
        return httpx.Response(200, json={'id':'synthetic-ack'})
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', handle)
    s.store.outbox('work', 1, 'ax1 '+ ('bounded '*250 if route_state == 'change-after-first' else 'private notification'))
    try:
        Worker(s, delivery).flush(2)
        if route_state == 'change-after-first': Worker(s, delivery).flush(3)
        rows = s.store.rows('SELECT * FROM outbox ORDER BY rowid')
        if route_state in {'unchanged', 'change-after-first'}:
            assert len(calls) == len(native_calls) == 1
            assert calls[0]['url'] == 'https://synthetic.example.test/synthetic-private'
            assert rows[0]['state'] == 'uncertain'
            assert all(row['state'] == 'blocked' for row in rows[1:])
        else:
            assert calls == native_calls == []
            assert rows[0]['state'] == 'blocked'
        if route_state == 'new-grant-stale-live':
            assert rows[0]['grant_generation'] == s.store.active_grant[0] == 2
            assert rows[0]['grant_fingerprint'] == s.store.active_grant[1]
        save('ntfy-'+route_state, {'calls':calls, 'native_calls':native_calls, 'rows':rows, 'active_grant':s.store.active_grant})
    finally:
        asyncio.run(adapter._http_client.aclose())
        adapter._http_client = None
