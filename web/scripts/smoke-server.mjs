import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

const root = process.cwd();
const buildDir = path.join(root, ".next");
const routesManifestPath = path.join(buildDir, "routes-manifest.json");
const nextBinary =
  process.platform === "win32"
    ? path.join(root, "node_modules", ".bin", "next.cmd")
    : path.join(root, "node_modules", ".bin", "next");

function assertIncludes(html, expected, label) {
  if (!html.includes(expected)) {
    throw new Error(`Missing ${label}: ${expected}`);
  }
}

async function waitForServer(url, timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // Keep polling until the server is ready.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function fetchHtml(pathname) {
  const response = await fetch(`http://127.0.0.1:1234${pathname}`);
  if (!response.ok) {
    throw new Error(`Request failed for ${pathname}: ${response.status}`);
  }
  return response.text();
}

async function stopServer(server) {
  if (server.exitCode !== null) {
    return server.exitCode;
  }
  server.kill("SIGTERM");
  return new Promise((resolve) => server.once("exit", resolve));
}

async function main() {
  const routesManifest = JSON.parse(await readFile(routesManifestPath, "utf8"));
  const hasDynamicRepoRoute = (routesManifest.dynamicRoutes || []).some(
    (route) => route.page === "/repo/[...fullName]"
  );
  if (!hasDynamicRepoRoute) {
    throw new Error("Missing dynamic repo detail route in routes manifest");
  }

  const server = spawn(nextBinary, ["start", "-H", "127.0.0.1", "-p", "1234"], {
    cwd: root,
    env: {
      ...process.env,
      API_BASE_URL: process.env.API_BASE_URL || "http://127.0.0.1:4321",
    },
    stdio: "pipe",
  });

  const serverLogs = [];
  const collectLogs = (stream) => {
    stream.on("data", (chunk) => {
      serverLogs.push(String(chunk));
    });
  };
  collectLogs(server.stdout);
  collectLogs(server.stderr);

  try {
    await waitForServer("http://127.0.0.1:1234/");

    const home = await fetchHtml("/");
    assertIncludes(home, "把你的星标像产品一样整理。", "home title");
    assertIncludes(home, 'href="/settings/"', "home settings link");
    assertIncludes(home, 'href="/admin/"', "home admin link");
    assertIncludes(home, "标签云", "home tag cloud");

    const admin = await fetchHtml("/admin/");
    assertIncludes(admin, "管理后台", "admin title");
    assertIncludes(admin, 'placeholder="ADMIN_TOKEN"', "admin token input");
    assertIncludes(admin, "登录", "admin login button");

    const settings = await fetchHtml("/settings/");
    assertIncludes(settings, "设置概览", "settings title");
    assertIncludes(settings, "前往管理", "settings admin link");
    assertIncludes(settings, "加载设置中...", "settings loading state");

    console.log("Server smoke checks passed");
  } finally {
    const exitCode = await stopServer(server);
    if (exitCode && exitCode !== 0 && serverLogs.length > 0) {
      console.error(serverLogs.join("").trim());
    }
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
