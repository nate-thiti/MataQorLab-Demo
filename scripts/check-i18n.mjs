import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const projectRoot = process.cwd();
const localeDir = path.join(projectRoot, 'src', 'locales');
const sourceRoots = ['app', 'src'].map((directory) => path.join(projectRoot, directory));
const sourcePattern = /\.(?:js|jsx|ts|tsx)$/;
const testFilePattern = /\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/;

const readJson = (filePath) => JSON.parse(fs.readFileSync(filePath, 'utf8'));

const flatten = (value, prefix = '', output = {}) => {
  Object.entries(value).forEach(([key, child]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      flatten(child, nextKey, output);
    } else {
      output[nextKey] = child;
    }
  });
  return output;
};

const placeholders = (value) => (
  [...String(value).matchAll(/\{([^}]+)\}/g)].map((match) => match[1]).sort()
);

const listSourceFiles = (directory) => fs.readdirSync(directory, { withFileTypes: true })
  .flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return listSourceFiles(fullPath);
    return sourcePattern.test(entry.name) && !testFilePattern.test(entry.name) ? [fullPath] : [];
  });

const en = flatten(readJson(path.join(localeDir, 'en.json')));
const th = flatten(readJson(path.join(localeDir, 'th.json')));
const errors = [];

for (const key of Object.keys(en)) {
  if (!(key in th)) errors.push(`Missing Thai key: ${key}`);
}
for (const key of Object.keys(th)) {
  if (!(key in en)) errors.push(`Missing English key: ${key}`);
}
for (const key of Object.keys(en)) {
  if (!(key in th)) continue;
  if (typeof en[key] !== 'string' || typeof th[key] !== 'string') {
    errors.push(`Translation leaf must be a string: ${key}`);
    continue;
  }
  const enPlaceholders = placeholders(en[key]);
  const thPlaceholders = placeholders(th[key]);
  if (enPlaceholders.join('|') !== thPlaceholders.join('|')) {
    errors.push(
      `Placeholder mismatch: ${key} (en: ${enPlaceholders.join(', ') || '-'}; th: ${thPlaceholders.join(', ') || '-'})`,
    );
  }
}

const literalKeyPatterns = [
  /\bt\(\s*[\w.]+\s*,\s*(['"])([^'"]+)\1/g,
  /\bt\(\s*(['"])([^'"]+)\1/g,
  /\btranslate\(\s*(['"])([^'"]+)\1/g,
  /\bmakeGenerateMetadata\(\s*(['"])([^'"]+)\1/g,
];

for (const filePath of sourceRoots.flatMap(listSourceFiles)) {
  const source = fs.readFileSync(filePath, 'utf8');
  for (const pattern of literalKeyPatterns) {
    pattern.lastIndex = 0;
    for (const match of source.matchAll(pattern)) {
      const key = match[2];
      if (key && !(key in en)) {
        errors.push(`${path.relative(projectRoot, filePath)} references missing key: ${key}`);
      }
    }
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`i18n audit passed: ${Object.keys(en).length} keys are aligned across en/th.`);
}
