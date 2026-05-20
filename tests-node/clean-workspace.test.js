const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  buildCleanupPlan,
  executeCleanupPlan,
  formatCleanupSummary,
  parseCleanupFlags,
} = require("../scripts/lib/clean-workspace");

function touch(filePath, content = "") {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

function relPaths(entries) {
  return entries.map((entry) => entry.relativePath).sort();
}

test("default cleanup removes generated caches but preserves runtime inputs", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-clean-"));

  touch(path.join(root, ".env"), "KEEP_ME=1");
  touch(path.join(root, ".venv", "bin", "python"), "binary");
  touch(path.join(root, ".cache", "index"), "cache");
  touch(path.join(root, ".pytest_cache", "state"), "cache");
  touch(path.join(root, ".run", "api.pid"), "123");
  touch(path.join(root, "logs", "api.log"), "log");
  touch(path.join(root, "web", ".next", "build"), "build");
  touch(path.join(root, "web", "out", "export"), "out");
  touch(path.join(root, "web", "node_modules", ".bin", "next"), "binary");
  touch(path.join(root, "api", "app", "__pycache__", "module.cpython-314.pyc"), "pyc");
  touch(path.join(root, "data", "app.db"), "sqlite");

  const plan = buildCleanupPlan(root);
  const planned = relPaths(plan);

  assert.ok(planned.includes(".cache"));
  assert.ok(planned.includes(".pytest_cache"));
  assert.ok(planned.includes(".run"));
  assert.ok(planned.includes("logs"));
  assert.ok(planned.includes("web/.next"));
  assert.ok(planned.includes("web/out"));
  assert.ok(planned.includes("api/app/__pycache__"));
  assert.ok(!planned.includes(".env"));
  assert.ok(!planned.includes(".venv"));
  assert.ok(!planned.includes("data/app.db"));
  assert.ok(!planned.includes("web/node_modules"));

  const dryRun = executeCleanupPlan(plan, { dryRun: true });
  assert.equal(dryRun.removed.length, 0);
  assert.ok(dryRun.wouldRemove.some((entry) => entry.relativePath === "web/.next"));
  assert.ok(fs.existsSync(path.join(root, ".env")));
  assert.ok(fs.existsSync(path.join(root, ".venv", "bin", "python")));
});

test("dependency cleanup can remove web and legacy API dependencies without touching root venv", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-clean-deps-"));

  touch(path.join(root, ".venv", "bin", "python"), "binary");
  touch(path.join(root, "api", ".venv", "bin", "python"), "binary");
  touch(path.join(root, "web", "node_modules", ".bin", "next"), "binary");

  const plan = buildCleanupPlan(root, { includeDeps: true });
  const planned = relPaths(plan);

  assert.ok(planned.includes("api/.venv"));
  assert.ok(planned.includes("web/node_modules"));
  assert.ok(!planned.includes(".venv"));

  const result = executeCleanupPlan(plan);
  assert.ok(result.removed.some((entry) => entry.relativePath === "api/.venv"));
  assert.ok(result.removed.some((entry) => entry.relativePath === "web/node_modules"));
  assert.ok(fs.existsSync(path.join(root, ".venv", "bin", "python")));
  assert.ok(!fs.existsSync(path.join(root, "api", ".venv")));
  assert.ok(!fs.existsSync(path.join(root, "web", "node_modules")));
});

test("data reset only removes app.db when requested", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-reset-data-"));

  touch(path.join(root, "data", "app.db"), "sqlite");
  touch(path.join(root, "data", "keep.txt"), "keep");

  const plan = buildCleanupPlan(root, { includeData: true });
  const planned = relPaths(plan);

  assert.ok(planned.includes("data/app.db"));
  assert.ok(!planned.includes("data"));

  const result = executeCleanupPlan(plan);
  assert.ok(result.removed.some((entry) => entry.relativePath === "data/app.db"));
  assert.ok(!fs.existsSync(path.join(root, "data", "app.db")));
  assert.ok(fs.existsSync(path.join(root, "data", "keep.txt")));
});

test("dry-run data reset keeps the destructive target explicit", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-reset-data-preview-"));

  touch(path.join(root, "data", "app.db"), "sqlite");
  touch(path.join(root, "data", "keep.txt"), "keep");

  const flags = parseCleanupFlags(["--data", "--dry-run"]);
  const plan = buildCleanupPlan(root, flags);
  const summary = formatCleanupSummary(plan, flags);

  assert.deepEqual(flags, {
    dryRun: true,
    includeDeps: false,
    includeData: true,
  });
  assert.deepEqual(relPaths(plan), ["data/app.db"]);
  assert.match(summary, /includes data reset/);
  assert.match(summary, /data\/app\.db/);

  const result = executeCleanupPlan(plan, { dryRun: true });
  assert.equal(result.removed.length, 0);
  assert.equal(result.wouldRemove.length, 1);
  assert.ok(fs.existsSync(path.join(root, "data", "app.db")));
  assert.ok(fs.existsSync(path.join(root, "data", "keep.txt")));
});
