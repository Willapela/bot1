import subprocess
import tempfile
import os

def is_js_obfuscator(code: str) -> bool:
    """Heurística: detecta o padrão de javascript-obfuscator (array de strings + shift/push)."""
    markers = [
        "_0x", 
        "while (true)", "while(!![])",
        "['push']", ".push(", 
    ]
    hits = sum(1 for m in markers if m in code)
    return hits >= 2 and "_0x" in code

def deobfuscate_js_obfuscator(code: str, timeout: int = 30) -> str:
    """
    Usa o webcrack (npm) para reverter ofuscação do tipo javascript-obfuscator.
    Retorna o código legível, ou levanta RuntimeError se falhar.
    """
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "input.js")
        out_dir = os.path.join(tmp, "out")
        with open(in_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            ["npx", "webcrack", in_path, "-o", out_dir],
            capture_output=True, text=True, timeout=timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"webcrack falhou: {result.stderr[:500]}")

        # webcrack normalmente gera deobfuscated.js dentro do out_dir
        out_file = os.path.join(out_dir, "deobfuscated.js")
        if not os.path.exists(out_file):
            # fallback: pega o primeiro .js gerado
            candidates = [f for f in os.listdir(out_dir) if f.endswith(".js")]
            if not candidates:
                raise RuntimeError("webcrack não gerou saída.")
            out_file = os.path.join(out_dir, candidates[0])

        with open(out_file, "r", encoding="utf-8") as f:
            return f.read()
