export interface GhostCursorProps {
  apiEndpoint?: string;
  theme?: Partial<Theme>;
  requireApprovalForActions?: boolean;
  onMessage?: (event: MessageEvent) => void;
  onActionsRequested?: (actions: any) => void;
  context?: {
    page?: string;
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
}

export interface Theme {
  primaryColor?: string;
  cursorColor?: string;
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
  [key: string]: any;
}