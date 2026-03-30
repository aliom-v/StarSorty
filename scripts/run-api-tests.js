#!/usr/bin/env node
const path = require("node:path");
const {
  runPythonTaskWithDockerFallback,
} = require("./lib/python-runner");

const root = path.resolve(__dirname, "..");
const apiDevRequirements = "api/requirements-dev.txt";
const runResult = runPythonTaskWithDockerFallback({
  root,
  taskLabel: "API tests",
  requirementsPath: apiDevRequirements,
  requiredImports: ["aiosqlite", "fastapi", "pytest", "yaml"],
  pythonArgs: ["-m", "pytest", "-q", "api/tests"],
  dockerShellCommand: "python -m pytest -q api/tests",
  timeout: 120000,
});

if (runResult.diagnostics) {
  console.error(runResult.diagnostics);
  process.exit(1);
}

process.exit(runResult.result?.status ?? 1);
