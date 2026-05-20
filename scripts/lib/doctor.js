const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const API_PORT = 4321;

function createCheck(name, status, detail, hardFailure = false, extra = {}) {
  return {
    name,
    status,
    detail: detail || null,
    hardFailure,
    ...extra,
  };
}

function candidateVenvPythonPaths(root) {
  return [
    path.join(root, ".venv", "bin", "python"),
    path.join(root, ".venv", "Scripts", "python.exe"),
  ];
}

function candidateWebExecutablePaths(root) {
  const binDir = path.join(root, "web", "node_modules", ".bin");
  return process.platform === "win32"
    ? [path.join(binDir, "next.cmd"), path.join(binDir, "next.ps1")]
    : [path.join(binDir, "next")];
}

function defaultRunGit(root, args) {
  return spawnSync("git", args, {
    cwd: root,
    encoding: "utf8",
  });
}

function defaultRunCommand(command, args) {
  return spawnSync(command, args, {
    encoding: "utf8",
  });
}

function checkRootVenv(root, existsSync = fs.existsSync) {
  const pythonPath = candidateVenvPythonPaths(root).find((candidate) =>
    existsSync(candidate)
  );
  if (!pythonPath) {
    return createCheck(
      "root .venv",
      "missing",
      "root Python venv is missing",
      true
    );
  }

  return createCheck("root .venv", "present", pythonPath);
}

function checkWebDependencies(root, existsSync = fs.existsSync) {
  const nodeModulesPath = path.join(root, "web", "node_modules");
  if (!existsSync(nodeModulesPath)) {
    return createCheck(
      "web/node_modules",
      "missing",
      "web dependencies are missing",
      true
    );
  }

  const executablePath = candidateWebExecutablePaths(root).find((candidate) =>
    existsSync(candidate)
  );
  if (!executablePath) {
    return createCheck(
      "web/node_modules",
      "incomplete",
      "required web binaries are missing",
      true
    );
  }

  return createCheck("web/node_modules", "present", executablePath);
}

function checkDatabase(root, existsSync = fs.existsSync) {
  const databasePath = path.join(root, "data", "app.db");
  if (!existsSync(databasePath)) {
    return createCheck(
      "data/app.db",
      "missing",
      "local SQLite database is absent",
      false
    );
  }

  return createCheck("data/app.db", "present", databasePath);
}

function inspectOriginMain(root, runGit = defaultRunGit) {
  const fetchResult = runGit(root, ["fetch", "--prune", "--quiet", "origin"]);
  if (fetchResult.status !== 0) {
    const message = String(fetchResult.stderr || fetchResult.stdout || "git fetch failed").trim();
    return createCheck("origin/main", "unavailable", message, true);
  }

  const statusResult = runGit(root, ["rev-list", "--left-right", "--count", "HEAD...origin/main"]);
  if (statusResult.status !== 0) {
    const message = String(
      statusResult.stderr || statusResult.stdout || "git rev-list failed"
    ).trim();
    return createCheck("origin/main", "unavailable", message, true);
  }

  const [aheadRaw, behindRaw] = String(statusResult.stdout || "")
    .trim()
    .split(/\s+/);
  const ahead = Number.parseInt(aheadRaw, 10);
  const behind = Number.parseInt(behindRaw, 10);
  if (Number.isNaN(ahead) || Number.isNaN(behind)) {
    return createCheck(
      "origin/main",
      "unavailable",
      `unexpected git rev-list output: ${String(statusResult.stdout || "").trim()}`,
      true
    );
  }
  const synced = ahead === 0 && behind === 0;

  return createCheck(
    "origin/main",
    synced ? "synced" : "diverged",
    synced ? "ahead 0, behind 0" : `ahead ${ahead}, behind ${behind}`,
    !synced,
    { ahead, behind }
  );
}

function checkApiPort(port = API_PORT, runCommand = defaultRunCommand) {
  if (process.platform === "win32") {
    const result = runCommand("powershell", [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      [
        `Get-NetTCPConnection -LocalPort ${port} -State Listen`,
        "-ErrorAction SilentlyContinue",
        "| Select-Object -ExpandProperty OwningProcess -Unique",
      ].join(" "),
    ]);

    if (result.error) {
      return createCheck(
        `API port ${port}`,
        "error",
        result.error.message || "port probe failed",
        true
      );
    }

    const output = String(result.stdout || "").trim();
    if (output) {
      return createCheck(
        `API port ${port}`,
        "in_use",
        `port ${port} is already in use`,
        true
      );
    }

    if (result.status !== 0) {
      return createCheck(
        `API port ${port}`,
        "error",
        String(result.stderr || result.stdout || "port probe failed").trim(),
        true
      );
    }

    return createCheck(`API port ${port}`, "free", `port ${port} is available`);
  }

  const result = runCommand("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"]);
  if (result.error) {
    return createCheck(
      `API port ${port}`,
      "error",
      result.error.message || "port probe failed",
      true
    );
  }

  const output = String(result.stdout || "").trim();
  if (result.status === 0 && output) {
    return createCheck(
      `API port ${port}`,
      "in_use",
      `port ${port} is already in use`,
      true
    );
  }

  if (result.status === 1 && !output) {
    return createCheck(`API port ${port}`, "free", `port ${port} is available`);
  }

  if (result.status !== 0) {
    return createCheck(
      `API port ${port}`,
      "error",
      String(result.stderr || result.stdout || "port probe failed").trim(),
      true
    );
  }

  return createCheck(`API port ${port}`, "free", `port ${port} is available`);
}

async function buildDoctorReport(root, options = {}) {
  const existsSync = options.existsSync || fs.existsSync;
  const runGit = options.runGit || defaultRunGit;
  const inspectOrigin = options.inspectOriginMain || inspectOriginMain;
  const checkPort = options.checkApiPort || checkApiPort;

  const checks = [
    checkRootVenv(root, existsSync),
    checkWebDependencies(root, existsSync),
    checkDatabase(root, existsSync),
    await Promise.resolve(inspectOrigin(root, runGit)),
    await Promise.resolve(checkPort(API_PORT)),
  ];

  const hardFailures = checks.filter((check) => check.hardFailure);
  return {
    root,
    checks,
    hardFailures,
    healthy: hardFailures.length === 0,
  };
}

function formatDoctorReport(report) {
  const lines = [];
  lines.push(`Doctor report: ${report.healthy ? "healthy" : "needs attention"}`);
  for (const check of report.checks) {
    const detail = check.detail ? ` (${check.detail})` : "";
    lines.push(`- ${check.name}: ${check.status}${detail}`);
  }
  if (report.hardFailures.length > 0) {
    lines.push("Hard failures:");
    for (const check of report.hardFailures) {
      lines.push(`- ${check.name}: ${check.detail || check.status}`);
    }
  }
  return lines.join("\n");
}

module.exports = {
  API_PORT,
  buildDoctorReport,
  checkApiPort,
  checkDatabase,
  checkRootVenv,
  checkWebDependencies,
  formatDoctorReport,
  inspectOriginMain,
  defaultRunCommand,
};
