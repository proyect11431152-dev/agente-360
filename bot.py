"""
Analista de Negocios 360 — Telegram Bot
Hace 5 preguntas, llama a Claude con web_search y devuelve el análisis completo.
"""

import asyncio
import os

import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# --- Estados de la conversación ---
Q1, Q2, Q3, Q4, Q5 = range(5)

QUESTIONS = [
    "¿Cuál es tu negocio? Descríbelo en una frase.",
    "¿Qué vendes exactamente? Productos, servicios, precios aproximados.",
    "¿Quién es tu cliente ideal?",
    "¿Cuántas personas trabajan y qué hace cada una?",
    "¿Qué es lo que más te quita tiempo o te estresa del día a día?",
]

PROMPT_TEMPLATE = """\
Eres un Analista de Negocios 360 experto en automatización con IA. \
El usuario te dio esta información sobre su negocio:

{answers_block}

Busca en la web los modelos y herramientas de IA más actuales disponibles en 2026. \
Luego entrega un análisis completo con estas 7 secciones: \
1. Anatomía del negocio \
2. Operaciones diarias \
3. Dolores y fricciones \
4. Oportunidades de automatización con IA (modelos, herramientas, costos reales 2026) \
5. Cálculo de ROI \
6. Riesgos y limitaciones \
7. Plan de implementación (esta semana, primer mes, tres meses). \
Sé específico, usa datos reales y habla directo.\
"""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"] = []
    await update.message.reply_text(
        "👋 ¡Bienvenido al *Analista de Negocios 360*!\n\n"
        "Voy a hacerte 5 preguntas sobre tu negocio. "
        "Al final recibirás un análisis completo con oportunidades reales de automatización con IA.\n\n"
        f"*Pregunta 1 de 5:*\n{QUESTIONS[0]}",
        parse_mode="Markdown",
    )
    return Q1


async def _save_and_ask_next(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    next_index: int,
    next_state: int,
) -> int:
    context.user_data["answers"].append(update.message.text)
    await update.message.reply_text(
        f"*Pregunta {next_index + 1} de 5:*\n{QUESTIONS[next_index]}",
        parse_mode="Markdown",
    )
    return next_state


async def q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_and_ask_next(update, context, 1, Q2)


async def q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_and_ask_next(update, context, 2, Q3)


async def q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_and_ask_next(update, context, 3, Q4)


async def q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_and_ask_next(update, context, 4, Q5)


async def q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"].append(update.message.text)
    answers = context.user_data["answers"]

    await update.message.reply_text(
        "⏳ Analizando tu negocio con IA y buscando herramientas 2026... "
        "Esto puede tardar 1-2 minutos. Dame un momento."
    )

    answers_block = "\n\n".join(
        f"Pregunta {i + 1}: {QUESTIONS[i]}\nRespuesta: {answers[i]}"
        for i in range(5)
    )
    prompt = PROMPT_TEMPLATE.format(answers_block=answers_block)

    try:
        result = await asyncio.to_thread(_call_anthropic, prompt)
    except Exception as exc:
        await update.message.reply_text(
            f"❌ Error al generar el análisis: {exc}\n\nIntenta de nuevo con /start."
        )
        return ConversationHandler.END

    if not result.strip():
        await update.message.reply_text(
            "No se pudo generar el análisis. Intenta de nuevo con /start."
        )
        return ConversationHandler.END

    # Enviar en partes de máximo 4000 caracteres
    chunk_size = 4000
    for i in range(0, len(result), chunk_size):
        await update.message.reply_text(result[i : i + chunk_size])

    await update.message.reply_text(
        "✅ ¡Análisis completo!\n\nPara analizar otro negocio escribe /start."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Análisis cancelado. Escribe /start cuando quieras comenzar de nuevo."
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Llamada a la API de Anthropic (síncrona — se ejecuta en un hilo)
# ---------------------------------------------------------------------------

def _call_anthropic(prompt: str) -> str:
    """
    Llama a Claude con la herramienta web_search habilitada.
    Maneja el caso pause_turn (límite de iteraciones del servidor) reencadenando
    la conversación hasta MAX_CONTINUATIONS veces.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    result_parts: list[str] = []
    max_continuations = 5

    for _ in range(max_continuations):
        # Usamos streaming para evitar timeouts en respuestas largas
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        for block in response.content:
            if block.type == "text":
                result_parts.append(block.text)

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "pause_turn":
            # El servidor llegó al límite de iteraciones internas;
            # reenviamos para que continúe
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
            ]
            continue

        # Cualquier otro stop_reason — salir
        break

    return "".join(result_parts)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, q1)],
            Q2: [MessageHandler(filters.TEXT & ~filters.COMMAND, q2)],
            Q3: [MessageHandler(filters.TEXT & ~filters.COMMAND, q3)],
            Q4: [MessageHandler(filters.TEXT & ~filters.COMMAND, q4)],
            Q5: [MessageHandler(filters.TEXT & ~filters.COMMAND, q5)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    print("Bot iniciado. Esperando mensajes...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
