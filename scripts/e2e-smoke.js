#!/usr/bin/env node
const assert = require("node:assert/strict");
const { existsSync, mkdtempSync, rmSync } = require("node:fs");
const path = require("node:path");
const { tmpdir } = require("node:os");
const { spawn, spawnSync } = require("node:child_process");

const {
  evaluatePythonCandidates,
  findUsablePython,
} = require("./lib/python-runner");

const root = path.resolve(__dirname, "..");
const apiDir = path.join(root, "api");
const webDir = path.join(root, "web");
const repoFullName = "alice/e2e-smoke";
const apiPort = Number.parseInt(process.env.E2E_API_PORT || "54321", 10);
const webPort = Number.parseInt(process.env.E2E_WEB_PORT || "54322", 10);
if (!Number.isInteger(apiPort) || !Number.isInteger(webPort)) {
  throw new Error("E2E_API_PORT and E2E_WEB_PORT must be integers");
}
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const repoPath = `/repo/${repoFullName.split("/").map(encodeURIComponent).join("/")}`;

function sqliteUrl(dbPath) {
  const absolute = path.resolve(dbPath).replace(/\\/g, "/");
  if (absolute.startsWith("/")) {
    return `sqlite:////${absolute.slice(1)}`;
  }
  return `sqlite:///${absolute}`;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForServer(url, child, name, timeoutMs = 30000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (child.exitCode !== null) {
      throw new Error(`${name} exited before it became ready`);
    }
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) {
        return;
      }
    } catch {}
    await delay(300);
  }
  throw new Error(`Timed out waiting for ${name} at ${url}`);
}

async function fetchHtml(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed for ${url}: ${response.status}`);
  }
  return response.text();
}

function spawnLogged(name, command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || root,
    env: options.env || process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const logs = [];
  const collect = (stream, prefix) => {
    stream.on("data", (chunk) => {
      logs.push(`${prefix}${String(chunk)}`);
    });
  };
  collect(child.stdout, `[${name}:out] `);
  collect(child.stderr, `[${name}:err] `);
  return { child, logs, name };
}

async function waitForExit(child) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  await new Promise((resolve) => child.once("exit", resolve));
}

function runSeed(pythonCommand, dbPath) {
  const seedScript = `
import asyncio
import json
import os
from pathlib import Path

import aiosqlite

from api.app.db import schema as schema_db
from api.app.config import clear_settings_cache

db_path = Path(${JSON.stringify(dbPath)})

row = {
    "full_name": "alice/e2e-smoke",
    "name": "e2e-smoke",
    "owner": "alice",
    "html_url": "https://example.com/alice/e2e-smoke",
    "description": "end to end smoke target",
    "language": "TypeScript",
    "stargazers_count": 128,
    "forks_count": 2,
    "topics": json.dumps(["smoke", "journey"]),
    "pushed_at": "2026-03-01T00:00:00+00:00",
    "updated_at": "2026-03-01T00:00:00+00:00",
    "starred_at": "2026-03-01T00:00:00+00:00",
    "star_users": json.dumps(["tester"]),
    "category": "Discovery",
    "subcategory": "Seed",
    "ai_confidence": 0.91,
    "ai_tags": json.dumps(["Agent"]),
    "ai_tag_ids": json.dumps(["ai.agent"]),
    "ai_provider": "openai",
    "ai_model": "gpt-4.1-mini",
    "ai_reason": "seeded smoke fixture",
    "ai_decision_source": "seed",
    "ai_rule_candidates": json.dumps([]),
    "ai_updated_at": "2026-03-01T00:00:00+00:00",
    "override_category": None,
    "override_subcategory": None,
    "override_tags": None,
    "override_tag_ids": None,
    "override_note": None,
    "readme_summary": "end to end smoke target",
    "readme_fetched_at": "2026-03-01T00:00:00+00:00",
    "readme_last_attempt_at": "2026-03-01T00:00:00+00:00",
    "readme_failures": 0,
    "readme_empty": 0,
}


async def main():
    clear_settings_cache()
    await schema_db.init_db()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            """
            INSERT INTO repos (
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users, category, subcategory, ai_confidence, ai_tags, ai_tag_ids,
                ai_provider, ai_model, ai_reason, ai_decision_source, ai_rule_candidates,
                ai_updated_at, override_category, override_subcategory, override_tags,
                override_tag_ids, override_note, readme_summary, readme_fetched_at,
                readme_last_attempt_at, readme_failures, readme_empty
            ) VALUES (
                :full_name, :name, :owner, :html_url, :description, :language,
                :stargazers_count, :forks_count, :topics, :pushed_at, :updated_at, :starred_at,
                :star_users, :category, :subcategory, :ai_confidence, :ai_tags, :ai_tag_ids,
                :ai_provider, :ai_model, :ai_reason, :ai_decision_source, :ai_rule_candidates,
                :ai_updated_at, :override_category, :override_subcategory, :override_tags,
                :override_tag_ids, :override_note, :readme_summary, :readme_fetched_at,
                :readme_last_attempt_at, :readme_failures, :readme_empty
            )
            """,
            row,
        )
        await conn.commit()

asyncio.run(main())
`;

  const result = spawnSync(pythonCommand, ["-c", seedScript], {
    cwd: root,
    env: {
      ...process.env,
      DATABASE_URL: sqliteUrl(dbPath),
    },
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 120000,
  });

  if (result.status !== 0) {
    const stderr = String(result.stderr || "").trim();
    const stdout = String(result.stdout || "").trim();
    throw new Error(
      [
        "Failed to seed smoke database.",
        stdout ? `stdout: ${stdout}` : null,
        stderr ? `stderr: ${stderr}` : null,
      ]
        .filter(Boolean)
        .join("\n")
    );
  }
}

async function main() {
  if (
    (spawnSync("npm", ["run", "web:build"], {
      cwd: root,
      stdio: "inherit",
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: apiUrl,
      },
    }).status ?? 1) !== 0
  ) {
    throw new Error("web build failed");
  }

  const dbDir = mkdtempSync(path.join(tmpdir(), "starsorty-e2e-"));
  const dbPath = path.join(dbDir, "smoke.db");

  const pythonReports = evaluatePythonCandidates(root, ["aiosqlite", "fastapi", "yaml"]);
  const python = findUsablePython(pythonReports);
  if (!python) {
    throw new Error("No usable Python found for the smoke test");
  }

  const env = {
    ...process.env,
    DATABASE_URL: sqliteUrl(dbPath),
    ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV: "1",
    API_BASE_URL: apiUrl,
    NEXT_PUBLIC_API_BASE_URL: apiUrl,
    HOSTNAME: "127.0.0.1",
    PORT: String(webPort),
  };

  runSeed(python.command, dbPath);

  let api = null;
  let web = null;

  try {
    const standaloneServerPath = path.join(webDir, ".next", "standalone", "server.js");
    const webCommand = existsSync(standaloneServerPath)
      ? { command: process.execPath, args: [standaloneServerPath] }
      : {
          command: path.join(
            webDir,
            "node_modules",
            ".bin",
            process.platform === "win32" ? "next.cmd" : "next"
          ),
          args: ["start", "-H", "127.0.0.1", "-p", String(webPort)],
        };

    api = spawnLogged(
      "api",
      python.command,
      [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(apiPort),
      ],
      {
        cwd: apiDir,
        env,
      }
    );
    web = spawnLogged("web", webCommand.command, webCommand.args, {
      cwd: webDir,
      env,
    });

    await waitForServer(`${apiUrl}/health`, api.child, "API");
    await waitForServer(webUrl, web.child, "Web");

    const searchBefore = await fetch(`${apiUrl}/repos?q=smoke`, { cache: "no-store" });
    assert.equal(searchBefore.ok, true);
    const searchBeforeJson = await searchBefore.json();
    assert.equal(searchBeforeJson.total, 1);
    assert.equal(searchBeforeJson.items[0].full_name, repoFullName);

    const detailBefore = await fetchHtml(`${webUrl}${repoPath}`);
    assert.match(detailBefore, /alice\/e2e-smoke/);
    assert.match(detailBefore, /Discovery/);
    assert.match(detailBefore, /Seed/);
    assert.match(detailBefore, /end to end smoke target/);

    const overrideResponse = await fetch(`${apiUrl}/repos/${encodeURIComponent(repoFullName)}/override`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        category: "Review",
        subcategory: "Tuning",
        tag_ids: ["llm"],
        note: "e2e smoke override",
      }),
    });
    assert.equal(overrideResponse.ok, true);

    const overrideHistory = await fetch(`${apiUrl}/repos/${encodeURIComponent(repoFullName)}/overrides`, {
      cache: "no-store",
    });
    assert.equal(overrideHistory.ok, true);
    const overrideHistoryJson = await overrideHistory.json();
    assert.equal(overrideHistoryJson.items.length > 0, true);
    assert.equal(overrideHistoryJson.items[0].category, "Review");
    assert.equal(overrideHistoryJson.items[0].subcategory, "Tuning");
    assert.deepEqual(overrideHistoryJson.items[0].tags, ["LLM"]);
    assert.equal(overrideHistoryJson.items[0].note, "e2e smoke override");

    const tagSearch = await fetch(`${apiUrl}/repos?tag=llm`, { cache: "no-store" });
    assert.equal(tagSearch.ok, true);
    const tagSearchJson = await tagSearch.json();
    assert.equal(tagSearchJson.total, 1);
    assert.equal(tagSearchJson.items[0].full_name, repoFullName);

    const detailAfter = await fetchHtml(`${webUrl}${repoPath}`);
    assert.match(detailAfter, /Review/);
    assert.match(detailAfter, /Tuning/);
    assert.match(detailAfter, /e2e smoke override/);
    assert.match(detailAfter, /LLM/);

    console.log("E2E smoke checks passed");
  } catch (error) {
    if (web?.logs?.length) {
      console.error(web.logs.join("").trim());
    }
    if (api?.logs?.length) {
      console.error(api.logs.join("").trim());
    }
    throw error;
  } finally {
    for (const proc of [web?.child, api?.child].filter(Boolean)) {
      if (proc.exitCode === null) {
        proc.kill("SIGTERM");
      }
    }
    const exitWaits = [];
    if (web?.child) {
      exitWaits.push(waitForExit(web.child));
    }
    if (api?.child) {
      exitWaits.push(waitForExit(api.child));
    }
    await Promise.all(exitWaits);
    rmSync(dbDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
