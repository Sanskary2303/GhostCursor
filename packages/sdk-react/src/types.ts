import type { Target } from '@ghost-cursor/sdk';

export interface GhostCursorProps {
  apiEndpoint?: string;
  theme?: Partial<Theme>;
  requireApprovalForActions?: boolean;
  allowSemanticLookup?: boolean;
  targets?: Record<string, Target>;
  onMessage?: (event: MessageEvent) => void;
  onActionsRequested?: (actions: any) => void;
  context?: {
    page?: string | (() => string);
    values?: Record<string, string | number | boolean>;
    availableTargets?: string[];
    [key: string]: any;
  };
  headers?: () => Record<string, string> | Promise<Record<string, string>>;
  selectors?: {
    exclude?: string[];
    include?: string[];
  };
  mount?: HTMLElement;
  streaming?: boolean;
  xray?: boolean;
  allowXrayParam?: boolean;
}

export interface Theme {
  primaryColor?: string;
  cursorColor?: string;
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
  mode?: 'midnight' | 'daylight' | 'auto';
  [key: string]: any;
}

