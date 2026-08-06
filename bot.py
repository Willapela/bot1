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


def extract_and_decode(raw: str) -> tuple[str | None, str]:
    """Retorna (resultado, método_usado)"""
    # 1. unescape('...') ou unescape("...")
    m = re.search(r"unescape\(\s*(['\"])(.*?)\1\s*\)", raw, re.DOTALL)
    if m:
        try:
            return js_unescape(m.group(2)), "unescape() / percent-encoding"
        except Exception:
            pass

    # 2. atob('...') ou atob("...")
    m = re.search(r"atob\(\s*(['\"])(.*?)\1\s*\)", raw, re.DOTALL)
    if m:
        res = try_base64(m.group(2))
        if res:
            return res, "atob() / base64"

    # 3. Tenta como string bruta
    payload = raw.strip().strip("'\"")

    if re.search(r'%[0-9a-fA-F]{2}|%u[0-9a-fA-F]{4}', payload, re.I):
        try:
            return js_unescape(payload), "unescape() / percent-encoding (auto)"
        except Exception:
            pass

    res = try_base64(payload)
    if res:
        return res, "atob() / base64 (auto)"

    return None, ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *Desofuscador de HTML*\n\n"
        "Envie o código ofuscado como *texto* ou como *arquivo* (.txt / .html)\n\n"
        "Eu devolvo o código limpo + o arquivo `.html` pronto para download.",
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
