const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const command = process.argv[2];

if (!command) {
  console.error("Usage: node scripts/run-platform.js <dev|start|stop|status>");
  process.exit(1);
}

const supported = new Set(["dev", "start", "stop", "status"]);
if (!supported.has(command)) {
  console.error(`Unsupported command: ${command}`);
  process.exit(1);
}

const isWin = process.platform === "win32";
const bin = isWin ? "powershell" : "bash";
const scriptPath = isWin
  ? path.join(__dirname, "windows", `${command}.ps1`)
  : path.join(__dirname, "unix", `${command}.sh`);
const args = isWin
  ? ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath]
  : [scriptPath];

const result = spawnSync(bin, args, { cwd: root, stdio: "inherit" });
if (typeof result.status === "number") {
  process.exit(result.status);
}

process.exit(1);
