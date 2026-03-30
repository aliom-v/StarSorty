const fs = require("node:fs");
const path = require("node:path");

const ROOT_DOC_FILES = ["README.md", "CONTRIBUTING.md", "CHANGELOG.md", "scripts/README.md"];
const DOC_DIRECTORIES = ["docs", "archive"];
const FORBIDDEN_DOC_FILES = [
  "docs/guides/README.md",
  "docs/roadmap/README.md",
  "docs/archive/README.md",
];
const FORBIDDEN_DOC_DIRECTORIES = ["docs/archive"];
const ALLOWED_MISSING_REFERENCE_EXAMPLES = new Set([
  "guides/README.md",
  "roadmap/README.md",
  "archive/README.md",
  "docs/guides/README.md",
  "docs/roadmap/README.md",
  "docs/archive/README.md",
]);
const ALLOWED_MISSING_REFERENCE_LINE_HINT = /不要再新增|重复入口|重复导航页/u;
const IGNORED_RUNTIME_REFERENCE_PREFIXES = [
  "data/",
  "logs/",
  "web/node_modules/",
  "evaluation/benchmarks/",
];
const ROOT_REFERENCE_FILES = new Set([
  "README.md",
  "CONTRIBUTING.md",
  "CHANGELOG.md",
  "docker-compose.yml",
  "package.json",
  "package-lock.json",
  "RTK.md",
  "AGENTS.md",
]);

function walkMarkdownFiles(rootDir, relativeDir) {
  const absoluteDir = path.join(rootDir, relativeDir);
  if (!fs.existsSync(absoluteDir)) {
    return [];
  }

  const entries = fs.readdirSync(absoluteDir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const childRelativePath = path.join(relativeDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkMarkdownFiles(rootDir, childRelativePath));
      continue;
    }

    if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(childRelativePath);
    }
  }

  return files;
}

function listDocumentationFiles(rootDir) {
  const files = [];

  for (const relativePath of ROOT_DOC_FILES) {
    if (fs.existsSync(path.join(rootDir, relativePath))) {
      files.push(relativePath);
    }
  }

  for (const relativeDir of DOC_DIRECTORIES) {
    files.push(...walkMarkdownFiles(rootDir, relativeDir));
  }

  return Array.from(new Set(files)).sort();
}

function stripAnchorAndQuery(reference) {
  let endIndex = reference.length;

  for (const delimiter of ["#", "?"]) {
    const delimiterIndex = reference.indexOf(delimiter);
    if (delimiterIndex !== -1) {
      endIndex = Math.min(endIndex, delimiterIndex);
    }
  }

  return reference.slice(0, endIndex);
}

function normalizeReferenceToken(rawToken) {
  if (!rawToken) {
    return null;
  }

  let token = rawToken.trim();
  if (!token) {
    return null;
  }

  if (token.startsWith("<") && token.endsWith(">")) {
    token = token.slice(1, -1).trim();
  }

  const firstWhitespaceIndex = token.search(/\s/);
  if (firstWhitespaceIndex !== -1) {
    token = token.slice(0, firstWhitespaceIndex);
  }

  token = stripAnchorAndQuery(token).trim();

  if (!token) {
    return null;
  }

  return token.replace(/[),.;:]+$/u, "");
}

function isLikelyRepoPath(token) {
  if (!token) {
    return false;
  }

  if (
    token.startsWith("#") ||
    token.startsWith("/") ||
    token.startsWith("http://") ||
    token.startsWith("https://") ||
    token.startsWith("mailto:") ||
    token.includes("://") ||
    token.includes("{") ||
    token.includes("}") ||
    token.includes("*") ||
    /\s/.test(token)
  ) {
    return false;
  }

  if (token.includes(":")) {
    return false;
  }

  if (ROOT_REFERENCE_FILES.has(token)) {
    return true;
  }

  if (token.startsWith("./") || token.startsWith("../")) {
    return true;
  }

  if (!token.includes("/")) {
    return false;
  }

  return token.endsWith("/") || path.posix.basename(token).includes(".");
}

function extractMarkdownLinks(line) {
  const references = [];
  const markdownLinkPattern = /!?\[[^\]]*]\(([^)]+)\)/g;
  let match;

  while ((match = markdownLinkPattern.exec(line)) !== null) {
    const normalizedReference = normalizeReferenceToken(match[1]);
    if (!isLikelyRepoPath(normalizedReference)) {
      continue;
    }

    references.push(normalizedReference);
  }

  return references;
}

function extractInlineCodeReferences(line) {
  const references = [];
  const inlineCodePattern = /`([^`\n]+)`/g;
  let match;

  while ((match = inlineCodePattern.exec(line)) !== null) {
    const normalizedReference = normalizeReferenceToken(match[1]);
    if (!isLikelyRepoPath(normalizedReference)) {
      continue;
    }

    references.push(normalizedReference);
  }

  return references;
}

function extractPathReferences(relativeFilePath, content) {
  const references = [];
  const lines = content.split(/\r?\n/u);
  let inFence = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\s*(```|~~~)/u.test(line)) {
      inFence = !inFence;
      continue;
    }

    if (inFence) {
      continue;
    }

    const lineNumber = index + 1;
    for (const value of extractMarkdownLinks(line)) {
      references.push({ value, line: lineNumber, lineText: line, kind: "link" });
    }
    for (const value of extractInlineCodeReferences(line)) {
      references.push({ value, line: lineNumber, lineText: line, kind: "inline_code" });
    }
  }

  return references.map((reference) => ({
    ...reference,
    source: relativeFilePath,
  }));
}

function validateDocumentation(rootDir) {
  const errors = [];
  const docFiles = listDocumentationFiles(rootDir);
  let checkedReferences = 0;

  for (const relativeDir of FORBIDDEN_DOC_DIRECTORIES) {
    const absoluteDir = path.join(rootDir, relativeDir);
    if (!fs.existsSync(absoluteDir)) {
      continue;
    }

    const entries = fs.readdirSync(absoluteDir);
    if (entries.length > 0) {
      errors.push(`${relativeDir} should not exist; move archived docs to the repository root archive/`);
    }
  }

  for (const relativePath of FORBIDDEN_DOC_FILES) {
    if (fs.existsSync(path.join(rootDir, relativePath))) {
      errors.push(`${relativePath} should not exist; docs/README.md is the only documentation index`);
    }
  }

  for (const relativeFilePath of docFiles) {
    const absoluteFilePath = path.join(rootDir, relativeFilePath);
    const content = fs.readFileSync(absoluteFilePath, "utf8");
    const references = extractPathReferences(relativeFilePath, content);

    checkedReferences += references.length;

    for (const reference of references) {
      if (
        ALLOWED_MISSING_REFERENCE_EXAMPLES.has(reference.value) &&
        ALLOWED_MISSING_REFERENCE_LINE_HINT.test(reference.lineText)
      ) {
        continue;
      }

      if (
        IGNORED_RUNTIME_REFERENCE_PREFIXES.some((prefix) => reference.value.startsWith(prefix))
      ) {
        continue;
      }

      const candidateTargets = [];
      if (reference.value.startsWith("./") || reference.value.startsWith("../")) {
        candidateTargets.push(path.resolve(path.dirname(absoluteFilePath), reference.value));
      } else {
        candidateTargets.push(path.resolve(path.dirname(absoluteFilePath), reference.value));
        candidateTargets.push(path.resolve(rootDir, reference.value));
      }

      if (!candidateTargets.some((candidatePath) => fs.existsSync(candidatePath))) {
        errors.push(
          `${reference.source}:${reference.line} references missing path \`${reference.value}\``
        );
      }
    }
  }

  return {
    checkedFiles: docFiles.length,
    checkedReferences,
    errors,
  };
}

module.exports = {
  extractPathReferences,
  isLikelyRepoPath,
  listDocumentationFiles,
  normalizeReferenceToken,
  validateDocumentation,
};
