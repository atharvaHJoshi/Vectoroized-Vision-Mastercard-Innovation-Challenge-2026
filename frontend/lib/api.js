/**
 * API client + shared formatting helpers.
 *
 * Every call goes through `req`, which normalises errors into thrown Error
 * objects carrying the server's message, so pages can render a real failure
 * state instead of a blank screen.
 */

async function req(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error(
      `Cannot reach the SovereignGuard API. Is the backend running? ` +
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

/**
 * /api/simulate and /api/loop are async jobs: they return {job_id} and the
 * work continues server-side. Poll until terminal, surfacing progress lines as
 * they appear so a two-minute run does not look like a hang.
 */
export async function runJob(path, payload, onProgress, intervalMs = 1500) {
  const started = await post(path, payload);
  if (!started || !started.job_id) {
    // Some endpoints are synchronous; pass their result straight through.
    return started;
  }
  let seen = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const job = await get(`/api/jobs/${started.job_id}`);
    const lines = (job && job.progress) || [];
    if (onProgress && lines.length > seen) {
      lines.slice(seen).forEach((l) => onProgress(l.message));
      seen = lines.length;
    }
    if (!job) continue;
    if (job.status === "complete") return job.result;
    if (job.status === "failed") throw new Error(job.error || "job failed");
  }
}

/**
 * Realtime run client.
 *
 * Starts an async job, then opens an EventSource on /api/sse/{job_id} so the
 * UI sees progress lines and per-scenario generation telemetry the moment they
 * happen — no polling. If EventSource is unavailable or the stream drops, the
 * caller's stream silently downgrades to classic /api/jobs polling through
 * `pollJob` so the run still completes.
 *
 * Returns { abort } for callers that need to cancel on unmount.
 */
export function runRealtime(path, payload, { onProgress, onGeneration, onDone, onError }) {
  let closed = false;
  let settled = false;
  // `settle` fires a terminal callback (done/error) exactly once. done and
  // error can arrive from the SSE stream, from a transport failure's fallback
  // poll, or from a sync endpoint result — whichever wins, the UI must not be
  // told twice.
  const settle = (fn, arg) => {
    if (settled) return;
    settled = true;
    if (fn) fn(arg);
  };
  const finish = (fn, arg) => { if (!closed && fn) fn(arg); };

  const started = () => post(path, payload).then((r) => {
    if (closed) return;
    if (!r || !r.job_id) { settle(onDone, r); return; }     // sync endpoint
    const jobId = r.job_id;

    if (typeof EventSource === "undefined") {
      pollJob(jobId, {
        onProgress, onDone: (res) => settle(onDone, res),
        onError: (e) => settle(onError, e), closed: () => closed,
      });
      return;
    }
    const es = new EventSource(`/api/sse/${jobId}`);
    let fallbackArmed = false;
    es.onopen = () => { fallbackArmed = true; };
    es.onerror = (e) => {
      // A server-sent `event: error` line carries data and lips here too; a
      // transport failure has no data. Distinguish so a real failure is
      // reported once, not double-handled.
      if (e && e.data) {
        es.close();
        let msg = "stream failed";
        try { msg = JSON.parse(e.data).error || msg; } catch { /* ignore */ }
        settle(onError, new Error(msg));
        return;
      }
      // Transport failure mid-stream: stop and let polling take over.
      if (fallbackArmed) {
        es.close();
        pollJob(jobId, {
          onProgress, onDone: (res) => settle(onDone, res),
          onError: (e) => settle(onError, e), closed: () => closed,
        });
      }
    };
    // The backend emits NAMED events: `event: progress|generation|done|error`.
    // EventSource.onmessage only receives default-typed ("message") events, so
    // named events must be subscribed with addEventListener — otherwise the
    // stream stays open forever and the UI hangs on "Building…".
    const parse = (e) => { try { return JSON.parse(e.data); } catch { return {}; } };
    es.addEventListener("generation", (e) => finish(onGeneration, parse(e)));
    es.addEventListener("progress", (e) => {
      const d = parse(e);
      if (d && d.message) finish(onProgress, d.message);
    });
    es.addEventListener("done", (e) => {
      es.close();
      settle(onDone, parse(e));
    });
  }).catch((err) => settle(onError, err));

  started();

  return {
    abort() {
      closed = true;
    },
  };
}

/** Poll a job to completion — durable fallback for runRealtime. */
async function pollJob(jobId, { onProgress, onDone, onError, closed }) {
  let seen = 0;
  for (;;) {
    if (closed()) return;
    try {
      const job = await get(`/api/jobs/${jobId}`);
      const lines = (job && job.progress) || [];
      if (onProgress && lines.length > seen) {
        lines.slice(seen).forEach((l) => onProgress(l.message));
        seen = lines.length;
      }
      if (job && job.status === "complete") return onDone(job.result);
      if (job && job.status === "failed")
        return onError(new Error(job.error || "job failed"));
    } catch (e) {
      return onError(e);
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
}

// ---------------------------------------------------------------- formatting
export const pct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(digits)}%`;

export const num = (v, digits = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(digits);

export const int = (v) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : Number(v).toLocaleString("en-US");

export const money = (v) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export const signed = (v, digits = 4) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Number(v);
  return `${s >= 0 ? "+" : ""}${s.toFixed(digits)}`;
};

export const severityClass = (s) =>
  ({ CRITICAL: "sev-critical", HIGH: "sev-high", MEDIUM: "sev-medium" }[s] || "sev-low");

export const bandClass = (b) =>
  ({
    LOW: "band-low",
    MEDIUM: "band-medium",
    HIGH: "band-high",
    CRITICAL: "band-critical",
  }[b] || "band-low");

/** Recall -> colour, used by the weakest-segment heatmap. */
export function recallColour(r) {
  if (r === null || r === undefined) return "var(--surface-3)";
  if (r >= 0.95) return "rgba(16,185,129,0.28)";
  if (r >= 0.85) return "rgba(16,185,129,0.16)";
  if (r >= 0.7) return "rgba(245,158,11,0.18)";
  if (r >= 0.5) return "rgba(251,146,60,0.22)";
  return "rgba(239,68,68,0.26)";
}

export const ATTACK_LABEL = {
  ACCOUNT_TAKEOVER: "Account Takeover",
  TRANSACTION_MANIPULATION: "Transaction Manipulation",
  SYNTHETIC_IDENTITY: "Synthetic Identity",
  MERCHANT_FRAUD: "Merchant Fraud",
  PHISHING_PAYMENT_LINK: "Phishing / Payment Link",
  SOCIAL_ENGINEERING: "Social Engineering",
  MULTI_STAGE: "Multi-Stage",
};

export const shortAttack = (t) => ATTACK_LABEL[t] || t;
