import { createRequire } from 'node:module';
import fs from 'node:fs';

const require = createRequire(import.meta.url);
const resolved = require.resolve('@ghost-cursor/sdk-react/dist/index.css');

if (!resolved || !fs.existsSync(resolved)) {
  console.error(`Failed to resolve @ghost-cursor/sdk-react/dist/index.css: resolved to ${resolved}`);
  process.exit(1);
}

console.log('Successfully resolved @ghost-cursor/sdk-react/dist/index.css:', resolved);

