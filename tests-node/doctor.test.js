const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  buildDoctorReport,
  checkApiPort,
  formatDoctorReport,
  inspectOriginMain,
} = require("../scripts/lib/doctor");

function touch(filePath, content = "") {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

test("package json exposes the doctor and reset preview commands", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8")
  );

  assert.equal(packageJson.scripts.doctor, "node scripts/doctor.js");
  assert.equal(
    packageJson.scripts["reset:data:dry-run"],
    "node scripts/clean-workspace.js --data --dry-run"
  );
});

test("inspectOriginMain reports divergence after refresh", () => {
  const calls = [];

  const result = inspectOriginMain("/tmp/star-sorty", (root, args) => {
    calls.push({ root, args });
    if (args[0] === "fetch") {
      return { status: 0, stdout: "", stderr: "" };
    }
    if (args[0] === "rev-list") {
      return { status: 0, stdout: "2 1", stderr: "" };
    }
    throw new Error(`Unexpected git command: ${args.join(" ")}`);
  });

  assert.equal(result.name, "origin/main");
  assert.equal(result.status, "diverged");
  assert.equal(result.ahead, 2);
  assert.equal(result.behind, 1);
  assert.equal(result.hardFailure, true);
  assert.match(result.detail, /ahead 2, behind 1/);
  assert.deepEqual(calls, [
    {
      root: "/tmp/star-sorty",
      args: ["fetch", "--prune", "--quiet", "origin"],
    },
    {
      root: "/tmp/star-sorty",
      args: ["rev-list", "--left-right", "--count", "HEAD...origin/main"],
    },
  ]);
});

test("checkApiPort detects occupied and free ports", () => {
  const busyResult = checkApiPort(4321, (command, args) => {
    if (process.platform === "win32") {
      assert.equal(command, "powershell");
      assert.ok(args.some((arg) => arg.includes("Get-NetTCPConnection -LocalPort 4321 -State Listen")));
      return { status: 0, stdout: "1234\n", stderr: "" };
    }

    assert.equal(command, "lsof");
    assert.deepEqual(args, ["-nP", "-iTCP:4321", "-sTCP:LISTEN"]);
    return { status: 0, stdout: "node 1234 user  22u  IPv4 0x0 TCP 127.0.0.1:4321 (LISTEN)\n", stderr: "" };
  });
  assert.equal(busyResult.status, "in_use");
  assert.equal(busyResult.hardFailure, true);

  const freeResult = checkApiPort(4321, (command, args) => {
    if (process.platform === "win32") {
      assert.equal(command, "powershell");
      assert.ok(args.some((arg) => arg.includes("Get-NetTCPConnection -LocalPort 4321 -State Listen")));
      return { status: 0, stdout: "", stderr: "" };
    }

    assert.equal(command, "lsof");
    assert.deepEqual(args, ["-nP", "-iTCP:4321", "-sTCP:LISTEN"]);
    return { status: 1, stdout: "", stderr: "" };
  });
  assert.equal(freeResult.status, "free");
  assert.equal(freeResult.hardFailure, false);
});

test("buildDoctorReport keeps missing data informational but fails on hard issues", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "starsorty-doctor-"));

  touch(path.join(root, "data", "keep.txt"), "keep");

  const report = await buildDoctorReport(root, {
    existsSync(filePath) {
      return fs.existsSync(filePath);
    },
    inspectOriginMain() {
      return {
        name: "origin/main",
        status: "diverged",
        detail: "ahead 1, behind 0",
        hardFailure: true,
        ahead: 1,
        behind: 0,
      };
    },
    checkApiPort() {
      return {
        name: "API port 4321",
        status: "in_use",
        detail: "port 4321 is already in use",
        hardFailure: true,
      };
    },
  });

  assert.equal(report.healthy, false);
  assert.deepEqual(
    report.hardFailures.map((check) => check.name),
    ["root .venv", "web/node_modules", "origin/main", "API port 4321"]
  );
  assert.equal(
    report.checks.find((check) => check.name === "data/app.db").status,
    "missing"
  );
  assert.equal(
    report.checks.find((check) => check.name === "data/app.db").hardFailure,
    false
  );

  const output = formatDoctorReport(report);
  assert.match(output, /Doctor report: needs attention/);
  assert.match(output, /data\/app\.db: missing/);
  assert.match(output, /Hard failures:/);
});
