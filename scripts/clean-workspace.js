#!/usr/bin/env node
const path = require("node:path");

const {
  buildCleanupPlan,
  executeCleanupPlan,
  formatCleanupSummary,
  parseCleanupFlags,
} = require("./lib/clean-workspace");

const root = path.resolve(__dirname, "..");
const flags = parseCleanupFlags(process.argv.slice(2));
const plan = buildCleanupPlan(root, flags);

if (plan.length === 0) {
  console.log("No generated files found.");
  process.exit(0);
}

if (flags.dryRun) {
  console.log(formatCleanupSummary(plan, flags));
  process.exit(0);
}

const result = executeCleanupPlan(plan);
if (result.errors.length > 0) {
  console.error("Cleanup failed:");
  for (const { entry, error } of result.errors) {
    console.error(`- ${entry.relativePath}: ${error.message}`);
  }
  process.exit(1);
}

console.log(`Removed ${result.removed.length} generated paths.`);
