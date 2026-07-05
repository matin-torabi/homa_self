import asyncio
import os
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes, ConversationHandler
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from handlers.client_manager import (
    clients,
    create_client,
    login_data,
    activate_client,
    deactivate_client,
)
from handlers.keybords import (
    get_calc_keyboard,
    get_code_keyboard,
    get_join_keyboard,
    get_start_keyboard,
)
from utils import get_balance, update_balance, db_execute
from config import supabase

CHANNEL_ID = "@Homa_self_Ch"
GROUP_ID = "@Homa_self_Gp"
CHANNEL_URL = "https://t.me/Homa_self_Ch"
GROUP_URL = "https://t.me/Homa_self_Gp"
SUPPORT_URL = "https://t.me/HOMA_SELFBOT_SUPPORT"

MAIN_MENU, START_PAYMENT, PHONE, CODE, PASSWORD, ENTER_INVITE_CODE = range(6)

running_tasks = {}

async def monitor_client(user_id: int, client):
    """تابع ناظر برای بررسی وضعیت کلاینت؛ در صورت دیسکانکت شدن، وضعیت دیتابیس را آپدیت می‌کند"""
    try:
        await client.run_until_disconnected()
    except Exception as e:
        print(f" s_bot {user_id} disconnected: {e}")
    finally:
        deactivate_client(user_id)  # 👈 پاک‌سازی user_status و clients در حافظه
        try:
            query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
            await db_execute(query)
        except:
            pass
        if user_id in running_tasks:
            del running_tasks[user_id]

def start_client_background(user_id: int, client):
    """اجرای ایمن کلاینت سلف‌بات در پس‌زمینه بدون خطر حذف از حافظه"""
    task = asyncio.create_task(monitor_client(user_id, client))
    running_tasks[user_id] = task


async def check_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        channel_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if channel_member.status in ["left", "kicked"]:
            return False
        group_member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if group_member.status in ["left", "kicked"]:
            return False
        return True
    except Exception:
        return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return ConversationHandler.END

    user_id = update.effective_user.id

    if context.args and context.args[0].startswith("inv_"):
        try:
            inviter_id = int(context.args[0].split("_")[1])
            if inviter_id != user_id:
                context.user_data["pending_invite_code"] = inviter_id
        except ValueError:
            pass

    is_subscribed = await check_sub(user_id, context)
    if not is_subscribed:
        msg_text = "⚠️ برای استفاده از ربات، ابتدا باید در کانال و گروه ما عضو شوید:"
        if update.message:
            await update.message.reply_text(msg_text, reply_markup=get_join_keyboard())
            await update.message.reply_text("⏱ دکمه دسترسی سریع فعال شد.", reply_markup=get_start_keyboard())
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg_text, reply_markup=get_join_keyboard())
        return MAIN_MENU

    session_exists = os.path.exists(f"new_sessions/{user_id}.session")

    keyboard = [
        [InlineKeyboardButton("⚙️ مدیریت و فعال‌سازی سلف‌بات", callback_data="menu_activation", style="success")]
    ]

    try:
        query = supabase.table("users_diamonds").select("referred_by").eq("user_id", user_id)
        user_row = await db_execute(query)
        if not user_row.data or user_row.data[0].get("referred_by") is None:
            keyboard.append([InlineKeyboardButton("🎁 وارد کردن کد دعوت دوستان", callback_data="enter_invite_menu", style="danger")])
    except:
        pass

    keyboard.extend([
        [
            InlineKeyboardButton("👥 گروه", url=GROUP_URL, style="primary"),
            InlineKeyboardButton("📢 چنل", url=CHANNEL_URL, style="primary"),
        ],
        [InlineKeyboardButton("💰 شارژ موجودی (طلا)", callback_data="charge_gold_menu", style="danger")],
        [InlineKeyboardButton("☎️ پشتیبانی", url=SUPPORT_URL, style="danger")],
        [InlineKeyboardButton("🤝 دعوت از دوستان (۳۵ طلا هدیه)", callback_data="menu_referral", style="success")],
        [InlineKeyboardButton("ℹ️ درباره سلف", callback_data="about_self", style="primary")],
        [InlineKeyboardButton("🔒 بستن پنل مدیریت", callback_data="close_panel", style="danger")]
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = "👋 به ربات مدیریت هوما سلف‌بات خوش آمدید!\nلطفاً از منوی زیر گزینه مورد نظر خود را انتخاب کنید:\n\n"

    if session_exists:
        try:
            status_query = supabase.table("users_diamonds").select("is_active").eq("user_id", user_id)
            db_status = await db_execute(status_query)
            is_active_db = db_status.data[0].get("is_active", False) if db_status.data else False
        except:
            is_active_db = False
        status_text = "🟢 روشن" if is_active_db else "🔴 خاموش"
        welcome_text += f"📊 وضعیت سلف‌بات شما: **{status_text}**"

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        await update.message.reply_text("🎛 منو بارگذاری شد.", reply_markup=get_start_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)

    return MAIN_MENU

async def handle_main_menu_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "check_membership":
        is_subscribed = await check_sub(user_id, context)
        if is_subscribed:
            return await start(update, context)
        else:
            await query.edit_message_text("❌ شما هنوز در کانال یا گروه عضو نشده‌اید! لطفاً ابتدا عضو شوید 👇", reply_markup=get_join_keyboard())
            return MAIN_MENU

    if not await check_sub(user_id, context):
        await query.edit_message_text("⚠️ اشتراک شما قطع شده است. لطفا ابتدا عضو شوید:", reply_markup=get_join_keyboard())
        return MAIN_MENU

    # ⚙️ هاب مدیریت و فعال‌سازی سلف‌بات
    if data == "menu_activation":
        session_exists = os.path.exists(f"new_sessions/{user_id}.session")

        try:
            status_query = supabase.table("users_diamonds").select("is_active").eq("user_id", user_id)
            db_status = await db_execute(status_query)
            is_active_db = db_status.data[0].get("is_active", False) if db_status.data else False
        except:
            is_active_db = False

        keyboard = []
        if session_exists:
            status_buttons = []
            if is_active_db:
                status_buttons.append(InlineKeyboardButton("⏸ خاموش کردن سلف", callback_data="self_stop", style="danger"))
            else:
                status_buttons.append(InlineKeyboardButton("▶️ روشن کردن سلف", callback_data="self_start", style="success"))

            status_buttons.append(InlineKeyboardButton("🗑 حذف کامل سلف", callback_data="self_delete", style="danger"))
            keyboard.append(status_buttons)
        else:
            keyboard.append([InlineKeyboardButton("🌟 پرداخت و تایید (۳۰ طلا)", callback_data="pay_activation", style="success")])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main", style="primary")])

        status_str = ("🟢 روشن" if is_active_db else "🔴 خاموش") if session_exists else "❌ فعال‌سازی نشده"
        await query.edit_message_text(
            f"⚙️ **تنظیمات و مدیریت هوما سلف‌بات**\n\n👤 آیدی عددی شما: `{user_id}`\n📊 وضعیت فعلی سلف‌بات: **{status_str}**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return MAIN_MENU

    # ---------------------------------------------------------
    # ℹ️ منوی درباره سلف‌بات و توضیحات امنیتی ربات
    # ---------------------------------------------------------
    elif data == "about_self":
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main", style="primary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            "ℹ️ <b>درباره سلف‌بات هوما</b>\n\n"
            "سلف بات تلگرامی یه رباتیه که داخل اکانت لاگین میشه و قابلیت هایی رو برای شما انجام میده و مزیت هایی داره.\n\n"
            "این ربات هیچگونه دسترسی ای به پیام های شما و یا مخاطبین شما نداره و صرفا دستوراتی که شما بهش میگید که داخل پنل این دستورات وجود داره رو انجام میده. هر گونه سوال یا اطلاعات بیشتری راجب سلف بات خواستید به پیوی مالکین مراجعه کنید.\n\n"
            "👤 <b>آیدی مالکین:</b> @Matintorabi_87, @slappy87"
        )

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return MAIN_MENU

    # 🌟 هندل دکمه پرداخت فعال‌سازی
    elif data == "pay_activation":
        return await handle_activation_payment(update, context)

    # 🤝 منوی نمایش لینک دعوت
    elif data == "menu_referral":
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start=inv_{user_id}"

        referral_text = (
            f"🤝 **برنامه دعوت از دوستان (کسب طلا رایگان)**\n\n"
            f"با لینک خود دوستانتان را دعوت کنید. زمانی که دوست شما وارد ربات شده و اقدام به فعال‌سازی سلف‌بات خود (با پرداخت طلا) کند، سیستم به طور خودکار به شما **۳۵ طلا** هدیه می‌دهد!💰\n\n"
            f"🔗 لینک دعوت اختصاصی شما:\n`{invite_link}`\n\n🆔 کد دعوت شما: `{user_id}`"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main", style="primary")]]
        await query.edit_message_text(referral_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU

    # 🎁 منوی ورود دستی کد دعوت معرف
    elif data == "enter_invite_menu":
        pending_code = context.user_data.get("pending_invite_code")
        if pending_code:
            try:
                update_query = supabase.table("users_diamonds").update({"referred_by": pending_code}).eq("user_id", user_id)
                await db_execute(update_query)
                await query.edit_message_text("✅ کد معرف با موفقیت ثبت شد! پس از خرید و فعال‌سازی سلف‌بات توسط شما، هدیه ۳۵ طلا به معرف تعلق خواهد گرفت.")
                context.user_data.pop("pending_invite_code", None)
            except Exception as e:
                await query.edit_message_text(f"⚠️ خطایی در ثبت خودکار رخ داد: {e}")
            return MAIN_MENU

        keyboard = [[InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="cancel_to_menu", style="primary")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "✍️ لطفاً آیدی عددی (کد دعوت) فردی که شما را دعوت کرده است را به صورت متنی ارسال کنید:",
            reply_markup=reply_markup
        )
        return ENTER_INVITE_CODE


    # ---------------------------------------------------------
    # ۱. منوی باز کردن اولیه ماشین حساب خرید طلا
    # ---------------------------------------------------------
    elif data == "charge_gold_menu" or data == "cancel_to_menu":
        context.user_data["gold_calculator_amount"] = 0

        keyboard = [
            [InlineKeyboardButton("1", callback_data="gold_1"), InlineKeyboardButton("2", callback_data="gold_2"), InlineKeyboardButton("3", callback_data="gold_3")],
            [InlineKeyboardButton("4", callback_data="gold_4"), InlineKeyboardButton("5", callback_data="gold_5"), InlineKeyboardButton("6", callback_data="gold_6")],
            [InlineKeyboardButton("7", callback_data="gold_7"), InlineKeyboardButton("8", callback_data="gold_8"), InlineKeyboardButton("9", callback_data="gold_9")],
            [InlineKeyboardButton("Clear ❌", callback_data="gold_clear", style="danger"), InlineKeyboardButton("0", callback_data="gold_0"), InlineKeyboardButton("Delete ⬅️", callback_data="gold_delete", style="primary")],
            [InlineKeyboardButton("💳 رفتن برای پرداخت", callback_data="gold_pay", style="success")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main", style="primary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            "💰 **بخش خرید و شارژ طلا**\n\n"
            "نرخ هر ۱ طلا **۳۵ تومان** می‌باشد.\n"
            "تعداد طلا را با ماشین حساب زیر وارد کنید:\n\n"
            "✍️ **تعداد طلای انتخابی:** `0` عدد\n"
            "💵 **قیمت کل:** `0` تومان"
        )
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        return MAIN_MENU

    # ---------------------------------------------------------
    # ۲. خروجی نهایی ماشین حساب: رفتن برای پرداخت و نمایش فاکتور کارت
    # ---------------------------------------------------------
    elif data == "gold_pay":
        try:
            final_amount = int(context.user_data.get("gold_calculator_amount", 0))
        except:
            final_amount = 0

        if final_amount <= 0:
            await query.answer("⚠️ لطفاً ابتدا تعداد طلا را با ماشین‌حساب وارد کنید!", show_alert=True)
            return MAIN_MENU

        price_toman = final_amount * 35
        formatted_price = "{:,}".format(price_toman)
        formatted_amount = "{:,}".format(final_amount)

        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت به ماشین حساب", callback_data="charge_gold_menu", style="primary")],
            [InlineKeyboardButton("🔙 منوی اصلی ربات", callback_data="back_to_main", style="success")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"💳 <b>اطلاعات واریز فاکتور خرید طلا:</b>\n\n"
            f"📦 <b>سفارش:</b> خرید {formatted_amount} طلا\n"
            f"💰 <b>مبلغ قابل پرداخت:</b> <code>{formatted_price}</code> تومان\n\n"
            f"📌 <b>شماره کارت جهت واریز:</b>\n<code>6037697614134663</code> سید حسین قاضی میرسعید\n\n"
            f"⚠️ <b>دستورالعمل تایید سفارش:</b>\n"
            f"لطفاً مبلغ دقیق فوق را به شماره کارت بالا واریز نمایید، سپس <b>تصویر فیش یا اسکرین‌شات رسید واریزی</b> (اگر فیش فیک بفرستید موجودی شما صفر میشود) .خود را برای پشتیبانی ارسال کنید تا حسابتان شارژ شود.\n\n"
            f"📞 <b>ارتباط با پشتیبانی هوما:</b> @HOMA_SELFBOT_SUPPORT"
        )

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return MAIN_MENU

    # ---------------------------------------------------------
    # ۳. پردازش دکمه‌های فشرده شده ماشین حساب طلا (اعداد و Clear/Delete)
    # ---------------------------------------------------------
    elif data.startswith("gold_"):
        action = data.replace("gold_", "")

        try:
            current_amount = int(context.user_data.get("gold_calculator_amount", 0))
        except:
            current_amount = 0

        current_amount_str = str(current_amount)
        if current_amount_str == "0":
            current_amount_str = ""

        if action.isdigit():
            if len(current_amount_str) < 6:
                current_amount_str += action
        elif action == "clear":
            current_amount_str = "0"
        elif action == "delete":
            current_amount_str = current_amount_str[:-1]
            if not current_amount_str:
                current_amount_str = "0"

        final_amount = int(current_amount_str) if current_amount_str else 0
        context.user_data["gold_calculator_amount"] = final_amount

        price_toman = final_amount * 35
        formatted_price = "{:,}".format(price_toman)
        formatted_amount = "{:,}".format(final_amount)

        keyboard = [
            [InlineKeyboardButton("1", callback_data="gold_1"), InlineKeyboardButton("2", callback_data="gold_2"), InlineKeyboardButton("3", callback_data="gold_3")],
            [InlineKeyboardButton("4", callback_data="gold_4"), InlineKeyboardButton("5", callback_data="gold_5"), InlineKeyboardButton("6", callback_data="gold_6")],
            [InlineKeyboardButton("7", callback_data="gold_7"), InlineKeyboardButton("8", callback_data="gold_8"), InlineKeyboardButton("9", callback_data="gold_9")],
            [InlineKeyboardButton("Clear ❌", callback_data="gold_clear", style="danger"), InlineKeyboardButton("0", callback_data="gold_0"), InlineKeyboardButton("Delete ⬅️", callback_data="gold_delete", style="primary")],
            [InlineKeyboardButton("💳 رفتن برای پرداخت", callback_data="gold_pay", style="success")],
            [InlineKeyboardButton("🔙 بازگشت و بسته شدن پنل", callback_data="back_to_main", style="primary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            "💰 **بخش خرید و شارژ طلا**\n\n"
            "نرخ هر ۱ طلا **۳۵ تومان** می‌باشد.\n"
            "تعداد طلا را با ماشین حساب زیر وارد کنید:\n\n"
            f"✍️ **تعداد طلای انتخابی:** `{formatted_amount}` عدد\n"
            f"💵 **قیمت کل:** `{formatted_price}` تومان"
        )
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except:
            pass
        return MAIN_MENU

    # ⏸ خاموش کردن منطقی سلف‌بات
    elif data == "self_stop":
        try:
            update_query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
            await db_execute(update_query)
            if user_id in clients:
                await clients[user_id].disconnect()
            deactivate_client(user_id)  # 👈 پاک‌سازی متمرکز user_status و clients
            if user_id in running_tasks:
                running_tasks[user_id].cancel()
                del running_tasks[user_id]
            await query.answer("🔴 سلف‌بات شما خاموش شد.", show_alert=True)
        except Exception as e:
            await query.answer(f"خطا در خاموش کردن: {e}", show_alert=True)
        return await start(update, context)

    # ▶️ روشن کردن منطقی و آنی سلف‌بات
    elif data == "self_start":
        session_file = f"new_sessions/{user_id}.session"
        if not os.path.exists(session_file):
            await query.answer("❌ فایل سشن یافت نشد. ابتدا لاگین کنید.", show_alert=True)
            return await start(update, context)

        try:
            await query.edit_message_text("⏳ در حال راه‌اندازی و اتصال به کلاینت تلگرام...")

            if user_id in clients:
                try: await clients[user_id].disconnect()
                except: pass
                deactivate_client(user_id)

            client = create_client(user_id)
            await client.connect()

            if await client.is_user_authorized():
                activate_client(client, user_id)  # 👈 گارد + هندلرها + وضعیت، همه یک‌جا
                start_client_background(user_id, client)

                try:
                    update_query = supabase.table("users_diamonds").update({"is_active": True}).eq("user_id", user_id)
                    await db_execute(update_query)
                except Exception as db_err:
                    print(f"Database error: {db_err}")

                await query.answer("🟢 سلف‌بات با موفقیت روشن و فعال شد!", show_alert=True)
            else:
                await query.answer("⚠️ سشن شما منقضی شده است.", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ خطای سیستم: {str(e)}", show_alert=True)

        return await start(update, context)

    # 🗑 حذف کامل سلف‌بات
    elif data == "self_delete":
        try:
            update_query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
            await db_execute(update_query)
            if user_id in clients:
                await clients[user_id].disconnect()
            deactivate_client(user_id)  # 👈 پاک‌سازی متمرکز
            if user_id in running_tasks:
                running_tasks[user_id].cancel()
                del running_tasks[user_id]
        except:
            pass
        session_file = f"new_sessions/{user_id}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
            await query.answer("🗑 سلف‌بات کاملاً حذف گردید.", show_alert=True)
        else:
            await query.answer("فایلی برای حذف پیدا نشد.", show_alert=True)
        return await start(update, context)

    elif data == "back_to_main":
        return await start(update, context)

    elif data == "close_panel":
        await query.edit_message_text("✅ پنل با موفقیت بسته شد.\nبرای باز کردن مجدد از دستور /start استفاده کنید.")
        return MAIN_MENU

    return MAIN_MENU


async def process_invite_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("❌ کد دعوت نامعتبر است. لطفاً فقط آیدی عددی معرف را ارسال کنید:")
        return ENTER_INVITE_CODE

    inviter_id = int(text)

    if inviter_id == user_id:
        await update.message.reply_text("❌ شما نمی‌توانید کد دعوت خودتان را وارد کنید!")
        return MAIN_MENU

    try:
        check_query = supabase.table("users_diamonds").select("user_id").eq("user_id", inviter_id)
        inviter_check = await db_execute(check_query)
        if not inviter_check.data:
            await update.message.reply_text("❌ چنین کد دعوتی در سیستم ثبت نشده است!")
            return MAIN_MENU

        update_query = supabase.table("users_diamonds").update({"referred_by": inviter_id, "invite_reward_paid": False}).eq("user_id", user_id)
        await db_execute(update_query)
        await update.message.reply_text("✅ کد معرف شما با موفقیت ثبت شد.\n🎁 پس از اینکه سلف‌بات خود را با طلا فعال کنید، جایزه ۳۵ طلا به معرف شما تعلق می‌گیرد.", reply_markup=get_start_keyboard())
    except Exception as e:
        await update.message.reply_text(f"⚠️ خطا در ارتباط با دیتابیس: {e}")

    return MAIN_MENU


async def handle_go_to_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gold_amount = int(query.data.split("_")[3])

    if gold_amount <= 0:
        await query.answer("⚠️ لطفاً ابتدا تعداد طلا را وارد کنید!", show_alert=True)
        return

    total_price = gold_amount * 35
    receipt_text = (
        f"🛍 **سفارش شما: {gold_amount} طلا به ارزش {total_price} تومان**\n\n"
        f"💳 شماره کارت:\nبه نام: سید حسین قاضی میرسعید\n"
        f"لطفا پس از واریز مبلغ فیش دریافتی را به پیوی ادمین ارسال کنید.\n"
        f"آیدی ادمین: @HOMA_SELFBOT_SUPPORT\n\n"
        f"نکته: در صورت فرستادن عکس فیش فیک تمامی طلاهای شما صفر خواهد شد."
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main", style="primary")]]
    await query.edit_message_text(receipt_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_activation_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not await check_sub(user_id, context):
        await query.message.reply_text("⚠️ برای ادامه باید عضو کانال و گروه باشید:", reply_markup=get_join_keyboard())
        return MAIN_MENU

    user_balance = await get_balance(user_id)
    REQUIRED_GOLD = 30

    if user_balance < REQUIRED_GOLD:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_activation", style="primary")]]
        await query.edit_message_text(
            f"❌ **موجودی طلای شما کافی نیست!**\n\n💰 موجودی فعلی: {user_balance} طلا\n"
            f"⚠️ برای فعال‌سازی به {REQUIRED_GOLD} طلا نیاز دارید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return MAIN_MENU

    deducted = await update_balance(user_id, -REQUIRED_GOLD)
    if not deducted:
        await query.edit_message_text("❌ خطا در کسر موجودی. ممکن است موجودی شما به‌تازگی تغییر کرده باشد؛ لطفاً دوباره تلاش کنید.")
        return MAIN_MENU

    try:
        ref_query = supabase.table("users_diamonds").select("referred_by", "invite_reward_paid").eq("user_id", user_id)
        user_data_db = await db_execute(ref_query)
        if user_data_db.data:
            inviter_id = user_data_db.data[0].get("referred_by")
            reward_paid = user_data_db.data[0].get("invite_reward_paid", False)

            if inviter_id and not reward_paid:
                await update_balance(inviter_id, 35)
                paid_query = supabase.table("users_diamonds").update({"invite_reward_paid": True}).eq("user_id", user_id)
                await db_execute(paid_query)

                try:
                    await context.bot.send_message(chat_id=inviter_id, text=f"🎉 یکی از زیرمجموعه‌های شما سلف‌بات خود را فعال کرد! ۳۵ طلا هدیه به حساب شما واریز شد.💰")
                except:
                    pass
    except Exception as e:
        print(f"Error in referral payout: {e}")

    try:
        active_query = supabase.table("users_diamonds").update({"is_active": True}).eq("user_id", user_id)
        await db_execute(active_query)
    except:
        pass

    contact_button = KeyboardButton(text="📱 ارسال شماره تلفن", request_contact=True)
    phone_keyboard = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)

    await query.edit_message_text("✅ پرداخت تایید شد. در حال انتقال به مرحله بعد...")
    await query.message.reply_text(
        f"✅ **پرداخت با موفقیت انجام شد!**\n💰 مبلغ {REQUIRED_GOLD} طلا از حساب شما کسر شد.\n"
        f"🔹 موجودی جدید: {await get_balance(user_id)} طلا\n\n"
        f"👇 برای تکمیل لاگین، روی دکمه بزرگ زیر صفحه بزنید تا شماره تلفنتان ارسال شود:",
        reply_markup=phone_keyboard,
    )
    return PHONE


async def handle_cancel_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.contact:
        await update.message.reply_text("❌ لطفاً شماره خود را فقط با استفاده از دکمه «📱 ارسال شماره تلفن» ارسال کنید.")
        return PHONE

    contact = update.message.contact
    user_id = update.effective_user.id
    phone = contact.phone_number

    if not phone.startswith("+"):
        phone = "+" + phone

    if user_id in login_data:
        del login_data[user_id]

    if user_id in clients:
        try:
            await clients[user_id].disconnect()
        except:
            pass

    client = create_client(user_id)
    await client.connect()

    try:
        sent_code = await client.send_code_request(phone)
        clients[user_id] = client
        login_data[user_id] = {
            "phone": phone,
            "phone_code_hash": sent_code.phone_code_hash,
            "used": False,
        }
        context.user_data["telegram_code"] = ""
        await update.message.reply_text(
            "🔢 **کد فعال‌سازی تلگرام ارسال شد.**\n\nلطفاً با استفاده از دکمه‌های شیشه‌ای زیر، کد دریافتی را وارد کنید:\n✍️ کد وارد شده: ",
            reply_markup=get_code_keyboard(""),
        )
        return CODE
    except Exception as e:
        await update.message.reply_text(
            f"❌ خطا در ارسال کد:\n{e}\n\nبرگشت به منوی اصلی...",
            reply_markup=get_start_keyboard(),
        )
        return ConversationHandler.END


async def handle_code_calculator_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    current_code = context.user_data.get("telegram_code", "")

    if data == "code_back":
        return await start(update, context)

    if data == "code_clear":
        current_code = ""
    elif data == "code_del":
        current_code = current_code[:-1]
    elif data.startswith("code_") and data != "code_submit":
        action = data.split("_")[1]
        if len(current_code) < 5:
            current_code += action

    context.user_data["telegram_code"] = current_code

    if data != "code_submit":
        try:
            await query.edit_message_text(
                "🔢 **کد فعال‌سازی تلگرام ارسال شد.**\n\nلطفاً با استفاده از دکمه‌های شیشه‌ای زیر، کد دریافتی را وارد کنید:\n"
                f"✍️ کد وارد شده: `{current_code}`",
                reply_markup=get_code_keyboard(current_code),
            )
        except Exception:
            pass
        await query.answer()
        return CODE

    if data == "code_submit":
        if len(current_code) < 5:
            await query.answer("⚠️ کد تلگرام حداقل باید ۵ رقم باشد!", show_alert=True)
            return CODE

        if user_id not in login_data:
            await query.message.reply_text("❌ جلسه شما یافت نشد. لطفاً دوباره /start بزنید.", reply_markup=get_start_keyboard())
            return ConversationHandler.END

        client = clients.get(user_id)
        login_info = login_data[user_id]

        try:
            if not client or not client.is_connected():
                await client.connect()

            await client.sign_in(phone=login_info["phone"], code=current_code, phone_code_hash=login_info["phone_code_hash"])
            await query.message.reply_text("✅ ورود موفقیت‌آمیز بود! سلف‌بات شما فعال شد.", reply_markup=get_start_keyboard())

            activate_client(client, user_id)  # 👈 گارد + هندلرها + وضعیت، همه یک‌جا
            start_client_background(user_id, client)

            del login_data[user_id]
            return ConversationHandler.END

        except PhoneCodeExpiredError:
            await query.message.reply_text("❌ کد منقضی شده است. لطفا دوباره از ابتدا تلاش کنید.", reply_markup=get_start_keyboard())
            return ConversationHandler.END
        except PhoneCodeInvalidError:
            await query.answer("❌ کد وارد شده اشتباه است! مجدد وارد کنید.", show_alert=True)
            context.user_data["telegram_code"] = ""
            await query.edit_message_text("🔢 **کد اشتباه بود. دوباره وارد کنید:**\n\n✍️ کد وارد شده: ", reply_markup=get_code_keyboard(""))
            return CODE
        except SessionPasswordNeededError:
            await query.message.reply_text("🔐 این اکانت رمز ۲ مرحله‌ای دارد، لطفاً رمز خود را به صورت متنی وارد کنید:")
            return PASSWORD
        except Exception as e:
            await query.message.reply_text(f"❌ خطای غیرمنتظره:\n{e}", reply_markup=get_start_keyboard())
            return ConversationHandler.END


async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    client = clients.get(user_id)

    if not client:
        await update.message.reply_text("❌ خطایی رخ داد. لطفا دوباره تلاش کنید.", reply_markup=get_start_keyboard())
        return ConversationHandler.END

    try:
        if not client.is_connected():
            await client.connect()

        await client.sign_in(password=password)
        await update.message.reply_text("✅ ورود با رمز دو مرحله‌ای موفقیت‌آمیز بود! سلف‌بات شما فعال شد.", reply_markup=get_start_keyboard())

        activate_client(client, user_id)  # 👈 گارد + هندلرها + وضعیت، همه یک‌جا
        start_client_background(user_id, client)

        if user_id in login_data:
            del login_data[user_id]
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ رمز عبور اشتباه است یا خطایی رخ داده:\n{e}\n\nلطفاً دوباره رمز عبور را ارسال کنید:")
        return PASSWORD


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)