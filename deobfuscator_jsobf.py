import subprocess
import tempfile
import os
import shutil

def is_js_obfuscator(code: str) -> bool:
    """Heurística: detecta o padrão de javascript-obfuscator."""
    if not code or len(code) < 500:
        return False
    markers = [
        "_0x",
        "while (true)", "while(!![])",
        "['push']", ".push(",
    ]
    hits = sum(1 for m in markers if m in code)
    return hits >= 2 and "_0x" in code


def _find_npx() -> str:
    """Procura o npx em vários lugares comuns."""
    # 1) PATH normal
    path = shutil.which("npx")
    if path:
        return path

    # 2) Caminhos comuns no Linux / Railway / Nixpacks
    candidates = [
        "/usr/bin/npx",
        "/usr/local/bin/npx",
        "/root/.nvm/versions/node/current/bin/npx",
        "/home/railway/.nvm/versions/node/current/bin/npx",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    raise FileNotFoundError(
        "npx não encontrado. Instale Node.js no build do Railway "
        "(adicione nodejs no nixpacks.toml ou no Dockerfile)."
    )


def deobfuscate_js_obfuscator(code: str, timeout: int = 60) -> str:
    """
    Usa o webcrack (via npx) para reverter ofuscação do tipo javascript-obfuscator.
    """
    npx = _find_npx()

    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "input.js")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)

        with open(in_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Garante que o PATH do subprocess tenha o diretório do npx
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
            candidates = [f for f in os.listdir(out_dir) if f.endswith(".js")]
            if not candidates:
                raise RuntimeError("webcrack não gerou saída .js")
            out_file = os.path.join(out_dir, candidates[0])

        with open(out_file, "r", encoding="utf-8") as f:
            return f.read()
