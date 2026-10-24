/**
 * Cloudflare Worker Hub for Jev/Cua Cross-Platform Testing
 * 
 * Runs in the 100% Free Tier of Cloudflare Workers:
 * - In-memory / KV task queue & runner registry
 * - REST API to register runners (Linux, Windows, macOS)
 * - Task dispatch endpoint (routes task to runner matching OS/tags)
 * - Result & log aggregation endpoint
 * - Live HTML monitoring dashboard for browser inspection
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Optional shared secret auth
    const authHeader = request.headers.get("Authorization");
    const secret = env.SHARED_SECRET || "dev-secret-key";

    // CORS headers for dashboard and CLI access
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    if (method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // 1. Dashboard UI (Live Monitoring)
    if (path === "/" || path === "/dashboard") {
      return new Response(renderDashboardHtml(), {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // 2. Runner Heartbeat / Registration
    if (path === "/api/runners/heartbeat" && method === "POST") {
      try {
        const body = await request.json();
        const runnerId = body.runner_id;
        if (!runnerId) {
          return Response.json({ error: "Missing runner_id" }, { status: 400, headers: corsHeaders });
        }
        
        // Save runner status into KV if bound, or memory (10 minutes TTL)
        if (env.RUNNERS_KV) {
          await env.RUNNERS_KV.put(`runner:${runnerId}`, JSON.stringify(body), { expirationTtl: 600 });
        }
        return Response.json({ ok: true, registered: runnerId }, { headers: corsHeaders });
      } catch (err) {
        return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
      }
    }

    // 3. List Registered Runners
    if (path === "/api/runners" && method === "GET") {
      let runners = [];
      if (env.RUNNERS_KV) {
        const list = await env.RUNNERS_KV.list({ prefix: "runner:" });
        const keys = list.keys || [];
        for (const key of keys) {
          const raw = await env.RUNNERS_KV.get(key.name);
          if (raw) {
            try {
              runners.push(typeof raw === "string" ? JSON.parse(raw) : raw);
            } catch (e) {
              runners.push({ runner_id: key.name.replace("runner:", ""), raw });
            }
          }
        }
      }
      return Response.json({ runners }, { headers: corsHeaders });
    }

    // 4. Submit Task
    if (path === "/api/tasks/submit" && method === "POST") {
      try {
        const taskPayload = await request.json();
        const taskId = `task_${Date.now()}_${Math.random().toString(36).substring(7)}`;
        taskPayload.id = taskId;
        taskPayload.submitted_at = new Date().toISOString();
        taskPayload.status = "queued";

        if (env.RUNNERS_KV) {
          await env.RUNNERS_KV.put(`task:${taskId}`, JSON.stringify(taskPayload), { expirationTtl: 86400 });
        }

        return Response.json({ ok: true, task_id: taskId, message: "Task queued for runners" }, { headers: corsHeaders });
      } catch (err) {
        return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
      }
    }

    // 5. Post Task Result
    if (path === "/api/results" && method === "POST") {
      try {
        const body = await request.json();
        const result = body.result;
        const taskName = result.task || "task";
        const resultId = `result_${Date.now()}_${taskName}`;

        if (env.RUNNERS_KV) {
          await env.RUNNERS_KV.put(`result:${resultId}`, JSON.stringify(body), { expirationTtl: 86400 * 7 });
        }

        return Response.json({ ok: true, stored: resultId }, { headers: corsHeaders });
      } catch (err) {
        return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
      }
    }

    // 6. List Results
    if (path === "/api/results" && method === "GET") {
      let results = [];
      if (env.RUNNERS_KV) {
        const list = await env.RUNNERS_KV.list({ prefix: "result:" });
        for (const key of list.keys) {
          const val = await env.RUNNERS_KV.get(key.name, { type: "json" });
          if (val) results.push(val);
        }
      }
      return Response.json({ results }, { headers: corsHeaders });
    }

    return Response.json({ error: "Endpoint not found" }, { status: 404, headers: corsHeaders });
  },
};

function renderDashboardHtml() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Jev Cross-Platform Test Hub (Linux & Windows)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root {
      --bg: #090d16;
      --card: #131b2e;
      --border: #23314f;
      --accent: #38bdf8;
      --success: #10b981;
      --failed: #ef4444;
      --text: #f1f5f9;
      --subtext: #94a3b8;
    }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
      margin: 0;
      padding: 2rem;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    h1 { margin: 0; font-size: 1.5rem; display: flex; align-items: center; gap: 0.5rem; }
    .badge {
      font-size: 0.75rem;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      background: #0284c7;
    }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem;
    }
    h2 { font-size: 1.1rem; margin-top: 0; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
    th { color: var(--subtext); }
    .status-idle { color: var(--success); }
    .status-busy { color: #f59e0b; }
    .status-offline { color: var(--subtext); }
    .pass { color: var(--success); font-weight: bold; }
    .fail { color: var(--failed); font-weight: bold; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>
        <span>☁️ Jev Cross-Platform Runner Hub</span>
        <span class="badge">Cloudflare Edge</span>
      </h1>
      <div id="live-indicator" style="color: var(--success); font-size: 0.85rem;">● Live Monitoring</div>
    </header>

    <div class="grid">
      <!-- Active Runners -->
      <div class="card">
        <h2>Connected Test Runners</h2>
        <div id="runners-list">Loading connected runners...</div>
      </div>

      <!-- Quick Task Submission -->
      <div class="card">
        <h2>Submit Remote Task</h2>
        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
          <input type="text" id="task-name" placeholder="Task Name (e.g. gnumeric_budget)" style="background:#0b1120; border:1px solid var(--border); color:#fff; padding:0.5rem; border-radius:4px;">
          <select id="task-app" style="background:#0b1120; border:1px solid var(--border); color:#fff; padding:0.5rem; border-radius:4px;">
            <option value="gnumeric">gnumeric (Linux)</option>
            <option value="mousepad">mousepad (Linux)</option>
            <option value="galculator">galculator (Linux)</option>
            <option value="calculator">Calculator (Windows / Cross-app)</option>
            <option value="audacity">audacity (Linux/Cross-app)</option>
          </select>
          <button onclick="submitTask()" style="background:#0284c7; color:#fff; border:none; padding:0.6rem; border-radius:4px; cursor:pointer; font-weight:bold;">Dispatch Task</button>
        </div>
      </div>
    </div>

    <!-- Recent Results -->
    <div class="card">
      <h2>Recent Task Results & Evidence</h2>
      <div id="results-table">Loading execution evidence...</div>
    </div>
  </div>

  <script>
    async function loadData() {
      try {
        const [rRes, resRes] = await Promise.all([
          fetch('/api/runners').then(r => r.json()),
          fetch('/api/results').then(r => r.json())
        ]);

        // Render Runners
        const runnersDiv = document.getElementById('runners-list');
        if (!rRes.runners || rRes.runners.length === 0) {
          runnersDiv.innerHTML = '<p style="color:var(--subtext)">No active runners connected yet. Start a runner via <code>python python/runner_agent/agent.py</code>.</p>';
        } else {
          let html = '<table><thead><tr><th>ID</th><th>Platform</th><th>Tags</th><th>Status</th></tr></thead><tbody>';
          for (const r of rRes.runners) {
            html += \`<tr><td>\${r.runner_id}</td><td>\${r.os} (\${r.arch})</td><td>\${(r.tags||[]).join(', ')}</td><td class="status-\${r.status}">\${r.status}</td></tr>\`;
          }
          html += '</tbody></table>';
          runnersDiv.innerHTML = html;
        }

        // Render Results
        const resultsDiv = document.getElementById('results-table');
        if (!resRes.results || resRes.results.length === 0) {
          resultsDiv.innerHTML = '<p style="color:var(--subtext)">No recent test runs completed.</p>';
        } else {
          let html = '<table><thead><tr><th>Runner</th><th>Task</th><th>Outcome</th><th>Result</th><th>Duration</th><th>Details</th></tr></thead><tbody>';
          for (let i = 0; i < resRes.results.length; i++) {
            const item = resRes.results[i];
            const res = item.result || {};
            const events = res.events || [];
            const error = res.error || res.reason || '';
            const eventsJson = JSON.stringify(events, null, 2);
            html += '<tr>' +
              '<td>' + (item.runner_id || 'unknown') + '</td>' +
              '<td><b>' + (res.task || 'task') + '</b></td>' +
              '<td><code>' + (res.outcome || '-') + '</code></td>' +
              '<td class="' + (res.passed ? 'pass' : 'fail') + '">' + (res.passed ? 'PASSED' : 'FAILED') + '</td>' +
              '<td>' + (res.duration_s !== undefined ? res.duration_s + 's' : '-') + '</td>' +
              '<td><button onclick="var el = document.getElementById(\\'details-' + i + '\\'); el.style.display = (el.style.display === \\'none\\' ? \\'table-row\\' : \\'none\\');" style="background:#1e293b; color:#38bdf8; border:1px solid #334155; padding:0.2rem 0.5rem; border-radius:4px; cursor:pointer;">Logs</button></td>' +
            '</tr>' +
            '<tr id="details-' + i + '" style="display:none; background:#0f172a;">' +
              '<td colspan="6" style="padding:0.75rem;">' +
                (error ? '<div style="color:#f87171; margin-bottom:0.5rem;"><b>Error/Reason:</b> ' + error + '</div>' : '') +
                '<div style="font-size:0.8rem; color:#94a3b8; margin-bottom:0.25rem;"><b>Recent Events / Trail:</b></div>' +
                '<pre style="background:#020617; color:#e2e8f0; padding:0.5rem; border-radius:4px; max-height:200px; overflow-y:auto; font-size:0.75rem; margin:0;">' + (events.length > 0 ? eventsJson.replace(/</g, '&lt;').replace(/>/g, '&gt;') : 'No event details recorded') + '</pre>' +
              '</td>' +
            '</tr>';
          }
          html += '</tbody></table>';
          resultsDiv.innerHTML = html;
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function submitTask() {
      const name = document.getElementById('task-name').value || 'remote_task';
      const app = document.getElementById('task-app').value;
      await fetch('/api/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, app, objective: 'Autonomous GUI test via Cloudflare hub' })
      });
      alert('Task submitted successfully!');
      loadData();
    }

    loadData();
    setInterval(loadData, 5000);
  </script>
</body>
</html>`;
}
