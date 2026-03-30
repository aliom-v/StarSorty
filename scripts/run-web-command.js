#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const webDir = path.join(root, "web");
const command = process.argv[2];
const passthroughArgs = process.argv.slice(3);

const supportedCommands = new Set(["dev", "build", "lint", "test", "smoke"]);
const requiredExecutables = {
  dev: ["next"],
  build: ["next"],
  lint: ["eslint"],
};

if (!command || !supportedCommands.has(command)) {
  console.error("Usage: node scripts/run-web-command.js <dev|build|lint|test|smoke>");
  process.exit(1);
}

function hasWebExecutable(name) {
  const binDir = path.join(webDir, "node_modules", ".bin");
  const candidates =
    process.platform === "win32"
      ? [path.join(binDir, `${name}.cmd`), path.join(binDir, `${name}.ps1`)]
      : [path.join(binDir, name)];

  return candidates.some((candidate) => existsSync(candidate));
}

const missingExecutables = (requiredExecutables[command] ?? []).filter(
  (name) => !hasWebExecutable(name)
);

if (missingExecutables.length > 0) {
  const nodeModulesPath = path.join(webDir, "node_modules");
  const installState = existsSync(nodeModulesPath)
    ? "The `web/node_modules` directory exists, but the required binaries are missing. Reinstall the web dependencies cleanly."
    : "The `web` dependencies are not installed yet.";

  console.error(
    [
      `Web dependency preflight failed for \`${command}\`.`,
      installState,
      `Missing executables: ${missingExecutables.join(", ")}`,
      "Run `npm --prefix web install` from the repository root before retrying.",
    ].join("\n")
  );
  process.exit(1);
}

const args = ["run", command];
if (passthroughArgs.length > 0) {
  args.push("--", ...passthroughArgs);
}

const result = spawnSync("npm", args, {
  cwd: webDir,
  stdio: "inherit",
});

if (typeof result.status === "number") {
  process.exit(result.status);
}

process.exit(1);
