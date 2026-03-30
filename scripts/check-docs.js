#!/usr/bin/env node

const path = require("node:path");

const { validateDocumentation } = require("./lib/docs-check");

const root = path.resolve(__dirname, "..");
const result = validateDocumentation(root);

if (result.errors.length > 0) {
  console.error("Documentation checks failed:");
  for (const error of result.errors) {
    console.error(`- ${error}`);
  }
  process.exit(1);
}

console.log(
  `Documentation checks passed (${result.checkedFiles} files, ${result.checkedReferences} references).`
);
