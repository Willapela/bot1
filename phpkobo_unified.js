/**
 * phpkobo_unified.js
 * Desofuscador baseado no snippet unificado do UnbuiltAlmond8/PHPKoboDeobfuscator
 * + captura via mock de document.write / insertRule (sem browser real)
 *
 * Uso:
 *   node phpkobo_unified.js < input.html
 *   echo "..." | node phpkobo_unified.js
 *
 * Saída: JSON { ok, html, css, method, error? }
 */

const fs = require("fs");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function extractPhpkoboPayload(raw) {
  // 1) Function('...')()  ou  ;Function("...")()
  let m = raw.match(/;?\s*Function\s*\(\s*(['"`])([\s\S]*?)\1\s*\)\s*\(\s*\)/);
  if (m) return m[0];

  // 2) (function(...){ ... Function(...) ... })({})
  m = raw.match(/\(function\s*\([^)]*\)\s*\{[\s\S]{200,}?\}\s*\)\s*\(\s*\{?\s*\}\s*\)/);
  if (m) return m[0];

  // 3) script inteiro se parecer phpkobo
  const scripts = [...raw.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map((x) => x[1]);
  if (scripts.length) {
    const biggest = scripts.sort((a, b) => b.length - a.length)[0];
    if (
      biggest.includes("Function(") ||
      biggest.includes("phpkobo") ||
      biggest.includes("document.write") ||
      biggest.length > 3000
    ) {
      return biggest;
    }
  }

  // 4) fallback: o raw inteiro
  return raw;
}

function tryDeobfuscateLink(code) {
  // Link obfuscator (do README do UnbuiltAlmond8)
  try {
    const parts = code.split("=this;");
    if (parts.length < 2) return null;
    const objStr = parts[1].split("}")[0].split("=")[1] + "}";
    // eval controlado do objeto
    // eslint-disable-next-line no-new-func
    const obfuscated_object = new Function("return (" + objStr + ")")();
    let keyIndex = /-\d+/.exec(code) || /\+\d+/.exec(code);
    if (!keyIndex) return null;
    const key = Number(keyIndex[0]);
    const results = [];
    for (const prop of Object.keys(obfuscated_object)) {
      const obfuscated_value = obfuscated_object[prop];
      if (typeof obfuscated_value === "string") {
        const result = obfuscated_value
          .split(":")
          .map((p) => String.fromCharCode(obfuscated_object[p] + key))
          .join("");
        results.push(result);
      }
    }
    const link = results.filter((v) => v.includes(".") && !v.startsWith("a["))[0];
    return link || null;
  } catch {
    return null;
  }
}

function runWithHooks(code) {
  const capturedHtml = [];
  const capturedCss = [];

  // Mocks mínimos de browser
  const document = {
    write(html) {
      capturedHtml.push(String(html));
    },
    writeln(html) {
      capturedHtml.push(String(html) + "\n");
    },
    currentScript: null,
    createElement() {
      return {
        style: {},
        setAttribute() {},
        appendChild() {},
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
    body: { appendChild() {}, style: {} },
    head: { appendChild() {}, style: {} },
    documentElement: { style: {} },
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

  // Bloqueia rede
  const fetch = () => Promise.resolve({ ok: false, text: async () => "" });
  function XMLHttpRequest() {
    this.open = () => {};
    this.send = () => {};
    this.setRequestHeader = () => {};
  }

  const window = global;
  const self = global;
  const navigator = { userAgent: "phpkobo-unified" };
  const location = { href: "about:blank", hostname: "localhost" };

  // Injeta no escopo global do eval
  global.document = document;
  global.window = window;
  global.self = self;
  global.navigator = navigator;
  global.location = location;
  global.CSSStyleSheet = CSSStyleSheet;
  global.fetch = fetch;
  global.XMLHttpRequest = XMLHttpRequest;

  // Hook extra no prototype (como no snippet original)
  try {
    CSSStyleSheet.prototype.insertRule = function (rule) {
      capturedCss.push(String(rule));
      return 0;
    };
  } catch (_) {}

  let evalError = null;
  try {
    // eslint-disable-next-line no-eval
    eval(code);
  } catch (e) {
    evalError = e.message || String(e);
  }

  return {
    html: capturedHtml.join(""),
    css: capturedCss.join("\n"),
    evalError,
  };
}

async function main() {
  let raw = "";
  try {
    raw = await readStdin();
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: "stdin read failed: " + e.message }));
    process.exit(1);
  }

  if (!raw || raw.trim().length < 50) {
    process.stdout.write(JSON.stringify({ ok: false, error: "input vazio ou muito curto" }));
    process.exit(1);
  }

  // Tenta link obfuscator primeiro
  const link = tryDeobfuscateLink(raw);
  if (link) {
    process.stdout.write(
      JSON.stringify({
        ok: true,
        method: "phpkobo-link",
        html: link,
        css: "",
      })
    );
    return;
  }

  const payload = extractPhpkoboPayload(raw);

  // Timeout de segurança
  const timer = setTimeout(() => {
    process.stdout.write(
      JSON.stringify({ ok: false, error: "timeout (15s) ao executar payload phpkobo" })
    );
    process.exit(1);
  }, 15000);

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
          ? "eval falhou e nada foi capturado: " + result.evalError
          : "nada capturado em document.write / insertRule",
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
      method: "phpkobo-unified (document.write hook)",
      html: out,
      css,
    })
  );
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: e.message || String(e) }));
  process.exit(1);
});
