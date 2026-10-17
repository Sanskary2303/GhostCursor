import { describe, it, expect, afterEach } from 'vitest';
import { describeAction, labelForTarget } from './chat/describe';
import { registerTarget, clearTargetRegistry } from './dom-utils';

describe('describeAction', () => {
  afterEach(() => { clearTargetRegistry(); document.body.innerHTML = ''; });

  it('uses visible text of the on-page target', () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'product.add_to_cart_btn');
    btn.textContent = ' Add to Cart ';
    document.body.appendChild(btn);
    expect(describeAction({ id: '1', type: 'click', target_id: 'product.add_to_cart_btn' })).toBe('Click Add to Cart');
  });

  it('prefers aria-label, then a registered label', () => {
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.setAttribute('data-ghost-id', 'theme.toggle');
    input.setAttribute('aria-label', 'Dark mode');
    document.body.appendChild(input);
    expect(describeAction({ id: '1', type: 'toggle_switch', target_id: 'theme.toggle', state: true })).toBe('Turn Dark mode ON');
    registerTarget('theme.toggle', { page: 'settings', resolve: () => input, operations: ['toggle'], label: 'Dark theme switch' });
    expect(labelForTarget('theme.toggle')).toBe('Dark theme switch');
  });

  it('falls back to a humanised id and formats other types', () => {
    expect(describeAction({ id: '1', type: 'click', target_id: 'checkout.place_order_btn' })).toBe('Click place order button');
    expect(describeAction({ id: '1', type: 'click', target_id: 'product.size.10' })).toBe('Click size 10');
    expect(describeAction({ id: '2', type: 'navigate', target_page: 'product/air-max-90' })).toBe('Go to Product Air Max 90');
    expect(describeAction({ id: '3', type: 'fill_input', target_id: 'checkout.zip', value: '10001' })).toBe('Type "10001" into zip');
  });

  it('never queries the DOM with an unsafe id', () => {
    expect(labelForTarget('x"],body,[a="')).toBe('x"],body,[a="');
  });

  it('uses associated label for select inputs instead of option text', () => {
    const select = document.createElement('select');
    select.setAttribute('data-ghost-id', 'checkout.state');
    for (const optText of ['Select', 'New York', 'Texas']) {
      const opt = document.createElement('option');
      opt.textContent = optText;
      select.appendChild(opt);
    }
    document.body.appendChild(select);
    expect(describeAction({ id: '1', type: 'select_option', target_id: 'checkout.state', option: 'NY' })).toBe('Choose "NY" in state');

    const label = document.createElement('label');
    label.setAttribute('for', 'st');
    label.textContent = 'State';
    select.id = 'st';
    document.body.appendChild(label);
    expect(describeAction({ id: '1', type: 'select_option', target_id: 'checkout.state', option: 'NY' })).toBe('Choose "NY" in State');
  });
});

