import asyncio
import os
import re 
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
from config import BOT_TOKEN, PANEL_BOT_TOKEN , supabase
from utils import db_execute  # اجرای غیرهمزمان کوئری‌های sync سوپابیس در thread pool

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
    handle_game_request,
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
            
    except telegram.error.BadRequest as e:
        if "Query is too old" in str(e):
            pass
        else:
            print(f"⚠️ Inline Panel BadRequest: {e}")
    except Exception as e:
        print(f"Error in async panel inline: {e}")

async def attach_game_buttons(update, context):
    if not context.args or len(context.args) < 3:
        return
        
    chat_id = int(context.args[0])
    msg_id = int(context.args[1])
    game_num = context.args[2]
    bot_username = context.bot.username

    keyboard = [
        [InlineKeyboardButton("🤝 قبول چالش و ورود", url=f"https://t.me/{bot_username}?start={game_num}")],
        [InlineKeyboardButton("❌ لغو بازی", callback_data=f"cancel_{game_num}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
    except Exception as e:
        print(f"Failed to edit markup: {e}")
        await context.bot.send_message(chat_id=chat_id, text="👇 دکمه‌های شیشه‌ای مدیریت بازی:", reply_to_message_id=msg_id, reply_markup=reply_markup)

# 📦 ساختار مدیریت وضعیت سراسری (کاملاً فیکس شده و بدون پترن‌های تداخلی)
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
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, 
                lambda update, context: __import__('handlers.auth_handler', fromlist=['process_invite_code_input']).process_invite_code_input(update, context)
            ),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", start) 
    ],
    allow_reentry=True,
)

# لیست آیدی‌هایی که نباید کسر الماس شوند
EXCLUDED_USER_IDS = [8004897709, 8668275780]

# محدودیت تعداد کوئری‌های همزمان برای جلوگیری از غرق شدن thread pool
_DEDUCT_JOB_CONCURRENCY = 20


async def _deduct_single_user(uid: int, current_diamonds: int, semaphore: asyncio.Semaphore):
    """کسر الماس یا غیرفعال‌سازی یک کاربر، با محدودیت همزمانی"""
    async with semaphore:
        try:
            if current_diamonds >= 2:
                new_balance = current_diamonds - 2
                query = supabase.table("users_diamonds").update({"diamonds": new_balance}).eq("user_id", uid)
            else:
                query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", uid)
            await db_execute(query)
        except Exception as e:
            print(f"❌ خطا در کسر الماس کاربر {uid}: {e}")


async def deduct_diamonds_job(context):
    """کسر ۲ الماس از کاربرانی که سلف‌بات آن‌ها فعال است"""
    try:
        # دریافت کاربران فعال (is_active = TRUE)
        query = supabase.table("users_diamonds").select("user_id, diamonds").eq("is_active", True)
        res = await db_execute(query)

        if not res.data:
            return

        semaphore = asyncio.Semaphore(_DEDUCT_JOB_CONCURRENCY)
        tasks = []

        for user in res.data:
            uid = user["user_id"]

            # بررسی آیدی‌های مستثنی شده
            if uid in EXCLUDED_USER_IDS:
                continue

            current_diamonds = user["diamonds"]
            tasks.append(_deduct_single_user(uid, current_diamonds, semaphore))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        print(f"❌ خطا در عملیات کسر الماس خودکار: {e}")

async def start_dual_bots():
    os.makedirs("new_sessions", exist_ok=True)

    # ربات اصلی با JobQueue فعال
    main_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .job_queue(JobQueue())
        .build()
    )

    # هندلرها
    main_app.add_handler(conv_handler)
    main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^طلا"), handle_balance_request))
    main_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^واریز طلا \d+$"), handle_transfer_request))
    register_rps_handlers(main_app)
    main_app.add_handler(CallbackQueryHandler(game_buttons_callback, pattern="^game_"))
    
    # فعال‌سازی جاب (هر یک ساعت)
    main_app.job_queue.run_repeating(deduct_diamonds_job, interval=3600, first=60)

    # ربات پنل
    panel_app = (
        Application.builder()
        .token(PANEL_BOT_TOKEN)
        .build()
    )
    
    import handlers.panel_handler
    handlers.panel_handler.panel_bot_app = panel_app
    panel_app.add_handler(CallbackQueryHandler(handle_panel_clicks)) 
    panel_app.add_handler(InlineQueryHandler(inline_panel_handler))

    # شروع کار
    await load_existing_sessions()
    await main_app.initialize()
    await panel_app.initialize()
    await main_app.start()
    await panel_app.start()
    await main_app.updater.start_polling()
    await panel_app.updater.start_polling()
    
    print("✅ سیستم هوما با موفقیت اجرا شد.")
    while True: await asyncio.sleep(86400)

if __name__ == "__main__":
    try: asyncio.run(start_dual_bots())
    except (KeyboardInterrupt, SystemExit): print("🛑 متوقف شد.")