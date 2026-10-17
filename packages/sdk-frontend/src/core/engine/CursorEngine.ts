/**
 * Cursor Engine - Animated ghost cursor for visual feedback
 * Operates on the Host DOM (not in Shadow DOM) to animate across the full viewport
 */

export interface CursorOptions {
  color?: string;
  size?: number;
  animationDuration?: number;
  easing?: string;
  zIndex?: number;
}

const DEFAULT_OPTIONS: Required<CursorOptions> = {
  color: '#FF4D4D',
  size: 24,
  animationDuration: 500,
  easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
  zIndex: 99999,
};

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** @deprecated Replaced by CursorController (core/cursor). The SDK no longer uses it; it will be removed in the next minor release. */
export class CursorEngine {
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private options: Required<CursorOptions>;
  private currentPosition: { x: number; y: number } = { x: 0, y: 0 };
  private targetPosition: { x: number; y: number } | null = null;
  private animationFrame: number | null = null;
  private isAnimating = false;
  private trail: Array<{ x: number; y: number; alpha: number }> = [];

  constructor(options: CursorOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.initCanvas();
  }

  private initCanvas(): void {
    // Create canvas overlay that covers the entire viewport
    this.canvas = document.createElement('canvas');
    this.canvas.id = 'ghost-cursor-canvas';
    this.canvas.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      pointer-events: none;
      z-index: ${this.options.zIndex};
      touch-action: none;
    `;

    // Set canvas size to match device pixel ratio
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = window.innerWidth * dpr;
    this.canvas.height = window.innerHeight * dpr;
    this.canvas.style.width = '100vw';
    this.canvas.style.height = '100vh';

    this.ctx = this.canvas.getContext('2d')!;
    this.ctx.scale(dpr, dpr);

    document.body.appendChild(this.canvas);

    // Handle resize
    window.addEventListener('resize', this.handleResize.bind(this));
  }

  private handleResize(): void {
    if (!this.canvas || !this.ctx) return;

    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = window.innerWidth * dpr;
    this.canvas.height = window.innerHeight * dpr;
    this.ctx.scale(dpr, dpr);
  }

  /**
   * Move cursor to target element with smooth animation
   */
  async moveTo(element: HTMLElement): Promise<void> {
    const rect = element.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top + rect.height / 2;

    if (prefersReducedMotion() || this.options.animationDuration === 0) {
      this.currentPosition = { x: targetX, y: targetY };
      this.targetPosition = null;
      this.trail = [];
      if (this.ctx) {
        this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
        this.drawCursor(this.currentPosition.x, this.currentPosition.y);
      }
      return;
    }

    this.targetPosition = { x: targetX, y: targetY };
    this.isAnimating = true;

    return new Promise(resolve => {
      const animate = () => {
        if (!this.targetPosition || !this.ctx) {
          this.isAnimating = false;
          resolve();
          return;
        }

        // Clear canvas
        this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

        // Update trail
        this.trail.push({ x: this.currentPosition.x, y: this.currentPosition.y, alpha: 1 });
        if (this.trail.length > 10) this.trail.shift();

        // Calculate interpolation
        const dx = this.targetPosition.x - this.currentPosition.x;
        const dy = this.targetPosition.y - this.currentPosition.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < 2) {
          // Arrived
          this.currentPosition = { ...this.targetPosition };
          this.targetPosition = null;
        } else {
          // Eased movement
          const progress = Math.min(1, 0.15 * (this.options.animationDuration / 16));
          this.currentPosition.x += dx * progress;
          this.currentPosition.y += dy * progress;
        }

        // Draw trail
        this.trail.forEach((point, index) => {
          const alpha = (index / this.trail.length) * 0.5;
          this.drawCursorPoint(point.x, point.y, alpha * 0.3);
        });

        // Draw main cursor
        this.drawCursor(this.currentPosition.x, this.currentPosition.y);

        // Continue animation
        if (this.targetPosition) {
          this.animationFrame = requestAnimationFrame(animate);
        } else {
          // Final frame
          this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
          this.drawCursor(this.currentPosition.x, this.currentPosition.y);
          this.isAnimating = false;
          resolve();
        }
      };

      this.animationFrame = requestAnimationFrame(animate);
    });
  }

  /**
   * Draw the ghost cursor at a position
   */
  private drawCursor(x: number, y: number, alpha = 1): void {
    if (!this.ctx) return;

    const { size, color } = this.options;
    const radius = size / 2;

    this.ctx.save();
    this.ctx.globalAlpha = alpha;
    this.ctx.translate(x, y);

    // Draw cursor body (ghost shape)
    this.ctx.beginPath();
    // Head
    this.ctx.arc(0, -radius * 0.3, radius * 0.7, 0, Math.PI * 2);
    // Body
    this.ctx.moveTo(-radius * 0.7, -radius * 0.3);
    this.ctx.quadraticCurveTo(-radius, radius * 0.5, -radius * 0.3, radius);
    this.ctx.quadraticCurveTo(0, radius * 1.5, radius * 0.3, radius);
    this.ctx.quadraticCurveTo(radius, radius * 0.5, radius * 0.7, -radius * 0.3);
    this.ctx.closePath();

    // Fill
    this.ctx.fillStyle = color;
    this.ctx.fill();

    // Glow effect
    this.ctx.shadowColor = color;
    this.ctx.shadowBlur = 15;
    this.ctx.fill();

    // Eyes
    this.ctx.fillStyle = 'white';
    this.ctx.beginPath();
    this.ctx.arc(-radius * 0.25, -radius * 0.4, radius * 0.15, 0, Math.PI * 2);
    this.ctx.arc(radius * 0.25, -radius * 0.4, radius * 0.15, 0, Math.PI * 2);
    this.ctx.fill();

    // Pupils
    this.ctx.fillStyle = '#333';
    this.ctx.beginPath();
    this.ctx.arc(-radius * 0.25, -radius * 0.4, radius * 0.07, 0, Math.PI * 2);
    this.ctx.arc(radius * 0.25, -radius * 0.4, radius * 0.07, 0, Math.PI * 2);
    this.ctx.fill();

    this.ctx.restore();
  }

  private drawCursorPoint(x: number, y: number, alpha: number): void {
    if (!this.ctx) return;

    const { size, color } = this.options;
    const radius = size / 2;

    this.ctx.save();
    this.ctx.globalAlpha = alpha;
    this.ctx.translate(x, y);

    this.ctx.beginPath();
    this.ctx.arc(0, 0, radius * 0.5, 0, Math.PI * 2);
    this.ctx.fillStyle = color;
    this.ctx.fill();

    this.ctx.restore();
  }

  /**
   * Show click animation at current position
   */
  async click(): Promise<void> {
    if (!this.ctx) return;

    if (prefersReducedMotion()) {
      this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      this.drawCursor(this.currentPosition.x, this.currentPosition.y);
      return;
    }

    const { size, color } = this.options;
    const radius = size / 2;

    // Ripple animation
    for (let i = 0; i < 15; i++) {
      this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      this.drawCursor(this.currentPosition.x, this.currentPosition.y);

      const rippleRadius = radius + (i * radius * 0.5);
      const alpha = 1 - i / 15;

      this.ctx.save();
      this.ctx.globalAlpha = alpha;
      this.ctx.strokeStyle = color;
      this.ctx.lineWidth = 3;
      this.ctx.beginPath();
      this.ctx.arc(this.currentPosition.x, this.currentPosition.y, rippleRadius, 0, Math.PI * 2);
      this.ctx.stroke();
      this.ctx.restore();

      await new Promise(resolve => setTimeout(resolve, 30));
    }

    // Redraw cursor
    this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    this.drawCursor(this.currentPosition.x, this.currentPosition.y);
  }

  /**
   * Hide the cursor
   */
  hide(): void {
    if (this.ctx) {
      this.ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
    this.targetPosition = null;
    this.isAnimating = false;
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
  }

  /**
   * Show the cursor at current position
   */
  show(): void {
    if (this.ctx) {
      this.drawCursor(this.currentPosition.x, this.currentPosition.y);
    }
  }

  /**
   * Set cursor color
   */
  setColor(color: string): void {
    this.options.color = color;
  }

  /**
   * Dispose and cleanup
   */
  dispose(): void {
    this.hide();
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
    this.canvas = null;
    this.ctx = null;
    window.removeEventListener('resize', this.handleResize.bind(this));
  }
}

// Singleton instance for easy access
let cursorInstance: CursorEngine | null = null;

export function getCursorEngine(options?: CursorOptions): CursorEngine {
  if (!cursorInstance) {
    cursorInstance = new CursorEngine(options);
  }
  return cursorInstance;
}

export function disposeCursorEngine(): void {
  if (cursorInstance) {
    cursorInstance.dispose();
    cursorInstance = null;
  }
}