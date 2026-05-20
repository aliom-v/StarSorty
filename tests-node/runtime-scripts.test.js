const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

test("host startup scripts use the root Python virtual environment", () => {
  const unixStart = read("scripts/unix/start.sh");
  const windowsStart = read("scripts/windows/start.ps1");
  const windowsDev = read("scripts/windows/dev.ps1");

  assert.match(unixStart, /\$ROOT\/\.venv\/bin\/python/);
  assert.doesNotMatch(unixStart, /api\/\.venv/);

  for (const content of [windowsStart, windowsDev]) {
    assert.match(content, /\.venv\\\\Scripts\\\\python\.exe/);
    assert.doesNotMatch(content, /api\\\\\.venv/);
  }
});
