export function setupEnvironment() {
  const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined';
  return {
    isBrowser,
    isNode: typeof process !== 'undefined' && process.versions != null && process.versions.node != null,
  };
}
