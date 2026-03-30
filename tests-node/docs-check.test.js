const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { extractPathReferences, validateDocumentation } = require("../scripts/lib/docs-check");

function writeFile(rootDir, relativePath, content = "") {
  const absolutePath = path.join(rootDir, relativePath);
  fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
  fs.writeFileSync(absolutePath, content, "utf8");
}

test("extractPathReferences ignores fenced code blocks and API routes", () => {
  const references = extractPathReferences(
    "docs/README.md",
    [
      "看 `../README.md` 与 [配置](guides/configuration.md#env)。",
      "不要把 `/sync` 当成仓库路径。",
      "```bash",
      "cat docs/guides/missing.md",
      "```",
      "再看 `../scripts/README.md`。",
      "",
    ].join("\n")
  );

  assert.deepEqual(
    references.map(({ value, line }) => ({ value, line })),
    [
      { value: "guides/configuration.md", line: 1 },
      { value: "../README.md", line: 1 },
      { value: "../scripts/README.md", line: 6 },
    ]
  );
});

test("validateDocumentation reports missing references and duplicate doc indexes", () => {
  const rootDir = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-docs-check-"));

  writeFile(
    rootDir,
    "README.md",
    "# Root\n\nSee `docs/README.md` and `CONTRIBUTING.md`.\n"
  );
  writeFile(rootDir, "CONTRIBUTING.md", "# Contributing\n");
  writeFile(
    rootDir,
    "docs/README.md",
    "# Docs\n\nSee `guides/missing.md` and `../CONTRIBUTING.md`.\n"
  );
  writeFile(rootDir, "docs/guides/README.md", "# Duplicate\n");

  const result = validateDocumentation(rootDir);

  assert.equal(result.checkedFiles, 4);
  assert.ok(
    result.errors.some((error) => error.includes("docs/guides/README.md should not exist")),
    `expected duplicate index error, got: ${result.errors.join("; ")}`
  );
  assert.ok(
    result.errors.some((error) => error.includes("docs/README.md:3")),
    `expected missing reference error, got: ${result.errors.join("; ")}`
  );
  assert.ok(
    result.errors.some((error) => error.includes("guides/missing.md")),
    `expected missing guides/missing.md error, got: ${result.errors.join("; ")}`
  );
});
