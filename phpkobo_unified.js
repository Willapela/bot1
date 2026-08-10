/**
 * phpkobo_unified.js
 * Executa payload phpkobo (ou camada do sandbox) com hook em document.write
 * Saída: JSON { ok, html, css, method, error? }
 */

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function stripHeader(raw) {
  return raw.replace(/^\/\*[\s\S]*?\*\/\s*/m, "").trim();
}

function extractPayload(raw) {
  raw = stripHeader(raw);

  let m = raw.match(/;?\s*Function\s*\(\s*(['"`])([\s\S]*?)\1\s*\)\s*\(\s*\)/);
  if (m) return m[0];

  m = raw.match(/\(function\s*\([^)]*\)\s*\{[\s\S]{200,}?\}\s*\)\s*\(\s*\{?\s*\}\s*\)/);
  if (m) return m[0];

  const scripts = [...raw.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map((x) => x[1]);
  if (scripts.length) {
    const biggest = scripts.sort((a, b) => b.length - a.length)[0];
    if (biggest.length > 500) return biggest;
  }

  return raw;
}

function runWithHooks(code) {
  const capturedHtml = [];
  const capturedCss = [];
  const capturedLogs = [];

  const document = {
    characterSet: "UTF-8",
    charset: "UTF-8",
    readyState: "complete",
    write(html) {
      capturedHtml.push(String(html));
    },
    writeln(html) {
      capturedHtml.push(String(html) + "\n");
    },
    currentScript: {
      remove() {},
      textContent: code.slice(0, 200),
    },
    createElement(tag) {
      return {
        tagName: String(tag).toUpperCase(),
        style: {},
        setAttribute() {},
        getAttribute() {
          return null;
        },
        appendChild() {},
        remove() {},
      };
    },
    getElementsByTagName() {
      return [];
    },
    querySelectorAll() {
      return [];
    },
    querySelector() {
      return null;
    },
    getElementById() {
      return null;
    },
    addEventListener() {},
    removeEventListener() {},
    body: {
      appendChild() {},
      style: {},
      innerHTML: "",
    },
    head: {
      appendChild() {},
      style: {},
    },
    documentElement: {
      style: {},
      getAttribute() {
        return null;
      },
    },
  };

  class CSSStyleSheet {
    insertRule(rule) {
      capturedCss.push(String(rule));
      return 0;
    }
    addRule(s, r) {
      capturedCss.push(String(s) + "{" + String(r) + "}");
    }
  }

  const fetch = () =>
    Promise.resolve({
      ok: false,
      text: async () => "",
      json: async () => ({}),
    });

  function XMLHttpRequest() {
    this.open = () => {};
    this.send = () => {};
    this.setRequestHeader = () => {};
    this.addEventListener = () => {};
  }

  const windowObj = {
    document,
    Function: Function,
    console: {
      log: (...a) => capturedLogs.push(a.join(" ")),
      warn: () => {},
      error: () => {},
    },
    navigator: { userAgent: "Mozilla/5.0 phpkobo-unified" },
    location: { href: "about:blank", hostname: "localhost", protocol: "https:" },
    setTimeout: (fn) => {
      try {
        if (typeof fn === "function") fn();
      } catch (_) {}
      return 0;
    },
    setInterval: () => 0,
    clearTimeout: () => {},
    clearInterval: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    CSSStyleSheet,
    fetch,
    XMLHttpRequest,
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
    parseInt,
    parseFloat,
    isNaN,
    String,
    Number,
    Array,
    Object,
    Math,
    JSON,
    Date,
    RegExp,
    Error,
    TypeError,
    ReferenceError,
    encodeURIComponent,
    decodeURIComponent,
    escape,
    unescape,
  };

  windowObj.window = windowObj;
  windowObj.self = windowObj;
  windowObj.globalThis = windowObj;
  windowObj.document.defaultView = windowObj;

  windowObj.eval = function (src) {
    return new Function(
      "window",
      "document",
      "self",
      "with(window){return eval(" + JSON.stringify(src) + ")}"
    )(windowObj, document, windowObj);
  };

  global.document = document;
  global.window = windowObj;
  global.self = windowObj;
  global.navigator = windowObj.navigator;
  global.location = windowObj.location;
  global.CSSStyleSheet = CSSStyleSheet;
  global.fetch = fetch;
  global.XMLHttpRequest = XMLHttpRequest;

  let evalError = null;
  try {
    const runner = new Function(
      "window",
      "document",
      "self",
      "console",
      `
      with (window) {
        ${code}
      }
      `
    );
    runner(windowObj, document, windowObj, windowObj.console);
  } catch (e) {
    evalError = (e && e.message) || String(e);
  }

  return {
    html: capturedHtml.join(""),
    css: capturedCss.join("\n"),
    logs: capturedLogs,
    evalError,
  };
}

async function main() {
  let raw = "";
  try {
    raw = await readStdin();
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: "stdin: " + e.message }));
    process.exit(1);
  }

  if (!raw || raw.trim().length < 30) {
    process.stdout.write(JSON.stringify({ ok: false, error: "input vazio" }));
    process.exit(1);
  }

  const payload = extractPayload(raw);

  const timer = setTimeout(() => {
    process.stdout.write(JSON.stringify({ ok: false, error: "timeout 20s" }));
    process.exit(1);
  }, 20000);

  let result;
  try {
    result = runWithHooks(payload);
  } catch (e) {
    clearTimeout(timer);
    process.stdout.write(JSON.stringify({ ok: false, error: e.message || String(e) }));
    process.exit(1);
  }
  clearTimeout(timer);

  const html = (result.html || "").trim();
  const css = (result.css || "").trim();

  if (!html && !css) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        error: result.evalError
          ? "eval falhou: " + result.evalError
          : "nada em document.write",
        method: "phpkobo-unified",
      })
    );
    return;
  }

  let out = "";
  if (css) out += "<style>\n" + css + "\n</style>\n";
  if (html) out += html;

  process.stdout.write(
    JSON.stringify({
      ok: true,
      method: "phpkobo-unified (document.write)",
      html: out,
      css,
    })
  );
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: e.message || String(e) }));
  process.exit(1);
});
