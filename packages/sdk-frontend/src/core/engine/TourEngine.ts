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
}

const DEFAULT_OPTIONS: Required<TourOptions> = {
  onStepChange: () => {},
  onComplete: () => {},
  onSkip: () => {},
  spotlightColor: '#0052FF',
  spotlightOpacity: 0.85,
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
      background: rgba(0, 0, 0, ${this.options.spotlightOpacity});
      pointer-events: none;
      z-index: 2147483350;
      display: none;
    `;
    this.state.shadowRoot.appendChild(this.state.overlayElement);

    // Create spotlight (the hole in the overlay)
    this.state.spotlightElement = document.createElement('div');
    this.state.spotlightElement.id = 'ghost-tour-spotlight';
    this.state.spotlightElement.style.cssText = `
      position: fixed;
      border-radius: 8px;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, ${this.options.spotlightOpacity});
      pointer-events: none;
      z-index: 2147483360;
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
      background: white;
      border-radius: 12px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
      z-index: 2147483370;
      display: none;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #1a1a2e;
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
      border-top: 1px solid #e5e7eb;
    `;
    controls.innerHTML = `
      <button id="ghost-tour-prev" style="
        padding: 8px 16px;
        background: #f3f4f6;
        color: #374151;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
      ">Previous</button>
      <button id="ghost-tour-next" style="
        padding: 8px 16px;
        background: #0052FF;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
      ">Next</button>
      <button id="ghost-tour-skip" style="
        padding: 8px 16px;
        background: transparent;
        color: #6b7280;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        margin-left: auto;
      ">Skip Tour</button>
    `;
    this.state.tooltipElement.appendChild(controls);

    // Attach event listeners
    this.state.shadowRoot.getElementById('ghost-tour-prev')!.addEventListener('click', () => this.previousStep());
    this.state.shadowRoot.getElementById('ghost-tour-next')!.addEventListener('click', () => this.nextStep());
    this.state.shadowRoot.getElementById('ghost-tour-skip')!.addEventListener('click', () => this.skipTour());

    // Keyboard navigation
    document.addEventListener('keydown', this.handleKeydown.bind(this));
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
        0%, 100% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.85), 0 0 20px rgba(0, 82, 255, 0.5); }
        50% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.85), 0 0 30px rgba(0, 82, 255, 0.8); }
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
    // Try data-ghost-id first
    let element = document.querySelector<HTMLElement>(`[data-ghost-id="${CSS.escape(targetId)}"]`);
    if (element) return element;

    // Try data-testid
    element = document.querySelector<HTMLElement>(`[data-testid="${CSS.escape(targetId)}"]`);
    if (element) return element;

    // Try id
    element = document.getElementById(targetId);
    if (element) return element;

    // Try aria-label
    element = document.querySelector<HTMLElement>(`[aria-label="${CSS.escape(targetId)}"]`);
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
    counter.style.cssText = 'font-size: 12px; color: #0052FF; font-weight: 600; margin-bottom: 4px;';
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
        nextBtn.style.background = '#10b981';
      } else {
        nextBtn.style.background = '#0052FF';
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
    document.removeEventListener('keydown', this.handleKeydown.bind(this));

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