// deobfuscate.js
// Uso: node deobfuscate.js < arquivo_ofuscado.html
// Lê o HTML/JS ofuscado do stdin, roda o "desempacotador" (loader) em uma
// sandbox isolada usando o módulo nativo `vm`, e intercepta as chamadas de
// Function(...)/eval(...) que o loader normalmente usaria para EXECUTAR o
// payload final — em vez de rodar, apenas devolvemos a string capturada.
//
// Isso evita executar de fato qualquer ação do código (fetch, DOM, etc.),
// então serve só para exibir/analisar o JS desofuscado.

const vm = require("vm");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function extractScriptBody(raw) {
  // Remove wrapper HTML e extrai o conteúdo de <script>...</script>
  const m = raw.match(/<script[^>]*>([\s\S]*?)<\/script>/i);
  return m ? m[1] : raw;
}

async function main() {
  const raw = await readStdin();
  const code = extractScriptBody(raw);

  const capturedPayloads = [];

  // Sandbox mínima: sem acesso a rede, DOM real, fs, etc.
  // 'window' e 'document' são stubs vazios só para o loader não quebrar
  // ao checar coisas como document.characterSet.
  const sandbox = {
    console: {
      log: (...args) => capturedPayloads.push({ type: "console.log", value: args.join(" ") }),
    },
    window: {},
    document: {
      characterSet: "UTF-8",
      addEventListener: () => {},
      removeEventListener: () => {},
    },
    // Interceptamos Function real: quando o loader chama
    // Function("codigo")(...), capturamos "codigo" em vez de criar
    // e executar a function de verdade.
    Function: function (...args) {
      const body = args[args.length - 1];
      if (typeof body === "string") {
        capturedPayloads.push({ type: "Function()", value: body });
      }
      // Retorna uma função inofensiva (no-op) para o loader poder
      // "chamar" sem quebrar, mas sem executar nada de real.
      return function () {
        return undefined;
      };
    },
    eval: function (body) {
      if (typeof body === "string") {
        capturedPayloads.push({ type: "eval()", value: body });
      }
      return undefined;
    },
    setTimeout: () => {},
    setInterval: () => {},
  };
  sandbox.window.document = sandbox.document;
  sandbox.window.eval = sandbox.eval;
  sandbox.globalThis = sandbox;

  const context = vm.createContext(sandbox);

  try {
    vm.runInContext(code, context, {
      timeout: 5000, // 5s: evita loop infinito consumindo CPU no Railway
      microtaskMode: "afterEvaluate",
    });
  } catch (err) {
    // Muitos loaders lançam erro de propósito (anti-debug) após capturar
    // o que precisávamos — isso não é necessariamente falha nossa.
    capturedPayloads.push({ type: "error", value: String(err && err.message) });
  }

  process.stdout.write(JSON.stringify(capturedPayloads));
}

main().catch((err) => {
  process.stderr.write(String(err));
  process.exit(1);
});
