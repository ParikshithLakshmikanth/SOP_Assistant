const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const OUTPUT_DIR = path.resolve('docs/screenshots');
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const VIEWS = [
  {
    name: 'dashboard.png',
    url: 'http://127.0.0.1:8501/?mode=dashboard',
    waitMs: 5000,
    desc: 'Executive Dashboard and Live System Telemetry'
  },
  {
    name: 'chatbot.png',
    url: 'http://127.0.0.1:8501/?mode=chat',
    waitMs: 5000,
    desc: 'Technical Consultation Chatbot with Traceable Evidence Citations'
  },
  {
    name: 'component_explorer.png',
    url: 'http://127.0.0.1:8501/?mode=explorer',
    waitMs: 5000,
    desc: 'Visual and Tabular Component Explorer with Multi-Level Filters'
  },
  {
    name: 'component_detail.png',
    url: 'http://127.0.0.1:8501/?mode=explorer&comp=Turret+Base+Ring',
    waitMs: 5000,
    desc: 'Component Detail Inspector with Verified Relationships and SOP Evidence'
  },
  {
    name: 'revision_comparison.png',
    url: 'http://127.0.0.1:8501/?mode=compare',
    waitMs: 5000,
    desc: 'SOP Revision Comparison Engine showing Structural and Tolerance Diffs'
  },
  {
    name: 'upload_workflow.png',
    url: 'http://127.0.0.1:8501/?mode=upload',
    waitMs: 5000,
    desc: 'Transactional 7-Stage SOP Ingestion and Verification Interface'
  },
  {
    name: 'system_health.png',
    url: 'http://127.0.0.1:8501/?mode=dashboard',
    waitMs: 5000,
    desc: 'Detailed Subsystem Diagnostics and Air-Gap Status'
  }
];

async function captureAll() {
  const port = 9888;
  console.log('='.repeat(70));
  console.log('HVF / AVNL SOP Assistant - High-Fidelity UI Screenshot Generator');
  console.log('='.repeat(70));
  console.log(`Starting isolated Chrome on remote port ${port}...`);

  const p = spawn(CHROME, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    '--disable-gpu',
    '--no-sandbox',
    '--window-size=1440,900'
  ], { stdio: 'ignore' });

  try {
    let targets = null;
    for (let i = 0; i < 20; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${port}/json`);
        targets = await res.json();
        if (targets && targets.find(t => t.type === 'page')) break;
      } catch (e) {
        await new Promise(r => setTimeout(r, 200));
      }
    }

    const pageTarget = targets.find(t => t.type === 'page');
    if (!pageTarget) throw new Error('Could not find active browser page target.');

    console.log(`Attached to target: "${pageTarget.title}"`);
    console.log(`WebSocket URL: ${pageTarget.webSocketDebuggerUrl}\n`);

    const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });

    let id = 1;
    function send(method, params = {}) {
      const cur = id++;
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          ws.removeEventListener('message', handler);
          reject(new Error(`Timeout executing ${method}`));
        }, 15000);

        function handler(evt) {
          try {
            const d = JSON.parse(evt.data);
            if (d.id === cur) {
              clearTimeout(timeout);
              ws.removeEventListener('message', handler);
              if (d.error) reject(d.error);
              else resolve(d.result);
            }
          } catch (err) {}
        }
        ws.addEventListener('message', handler);
        ws.send(JSON.stringify({ id: cur, method, params }));
      });
    }

    await send('Page.enable');

    for (const view of VIEWS) {
      console.log(`>>> Capturing: ${view.name}`);
      console.log(`    URL: ${view.url}`);
      console.log(`    Role: ${view.desc}`);

      await send('Page.navigate', { url: view.url });
      await new Promise(r => setTimeout(r, view.waitMs));

      const res = await send('Page.captureScreenshot', { format: 'png' });
      const buf = Buffer.from(res.data, 'base64');
      const targetPath = path.join(OUTPUT_DIR, view.name);
      fs.writeFileSync(targetPath, buf);
      console.log(`    Saved: ${targetPath} (${buf.length} bytes)\n`);
    }

    ws.close();
    console.log('All screenshots captured successfully.');
  } finally {
    p.kill();
  }
}

captureAll().catch(err => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});

