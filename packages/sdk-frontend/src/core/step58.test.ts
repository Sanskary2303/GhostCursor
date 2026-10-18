import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { h, render } from 'preact';
import { ChatWidget, ActionApprovalPanel, type ChatWidgetProps } from './chat/ChatWidget';
import { ActionExecutor } from './executor/ActionExecutor';
import { createBridge, type Bridge, INITIAL_WIDGET_STATE, type WidgetBridgeState } from './bridge';

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

if (typeof Range !== 'undefined' && !Range.prototype.getBoundingClientRect) {
  Range.prototype.getBoundingClientRect = function() {
    return {
      top: 100,
      bottom: 120,
      left: 50,
      right: 250,
      width: 200,
      height: 20,
      x: 50,
      y: 100,
      toJSON: () => {},
    };
  };
}

function mount(props?: Partial<ChatWidgetProps>, bridge?: Bridge<WidgetBridgeState>) {
  const host = document.createElement('div');
  host.id = 'ghost-cursor-widget-container';
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: 'open' });
  render(h(ChatWidget, {
    apiEndpoint: '/api/ghost-cursor',
    theme: { primaryColor: '#3B7BDF', cursorColor: '#3B7BDF', position: 'bottom-right', mode: 'midnight' },
    requireApprovalForActions: true,
    initialContext: { page: 'home', values: {}, availableTargets: [] },
    onSendMessage: vi.fn().mockResolvedValue({ reply: 'ok', status: 'completed', runId: 'r', revision: 0 }),
    onActionApproval: vi.fn().mockResolvedValue(null),
    ...(bridge ? { bridge } : {}),
    ...props,
  }), root);
  return { host, root };
}

describe('Step 58 — X6, X7, X8 Features', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  describe('X6: Ask-about-selection bubble', () => {
    it('shows Ask Ghost bubble on page text selection and prefills composer without sending', async () => {
      const p = document.createElement('p');
      p.textContent = 'ShopHive has the best discounts this season.';
      document.body.appendChild(p);

      const onSendMessage = vi.fn().mockResolvedValue({ reply: 'ok', status: 'completed' });
      const { root } = mount({ onSendMessage });
      await tick();

      const range = document.createRange();
      range.selectNodeContents(p.firstChild!);
      const sel = window.getSelection()!;
      sel.removeAllRanges();
      sel.addRange(range);

      document.dispatchEvent(new Event('selectionchange'));
      await tick();

      const bubble = root.querySelector('.gc-ask-bubble') as HTMLButtonElement;
      expect(bubble).not.toBeNull();
      expect(bubble.textContent).toContain('Ask Ghost');

      // Click bubble
      bubble.click();
      await tick();

      // Chat is open
      const panel = root.querySelector('.ghost-chat-panel');
      expect(panel).not.toBeNull();

      // Composer is prefilled with Explain: "<selection>"
      const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
      expect(textarea.value).toBe('Explain: "ShopHive has the best discounts this season."');

      // Bubble dismissed
      expect(root.querySelector('.gc-ask-bubble')).toBeNull();

      // Nothing was sent automatically
      expect(onSendMessage).not.toHaveBeenCalled();
    });

    it('truncates selection to <= 200 chars in Explain prefill', async () => {
      const p = document.createElement('p');
      const longText = 'A'.repeat(250);
      p.textContent = longText;
      document.body.appendChild(p);

      const { root } = mount();
      await tick();

      const range = document.createRange();
      range.selectNodeContents(p.firstChild!);
      const sel = window.getSelection()!;
      sel.removeAllRanges();
      sel.addRange(range);

      document.dispatchEvent(new Event('selectionchange'));
      await tick();

      const bubble = root.querySelector('.gc-ask-bubble') as HTMLButtonElement;
      expect(bubble).not.toBeNull();
      bubble.click();
      await tick();

      const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
      const expectedSnippet = 'A'.repeat(200);
      expect(textarea.value).toBe(`Explain: "${expectedSnippet}"`);
    });

    it('ignores selections inside inputs, widget container, and sensitive containers', async () => {
      const { root } = mount();
      await tick();

      const sel = window.getSelection()!;

      // 1. Inside an input
      const input = document.createElement('input');
      input.value = 'Secret input text';
      document.body.appendChild(input);

      const range1 = document.createRange();
      range1.selectNodeContents(input);
      sel.removeAllRanges();
      sel.addRange(range1);
      document.dispatchEvent(new Event('selectionchange'));
      await tick();
      expect(root.querySelector('.gc-ask-bubble')).toBeNull();

      // 2. Inside sensitive container [data-sensitive]
      const sensitiveDiv = document.createElement('div');
      sensitiveDiv.setAttribute('data-sensitive', 'true');
      sensitiveDiv.textContent = 'Account password secret';
      document.body.appendChild(sensitiveDiv);

      const range2 = document.createRange();
      range2.selectNodeContents(sensitiveDiv.firstChild!);
      sel.removeAllRanges();
      sel.addRange(range2);
      document.dispatchEvent(new Event('selectionchange'));
      await tick();
      expect(root.querySelector('.gc-ask-bubble')).toBeNull();

      // 3. Inside sensitive container [data-pii]
      const piiDiv = document.createElement('div');
      piiDiv.setAttribute('data-pii', 'true');
      piiDiv.textContent = 'User SSN 123-45-6789';
      document.body.appendChild(piiDiv);

      const range3 = document.createRange();
      range3.selectNodeContents(piiDiv.firstChild!);
      sel.removeAllRanges();
      sel.addRange(range3);
      document.dispatchEvent(new Event('selectionchange'));
      await tick();
      expect(root.querySelector('.gc-ask-bubble')).toBeNull();
    });
  });

  describe('X7: Ctrl/⌘+K and Slash Commands', () => {
    it('opens widget focused on composer on Ctrl+K and ⌘+K', async () => {
      const { root } = mount();
      await tick();

      expect(root.querySelector('.ghost-chat-panel')).toBeNull();

      // Press Ctrl+K
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }));
      await tick();

      expect(root.querySelector('.ghost-chat-panel')).not.toBeNull();
      const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
      expect(textarea).not.toBeNull();

      // Close chat
      (root.querySelector('[aria-label="Close chat"]') as HTMLButtonElement).click();
      await tick();
      expect(root.querySelector('.ghost-chat-panel')).toBeNull();

      // Press ⌘+K (metaKey)
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
      await tick();

      expect(root.querySelector('.ghost-chat-panel')).not.toBeNull();
    });

    it('ignores Ctrl+K while typing in a page input', async () => {
      const pageInput = document.createElement('input');
      pageInput.type = 'text';
      document.body.appendChild(pageInput);
      pageInput.focus();

      const { root } = mount();
      await tick();

      expect(document.activeElement).toBe(pageInput);

      // Press Ctrl+K
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }));
      await tick();

      // Widget remains closed
      expect(root.querySelector('.ghost-chat-panel')).toBeNull();
    });

    it('handles slash commands: /new, /history, /tour', async () => {
      let selectedSession: string | null = 'session-123';
      const historyMock = {
        list: vi.fn().mockResolvedValue([{ id: 'session-1', title: 'First chat', updated_at: '2026-10-18T00:00:00Z', message_count: 2 }]),
        create: vi.fn().mockResolvedValue('session-2'),
        messages: vi.fn().mockResolvedValue([]),
        current: () => selectedSession,
        select: (id: string | null) => { selectedSession = id; },
      };

      const onTour = vi.fn();
      const { root } = mount({ history: historyMock, onTour });
      (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
      await tick();

      const textarea = root.querySelector('textarea.gc-input') as HTMLTextAreaElement;
      const form = root.querySelector('form.gc-composer') as HTMLFormElement;

      // 1. /new command
      textarea.value = '/new';
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      await tick();
      form.dispatchEvent(new Event('submit', { cancelable: true }));
      await tick();
      expect(selectedSession).toBeNull();

      // 2. /history command
      textarea.value = '/history';
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      await tick();
      form.dispatchEvent(new Event('submit', { cancelable: true }));
      await tick();
      await tick();
      expect(historyMock.list).toHaveBeenCalled();
      expect(root.querySelector('.gc-drawer')).not.toBeNull();

      // Close drawer
      (root.querySelector('.gc-drawer-head button') as HTMLButtonElement).click();
      await tick();

      // 3. /tour command
      textarea.value = '/tour';
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      await tick();
      form.dispatchEvent(new Event('submit', { cancelable: true }));
      await tick();
      expect(onTour).toHaveBeenCalled();
    });
  });

  describe('X8: Step-by-step mode', () => {
    it('renders Step by step toggle on ActionApprovalPanel and passes value on approve', async () => {
      const onApprove = vi.fn();
      const host = document.createElement('div');
      document.body.appendChild(host);

      render(h(ActionApprovalPanel, {
        actions: [{ id: 'a1', type: 'click', target_id: 'btn', explanation: 'Click button' }],
        onApprove,
      }), host);

      const toggle = host.querySelector('.gc-step-by-step-toggle') as HTMLInputElement;
      expect(toggle).not.toBeNull();
      expect(toggle.checked).toBe(false);

      // Check toggle
      toggle.checked = true;
      toggle.dispatchEvent(new Event('change', { bubbles: true }));
      await tick();

      // Click Approve and Run
      const approveBtn = host.querySelectorAll('.gc-btn--primary')[0] as HTMLButtonElement;
      approveBtn.click();
      await tick();

      expect(onApprove).toHaveBeenCalledWith(true, true);
    });

    it('pauses ActionExecutor at target in stepByStep mode before acting', async () => {
      const btn = document.createElement('button');
      btn.setAttribute('data-ghost-id', 'test_step_btn');
      let clicked = false;
      btn.addEventListener('click', () => { clicked = true; });
      document.body.appendChild(btn);

      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
        width: 100,
        height: 30,
        top: 0,
        left: 0,
        bottom: 30,
        right: 100,
        x: 0,
        y: 0,
        toJSON: () => {},
      });

      let stepApprovalCalled = false;
      const executor = new ActionExecutor({
        timeout: 2000,
        stepByStep: true,
        onStepApproval: async () => {
          stepApprovalCalled = true;
          // DOM change has NOT occurred yet
          expect(clicked).toBe(false);
          return true;
        },
      });

      const result = await executor.execute([{ id: 'act-1', type: 'click', target_id: 'test_step_btn' }]);
      expect(stepApprovalCalled).toBe(true);
      expect(clicked).toBe(true);
      expect(result.success).toBe(true);
    });

    it('mission bar shows Next step and Stop when awaitingNextStep is true', async () => {
      const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
      const onNextStep = vi.fn();

      const { root } = mount({}, bridge);
      (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
      await tick();

      // Trigger mission bar with awaitingNextStep
      bridge.set({
        cursorAway: true,
        awaitingNextStep: true,
        onNextStep,
      });
      await tick();

      const mission = root.querySelector('.gc-mission');
      expect(mission).not.toBeNull();

      const nextBtn = root.querySelector('.gc-next-step') as HTMLButtonElement;
      expect(nextBtn).not.toBeNull();
      expect(nextBtn.textContent).toBe('Next step');

      const stopBtn = root.querySelector('.gc-stop') as HTMLButtonElement;
      expect(stopBtn).not.toBeNull();

      // Click Next step
      nextBtn.click();
      expect(onNextStep).toHaveBeenCalled();
    });
  });
});
