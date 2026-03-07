import { readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();
const outDir = path.join(root, 'out');

async function readPage(relativePath) {
  return readFile(path.join(outDir, relativePath), 'utf8');
}

function assertIncludes(html, expected, label) {
  if (!html.includes(expected)) {
    throw new Error(`Missing ${label}: ${expected}`);
  }
}

async function main() {
  const home = await readPage(path.join('index.html'));
  assertIncludes(home, '把你的星标像产品一样整理。', 'home title');
  assertIncludes(home, 'href="/settings/"', 'home settings link');
  assertIncludes(home, 'href="/admin/"', 'home admin link');
  assertIncludes(home, '标签云', 'home tag cloud');

  const admin = await readPage(path.join('admin', 'index.html'));
  assertIncludes(admin, '管理后台', 'admin title');
  assertIncludes(admin, 'placeholder="ADMIN_TOKEN"', 'admin token input');
  assertIncludes(admin, '登录', 'admin login button');

  const settings = await readPage(path.join('settings', 'index.html'));
  assertIncludes(settings, '设置概览', 'settings title');
  assertIncludes(settings, '前往管理', 'settings admin link');
  assertIncludes(settings, '加载设置中...', 'settings loading state');

  console.log('Static smoke checks passed');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
