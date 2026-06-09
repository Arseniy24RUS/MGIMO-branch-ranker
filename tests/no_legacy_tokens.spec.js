const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SUFFIXES = new Set(['.html', '.js', '.cjs', '.css', '.json', '.csv', '.md', '.py', '.yaml', '.yml']);
const SKIP_DIRS = new Set(['.git', '.playwright-mcp', '.pytest_cache', 'artifacts', 'internal_archive', 'node_modules', 'playwright-report', 'reports', 'test-results', 'vendor', 'v2.0 legacy']);
const SKIP_FILES = new Set(['package-lock.json']);
const SKIP_PREFIXES = [
  ['data', 'raw'],
  ['docs', 'assets', 'vendor']
];

function term(...parts) {
  return parts.join('');
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const disallowedTerms = [
  term('place', 'holder'),
  term('pro', 'xy'),
  term('fall', 'back'),
  term('mo', 'ck'),
  term('st', 'ub'),
  term('fa', 'ke'),
  term('temp', 'orary'),
  term('sub', 'stitute'),
  term('extra', 'polated'),
  term('заг', 'луш'),
  term('прок', 'си'),
  term('врем', 'енн'),
  term('фол', 'лбек'),
  term('под', 'став')
];

const PATTERNS = [
  ['old decision modes', new RegExp([
    term('scenario', 'Weights'),
    term('snapshot', 'Countries'),
    term('base', 'line'),
    term('soft', '_power'),
    term('comm', 'ercial'),
    term('risk', '_averse')
  ].map(escapeRegExp).join('|'), 'i')],
  ['old youth cohort', new RegExp(`${escapeRegExp(term('youth', '17_24'))}|${escapeRegExp(term('17', '-24'))}`, 'i')],
  ['old demography chart', new RegExp(`${escapeRegExp(term('demography', 'TrendChart'))}|${escapeRegExp(term('render', 'DemographyTrendChart'))}`)],
  ['old output names', new RegExp(`${escapeRegExp(term('live', '_final'))}|${escapeRegExp(term('final', '_snapshot'))}`, 'i')],
  ['old SAI mobility key', new RegExp(escapeRegExp(term('A_MOBILITY', '_READINESS')))],
  ['old demographic provenance', new RegExp([
    term('world', '_bank_wpp_linked'),
    term('model', '_forecast'),
    `${term('temp', 'orary')} ${term('sub', 'stitute')}`,
    `${term('fall', 'back')} dashboard demography`
  ].map(escapeRegExp).join('|'), 'i')],
  ['disallowed wording', new RegExp(disallowedTerms.map(escapeRegExp).join('|'), 'i')]
];

function shouldSkip(file) {
  const rel = path.relative(ROOT, file).split(path.sep);
  if (SKIP_FILES.has(path.basename(file))) return true;
  if (rel.some((part) => SKIP_DIRS.has(part))) return true;
  return SKIP_PREFIXES.some((prefix) => prefix.every((part, index) => rel[index] === part));
}

function files(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (shouldSkip(full)) continue;
    if (entry.isDirectory()) files(full, out);
    else if (SUFFIXES.has(path.extname(entry.name).toLowerCase())) out.push(full);
  }
  return out;
}

test('project-owned files have no disallowed data-substitution wording', async () => {
  const failures = [];
  for (const file of files(ROOT)) {
    const text = fs.readFileSync(file, 'utf8');
    for (const [label, re] of PATTERNS) {
      const match = text.match(re);
      if (match) failures.push(`${label}: ${path.relative(ROOT, file)} near ${match[0]}`);
    }
  }
  expect(failures).toEqual([]);
});
