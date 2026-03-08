#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const DEFAULT_BUDGETS_MB = {
  total: 8,
  largest: 2.5,
  javascript: 2.5,
  css: 0.8,
};

const toBytes = (megabytes) => Math.round(megabytes * 1024 * 1024);
const formatMb = (bytes) => `${(bytes / (1024 * 1024)).toFixed(2)} MB`;

const parseBudgetMb = (envName, fallbackMb) => {
  const raw = process.env[envName];
  if (!raw) {
    return fallbackMb;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackMb;
};

const budgetsMb = {
  total: parseBudgetMb('MERLIN_FRONTEND_BUNDLE_MAX_TOTAL_MB', DEFAULT_BUDGETS_MB.total),
  largest: parseBudgetMb('MERLIN_FRONTEND_BUNDLE_MAX_FILE_MB', DEFAULT_BUDGETS_MB.largest),
  javascript: parseBudgetMb('MERLIN_FRONTEND_BUNDLE_MAX_JS_MB', DEFAULT_BUDGETS_MB.javascript),
  css: parseBudgetMb('MERLIN_FRONTEND_BUNDLE_MAX_CSS_MB', DEFAULT_BUDGETS_MB.css),
};

const budgetsBytes = {
  total: toBytes(budgetsMb.total),
  largest: toBytes(budgetsMb.largest),
  javascript: toBytes(budgetsMb.javascript),
  css: toBytes(budgetsMb.css),
};

const reportPath =
  process.env.MERLIN_FRONTEND_DIST_SIZE_REPORT ||
  path.resolve(process.cwd(), '../artifacts/frontend/frontend-dist-size-report.json');
const distDir = path.resolve(process.cwd(), 'dist');

const walk = (dir, results = []) => {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, results);
      continue;
    }
    if (entry.isFile()) {
      const stats = fs.statSync(fullPath);
      results.push({ path: fullPath, size: stats.size });
    }
  }
  return results;
};

const writeReport = (report) => {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
};

if (!fs.existsSync(distDir)) {
  const report = {
    status: 'error',
    reason: `dist directory not found at ${distDir}`,
  };
  writeReport(report);
  console.error(report.reason);
  process.exit(1);
}

const files = walk(distDir);
if (files.length === 0) {
  const report = {
    status: 'error',
    reason: `dist directory is empty at ${distDir}`,
  };
  writeReport(report);
  console.error(report.reason);
  process.exit(1);
}

let totalBytes = 0;
let jsBytes = 0;
let cssBytes = 0;
let largest = files[0];

for (const file of files) {
  totalBytes += file.size;
  if (file.size > largest.size) {
    largest = file;
  }

  if (file.path.endsWith('.js')) {
    jsBytes += file.size;
  } else if (file.path.endsWith('.css')) {
    cssBytes += file.size;
  }
}

const violations = [];
if (totalBytes > budgetsBytes.total) {
  violations.push(`Total bundle size ${formatMb(totalBytes)} exceeds ${budgetsMb.total} MB`);
}
if (largest.size > budgetsBytes.largest) {
  violations.push(
    `Largest asset ${path.relative(distDir, largest.path)} (${formatMb(largest.size)}) exceeds ${budgetsMb.largest} MB`
  );
}
if (jsBytes > budgetsBytes.javascript) {
  violations.push(`JavaScript assets total ${formatMb(jsBytes)} exceeds ${budgetsMb.javascript} MB`);
}
if (cssBytes > budgetsBytes.css) {
  violations.push(`CSS assets total ${formatMb(cssBytes)} exceeds ${budgetsMb.css} MB`);
}

const report = {
  schema_name: 'AAS.FrontendBundleBudgetReport',
  schema_version: '1.0.0',
  generated_at: new Date().toISOString(),
  dist_dir: distDir,
  budgets_mb: budgetsMb,
  metrics: {
    file_count: files.length,
    total_mb: Number((totalBytes / (1024 * 1024)).toFixed(3)),
    javascript_mb: Number((jsBytes / (1024 * 1024)).toFixed(3)),
    css_mb: Number((cssBytes / (1024 * 1024)).toFixed(3)),
    largest_asset: {
      relative_path: path.relative(distDir, largest.path),
      size_mb: Number((largest.size / (1024 * 1024)).toFixed(3)),
    },
  },
  violations,
  status: violations.length > 0 ? 'failed' : 'passed',
};

writeReport(report);

console.log(`dist total: ${formatMb(totalBytes)} (budget ${budgetsMb.total} MB)`);
console.log(
  `largest file: ${path.relative(distDir, largest.path)} (${formatMb(largest.size)}) (budget ${budgetsMb.largest} MB)`
);
console.log(`javascript total: ${formatMb(jsBytes)} (budget ${budgetsMb.javascript} MB)`);
console.log(`css total: ${formatMb(cssBytes)} (budget ${budgetsMb.css} MB)`);
console.log(`bundle budget report: ${reportPath}`);

if (violations.length > 0) {
  for (const violation of violations) {
    console.error(violation);
  }
  process.exit(1);
}
