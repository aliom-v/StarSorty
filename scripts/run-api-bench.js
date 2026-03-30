#!/usr/bin/env node
const path = require("node:path");
const {
  runPythonTaskWithDockerFallback,
} = require("./lib/python-runner");

const root = path.resolve(__dirname, "..");
const apiDevRequirements = "api/requirements-dev.txt";
const runResult = runPythonTaskWithDockerFallback({
  root,
  taskLabel: "API benchmarks",
  requirementsPath: apiDevRequirements,
  requiredImports: ["aiosqlite", "fastapi", "yaml"],
  pythonArgs: ["evaluation/benchmark_api_perf.py", ...process.argv.slice(2)],
  dockerShellCommand: 'python evaluation/benchmark_api_perf.py "$@"',
  dockerExtraArgs: ["sh", ...process.argv.slice(2)],
  timeout: 900000,
});

if (runResult.diagnostics) {
  console.error(runResult.diagnostics);
  process.exit(1);
}

process.exit(runResult.result?.status ?? 1);
