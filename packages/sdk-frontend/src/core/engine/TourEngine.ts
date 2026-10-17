/**
 * Tour Engine - Guided spotlight walkthrough overlay
 * Renders in Shadow DOM for style isolation while highlighting Host DOM elements
 */

import type { TourStep } from '../types';
import { getRegisteredTarget } from '../dom-utils';

export interface TourOptions {
  onStepChange?: (stepIndex: number, step: TourStep) => void;
  onComplete?: () => void;
  onSkip?: () => void;
  spotlightColor?: string;
  spotlightOpacity?: number;
  /** Awaited after the spotlight is placed and before the tooltip shows. Fly the cursor here. */
  onStepShown?: (index: number, element: HTMLElement, step: TourStep) => Promise<void> | void;
}

const DEFAULT_OPTIONS: Required<TourOptions> = {
  onStepChange: () => {},
  onComplete: () => {},
  onSkip: () => {},
  spotlightColor: '#3B7BDF',
  spotlightOpacity: 0.55,
  onStepShown: () => {},
};

interface TourState {
  steps: TourStep[];
  currentIndex: number;
  isActive: boolean;
  overlayElement: HTMLElement | null;
  spotlightElement: HTMLElement | null;
  tooltipElement: HTMLElement | null;
  shadowRoot: ShadowRoot | null;
}

export class TourEngine {
  private options: Required<TourOptions>;
  private state: TourState;
  private hostElement: HTMLElement | null = null;
  private readonly onKeydown = (event: KeyboardEvent) => this.handleKeydown(event);

  constructor(options: TourOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.state = {
      steps: [],
      currentIndex: 0,
      isActive: false,
      overlayElement: null,
      spotlightElement: null,
      tooltipElement: null,
      shadowRoot: null,
    };
  }

  /**
   * Start a guided tour
   */
  async start(steps: TourStep[], hostElement: HTMLElement): Promise<void> {
    if (this.state.isActive) {
      await this.stop();
    }

    this.hostElement = hostElement;
    this.state.steps = steps;
    this.state.currentIndex = 0;
    this.state.isActive = true;

    // Create shadow root for isolated styles
    this.createShadowUI();

    // Show first step
    await this.showStep(0);
  }

  /**
   * Create the Shadow DOM UI for tour controls
   */
  private createShadowUI(): void {
    if (!this.hostElement) return;

    // Create a custom element to hold our shadow root
    const container = document.createElement('div');
    container.id = 'ghost-tour-container';
    this.hostElement.appendChild(container);

    // Attach shadow root
    this.state.shadowRoot = container.attachShadow({ mode: 'open' });

    // Inject styles
    this.injectStyles();

    // Create overlay (covers entire viewport, with hole for spotlight)
    this.state.overlayElement = document.createElement('div');
    this.state.overlayElement.id = 'ghost-tour-overlay';
    this.state.overlayElement.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: transparent;
      pointer-events: none;
      z-index: 2147483000;
      display: none;
    `;
    this.state.overlayElement.style.background = 'transparent';
    this.state.shadowRoot.appendChild(this.state.overlayElement);

    // Create spotlight (the hole in the overlay)
    this.state.spotlightElement = document.createElement('div');
    this.state.spotlightElement.id = 'ghost-tour-spotlight';
    this.state.spotlightElement.style.cssText = `
      position: fixed;
      border-radius: 8px;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, ${this.options.spotlightOpacity});
      pointer-events: none;
      z-index: 2147483001;
      display: none;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      border: 3px solid ${this.options.spotlightColor};
    `;
    this.state.shadowRoot.appendChild(this.state.spotlightElement);

    // Create tooltip
    this.state.tooltipElement = document.createElement('div');
    this.state.tooltipElement.id = 'ghost-tour-tooltip';
    this.state.tooltipElement.style.cssText = `
      position: fixed;
      max-width: 320px;
      padding: 16px 20px;
      background: #111828;
      color: #F8FAFC;
      border: 1px dashed rgba(59, 123, 223, 0.6);
      border-radius: 12px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
      z-index: 2147483250;
      display: none;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      pointer-events: auto;
    `;
    this.state.shadowRoot.appendChild(this.state.tooltipElement);

    // Create navigation controls
    const controls = document.createElement('div');
    controls.id = 'ghost-tour-controls';
    controls.style.cssText = `
      display: flex;
      gap: 8px;
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px dashed rgba(59, 123, 223, 0.35);
    `;
    const base = 'padding:8px 14px;border:none;border-radius:8px;cursor:pointer;font:600 13px/1 Inter,-apple-system,"Segoe UI",Roboto,sans-serif;';
    const makeButton = (id: string, text: string, css: string) => {
      const button = document.createElement('button');
      button.id = id;
      button.type = 'button';
      button.textContent = text;
      button.style.cssText = base + css;
      return button;
    };
    controls.append(
      makeButton('ghost-tour-prev', 'Previous', 'background:#1A2336;color:#F8FAFC;'),
      makeButton('ghost-tour-next', 'Next', 'background:#3B7BDF;color:#fff;'),
      makeButton('ghost-tour-skip', 'Skip Tour', 'background:transparent;color:#94A3B8;margin-left:auto;'),
    );
    this.state.tooltipElement.appendChild(controls);

    // Attach event listeners
    this.state.shadowRoot.getElementById('ghost-tour-prev')!.addEventListener('click', () => this.previousStep());
    this.state.shadowRoot.getElementById('ghost-tour-next')!.addEventListener('click', () => this.nextStep());
    this.state.shadowRoot.getElementById('ghost-tour-skip')!.addEventListener('click', () => this.skipTour());

    // Keyboard navigation
    document.addEventListener('keydown', this.onKeydown);
  }

  private injectStyles(): void {
    const style = document.createElement('style');
    style.textContent = `
      #ghost-tour-tooltip {
        animation: ghost-tour-slide-in 0.3s ease-out;
      }
      @keyframes ghost-tour-slide-in {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      #ghost-tour-spotlight {
        animation: ghost-tour-pulse 2s ease-in-out infinite;
      }
      @keyframes ghost-tour-pulse {
        0%, 100% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55), 0 0 20px rgba(59, 123, 223, 0.5); }
        50% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55), 0 0 30px rgba(59, 123, 223, 0.8); }
      }
      #ghost-tour-overlay {
        animation: ghost-tour-fade-in 0.3s ease-out;
      }
      @keyframes ghost-tour-fade-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }
    `;
    this.state.shadowRoot!.appendChild(style);
  }

  private handleKeydown(event: KeyboardEvent): void {
    if (!this.state.isActive) return;

    const origin = event.composedPath()[0];
    if (origin instanceof HTMLElement && (origin.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(origin.tagName))) return;

    switch (event.key) {
      case 'ArrowRight':
      case ' ':
        event.preventDefault();
        this.nextStep();
        break;
      case 'ArrowLeft':
        event.preventDefault();
        this.previousStep();
        break;
      case 'Escape':
        this.skipTour();
        break;
    }
  }

  /**
   * Show a specific step
   */
  private async showStep(index: number): Promise<void> {
    const step = this.state.steps[index];
    if (!step) return;

    // Find target element with retry
    let targetElement = this.findTargetElement(step.target_id);
    if (!targetElement) {
      const start = Date.now();
      while (!targetElement && Date.now() - start < 1500) {
        await new Promise(resolve => setTimeout(resolve, 50));
        targetElement = this.findTargetElement(step.target_id);
      }
    }

    if (!targetElement) {
      console.warn(`[TourEngine] Target element not found: ${step.target_id}`);
      // Move to next step if target not found
      if (index < this.state.steps.length - 1) {
        await this.showStep(index + 1);
      } else {
        await this.complete();
      }
      return;
    }

    // Scroll target into view
    const reduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    targetElement.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center', inline: 'center' });
    await new Promise(resolve => setTimeout(resolve, reduced ? 50 : 400));

    // Get target position
    const rect = targetElement.getBoundingClientRect();

    // Show overlay and spotlight
    if (this.state.overlayElement) {
      this.state.overlayElement.style.display = 'block';
    }
    if (this.state.spotlightElement) {
      this.state.spotlightElement.style.display = 'block';
      this.state.spotlightElement.style.left = `${rect.left - 8}px`;
      this.state.spotlightElement.style.top = `${rect.top - 8}px`;
      this.state.spotlightElement.style.width = `${rect.width + 16}px`;
      this.state.spotlightElement.style.height = `${rect.height + 16}px`;
    }

    await this.options.onStepShown(index, targetElement, step);
    if (!this.state.isActive) return;

    // Position tooltip
    this.positionTooltip(rect, step.message);

    // Update controls
    this.updateControls(index);

    // Notify callback
    this.options.onStepChange(index, step);
  }

  /**
   * Find target element using the Element Targeting Cascade
   */
  private findTargetElement(targetId: string): HTMLElement | null {
    const esc = typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(targetId)
      : targetId.replace(/["\\]/g, '\\$&');

    // Try data-ghost-id first
    let element = document.querySelector<HTMLElement>(`[data-ghost-id="${esc}"]`);
    if (element) return element;

    // Try data-testid
    element = document.querySelector<HTMLElement>(`[data-testid="${esc}"]`);
    if (element) return element;

    // Try id
    element = document.getElementById(targetId);
    if (element) return element;

    // Try aria-label
    element = document.querySelector<HTMLElement>(`[aria-label="${esc}"]`);
    if (element) return element;

    // Try registered target
    try {
      const reg = getRegisteredTarget(targetId);
      if (reg) {
        if (typeof reg.resolve === 'function') {
          const el = reg.resolve();
          if (el) return el;
        }
        if ((reg as any).selector) {
          const el = document.querySelector<HTMLElement>((reg as any).selector);
          if (el) return el;
        }
      }
    } catch {}

    // Read-only fallback (tours never change the page): exact visible text or aria-label.
    const wanted = targetId.replace(/[_-]+/g, ' ').trim().toLowerCase();
    if (wanted.length >= 3 && wanted.length <= 60) {
      const candidates = document.querySelectorAll<HTMLElement>('a, button, [role="button"], [role="tab"], h1, h2, h3, label');
      for (const el of Array.from(candidates)) {
        if (el.closest('[data-sensitive], [data-pii], #ghost-cursor-widget-container')) continue;
        const text = (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
        if (text === wanted) return el;
      }
    }

    return null;
  }

  /**
   * Position tooltip near the spotlight
   */
  private positionTooltip(rect: DOMRect, message: string): void {
    if (!this.state.tooltipElement) return;

    const tooltip = this.state.tooltipElement;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const tooltipRect = { width: 320, height: 140 }; // Estimated

    // Try to position below the target
    let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
    let top = rect.bottom + 16;

    // Adjust if off-screen
    if (left < 16) left = 16;
    if (left + tooltipRect.width > viewportWidth - 16) {
      left = viewportWidth - tooltipRect.width - 16;
    }
    if (top + tooltipRect.height > viewportHeight - 16) {
      top = rect.top - tooltipRect.height - 16;
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.style.display = 'block';

    // Update message content
    const stepNumber = this.state.currentIndex + 1;
    const totalSteps = this.state.steps.length;

    const messageEl = (tooltip.querySelector('.tour-message') as HTMLElement) || document.createElement('div');
    messageEl.className = 'tour-message';
    messageEl.style.marginBottom = '8px';
    const counter = document.createElement('div');
    counter.style.cssText = 'font-size: 12px; color: #3B7BDF; font-weight: 600; margin-bottom: 4px;';
    counter.textContent = `Step ${stepNumber} of ${totalSteps}`;
    const body = document.createElement('div');
    body.textContent = message;
    messageEl.replaceChildren(counter, body);

    // Insert message before controls
    const controls = tooltip.querySelector('#ghost-tour-controls');
    if (controls && !tooltip.contains(messageEl)) {
      tooltip.insertBefore(messageEl, controls);
    }
  }

  private updateControls(index: number): void {
    if (!this.state.shadowRoot) return;

    const prevBtn = this.state.shadowRoot.getElementById('ghost-tour-prev') as HTMLButtonElement;
    const nextBtn = this.state.shadowRoot.getElementById('ghost-tour-next') as HTMLButtonElement;

    if (prevBtn) {
      prevBtn.disabled = index === 0;
      prevBtn.style.opacity = index === 0 ? '0.5' : '1';
      prevBtn.style.cursor = index === 0 ? 'not-allowed' : 'pointer';
    }

    if (nextBtn) {
      const isLast = index === this.state.steps.length - 1;
      nextBtn.textContent = isLast ? 'Finish' : 'Next';
      if (isLast) {
        nextBtn.style.background = '#22C55E';
      } else {
        nextBtn.style.background = '#3B7BDF';
      }
    }
  }

  /**
   * Go to next step
   */
  async nextStep(): Promise<void> {
    if (this.state.currentIndex < this.state.steps.length - 1) {
      this.state.currentIndex++;
      await this.showStep(this.state.currentIndex);
    } else {
      await this.complete();
    }
  }

  /**
   * Go to previous step
   */
  async previousStep(): Promise<void> {
    if (this.state.currentIndex > 0) {
      this.state.currentIndex--;
      await this.showStep(this.state.currentIndex);
    }
  }

  /**
   * Skip the tour
   */
  async skipTour(): Promise<void> {
    await this.stop();
    this.options.onSkip();
  }

  /**
   * Complete the tour
   */
  async complete(): Promise<void> {
    await this.stop();
    this.options.onComplete();
  }

  /**
   * Stop the tour and cleanup
   */
  async stop(): Promise<void> {
    if (!this.state.isActive) return;

    this.state.isActive = false;

    // Remove event listeners
    document.removeEventListener('keydown', this.onKeydown);

    // Remove shadow DOM
    if (this.state.shadowRoot) {
      this.state.shadowRoot.host.remove();
    }

    // Reset state
    this.state = {
      steps: [],
      currentIndex: 0,
      isActive: false,
      overlayElement: null,
      spotlightElement: null,
      tooltipElement: null,
      shadowRoot: null,
    };
  }

  /**
   * Get current step index
   */
  getCurrentStep(): number {
    return this.state.currentIndex;
  }

  /**
   * Get total steps
   */
  getTotalSteps(): number {
    return this.state.steps.length;
  }

  /**
   * Check if tour is active
   */
  isRunning(): boolean {
    return this.state.isActive;
  }
}