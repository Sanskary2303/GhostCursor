import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TourEngine } from './engine/TourEngine';
import type { TourStep } from './types';

const box = (left: number, top: number, width: number, height: number) =>
  ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect;

if (typeof CSS === 'undefined') {
  (globalThis as any).CSS = { escape: (s: string) => s };
}

const steps: TourStep[] = [
  { target_id: 'step-1-btn', message: 'First step description' },
  { target_id: 'step-2-btn', message: 'Second step description' },
];

function setupButtons() {
  const btn1 = document.createElement('button');
  btn1.setAttribute('data-ghost-id', 'step-1-btn');
  btn1.getBoundingClientRect = () => box(50, 50, 100, 40);
  btn1.scrollIntoView = () => {};
  document.body.appendChild(btn1);

  const btn2 = document.createElement('button');
  btn2.setAttribute('data-ghost-id', 'step-2-btn');
  btn2.getBoundingClientRect = () => box(200, 200, 100, 40);
  btn2.scrollIntoView = () => {};
  document.body.appendChild(btn2);

  return { btn1, btn2 };
}

describe('TourEngine', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('calls onStepShown with index 0 and element before tooltip exists', async () => {
    const { btn1 } = setupButtons();
    let recordedElement: HTMLElement | null = null;
    let recordedIndex: number | null = null;
    let messageElDuringCallback: Element | null = null;

    const tour = new TourEngine({
      onStepShown: (index, element) => {
        recordedIndex = index;
        recordedElement = element;
        const shadow = document.getElementById('ghost-tour-container')?.shadowRoot;
        messageElDuringCallback = shadow?.querySelector('.tour-message') ?? null;
      },
    });

    await tour.start(steps, document.body);

    expect(recordedIndex).toBe(0);
    expect(recordedElement).toBe(btn1);
    expect(messageElDuringCallback).toBeNull();

    const shadow = document.getElementById('ghost-tour-container')!.shadowRoot!;
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Step 1 of 2');

    await tour.stop();
  });

  it('sets tooltip z-index to 2147483250', async () => {
    setupButtons();
    const tour = new TourEngine();
    await tour.start(steps, document.body);

    const shadow = document.getElementById('ghost-tour-container')!.shadowRoot!;
    const tooltip = shadow.getElementById('ghost-tour-tooltip')!;
    expect(tooltip.style.zIndex).toBe('2147483250');

    await tour.stop();
  });

  it('moves to step 2 on ArrowRight from document, but ignores space from input', async () => {
    setupButtons();
    const input = document.createElement('input');
    document.body.appendChild(input);

    const tour = new TourEngine();
    await tour.start(steps, document.body);

    const shadow = document.getElementById('ghost-tour-container')!.shadowRoot!;
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Step 1 of 2');

    // Space from input should not trigger step change
    input.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, composed: true, cancelable: true }));
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Step 1 of 2');

    // ArrowRight on document moves to step 2
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    await new Promise(resolve => setTimeout(resolve, 80));
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Step 2 of 2');

    await tour.stop();
  });

  it('stops listening to keydown after stop() and removes bound listener', async () => {
    setupButtons();
    const addSpy = vi.spyOn(document, 'addEventListener');
    const removeSpy = vi.spyOn(document, 'removeEventListener');

    const tour = new TourEngine();
    await tour.start(steps, document.body);

    const addCall = addSpy.mock.calls.find(call => call[0] === 'keydown');
    expect(addCall).toBeDefined();
    const listener = addCall![1];

    await tour.stop();

    const removeCall = removeSpy.mock.calls.find(call => call[0] === 'keydown');
    expect(removeCall).toBeDefined();
    expect(removeCall![1]).toBe(listener);

    expect(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    }).not.toThrow();
    expect(document.getElementById('ghost-tour-container')).toBeNull();
  });

  it('sets Next button text to Next on step 1 and Finish on last step', async () => {
    setupButtons();
    const tour = new TourEngine();
    await tour.start(steps, document.body);

    const shadow = document.getElementById('ghost-tour-container')!.shadowRoot!;
    const nextBtn = shadow.getElementById('ghost-tour-next') as HTMLButtonElement;
    expect(nextBtn.textContent).toBe('Next');

    await tour.nextStep();
    await new Promise(resolve => setTimeout(resolve, 80));
    expect(nextBtn.textContent).toBe('Finish');

    await tour.stop();
  });

  it('matches target elements by visible text or aria-label as read-only fallback', async () => {
    const heading = document.createElement('h2');
    heading.textContent = 'Account Overview';
    heading.scrollIntoView = () => {};
    heading.getBoundingClientRect = () => box(10, 10, 150, 30);
    document.body.appendChild(heading);

    const tour = new TourEngine();
    await tour.start([{ target_id: 'account_overview', message: 'Look here' }], document.body);

    const shadow = document.getElementById('ghost-tour-container')!.shadowRoot!;
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Step 1 of 1');
    expect(shadow.querySelector('.tour-message')?.textContent).toContain('Look here');

    await tour.stop();
  });
});
