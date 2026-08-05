# Bot Desofuscador de HTML (Telegram)

Bot que recebe código HTML ofuscado (`unescape` / `atob`) e devolve o código limpo + arquivo `.html`.

## Como usar no Railway

1. Crie um novo projeto no [Railway](https://railway.app)
2. Conecte este repositório
3. Vá em **Variables** e adicione:
   ```
   TOKEN = seu_token_do_botfather
   ```
4. O serviço será detectado automaticamente como **Worker**

## Comandos

- `/start` ou `/desofuscar` → Mostra as instruções
- Envie texto ofuscado → Recebe o `.html` limpo
- Envie arquivo `.txt` ou `.html` → Recebe o `.html` limpo

## Formatos suportados

- `document.write(unescape('...'))`
- `document.write(atob('...'))`
- String percent-encoded pura
- String base64 pura
