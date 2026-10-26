/**
 * API client for SentinelGraph. Every call goes through `req`, which
 * normalises errors into thrown Error objects carrying the server's message.
 */

async function req(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error(
      `Cannot reach the SentinelGraph API. Is the backend running? ` +
        `Start it with: python sg.py serve   (${e.message})`
    );
  }
  const text = await res.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new Error(`Malformed response from ${path}: ${text.slice(0, 200)}`);
    }
  }
  if (!res.ok) {
    const msg = (body && (body.error || body.message)) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return body;
}

export const get = (path) => req(path, { method: "GET" });

export const post = (path, payload) =>
  req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });

export const health = () => get("/api/health");
export const ingest = (payload) => post("/api/ingest", payload);
export const investigate = (payload) => post("/api/investigate", payload);
export const verify = (payload) => post("/api/verify", payload);
export const commit = (payload) => post("/api/commit", payload);
export const companyBrain = (payload) => post("/api/company-brain", payload);
export const runEval = (payload) => post("/api/eval", payload);
export const audit = (tenantId) => get(`/api/audit?tenant_id=${tenantId}`);
export const graphStats = () => get("/api/graph/stats");
