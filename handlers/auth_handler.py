import asyncio
import os
from functools import partial
from cachetools import TTLCache
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
    register_handlers,
)
from handlers.keybords import (
    get_calc_keyboard,
    get_code_keyboard,
    get_join_keyboard,
    get_start_keyboard,
)
from utils import get_balance, update_balance, supabase

CHANNEL_ID = "@Homa_self_Ch"
GROUP_ID = "@Homa_self_Gp"
CHANNEL_URL = "https://t.me/Homa_self_Ch"
GROUP_URL = "https://t.me/Homa_self_Gp"
SUPPORT_URL = "https://t.me/HOMA_SELFBOT_SUPPORT"

MAIN_MENU, START_PAYMENT, PHONE, CODE, PASSWORD, ENTER_INVITE_CODE = range(6)

# 🟢 دیکشنری برای نگه‌داشتن رفرنس تسک‌های پس‌زمینه جهت جلوگیری از کرش سلف‌بات‌ها
running_tasks = {}

async def perform_async_login(user_id, query, context):
    """
    این تابع عملیات سنگین اتصال کلاینت را در پس‌زمینه انجام می‌دهد
    تا Event Loop اصلی ربات برای ۸۰۰۰ کاربر دیگر بلاک نشود.
    """
    try:
        session_file = f"new_sessions/{user_id}.session"
        if not os.path.exists(session_file):
            await query.edit_message_text("❌ فایل سشن یافت نشد.")
            return

        # ایجاد و اتصال کلاینت
        client = create_client(user_id)
        await client.connect()

        if await client.is_user_authorized():
            clients[user_id] = client
            register_handlers(client)
            start_client_background(user_id, client)
            
            # آپدیت دیتابیس به صورت غیرهمگام
            await run_db(lambda: supabase.table("users_diamonds").update({"is_active": True}).eq("user_id", user_id).execute())
            
            await query.edit_message_text("🟢 سلف‌بات با موفقیت روشن و فعال شد!")
        else:
            await query.edit_message_text("⚠️ سشن شما منقضی شده است. دوباره لاگین کنید.")
            
    except Exception as e:
        await query.edit_message_text(f"❌ خطای سیستم در اتصال: {str(e)}")

async def run_db(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

async def monitor_client(user_id: int, client):
    """تابع ناظر بهینه شده با استفاده از Executor برای عدم بلاک شدن ربات"""
    try:
        # اجرای کلاینت
        await client.run_until_disconnected()
    except Exception as e:
        print(f"S_bot {user_id} disconnected with error: {e}")
    finally:
        # استفاده از run_db برای اینکه دیتابیس ربات رو کند نکنه
        try:
            await run_db(
                supabase.table("users_diamonds")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .execute
            )
        except Exception as db_err:
            print(f"Error updating DB for {user_id}: {db_err}")
        
        # پاکسازی حافظه
        if user_id in clients:
            try:
                # اطمینان از بسته شدن کامل کلاینت
                await clients[user_id].disconnect()
            except:
                pass
            del clients[user_id]
            
        if user_id in running_tasks:
            del running_tasks[user_id]

def start_client_background(user_id: int, client):
    """اجرای ایمن کلاینت سلف‌بات در پس‌زمینه بدون خطر حذف از حافظه"""
    task = asyncio.create_task(monitor_client(user_id, client))
    running_tasks[user_id] = task


sub_cache = TTLCache(maxsize=10000, ttl=1800)

async def check_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # چک کردن کش
    if user_id in sub_cache:
        return sub_cache[user_id]
    
    try:
        # اگر در کش نبود، از تلگرام بپرس
        channel_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if channel_member.status in ["left", "kicked"]:
            sub_cache[user_id] = False
            return False
            
        group_member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if group_member.status in ["left", "kicked"]:
            sub_cache[user_id] = False
            return False
        
        # ثبت در کش
        sub_cache[user_id] = True
        return True
    except Exception:
        # اگر خطایی رخ داد (مثلاً کاربر پیدا نشد یا ربات دسترسی نداشت)، فرض رو بر عضویت بگذار
        return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.type != 'private':
        return

    # منطق دعوت دوستان (بهینه‌تر)
    if context.args and context.args[0].startswith("inv_"):
        try:
            inviter_id = int(context.args[0].split("_")[1])
            if inviter_id != user_id:
                context.user_data["pending_invite_code"] = inviter_id
        except ValueError:
            pass

    # چک کردن عضویت (حالا از کش استفاده می‌کند که خیلی سریع‌تر است)
    if not await check_sub(user_id, context):
        msg_text = "⚠️ برای استفاده از ربات، ابتدا باید در کانال و گروه ما عضو شوید:"
        if update.message:
            await update.message.reply_text(msg_text, reply_markup=get_join_keyboard())
            await update.message.reply_text("⏱ دکمه دسترسی سریع فعال شد.", reply_markup=get_start_keyboard())
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg_text, reply_markup=get_join_keyboard())
        return MAIN_MENU

    # استفاده از run_db برای عدم مسدود شدن ربات
    # استفاده از یک کوئری ترکیبی برای کاهش دفعات رفت و آمد به دیتابیس
    user_row = await run_db(
        lambda: supabase.table("users_diamonds")
        .select("referred_by, is_active")
        .eq("user_id", user_id)
        .execute()
    )
    
    data = user_row.data[0] if user_row.data else {}
    referred_by = data.get("referred_by")
    is_active_db = data.get("is_active", False)
    
    session_exists = os.path.exists(f"new_sessions/{user_id}.session")

    # ساخت کیبورد (بهینه‌سازی شده)
    keyboard = [[InlineKeyboardButton("⚙️ مدیریت و فعال‌سازی سلف‌بات", callback_data="menu_activation")]]
    
    if not referred_by:
        keyboard.append([InlineKeyboardButton("🎁 وارد کردن کد دعوت دوستان", callback_data="enter_invite_menu")])

    keyboard.extend([
        [InlineKeyboardButton("👥 گروه", url=GROUP_URL), InlineKeyboardButton("📢 چنل", url=CHANNEL_URL)],
        [InlineKeyboardButton("💰 شارژ موجودی (طلا)", callback_data="charge_gold_menu")],
        [InlineKeyboardButton("☎️ پشتیبانی", url=SUPPORT_URL)],
        [InlineKeyboardButton("🤝 دعوت از دوستان (۳۵ الماس هدیه)", callback_data="menu_referral")],
        [InlineKeyboardButton("ℹ️ درباره سلف", callback_data="about_self")],
        [InlineKeyboardButton("🔒 بستن پنل مدیریت", callback_data="close_panel")]
    ])

    welcome_text = "👋 به ربات مدیریت هوما سلف‌بات خوش آمدید!\n\n"
    if session_exists:
        status_text = "🟢 روشن" if is_active_db else "🔴 خاموش"
        welcome_text += f"📊 وضعیت سلف‌بات شما: **{status_text}**\n\n"
    
    welcome_text += "لطفاً از منوی زیر گزینه مورد نظر خود را انتخاب کنید:"

    # ارسال پاسخ
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await update.message.reply_text("🎛 منو بارگذاری شد.", reply_markup=get_start_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    return MAIN_MENU

async def handle_main_menu_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "check_membership":
            if await check_sub(user_id, context):
                return await start(update, context)
            await query.edit_message_text("❌ عضو نیستید! لطفاً ابتدا عضو شوید.", reply_markup=get_join_keyboard())
            return MAIN_MENU

    if not await check_sub(user_id, context):
        await query.edit_message_text("⚠️ اشتراک شما قطع شده است.", reply_markup=get_join_keyboard())
        return MAIN_MENU

    # ⚙️ هاب مدیریت و فعال‌سازی سلف‌بات
    if data == "menu_activation":
        session_exists = os.path.exists(f"new_sessions/{user_id}.session")
        
        # کوئری بهینه دیتابیس
        db_res = await run_db(lambda: supabase.table("users_diamonds").select("is_active").eq("user_id", user_id).execute())
        is_active_db = db_res.data[0].get("is_active", False) if db_res.data else False

        keyboard = []
        if session_exists:
            status_buttons = []
            if is_active_db:
                status_buttons.append(InlineKeyboardButton("⏸ خاموش کردن سلف", callback_data="self_stop"))
            else:
                status_buttons.append(InlineKeyboardButton("▶️ روشن کردن سلف", callback_data="self_start"))
            
            status_buttons.append(InlineKeyboardButton("🗑 حذف کامل سلف", callback_data="self_delete"))
            keyboard.append(status_buttons)
        else:
            keyboard.append([InlineKeyboardButton("🌟 پرداخت و تایید (۳۰ طلا)", callback_data="pay_activation")])
            
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")])
        
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
            [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ⚡ متن درخواستی شما به همراه دکمه بازگشت با ساختار امن HTML
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
            f"🤝 **برنامه دعوت از دوستان (کسب الماس رایگان)**\n\n"
            f"با لینک خود دوستانتان را دعوت کنید. زمانی که دوست شما وارد ربات شده و اقدام به فعال‌سازی سلف‌بات خود (با پرداخت طلا) کند، سیستم به طور خودکار به شما **۳۵ الماس** هدیه می‌دهد!💎\n\n"
            f"🔗 لینک دعوت اختصاصی شما:\n`{invite_link}`\n\n🆔 کد دعوت شما: `{user_id}`"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]]
        await query.edit_message_text(referral_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU

    # 🎁 منوی ورود دستی کد دعوت معرف
    elif data == "enter_invite_menu":
        pending_code = context.user_data.get("pending_invite_code")
        if pending_code:
            try:
                await run_db(lambda: supabase.table("users_diamonds").update({"referred_by": pending_code}).eq("user_id", user_id).execute())
                await query.edit_message_text("✅ کد معرف با موفقیت ثبت شد! پس از خرید و فعال‌سازی سلف‌بات توسط شما، هدیه ۳۵ الماس به معرف تعلق خواهد گرفت.")
                context.user_data.pop("pending_invite_code", None)
            except Exception as e:
                await query.edit_message_text(f"⚠️ خطایی در ثبت خودکار رخ داد: {e}")
            return MAIN_MENU
            
        keyboard = [[InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="cancel_to_menu")]]
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
        # ذخیره به صورت عدد صحیح خالص
        context.user_data["gold_calculator_amount"] = 0
        
        keyboard = [
            [InlineKeyboardButton("1", callback_data="gold_1"), InlineKeyboardButton("2", callback_data="gold_2"), InlineKeyboardButton("3", callback_data="gold_3")],
            [InlineKeyboardButton("4", callback_data="gold_4"), InlineKeyboardButton("5", callback_data="gold_5"), InlineKeyboardButton("6", callback_data="gold_6")],
            [InlineKeyboardButton("7", callback_data="gold_7"), InlineKeyboardButton("8", callback_data="gold_8"), InlineKeyboardButton("9", callback_data="gold_9")],
            [InlineKeyboardButton("Clear ❌", callback_data="gold_clear"), InlineKeyboardButton("0", callback_data="gold_0"), InlineKeyboardButton("Delete ⬅️", callback_data="gold_delete")],
            [InlineKeyboardButton("💳 رفتن برای پرداخت", callback_data="gold_pay")],
            [InlineKeyboardButton("🔙 بازگشت و بسته شدن پنل", callback_data="back_to_main")]
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
        # گرفتن مقدار به صورت عدد صحیح خالص
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
            [InlineKeyboardButton("🔙 بازگشت به ماشین حساب", callback_data="charge_gold_menu")],
            [InlineKeyboardButton("🔙 منوی اصلی ربات", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ⚡ متن با ساختار امن HTML بازنویسی شد تا آندرلاین آیدی پشتیبانی ارور ندهد
        text = (
            f"💳 <b>اطلاعات واریز فاکتور خرید طلا:</b>\n\n"
            f"📦 <b>سفارش:</b> خرید {formatted_amount} طلا\n"
            f"💰 <b>مبلغ قابل پرداخت:</b> <code>{formatted_price}</code> تومان\n\n"
            f"📌 <b>شماره کارت جهت واریز:</b>\n<code>6037697614134663</code> سید حسین قاضی میرسعید\n\n"
            f"⚠️ <b>دستورالعمل تایید سفارش:</b>\n"
            f"لطفاً مبلغ دقیق فوق را به شماره کارت بالا واریز نمایید، سپس <b>تصویر فیش یا اسکرین‌شات رسید واریزی</b> (اگر فیش فیک بفرستید موجودی شما صفر میشود) .خود را برای پشتیبانی ارسال کنید تا حسابتان شارژ شود.\n\n"
            f"📞 <b>ارتباط با پشتیبانی هوما:</b> @HOMA_SELFBOT_SUPPORT"
        )
        
        # ⚡ تغییر پارس مود به HTML جهت پایداری کامل متن
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return MAIN_MENU

    # ---------------------------------------------------------
    # ۳. پردازش دکمه‌های فشرده شده ماشین حساب طلا (اعداد و Clear/Delete)
    # ---------------------------------------------------------
    elif data.startswith("gold_"):
        action = data.replace("gold_", "")
        
        # مقدار فعلی رو همیشه به صورت عدد خالص لود می‌کنیم تا ویرگول‌ها خرابش نکنند
        try:
            current_amount = int(context.user_data.get("gold_calculator_amount", 0))
        except:
            current_amount = 0
            
        current_amount_str = str(current_amount)
        if current_amount_str == "0":
            current_amount_str = ""

        if action.isdigit():
            if len(current_amount_str) < 6:  # قفل روی ۶ رقم برای قالب تمیز
                current_amount_str += action
        elif action == "clear":
            current_amount_str = "0"
        elif action == "delete":
            current_amount_str = current_amount_str[:-1]
            if not current_amount_str:
                current_amount_str = "0"

        # ذخیره مجدد به صورت عدد صحیح خالص (بدون ویرگول فرستادن در مموری)
        final_amount = int(current_amount_str) if current_amount_str else 0
        context.user_data["gold_calculator_amount"] = final_amount
        
        # محاسبات قیمت
        price_toman = final_amount * 35
        formatted_price = "{:,}".format(price_toman)
        formatted_amount = "{:,}".format(final_amount)

        keyboard = [
            [InlineKeyboardButton("1", callback_data="gold_1"), InlineKeyboardButton("2", callback_data="gold_2"), InlineKeyboardButton("3", callback_data="gold_3")],
            [InlineKeyboardButton("4", callback_data="gold_4"), InlineKeyboardButton("5", callback_data="gold_5"), InlineKeyboardButton("6", callback_data="gold_6")],
            [InlineKeyboardButton("7", callback_data="gold_7"), InlineKeyboardButton("8", callback_data="gold_8"), InlineKeyboardButton("9", callback_data="gold_9")],
            [InlineKeyboardButton("Clear ❌", callback_data="gold_clear"), InlineKeyboardButton("0", callback_data="gold_0"), InlineKeyboardButton("Delete ⬅️", callback_data="gold_delete")],
            [InlineKeyboardButton("💳 رفتن برای پرداخت", callback_data="gold_pay")],
            [InlineKeyboardButton("🔙 بازگشت و بسته شدن پنل", callback_data="back_to_main")]
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


    elif data in ["self_stop", "self_start", "self_delete"]:
        await query.edit_message_text("⏳ در حال پردازش دستور...")
        
        if data == "self_stop":
            await run_db(lambda: supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id).execute())
            # پاکسازی کلاینت
            if user_id in clients:
                try: await clients[user_id].disconnect() 
                except: pass
                del clients[user_id]
            if user_id in running_tasks:
                running_tasks[user_id].cancel()
                del running_tasks[user_id]
            await query.answer("🔴 سلف‌بات خاموش شد.", show_alert=True)

        elif data == "self_start":
            # اجرای لاگین در یک تسک مجزا برای جلوگیری از فریز شدن ربات
            asyncio.create_task(perform_async_login(user_id, query, context))
            return MAIN_MENU
            
        elif data == "self_delete":
            # پاکسازی کامل
            await run_db(lambda: supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id).execute())
            # ... حذف فایل و کلاینت (مانند self_stop)
            session_file = f"new_sessions/{user_id}.session"
            if os.path.exists(session_file): os.remove(session_file)
            await query.answer("🗑 سلف‌بات حذف شد.", show_alert=True)

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
        # اجرای عملیات‌های دیتابیس در ترد جداگانه
        # استفاده از یک Lambda برای ارسال به run_db
        inviter_check = await run_db(
            lambda: supabase.table("users_diamonds").select("user_id").eq("user_id", inviter_id).execute()
        )
        
        if not inviter_check.data:
            await update.message.reply_text("❌ چنین کد دعوتی در سیستم ثبت نشده است!")
            return MAIN_MENU

        # آپدیت وضعیت در دیتابیس
        await run_db(
            lambda: supabase.table("users_diamonds")
            .update({"referred_by": inviter_id, "invite_reward_paid": False})
            .eq("user_id", user_id)
            .execute()
        )
        
        await update.message.reply_text(
            "✅ کد معرف شما با موفقیت ثبت شد.\n🎁 پس از اینکه سلف‌بات خود را با طلا فعال کنید، جایزه ۳۵ الماس به معرف شما تعلق می‌گیرد.", 
            reply_markup=get_start_keyboard()
        )
    except Exception as e:
        # لاگ کردن خطا به جای نمایش مستقیم به کاربر (امن‌تر است)
        print(f"Database error in process_invite_code_input: {e}")
        await update.message.reply_text("⚠️ خطایی در ارتباط با سرور رخ داد. لطفاً دوباره تلاش کنید.")

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
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]]
    await query.edit_message_text(receipt_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_activation_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not await check_sub(user_id, context):
        await query.message.reply_text("⚠️ برای ادامه باید عضو کانال و گروه باشید:", reply_markup=get_join_keyboard())
        return MAIN_MENU

    # ۱. استفاده از run_db برای گرفتن موجودی (برای جلوگیری از فریز شدن ربات)
    user_balance = await run_db(lambda: get_balance(user_id))
    REQUIRED_GOLD = 30

    if user_balance < REQUIRED_GOLD:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_activation")]]
        await query.edit_message_text(
            f"❌ **موجودی طلای شما کافی نیست!**\n\n💰 موجودی فعلی: {user_balance} طلا\n"
            f"⚠️ برای فعال‌سازی به {REQUIRED_GOLD} طلا نیاز دارید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return MAIN_MENU

    # ۲. کسر موجودی و انجام عملیات‌های دیتابیسی در پس‌زمینه
    await run_db(lambda: update_balance(user_id, -REQUIRED_GOLD))
    
    # ۳. منطق پرداخت هدیه به معرف (به صورت غیرهمگام)
    asyncio.create_task(process_referral_reward(user_id, context))

    # ۴. فعال‌سازی نهایی
    await run_db(lambda: supabase.table("users_diamonds").update({"is_active": True}).eq("user_id", user_id).execute())

    contact_button = KeyboardButton(text="📱 ارسال شماره تلفن", request_contact=True)
    phone_keyboard = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)

    await query.edit_message_text("✅ پرداخت تایید شد. در حال انتقال به مرحله بعد...")
    await query.message.reply_text(
        f"✅ **پرداخت با موفقیت انجام شد!**\n💰 مبلغ {REQUIRED_GOLD} طلا از حساب شما کسر شد.\n"
        f"👇 برای تکمیل لاگین، روی دکمه بزرگ زیر صفحه بزنید تا شماره تلفنتان ارسال شود:",
        reply_markup=phone_keyboard,
    )
    return PHONE

async def process_referral_reward(user_id, context):
    """تابع کمکی برای واریز هدیه به معرف بدون مسدود کردن ترد اصلی"""
    try:
        user_data = await run_db(lambda: supabase.table("users_diamonds")
            .select("referred_by", "invite_reward_paid")
            .eq("user_id", user_id).execute())
            
        if user_data.data:
            inviter_id = user_data.data[0].get("referred_by")
            reward_paid = user_data.data[0].get("invite_reward_paid", False)
            
            if inviter_id and not reward_paid:
                inviter_bal = await run_db(lambda: get_balance(inviter_id))
                await run_db(lambda: supabase.table("users_diamonds").update({"diamonds": inviter_bal + 35}).eq("user_id", inviter_id).execute())
                await run_db(lambda: supabase.table("users_diamonds").update({"invite_reward_paid": True}).eq("user_id", user_id).execute())
                
                try:
                    await context.bot.send_message(chat_id=inviter_id, text=f"🎉 یکی از زیرمجموعه‌های شما سلف‌بات خود را فعال کرد! ۳۵ الماس هدیه به حساب شما واریز شد.💎")
                except:
                    pass
    except Exception as e:
        print(f"Error in background referral payout: {e}")

async def handle_cancel_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.contact:
        await update.message.reply_text("❌ لطفاً شماره خود را فقط با استفاده از دکمه «📱 ارسال شماره تلفن» ارسال کنید.")
        return PHONE

    user_id = update.effective_user.id
    phone = update.message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    # نمایش پیام وضعیت به کاربر
    status_msg = await update.message.reply_text("⏳ در حال برقراری ارتباط با تلگرام و ارسال کد...")

    # انتقال منطق سنگین به یک تابع Async جداگانه
    asyncio.create_task(perform_async_phone_auth(user_id, phone, status_msg, context))
    
    return CODE

async def perform_async_phone_auth(user_id, phone, status_msg, context):
    """
    اجرای عملیات سنگینِ اتصال به تلگرام در پس‌زمینه
    """
    try:
        # پاکسازی قبلی‌ها
        if user_id in login_data: del login_data[user_id]
        if user_id in clients:
            try: await clients[user_id].disconnect()
            except: pass
            del clients[user_id]

        client = create_client(user_id)
        await client.connect()

        # درخواست کد از تلگرام
        sent_code = await client.send_code_request(phone)
        
        clients[user_id] = client
        login_data[user_id] = {
            "phone": phone,
            "phone_code_hash": sent_code.phone_code_hash,
            "used": False,
        }
        
        await status_msg.edit_text(
            "🔢 **کد فعال‌سازی تلگرام ارسال شد.**\n\nلطفاً کد دریافتی را وارد کنید:",
            reply_markup=get_code_keyboard("")
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در ارسال کد:\n{e}")
        # در صورت خطا، ConversationHandler را ببندید
        # (نکته: در اینجا به دلیل استفاده از task، ممکن است نیاز باشد کاربر را به منوی اصلی هدایت کنید)
async def handle_code_calculator_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    current_code = context.user_data.get("telegram_code", "")

    # مدیریت دکمه‌های ماشین‌حساب (سریع و سبک)
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
        await query.edit_message_text(
            f"🔢 **کد فعال‌سازی تلگرام ارسال شد.**\n\n✍️ کد وارد شده: `{current_code}`",
            reply_markup=get_code_keyboard(current_code),
        )
        await query.answer()
        return CODE

    # منطق سابمیت کد (بخش سنگین)
    if len(current_code) < 5:
        await query.answer("⚠️ کد تلگرام حداقل باید ۵ رقم باشد!", show_alert=True)
        return CODE

    if user_id not in login_data:
        await query.message.reply_text("❌ جلسه شما یافت نشد. مجدد /start بزنید.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ در حال تایید کد و اتصال به تلگرام...")
    
    # انتقال عملیات احراز هویت به یک تسک پس‌زمینه
    asyncio.create_task(perform_async_sign_in(user_id, current_code, query, context))
    return ConversationHandler.END

async def perform_async_sign_in(user_id, code, query, context):
    """انجام عملیات احراز هویت در پس‌زمینه"""
    try:
        client = clients.get(user_id)
        login_info = login_data[user_id]

        if not client:
            await query.message.reply_text("❌ کلاینت یافت نشد.")
            return

        # انجام Sign In در ترد اصلیِ کلاینت (اما غیرهمگام برای ربات اصلی)
        await client.sign_in(
            phone=login_info["phone"], 
            code=code, 
            phone_code_hash=login_info["phone_code_hash"]
        )
        
        await query.message.reply_text("✅ ورود موفقیت‌آمیز بود! سلف‌بات فعال شد.", reply_markup=get_start_keyboard())
        
        register_handlers(client)
        start_client_background(user_id, client)
        
        # پاکسازی
        if user_id in login_data: del login_data[user_id]
        
    except PhoneCodeExpiredError:
        await query.message.reply_text("❌ کد منقضی شده است. مجدد تلاش کنید.")
    except PhoneCodeInvalidError:
        await query.message.reply_text("❌ کد اشتباه است. لطفا دوباره تلاش کنید.")
    except SessionPasswordNeededError:
        await query.message.reply_text("🔐 اکانت رمز ۲ مرحله‌ای دارد. رمز را بفرستید:")
        context.user_data["awaiting_password"] = True # ذخیره وضعیت برای مرحله بعد
    except Exception as e:
        await query.message.reply_text(f"❌ خطای احراز هویت: {e}")


async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    # نمایش پیام وضعیت به کاربر
    status_msg = await update.message.reply_text("⏳ در حال بررسی رمز دو مرحله‌ای...")

    # انتقال عملیات احراز هویت رمز به یک تسک پس‌زمینه
    asyncio.create_task(perform_async_password_signin(user_id, password, status_msg))
    
    return ConversationHandler.END

async def perform_async_password_signin(user_id, password, status_msg):
    """انجام Sign In با رمز در پس‌زمینه"""
    try:
        client = clients.get(user_id)
        if not client:
            await status_msg.edit_text("❌ کلاینت یافت نشد. لطفاً دوباره /start بزنید.")
            return

        # انجام عملیات سنگین در پس‌زمینه
        await client.sign_in(password=password)
        
        await status_msg.edit_text("✅ ورود موفقیت‌آمیز بود! سلف‌بات شما فعال شد.")
        
        register_handlers(client)
        start_client_background(user_id, client)
        
        # پاکسازی داده‌های موقت لاگین
        if user_id in login_data:
            del login_data[user_id]
            
    except Exception as e:
        await status_msg.edit_text(f"❌ رمز عبور اشتباه است یا خطایی رخ داده:\n{e}\n\nلطفاً دوباره /start بزنید.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)