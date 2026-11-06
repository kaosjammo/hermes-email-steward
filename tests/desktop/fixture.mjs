// Contract fixture, not the production service. Its only data is synthetic.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
const copy = value => JSON.parse(JSON.stringify(value));
export const starter = { name: 'Direct requests', enabled: true, mailbox_id: null, priority: 100,
  conditions: [{ field: 'body', operator: 'contains', value: 'please' }], actions: { classification: 'needs_action', archive: false } };
const boxes = [{ id: 'mailbox-1', address: 'alex@example.test', display_name: 'Personal' }, { id: 'mailbox-2', address: 'sam@example.test', display_name: 'Work' }];
export class Fixture {
  constructor(file) { this.file = file; this.reset(); if (file && existsSync(file)) this.state = JSON.parse(readFileSync(file)); }
  reset() {
    this.state = { rules: [], installed: [], sequence: 0, items: [{ reference: 'ax1', mailbox_id: 'mailbox-1', sender: 'billing@example.test', subject: 'Invoice check', summary: 'Please check invoice.', classification: 'needs_review', reason: 'Attachment significance needs review.', rule_id: null, version: 1, archived: false, attachment_status: 'unreadable', link: '' }] };
    this.calls = []; this.fail = null; this.delay = 0; this.denied = false; this.persist();
  }
  persist() { if (this.file) writeFileSync(this.file, JSON.stringify(this.state)); }
  reject(status, code, message, fields) { const error = new Error(JSON.stringify({ error: { code, message, ...(fields ? { fields } : {}) } })); error.status = status; throw error; }
  conflict() { if (this.state.rules[0]) { this.state.rules[0].version++; this.state.rules[0].name = 'Changed elsewhere'; this.persist(); } }
  async rest(path, { method = 'GET', body } = {}) {
    this.calls.push({ path, method, body: copy(body ?? null) });
    if (this.delay) await new Promise(resolve => setTimeout(resolve, this.delay));
    if (this.denied) this.reject(403, 'forbidden', 'This Desktop principal is not authorised.');
    if (this.fail && (this.fail === 'any' || method !== 'GET')) { this.fail = null; this.reject(503, 'unavailable', 'Synthetic service unavailable; try reloading.'); }
    if (path === '/rules' && method === 'GET') return copy({ rules: [...this.state.rules].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id)) });
    if (path === '/mailboxes') return copy({ mailboxes: boxes });
    if (path === '/packs' && method === 'GET') return copy({ packs: [{ id: 'starter-action', name: 'Direct requests', description: 'Questions and requests stay visible.', enabled: this.state.installed.length > 0, enabled_scopes: this.state.installed, rules: [starter] }] });
    if (path === '/items' && method === 'GET') return copy({ items: this.state.items });
    if (path === '/rules/preview') {
      const rule = body.rule;
      if (!rule.name.trim() || !rule.conditions[0]?.value.trim()) this.reject(422, 'validation_error', 'Invalid rule.', { name: 'A name is required.' });
      const sample = body.sample || (body.reference === 'ax1' ? { ...this.state.items[0], body: 'Please check invoice.' } : null);
      if (!sample) this.reject(404, 'not_found', 'Reference not found.');
      const matched = rule.enabled && (!rule.mailbox_id || rule.mailbox_id === sample.mailbox_id) && rule.conditions.every(c => c.operator === 'equals' ? sample[c.field].toLowerCase() === c.value.toLowerCase() : sample[c.field].toLowerCase().includes(c.value.toLowerCase()));
      const held = body.reference && rule.actions.archive;
      return { matched, explanation: matched ? `Matched ${rule.name}: all ${rule.conditions.length} conditions matched.` : 'Mailbox scope or text conditions did not match.', classification: matched ? rule.actions.classification : null, archive: !!(matched && rule.actions.archive && !held), holds: held ? ['Unreadable attachment holds archiving.'] : [] };
    }
    if (path === '/rules' && method === 'POST') {
      const rule = { ...copy(body), id: `rule-${++this.state.sequence}`, version: 1, pack_id: null };
      this.state.rules.push(rule); this.persist(); return { rule: copy(rule) };
    }
    const match = path.match(/^\/rules\/([^/]+)(\/toggle)?$/);
    if (match) {
      const rule = this.state.rules.find(r => r.id === decodeURIComponent(match[1]));
      if (!rule) this.reject(404, 'not_found', 'Rule not found.');
      if (body.version !== rule.version) this.reject(409, 'version_conflict', 'Rule changed.');
      if (match[2]) rule.enabled = body.enabled;
      else { const { version, ...fields } = body; Object.assign(rule, fields); }
      rule.version++; this.persist(); return { rule: copy(rule) };
    }
    if (path === '/packs/starter-action/enable') {
      if (!this.state.installed.includes(body.mailbox_id)) {
        this.state.installed.push(body.mailbox_id);
        this.state.rules.push({ ...copy(starter), mailbox_id: body.mailbox_id, id: `rule-${++this.state.sequence}`, version: 1, pack_id: 'starter-action' }); this.persist();
      }
      return copy({ rules: this.state.rules.filter(r => r.pack_id === 'starter-action') });
    }
    if (path === '/items/ax1/correct') {
      const item = this.state.items[0];
      if (body.version !== item.version) this.reject(409, 'version_conflict', 'Item changed.');
      Object.assign(item, { classification: body.classification, version: item.version + 1 }); this.persist();
      return copy({ item, suggested_rule: { ...starter, name: 'Invoice correction', actions: { classification: body.classification, archive: false }, conditions: [{ field: 'subject', operator: 'contains', value: 'Invoice' }] } });
    }
    this.reject(404, 'not_found', 'Unknown fixture route.');
  }
}
