"""Human-facing command replies; machine results and service authority stay separate."""
from datetime import datetime
from zoneinfo import ZoneInfo
from .gateways import capability

LABELS = {'needs_action': 'Needs action', 'needs_review': 'Needs review', 'fyi': 'FYI', 'waiting': 'Waiting', 'done': 'Done'}


def next_step(settings, ref='REF'):
    if capability(settings.platform).mode == 'interactive':
        return 'Next: inspect ' + ref + ' for details · done ' + ref + ' when resolved · help for snooze and reminders'
    return ('Notification-only destination. Open the Gmail link to handle the message. '
            'Email rules and classifications are available in Hermes Desktop with an owner grant. '
            'Steward Done, snooze and reminders require a supported interactive destination selected in setup.')


def decision_reason(item, rule_name=None):
    """Routine explanation from bounded decision metadata; inspection keeps diagnostics."""
    if item.get('rule_id'):
        reason = 'Your rule “' + (rule_name or 'Saved rule') + '” matched.'
    elif item.get('model_routing'):
        reason = 'Assessed through your configured Hermes model routing. Inspect for reported route details.'
    elif item.get('context_source'):
        reason = 'The message contains a request or problem needing your decision.'
    elif item['classification'] == 'fyi':
        reason = 'Kept as an informational update.'
    else:
        reason = 'Needs your review before a safe decision can be made.'
    if item.get('holds'):
        reason += ' Kept in the inbox for review.'
    return reason


def when(epoch, zone):
    return datetime.fromtimestamp(epoch, ZoneInfo(zone)).strftime('%a %-d %b at %H:%M %Z') if epoch else None


def item_lines(item, *, detail=False):
    lines = [f"{item['reference']} · {LABELS.get(item['classification'], item['classification'])}", item.get('subject') or '(No subject)']
    if item.get('sender'): lines.append('Sender: ' + item['sender'])
    if item.get('summary'): lines.append(item['summary'])
    if detail and item.get('reason'): lines.append('Why: ' + item['reason'])
    if item.get('attachment_status') not in {None, 'none', 'ok'}:
        lines.append('Attachment needs review: ' + item['attachment_status'])
    if item.get('link'): lines.append(item['link'])
    return lines


def rule_lines(rule):
    conditions = ' and '.join(f"{c['field']} {c['operator']} “{c['value']}”" for c in rule['conditions'])
    return [rule['name'] + (' · On' if rule['enabled'] else ' · Off'),
            'When ' + conditions, 'Then ' + LABELS[rule['actions']['classification']] +
            ('; archive if safe' if rule['actions']['archive'] else '; keep inbox location'),
            f"Priority {rule['priority']} · {rule.get('mailbox_id') or 'All mailboxes'}", 'Rule ID: ' + str(rule.get('id', 'unsaved'))]


def error_reply(error):
    code = error.get('code', '')
    if code == 'principal_unavailable':
        return ('Commands unavailable here\nNotification-only destination. '
                'Use the Gmail link to handle the message, or select a supported interactive destination in setup. '
                'Hermes Desktop can manage rules and classifications with an owner grant.\n'
                'Details: principal_unavailable')
    title = {'principal_unavailable':'Commands unavailable here', 'forbidden':'Access denied',
             'grant_revoked':'Private destination changed', 'version_conflict':'A newer version exists',
             'validation_error':'Check the command', 'service_unavailable':'Could not complete this request'}.get(code, 'Request not completed')
    # The code is useful when diagnosing an explicitly failed request, not a serialised record.
    return f"{title}\n{error.get('message', 'Check Email Steward health before retrying.')}\nDetails: {code}"


def readable(value, indent=''):
    """Details requested explicitly (health, schedules, outbox), never raw JSON."""
    if isinstance(value, dict):
        return '\n'.join(indent + k.replace('_', ' ').capitalize() + ': ' +
            ('\n' + readable(v, indent+'  ') if isinstance(v, (dict,list)) else readable(v)) for k,v in value.items())
    if isinstance(value, list): return '\n'.join(indent + '• ' + readable(v) for v in value) or 'None'
    if value is None: return 'None'
    if isinstance(value, bool): return 'Yes' if value else 'No'
    return str(value)


def command_reply(raw, result, store, zone):
    command = raw.strip().partition(' ')[0]
    if 'error' in result: return error_reply(result['error'])
    if 'help' in result: return result['help'] + '\nModel privacy\n' + result['disclosure']
    if 'item' in result:
        item = result['item']; ref = item['reference']; lines=[]
        if command in {'done','archive','restore','snooze','remind','waiting'}:
            current = store.item(ref)
            messages = {
                'done': 'Done · ' + ref + '\nConversation archived. Reminders and snooze cancelled. Read/unread unchanged.',
                'archive': 'Archived · ' + ref + '\nThe obligation stays ' + LABELS.get(item['classification'], item['classification']) + '. Read/unread unchanged.',
                'restore': 'Restored to inbox · ' + ref + '\nThe obligation stays ' + LABELS.get(item['classification'], item['classification']) + '.',
                'snooze': 'Snoozed · ' + ref + '\nReturns to your inbox ' + str(when(current.get('snooze_until'),zone)) + '.',
                'remind': 'Reminder set · ' + ref + '\n' + str(when(current.get('reminder_at'),zone)) + '. Inbox location unchanged.',
                'waiting': 'Waiting for a reply · ' + ref + '\n' + ('Follow-up ' + when(current['reminder_at'],zone) + '.' if current.get('reminder_at') else 'No follow-up date set.')}
            return messages[command] + '\n' + (item.get('subject') or '(No subject)') + '\n' + item.get('link','')
        if command == 'correct':
            saved = result.get('applied_rule')
            lines.append(('Classification updated. Reusable rule “' + saved['name'] + '” saved and ' +
                          ('enabled' if saved['enabled'] else 'disabled') + ' for future matching mail.') if saved else
                         'Classification updated for this item only. No reusable rule added.')
        lines.extend(item_lines(item, detail=True))
        review = result.get('activity_review')
        if review: lines.extend(['Latest activity also needs review: ' + review['subject'], review['summary'], review['reason']])
        if 'text' in result: lines.extend(['Requested message text', result['text'] or '(No readable body)'])
        for extract in result.get('extracts', []):
            lines.extend([f"Attachment: {extract['filename']} · {extract['status']}",extract.get('reason',''),extract.get('text','')])
        if 'extracts' in result and not result['extracts']: lines.append('No attachments on the relevant message.')
        if result.get('suggested_rule') and not result.get('applied_rule'): lines.append('A reusable rule is available for separate review in Email rules. Nothing was enabled automatically.')
        return '\n'.join(lines)
    if 'items' in result:
        items = result['items']
        return ('Email items\n' + '\n\n'.join('\n'.join(item_lines(i)) for i in items) + '\nInspect with: inspect REF') if items else 'No processed email items yet. New inbox arrivals appear after processing.'
    if 'rules' in result or 'rule' in result:
        rules = result.get('rules', [result.get('rule')])
        title = 'Rules saved' if command in {'rule-save','rule-update','rule-toggle','pack-enable'} else 'Email rules'
        return title + '\n' + ('\n\n'.join('\n'.join(rule_lines(r)) for r in rules) if rules else 'No rules yet. Review packs or create a rule in Email rules.')
    if 'packs' in result:
        return 'Suggested rule packs\n' + '\n\n'.join(p['name'] + '\n' + p['description'] + '\n' + ('Already added' if p['enabled'] else 'Not enabled') + ' · ID: ' + p['id'] for p in result['packs']) + '\nReview rules and mailbox scope before enabling a pack.'
    if 'digest' in result: return 'Brief prepared · ' + result['digest'] + '\nCheck the brief above. Use outbox if any part is missing; provider acceptance is not delivery confirmation.'
    if 'disclosure' in result:
        return ('Model content sharing ' + ('disabled' if result.get('model_consent')=='off' else 'updated') + '\n' if 'model_consent' in result else '') + result['disclosure']
    if 'matched' in result:
        return ('Rule matches' if result['matched'] else 'Rule does not match') + '\n' + result['explanation'] + '\n' + ('\n'.join(result.get('holds',[]))) + '\nPreview only: no mail or rules changed.'
    if 'outbox' in result and not result['outbox']: return 'No unresolved deliveries.'
    return readable(result)
