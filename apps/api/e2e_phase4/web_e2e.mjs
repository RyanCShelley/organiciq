#!/usr/bin/env node
/**
 * Tier 4B Full-Stack Headless Chrome CDP Browser E2E Suite for Phase 4.
 *
 * Executes 5 scenarios (S5, S1, S2, S3, S4) against a live Next.js (`apps/web-v2`)
 * and FastAPI (`mock_api_server.py`) stack using Node 24 native WebSocket CDP and
 * `@auth/core/jwt` JWE session cookies.
 */

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const AUTH_JWT_PATH = path.join(
  REPO_ROOT,
  "apps/web-v2/node_modules/@auth/core/jwt.js",
);
const CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const WEB_URL = (process.env.WEB_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
const API_URL = (process.env.API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const AUTH_SECRET =
  process.env.AUTH_SECRET || "test-auth-secret-for-the-suite-only-0123456789";
const SEED_MANIFEST_PATH = process.env.SEED_MANIFEST_PATH;

if (!SEED_MANIFEST_PATH) {
  throw new Error("SEED_MANIFEST_PATH env var is required.");
}
if (!fs.existsSync(CHROME_BIN)) {
  throw new Error(`Google Chrome binary not found at ${CHROME_BIN}`);
}

const manifest = JSON.parse(fs.readFileSync(SEED_MANIFEST_PATH, "utf-8"));
const alpha = manifest.clients.alpha;
const beta = manifest.clients.beta;
const gamma = manifest.clients.gamma;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function mintSessionCookie(email, name) {
  const { encode } = await import(pathToFileURL(AUTH_JWT_PATH).href);
  const cookieName = "authjs.session-token";
  return encode({
    token: {
      email: email.toLowerCase(),
      name,
      sub: email.toLowerCase(),
    },
    secret: AUTH_SECRET,
    salt: cookieName,
    maxAge: 24 * 60 * 60,
  });
}

async function launchChrome() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "oiq-e2e-chrome-"));
  const args = [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1440,960",
    "--remote-debugging-port=0",
    `--user-data-dir=${userDataDir}`,
    "about:blank",
  ];

  const proc = spawn(CHROME_BIN, args, {
    stdio: ["ignore", "pipe", "pipe"],
  });

  const exitPromise = new Promise((resolve) => {
    proc.once("exit", (code, signal) => resolve({ code, signal }));
  });

  let stderrBuf = "";
  const wsUrl = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Timed out waiting for Chrome DevTools WS URL. stderr:\n${stderrBuf}`));
    }, 20000);

    const onData = (chunk) => {
      stderrBuf += chunk.toString("utf-8");
      const match = stderrBuf.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/devtools\/browser\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        proc.stderr.off("data", onData);
        resolve(match[1]);
      }
    };

    proc.stderr.on("data", onData);
    proc.once("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    proc.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chrome exited early (${code}). stderr:\n${stderrBuf}`));
    });
  });

  const parsedWs = new URL(wsUrl);
  const listRes = await fetch(`http://${parsedWs.host}/json/list`);
  if (!listRes.ok) {
    throw new Error(`Failed to fetch Chrome /json/list: ${listRes.status}`);
  }
  const targets = await listRes.json();
  const pageTarget = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
  if (!pageTarget) {
    throw new Error(`No debuggable page target found in ${JSON.stringify(targets)}`);
  }

  async function requestBrowserClose(timeoutMs = 1500) {
    let ws;
    try {
      ws = new WebSocket(wsUrl);
      await new Promise((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve();
        };
        const timer = setTimeout(finish, timeoutMs);
        ws.addEventListener(
          "open",
          () => {
            try {
              ws.send(JSON.stringify({ id: 1, method: "Browser.close", params: {} }));
            } catch {
              finish();
            }
          },
          { once: true },
        );
        ws.addEventListener("message", finish, { once: true });
        ws.addEventListener("close", finish, { once: true });
        ws.addEventListener("error", finish, { once: true });
      });
    } catch {
      // Fall back to SIGTERM below if CDP Browser.close fails.
    } finally {
      try {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
          ws.close();
        }
      } catch {
        // Ignore close errors during teardown.
      }
    }
  }

  async function close() {
    if (proc.exitCode === null && proc.signalCode === null) {
      await requestBrowserClose(1500);
      const gracefulExit = await Promise.race([
        exitPromise.then(() => true),
        sleep(2500).then(() => false),
      ]);
      if (!gracefulExit && proc.exitCode === null && proc.signalCode === null) {
        proc.kill("SIGTERM");
        const exited = await Promise.race([
          exitPromise.then(() => true),
          sleep(4000).then(() => false),
        ]);
        if (!exited && proc.exitCode === null && proc.signalCode === null) {
          proc.kill("SIGKILL");
          await exitPromise;
        }
      }
    } else {
      await exitPromise;
    }
    try {
      fs.rmSync(userDataDir, {
        recursive: true,
        force: true,
        maxRetries: 10,
        retryDelay: 100,
      });
    } catch (err) {
      console.warn(
        `Warning: failed to remove Chrome userDataDir ${userDataDir}: ${err?.message || err}`,
      );
    }
  }

  return { pageWsUrl: pageTarget.webSocketDebuggerUrl, close };
}

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      const onOpen = () => {
        this.ws.removeEventListener("error", onErr);
        resolve();
      };
      const onErr = (ev) => {
        this.ws.removeEventListener("open", onOpen);
        reject(new Error(`WebSocket connection failed: ${ev?.message || "unknown error"}`));
      };
      this.ws.addEventListener("open", onOpen, { once: true });
      this.ws.addEventListener("error", onErr, { once: true });
    });

    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id !== undefined) {
        const entry = this.pending.get(msg.id);
        if (!entry) return;
        this.pending.delete(msg.id);
        clearTimeout(entry.timer);
        if (msg.error) {
          entry.reject(new Error(`CDP ${entry.method} error: ${JSON.stringify(msg.error)}`));
        } else {
          entry.resolve(msg.result);
        }
        return;
      }
      if (msg.method) {
        const handlers = this.listeners.get(msg.method) || [];
        for (const h of handlers) h(msg.params);
      }
    });
  }

  on(method, handler) {
    if (!this.listeners.has(method)) this.listeners.set(method, []);
    this.listeners.get(method).push(handler);
  }

  send(method, params = {}, timeoutMs = 20000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP timeout after ${timeoutMs}ms calling ${method}`));
      }, timeoutMs);
      this.pending.set(id, { method, resolve, reject, timer });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evalExpr(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(
        `Browser eval exception: ${res.exceptionDetails.text || ""} ${
          res.exceptionDetails.exception?.description || ""
        }`,
      );
    }
    return res.result?.value;
  }

  async waitFor(fnSource, timeoutMs = 20000, description = "condition") {
    const start = Date.now();
    let lastErr = null;
    while (Date.now() - start < timeoutMs) {
      try {
        const ok = await this.evalExpr(`(${fnSource})()`);
        if (ok) return ok;
      } catch (err) {
        lastErr = err;
      }
      await sleep(150);
    }
    const snapshot = await this.evalExpr(
      `(() => ({ url: location.href, text: (document.body?.innerText || "").slice(0, 1200) }))()`,
    ).catch(() => ({}));
    throw new Error(
      `Timed out waiting for ${description} after ${timeoutMs}ms.${
        lastErr ? ` Last eval error: ${lastErr.message}` : ""
      }\nState: ${JSON.stringify(snapshot)}`,
    );
  }

  async navigate(url) {
    await this.send("Page.navigate", { url });
    await this.waitFor(
      () => document.readyState === "complete" && Boolean(document.body),
      25000,
      `navigation to ${url}`,
    );
    await sleep(250);
  }

  async reload() {
    await this.send("Page.reload", { ignoreCache: true });
    await this.waitFor(
      () => document.readyState === "complete" && Boolean(document.body),
      25000,
      "page reload",
    );
    await sleep(250);
  }

  close() {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(new Error("CDP closed"));
    }
    this.pending.clear();
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close();
    }
  }
}

async function runSuite() {
  const adminToken = await mintSessionCookie(manifest.users.admin.email, "Admin");
  const chrome = await launchChrome();
  const cdp = new CdpClient(chrome.pageWsUrl);

  const errors = {
    consoleErrors: [],
    exceptions: [],
    server5xx: [],
  };

  function assertZeroErrors(stage) {
    const summary = [];
    if (errors.consoleErrors.length) {
      summary.push(`console.error(${errors.consoleErrors.length}): ${JSON.stringify(errors.consoleErrors)}`);
    }
    if (errors.exceptions.length) {
      summary.push(`exceptions(${errors.exceptions.length}): ${JSON.stringify(errors.exceptions)}`);
    }
    if (errors.server5xx.length) {
      summary.push(`5xx(${errors.server5xx.length}): ${JSON.stringify(errors.server5xx)}`);
    }
    if (summary.length > 0) {
      throw new Error(`Zero-error monitor failed at [${stage}]:\n${summary.join("\n")}`);
    }
  }

  try {
    await cdp.connect();
    await Promise.all([
      cdp.send("Runtime.enable"),
      cdp.send("Network.enable"),
      cdp.send("Page.enable"),
      cdp.send("DOM.enable"),
    ]);

    cdp.on("Runtime.consoleAPICalled", (params) => {
      if (params.type === "error") {
        const text = (params.args || [])
          .map((a) => a.value ?? a.description ?? JSON.stringify(a))
          .join(" ");
        errors.consoleErrors.push(text);
      }
    });

    cdp.on("Runtime.exceptionThrown", (params) => {
      errors.exceptions.push(
        params.exceptionDetails?.exception?.description ||
          params.exceptionDetails?.text ||
          JSON.stringify(params),
      );
    });

    cdp.on("Network.responseReceived", (params) => {
      const st = params.response?.status ?? 0;
      const url = params.response?.url ?? "";
      if (st >= 500 && (url.startsWith(WEB_URL) || url.startsWith(API_URL))) {
        errors.server5xx.push({ status: st, url });
      }
    });

    const cookieSet = await cdp.send("Network.setCookie", {
      name: "authjs.session-token",
      value: adminToken,
      url: WEB_URL,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });
    assert.equal(cookieSet.success, true, "Failed to inject authjs.session-token cookie");

    // Helper injected per evaluation via string builders
    const setValHelper = `
      function setReactValue(el, value) {
        if (!el) throw new Error("Target element missing for setReactValue");
        const tag = el.tagName.toLowerCase();
        const proto = tag === "textarea"
          ? window.HTMLTextAreaElement.prototype
          : tag === "select"
            ? window.HTMLSelectElement.prototype
            : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (setter) setter.call(el, value);
        else el.value = value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
    `;

    // ── S5: Home / All-Clients Overview ──────────────────────────────────────
    console.log("Running S5: Home / All-Clients Overview...");
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      `() =>
        document.querySelector("h1")?.textContent?.includes("All clients") &&
        document.body.innerText.includes(${JSON.stringify(alpha.name)}) &&
        document.body.innerText.includes(${JSON.stringify(beta.name)}) &&
        document.body.innerText.includes(${JSON.stringify(gamma.name)})`,
      20000,
      "All clients overview table",
    );

    const homePath = await cdp.evalExpr(`location.pathname`);
    assert.equal(homePath, "/", `Expected '/' without auto-redirect, got ${homePath}`);

    const getRowOrder = () =>
      cdp.evalExpr(
        `Array.from(document.querySelectorAll("tbody tr")).map(tr => tr.innerText.replace(/\\s+/g, " ").trim())`,
      );
    const clickSortHeader = async (label, expectedSort) => {
      await cdp.evalExpr(`(() => {
        const btn = Array.from(document.querySelectorAll("thead th button"))
          .find(b => b.textContent.trim() === ${JSON.stringify(label)});
        if (!btn) throw new Error("Missing sort header: " + ${JSON.stringify(label)});
        btn.click();
      })()`);
      await cdp.waitFor(
        `() => {
          const btn = Array.from(document.querySelectorAll("thead th button"))
            .find(b => b.textContent.trim() === ${JSON.stringify(label)});
          return Boolean(btn && btn.closest("th")?.getAttribute("aria-sort") === ${JSON.stringify(expectedSort)});
        }`,
        5000,
        `sort header '${label}' aria-sort === '${expectedSort}'`,
      );
      return expectedSort;
    };

    // Visibility descending -> Beacon > Acme, Cedar last
    assert.equal(await clickSortHeader("Visibility", "descending"), "descending");
    let rows = await getRowOrder();
    assert.ok(rows[0].includes(beta.name), `Expected ${beta.name} first on Visibility desc, got: ${rows[0]}`);
    assert.ok(rows[rows.length - 1].includes(gamma.name), `Expected ${gamma.name} (nulls) last, got: ${rows[rows.length - 1]}`);

    // Visibility ascending -> nulls STILL last
    assert.equal(await clickSortHeader("Visibility", "ascending"), "ascending");
    rows = await getRowOrder();
    assert.ok(rows[0].includes(alpha.name), `Expected ${alpha.name} first on Visibility asc, got: ${rows[0]}`);
    assert.ok(rows[rows.length - 1].includes(gamma.name), `Expected ${gamma.name} (nulls) last on asc too, got: ${rows[rows.length - 1]}`);

    // Traffic descending -> Beacon > Acme, Cedar last
    assert.equal(await clickSortHeader("Traffic", "descending"), "descending");
    rows = await getRowOrder();
    assert.ok(rows[0].includes(beta.name));
    assert.ok(rows[rows.length - 1].includes(gamma.name));

    // Leads descending -> Beacon > Acme, Cedar last
    assert.equal(await clickSortHeader("Leads", "descending"), "descending");
    rows = await getRowOrder();
    assert.ok(rows[0].includes(beta.name));
    assert.ok(rows[rows.length - 1].includes(gamma.name));

    // Client ascending
    assert.equal(await clickSortHeader("Client", "ascending"), "ascending");
    rows = await getRowOrder();
    assert.ok(rows[0].includes(alpha.name));

    // Click into Acme Plumbing
    await cdp.evalExpr(`(() => {
      const link = Array.from(document.querySelectorAll("tbody a"))
        .find(a => a.textContent.includes(${JSON.stringify(alpha.name)}));
      if (!link) throw new Error("Alpha client link not found");
      link.click();
    })()`);
    await cdp.waitFor(
      `() => location.pathname.startsWith(${JSON.stringify("/" + alpha.slug)})`,
      15000,
      `navigation into ${alpha.name}`,
    );
    assertZeroErrors("S5");

    // ── S1: Guided Setup & Client Flow ───────────────────────────────────────
    console.log("Running S1: Guided Setup & Client Flow...");
    await cdp.navigate(`${WEB_URL}/new-client`);
    await cdp.waitFor(
      () => document.querySelector("h1")?.textContent?.includes("Add a client"),
      15000,
      "Add a client heading",
    );

    const newClientCheck = await cdp.evalExpr(`(() => {
      const text = document.body.innerText;
      const moreBtn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.includes("More options"));
      const hasHiddenOptionalBefore = !text.includes("Agency services") && !text.includes("Contract start date");
      if (moreBtn) moreBtn.click();
      return { hasMoreBtn: Boolean(moreBtn), hasHiddenOptionalBefore };
    })()`);
    assert.equal(newClientCheck.hasMoreBtn, true, "Expected 'More options' progressive disclosure button");
    assert.equal(newClientCheck.hasHiddenOptionalBefore, true, "Expected optional fields tucked by default");

    await cdp.waitFor(
      () => document.body.innerText.includes("Agency services"),
      5000,
      "More options disclosed Agency services section",
    );

    const defaultService = await cdp.evalExpr(`(() => {
      const selects = Array.from(document.querySelectorAll("select"));
      const svc = selects.find(s => Array.from(s.options).some(o => o.value === "organiciq"));
      return svc ? svc.value : null;
    })()`);
    assert.equal(defaultService, "organiciq", "NewClientForm should default service to organiciq");

    await cdp.navigate(`${WEB_URL}/${alpha.slug}/settings`);
    await cdp.waitFor(
      () => Boolean(document.querySelector("#guided-setup")),
      15000,
      "Guided setup checklist on /settings",
    );
    const setupCheck = await cdp.evalExpr(`(() => {
      const root = document.querySelector("#guided-setup");
      const text = root.innerText;
      const hrefs = Array.from(root.querySelectorAll("a")).map(a => a.getAttribute("href"));
      return { text, hrefs };
    })()`);

    for (const expectedStep of [
      "General information",
      "Connect GA4 & Search Console",
      "First data pull",
      "Conversion & lead definitions",
      "Baseline snapshot",
      "Watchlist keywords",
      "First Decision Engine task",
    ]) {
      assert.ok(setupCheck.text.includes(expectedStep), `Missing setup step '${expectedStep}'`);
    }
    assert.ok(!setupCheck.text.includes("Content sources"), "Legacy content_sources must not appear in checklist");
    assert.ok(!setupCheck.text.includes("Conversion pages"), "Legacy conversion_pages must not appear in checklist");
    assert.ok(
      setupCheck.hrefs.some((h) => h === `/${alpha.slug}/settings/connections`),
      "Expected checklist link to /settings/connections",
    );
    assert.ok(
      setupCheck.hrefs.some((h) => h === `/${alpha.slug}/watchlist`),
      "Expected checklist link to /watchlist",
    );
    assertZeroErrors("S1");

    // ── S2: Baseline & Projections ───────────────────────────────────────────
    console.log("Running S2: Baseline & Projections...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/settings/baseline`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Modeled Baseline & 12-Month Projection") &&
        document.body.innerText.includes("Suggested monthly goal:"),
      20000,
      "Baseline modeled projection & suggested goal",
    );

    const baselineText = await cdp.evalExpr(`document.body.textContent || ""`);
    for (const marker of ["Today", "3 months", "6 months", "9 months", "12 months"]) {
      assert.ok(baselineText.includes(marker), `Missing projection checkpoint '${marker}'`);
    }

    // Lock v1 from the simplified form
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.includes("Lock as version 1"));
      if (!btn) throw new Error("Lock as version 1 button not found");
      btn.click();
    })()`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Current Locked Baseline (v1)") &&
        document.body.innerText.includes("Next: Build your keyword watchlist"),
      20000,
      "Baseline v1 lock confirmation",
    );

    // Update monthly goal directly & verify persistence across reload
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const input = document.querySelector('input[aria-label*="Monthly"]');
      if (!input) throw new Error("Monthly goal input not found");
      setReactValue(input, "52");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const updateBtn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Update");
      if (!updateBtn) throw new Error("Update goal button not found");
      updateBtn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Monthly goal updated to 52/mo."),
      15000,
      "Goal update confirmation",
    );

    await cdp.reload();
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Current Locked Baseline (v1)") &&
        document.body.innerText.includes("52/mo"),
      15000,
      "Persisted baseline v1 and 52/mo goal after reload",
    );
    assertZeroErrors("S2");

    // ── S3: Unified Watchlist & Redirect ─────────────────────────────────────
    console.log("Running S3: Unified Watchlist & Redirect...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/watchlist`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("water heater repair") &&
        Boolean(document.querySelector('input[aria-label="Quick-add keyword"]')),
      15000,
      "Unified watchlist page",
    );

    // Quick-add keyword
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const input = document.querySelector('input[aria-label="Quick-add keyword"]');
      setReactValue(input, "tankless water heater install");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim() === "+ Add");
      if (!btn) throw new Error("Quick-add submit button not found");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("tankless water heater install"),
      15000,
      "Quick-added keyword in watchlist",
    );

    // Edit existing keyword ("water heater repair")
    await cdp.evalExpr(`(() => {
      const row = Array.from(document.querySelectorAll("tbody tr"))
        .find(tr => tr.innerText.includes("water heater repair"));
      if (!row) throw new Error("Row for 'water heater repair' not found");
      const editBtn = Array.from(row.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Edit");
      if (!editBtn) throw new Error("Edit button not found");
      editBtn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('[role="dialog"][aria-label="Edit keyword"]')),
      10000,
      "Edit keyword drawer",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const dlg = document.querySelector('[role="dialog"][aria-label="Edit keyword"]');
      const numInputs = dlg.querySelectorAll('input[type="number"]');
      if (numInputs.length < 1) throw new Error("Volume input not found in edit drawer");
      setReactValue(numInputs[0], "2150");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="Edit keyword"]');
      const saveBtn = Array.from(dlg.querySelectorAll('button[type="submit"]'))
        .find(b => b.textContent.includes("Save changes"));
      if (!saveBtn) throw new Error("Save changes button not found");
      saveBtn.click();
    })()`);
    await cdp.waitFor(
      () =>
        !document.querySelector('[role="dialog"][aria-label="Edit keyword"]') &&
        document.body.innerText.includes("2,150"),
      15000,
      "Updated keyword volume 2,150 in watchlist",
    );

    // Add GSC suggestion to a bucket
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.includes("GSC keyword suggestions"));
      if (!btn) throw new Error("GSC keyword suggestions button not found");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => {
        const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
        return dlg && dlg.querySelectorAll("ul li").length > 0;
      },
      15000,
      "GSC suggestions list inside drawer",
    );
    const addedSuggestionQuery = await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
      const firstLi = dlg.querySelector("ul li");
      const queryText = firstLi.querySelector("span.font-semibold")?.textContent?.trim() || "";
      const addBtn = Array.from(firstLi.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Add");
      if (!addBtn) throw new Error("Add button missing on suggestion item");
      addBtn.click();
      return queryText;
    })()`);
    assert.ok(addedSuggestionQuery.length > 0, "Expected non-empty GSC suggestion query");
    await cdp.waitFor(
      `() => {
        const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
        const inTable = Array.from(document.querySelectorAll("table"))
          .filter(t => !t.closest('[role="dialog"]'))
          .some(t => t.innerText.includes(${JSON.stringify(addedSuggestionQuery)}));
        return Boolean((dlg && dlg.innerText.includes("Added")) || inTable);
      }`,
      15000,
      "GSC suggestion added confirmation or watchlist table update",
    );
    await cdp.evalExpr(`document.querySelector('button[aria-label="Close suggestions drawer"]')?.click()`);
    await cdp.waitFor(
      `() =>
        !document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]') &&
        Array.from(document.querySelectorAll("table"))
          .filter(t => !t.closest('[role="dialog"]'))
          .some(t => t.innerText.includes(${JSON.stringify(addedSuggestionQuery)}))`,
      15000,
      "Added GSC suggestion visible in watchlist table outside drawer",
    );

    // Reload and verify persistence
    await cdp.reload();
    await cdp.waitFor(
      `() =>
        document.body.innerText.includes("tankless water heater install") &&
        document.body.innerText.includes("2,150") &&
        document.body.innerText.includes(${JSON.stringify(addedSuggestionQuery)})`,
      15000,
      "Persisted watchlist changes after reload",
    );

    // /settings/watchlist redirects cleanly to /watchlist
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/settings/watchlist`);
    await cdp.waitFor(
      `() =>
        location.pathname === ${JSON.stringify(`/${alpha.slug}/watchlist`)} &&
        document.body.innerText.includes("Watchlist")`,
      15000,
      "Redirect from /settings/watchlist to /watchlist",
    );
    assertZeroErrors("S3");

    // ── S4: Content Tools (Gaps, Optimizer Ad-Hoc, Sitemap, No Feeds) ────────
    console.log("Running S4: Content Tools...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/content-gaps`);
    await cdp.waitFor(
      () =>
        document.querySelector("h1")?.textContent?.includes("Content gaps") &&
        document.body.innerText.includes("hydro jetting sewer line"),
      15000,
      "Content gaps table",
    );
    const gapsText = await cdp.evalExpr(`document.querySelector("table")?.innerText || ""`);
    assert.ok(gapsText.includes("hydro jetting sewer line"), "Expected relevant gap 'hydro jetting sewer line'");
    assert.ok(gapsText.includes("copper repiping cost"), "Expected relevant gap 'copper repiping cost'");
    for (const noise of ["free plumbing sticker", "rivalplumbing pricing", "acme plumbing near me"]) {
      assert.ok(!gapsText.toLowerCase().includes(noise), `Irrelevant/excluded term '${noise}' leaked into table`);
    }

    // Content Optimizer ad-hoc keyword on unranked URL
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/content-optimizer`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('input[aria-label="Page address"]')),
      15000,
      "Content optimizer page input",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const input = document.querySelector('input[aria-label="Page address"]');
      setReactValue(input, ${JSON.stringify(alpha.unranked_optimizer_url)});
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim() === "Open");
      if (!btn) throw new Error("Open button not found");
      btn.click();
    })()`);

    await cdp.waitFor(
      () => Boolean(document.querySelector('input[placeholder="e.g. emergency plumbing repair"]')),
      15000,
      "Content optimizer target keyword input",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const kwInput = document.querySelector('input[placeholder="e.g. emergency plumbing repair"]');
      setReactValue(kwInput, "trenchless sewer line replacement");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const askBtn = Array.from(document.querySelectorAll("button"))
        .find(b => b.getAttribute("role") !== "tab" && b.textContent.trim() === "Rewrite the opening");
      if (!askBtn) throw new Error("Rewrite the opening action button not found");
      askBtn.click();
    })()`);

    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Target keyword: trenchless sewer line replacement") &&
        document.body.innerText.includes("E2E optimized opening"),
      25000,
      "Completed Content Optimizer ad-hoc draft",
    );

    // Settings Content: Sitemap form present, feeds absent, update persists
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/settings/content`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Website sitemap"),
      15000,
      "Website sitemap card",
    );
    const contentSettingsText = await cdp.evalExpr(`document.body.innerText`);
    assert.ok(!/blog feeds/i.test(contentSettingsText), "Removed feed settings copy should not render");
    assert.ok(!/add feed/i.test(contentSettingsText), "Removed Add feed button should not render");

    const updatedSitemap = "https://acmeplumbing.example/sitemap-e2e.xml";
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const input = document.querySelector('input[placeholder*="Found automatically"]');
      if (!input) throw new Error("Sitemap URL input not found");
      setReactValue(input, ${JSON.stringify(updatedSitemap)});
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const saveBtn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim().startsWith("Save"));
      if (!saveBtn) throw new Error("Sitemap Save button not found");
      saveBtn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Saved"),
      15000,
      "Sitemap save confirmation",
    );

    await cdp.reload();
    await cdp.waitFor(
      () => {
        const input = document.querySelector('input[placeholder*="Found automatically"]');
        return input && input.value === "https://acmeplumbing.example/sitemap-e2e.xml";
      },
      15000,
      "Persisted sitemap URL after reload",
    );
    assertZeroErrors("S4");

    // ── T5-B6: AllClientsOverview search, status filter, Avg Pos / Updated sort, empty state ──
    console.log("Running T5-B6: Overview filters & Avg Pos / Updated sort...");
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      () => document.querySelectorAll("tbody tr").length >= 3,
      15000,
      "Overview rows loaded",
    );

    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Filter clients"]'), "Beacon");
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Showing 1 of 3") && document.querySelectorAll("tbody tr").length === 1,
      5000,
      "Overview search filter for Beacon",
    );

    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Filter clients"]'), "");
      const btn = Array.from(document.querySelectorAll('[aria-label="Filter by status"] button'))
        .find(b => b.textContent.trim() === "Onboarding");
      if (!btn) throw new Error("Onboarding status pill missing");
      btn.click();
    })()`);
    await cdp.waitFor(
      `() =>
        document.body.innerText.includes("Showing 1 of 3") &&
        document.body.innerText.includes(${JSON.stringify(gamma.name)})`,
      5000,
      "Overview status filter Onboarding",
    );

    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll('[aria-label="Filter by status"] button'))
        .find(b => b.textContent.trim() === "All");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.querySelectorAll("tbody tr").length === 3,
      5000,
      "Overview status reset to All",
    );

    assert.equal(await clickSortHeader("Avg Pos", "ascending"), "ascending");
    rows = await getRowOrder();
    assert.ok(rows[0].includes(beta.name), `Expected ${beta.name} first on Avg Pos asc`);
    assert.ok(rows[rows.length - 1].includes(gamma.name), `Expected ${gamma.name} nulls last on Avg Pos`);

    assert.equal(await clickSortHeader("Updated", "descending"), "descending");
    rows = await getRowOrder();
    assert.ok(rows[rows.length - 1].includes(gamma.name), `Expected ${gamma.name} nulls last on Updated`);

    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Filter clients"]'), "zzznomatch");
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("No clients match the current filter."),
      5000,
      "Overview empty state",
    );
    assertZeroErrors("T5-B6");

    // ── T5-B1: Consulting mode client lifecycle in Chrome ────────────────────
    console.log("Running T5-B1: Consulting mode lifecycle...");
    await cdp.navigate(`${WEB_URL}/new-client`);
    await cdp.waitFor(
      () => document.querySelector("h1")?.textContent?.includes("Add a client"),
      15000,
      "New client form for consulting",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const selects = Array.from(document.querySelectorAll("select"));
      const modeSel = selects.find(s => Array.from(s.options).some(o => o.value === "consulting"));
      if (!modeSel) throw new Error("Mode select not found");
      setReactValue(modeSel, "consulting");
    })()`);
    await cdp.waitFor(
      () => !document.body.innerText.includes("OrganicIQ tier"),
      5000,
      "Tier field hidden in consulting mode",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const inputs = Array.from(document.querySelectorAll("main form input:not([type='hidden'])"));
      setReactValue(inputs[0], "Delta Advisory");
      setReactValue(inputs[1], "deltaadvisory.example");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim() === "Add client");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => location.pathname.includes("/settings/connections"),
      15000,
      "Redirect to consulting connections",
    );
    const consultingSlug = await cdp.evalExpr(`location.pathname.split("/")[1]`);
    await cdp.navigate(`${WEB_URL}/${consultingSlug}/settings`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Consulting mode") &&
        document.body.innerText.includes("Consulting workspace profile") &&
        document.body.innerText.includes("First recommendation or report"),
      15000,
      "Consulting checklist steps",
    );
    const consultSettingsText = await cdp.evalExpr(`document.body.innerText`);
    assert.ok(!consultSettingsText.includes("First Decision Engine task"));
    assert.ok(!consultSettingsText.includes("OrganicIQ tier"));
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Delta Advisory") && document.body.innerText.includes("Consulting"),
      15000,
      "Delta Advisory Consulting badge on overview",
    );
    assertZeroErrors("T5-B1");

    // ── T5-B3: Watchlist bucket CRUD, KD validation, suggestion sync after delete, CSV Preview+Import ──
    console.log("Running T5-B3: Watchlist full lifecycle & suggestion sync...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/watchlist`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('input[aria-label="Quick-add keyword"]')),
      15000,
      "Watchlist page for T5-B3",
    );

    // Create bucket -> Rename bucket
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "+ New bucket");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('input[placeholder="e.g. Core Services"]')),
      5000,
      "New bucket form",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[placeholder="e.g. Core Services"]'), "Seasonal Offers");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim() === "Create bucket");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Seasonal Offers"),
      10000,
      "Created bucket Seasonal Offers",
    );

    await cdp.evalExpr(`(() => {
      const hdr = Array.from(document.querySelectorAll("h3"))
        .find(h => h.textContent.includes("Seasonal Offers"))
        ?.closest("div");
      const renBtn = Array.from(hdr.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Rename");
      renBtn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('input[aria-label="Rename bucket Seasonal Offers"]')),
      5000,
      "Rename bucket input",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Rename bucket Seasonal Offers"]'), "Seasonal Deals");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']"))
        .find(b => b.textContent.trim() === "Save");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Seasonal Deals"),
      10000,
      "Renamed bucket Seasonal Deals",
    );

    // Add keyword via drawer with progressive disclosure & invalid KD error
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("header button"))
        .find(b => b.textContent.trim() === "+ Add keyword");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('[role="dialog"][aria-label="Add keyword"]')),
      5000,
      "Add keyword drawer",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const dlg = document.querySelector('[role="dialog"][aria-label="Add keyword"]');
      const kwInput = dlg.querySelector('input[placeholder="e.g. mineral sunscreen"]');
      setReactValue(kwInput, "sump pump backup");
      const sel = dlg.querySelector("select");
      const opt = Array.from(sel.options).find(o => o.text.includes("Seasonal Deals"));
      if (opt) setReactValue(sel, opt.value);
      const discBtn = Array.from(dlg.querySelectorAll("button"))
        .find(b => b.textContent.includes("Optional metadata"));
      discBtn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('[role="dialog"][aria-label="Add keyword"] input[placeholder="0–100"]')),
      5000,
      "Optional metadata fields opened",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const dlg = document.querySelector('[role="dialog"][aria-label="Add keyword"]');
      setReactValue(dlg.querySelector('input[placeholder="0–100"]'), "150");
      dlg.querySelector('button[type="submit"]').click();
    })()`);
    await cdp.waitFor(
      () => {
        const dlg = document.querySelector('[role="dialog"][aria-label="Add keyword"]');
        return dlg && dlg.innerText.includes("KD must be");
      },
      5000,
      "Invalid KD error alert (note: native min/max or JS validation)",
    ).catch(async () => {
      // Browser HTML5 max=100 may block submit natively; verify validationMessage
      const msg = await cdp.evalExpr(`document.querySelector('[role="dialog"][aria-label="Add keyword"] input[placeholder="0–100"]')?.validationMessage || ""`);
      assert.ok(msg.length > 0, "Expected KD=150 validation message");
    });

    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const dlg = document.querySelector('[role="dialog"][aria-label="Add keyword"]');
      setReactValue(dlg.querySelector('input[placeholder="e.g. 2400"]'), "1400");
      setReactValue(dlg.querySelector('input[placeholder="0–100"]'), "28");
      setReactValue(dlg.querySelector('input[placeholder="e.g. Commercial"]'), "Commercial");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="Add keyword"]');
      dlg.querySelector('button[type="submit"]').click();
    })()`);
    await cdp.waitFor(
      () =>
        !document.querySelector('[role="dialog"][aria-label="Add keyword"]') &&
        document.body.innerText.includes("sump pump backup"),
      15000,
      "Keyword sump pump backup saved",
    );

    // Delete previously added GSC suggestion keyword -> verify it reappears in GSC suggestions drawer WITHOUT hard reload!
    await cdp.evalExpr(`(() => {
      const row = Array.from(document.querySelectorAll("tbody tr"))
        .find(tr => tr.innerText.includes(${JSON.stringify(addedSuggestionQuery)}));
      if (!row) throw new Error("Row for deleted suggestion not found");
      const delBtn = Array.from(row.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Delete");
      delBtn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(Array.from(document.querySelectorAll("tbody button")).find(b => b.textContent.trim() === "Confirm")),
      5000,
      "Keyword delete Confirm button",
    );
    await cdp.evalExpr(`(() => {
      const cfm = Array.from(document.querySelectorAll("tbody button")).find(b => b.textContent.trim() === "Confirm");
      cfm.click();
    })()`);
    await cdp.waitFor(
      `() => !Array.from(document.querySelectorAll("table")).some(t => t.innerText.includes(${JSON.stringify(addedSuggestionQuery)}))`,
      15000,
      "Deleted suggestion removed from table",
    );

    // Open GSC suggestions drawer without reload -> deleted query must be back in suggestionsData!
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.includes("GSC keyword suggestions"));
      btn.click();
    })()`);
    await cdp.waitFor(
      `() => {
        const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
        return dlg && dlg.innerText.includes(${JSON.stringify(addedSuggestionQuery)});
      }`,
      10000,
      "Deleted keyword reappeared in GSC suggestions drawer without reload",
    );
    // Toggle 28d -> 90d and close drawer
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
      const b28 = Array.from(dlg.querySelectorAll("button")).find(b => b.textContent.trim() === "28d");
      b28.click();
    })()`);
    await sleep(300);
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="GSC keyword suggestions"]');
      const b90 = Array.from(dlg.querySelectorAll("button")).find(b => b.textContent.trim() === "90d");
      b90.click();
    })()`);
    await sleep(300);
    await cdp.evalExpr(`document.querySelector('button[aria-label="Close suggestions drawer"]')?.click()`);

    // Delete non-empty Seasonal Deals bucket
    await cdp.evalExpr(`(() => {
      const hdr = Array.from(document.querySelectorAll("h3"))
        .find(h => h.textContent.includes("Seasonal Deals"))
        ?.closest("div");
      const delBtn = Array.from(hdr.querySelectorAll("button")).find(b => b.textContent.trim() === "Delete");
      delBtn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes('Delete "Seasonal Deals" and all 1 keyword(s) inside it?'),
      5000,
      "Bucket delete confirmation with keyword count",
    );
    await cdp.evalExpr(`(() => {
      const cfm = Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Confirm delete");
      cfm.click();
    })()`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes('Deleted bucket "Seasonal Deals"') &&
        !Array.from(document.querySelectorAll("h3")).some(h => h.textContent.includes("Seasonal Deals")) &&
        !document.body.innerText.includes("sump pump backup"),
      15000,
      "Non-empty bucket and keyword deleted",
    );

    // Embedded CSV Preview + Import
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button"))
        .find(b => b.textContent.trim() === "Import CSV");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('[role="dialog"][aria-label="Import watchlist from CSV"]')),
      5000,
      "CSV import drawer",
    );
    await cdp.evalExpr(`(() => {
      const input = document.querySelector('input[aria-label="Watchlist CSV"]');
      const dt = new DataTransfer();
      dt.items.add(new File(["Topic,Keyword,Volume,Difficulty\\nImported Bucket,csv sump repair,600,25\\n"], "watchlist.csv", { type: "text/csv" }));
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    })()`);
    await cdp.waitFor(
      () => {
        const dlg = document.querySelector('[role="dialog"][aria-label="Import watchlist from CSV"]');
        const prevBtn = Array.from(dlg.querySelectorAll("button")).find(b => b.textContent.trim() === "Preview");
        return prevBtn && !prevBtn.disabled;
      },
      5000,
      "Preview button enabled after CSV file attach",
    );
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="Import watchlist from CSV"]');
      Array.from(dlg.querySelectorAll("button")).find(b => b.textContent.trim() === "Preview").click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Preview, nothing saved"),
      10000,
      "CSV preview report",
    );
    await cdp.evalExpr(`(() => {
      const dlg = document.querySelector('[role="dialog"][aria-label="Import watchlist from CSV"]');
      Array.from(dlg.querySelectorAll("button")).find(b => b.textContent.trim() === "Import").click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Imported · watchlist.csv"),
      15000,
      "CSV import report",
    );
    await cdp.evalExpr(`document.querySelector('button[aria-label="Close CSV import drawer"]')?.click()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("csv sump repair"),
      10000,
      "Imported CSV keyword visible in watchlist",
    );
    assertZeroErrors("T5-B3");

    // ── T5-B4: Baseline re-lock v2, CSV fallback, & '/' goal sync without hard reload ──
    console.log("Running T5-B4: Baseline v2 re-lock, CSV fallback & '/' goal sync...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/settings/baseline`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Current Locked Baseline (v1)"),
      15000,
      "Baseline v1 visible for T5-B4",
    );
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Re-baseline");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 2"))),
      5000,
      "Re-baseline v2 form",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const goalInput = document.querySelector('input[placeholder*="Default:"], input[placeholder*="Current:"]');
      setReactValue(goalInput, "64");
      const sel = Array.from(document.querySelectorAll("select")).find(s => Array.from(s.options).some(o => o.value === "relaunch"));
      setReactValue(sel, "relaunch");
      const noteArea = document.querySelector("form textarea");
      setReactValue(noteArea, "Site relaunch and tracking verification completed.");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 2"));
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Current Locked Baseline (v2)") && document.body.innerText.includes("64/mo"),
      20000,
      "Baseline v2 locked with 64/mo",
    );

    // CSV fallback analysis
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Advanced options & monthly series"));
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "CSV fallback")),
      5000,
      "Advanced options expanded",
    );
    await cdp.evalExpr(`(() => {
      Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "CSV fallback").click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('textarea[placeholder*="month,sessions,leads"]')),
      5000,
      "CSV fallback textarea",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(
        document.querySelector('textarea[placeholder*="month,sessions,leads"]'),
        "month,sessions,leads\\n2026-06,1200,18\\n2026-07,1350,21\\n2026-08,1400,22\\n"
      );
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Analyze CSV").click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Monthly series (3 months)"),
      15000,
      "CSV fallback 3-month series",
    );

    // Navigate back to '/' and confirm overview reflects updated locked baseline checkpoint (not stale goal 25)
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      `() => {
        const acmeRow = Array.from(document.querySelectorAll("tbody tr")).find(tr => tr.innerText.includes(${JSON.stringify(alpha.name)}));
        return Boolean(acmeRow && acmeRow.innerText.includes("goal 23") && !acmeRow.innerText.includes("goal 25"));
      }`,
      15000,
      "Overview reflects updated baseline checkpoint goal 23",
    );
    assertZeroErrors("T5-B4");

    // ── T5-B5: ContentOptimizer URL validation, tab switch clears error, FAQ JSON-LD ──
    console.log("Running T5-B5: ContentOptimizer tab switching & validation...");
    await cdp.navigate(`${WEB_URL}/${alpha.slug}/content-optimizer`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('input[aria-label="Page address"]')),
      15000,
      "Content optimizer for T5-B5",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Page address"]'), "foo");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      Array.from(document.querySelectorAll("form button[type='submit']")).find(b => b.textContent.trim() === "Open").click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("at least 8 characters"),
      5000,
      "Short URL client-side validation error",
    );

    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[aria-label="Page address"]'), ${JSON.stringify(alpha.unranked_optimizer_url)});
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      Array.from(document.querySelectorAll("form button[type='submit']")).find(b => b.textContent.trim() === "Open").click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('button[role="tab"]')),
      15000,
      "Optimizer tabs rendered",
    );

    // Switch to 'Work in these terms' tab, trigger blank keyword error, switch to 'Write the FAQ' -> error clears!
    await cdp.evalExpr(`(() => {
      const tab = Array.from(document.querySelectorAll('button[role="tab"]')).find(b => b.textContent.includes("Work in these terms"));
      tab.click();
    })()`);
    await sleep(100);
    await cdp.evalExpr(`(() => {
      const askBtn = Array.from(document.querySelectorAll("button"))
        .find(b => b.getAttribute("role") !== "tab" && b.textContent.trim() === "Work in these terms");
      askBtn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(document.querySelector('[role="alert"]')?.innerText?.includes("Enter a target keyword")),
      5000,
      "Blank target keyword error on terms tab",
    );
    await cdp.evalExpr(`(() => {
      const tab = Array.from(document.querySelectorAll('button[role="tab"]')).find(b => b.textContent.includes("Write the FAQ"));
      tab.click();
    })()`);
    await cdp.waitFor(
      () => !document.querySelector('[role="alert"]'),
      5000,
      "Tab switch clears validation error",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      setReactValue(document.querySelector('input[placeholder="e.g. emergency plumbing repair"]'), "copper pipe repiping");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const askBtn = Array.from(document.querySelectorAll("button"))
        .find(b => b.getAttribute("role") !== "tab" && b.textContent.trim() === "Write the FAQ");
      askBtn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Copy the FAQ markup"),
      25000,
      "Completed FAQ draft with JSON-LD markup",
    );
    assertZeroErrors("T5-B5");

    // ── T5-B7: BaselineBuilder conversion-scope parity (lead_gen + ecommerce with lingering lead) ──
    console.log("Running T5-B7: Baseline conversion parity (lead_gen & mixed ecommerce)...");
    await cdp.navigate(`${WEB_URL}/${beta.slug}/settings/baseline`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Modeled Baseline & 12-Month Projection") &&
        Boolean(Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 1"))),
      20000,
      "Beta lead_gen baseline modeled & ready to lock",
    );
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 1"));
      btn.click();
    })()`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Current Locked Baseline (v1)") &&
        document.body.innerText.includes("Events: book_appointment") &&
        !document.body.innerText.includes("Events: book_appointment, purchase"),
      20000,
      "Beta v1 locked counting only lead_gen event book_appointment",
    );

    // Switch beta business_model to ecommerce while book_appointment (lead) remains active, then re-lock v2 with zero UI deadlock
    await cdp.navigate(`${WEB_URL}/${beta.slug}/settings`);
    await cdp.waitFor(
      () => Boolean(Array.from(document.querySelectorAll("select")).find(s => Array.from(s.options).some(o => o.value === "ecommerce"))),
      15000,
      "Beta general settings business model select",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const sel = Array.from(document.querySelectorAll("select")).find(s => Array.from(s.options).some(o => o.value === "ecommerce"));
      setReactValue(sel, "ecommerce");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("form button[type='submit']")).find(b => b.textContent.trim().startsWith("Save"));
      if (!btn) throw new Error("General settings Save button not found");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Saved"),
      15000,
      "Beta business_model saved as ecommerce",
    );

    await cdp.navigate(`${WEB_URL}/${beta.slug}/settings/baseline`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Current Locked Baseline (v1)") &&
        (document.body.textContent || "").includes("Modeled orders / mo"),
      20000,
      "Beta ecommerce modeled baseline loaded",
    );
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Re-baseline");
      btn.click();
    })()`);
    await cdp.waitFor(
      () => Boolean(Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 2"))),
      5000,
      "Beta ecommerce re-baseline v2 form",
    );
    await cdp.evalExpr(`(() => {
      ${setValHelper}
      const sel = Array.from(document.querySelectorAll("select")).find(s => Array.from(s.options).some(o => o.value === "definition_change"));
      setReactValue(sel, "definition_change");
      const noteArea = document.querySelector("form textarea");
      setReactValue(noteArea, "Switched client model to ecommerce purchase conversions.");
    })()`);
    await sleep(50);
    await cdp.evalExpr(`(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Lock as version 2"));
      btn.click();
    })()`);
    await cdp.waitFor(
      () =>
        document.body.innerText.includes("Current Locked Baseline (v2)") &&
        document.body.innerText.includes("Events: purchase"),
      20000,
      "Beta ecommerce v2 locked cleanly despite lingering active lead",
    );
    assertZeroErrors("T5-B7");

    // ── T5-B2: Multi-tenant RBAC in Chrome (SMA_TEAM & CLIENT_VIEWER) ───────
    console.log("Running T5-B2: Multi-tenant RBAC (SMA_TEAM & CLIENT_VIEWER)...");
    const teamToken = await mintSessionCookie(manifest.users.team.email, "Team Member");
    await cdp.send("Network.setCookie", {
      name: "authjs.session-token",
      value: teamToken,
      url: WEB_URL,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      `() =>
        document.querySelector("h1")?.textContent?.includes("All clients") &&
        document.body.innerText.includes(${JSON.stringify(alpha.name)})`,
      15000,
      "SMA_TEAM sees assigned Acme Plumbing",
    );
    const teamText = await cdp.evalExpr(`document.body.innerText`);
    assert.ok(!teamText.includes(beta.name), "SMA_TEAM must not see unassigned Beacon Dental");
    assertZeroErrors("T5-B2-team");

    const viewerToken = await mintSessionCookie(manifest.users.viewer.email, "Client Viewer");
    await cdp.send("Network.setCookie", {
      name: "authjs.session-token",
      value: viewerToken,
      url: WEB_URL,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });
    await cdp.navigate(`${WEB_URL}/`);
    await cdp.waitFor(
      () => document.body.innerText.includes("Only SMA staff can view the all-clients overview."),
      15000,
      "CLIENT_VIEWER friendly 403 message on '/'",
    );
    assertZeroErrors("T5-B2-viewer");

    console.log("ALL 5 BROWSER E2E SCENARIOS PASSED (S5, S1, S2, S3, S4) WITH ZERO ERRORS.");
    console.log("ALL 7 TIER-5 BROWSER SCENARIOS PASSED (T5-B6, T5-B1, T5-B3, T5-B4, T5-B5, T5-B7, T5-B2) WITH ZERO ERRORS.");
  } finally {
    cdp.close();
    await chrome.close();
  }
}

runSuite().catch((err) => {
  console.error("WEB E2E FAILED:", err);
  process.exitCode = 1;
});
