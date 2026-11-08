import { useEffect, useId, useRef, useState } from 'react';
import { jsx as h, jsxs } from 'react/jsx-runtime';
import {
  host, useValue, useQuery, useMutation, useQueryClient,
  ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA,
  Button, Input, Textarea, Switch, Badge, Skeleton, EmptyState, ErrorState,
  Select as NativeSelect, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@hermes/plugin-sdk';

const PATH = '/email-steward/rules';
const LABELS = { needs_action: 'Needs action', fyi: 'FYI', needs_review: 'Needs review' };
const css = `
.es-rules{color:var(--ui-text-primary);font:inherit;font-size:13px;line-height:1.55;max-width:1180px;margin:auto;padding:24px;overflow-wrap:anywhere}
.es-rules *{box-sizing:border-box}.es-rules h1{font-size:23px;line-height:1.3;font-weight:600;margin:0}.es-rules h2{font-size:16px;font-weight:600;margin:0}.es-rules h3{font-size:14px;font-weight:600;margin:0}
.es-rules p{margin:6px 0;max-width:74ch}.es-rules .es-muted{color:var(--ui-text-secondary)}.es-rules .es-header,.es-rules .es-row{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}.es-rules .es-header{margin-bottom:24px}.es-rules .es-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.es-rules .es-layout{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:32px}.es-rules .es-section{border-top:1px solid var(--ui-stroke-secondary);padding-top:16px}.es-rules .es-rule{padding:18px 0;border-bottom:1px solid var(--ui-stroke-secondary)}.es-rules .es-rule p{margin:8px 0}.es-rules .es-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px}.es-rules .es-pack{padding:18px 0;border-bottom:1px solid var(--ui-stroke-secondary)}.es-rules .es-pack p{font-size:12px}.es-rules .es-notice{margin:14px 0;padding:12px;border:1px solid var(--ui-stroke-secondary);border-radius:4px;background:var(--ui-bg-quinary)}.es-rules .es-error{border-left:3px solid var(--ui-accent);padding:12px;margin:12px 0}.es-rules .es-form{display:grid;gap:22px;max-width:880px}.es-rules .es-form>fieldset{display:grid;gap:22px}.es-rules fieldset{padding:0;margin:0;border:0;min-width:0}.es-rules legend{font-size:15px;font-weight:600;margin-bottom:10px}.es-rules .es-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.es-rules .es-field{display:grid;gap:5px;align-content:start}.es-rules label{font-weight:500}.es-rules input,.es-rules textarea,.es-rules select{max-width:100%;width:100%;font:inherit}.es-rules select{border:1px solid var(--ui-stroke-secondary);border-radius:4px;padding:7px 9px;background:var(--ui-bg-quinary);color:var(--ui-text-primary)}.es-rules .es-condition{display:grid;grid-template-columns:110px 120px minmax(100px,1fr) auto;gap:10px;margin-bottom:12px;align-items:end}.es-rules .es-footer{display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-top:1px solid var(--ui-stroke-secondary);padding-top:18px;margin-top:8px}.es-rules .es-preview{padding:16px;border:1px solid var(--ui-stroke-secondary);border-radius:4px;margin-top:14px}.es-rules .es-preview h3{margin-bottom:8px}.es-rules ul{padding-left:20px}.es-rules :focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}.es-rules [tabindex="-1"]:focus{outline:none}.es-rules .es-check{display:flex;gap:10px;align-items:center}.es-rules .es-check label{font-weight:400}.es-rules .es-skeleton{height:64px;margin:16px 0}.es-rules .es-help{font-size:12px;color:var(--ui-text-secondary)}
@media(max-width:850px){.es-rules .es-layout{grid-template-columns:1fr}.es-rules{padding:18px}.es-rules .es-condition{grid-template-columns:1fr 1fr}.es-rules .es-condition .es-field:nth-child(3){grid-column:1/-1}}@media(max-width:480px){.es-rules .es-grid{grid-template-columns:1fr}.es-rules{padding:14px}.es-rules h1{font-size:21px}}

.es-rules{font-size:14px;max-width:1200px;padding:28px 24px}
.es-rules .es-layout{grid-template-columns:minmax(0,1fr) 260px;gap:36px}
.es-rules .es-section,.es-rules .es-rule,.es-rules .es-pack,.es-rules .es-footer{border-color:var(--ui-stroke-tertiary)}
.es-rules .es-rule{padding:16px 0}.es-rules .es-pack{padding:14px 0}
.es-rules .es-form{max-width:none}.es-rules .es-form>fieldset{grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:20px 32px;align-items:start}
.es-rules .es-definition{display:grid;gap:20px;min-width:0;grid-column:1;grid-row:1}
.es-rules .es-form>fieldset>.es-preview-panel{grid-column:2;grid-row:1;border-top:0;border-left:1px solid var(--ui-stroke-tertiary);padding:0 0 0 28px}
.es-rules .es-preview-panel .es-grid{grid-template-columns:1fr;gap:12px}
.es-rules .es-footer{grid-column:1/-1}
.es-rules .es-footer>.es-error{flex-basis:100%;margin:0}.es-rules .es-footer{padding:14px 0;position:static}.es-rules .es-form legend{margin-bottom:6px}.es-rules .es-advanced{align-self:center}.es-rules summary{cursor:pointer;color:var(--ui-text-secondary);font-size:12px;padding:6px 0}.es-rules .es-advanced[open]{grid-column:1/-1}.es-rules .es-advanced .es-field{max-width:260px}
.es-rules .es-select{font:inherit;min-height:34px;white-space:normal;text-align:left}
.es-rules input{min-height:34px}.es-rules .es-condition{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}
.es-rules .es-condition .es-field:nth-child(3){grid-column:1/-1}.es-rules .es-condition>button{justify-self:start}.es-rules .es-preview-panel>.es-field{margin:12px 0}.es-rules .es-preview-panel .es-grid{margin-top:12px}
.es-rules .es-correction{max-width:580px}.es-rules .es-correction>button{margin:8px 8px 0 0}.es-rules .es-preview{border-color:var(--ui-stroke-tertiary);background:var(--ui-bg-quinary)}
@media(max-width:1000px){.es-rules .es-form>fieldset{grid-template-columns:1fr}.es-rules .es-form>fieldset>.es-preview-panel{grid-column:1;grid-row:auto;border-left:0;border-top:1px solid var(--ui-stroke-tertiary);padding:16px 0 0}.es-rules .es-preview-panel .es-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:850px){.es-rules .es-layout{grid-template-columns:1fr}.es-rules{padding:20px 16px}}
@media(max-width:480px){.es-rules .es-grid,.es-rules .es-preview-panel .es-grid{grid-template-columns:1fr}.es-rules{padding:16px 12px}.es-rules .es-button{min-height:36px}.es-rules .es-header{align-items:flex-start}.es-rules h1{font-size:21px}}
`;

export function newRule() {
  return { name: '', enabled: true, mailbox_id: null, priority: 100,
    conditions: [{ field: 'subject', operator: 'contains', value: '' }],
    actions: { classification: 'needs_review', archive: false } };
}
export function mutableRule(rule) {
  return { name: rule.name.trim(), enabled: rule.enabled, mailbox_id: rule.mailbox_id,
    priority: Number(rule.priority), conditions: rule.conditions.map(c => ({ ...c })),
    actions: { ...rule.actions } };
}
export function validateRule(rule) {
  const errors = {};
  if (!rule.name.trim() || rule.name.trim().length > 100) errors.name = 'Enter a name of 1–100 characters.';
  if (!Number.isInteger(Number(rule.priority)) || rule.priority === '' || Number(rule.priority) < -1000 || Number(rule.priority) > 1000)
    errors.priority = 'Priority must be a whole number from −1000 to 1000.';
  if (!rule.conditions.length || rule.conditions.length > 20) errors.conditions = 'Use 1–20 conditions.';
  rule.conditions.forEach((c, i) => {
    if (!['sender', 'subject', 'body'].includes(c.field) || !['contains', 'equals'].includes(c.operator) || !c.value.trim() || c.value.length > 500)
      errors[`condition-${i}`] = 'Choose a field and operator, and enter 1–500 characters.';
  });
  if (!Object.hasOwn(LABELS, rule.actions.classification)) errors.actions = 'Choose a supported classification.';
  if (rule.actions.archive && rule.actions.classification !== 'fyi') errors.actions = 'Only FYI rules can archive.';
  return errors;
}

// ctx.rest currently wraps HTTP failures in Error.message. Accept structured
// errors too, without depending on an undocumented status property.
export function apiError(error) {
  let value = error;
  if (typeof error?.message === 'string') {
    const start = error.message.indexOf('{');
    if (start >= 0) {
      try { value = JSON.parse(error.message.slice(start)); } catch { value = null; }
    }
  }
  const detail = value?.error || value?.detail?.error;
  if (detail?.code === 'version_conflict') return { conflict: true, message: 'This changed in another session. Reload the latest version and review it before saving again.', fields: {} };
  if (detail && typeof detail.message === 'string') return { message: detail.message, fields: detail.fields || {} };
  return { message: 'The service could not complete this request. Check that Email Steward is enabled and your Desktop session is authorised, then reload. A failed save may have reached the server; check the rules before retrying.', fields: {} };
}

function currentOwner() { return [host.state.connectionId.get(), host.state.profile.get()]; }
function sameOwner(owner) { return JSON.stringify(owner) === JSON.stringify(currentOwner()); }
export function createApi(ctx, owner) {
  return async (path, options) => {
    if (!sameOwner(owner)) throw new Error('The active connection or profile changed.');
    const result = await ctx.rest(path, options);
    if (!sameOwner(owner)) throw new Error('The active connection or profile changed.');
    return result;
  };
}
const button = (label, onClick, props = {}) => h(Button, { type: 'button', className: 'es-button', variant: 'outline', onClick, 'aria-label': label, ...props, children: label });
function Field({ label, children, error, hint }) {
  const id = useId();
  return jsxs('div', { className: 'es-field', children: [h('label', { htmlFor: id, children: label }),
    children({ id, 'aria-invalid': !!error, 'aria-describedby': error || hint ? `${id}-help` : undefined }),
    (error || hint) && h('span', { id: `${id}-help`, className: 'es-help', children: error || hint })] });
}
function Select({ options, value, onChange, disabled, ...props }) {
  const empty = '__es_empty__';
  return jsxs(NativeSelect, { value: value || empty, disabled, onValueChange: v => onChange(v === empty ? '' : v), children: [
    h(SelectTrigger, { ...props, className: 'es-select', disabled, style: { width: '100%', minWidth: 0 }, children: h(SelectValue, {}) }),
    h(SelectContent, { children: options.map(([v, label]) => h(SelectItem, { value: v || empty, children: label }, v)) }),
  ] });
}
function Scope({ mailboxes, value, onChange, label = 'Mailbox scope', disabled = false }) {
  return h(Field, { label, children: props => h(Select, { ...props, disabled, value: value || '', onChange: v => onChange(v || null),
    options: [['', 'All connected mailboxes'], ...mailboxes.map(m => [m.id, `${m.display_name} (${m.address})`])] }) });
}
function Failure({ error, onReload }) {
  const detail = apiError(error);
  return jsxs('div', { className: 'es-error', role: 'alert', children: [h('p', { children: detail.message }),
    onReload && button(detail.conflict ? 'Reload latest version' : 'Reload from server', onReload)] });
}
function ruleSummary(rule) {
  return rule.conditions.map(c => `${c.field} ${c.operator} “${c.value}”`).join(' and ');
}
function scopeName(id, mailboxes) {
  if (!id) return 'All mailboxes';
  const box = mailboxes.find(m => m.id === id);
  return box ? `${box.display_name} (${box.address})` : 'Mailbox unavailable';
}
function useWrite(api, onSuccess) {
  return useMutation({ mutationFn: ({ path, body, method = 'POST' }) => api(path, { method, body }), retry: false, onSuccess });
}

function RuleEditor({ initial, mailboxes, api, onClose, onSaved, reloadRule }) {
  const [draft, setDraft] = useState(() => mutableRule(initial));
  const [errors, setErrors] = useState({});
  const [mode, setMode] = useState('sample');
  const [reference, setReference] = useState('');
  const [sample, setSample] = useState({ mailbox_id: initial.mailbox_id || mailboxes[0]?.id || '', sender: '', subject: '', body: '' });
  const [preview, setPreview] = useState(null);
  const [previewSignature, setPreviewSignature] = useState('');
  const [reloading, setReloading] = useState(false);
  const [reloadError, setReloadError] = useState(null);
  const heading = useRef(null);
  const form = useRef(null);
  useEffect(() => {
    if (Object.keys(errors).length) (form.current?.querySelector('[aria-invalid="true"]') || form.current?.querySelector('[role="alert"]'))?.focus();
  }, [errors]);
  const state = useRef();
  state.current = { draft, sample, mode, reference };
  useEffect(() => { heading.current?.focus(); }, []);
  const signature = JSON.stringify({ draft, sample, mode, reference });
  const save = useWrite(api, onSaved);
  const check = useMutation({ mutationFn: async ({ body, signature: checked }) => ({ result: await api('/rules/preview', { method: 'POST', body }), checked }), retry: false,
    onSuccess: ({ result, checked }) => { setPreview(result); setPreviewSignature(checked); } });
  const busy = save.isPending || check.isPending || reloading;
  const change = patch => { setDraft(d => ({ ...d, ...patch })); setPreview(null); setPreviewSignature(''); setErrors({}); check.reset(); };
  const condition = (i, patch) => setDraft(d => ({ ...d, conditions: d.conditions.map((c, n) => n === i ? { ...c, ...patch } : c) }));
  const clearPreview = () => { setPreview(null); setPreviewSignature(''); check.reset(); };
  const validate = () => {
    const next = validateRule(state.current.draft); setErrors(next);
    return !Object.keys(next).length;
  };
  const runPreview = () => {
    if (!validate()) return;
    const s = state.current;
    if ((s.mode === 'sample' && !s.sample.mailbox_id) || (s.mode === 'reference' && !s.reference.trim())) {
      setErrors({ sample: s.mode === 'sample' ? 'Choose a connected mailbox to test.' : 'Enter a permanent item reference.' }); return;
    }
    const body = { rule: mutableRule(s.draft), ...(s.mode === 'sample' ? { sample: s.sample } : { reference: s.reference.trim() }) };
    clearPreview(); check.mutate({ body, signature: JSON.stringify(s) });
  };
  const submit = event => {
    event.preventDefault();
    if (!validate() || busy || save.error || !preview || previewSignature !== signature) return;
    const body = mutableRule(state.current.draft);
    if (initial.id) body.version = initial.version;
    save.mutate({ path: initial.id ? `/rules/${encodeURIComponent(initial.id)}` : '/rules', method: initial.id ? 'PUT' : 'POST', body });
  };
  const reload = async () => {
    setReloading(true); setReloadError(null);
    try { await reloadRule(initial.id); } catch (error) { setReloadError(error); } finally { setReloading(false); }
  };
  const fieldError = name => errors[name] || apiError(save.error).fields?.[name];
  const title = initial.id ? 'Edit rule' : 'Create rule';
  return jsxs('section', { 'aria-labelledby': 'es-editor-title', children: [
    jsxs('header', { className: 'es-header', children: [jsxs('div', { children: [h('h1', { id: 'es-editor-title', tabIndex: -1, ref: heading, children: title }),
      h('p', { className: 'es-muted', children: initial.id ? `Update the rule, preview the result, then save your changes.` : 'Choose what to match and how to organise it. Preview before saving.' })] }), button('Cancel', onClose, { disabled: busy })] }),
    jsxs('form', { className: 'es-form', ref: form, onSubmit: submit, children: [
      Object.keys(errors).length > 0 && h('div', { className: 'es-error', role: 'alert', tabIndex: -1, children: 'Check the highlighted fields before continuing.' }),
      jsxs('fieldset', { disabled: busy, children: [
      jsxs('div', { className: 'es-definition', children: [jsxs('div', { className: 'es-grid', children: [h(Field, { label: 'Rule name', error: fieldError('name'), children: props => h(Input, { ...props, value: draft.name, maxLength: 100, onChange: e => change({ name: e.target.value }) }) }),
        h(Scope, { mailboxes, value: draft.mailbox_id, onChange: mailbox_id => change({ mailbox_id }) }),
        jsxs('div', { className: 'es-check', children: [h(Switch, { id: 'es-enabled', checked: draft.enabled, onCheckedChange: enabled => change({ enabled }) }), h('label', { htmlFor: 'es-enabled', children: 'Enable after saving' })] }),
        jsxs('details', { className: 'es-advanced', open: fieldError('priority') ? true : undefined, children: [h('summary', { children: 'Rule order' }),
          h(Field, { label: 'Priority', error: fieldError('priority'), hint: 'Higher numbers run first (−1000 to 1000). Default: 100.', children: props => h(Input, { ...props, type: 'number', min: -1000, max: 1000, step: 1, value: draft.priority, onChange: e => change({ priority: e.target.value }) }) })] })] }),
      jsxs('fieldset', { className: 'es-section', children: [h('legend', { children: 'When all conditions match' }), h('p', { className: 'es-help', children: 'Every condition must match. Uppercase and lowercase are treated the same.' }),
        draft.conditions.map((c, i) => jsxs('div', { className: 'es-condition', children: [
          h(Field, { label: `Field ${i + 1}`, children: props => h(Select, { ...props, value: c.field, onChange: field => { condition(i, { field }); clearPreview(); }, options: [['sender', 'Sender'], ['subject', 'Subject'], ['body', 'Body']] }) }),
          h(Field, { label: `Match ${i + 1}`, children: props => h(Select, { ...props, value: c.operator, onChange: operator => { condition(i, { operator }); clearPreview(); }, options: [['contains', 'Contains'], ['equals', 'Equals']] }) }),
          h(Field, { label: `Text ${i + 1}`, error: errors[`condition-${i}`], children: props => h(Input, { ...props, value: c.value, maxLength: 500, onChange: e => { condition(i, { value: e.target.value }); clearPreview(); } }) }),
          draft.conditions.length > 1 && button('Remove', () => { setDraft(d => ({ ...d, conditions: d.conditions.filter((_, n) => n !== i) })); clearPreview(); }, { disabled: draft.conditions.length === 1, 'aria-label': `Remove condition ${i + 1}` })
        ] }, i)),
        button('Add condition', () => { setDraft(d => ({ ...d, conditions: [...d.conditions, { field: 'subject', operator: 'contains', value: '' }] })); clearPreview(); }, { disabled: draft.conditions.length >= 20 })] }),
      jsxs('fieldset', { className: 'es-section', children: [h('legend', { children: 'Then classify' }),
        jsxs('div', { className: 'es-grid', children: [h(Field, { label: 'Classification', error: fieldError('actions'), children: props => h(Select, { ...props, value: draft.actions.classification, options: Object.entries(LABELS), onChange: classification => change({ actions: { classification, archive: classification === 'fyi' && draft.actions.archive } }) }) }),
          jsxs('div', { className: 'es-check', children: [h(Switch, { id: 'es-archive', checked: draft.actions.archive, disabled: draft.actions.classification !== 'fyi', onCheckedChange: archive => change({ actions: { ...state.current.draft.actions, archive } }) }), h('label', { htmlFor: 'es-archive', children: 'Archive FYI matches' })] })] }),
        h('p', { className: 'es-help', children: 'Read/unread stays unchanged. Requests and attachment warnings hold archiving.' })] })] }),
      jsxs('fieldset', { className: 'es-section es-preview-panel', children: [h('legend', { children: 'Preview before saving' }),
        h('p', { className: 'es-help', children: 'Try a message before saving. Preview changes no mail and uses no model.' }),
        h(Field, { label: 'Preview source', children: props => h(Select, { ...props, value: mode, onChange: value => { setMode(value); clearPreview(); }, options: [['sample', 'Test text I provide'], ['reference', 'Existing item reference']] }) }),
        mode === 'reference' ? h(Field, { label: 'Permanent reference', error: errors.sample, children: props => h(Input, { ...props, value: reference, onChange: e => { setReference(e.target.value); clearPreview(); } }) }) :
          jsxs('div', { className: 'es-grid', children: [h(Field, { label: 'Test mailbox', error: errors.sample, children: props => h(Select, { ...props, value: sample.mailbox_id, onChange: mailbox_id => { setSample(s => ({ ...s, mailbox_id })); clearPreview(); }, options: [['', 'Choose mailbox'], ...mailboxes.map(m => [m.id, `${m.display_name} (${m.address})`])] }) }),
            h(Field, { label: 'Test sender', children: props => h(Input, { ...props, value: sample.sender, maxLength: 320, onChange: e => { setSample(s => ({ ...s, sender: e.target.value })); clearPreview(); } }) }),
            h(Field, { label: 'Test subject', children: props => h(Input, { ...props, value: sample.subject, maxLength: 1000, onChange: e => { setSample(s => ({ ...s, subject: e.target.value })); clearPreview(); } }) }),
            h(Field, { label: 'Test body', children: props => h(Textarea, { ...props, value: sample.body, maxLength: 32000, rows: 3, onChange: e => { setSample(s => ({ ...s, body: e.target.value })); clearPreview(); } }) })] }),
        button(check.isPending ? 'Checking match…' : 'Preview match', runPreview, { loading: check.isPending, style: { marginTop: 14 } }),
        check.error && h(Failure, { error: check.error }),
        preview && previewSignature === signature && jsxs('div', { className: 'es-preview', role: 'status', children: [h('h3', { children: preview.matched ? 'Rule matches' : 'Rule does not match' }),
          h('p', { children: preview.matched ? 'Every condition matches this message.' : preview.explanation }), preview.matched && h('p', { children: `${LABELS[preview.classification] || preview.classification}; ${preview.archive ? 'would archive if safe' : 'inbox location unchanged'}.` }),
          preview.holds?.length > 0 && h('ul', { children: preview.holds.map((hold, i) => h('li', { children: hold === 'Attachment significance unresolved: unassessed' ? 'Attachments were not assessed in this text preview. Archiving stays on hold.' : hold === 'Substantive request or problem needs an owner decision' ? 'A request or problem needs your decision. It stays visible.' : hold }, i)) })] })] }),
      jsxs('div', { className: 'es-footer', children: [save.error && h(Failure, { error: save.error, onReload: reload }), reloadError && h(Failure, { error: reloadError }),
        h(Button, { type: 'submit', className: 'es-button', disabled: busy || !!save.error || !preview || previewSignature !== signature, loading: save.isPending, 'aria-label': save.isPending ? 'Saving rule' : initial.id ? 'Save changes' : 'Save rule', children: initial.id ? 'Save changes' : 'Save rule' }),
        h('span', { className: 'es-help', role: 'status', children: save.error ? 'Save not confirmed. Reload and review the server version before continuing.' : save.isPending ? 'Saving your rule…' : preview && previewSignature === signature ? 'Ready to save. This applies to future matching mail.' : 'Run a preview of your current changes to enable saving.' })] })
    ] })] })] });
}

function Packs({ packs, mailboxes, api, invalidate, onTry }) {
  const [scope, setScope] = useState(null);
  const [review, setReview] = useState(null);
  const [success, setSuccess] = useState('');
  const write = useWrite(api, async () => { setSuccess('Pack added. Its rules are ready to edit or pause.'); setReview(null); await invalidate(); });
  const installed = pack => pack.enabled_scopes ? pack.enabled_scopes.includes(scope) : pack.enabled && scope === null;
  return jsxs('aside', { className: 'es-section', 'aria-labelledby': 'es-packs', children: [h('h2', { id: 'es-packs', children: 'Suggested packs' }),
    h('p', { className: 'es-muted', children: 'Optional starting points. Review each pack before enabling it.' }), h(Scope, { mailboxes, value: scope, onChange: value => { setScope(value); setReview(null); write.reset(); }, label: 'Pack mailbox scope', disabled: write.isPending }),
    success && h('p', { role: 'status', children: success }), write.error && h(Failure, { error: write.error, onReload: invalidate }),
    packs.length === 0 && h('p', { children: 'No suggested packs are available from this service.' }),
    packs.map(pack => jsxs('section', { className: 'es-pack', children: [h('h3', { children: pack.name }), h('p', { className: 'es-muted', children: pack.description }),
      installed(pack) ? h(Badge, { variant: 'muted', children: 'Already added at this scope' }) : button('Review pack', () => { setReview(review === pack.id ? null : pack.id); setSuccess(''); }, { disabled: write.isPending, 'aria-expanded': review === pack.id, 'aria-label': `Review pack ${pack.name}` }),
      review === pack.id && jsxs('div', { children: [h('p', { className: 'es-help', children: `Adds ${pack.rules.length} rule(s) for ${scopeName(scope, mailboxes)}. Existing rules and safety holds remain in effect.` }),
        h('ul', { children: pack.rules.map((rule, i) => jsxs('li', { children: [h('strong', { children: rule.name }), h('p', { children: ruleSummary(rule) }),
          h('p', { children: `${LABELS[rule.actions.classification]}${rule.actions.archive ? ', archive requested' : ''}; priority ${rule.priority}.` }),
          button('Try in editor', () => onTry({ ...rule, mailbox_id: scope }), { disabled: write.isPending, 'aria-label': `Try in editor ${rule.name}` })] }, i)) }),
        button('Enable pack', () => write.mutate({ path: `/packs/${encodeURIComponent(pack.id)}/enable`, body: { mailbox_id: scope } }), { variant: 'default', loading: write.isPending })] })] }, pack.id))] });
}

function Outcomes({ api, queryKey, onSuggest, mailboxes }) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [classification, setClassification] = useState('needs_review');
  const [result, setResult] = useState(null);
  const query = useQuery({ queryKey: [...queryKey, 'items'], queryFn: () => api('/items'), enabled: open, retry: false, gcTime: 0, refetchInterval: open ? 15000 : false });
  const write = useWrite(api, async data => { setResult(data); setTarget(null); await query.refetch(); });
  return jsxs('section', { className: 'es-section', style: { marginTop: 24 }, children: [jsxs('div', { className: 'es-row', children: [h('h2', { children: 'Recent decisions' }), button(open ? 'Hide outcomes' : 'Show recent outcomes', () => setOpen(v => !v), { 'aria-expanded': open })] }),
    open && jsxs('div', { children: [query.isLoading && h('p', { role: 'status', children: 'Loading outcomes…' }), query.error && h(Failure, { error: query.error, onReload: query.refetch }),
      write.error && h(Failure, { error: write.error, onReload: async () => { await query.refetch(); setTarget(null); write.reset(); } }),
      result && jsxs('div', { className: 'es-notice', role: 'status', children: [h('p', { children: 'Item corrected. No reusable rule has been added.' }), result.suggested_rule && button('Review suggested rule', () => onSuggest(result.suggested_rule))] }),
      query.data?.items.length === 0 && h(EmptyState, { title: 'No processed items yet', description: 'Explanations appear after authorised inbox processing.' }),
      query.data?.items.map(item => jsxs('article', { className: 'es-rule', children: [h('h3', { children: `${item.reference}: ${item.subject}` }), h('p', { className: 'es-help', children: `${item.sender} — ${LABELS[item.classification] || item.classification}` }),
        h('p', { children: item.summary }), h('p', { className: 'es-help', children: scopeName(item.mailbox_id, mailboxes) }),
        jsxs('details', { children: [h('summary', { children: 'Why this decision' }), h('p', { children: item.reason }), h('p', { className: 'es-help', children: item.rule_id ? 'Matched one of your rules' : 'No rule matched this message' })] }),
        button('Change classification', () => { setTarget(item); setClassification(item.classification); setResult(null); write.reset(); }, { disabled: write.isPending, 'aria-label': `Change classification for ${item.reference}` }),
        target?.reference === item.reference && jsxs('div', { className: 'es-notice es-correction', children: [h(Field, { label: `Classification for ${item.reference}`, children: props => h(Select, { ...props, value: classification, disabled: write.isPending, onChange: setClassification, options: Object.entries(LABELS) }) }),
          h('p', { className: 'es-help', children: 'Applies to this item only. A suggested rule requires your separate approval.' }),
          button('Apply one-off correction', () => write.mutate({ path: `/items/${encodeURIComponent(target.reference)}/correct`, body: { version: target.version, classification, always: false } }), { loading: write.isPending }), button('Cancel correction', () => setTarget(null), { disabled: write.isPending })] })] }, item.reference))] })] });
}

function RulesWorkspace({ ctx, owner }) {
  const queryClient = useQueryClient();
  const [api] = useState(() => createApi(ctx, owner));
  const queryKey = [ctx.source, ...owner, 'rules-screen'];
  const query = useQuery({ queryKey, queryFn: async () => {
    const [rules, packs, mailboxes] = await Promise.all([api('/rules'), api('/packs'), api('/mailboxes')]);
    return { ...rules, ...packs, ...mailboxes };
  }, retry: false, staleTime: 0, gcTime: 0, refetchInterval: 15000 });
  const [editor, setEditor] = useState(null);
  const [editorKey, setEditorKey] = useState(0);
  const [notice, setNotice] = useState('');
  const heading = useRef(null);
  const returnFocus = useRef(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey });
  const write = useWrite(api, async () => { setNotice('Rule updated.'); await invalidate(); });
  const edit = initial => {
    returnFocus.current = document.activeElement; setEditor(initial); setEditorKey(k => k + 1); setNotice(''); write.reset();
  };
  const close = () => { setEditor(null); requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus(); else heading.current?.focus(); }); };
  const reload = async id => {
    const response = await query.refetch();
    if (response.error) throw response.error;
    if (!id) { close(); return; }
    const latest = response.data.rules.find(r => r.id === id);
    if (!latest) throw new Error('Rule no longer exists.');
    setEditor(latest); setEditorKey(k => k + 1);
  };
  if (query.isLoading) return jsxs('section', { role: 'status', 'aria-label': 'Loading rules', children: [h('h1', { children: 'Email rules' }), h('p', { children: 'Loading your rules and connected mailboxes…' }), h(Skeleton, { className: 'es-skeleton' }), h(Skeleton, { className: 'es-skeleton' })] });
  if (!query.data) return h(ErrorState, { title: 'Could not load email rules', description: apiError(query.error).message, children: button('Reload from server', query.refetch) });
  const data = query.data;
  if (editor) return h(RuleEditor, { initial: editor, mailboxes: data.mailboxes, api, onClose: close,
    onSaved: async () => { setNotice('Rule saved. Future matching mail will use it.'); close(); await invalidate(); }, reloadRule: reload }, editorKey);
  return jsxs('div', { children: [jsxs('header', { className: 'es-header', children: [jsxs('div', { children: [h('h1', { ref: heading, tabIndex: -1, children: 'Email rules' }), h('p', { className: 'es-muted', children: 'Choose what needs attention and what can leave your inbox. Shared with your private gateway.' })] }),
    jsxs('div', { className: 'es-actions', children: [button(query.isFetching ? 'Refreshing…' : 'Refresh', query.refetch, { disabled: query.isFetching }), button('Create rule', () => edit(newRule()), { variant: 'default' })] })] }),
    notice && h('p', { role: 'status', children: notice }), query.error && h(Failure, { error: query.error, onReload: query.refetch }),
    write.error && h(Failure, { error: write.error, onReload: async () => { const result = await query.refetch(); if (!result.error) write.reset(); } }),
    data.mailboxes.length === 0 && h('p', { className: 'es-notice', children: 'No connected mailboxes. Connect Gmail through the authorised Email Steward setup to preview against a mailbox.' }),
    jsxs('div', { className: 'es-layout', children: [jsxs('main', { className: 'es-section', children: [jsxs('div', { className: 'es-row', children: [h('h2', { children: 'Your rules' }), h('span', { className: 'es-help', children: `${data.rules.filter(r => r.enabled).length} enabled / ${data.rules.length} total` })] }),
      h('p', { className: 'es-help', children: 'Rules run in priority order. Unresolved requests and attachment warnings always stay visible.' }),
      data.rules.length === 0 && h(EmptyState, { title: 'No rules yet', description: 'Create a rule or review a suggested pack. Packs are never enabled automatically.' }),
      data.rules.map(rule => jsxs('article', { className: 'es-rule', children: [jsxs('div', { className: 'es-row', children: [h('h3', { children: rule.name }), h(Switch, { checked: rule.enabled, disabled: write.isPending || !!write.error || !!query.error, 'aria-label': `${rule.enabled ? 'Disable' : 'Enable'} ${rule.name}`,
        onCheckedChange: enabled => write.mutate({ path: `/rules/${encodeURIComponent(rule.id)}/toggle`, body: { version: rule.version, enabled } }) })] }),
        jsxs('div', { className: 'es-meta', children: [h(Badge, { variant: rule.enabled ? 'default' : 'muted', children: rule.enabled ? LABELS[rule.actions.classification] : 'Disabled' }), h('span', { className: 'es-help', children: `Priority ${rule.priority} · ${scopeName(rule.mailbox_id, data.mailboxes)}` })] }),
        h('p', { children: ruleSummary(rule) }), jsxs('div', { className: 'es-row', children: [h('span', { className: 'es-help', children: `${rule.actions.archive ? 'Archive requested for FYI' : 'Keep inbox location'}` }),
          button('Edit & preview', () => edit(rule), { disabled: write.isPending, 'aria-label': `Edit & preview ${rule.name}` })] })] }, rule.id))] }),
      h(Packs, { packs: data.packs, mailboxes: data.mailboxes, api, invalidate, onTry: edit })] }), h(Outcomes, { api, queryKey, mailboxes: data.mailboxes, onSuggest: edit })] });
}
function RulesPage({ ctx }) {
  const connection = useValue(host.state.connectionId);
  const profile = useValue(host.state.profile);
  const owner = [connection, profile];
  return jsxs('div', { className: 'es-rules', children: [h('style', { children: css }), h(RulesWorkspace, { ctx, owner }, JSON.stringify(owner))] });
}
export default {
  id: 'email-steward', name: 'Email Steward', defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      { id: 'rules-page', area: ROUTES_AREA, data: { path: PATH }, render: () => h(RulesPage, { ctx }) },
      { id: 'rules-nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Email rules', codicon: 'mail' } },
      { id: 'rules-open', area: PALETTE_AREA, data: { id: 'email-steward.rules', label: 'Open Email Steward rules', keywords: ['email', 'rules', 'mail'], run: () => host.navigate(PATH) } },
    ]);
  },
};
