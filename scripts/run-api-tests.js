#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');

const root = process.cwd();
const apiDevRequirements = 'api/requirements-dev.txt';
const testArgs = ['-m', 'pytest', '-q', 'api/tests'];

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
  if (major !== 3 || minor < 11 || minor >= 15) {
    return false;
  }
  const imports = runCapture(
    command,
    ['-c', 'import aiosqlite, fastapi, pytest, yaml'],
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
    `pip install --no-cache-dir -r ${apiDevRequirements} >/tmp/pip-install.log && python -m pytest -q api/tests`,
  ]);
}

for (const candidate of getPythonCandidates()) {
  if (!isUsablePython(candidate)) {
    continue;
  }
  const result = runCommand(candidate, testArgs, { timeout: 120000 });
  if (result.error && (result.error.code === 'ENOENT' || result.error.code === 'ETIMEDOUT')) {
    continue;
  }
  process.exit(result.status ?? 1);
}

const dockerResult = runDockerFallback();
if (dockerResult) {
  process.exit(dockerResult.status ?? 1);
}

console.error(
  `No usable Python environment or Docker runtime found for API tests.\n` +
  `Install ${apiDevRequirements} into a local Python 3.11-3.14 environment, or enable Docker fallback.`
);
process.exit(1);
