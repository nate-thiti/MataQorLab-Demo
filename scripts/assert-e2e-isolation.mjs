import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const root = join(process.cwd(), '.next');
const allowedHosts = new Set(['example.supabase.co']);
const discovered = new Set();

async function visit(path) {
  for (const entry of await readdir(path, { withFileTypes: true })) {
    const target = join(path, entry.name);
    if (entry.isDirectory()) {
      await visit(target);
      continue;
    }
    if (!/\.(?:js|json|html|txt)$/.test(entry.name)) continue;
    const content = await readFile(target, 'utf8').catch(() => '');
    for (const match of content.matchAll(/https:\/\/([a-z0-9-]+\.supabase\.co)/gi)) {
      discovered.add(match[1].toLowerCase());
    }
  }
}

try {
  await visit(root);
} catch {
  throw new Error('Missing .next build. Run npm run build:e2e before Playwright.');
}

const unsafe = [...discovered].filter((host) => !allowedHosts.has(host));
if (unsafe.length) {
  throw new Error(
    `E2E build contains non-test Supabase hosts: ${unsafe.join(', ')}. `
    + 'Rebuild with npm run build:e2e; refusing to contact live projects.',
  );
}
