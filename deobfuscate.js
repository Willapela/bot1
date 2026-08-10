/**
 * deobfuscate.js
 * Sandbox vm com Function/eval DENTRO do contexto + captura document.write
 */

const vm = require("vm");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function extractScriptBody(raw) {
  const m = raw.match(/<script[^>]*>([\s\S]*?)<\/script>/i);
  return m ? m[1] : raw;
}

async function main() {
  const raw = await readStdin();
  const code = extractScriptBody(raw);
  const captured = [];

  let context = null;

  const document = {
    characterSet: "UTF-8",
    charset: "UTF-8",
    readyState: "complete",
    write(html) {
      captured.push({ type: "document.write", value: String(html) });
    },
    writeln(html) {
      captured.push({ type: "document.write", value: String(html) + "\n" });
    },
    currentScript: { remove() {}, textContent: "" },
    createElement(tag) {
      return {
        tagName: String(tag || "div").toUpperCase(),
        style: {},
        setAttribute() {},
        getAttribute() { return null; },
        appendChild() {},
        remove() {},
      };
    },
    getElementsByTagName() { return []; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    getElementById() { return null; },
    addEventListener() {},
    removeEventListener() {},
    body: { appendChild() {}, style: {}, innerHTML: "" },
    head: { appendChild() {}, style: {} },
    documentElement: { style: {}, getAttribute() { return null; } },
  };

  class CSSStyleSheet {
    insertRule(rule) {
      captured.push({ type: "insertRule", value: String(rule) });
      return 0;
    }
    addRule(s, r) {
      captured.push({ type: "insertRule", value: String(s) + "{" + String(r) + "}" });
    }
  }

  function sandboxedFunction(...args) {
    const body = args[args.length - 1];
    const params = args.slice(0, -1).map(String);

    if (typeof body === "string" && body.length > 50) {
      captured.push({ type: "Function()", value: body });
    }

    return function (...callArgs) {
      if (!context) return undefined;
      try {
        const paramList = params.join(",");
        const wrapper =
          "(function(" + paramList + "){\n" + String(body) + "\n})";
        const fn = vm.runInContext(wrapper, context, { timeout: 8000 });
        return fn.apply(this, callArgs);
      } catch (e) {
        captured.push({
          type: "error",
          value: "Function exec: " + (e && e.message ? e.message : String(e)),
        });
        return undefined;
      }
    };
  }

  function sandboxedEval(src) {
    if (typeof src === "string" && src.length > 50) {
      captured.push({ type: "eval()", value: src });
    }
    if (!context) return undefined;
    try {
      return vm.runInContext(String(src), context, { timeout: 8000 });
    } catch (e) {
      captured.push({
        type: "error",
        value: "eval: " + (e && e.message ? e.message : String(e)),
      });
      return undefined;
    }
  }

  const windowObj = {
    document,
    console: {
      log: (...a) => captured.push({ type: "console.log", value: a.join(" ") }),
      warn() {},
      error() {},
    },
    navigator: { userAgent: "Mozilla/5.0" },
    location: { href: "about:blank", hostname: "localhost", protocol: "https:" },
    setTimeout(fn) {
      try { if (typeof fn === "function") fn(); } catch (_) {}
      return 0;
    },
    setInterval() { return 0; },
    clearTimeout() {},
    clearInterval() {},
    addEventListener() {},
    removeEventListener() {},
    CSSStyleSheet,
    fetch: () =>
      Promise.resolve({
        ok: false,
        text: async () => "",
        json: async () => ({}),
      }),
    XMLHttpRequest: function () {
      this.open = () => {};
      this.send = () => {};
      this.setRequestHeader = () => {};
      this.addEventListener = () => {};
    },
    atob: (s) => Buffer.from(String(s), "base64").toString("binary"),
    btoa: (s) => Buffer.from(String(s), "binary").toString("base64"),
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
    Function: sandboxedFunction,
    eval: sandboxedEval,
  };

  windowObj.window = windowObj;
  windowObj.self = windowObj;
  windowObj.globalThis = windowObj;
  windowObj.document.defaultView = windowObj;

  const sandbox = {
    window: windowObj,
    document,
    self: windowObj,
    globalThis: windowObj,
    console: windowObj.console,
    navigator: windowObj.navigator,
    location: windowObj.location,
    Function: sandboxedFunction,
    eval: sandboxedEval,
    setTimeout: windowObj.setTimeout,
    setInterval: windowObj.setInterval,
    clearTimeout: windowObj.clearTimeout,
    clearInterval: windowObj.clearInterval,
    CSSStyleSheet,
    fetch: windowObj.fetch,
    XMLHttpRequest: windowObj.XMLHttpRequest,
    atob: windowObj.atob,
    btoa: windowObj.btoa,
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

  context = vm.createContext(sandbox);

  try {
    vm.runInContext(code, context, {
      timeout: 15000,
      microtaskMode: "afterEvaluate",
    });
  } catch (err) {
    captured.push({
      type: "error",
      value: String(err && err.message ? err.message : err),
    });
  }

  process.stdout.write(JSON.stringify(captured));
}

main().catch((err) => {
  process.stderr.write(String(err));
  process.exit(1);
});
