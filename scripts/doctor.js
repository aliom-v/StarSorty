#!/usr/bin/env node
const path = require("node:path");

const {
  buildDoctorReport,
  formatDoctorReport,
} = require("./lib/doctor");

async function main() {
  const root = path.resolve(__dirname, "..");
  const report = await buildDoctorReport(root);
  console.log(formatDoctorReport(report));
  process.exit(report.healthy ? 0 : 1);
}

main().catch((error) => {
  console.error(`Doctor failed: ${error.message}`);
  process.exit(1);
});
