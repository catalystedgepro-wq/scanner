import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.join(__dirname, 'docs', 'hud');
const outputDir = path.join(__dirname, 'output', 'playwright');
const outputPath = path.join(outputDir, 'hud-visual-audit.png');
const port = 4173;
const upstreamOrigin = 'http://67.205.148.181';

fs.mkdirSync(outputDir, { recursive: true });

const mimeByExt = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${port}`);
  if (url.pathname.startsWith('/api/')) {
    try {
      const upstream = await fetch(`${upstreamOrigin}${url.pathname}${url.search}`, {
        method: req.method || 'GET',
        headers: {
          accept: req.headers.accept || '*/*',
        },
      });
      res.writeHead(upstream.status, Object.fromEntries(upstream.headers.entries()));
      const body = Buffer.from(await upstream.arrayBuffer());
      res.end(body);
      return;
    } catch (error) {
      res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: String(error) }));
      return;
    }
  }

  if (url.pathname.startsWith('/ws/')) {
    res.writeHead(204);
    res.end();
    return;
  }

  let requestPath = decodeURIComponent(url.pathname);
  if (requestPath === '/') {
    requestPath = '/index.html';
  }
  const filePath = path.join(rootDir, requestPath);
  const normalized = path.normalize(filePath);
  if (!normalized.startsWith(rootDir)) {
    res.writeHead(403);
    res.end('forbidden');
    return;
  }

  let finalPath = normalized;
  if (!fs.existsSync(finalPath) || fs.statSync(finalPath).isDirectory()) {
    finalPath = path.join(rootDir, 'index.html');
  }

  try {
    const ext = path.extname(finalPath).toLowerCase();
    const content = fs.readFileSync(finalPath);
    res.writeHead(200, {
      'content-type': mimeByExt[ext] || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    res.end(content);
  } catch (error) {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end(String(error));
  }
});

await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, colorScheme: 'dark' });
  const consoleMessages = [];
  page.on('console', (msg) => {
    consoleMessages.push(`${msg.type()}: ${msg.text()}`);
  });
  await page.goto(`http://127.0.0.1:${port}`, { waitUntil: 'domcontentloaded' });
  const launchButton = page.getByRole('button', { name: /launch hud/i });
  if (await launchButton.count()) {
    await launchButton.click();
  }
  await page.waitForTimeout(9000);
  await page.screenshot({ path: outputPath, fullPage: false });
  const markers = await page.evaluate(() => {
    const bodyText = document.body?.innerText || '';
    return {
      hasVelocityDeck: bodyText.toLowerCase().includes('velocity'),
      hasReset: bodyText.toLowerCase().includes('reset'),
      hasCommand: bodyText.toLowerCase().includes('command'),
    };
  });
  console.log(JSON.stringify({ outputPath, consoleMessages, markers }, null, 2));
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
