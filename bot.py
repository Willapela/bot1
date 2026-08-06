import os
import re
from io import BytesIO
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

TOKEN = os.environ.get("TOKEN")

def js_unescape(s: str) -> str:
    """Versão Python do unescape() clássico (mais tolerante)"""
    # %uXXXX (unicode)
    s = re.sub(
        r'%u([0-9a-fA-F]{4})',
        lambda m: chr(int(m.group(1), 16)),
        s,
        flags=re.I
    )
    # %XX (bytes)
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


def try_phpkobo(raw: str) -> tuple[str | None, str]:
    """
    Extração experimental do tipo phpkobo.com/html-obfuscator.
    Remove a casca do Function("...") e devolve o código interno.
    Não executa o JS — só extrai o conteúdo.
    """
    # Detecta o comentário ou a estrutura típica
    is_phpkobo = (
        "phpkobo.com" in raw.lower()
        or "html-obfuscator" in raw.lower()
        or (raw.strip().startswith((";Function(", "Function(")) and len(raw) > 5000)
    )

    if not is_phpkobo:
        # Também tenta achar Function("...") mesmo sem o comentário
        if "Function(" not in raw or len(raw) < 3000:
            return None, ""

    # Remove tags HTML e comentários
    js = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    js = re.sub(r"<!DOCTYPE[^>]*>", "", js, flags=re.I)
    js = re.sub(r"<meta[^>]*>", "", js, flags=re.I)
    js = re.sub(r"</?script[^>]*>", "", js, flags=re.I)
    js = js.strip()

    # Tenta extrair o argumento de Function("...") ou Function('...')
    # O argumento costuma ser muito grande e terminar com ")();"
    m = re.search(
        r"""Function\s*\(\s*(['"])(.*?)\1\s*\)\s*\(\s*\)""",
        js,
        re.DOTALL,
    )
    if m:
        inner = m.group(2)
        # Desescapa sequências comuns
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

        # Decodifica \xNN e \uNNNN se existirem
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
            "   EXTRAÇÃO EXPERIMENTAL (phpkobo / Function packing)\n"
            "   O código abaixo ainda pode estar parcialmente ofuscado.\n"
            "   Não é uma desofuscação completa — apenas remove a casca.\n"
            "   ============================================================ */\n\n"
        )
        return header + inner, "phpkobo (extração experimental)"

    return None, ""


def extract_and_decode(raw: str) -> tuple[str | None, str]:
    """Retorna (resultado, método_usado)"""

    # 0. phpkobo / Function packing PRIMEIRO
    # (arquivos grandes travam nos regex de unescape/atob se ficarem por último)
    if (
        "phpkobo.com" in raw.lower()
        or "html-obfuscator" in raw.lower()
        or ("Function(" in raw and len(raw) > 8000)
    ):
        result, method = try_phpkobo(raw)
        if result:
            return result, method

    # 1. unescape — versão rápida (sem regex pesado)
    idx = raw.find("unescape(")
    if idx != -1:
        rest = raw[idx + 9:].lstrip()
        if rest and rest[0] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            if end != -1:
                try:
                    return js_unescape(rest[1:end]), "unescape() / percent-encoding"
                except Exception:
                    pass

    # 2. atob — versão rápida
    idx = raw.find("atob(")
    if idx != -1:
        rest = raw[idx + 5:].lstrip()
        if rest and rest[0] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            if end != -1:
                res = try_base64(rest[1:end])
                if res:
                    return res, "atob() / base64"

    # 3. Tenta como string bruta (percent / base64)
    payload = raw.strip().strip("'\"")

    if re.search(r"%[0-9a-fA-F]{2}|%u[0-9a-fA-F]{4}", payload[:5000], re.I):
        try:
            return js_unescape(payload), "unescape() / percent-encoding (auto)"
        except Exception:
            pass

    if len(payload) < 200000:
        res = try_base64(payload)
        if res:
            return res, "atob() / base64 (auto)"

    # 4. Última tentativa phpkobo
    result, method = try_phpkobo(raw)
    if result:
        return result, method

    return None, ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *Desofuscador de HTML*\n\n"
        "Envie o código ofuscado como *texto* ou como *arquivo* (.txt / .html)\n\n"
        "Formatos suportados:\n"
        "• `unescape()` / percent-encoding (html-code-generator)\n"
        "• `atob()` / base64\n"
        "• phpkobo (extração experimental)\n\n"
        "Eu devolvo o código + o arquivo `.html` pronto para download.",
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    if not raw or len(raw) < 20:
        await update.message.reply_text("Envie o código ofuscado completo.")
        return

    msg = await update.message.reply_text("⏳ Desofuscando...")

    result, method = extract_and_decode(raw)

    if not result:
        await msg.edit_text(
            "❌ Não consegui identificar o formato.\n\n"
            "Cole o script completo com `unescape(...)` ou `atob(...)`."
        )
        return

    await msg.edit_text(f"✅ Decodificado com sucesso!\nMétodo: *{method}*", parse_mode="Markdown")

    # Envia o arquivo .html
    try:
        # Trata surrogates e caracteres inválidos (erro utf-8)
        clean = result.encode('utf-8', errors='replace').decode('utf-8')
        bio = BytesIO(clean.encode('utf-8'))
        bio.seek(0)
        await update.message.reply_document(
            document=bio,
            filename="decodificado.html",
            caption=f"✅ Arquivo pronto!\nMétodo usado: {method}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar o arquivo: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    # Limite de tamanho (Telegram permite até 20MB, mas vamos limitar)
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

    result, method = extract_and_decode(raw)

    if not result:
        await msg.edit_text("❌ Não consegui desofuscar esse arquivo.")
        return

    await msg.edit_text(f"✅ Decodificado com sucesso!\nMétodo: *{method}*", parse_mode="Markdown")

    # Envia o arquivo .html
    try:
        # Trata surrogates e caracteres inválidos (erro utf-8)
        clean = result.encode('utf-8', errors='replace').decode('utf-8')
        bio = BytesIO(clean.encode('utf-8'))
        bio.seek(0)
        await update.message.reply_document(
            document=bio,
            filename="decodificado.html",
            caption=f"✅ Arquivo pronto!\nMétodo usado: {method}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar o arquivo: {e}")


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
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
