const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  buildDockerPythonRunArgs,
  classifyDockerProbeResult,
  formatEnvironmentDiagnostics,
  probeDocker,
} = require("../scripts/lib/python-runner");

function withFakePath(binDir, callback) {
  const originalPath = process.env.PATH || "";
  process.env.PATH = `${binDir}${path.delimiter}${originalPath}`;
  try {
    return callback();
  } finally {
    process.env.PATH = originalPath;
  }
}

function writeExecutable(filePath, content) {
  fs.writeFileSync(filePath, content, { encoding: "utf8", mode: 0o755 });
}

test("classifyDockerProbeResult distinguishes permission denied failures", () => {
  const report = classifyDockerProbeResult({
    status: 1,
    stdout: "",
    stderr: "permission denied while trying to connect to the docker API",
    error: null,
  });

  assert.deepEqual(report, {
    available: false,
    reason: "permission_denied",
    detail: "permission denied while trying to connect to the docker API",
  });
});

test("probeDocker falls back to sg docker when direct daemon access is denied", () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-docker-probe-"));
  const binDir = path.join(tempDir, "bin");
  fs.mkdirSync(binDir, { recursive: true });

  writeExecutable(
    path.join(binDir, "docker"),
    [
      "#!/usr/bin/env bash",
      "echo 'permission denied while trying to connect to the docker API at unix:///var/run/docker.sock' >&2",
      "exit 1",
      "",
    ].join("\n")
  );
  writeExecutable(
    path.join(binDir, "sg"),
    [
      "#!/usr/bin/env bash",
      "exit 0",
      "",
    ].join("\n")
  );

  const report = withFakePath(binDir, () => probeDocker(tempDir));

  assert.equal(report.available, true);
  assert.equal(report.reason, "available");
  assert.equal(report.accessMode, "sg");
});

test("buildDockerPythonRunArgs uses a stable named volume and preserves extra args", () => {
  const args = buildDockerPythonRunArgs("/tmp/Star Sorty!", {
    requirementsPath: "api/requirements dev.txt",
    shellCommand: 'python evaluation/benchmark_api_perf.py "$@"',
    extraArgs: ["sh", "--help"],
  });

  assert.deepEqual(args.slice(0, 8), [
    "run",
    "--rm",
    "-e",
    "PIP_DISABLE_PIP_VERSION_CHECK=1",
    "-e",
    "PIP_ROOT_USER_ACTION=ignore",
    "-v",
    "/tmp/Star Sorty!:/work",
  ]);
  assert.ok(
    args.includes("star-sorty-docker-pip-cache:/root/.cache/pip"),
    "expected named Docker volume cache mount"
  );
  assert.ok(
    args.includes("python:3.11-slim"),
    "expected Python 3.11 Docker fallback image"
  );
  const shellCommand = args[args.indexOf("-lc") + 1];
  assert.match(shellCommand, /python -m pip install --cache-dir '\/root\/\.cache\/pip'/);
  assert.match(shellCommand, /-r 'api\/requirements dev\.txt'/);
  assert.match(shellCommand, /python evaluation\/benchmark_api_perf\.py "\$@"/);
  assert.deepEqual(args.slice(-2), ["sh", "--help"]);
});

test("formatEnvironmentDiagnostics surfaces actionable docker permission guidance", () => {
  const output = formatEnvironmentDiagnostics({
    taskLabel: "API tests",
    requirementsPath: "api/requirements-dev.txt",
    pythonReports: [
      {
        command: "python3",
        usable: false,
        reason: "unsupported_async_sqlite_runtime",
        version: "3.14",
      },
    ],
    dockerReport: {
      available: false,
      reason: "permission_denied",
      detail: "permission denied while trying to connect to the docker API",
      accessMode: "direct",
    },
  });

  assert.match(
    output,
    /No usable Python environment found for API tests, and Docker is installed but this shell cannot access the Docker daemon\./
  );
  assert.match(output, /Install api\/requirements-dev\.txt into a local Python 3\.11-3\.13 environment/);
  assert.match(output, /log in again after adding your user to the `docker` group/);
  assert.match(output, /- python3: Python 3\.14 is unsupported for local async SQLite runtime/);
  assert.match(
    output,
    /- docker: installed, but the current shell cannot access the daemon \(permission denied while trying to connect to the docker API\)/
  );
});
