// Synthetic SDK host only. No host grants, real mail, credentials or model calls.
import { createElement as h } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import plugin from '../../desktop/plugin.js';
const contributions = [];
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
plugin.register({ source: 'plugin:email-steward', registerMany: cs => contributions.push(...cs), rest: async (path, options = {}) => {
  const response = await fetch(`/api/plugins/email-steward${path}`, { method: options.method || 'GET', headers: { 'Content-Type': 'application/json' }, ...(options.body ? { body: JSON.stringify(options.body) } : {}) });
  const data = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(data));
  return data;
} });
const page = contributions.find(c => c.area === 'routes');
const root = createRoot(document.getElementById('root'));
root.render(h(QueryClientProvider, { client }, page.render()));
for (const button of document.querySelectorAll('[data-control]')) button.onclick = async () => {
  const result = await fetch(`/control/${button.dataset.control}`, { method: 'POST' });
  document.getElementById('control-status').textContent = await result.text();
  if (button.dataset.control === 'reset') await client.invalidateQueries();
};
