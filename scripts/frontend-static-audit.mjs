#!/usr/bin/env node

import { readdir, readFile } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const roots = ['h5-web/src', 'admin-web/src'];
const banned = [
  { pattern: /\/quiz\/0/g, reason: 'hard-coded invalid quiz route' },
  { pattern: /\/bank\/0/g, reason: 'hard-coded invalid bank route' },
  { pattern: /\bdebugger\b/g, reason: 'debugger statement' },
  { pattern: /\bconsole\.log\b/g, reason: 'console.log left in frontend source' },
  { pattern: /\bTODO\b|\bFIXME\b/g, reason: 'unfinished frontend marker' },
];

async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const result = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      result.push(...await files(path));
    } else if (/\.(vue|ts|tsx|js|jsx)$/.test(entry.name)) {
      result.push(path);
    }
  }
  return result;
}

async function main() {
  const findings = [];
  for (const scope of roots) {
    for (const file of await files(join(root, scope))) {
      const text = await readFile(file, 'utf8');
      const lines = text.split(/\r?\n/);
      for (const rule of banned) {
        rule.pattern.lastIndex = 0;
        let match;
        while ((match = rule.pattern.exec(text))) {
          const line = text.slice(0, match.index).split(/\r?\n/).length;
          findings.push({
            file: relative(root, file),
            line,
            value: lines[line - 1].trim(),
            reason: rule.reason,
          });
        }
      }
    }
  }

  if (findings.length) {
    console.error('Frontend static audit failed');
    for (const item of findings) {
      console.error(`${item.file}:${item.line} ${item.reason}: ${item.value}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log('Frontend static audit passed');
}

main().catch((error) => {
  console.error(`Frontend static audit failed: ${error.message}`);
  process.exitCode = 1;
});
