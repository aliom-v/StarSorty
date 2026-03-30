const { spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

const MIN_PYTHON_MINOR = 11;
const MAX_PYTHON_MINOR_EXCLUSIVE = 14;
const PYTHON_PROBE_TIMEOUT_MS = 5000;
const DOCKER_PROBE_TIMEOUT_MS = 10000;
const DOCKER_FALLBACK_PYTHON = "3.11";
const DOCKER_FALLBACK_IMAGE = `python:${DOCKER_FALLBACK_PYTHON}-slim`;
const DOCKER_PIP_CACHE_MOUNT = "/root/.cache/pip";

function runCommand(root, command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    ...options,
  });
}

function runCapture(root, command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
}

function compactProbeDetail(text) {
  const normalized = String(text || "")
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join(" | ");

  return normalized ? normalized.slice(0, 240) : null;
}

function shellEscape(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function buildShellCommand(command, args) {
  return [command, ...args].map(shellEscape).join(" ");
}

function getDockerPipCacheVolumeName(root) {
  const basename = path.basename(root).toLowerCase();
  const normalized = basename.replace(/[^a-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "");
  const safeName =
    normalized && /^[a-z0-9]/.test(normalized) ? normalized : "project";
  return `${safeName}-docker-pip-cache`;
}

function getPythonCandidates(root) {
  return [
    path.join(root, ".venv", "bin", "python"),
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, "api", ".venv", "bin", "python"),
    path.join(root, "api", ".venv", "Scripts", "python.exe"),
    "python3.13",
    "python3.12",
    "python3.11",
    "python",
    "python3",
  ];
}

function probeAiosqliteRuntime(root, command) {
  const runtimeResult = runCapture(
    root,
    command,
    [
      "-c",
      [
        "import asyncio",
        "import aiosqlite",
        "",
        "async def main():",
        "    conn = await aiosqlite.connect(':memory:')",
        "    await conn.execute('SELECT 1')",
        "    await conn.close()",
        "",
        "asyncio.run(main())",
      ].join("\n"),
    ],
    { timeout: PYTHON_PROBE_TIMEOUT_MS }
  );

  if (!runtimeResult.error && runtimeResult.status === 0) {
    return null;
  }

  if (runtimeResult.error && runtimeResult.error.code === "ETIMEDOUT") {
    return "timed out while opening an async SQLite connection";
  }

  const stderr = String(runtimeResult.stderr || "").trim();
  if (stderr) {
    return compactProbeDetail(stderr);
  }

  return "failed to open an async SQLite connection";
}

function probePython(root, command, requiredImports) {
  if (command.includes(path.sep) && !existsSync(command)) {
    return {
      command,
      usable: false,
      reason: "missing_path",
    };
  }

  const versionResult = runCapture(
    root,
    command,
    ["-c", 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],
    { timeout: PYTHON_PROBE_TIMEOUT_MS }
  );
  if (versionResult.error || versionResult.status !== 0) {
    return {
      command,
      usable: false,
      reason: "unavailable",
    };
  }

  const version = String(versionResult.stdout || "").trim();
  const [major, minor] = version
    .split(".")
    .map((value) => Number.parseInt(value, 10));
  if (!version || Number.isNaN(major) || Number.isNaN(minor)) {
    return {
      command,
      usable: false,
      reason: "invalid_version",
      version,
    };
  }

  if (major === 3 && minor >= 14) {
    return {
      command,
      usable: false,
      reason: "unsupported_async_sqlite_runtime",
      version,
    };
  }

  if (
    major !== 3 ||
    minor < MIN_PYTHON_MINOR ||
    minor >= MAX_PYTHON_MINOR_EXCLUSIVE
  ) {
    return {
      command,
      usable: false,
      reason: "unsupported_version",
      version,
    };
  }

  const importsResult = runCapture(
    root,
    command,
    [
      "-c",
      `import importlib.util; mods=${JSON.stringify(
        requiredImports
      )}; missing=[m for m in mods if importlib.util.find_spec(m) is None]; print(",".join(missing))`,
    ],
    { timeout: PYTHON_PROBE_TIMEOUT_MS }
  );
  if (importsResult.error || importsResult.status !== 0) {
    return {
      command,
      usable: false,
      reason: "module_probe_failed",
      version,
    };
  }

  const missingModules = String(importsResult.stdout || "")
    .trim()
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (missingModules.length > 0) {
    return {
      command,
      usable: false,
      reason: "missing_modules",
      version,
      missingModules,
    };
  }

  if (requiredImports.includes("aiosqlite")) {
    const runtimeFailure = probeAiosqliteRuntime(root, command);
    if (runtimeFailure) {
      return {
        command,
        usable: false,
        reason: "runtime_probe_failed",
        version,
        runtimeFailure,
      };
    }
  }

  return {
    command,
    usable: true,
    version,
  };
}

function evaluatePythonCandidates(root, requiredImports) {
  const seen = new Set();
  const reports = [];

  for (const candidate of getPythonCandidates(root)) {
    if (seen.has(candidate)) {
      continue;
    }
    seen.add(candidate);
    reports.push(probePython(root, candidate, requiredImports));
  }

  return reports;
}

function findUsablePython(reports) {
  return reports.find((report) => report.usable) ?? null;
}

function classifyDockerProbeResult(result) {
  if (!result.error && result.status === 0) {
    return {
      available: true,
      reason: "available",
      detail: null,
    };
  }

  const detail =
    compactProbeDetail(result.stderr) ||
    compactProbeDetail(result.stdout) ||
    compactProbeDetail(result.error?.message);
  const errorCode = result.error?.code || null;
  const haystack = [detail, errorCode, result.error?.message]
    .filter(Boolean)
    .join(" | ")
    .toLowerCase();

  if (errorCode === "ENOENT") {
    return {
      available: false,
      reason: "missing_cli",
      detail,
    };
  }

  if (errorCode === "ETIMEDOUT") {
    return {
      available: false,
      reason: "probe_timed_out",
      detail: detail || "timed out while contacting the Docker daemon",
    };
  }

  if (
    errorCode === "EPERM" ||
    haystack.includes("permission denied") ||
    haystack.includes("access is denied")
  ) {
    return {
      available: false,
      reason: "permission_denied",
      detail: detail || "permission denied while contacting the Docker daemon",
    };
  }

  if (
    haystack.includes("cannot connect to the docker daemon") ||
    haystack.includes("is the docker daemon running") ||
    haystack.includes("error during connect") ||
    haystack.includes("cannot connect to the docker engine")
  ) {
    return {
      available: false,
      reason: "daemon_unreachable",
      detail: detail || "Docker daemon is unreachable",
    };
  }

  return {
    available: false,
    reason: "probe_failed",
    detail,
  };
}

function probeDocker(root) {
  const availability = runCapture(
    root,
    "docker",
    ["images", "--format", "{{.Repository}}:{{.Tag}}"],
    { timeout: DOCKER_PROBE_TIMEOUT_MS }
  );

  const directReport = {
    ...classifyDockerProbeResult(availability),
    accessMode: "direct",
  };
  if (
    directReport.available ||
    directReport.reason !== "permission_denied" ||
    process.platform === "win32"
  ) {
    return directReport;
  }

  const sgResult = runCapture(
    root,
    "sg",
    ["docker", "-c", buildShellCommand("docker", ["images", "--format", "{{.Repository}}:{{.Tag}}"])],
    { timeout: DOCKER_PROBE_TIMEOUT_MS }
  );
  const sgReport = classifyDockerProbeResult(sgResult);
  if (sgReport.available) {
    return {
      ...sgReport,
      accessMode: "sg",
    };
  }

  return directReport;
}

function runDockerCommand(root, args, options = {}, dockerReport = null) {
  const report = dockerReport || probeDocker(root);
  if (report.accessMode === "sg") {
    return runCommand(root, "sg", ["docker", "-c", buildShellCommand("docker", args)], options);
  }
  return runCommand(root, "docker", args, options);
}

function buildDockerPythonRunArgs(root, { requirementsPath, shellCommand, extraArgs = [] }) {
  const pipCacheVolume = getDockerPipCacheVolumeName(root);
  const installAndRun = [
    `python -m pip install --cache-dir ${shellEscape(
      DOCKER_PIP_CACHE_MOUNT
    )} -r ${shellEscape(requirementsPath)} >/tmp/pip-install.log`,
    shellCommand,
  ].join(" && ");

  return [
    "run",
    "--rm",
    "-e",
    "PIP_DISABLE_PIP_VERSION_CHECK=1",
    "-e",
    "PIP_ROOT_USER_ACTION=ignore",
    "-v",
    `${root}:/work`,
    "-v",
    `${pipCacheVolume}:${DOCKER_PIP_CACHE_MOUNT}`,
    "-w",
    "/work",
    DOCKER_FALLBACK_IMAGE,
    "sh",
    "-lc",
    installAndRun,
    ...extraArgs,
  ];
}

function shouldRetryWithDocker(result) {
  return Boolean(
    result?.error &&
      (result.error.code === "ENOENT" || result.error.code === "ETIMEDOUT")
  );
}

function runPythonTaskWithDockerFallback(
  {
    root,
    taskLabel,
    requirementsPath,
    requiredImports,
    pythonArgs,
    dockerShellCommand,
    dockerExtraArgs = [],
    timeout,
  },
  overrides = {}
) {
  const evaluateCandidates =
    overrides.evaluatePythonCandidates || evaluatePythonCandidates;
  const selectUsablePython = overrides.findUsablePython || findUsablePython;
  const runLocalCommand = overrides.runCommand || runCommand;
  const probeDockerRuntime = overrides.probeDocker || probeDocker;
  const buildDockerArgs =
    overrides.buildDockerPythonRunArgs || buildDockerPythonRunArgs;
  const runDockerFallback = overrides.runDockerCommand || runDockerCommand;
  const formatDiagnostics =
    overrides.formatEnvironmentDiagnostics || formatEnvironmentDiagnostics;

  const pythonReports = evaluateCandidates(root, requiredImports);
  const usablePython = selectUsablePython(pythonReports);

  if (usablePython) {
    const localResult = runLocalCommand(root, usablePython.command, pythonArgs, {
      timeout,
    });
    if (!shouldRetryWithDocker(localResult)) {
      return {
        mode: "local",
        result: localResult,
        pythonReports,
        dockerReport: null,
        diagnostics: null,
      };
    }
  }

  const dockerReport = probeDockerRuntime(root);
  if (dockerReport.available) {
    const dockerArgs = buildDockerArgs(root, {
      requirementsPath,
      shellCommand: dockerShellCommand,
      extraArgs: dockerExtraArgs,
    });
    const dockerResult = runDockerFallback(
      root,
      dockerArgs,
      { timeout },
      dockerReport
    );
    return {
      mode: "docker",
      result: dockerResult,
      pythonReports,
      dockerReport,
      diagnostics: null,
    };
  }

  return {
    mode: "unavailable",
    result: null,
    pythonReports,
    dockerReport,
    diagnostics: formatDiagnostics({
      taskLabel,
      requirementsPath,
      pythonReports,
      dockerReport,
    }),
  };
}

function formatDockerResolution(requirementsPath, dockerReport) {
  const localPythonResolution = `Install ${requirementsPath} into a local Python 3.${MIN_PYTHON_MINOR}-3.${
    MAX_PYTHON_MINOR_EXCLUSIVE - 1
  } environment`;

  switch (dockerReport.reason) {
    case "permission_denied":
      return `${localPythonResolution}, or restart your shell or log in again after adding your user to the \`docker\` group so Docker fallback can reach the daemon.`;
    case "daemon_unreachable":
      return `${localPythonResolution}, or start the Docker daemon before retrying Docker fallback.`;
    case "probe_timed_out":
      return `${localPythonResolution}, or make sure the Docker daemon responds within ${
        DOCKER_PROBE_TIMEOUT_MS / 1000
      }s before retrying Docker fallback.`;
    case "missing_cli":
      return `${localPythonResolution}, or install Docker for container fallback.`;
    default:
      return `${localPythonResolution}, or enable Docker fallback.`;
  }
}

function formatDockerSummary(dockerReport) {
  if (dockerReport.available) {
    return dockerReport.accessMode === "sg"
      ? "- docker: available via `sg docker` fallback for the current shell"
      : "- docker: available";
  }

  switch (dockerReport.reason) {
    case "missing_cli":
      return "- docker: command not found";
    case "permission_denied":
      return `- docker: installed, but the current shell cannot access the daemon (${dockerReport.detail})`;
    case "daemon_unreachable":
      return `- docker: CLI available, but the daemon is unreachable (${dockerReport.detail})`;
    case "probe_timed_out":
      return `- docker: daemon probe timed out (${dockerReport.detail})`;
    default:
      return `- docker: probe failed${dockerReport.detail ? ` (${dockerReport.detail})` : ""}`;
  }
}

function formatEnvironmentDiagnostics({
  taskLabel,
  requirementsPath,
  pythonReports,
  dockerReport,
}) {
  const header =
    dockerReport.reason === "permission_denied"
      ? `No usable Python environment found for ${taskLabel}, and Docker is installed but this shell cannot access the Docker daemon.`
      : dockerReport.reason === "daemon_unreachable"
        ? `No usable Python environment found for ${taskLabel}, and the Docker daemon is not reachable from this shell.`
        : `No usable Python environment or Docker runtime found for ${taskLabel}.`;
  const lines = [
    header,
    formatDockerResolution(requirementsPath, dockerReport),
    "",
    "Probe summary:",
  ];

  for (const report of pythonReports) {
    if (report.usable) {
      lines.push(`- ${report.command}: Python ${report.version} with required modules`);
      continue;
    }

    switch (report.reason) {
      case "missing_path":
        lines.push(`- ${report.command}: not found`);
        break;
      case "unsupported_version":
        lines.push(
          `- ${report.command}: unsupported Python ${report.version} (expected 3.${MIN_PYTHON_MINOR}-3.${
            MAX_PYTHON_MINOR_EXCLUSIVE - 1
          })`
        );
        break;
      case "unsupported_async_sqlite_runtime":
        lines.push(
          `- ${report.command}: Python ${report.version} is unsupported for local async SQLite runtime (aiosqlite can hang in this environment; use 3.${MIN_PYTHON_MINOR}-3.${
            MAX_PYTHON_MINOR_EXCLUSIVE - 1
          } or Docker Python ${DOCKER_FALLBACK_PYTHON})`
        );
        break;
      case "missing_modules":
        lines.push(
          `- ${report.command}: Python ${report.version}, missing modules: ${report.missingModules.join(
            ", "
          )}`
        );
        break;
      case "module_probe_failed":
        lines.push(
          `- ${report.command}: Python ${report.version}, but dependency probe failed`
        );
        break;
      case "runtime_probe_failed":
        lines.push(
          `- ${report.command}: Python ${report.version} with required modules, but runtime probe failed: ${report.runtimeFailure}`
        );
        break;
      case "invalid_version":
        lines.push(`- ${report.command}: returned an invalid Python version string`);
        break;
      default:
        lines.push(`- ${report.command}: unavailable`);
        break;
    }
  }

  lines.push(formatDockerSummary(dockerReport));
  return lines.join("\n");
}

module.exports = {
  buildDockerPythonRunArgs,
  classifyDockerProbeResult,
  evaluatePythonCandidates,
  findUsablePython,
  formatEnvironmentDiagnostics,
  probeDocker,
  runDockerCommand,
  runCommand,
  runPythonTaskWithDockerFallback,
};
