import os
import re
import json
import shutil
import subprocess
from io import BytesIO
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# === Módulo javascript-obfuscator (você já subiu) ===
try:
    from deobfuscator_jsobf import is_js_obfuscator as _module_is_js_obf
    from deobfuscator_jsobf import deobfuscate_js_obfuscator
    HAS_JS_OBF_MODULE = True
except ImportError:
    HAS_JS_OBF_MODULE = False
    def deobfuscate_js_obfuscator(code: str) -> str:
        raise RuntimeError("Módulo deobfuscator_jsobf não encontrado")

TOKEN = os.environ.get("TOKEN")

NODE_SCRIPT = os.path.join(os.path.dirname(__file__), "deobfuscate.js")

MAX_INPUT_SIZE = 2_000_000
NODE_TIMEOUT_SECONDS = 8


# =====================================================================
# Detecção melhorada de javascript-obfuscator (funciona dentro de HTML)
# =====================================================================

def is_js_obfuscator(code: str) -> bool:
    """Detecta javascript-obfuscator mesmo quando está dentro de HTML."""
    if not code or len(code) < 2000:
        return False

    # Se o módulo externo tiver uma detecção própria, usa ela também
    if HAS_JS_OBF_MODULE:
        try:
            if _module_is_js_obf(code):
                return True
        except Exception:
            pass

    scripts = re.findall(r'<script[^>]*>(.*?)</script>', code, re.DOTALL | re.I)
    target = max(scripts, key=len) if scripts else code

    count_0x = len(re.findall(r'_0x[a-fA-F0-9]{4,}', target))
    has_function_0x = bool(re.search(r'function\s*\(\s*_0x[a-fA-F0-9]+', target))
    has_return_0x = bool(re.search(r'return\s+_0x[a-fA-F0-9]+\(', target))
    has_array_shuffle = bool(re.search(r'for\s*\(\s*(?:var|let|const)?\s*_0x[a-fA-F0-9]+\s*=', target))
    has_string_array = bool(re.search(r'(?:var|let|const)\s+_0x[a-fA-F0-9]+\s*=\s*\[', target))

    score = 0
    if count_0x > 80:       score += 3
    if count_0x > 300:      score += 2
    if has_function_0x:     score += 2
    if has_return_0x:       score += 1
    if has_array_shuffle:   score += 2
    if has_string_array:    score += 1

    return score >= 5


def extract_js_from_html(code: str) -> str:
    """Extrai o maior bloco <script> do HTML."""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', code, re.DOTALL | re.I)
    if not scripts:
        return code
    return max(scripts, key=len).strip()


# =====================================================================
# Funções antigas (unescape / base64 / phpkobo)
# =====================================================================

def js_unescape(s: str) -> str:
    s = re.sub(
        r'%u([0-9a-fA-F]{4})',
        lambda m: chr(int(m.group(1), 16)),
        s,
        flags=re.I
    )
    s = re.sub(
        r'%([0-9a-fA-F]{2})',
        lambda m: chr(int(m.group(1), 16)),
        s,
        flags=re.I
    )
    return s


def try_base64(s: str) -> str | None:
    import base64
    try:
        cleaned = re.sub(r'\s+', '', s.strip())
        if not re.fullmatch(r'[A-Za-z0-9+/=]+', cleaned):
            return None
        return base64.b64decode(cleaned).decode('utf-8', errors='replace')
    except Exception:
        return None


def node_available() -> bool:
    return shutil.which("node") is not None and os.path.exists(NODE_SCRIPT)


def try_phpkobo_sandbox(raw: str) -> tuple[str | None, str]:
    if not node_available():
        return None, ""

    if len(raw) > MAX_INPUT_SIZE:
        return None, "arquivo excede o limite de processamento seguro"

    try:
        proc = subprocess.run(
            ["node", NODE_SCRIPT],
            input=raw,
            capture_output=True,
            text=True,
            timeout=NODE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout ao executar sandbox (arquivo muito complexo)"
    except Exception as e:
        return None, f"erro ao chamar sandbox: {e}"

    if proc.returncode != 0 or not proc.stdout:
        return None, ""

    try:
        captured = json.loads(proc.stdout)
    except Exception:
        return None, ""

    candidates = [c["value"] for c in captured if c["type"] in ("Function()", "eval()")]
    if not candidates:
        return None, ""

    best = max(candidates, key=len)
    header = (
        "/* ============================================================\n"
        "   DESOFUSCAÇÃO VIA SANDBOX (Node vm, Function/eval interceptados)\n"
        "   O código abaixo foi capturado antes de ser executado de fato.\n"
        "   ============================================================ */\n\n"
    )
    return header + best, "phpkobo (sandbox Node)"


def try_phpkobo_regex(raw: str) -> tuple[str | None, str]:
    is_phpkobo = (
        "phpkobo.com" in raw.lower()
        or "html-obfuscator" in raw.lower()
        or (raw.strip().startswith((";Function(", "Function(")) and len(raw) > 5000)
    )
    if not is_phpkobo:
        if "Function(" not in raw or len(raw) < 3000:
            return None, ""

    js = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    js = re.sub(r"<!DOCTYPE[^>]*>", "", js, flags=re.I)
    js = re.sub(r"<meta[^>]*>", "", js, flags=re.I)
    js = re.sub(r"</?script[^>]*>", "", js, flags=re.I)
    js = js.strip()

    m = re.search(r"""Function\s*\(\s*(['"])(.*?)\1\s*\)\s*\(\s*\)""", js, re.DOTALL)
    if not m:
        return None, ""

    inner = m.group(2)
    try:
        inner = (
            inner.replace("\\\\", "\\")
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace("\\'", "'")
            .replace('\\"', '"')
        )
    except Exception:
        pass

    def decode_escapes(s):
        def repl_x(mo):
            try:
                return chr(int(mo.group(1), 16))
            except Exception:
                return mo.group(0)
        s = re.sub(r"\\x([0-9a-fA-F]{2})", repl_x, s)
        s = re.sub(r"\\u([0-9a-fA-F]{4})", repl_x, s)
        return s

    inner = decode_escapes(inner)

    header = (
        "/* ============================================================\n"
        "   EXTRAÇÃO EXPERIMENTAL (phpkobo / Function packing, regex)\n"
        "   Só remove a casca — não executa nada. Pode ainda estar cifrado.\n"
        "   ============================================================ */\n\n"
    )
    return header + inner, "phpkobo (extração experimental / regex)"


# =====================================================================
# Função principal de desofuscação
# =====================================================================

def extract_and_decode(raw: str) -> tuple[str | None, str, str]:
    """
    Retorna (resultado, método_usado, extensão)
    extensão: "js" ou "html"
    """

    # ---------------------------------------------------------------
    # 1) JAVASCRIPT-OBFUSCATOR (prioridade alta)
    # ---------------------------------------------------------------
    if is_js_obfuscator(raw):
        try:
            pure_js = extract_js_from_html(raw)
            result = deobfuscate_js_obfuscator(pure_js)
            if result and len(result.strip()) > 100:
                header = (
                    "/* ============================================================\n"
                    "   DESOFUSCAÇÃO: javascript-obfuscator\n"
                    "   ============================================================ */\n\n"
                )
                return header + result, "javascript-obfuscator", "js"
        except Exception:
            pass  # continua para os outros métodos

    # ---------------------------------------------------------------
    # 2) phpkobo / Function packing
    # ---------------------------------------------------------------
    is_phpkobo_like = (
        "phpkobo.com" in raw.lower()
        or "html-obfuscator" in raw.lower()
        or ("Function(" in raw and len(raw) > 8000)
    )

    if is_phpkobo_like:
        result, method = try_phpkobo_sandbox(raw)
        if result:
            return result, method, "html"

        result, method = try_phpkobo_regex(raw)
        if result:
            return result, method, "html"

    # ---------------------------------------------------------------
    # 3) unescape() / percent-encoding
    # ---------------------------------------------------------------
    idx = raw.find("unescape(")
    if idx != -1:
        rest = raw[idx + 9:].lstrip()
        if rest and rest[0] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            if end != -1:
                try:
                    return js_unescape(rest[1:end]), "unescape() / percent-encoding", "html"
                except Exception:
                    pass

    # ---------------------------------------------------------------
    # 4) atob() / base64
    # ---------------------------------------------------------------
    idx = raw.find("atob(")
    if idx != -1:
        rest = raw[idx + 5:].lstrip()
        if rest and rest[0] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            if end != -1:
                res = try_base64(rest[1:end])
                if res:
                    return res, "atob() / base64", "html"

    # ---------------------------------------------------------------
    # 5) Detecção automática
    # ---------------------------------------------------------------
    payload = raw.strip().strip("'\"")

    if re.search(r"%[0-9a-fA-F]{2}|%u[0-9a-fA-F]{4}", payload[:5000], re.I):
        try:
            return js_unescape(payload), "unescape() / percent-encoding (auto)", "html"
        except Exception:
            pass

    if len(payload) < 200000:
        res = try_base64(payload)
        if res:
            return res, "atob() / base64 (auto)", "html"

    return None, "", "html"


# =====================================================================
# Handlers do Telegram
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    node_status = "✅ disponível" if node_available() else "⚠️ indisponível (usando fallback regex)"
    js_obf_status = "✅ disponível" if HAS_JS_OBF_MODULE else "⚠️ módulo não encontrado"

    await update.message.reply_text(
        "🔓 *Desofuscador de HTML / JS*\n\n"
        "Envie o código ofuscado como *texto* ou como *arquivo* (.txt / .html / .js)\n\n"
        "Formatos suportados:\n"
        "• `unescape()` / percent-encoding\n"
        "• `atob()` / base64\n"
        "• phpkobo (sandbox Node ou regex)\n"
        "• **javascript-obfuscator**\n\n"
        f"Sandbox Node: {node_status}\n"
        f"JS-Obfuscator: {js_obf_status}\n\n"
        "Eu devolvo o código + o arquivo pronto para download.",
        parse_mode="Markdown"
    )


async def _process_and_reply(update: Update, msg, raw: str):
    if is_js_obfuscator(raw):
        await msg.edit_text(
            "🔍 Detectado padrão **javascript-obfuscator**...\n"
            "Processando (pode levar alguns segundos)..."
        )

    result, method, extension = extract_and_decode(raw)

    if not result:
        await msg.edit_text(
            "❌ Não consegui identificar/desofuscar o formato.\n\n"
            "Cole o script completo com `unescape(...)`, `atob(...)`, "
            "phpkobo ou javascript-obfuscator."
        )
        return

    await msg.edit_text(
        f"✅ Decodificado com sucesso!\nMétodo: *{method}*",
        parse_mode="Markdown"
    )

    try:
        clean = result.encode('utf-8', errors='replace').decode('utf-8')
        bio = BytesIO(clean.encode('utf-8'))
        bio.seek(0)

        filename = f"decodificado.{extension}"
        await update.message.reply_document(
            document=bio,
            filename=filename,
            caption=f"✅ Arquivo pronto!\nMétodo usado: {method}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar o arquivo: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    if not raw or len(raw) < 20:
        await update.message.reply_text("Envie o código ofuscado completo.")
        return

    if len(raw) > MAX_INPUT_SIZE:
        await update.message.reply_text("❌ Texto muito grande. Envie como arquivo (.txt/.html/.js).")
        return

    msg = await update.message.reply_text("⏳ Desofuscando...")
    await _process_and_reply(update, msg, raw)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ Arquivo muito grande (máximo 5MB).")
        return

    msg = await update.message.reply_text("⏳ Baixando e desofuscando arquivo...")

    try:
        file = await doc.get_file()
        data = await file.download_as_bytearray()
        raw = data.decode('utf-8', errors='replace')
    except Exception as e:
        await msg.edit_text(f"❌ Erro ao baixar o arquivo: {e}")
        return

    await _process_and_reply(update, msg, raw)


def main():
    if not TOKEN:
        print("❌ ERRO: Variável de ambiente TOKEN não definida!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("desofuscar", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("🤖 Bot desofuscador rodando...")
    print(f"   JS-Obfuscator: {'✅' if HAS_JS_OBF_MODULE else '❌ módulo não encontrado'}")
    print(f"   Node sandbox:  {'✅' if node_available() else '❌'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
