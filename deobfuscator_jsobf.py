import subprocess
import tempfile
import os
import shutil
import glob


def is_js_obfuscator(code: str) -> bool:
    """Heurística: detecta o padrão de javascript-obfuscator."""
    if not code or len(code) < 500:
        return False
    markers = [
        "_0x",
        "while (true)",
        "while(!![])",
        "['push']",
        ".push(",
    ]
    hits = sum(1 for m in markers if m in code)
    return hits >= 2 and "_0x" in code


def _find_npx() -> str:
    """Procura o npx em vários lugares comuns."""
    # 1) PATH normal
    path = shutil.which("npx")
    if path:
        return path

    # 2) Caminhos fixos comuns
    candidates = [
        "/usr/bin/npx",
        "/usr/local/bin/npx",
        "/bin/npx",
    ]

    # 3) Nix store (caso ainda use Nixpacks)
    candidates += glob.glob("/nix/store/*nodejs*/bin/npx")
    candidates += glob.glob("/nix/store/*-nodejs-*/bin/npx")

    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    # 4) Debug
    debug = []
    debug.append(f"PATH={os.environ.get('PATH', '')}")
    debug.append(f"which(npx)={shutil.which('npx')}")
    debug.append(f"which(node)={shutil.which('node')}")
    raise FileNotFoundError(
        "npx não encontrado. " + " | ".join(debug)
    )


def deobfuscate_js_obfuscator(code: str, timeout: int = 90) -> str:
    """
    Usa o webcrack (via npx) para reverter ofuscação do tipo javascript-obfuscator.
    """
    npx = _find_npx()

    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "input.js")
        out_dir = os.path.join(tmp, "out")  # NÃO criar a pasta antes

        with open(in_path, "w", encoding="utf-8") as f:
            f.write(code)

        env = os.environ.copy()
        npx_dir = os.path.dirname(npx)
        env["PATH"] = npx_dir + os.pathsep + env.get("PATH", "")

        result = subprocess.run(
            [npx, "--yes", "webcrack", in_path, "-o", out_dir],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:800]
            raise RuntimeError(f"webcrack falhou (code {result.returncode}): {err}")

        out_file = os.path.join(out_dir, "deobfuscated.js")
        if not os.path.exists(out_file):
            if not os.path.isdir(out_dir):
                raise RuntimeError("webcrack não criou a pasta de saída")
            candidates = [f for f in os.listdir(out_dir) if f.endswith(".js")]
            if not candidates:
                raise RuntimeError("webcrack não gerou saída .js")
            out_file = os.path.join(out_dir, candidates[0])

        with open(out_file, "r", encoding="utf-8") as f:
            return f.read()
