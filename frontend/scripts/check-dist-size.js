#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const MAX_TOTAL_MB = 100;
const MAX_FILE_MB = 100;
const MAX_TOTAL_BYTES = MAX_TOTAL_MB * 1024 * 1024;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const distDir = path.resolve(process.cwd(), 'dist');

const formatMb = (bytes) => `${(bytes / (1024 * 1024)).toFixed(2)} MB`;

const walk = (dir, results = []) => {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, results);
    } else if (entry.isFile()) {
      const stats = fs.statSync(fullPath);
      results.push({ path: fullPath, size: stats.size });
    }
  }
  return results;
};

if (!fs.existsSync(distDir)) {
  console.error(`dist directory not found at ${distDir}`);
  process.exit(1);
}

const files = walk(distDir);

if (files.length === 0) {
  console.error(`dist directory is empty at ${distDir}`);
  process.exit(1);
}

let totalBytes = 0;
let largest = files[0];

for (const file of files) {
  totalBytes += file.size;
  if (file.size > largest.size) {
    largest = file;
  }
}

console.log(`dist total: ${formatMb(totalBytes)}`);
console.log(`largest file: ${path.relative(distDir, largest.path)} (${formatMb(largest.size)})`);

if (totalBytes > MAX_TOTAL_BYTES) {
  console.error(`dist total exceeds ${MAX_TOTAL_MB} MB limit`);
  process.exit(1);
}

if (largest.size > MAX_FILE_BYTES) {
  console.error(`largest file exceeds ${MAX_FILE_MB} MB limit`);
  process.exit(1);
}
