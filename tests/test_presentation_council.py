"""Council findings through real service/command/worker entrypoints; synthetic data."""
import json
import re
import time

import pytest
from test_backend import env, client_for, rule
from test_gateways import configured
from email_steward.chat import Chat
from email_steward.security import Access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.synthetic import SyntheticGmail, SyntheticDelivery
from email_steward.worker import Worker


@pytest.mark.parametrize('enabled', [True, False])
def test_approved_correction_reports_the_rule_actually_saved(env, enabled):
    s,w,p,d,a,source=env
    p.add('request',body='Please approve the renewal by Friday at 17:00.');w.tick();d.sent.clear()
    approved={**rule(), 'name':'Renewal decisions', 'enabled':enabled}
    payload={'version':s.store.item('ax1')['version'],'classification':'needs_review','always':True,'rule':approved}
    ack=Chat(lambda:s,lambda _:w).command('correct ax1 '+json.dumps(payload),source=source)
    saved=s.rules(a);assert len(saved)==1 and saved[0]['enabled'] is enabled
    assert s.store.item('ax1')['rule_id']==saved[0]['id']
    text='\n'.join(x[2] for x in d.sent)
    assert ack.startswith('Reply accepted:')
    assert 'Renewal decisions' in text and ('enabled' if enabled else 'disabled') in text.lower()
    assert 'No reusable rule' not in text and 'item only' not in text and 'Nothing was enabled' not in text


def test_one_off_correction_stays_one_off_and_invalid_time_has_an_example(env):
    s,w,p,d,a,source=env;p.add('request',body='Please review renewal.');w.tick();d.sent.clear()
    chat=Chat(lambda:s,lambda _:w)
    chat.command('correct ax1 '+json.dumps({'version':s.store.item('ax1')['version'],'classification':'fyi','always':False}),source=source)
    assert not s.rules(a)
    assert 'No reusable rule' in '\n'.join(x[2] for x in d.sent)
    before=s.store.item('ax1');d.sent.clear()
    ack=chat.command('snooze ax1 invalid-date',source=source)
    text='\n'.join(x[2] for x in d.sent)
    assert ack.startswith('Request not completed.') and s.store.item('ax1')==before
    assert re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}.*\+\d{2}:\d{2}',text)


def test_notification_only_worker_does_not_offer_unavailable_commands(tmp_path):
    settings=configured(tmp_path,route_context='{}')
    from dataclasses import replace
    settings=replace(settings,platform='telegram',account='synthetic:telegram')
    p=SyntheticGmail();d=SyntheticDelivery();s=Steward(Store(tmp_path/'data'),settings,lambda _:p)
    s.connect(Access(settings.home,settings.owner,'local-operator-cli'),'gmail-1',p.address,'Synthetic')
    p.add('alert',subject='Security alert',body='Suspicious sign-in. Please review today.')
    w=Worker(s,d);now=time.time();w.tick(now);w.brief(now+1,key='notification-council');w.flush(now+1)
    text='\n'.join(x[2] for x in d.sent)
    assert 'notification-only' in text.lower() and 'Gmail' in text
    assert 'Next: inspect' not in text and 'done ax' not in text and 'help for snooze' not in text
    assert 'https://mail.google.com/' in text
    assert all(len(x[2].encode())<=900 for x in d.sent)


def test_brief_parts_retain_the_context_of_every_link_and_reason(env):
    s,w,p,d,a,source=env
    for n in range(3):
        p.add('message'+str(n),subject='Renewal '+str(n)+' '+('long subject '*12),
              body='Please approve the disputed renewal '+str(n)+' by Friday at 17:00. '+('Important context. '*15))
    w.tick();digest=w.brief(key='context-council')
    rows=s.store.rows('SELECT text FROM outbox WHERE id LIKE ? ORDER BY rowid',('brief:'+digest+':%',))
    assert len(rows)>1
    for item in s.store.items():
        pieces=[r['text'] for r in rows if item['link'] in r['text']]
        assert len(pieces)==1
        assert re.search(r'(?:A\d+ · '+item['reference']+r' ·|'+item['reference']+r' · continued)',pieces[0])
    assert all(len(r['text'].encode())<=900 and '\n\n' not in r['text'] for r in rows)
    assert 'Friday at 17:00' in '\n'.join(r['text'] for r in rows)


def test_preview_explains_disabled_scope_and_condition_without_mutation(env):
    s,w,p,d,a,source=env
    work=SyntheticGmail('work@example.test');s.provider_factory=lambda account:work if account['id']=='gmail-2' else p
    s.connect(a,'gmail-2',work.address,'Work')
    api=client_for(s);sample={'mailbox_id':'gmail-1','sender':'test@example.test','subject':'invoice','body':'Receipt enclosed.'}
    checks=[({**rule(),'enabled':False},'disabled'),({**rule(),'mailbox_id':'gmail-2'},'mailbox'),
            ({**rule(),'conditions':[{'field':'subject','operator':'contains','value':'invoice'},{'field':'body','operator':'contains','value':'absent'}]},'condition 2')]
    for draft,expected in checks:
        result=api.post('/api/plugins/email-steward/rules/preview',json={'rule':draft,'sample':sample})
        assert result.status_code==200 and result.json()['matched'] is False
        assert expected in result.json()['explanation'].lower()
    assert not s.rules(a) and not s.items(a) and not p.modifications and not s.model.calls


def test_routine_brief_uses_rule_name_but_explicit_inspection_retains_details(env):
    s,w,p,d,a,source=env;s.enable_pack(a,'starter-action',{'mailbox_id':None})
    p.add('request',body='Please approve the renewal by Friday at 17:00.');w.tick();d.sent.clear()
    item=s.store.item('ax1');digest=w.brief(key='reason-council')
    text='\n'.join(r['text'] for r in s.store.rows('SELECT text FROM outbox WHERE id LIKE ?',('brief:'+digest+':%',)))
    assert 'Please requests' in text and item['rule_id'] not in text
    assert 'scoped AND' not in text and 'Conservative local' not in text
    assert item['rule_id'] in s.inspect(a,'ax1')['item']['reason']
