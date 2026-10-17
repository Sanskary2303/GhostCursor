import { Component, createRef } from 'preact';
import { createCursorSvg } from '../cursor/assets';

interface BrandCursorProps {
  width?: number;
  accent?: string;
  className?: string;
}

/** The brand cursor as an inline SVG (built with createElementNS, never innerHTML). */
export class BrandCursor extends Component<BrandCursorProps> {
  private hostRef = createRef<HTMLSpanElement>();
  private svg: SVGSVGElement | null = null;

  componentDidMount() {
    this.mountSvg();
  }

  componentDidUpdate(prev: BrandCursorProps) {
    if (prev.width !== this.props.width || prev.accent !== this.props.accent) this.mountSvg();
  }

  componentWillUnmount() {
    this.unmountSvg();
  }

  private mountSvg() {
    this.unmountSvg();
    const host = this.hostRef.current;
    if (!host) return;
    this.svg = createCursorSvg(document, { width: this.props.width ?? 22, accent: this.props.accent });
    host.appendChild(this.svg);
  }

  private unmountSvg() {
    const svg = this.svg;
    this.svg = null;
    if (svg && svg.parentNode) svg.parentNode.removeChild(svg);
  }

  render() {
    return <span ref={this.hostRef} className={this.props.className ?? 'gc-brand-cursor'} aria-hidden="true" />;
  }
}

