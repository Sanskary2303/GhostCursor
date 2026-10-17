import { describe, it, expect, afterEach } from 'vitest';
import { h, render } from 'preact';
import { ChatWidget, type ChatWidgetProps } from './chat/ChatWidget';

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

function mount(props?: Partial<ChatWidgetProps>) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: 'open' });
  render(h(ChatWidget, {
    apiEndpoint: '/api/ghost-cursor',
    theme: { primaryColor: '#3B7BDF', cursorColor: '#3B7BDF', position: 'bottom-right', mode: 'midnight' },
    requireApprovalForActions: true,
    initialContext: { page: 'home', values: {}, availableTargets: [] },
    onSendMessage: async () => ({ reply: 'ok', status: 'completed', runId: 'r', revision: 0 }),
    onActionApproval: async () => null,
    ...props,
  }), root);
  return { host, root };
}

describe('ChatWidget shell', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  it('renders one themed stylesheet and a branded launcher', () => {
    const { root } = mount();
    const styles = root.querySelectorAll('style');
    expect(styles).toHaveLength(1);
    expect(styles[0].textContent).toContain('--gc-accent:#3B7BDF;');
    expect(styles[0].textContent).toContain('@keyframes ghost-fade-in');
    const launcher = root.querySelector('#gc-launcher')!;
    expect(launcher.getAttribute('aria-label')).toBe('Open Ghost Cursor chat');
    expect(launcher.querySelector('svg polygon.gc-body')).not.toBeNull();
  });

  it('opens a panel with the dock socket, wordmark and status', async () => {
    const { root } = mount();
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();
    const panel = root.querySelector('.ghost-chat-panel')!;
    expect(panel).not.toBeNull();
    expect(root.querySelector('#gc-dock')!.getAttribute('data-state')).toBe('home');
    expect(panel.textContent).toContain('GHOSTCURSOR');
    expect(panel.textContent).toContain('AI COMPANION FOR THE WEB');
    expect(root.querySelector('.gc-status')!.textContent).toBe('Online');
    expect(root.querySelector('[aria-label="Close chat"]')).not.toBeNull();
  });

  it('renders the plan card when actions await approval', async () => {
    const { root } = mount({
      onSendMessage: async () => ({
        reply: 'Plan',
        status: 'awaiting_actions',
        runId: 'r',
        revision: 0,
        actions: [{ id: 'a1', type: 'toggle_switch', target_id: 'theme.toggle', state: true, explanation: 'Turn it on' }],
      }),
    });
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
    textarea.value = 'Turn on dark mode';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    const form = root.querySelector('form.gc-composer') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));

    await tick();
    await tick();
    await tick();

    const plan = root.querySelector('.gc-plan')!;
    expect(plan).not.toBeNull();
    expect(plan.textContent).toContain('Turn toggle ON');
    expect(plan.textContent).toContain('Turn it on');
    expect(plan.textContent).toContain('Cancel');
    expect(plan.textContent).toContain('Approve and Run');
    expect(plan.textContent).not.toContain('theme.toggle');
  });
});

