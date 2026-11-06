// Synthetic SDK host, NOT Hermes Desktop. Real React and React Query; small
// presentation substitutes mirror the documented native component prop API.
import { createElement as h, useSyncExternalStore } from 'react';
export { useQuery, useMutation, useQueryClient, QueryClient, QueryClientProvider } from '@tanstack/react-query';
function atom(value) {
  const listeners = new Set();
  return { get: () => value, set: next => { value = next; listeners.forEach(fn => fn()); }, listen: fn => { listeners.add(fn); return () => listeners.delete(fn); } };
}
export const host = { state: { connectionId: atom('synthetic-host'), profile: atom('desktop-test') }, navigate: path => { host.lastNavigation = path; } };
export const useValue = store => useSyncExternalStore(store.listen, store.get, store.get);
export const ROUTES_AREA = 'routes', SIDEBAR_NAV_AREA = 'sidebar.nav', PALETTE_AREA = 'palette';
export function Button({ loading, variant = 'default', size, asChild, ...props }) {
  return h('button', { ...props, disabled: props.disabled || loading, 'aria-busy': loading || undefined, 'data-slot': 'button', 'data-variant': variant });
}
export const Input = props => h('input', { ...props, 'data-slot': 'input' });
export const Textarea = props => h('textarea', { ...props, 'data-slot': 'textarea' });
export function Switch({ checked, onCheckedChange, ...props }) {
  return h('button', { ...props, type: 'button', role: 'switch', 'aria-checked': checked, 'data-slot': 'switch', onClick: () => onCheckedChange(!checked), children: checked ? 'On' : 'Off' });
}
export const Badge = ({ variant, ...props }) => h('span', { ...props, 'data-slot': 'badge' });
export const Skeleton = props => h('div', { ...props, 'data-slot': 'skeleton' });
export const EmptyState = ({ title, description }) => h('div', { 'data-slot': 'empty-state' }, h('h3', null, title), h('p', null, description));
export const ErrorState = ({ title, description, children }) => h('div', { 'data-slot': 'error-state', role: 'alert' }, h('h2', null, title), h('p', null, description), children);
// Synthetic Select presentation only; actual Radix keyboard/portal behaviour is
// qualified separately in the upstream browser-hosted Desktop renderer.
export function Select({value,onValueChange,disabled,children}) {
  const [trigger,content]=children;
  return h('select',{...trigger.props,disabled,value,onChange:e=>onValueChange(e.target.value),children:content.props.children});
}
export const SelectTrigger=props=>h('button',props);
export const SelectValue=()=>null;
export const SelectContent=props=>h('div',props);
export const SelectItem=props=>h('option',props);
