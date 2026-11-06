import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://synthetic.test', pretendToBeVisual: true });
for (const name of ['window', 'document', 'HTMLElement', 'Node', 'MutationObserver', 'getComputedStyle']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { default: test, afterEach, after } = await import('node:test');
const { default: assert } = await import('node:assert/strict');
const { createElement: h } = await import('react');
const { render, screen, waitFor, cleanup, act } = await import('@testing-library/react');
const userModule = await import('@testing-library/user-event');
const userEvent = userModule.userEvent || userModule.default.default || userModule.default;
const { QueryClient, QueryClientProvider, host } = await import('@hermes/plugin-sdk');
const { default: plugin, newRule, validateRule, mutableRule, apiError, createApi } = await import('../../desktop/plugin.js');
const { Fixture } = await import('./fixture.mjs');
const clients = [];
after(() => dom.window.close());
afterEach(() => { cleanup(); clients.forEach(c => c.clear()); clients.length = 0; });
function mount(fixture = new Fixture()) {
  const contributions = [];
  const ctx = { source: 'plugin:email-steward', rest: fixture.rest.bind(fixture), registerMany: values => contributions.push(...values) };
  plugin.register(ctx);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } } }); clients.push(client);
  const view = render(h(QueryClientProvider, { client }, contributions.find(c => c.area === 'routes').render()));
  return { fixture, view, contributions, client, user: userEvent.setup({ document: dom.window.document }) };
}
async function startRule(user) {
  await user.click(await screen.findByRole('button', { name: 'Create rule' }));
  await user.type(screen.getByLabelText('Rule name'), 'Invoice review');
  await user.type(screen.getByLabelText('Text 1'), 'invoice');
  await user.type(screen.getByLabelText('Test subject'), 'Please check invoice');
}
async function preview(user, matched = true) { await user.click(screen.getByRole('button', { name: 'Preview match' })); await screen.findByText(matched ? 'Rule matches' : 'Rule does not match'); }

test('native contributions, opt-in registration, strict mutable fields and validation', async () => {
  const { contributions, fixture } = mount();
  await screen.findByText('No rules yet');
  assert.equal(plugin.defaultEnabled, false); assert.equal(contributions.length, 3);
  contributions.find(c => c.area === 'palette').data.run(); assert.equal(host.lastNavigation, '/email-steward/rules');
  assert.equal(fixture.calls.filter(c => c.method !== 'GET').length, 0);
  const rule = newRule(); assert.ok(validateRule(rule).name); rule.name = 'Test'; rule.conditions[0].value = 'x';
  rule.priority = 1001; assert.ok(validateRule(rule).priority); rule.priority = 10;
  rule.actions.archive = true; assert.ok(validateRule(rule).actions);
  assert.equal(Object.hasOwn(mutableRule({ ...rule, id: 'bad', version: 20, pack_id: 'bad' }), 'id'), false);
  assert.equal(apiError(new Error('HTTP 409: {"error":{"code":"version_conflict"}}')).conflict, true);
});

test('add, preview gating, edit, toggle and reload use canonical API state', async () => {
  const { user, fixture, view } = mount(); await startRule(user);
  assert.equal(screen.getByRole('button', { name: 'Save rule' }).disabled, true);
  await preview(user); await user.type(screen.getByLabelText('Rule name'), ' edited');
  assert.equal(screen.getByRole('button', { name: 'Save rule' }).disabled, true);
  await preview(user); await user.click(screen.getByRole('button', { name: 'Save rule' }));
  await screen.findByRole('heading', { name: 'Invoice review edited' });
  assert.equal(fixture.state.rules.length, 1); assert.equal(fixture.state.rules[0].version, 1);
  await user.click(screen.getByRole('switch', { name: 'Disable Invoice review edited' }));
  await screen.findByRole('switch', { name: 'Enable Invoice review edited' }); assert.equal(fixture.state.rules[0].enabled, false);
  await user.click(screen.getByRole('button', { name: 'Edit & preview Invoice review edited' }));
  await user.click(screen.getByText('Rule order'));
  await user.clear(screen.getByLabelText('Priority')); await user.type(screen.getByLabelText('Priority'), '200');
  await user.selectOptions(screen.getByLabelText('Mailbox scope'), 'mailbox-2');
  await user.selectOptions(screen.getByLabelText('Test mailbox'), 'mailbox-2');
  await user.type(screen.getByLabelText('Test subject'), 'invoice'); await preview(user, false);
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByRole('heading', { name: 'Invoice review edited' });
  assert.equal(fixture.state.rules[0].priority, 200); assert.equal(fixture.state.rules[0].mailbox_id, 'mailbox-2');
  assert.equal(fixture.state.rules[0].version, 3);
  view.unmount(); mount(fixture); await screen.findByRole('heading', { name: 'Invoice review edited' });
  assert.equal(screen.getByRole('switch', { name: 'Enable Invoice review edited' }).getAttribute('aria-checked'), 'false');
});

test('validation, AND conditions, scope mismatch and effective archive holds', async () => {
  const { user } = mount(); await user.click(await screen.findByRole('button', { name: 'Create rule' }));
  await user.click(screen.getByRole('button', { name: 'Preview match' })); await screen.findByRole('alert');
  assert.equal(screen.getByLabelText('Rule name').getAttribute('aria-invalid'), 'true');
  await user.type(screen.getByLabelText('Rule name'), 'FYI invoice'); await user.type(screen.getByLabelText('Text 1'), 'invoice');
  await user.selectOptions(screen.getByLabelText('Classification'), 'fyi'); await user.click(screen.getByRole('switch', { name: 'Archive FYI matches' }));
  await user.selectOptions(screen.getByLabelText('Preview source'), 'reference'); await user.type(screen.getByLabelText('Permanent reference'), 'ax1');
  await preview(user); await screen.findByText('Unreadable attachment holds archiving.');
  await user.click(screen.getByRole('button', { name: 'Add condition' })); await user.type(screen.getByLabelText('Text 2'), 'missing');
  await user.click(screen.getByRole('button', { name: 'Preview match' })); await screen.findByText('Rule does not match');
  await user.click(screen.getByRole('button', { name: 'Remove condition 2' }));
  await user.selectOptions(screen.getByLabelText('Mailbox scope'), 'mailbox-2');
  await user.click(screen.getByRole('button', { name: 'Preview match' })); await screen.findByText('Rule does not match');
});

test('stale update is blocked, requires reload, and never silently overwrites', async () => {
  const { user, fixture } = mount(); await startRule(user); await preview(user); await user.click(screen.getByRole('button', { name: 'Save rule' }));
  await user.click(await screen.findByRole('button', { name: 'Edit & preview Invoice review' }));
  await user.type(screen.getByLabelText('Test subject'), 'invoice'); await preview(user); fixture.conflict();
  await user.click(screen.getByRole('button', { name: 'Save changes' })); await screen.findByText(/This changed in another session/);
  assert.equal(screen.getByRole('button', { name: 'Save changes' }).disabled, true); assert.equal(fixture.state.rules[0].name, 'Changed elsewhere');
  await user.click(screen.getByRole('button', { name: 'Reload latest version' })); await waitFor(() => assert.equal(screen.getByLabelText('Rule name').value, 'Changed elsewhere'));
  assert.equal(screen.getByRole('button', { name: 'Save changes' }).disabled, true);
});

test('loading, denied initial read, preview and save failures are visible and recoverable', async () => {
  const fixture = new Fixture(); fixture.delay = 30; fixture.denied = true;
  const { user } = mount(fixture); assert.ok(screen.getByRole('status', { name: 'Loading rules' }));
  await screen.findByText('Could not load email rules'); await screen.findByText('This Desktop principal is not authorised.');
  fixture.denied = false; fixture.delay = 0; await user.click(screen.getByRole('button', { name: 'Reload from server' }));
  await startRule(user); fixture.fail = 'write'; await user.click(screen.getByRole('button', { name: 'Preview match' })); await screen.findByText(/Synthetic service unavailable/);
  assert.equal(screen.getByRole('button', { name: 'Save rule' }).disabled, true); await preview(user);
  fixture.fail = 'write'; await user.click(screen.getByRole('button', { name: 'Save rule' })); await screen.findByText(/Synthetic service unavailable/);
  assert.equal(screen.getByRole('button', { name: 'Save rule' }).disabled, true);
  assert.equal(fixture.state.rules.length, 0); await user.click(screen.getByRole('button', { name: 'Reload from server' })); await screen.findByText('No rules yet');
});

test('pack approval, one-off correction and suggestion keep distinct approvals', async () => {
  const { user, fixture } = mount(); await user.click(await screen.findByRole('button', { name: 'Review pack Direct requests' }));
  assert.equal(fixture.state.rules.length, 0); await user.click(screen.getByRole('button', { name: 'Enable pack' }));
  await screen.findByText('Already added at this scope'); assert.equal(fixture.state.rules.length, 1);
  await user.click(screen.getByRole('button', { name: 'Show recent outcomes' })); await user.click(await screen.findByRole('button', { name: 'Change classification for ax1' }));
  await user.selectOptions(screen.getByLabelText('Classification for ax1'), 'needs_action'); await user.click(screen.getByRole('button', { name: 'Apply one-off correction' }));
  await screen.findByText('Item corrected. No reusable rule has been added.'); assert.equal(fixture.state.rules.length, 1);
  assert.equal(fixture.state.items[0].classification, 'needs_action'); await user.click(screen.getByRole('button', { name: 'Review suggested rule' }));
  assert.equal(screen.getByLabelText('Rule name').value, 'Invoice correction'); assert.equal(fixture.state.rules.length, 1);
});

test('keyboard focus and profile changes discard draft and fence old API handles', async () => {
  const { user, fixture } = mount(); await user.click(await screen.findByRole('button', { name: 'Create rule' }));
  assert.equal(document.activeElement.textContent, 'Create rule'); await user.tab(); assert.equal(document.activeElement.textContent, 'Cancel');
  const api = createApi({ rest: fixture.rest.bind(fixture) }, [host.state.connectionId.get(), host.state.profile.get()]);
  await act(async () => host.state.profile.set('another-profile'));
  await screen.findByText('No rules yet'); assert.equal(screen.queryByLabelText('Rule name'), null);
  const before = fixture.calls.length; await assert.rejects(api('/rules')); assert.equal(fixture.calls.length, before);
  await act(async () => host.state.profile.set('desktop-test'));
});

test('council: validation focuses the first invalid control, then the next one', async () => {
  const { user } = mount(); await user.click(await screen.findByRole('button', { name: 'Create rule' }));
  await user.click(screen.getByRole('button', { name: 'Preview match' }));
  await waitFor(() => assert.ok(document.activeElement === screen.getByLabelText('Rule name'), 'Rule name receives focus'));
  await user.type(screen.getByLabelText('Rule name'), 'Renewal');
  await user.click(screen.getByRole('button', { name: 'Preview match' }));
  await waitFor(() => assert.ok(document.activeElement === screen.getByLabelText('Text 1'), 'Text 1 receives focus'));
});

test('council: contextual accessible action names retain their visible wording', async () => {
  const { user } = mount();
  assert.ok(await screen.findByRole('button', { name: 'Review pack Direct requests' }));
  await startRule(user); await preview(user); await user.click(screen.getByRole('button', { name: 'Save rule' }));
  assert.ok(await screen.findByRole('button', { name: 'Edit & preview Invoice review' }));
  await user.click(screen.getByRole('button', { name: 'Show recent outcomes' }));
  assert.ok(await screen.findByRole('button', { name: 'Change classification for ax1' }));
});
