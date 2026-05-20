const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_DIRECT_PATHS = [
  ".cache",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  ".run",
  "logs",
  "web/.next",
  "web/out",
];

const DEPENDENCY_PATHS = ["web/node_modules", "api/.venv"];
const DATA_PATHS = ["data/app.db"];
const CACHE_SKIP_DIRECTORIES = new Set([".git", ".venv", "node_modules", "data"]);

function toPosix(relativePath) {
  return relativePath.split(path.sep).join("/");
}

function exists(filePath) {
  try {
    fs.lstatSync(filePath);
    return true;
  } catch {
    return false;
  }
}

function addPlanEntry(plan, root, relativePath, kind) {
  const normalized = toPosix(relativePath);
  const absolutePath = path.join(root, ...normalized.split("/"));
  if (!exists(absolutePath)) {
    return;
  }
  const key = normalized;
  if (!plan.has(key)) {
    plan.set(key, {
      absolutePath,
      relativePath: normalized,
      kind,
    });
  }
}

function collectPythonCaches(root, relativePath, plan) {
  const absolutePath = relativePath ? path.join(root, ...relativePath.split("/")) : root;
  let entries;
  try {
    entries = fs.readdirSync(absolutePath, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    const childRelativePath = relativePath ? `${relativePath}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      if (entry.name === "__pycache__") {
        addPlanEntry(plan, root, childRelativePath, "dir");
        continue;
      }
      if (CACHE_SKIP_DIRECTORIES.has(entry.name)) {
        continue;
      }
      collectPythonCaches(root, childRelativePath, plan);
    }
  }
}

function buildCleanupPlan(root, options = {}) {
  const plan = new Map();
  const includeDeps = Boolean(options.includeDeps);
  const includeData = Boolean(options.includeData);

  for (const relativePath of DEFAULT_DIRECT_PATHS) {
    addPlanEntry(plan, root, relativePath, "dir");
  }

  if (includeDeps) {
    for (const relativePath of DEPENDENCY_PATHS) {
      addPlanEntry(plan, root, relativePath, "dir");
    }
  }

  if (includeData) {
    for (const relativePath of DATA_PATHS) {
      addPlanEntry(plan, root, relativePath, "file");
    }
  }

  collectPythonCaches(root, "", plan);

  return [...plan.values()].sort((left, right) =>
    left.relativePath.localeCompare(right.relativePath)
  );
}

function executeCleanupPlan(plan, options = {}) {
  const dryRun = Boolean(options.dryRun);
  const removed = [];
  const errors = [];

  for (const entry of plan) {
    if (dryRun) {
      continue;
    }
    try {
      fs.rmSync(entry.absolutePath, { recursive: true, force: true });
      removed.push(entry);
    } catch (error) {
      errors.push({ entry, error });
    }
  }

  return {
    removed,
    errors,
    wouldRemove: dryRun ? [...plan] : [],
  };
}

function formatCleanupSummary(plan, options = {}) {
  const lines = [];
  lines.push(`Cleanup plan (${plan.length} paths)`);
  if (options.includeDeps) {
    lines.push("- includes dependency cleanup");
  }
  if (options.includeData) {
    lines.push("- includes data reset");
  }
  for (const entry of plan) {
    lines.push(`- ${entry.relativePath}`);
  }
  return lines.join("\n");
}

function parseCleanupFlags(argv) {
  const args = new Set(argv);
  return {
    dryRun: args.has("--dry-run"),
    includeDeps: args.has("--deps") || args.has("--all"),
    includeData: args.has("--data") || args.has("--all"),
  };
}

module.exports = {
  buildCleanupPlan,
  executeCleanupPlan,
  formatCleanupSummary,
  parseCleanupFlags,
};
