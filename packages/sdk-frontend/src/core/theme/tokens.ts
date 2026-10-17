import { BRAND } from '../cursor/assets';

export type ThemeMode = 'midnight' | 'daylight' | 'auto';

export interface ThemeTokens {
  bg: string;
  bgSolid: string;
  surface: string;
  surface2: string;
  text: string;
  muted: string;
  border: string;
  accent: string;
  accentSoft: string;
  accentLine: string;
  success: string;
  danger: string;
  dockBg: string;
  launcherBg: string;
  shadow: string;
}

export const MIDNIGHT: ThemeTokens = {
  bg: 'rgba(17, 24, 40, 0.96)',
  bgSolid: BRAND.navy,
  surface: BRAND.ink,
  surface2: '#1A2336',
  text: '#F8FAFC',
  muted: BRAND.muted,
  border: 'rgba(255, 255, 255, 0.08)',
  accent: BRAND.blue,
  accentSoft: 'rgba(59, 123, 223, 0.18)',
  accentLine: 'rgba(59, 123, 223, 0.45)',
  success: BRAND.success,
  danger: BRAND.danger,
  dockBg: BRAND.ink,
  launcherBg: BRAND.navy,
  shadow: '0 24px 64px rgba(2, 6, 23, 0.55)',
};

export const DAYLIGHT: ThemeTokens = {
  bg: 'rgba(255, 255, 255, 0.98)',
  bgSolid: BRAND.white,
  surface: '#F8FAFC',
  surface2: '#EEF2F7',
  text: BRAND.navy,
  muted: '#64748B',
  border: '#E2E8F0',
  accent: BRAND.blue,
  accentSoft: 'rgba(59, 123, 223, 0.12)',
  accentLine: 'rgba(59, 123, 223, 0.35)',
  success: '#16A34A',
  danger: '#DC2626',
  // The dock and launcher stay navy so the white cursor is always visible.
  dockBg: BRAND.navy,
  launcherBg: BRAND.navy,
  shadow: '0 20px 50px rgba(15, 23, 42, 0.18)',
};

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

export function resolveMode(mode: ThemeMode | undefined, prefersDark: boolean): 'midnight' | 'daylight' {
  if (mode === 'midnight' || mode === 'daylight') return mode;
  if (mode === 'auto') return prefersDark ? 'midnight' : 'daylight';
  return 'midnight';
}

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Tokens for a mode. `accent` must be a #RRGGBB colour; anything else is ignored (no CSS injection). */
export function tokensFor(mode: 'midnight' | 'daylight', accent?: string): ThemeTokens {
  const base = mode === 'daylight' ? DAYLIGHT : MIDNIGHT;
  if (!accent || !HEX_COLOR.test(accent)) return base;
  return {
    ...base,
    accent,
    accentSoft: hexToRgba(accent, mode === 'daylight' ? 0.12 : 0.18),
    accentLine: hexToRgba(accent, mode === 'daylight' ? 0.35 : 0.45),
  };
}

/** `:host{--gc-bg:...;--gc-accent-soft:...}` for the widget's shadow root. */
export function tokensToCss(tokens: ThemeTokens): string {
  const vars = Object.entries(tokens)
    .map(([key, value]) => `--gc-${key.replace(/[A-Z0-9]/g, (c) => `-${c.toLowerCase()}`)}:${value};`)
    .join('');
  return `:host{${vars}}`;
}

export function prefersDarkScheme(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

