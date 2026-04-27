import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
// Attach CDP session BEFORE navigation
const client = await page.context().newCDPSession(page);
await client.send('DOM.enable');
await client.send('CSS.enable');

await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);

// Find node IDs using CDP
const { root } = await client.send('DOM.getDocument', { depth: -1 });

// Walk tree to find .ts-card.ts-active
function findNode(node, pred) {
  if (pred(node)) return node;
  for (const c of node.children || []) {
    const f = findNode(c, pred);
    if (f) return f;
  }
  return null;
}
const isActiveCard = n => n.nodeName === 'A' && (n.attributes || []).join(' ').includes('ts-card ts-active');
const isHeadline = n => n.nodeName === 'SPAN' && (n.attributes || []).join(' ').includes('ts-headline');
const isStrip = n => n.nodeName === 'SECTION' && (n.attributes || []).join(' ').includes('tactical-strip');

const stripNode = findNode(root, isStrip);
const cardNode = findNode(root, isActiveCard);
const headlineNode = findNode(root, isHeadline);

console.log('Found nodes:', { strip: !!stripNode, card: !!cardNode, headline: !!headlineNode });

if (headlineNode) {
  const { matchedCSSRules, inlineStyle, pseudoElements } = await client.send(
    'CSS.getMatchedStylesForNode',
    { nodeId: headlineNode.nodeId }
  );
  console.log('\n=== .ts-headline matched rules ===');
  for (const m of matchedCSSRules || []) {
    const r = m.rule;
    const selector = r.selectorList?.text || '';
    const props = (r.style?.cssProperties || [])
      .filter(p => !p.implicit)
      .map(p => `${p.name}: ${p.value}`)
      .join('; ');
    console.log(`  { ${selector} } ${props}`);
  }
}

if (cardNode) {
  const { matchedCSSRules } = await client.send(
    'CSS.getMatchedStylesForNode',
    { nodeId: cardNode.nodeId }
  );
  console.log('\n=== .ts-card.ts-active matched rules ===');
  for (const m of matchedCSSRules || []) {
    const r = m.rule;
    const selector = r.selectorList?.text || '';
    const props = (r.style?.cssProperties || [])
      .filter(p => !p.implicit)
      .map(p => `${p.name}: ${p.value}`)
      .join('; ');
    console.log(`  { ${selector} } ${props}`);
  }
}

if (stripNode) {
  const { matchedCSSRules, pseudoElements } = await client.send(
    'CSS.getMatchedStylesForNode',
    { nodeId: stripNode.nodeId }
  );
  console.log('\n=== .tactical-strip matched rules ===');
  for (const m of matchedCSSRules || []) {
    const r = m.rule;
    const selector = r.selectorList?.text || '';
    const props = (r.style?.cssProperties || [])
      .filter(p => !p.implicit)
      .map(p => `${p.name}: ${p.value}`)
      .join('; ');
    console.log(`  { ${selector} } ${props}`);
  }
  console.log('\n=== pseudo-elements ===');
  for (const pe of pseudoElements || []) {
    console.log(`-- ${pe.pseudoType} --`);
    for (const m of pe.matches || []) {
      const r = m.rule;
      const selector = r.selectorList?.text || '';
      const props = (r.style?.cssProperties || [])
        .filter(p => !p.implicit)
        .map(p => `${p.name}: ${p.value}`)
        .join('; ');
      console.log(`  { ${selector} } ${props}`);
    }
  }
}

await browser.close();
