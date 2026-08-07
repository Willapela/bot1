def deobfuscate_js_obfuscator(code: str, timeout: int = 90) -> str:
    npx = _find_npx()

    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "input.js")
        out_dir = os.path.join(tmp, "out")   # NÃO criar a pasta aqui

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
            # fallback: pega qualquer .js gerado
            if not os.path.isdir(out_dir):
                raise RuntimeError("webcrack não criou a pasta de saída")
            candidates = [f for f in os.listdir(out_dir) if f.endswith(".js")]
            if not candidates:
                raise RuntimeError("webcrack não gerou saída .js")
            out_file = os.path.join(out_dir, candidates[0])

        with open(out_file, "r", encoding="utf-8") as f:
            return f.read()
