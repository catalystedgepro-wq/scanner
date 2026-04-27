import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';

const port = Number(process.env.PLAYWRIGHT_STATIC_PORT || 4173);
const root = resolve('.');

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.webp': 'image/webp',
};

const send = (res, status, body, contentType = 'text/plain; charset=utf-8') => {
  res.writeHead(status, { 'Content-Type': contentType });
  res.end(body);
};

const toFilePath = (urlPath) => {
  const cleanPath = decodeURIComponent((urlPath || '/').split('?')[0]);
  const normalized = normalize(cleanPath).replace(/^(\.\.[/\\])+/, '');
  const candidate = normalized === '/'
    ? '/docs/index.html'
    : normalized.startsWith('/assets/')
      ? `/docs/hud${normalized}`
      : normalized;
  const filePath = resolve(join(root, candidate));
  if (!filePath.startsWith(root)) {
    return null;
  }
  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    const indexPath = resolve(join(filePath, 'index.html'));
    return existsSync(indexPath) ? indexPath : null;
  }
  return existsSync(filePath) ? filePath : null;
};

const server = createServer((req, res) => {
  const filePath = toFilePath(req.url || '/');
  if (!filePath) {
    send(res, 404, 'Not Found');
    return;
  }

  const ext = extname(filePath).toLowerCase();
  res.writeHead(200, {
    'Cache-Control': 'no-store',
    'Content-Type': contentTypes[ext] || 'application/octet-stream',
  });
  createReadStream(filePath).pipe(res);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`Playwright static server running at http://127.0.0.1:${port}`);
});
