"""Human replies through authorised production commands; synthetic mail only."""
import time
from datetime import datetime, timezone
from test_backend import env
from email_steward.chat import Chat
from email_steward.presentation import redact
from email_steward.outbound import chunks


def test_native_reply_has_useful_after_state_without_internal_record(env):
    s,w,p,d,a,source=env
    p.add('request',thread='t',subject='Renewal',body='Please approve the renewal by Friday at 17:00.')
    w.tick();d.sent.clear()
    c=Chat(lambda:s,lambda _:w)
    due=datetime.fromtimestamp(time.time()+3600,timezone.utc).isoformat()
    result=c.command('remind ax1 '+due,source=source)
    output='\n'.join(x[2] for x in d.sent)
    assert 'Reply accepted:' in result
    assert 'Reminder set' in output and 'ax1' in output
    assert 'mailbox_id' not in output and '｛' not in output and 'rule_id' not in output
    assert s.store.item('ax1')['reminder_at'] is not None
    d.sent.clear();c.command('done ax1',source=source)
    output='\n'.join(x[2] for x in d.sent)
    assert 'Done' in output and 'archived' in output and 'cancelled' in output
    assert s.store.item('ax1')['classification']=='done'
    assert s.store.item('ax1')['reminder_at'] is None


def test_security_copy_keeps_meaning_but_suppresses_credentials():
    assert redact('Security alert: a new device signed in.')=='Security alert: a new device signed in.'
    for text in ['security code: A6B8C0','verification code is 987654','OTP 123456','password=shhh-secret','api_key=sk-secret-value']:
        assert 'redacted' in redact(text)
    parts=chunks('ax1\n'+'A complete sentence about a renewal. '*35+'\nNext step: inspect ax1')
    assert all(len(p.encode())<=900 for p in parts)
    assert all(not p.endswith(('rene','sent','comple')) for p in parts)


def test_worker_brief_and_urgent_expose_substance_and_clear_next_step(env):
    s,w,p,d,a,source=env
    p.add('request',thread='t',subject='Renewal',body='Please approve the disputed renewal by Friday at 17:00.')
    p.add('security',subject='Security alert',body='Suspicious sign-in on the example account. Please review today.')
    w.tick()
    alerts='\n'.join(x[2] for x in d.sent)
    assert 'Suspicious sign-in' in alerts
    assert 'Next: inspect ' in alerts
    d.sent.clear(); w.brief(); w.flush()
    text='\n'.join(x[2] for x in d.sent)
    assert 'Needs action' in text and 'needs_action' not in text and 'needs＿action' not in text
    assert 'disputed renewal' in text and 'Friday at 17:00' in text
    assert 'Deadline:' in text and 'Next: inspect REF' in text
    assert 'UNHEALTHY' not in text
