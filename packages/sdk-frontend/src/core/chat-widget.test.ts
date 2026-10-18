import { describe, it, expect, vi, afterEach } from 'vitest';
import { h, render } from 'preact';
import { ChatWidget, type ChatWidgetProps, ActionApprovalPanel, createBarsSvg } from './chat/ChatWidget';
import { createBridge, type Bridge, INITIAL_WIDGET_STATE, type WidgetBridgeState } from './bridge';
import { registerTarget, clearTargetRegistry } from './dom-utils';

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

function mount(props?: Partial<ChatWidgetProps>, bridge?: Bridge<WidgetBridgeState>) {
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
    ...(bridge ? { bridge } : {}),
    ...props,
  }), root);
  return { host, root };
}

describe('ChatWidget shell', () => {
  afterEach(() => {
    clearTargetRegistry();
    document.body.innerHTML = '';
  });

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

  it('updates header dock state and status info from bridge', async () => {
    const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
    const { root } = mount({}, bridge);
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    bridge.set({ step: { index: 2, total: 3 } });
    await tick();
    expect(root.querySelector('.gc-status')!.textContent).toBe('Step 2/3');

    bridge.set({ step: null, outcome: 'error' });
    await tick();
    expect(root.querySelector('#gc-dock')!.getAttribute('data-outcome')).toBe('error');
    expect(root.querySelector('.gc-status')!.textContent).toBe('Needs help');

    bridge.set({ cursorAway: true });
    await tick();
    expect(root.querySelector('#gc-dock')!.getAttribute('data-state')).toBe('away');
  });

  it('collapses into the mission bar while cursor is away and restores full panel when back', async () => {
    const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
    const { root } = mount({}, bridge);
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    expect(root.querySelector('[role="log"]')).not.toBeNull();
    expect(root.querySelector('.ghost-chat-panel.gc-mission')).toBeNull();

    bridge.set({ cursorAway: true, status: '2/3 • Click Add to Cart' });
    await tick();

    expect(root.querySelector('.ghost-chat-panel.gc-mission')).not.toBeNull();
    expect(root.querySelector('[role="log"]')).toBeNull();
    expect(root.querySelector('.gc-mission-status')!.textContent).toBe('2/3 • Click Add to Cart');

    bridge.set({ cursorAway: false });
    await tick();

    expect(root.querySelector('.ghost-chat-panel.gc-mission')).toBeNull();
    expect(root.querySelector('[role="log"]')).not.toBeNull();
  });

  it('renders recovery card with duration and allows retry on action failure', async () => {
    const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
    let sendCount = 0;
    let showedSteps: any = null;
    const { root } = mount({
      onSendMessage: async () => {
        sendCount++;
        return {
          reply: 'Plan',
          status: 'awaiting_actions',
          runId: 'r',
          revision: 0,
          actions: [
            { id: 'a1', type: 'click', target_id: 'cart.btn', explanation: 'Add to cart' },
          ],
        };
      },
      onActionApproval: async () => {
        bridge.set({
          lastRun: {
            results: [{ ok: false, error: 'Element disabled' }],
            ms: 2400,
          },
        });
        return {
          reply: 'Step 1 of 1 couldn\'t finish: "Element disabled". Steps done before it were kept.',
          status: 'failed',
          runId: 'r',
          revision: 1,
        };
      },
      onShowMe: (steps) => {
        showedSteps = steps;
      },
    }, bridge);

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
    textarea.value = 'Add to cart';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    const form = root.querySelector('form.gc-composer') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));

    await tick();
    await tick();
    await tick();

    const approveBtn = root.querySelector('.gc-plan .gc-btn--primary') as HTMLButtonElement;
    expect(approveBtn).not.toBeNull();
    approveBtn.click();

    await tick();
    await tick();
    await tick();

    const card = root.querySelector('.gc-card--recovery')!;
    expect(card).not.toBeNull();
    expect(card.textContent).toContain('FAILED AT STEP 1');
    expect(card.textContent).toContain('2.4 s');
    expect(card.textContent).toContain('✕');
    expect(card.textContent).toContain('Element disabled');

    const showMeBtn = card.querySelector('button.gc-btn--ghost') as HTMLButtonElement;
    expect(showMeBtn).not.toBeNull();
    expect(showMeBtn.textContent).toContain('Show me where');
    showMeBtn.click();
    expect(showedSteps).toEqual([{ targetId: 'cart.btn', label: 'Click button' }]);

    const tryAgainBtn = card.querySelector('button.gc-btn--primary') as HTMLButtonElement;
    expect(tryAgainBtn).not.toBeNull();
    expect(tryAgainBtn.textContent).toContain('Try again');

    expect(sendCount).toBe(1);
    tryAgainBtn.click();
    await tick();
    await tick();
    expect(sendCount).toBe(2);
  });

  it('calls onShowMe with only unfinished steps (failed and skipped)', async () => {
    const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
    let showedSteps: any = null;
    const { root } = mount({
      onSendMessage: async () => ({
        reply: 'Plan',
        status: 'awaiting_actions',
        runId: 'r',
        revision: 0,
        actions: [
          { id: 'a1', type: 'click', target_id: 'cart.step1', explanation: 'Step 1' },
          { id: 'a2', type: 'click', target_id: 'cart.step2', explanation: 'Step 2' },
          { id: 'a3', type: 'click', target_id: 'cart.step3', explanation: 'Step 3' },
        ],
      }),
      onActionApproval: async () => {
        bridge.set({
          lastRun: {
            results: [
              { ok: true },
              { ok: false, error: 'Target obstructed' },
            ],
            ms: 3100,
          },
        });
        return {
          reply: 'Plan failed at step 2',
          status: 'failed',
          runId: 'r',
          revision: 1,
        };
      },
      onShowMe: (steps) => {
        showedSteps = steps;
      },
    }, bridge);

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
    textarea.value = 'Checkout';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    const form = root.querySelector('form.gc-composer') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));

    await tick();
    await tick();
    await tick();

    const approveBtn = root.querySelector('.gc-plan .gc-btn--primary') as HTMLButtonElement;
    expect(approveBtn).not.toBeNull();
    approveBtn.click();

    await tick();
    await tick();
    await tick();

    const card = root.querySelector('.gc-card--recovery')!;
    expect(card).not.toBeNull();
    expect(card.querySelectorAll('.gc-card-step')).toHaveLength(3);

    const showMeBtn = card.querySelector('button.gc-btn--ghost') as HTMLButtonElement;
    expect(showMeBtn).not.toBeNull();
    showMeBtn.click();

    expect(showedSteps).toHaveLength(2);
    expect(showedSteps).toEqual([
      { targetId: 'cart.step2', label: 'Click step2' },
      { targetId: 'cart.step3', label: 'Click step3' },
    ]);
  });

  it('renders history button and opens drawer to list sessions and filter by query', async () => {
    const mockSessions = [
      { session_id: '11111111-1111-1111-1111-111111111111', title: 'Sneakers Search', summary: 'Looking for Nike shoes', updated_at: '2026-10-17T12:00:00Z' },
      { session_id: '22222222-2222-2222-2222-222222222222', title: 'Order Tracking', summary: 'Where is SH-1024', updated_at: '2026-10-17T14:00:00Z' },
    ];
    let selectedId: string | null = 'initial';

    const history = {
      list: async () => mockSessions,
      create: async () => '33333333-3333-3333-3333-333333333333',
      messages: async () => [],
      current: () => selectedId,
      select: (id: string | null) => { selectedId = id; },
    };

    const { root } = mount({ history });

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const histBtn = root.querySelector('button[aria-label="Chat history"]') as HTMLButtonElement;
    expect(histBtn).not.toBeNull();

    // Open drawer
    histBtn.click();
    await tick();

    const drawer = root.querySelector('.gc-drawer');
    expect(drawer).not.toBeNull();

    const items = drawer!.querySelectorAll('.gc-drawer-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('Sneakers Search');
    expect(items[1].textContent).toContain('Order Tracking');

    // Filter by query
    const searchInput = drawer!.querySelector('.gc-drawer-search') as HTMLInputElement;
    searchInput.value = 'order';
    searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    const filteredItems = drawer!.querySelectorAll('.gc-drawer-item');
    expect(filteredItems).toHaveLength(1);
    expect(filteredItems[0].textContent).toContain('Order Tracking');

    // Escape closes the drawer first while panel remains open
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await tick();
    expect(root.querySelector('.gc-drawer')).toBeNull();
    expect(root.querySelector('.ghost-chat-panel')).not.toBeNull();
  });

  it('re-hydrates messages on mount and displays Earlier in this chat divider', async () => {
    const history = {
      list: async () => [],
      create: async () => null,
      messages: async () => [
        { role: 'user' as const, content: 'What sizes are available?' },
        { role: 'assistant' as const, content: 'Size 10 and 11 are in stock.' },
      ],
      current: () => '11111111-1111-1111-1111-111111111111',
      select: () => {},
    };

    const { root } = mount({ history });
    await tick();
    await tick();

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const divider = root.querySelector('.gc-divider');
    expect(divider).not.toBeNull();
    expect(divider!.textContent).toBe('Earlier in this chat');

    const msgs = root.querySelectorAll('.gc-msg');
    expect(msgs).toHaveLength(2);
    expect(msgs[0].textContent).toContain('What sizes are available?');
    expect(msgs[1].textContent).toContain('Size 10 and 11 are in stock.');
  });

  it('clears stale session when messages(storedId) returns 404', async () => {
    let selectedId: string | null = 'stale-session-id';
    const history = {
      list: async () => [],
      create: async () => null,
      messages: async () => {
        throw new Error('HTTP 404');
      },
      current: () => selectedId,
      select: (id: string | null) => {
        selectedId = id;
      },
    };

    const { root } = mount({ history });
    await tick();
    await tick();

    expect(selectedId).toBeNull();

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const empty = root.querySelector('.gc-empty');
    expect(empty).not.toBeNull();
    expect(root.querySelectorAll('.gc-msg')).toHaveLength(0);
  });

  it('displays user-friendly message on HTTP 401 and clears error on subsequent send', async () => {
    let shouldFail = true;
    const { root } = mount({
      onSendMessage: async () => {
        if (shouldFail) {
          throw new Error('HTTP 401');
        }
        return { reply: 'Welcome back!', status: 'completed', runId: 'r2', revision: 0 };
      },
    });

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
    const form = root.querySelector('form.gc-composer') as HTMLFormElement;

    textarea.value = 'Hello';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await tick();
    await tick();

    const msgs = root.querySelectorAll('.gc-msg');
    expect(msgs).toHaveLength(2);
    expect(msgs[1].textContent).toContain('Please sign in to use the assistant.');

    // Next turn recovers and clears error
    shouldFail = false;
    textarea.value = 'Hello again';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await tick();
    await tick();

    const updatedMsgs = root.querySelectorAll('.gc-msg');
    expect(updatedMsgs).toHaveLength(4);
    expect(updatedMsgs[3].textContent).toContain('Welcome back!');
  });

  it('risk: "confirm" shows warning ⚠️, requires confirmation checkbox before Approve and Run is enabled', async () => {
    registerTarget('sensitive_btn', {
      page: 'checkout',
      resolve: () => document.createElement('button'),
      operations: ['click'],
      risk: 'confirm',
    });

    const onApprove = vi.fn();
    const host = document.createElement('div');
    document.body.appendChild(host);
    render(h(ActionApprovalPanel, {
      actions: [{ id: 'a1', type: 'click', target_id: 'sensitive_btn' }],
      onApprove,
      currentPage: 'checkout',
    }), host);

    expect(host.textContent).toContain('⚠️');
    expect(host.textContent).toContain("I understand this step can't be undone");

    const approveBtn = host.querySelector('.gc-btn--primary') as HTMLButtonElement;
    expect(approveBtn).not.toBeNull();
    expect(approveBtn.disabled).toBe(true);

    const checkbox = host.querySelector('.gc-plan-confirm-checkbox') as HTMLInputElement;
    expect(checkbox).not.toBeNull();
    expect(checkbox.checked).toBe(false);

    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    await tick();

    expect(approveBtn.disabled).toBe(false);
    approveBtn.click();
    expect(onApprove).toHaveBeenCalledWith(true, false);
  });

  it('preview link and other page label in ActionApprovalPanel', async () => {
    const el = document.createElement('button');
    el.setAttribute('data-ghost-id', 'page_btn');
    document.body.appendChild(el);

    registerTarget('page_btn', {
      page: 'home',
      resolve: () => el,
      operations: ['click'],
    });

    registerTarget('settings_btn', {
      page: 'settings',
      resolve: () => null,
      operations: ['click'],
    });

    const onPreview = vi.fn();
    const onClearPreview = vi.fn();
    const host = document.createElement('div');
    document.body.appendChild(host);

    render(h(ActionApprovalPanel, {
      actions: [
        { id: 's1', type: 'click', target_id: 'page_btn' },
        { id: 's2', type: 'click', target_id: 'settings_btn' },
      ],
      onApprove: () => {},
      currentPage: 'home',
      onPreview,
      onClearPreview,
    }), host);

    // Step on settings shows "on Settings"
    expect(host.textContent).toContain('on Settings');

    // Preview link triggers onPreview with on-page elements
    const previewBtn = host.querySelector('.gc-plan-preview') as HTMLButtonElement;
    expect(previewBtn).not.toBeNull();
    previewBtn.click();
    expect(onPreview).toHaveBeenCalledWith([el]);

    // Mouse leave triggers onClearPreview
    const plan = host.querySelector('.gc-plan') as HTMLElement;
    plan.dispatchEvent(new Event('mouseleave'));
    expect(onClearPreview).toHaveBeenCalled();
  });

  it('tracks running page: navigate step has no other page label, subsequent step on that page has "on Settings"', async () => {
    registerTarget('theme.toggle', {
      page: 'settings',
      resolve: () => document.createElement('input'),
      operations: ['toggle'],
    });

    const host = document.createElement('div');
    document.body.appendChild(host);

    render(h(ActionApprovalPanel, {
      actions: [
        { id: 'a1', type: 'navigate', target_page: 'settings' },
        { id: 'a2', type: 'toggle_switch', target_id: 'theme.toggle', state: true },
      ],
      onApprove: () => {},
      currentPage: 'home',
    }), host);

    const steps = host.querySelectorAll('.gc-plan-step');
    expect(steps).toHaveLength(2);

    // The navigate step's text does not contain "on Settings"
    expect(steps[0].textContent).not.toContain('on Settings');

    // The toggle step's text contains "on Settings"
    expect(steps[1].textContent).toContain('on Settings');
  });

  it('renders SVG bar chart with createElementNS and sets textContent', () => {
    const barsCard = {
      type: 'bars' as const,
      series: [
        { label: 'Current', value: 30 },
        { label: 'SAVE20', value: 25 },
        { label: 'Break-even Vol', value: 14.5 },
      ],
    };

    const svg = createBarsSvg(barsCard);
    expect(svg.namespaceURI).toBe('http://www.w3.org/2000/svg');
    expect(svg.getAttribute('viewBox')).toBe('0 0 280 120');

    const rects = svg.querySelectorAll('rect.gc-bar-rect');
    expect(rects).toHaveLength(3);

    const valTexts = svg.querySelectorAll('text.gc-bar-val');
    expect(valTexts).toHaveLength(3);
    expect(valTexts[0].textContent).toBe('30');
    expect(valTexts[1].textContent).toBe('25');
    expect(valTexts[2].textContent).toBe('14.5');

    const labelTexts = svg.querySelectorAll('text.gc-bar-label');
    expect(labelTexts).toHaveLength(3);
    expect(labelTexts[0].textContent).toBe('Current');
    expect(labelTexts[1].textContent).toBe('SAVE20');
    expect(labelTexts[2].textContent).toBe('Break-even Vol');
  });

  it('renders metric and bars cards in chat widget response', async () => {
    const { root } = mount({
      onSendMessage: async () => ({
        reply: 'Here is your simulated margin analysis.',
        status: 'completed',
        runId: 'r_sim',
        revision: 1,
        cards: [
          {
            type: 'metric',
            label: 'Projected Margin',
            value: '25%',
            delta: '-5%',
          },
          {
            type: 'bars',
            series: [
              { label: 'Current', value: 30 },
              { label: 'SAVE20', value: 25 },
            ],
          },
        ],
      }),
    });

    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();

    const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
    textarea.value = 'Simulate SAVE20 margin';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();

    const form = root.querySelector('form.gc-composer') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));

    await tick();
    await tick();
    await tick();

    // Verify insight cards rendered
    const cardsContainer = root.querySelector('.gc-insight-cards');
    expect(cardsContainer).not.toBeNull();

    const metricCard = root.querySelector('.gc-metric-card');
    expect(metricCard).not.toBeNull();
    expect(metricCard!.querySelector('.gc-metric-label')!.textContent).toBe('Projected Margin');
    expect(metricCard!.querySelector('.gc-metric-value')!.textContent).toBe('25%');
    expect(metricCard!.querySelector('.gc-metric-delta')!.textContent).toBe('-5%');

    const barsCard = root.querySelector('.gc-bars-card');
    expect(barsCard).not.toBeNull();
    expect(barsCard!.querySelector('svg.gc-bars-svg')).not.toBeNull();
    const labels = Array.from(barsCard!.querySelectorAll('.gc-bar-label')).map(el => el.textContent);
    expect(labels).toEqual(['Current', 'SAVE20']);
  });

  it('renders suggestion chips in empty state and clicking sends message', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: any) => {
      if (String(url).includes('/suggestions')) {
        return {
          ok: true,
          json: async () => ['What sizes are in stock?', 'Is shipping free?'],
        } as any;
      }
      return { ok: false } as any;
    });

    const sendSpy = vi.fn().mockResolvedValue({ reply: 'Here are sizes', status: 'completed', runId: 'r', revision: 0 });
    const { root } = mount({
      onSendMessage: sendSpy,
      getPage: () => 'products',
    });

    // Open chat
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();
    await tick();

    // Verify chips rendered
    const chips = root.querySelectorAll('.gc-chip');
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toBe('What sizes are in stock?');
    expect(chips[1].textContent).toBe('Is shipping free?');

    // Click first chip
    (chips[0] as HTMLButtonElement).click();
    await tick();

    expect(sendSpy).toHaveBeenCalledWith(
      'What sizes are in stock?',
      expect.anything(),
      expect.anything(),
    );

    fetchSpy.mockRestore();
  });
});



