#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');

const root = process.cwd();
const benchmarkArgs = ['evaluation/benchmark_api_perf.py', ...process.argv.slice(2)];
const dockerInstallAndRun = [
  'pip install --no-cache-dir -r api/requirements-dev.txt >/tmp/pip-install.log',
  'python evaluation/benchmark_api_perf.py "$@"',
].join(' && ');

function runCommand(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    stdio: 'inherit',
    ...options,
  });
}

function runCapture(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  });
}

function getPythonCandidates() {
  return [
    path.join(root, '.venv', 'bin', 'python'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    path.join(root, 'api', '.venv', 'bin', 'python'),
    path.join(root, 'api', '.venv', 'Scripts', 'python.exe'),
    'python',
    'python3',
  ];
}

function isUsablePython(command) {
  if (command.includes(path.sep) && !existsSync(command)) {
    return false;
  }
  const version = runCapture(
    command,
    ['-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],
    { timeout: 5000 }
  );
  if (version.error || version.status !== 0) {
    return false;
  }
  const output = String(version.stdout || '').trim();
  if (!output) {
    return false;
  }
  const [major, minor] = output.split('.').map((value) => Number.parseInt(value, 10));
  if (major !== 3 || minor >= 14) {
    return false;
  }
  const imports = runCapture(
    command,
    ['-c', 'import aiosqlite, fastapi, yaml'],
    { timeout: 5000 }
  );
  return !imports.error && imports.status === 0;
}

function runDockerFallback() {
  const availability = runCapture('docker', ['images', '--format', '{{.Repository}}:{{.Tag}}'], { timeout: 10000 });
  if (availability.error || availability.status !== 0) {
    return null;
  }
  return runCommand('docker', [
    'run', '--rm',
    '-v', `${root}:/work`,
    '-w', '/work',
    'python:3.11-slim',
    'sh', '-lc',
    dockerInstallAndRun,
    'sh',
    ...process.argv.slice(2),
  ], { timeout: 900000 });
}

for (const candidate of getPythonCandidates()) {
  if (!isUsablePython(candidate)) {
    continue;
  }
  const result = runCommand(candidate, benchmarkArgs, { timeout: 900000 });
  if (result.error && (result.error.code === 'ENOENT' || result.error.code === 'ETIMEDOUT')) {
    continue;
  }
  process.exit(result.status ?? 1);
}

const dockerResult = runDockerFallback();
if (dockerResult) {
  process.exit(dockerResult.status ?? 1);
}

console.error('No usable Python environment or Docker runtime found for API benchmarks.');
process.exit(1);
