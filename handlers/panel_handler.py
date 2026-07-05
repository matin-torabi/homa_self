import telegram
from telethon import events
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import re
from utils import get_user_locks_from_db, save_user_lock_to_db
from handlers.text_mode_handler import get_user_text_mode, set_user_text_mode 
from handlers.chat_action_handler import get_user_chat_action, set_user_chat_action
from utils import get_user_filters_from_db, save_user_filters_to_db, db_execute
from utils import get_chat_guard_from_db, save_chat_guard_to_db

CALC_STATE = {}

# تابع کمکی برای ساخت دکمه‌های ماشین‌حساب
def get_calculator_keyboard(owner_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("7", callback_data=f"clc_7_{owner_id}"),
            InlineKeyboardButton("8", callback_data=f"clc_8_{owner_id}"),
            InlineKeyboardButton("9", callback_data=f"clc_9_{owner_id}"),
            InlineKeyboardButton("÷", callback_data=f"clc_div_{owner_id}")
        ],
        [
            InlineKeyboardButton("4", callback_data=f"clc_4_{owner_id}"),
            InlineKeyboardButton("5", callback_data=f"clc_5_{owner_id}"),
            InlineKeyboardButton("6", callback_data=f"clc_6_{owner_id}"),
            InlineKeyboardButton("×", callback_data=f"clc_mul_{owner_id}")
        ],
        [
            InlineKeyboardButton("1", callback_data=f"clc_1_{owner_id}"),
            InlineKeyboardButton("2", callback_data=f"clc_2_{owner_id}"),
            InlineKeyboardButton("3", callback_data=f"clc_3_{owner_id}"),
            InlineKeyboardButton("-", callback_data=f"clc_sub_{owner_id}")
        ],
        [
            InlineKeyboardButton("0", callback_data=f"clc_0_{owner_id}"),
            InlineKeyboardButton(".", callback_data=f"clc_dot_{owner_id}"),
            InlineKeyboardButton("=", callback_data=f"clc_equal_{owner_id}"),
            InlineKeyboardButton("+", callback_data=f"clc_add_{owner_id}")
        ],
        [
            InlineKeyboardButton("C", callback_data=f"clc_clear_{owner_id}", style="danger"),
            InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")
        ]
    ])

async def get_locks_keyboard(owner_id):
    # دریافت آخرین وضعیت از دیتابیس
    locks = await get_user_locks_from_db(owner_id)
    if not locks:
        locks = {
            "username": False, "link": False, "reply": False, "photo": False,
            "gif": False, "sticker": False, "pv": False, "forward": False
        }

    def status_color(key):
        return "success" if locks.get(key, False) else "danger"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"قفل یوزرنیم", callback_data=f"tog_username_{owner_id}", style=f"{status_color('username')}"),
            InlineKeyboardButton(f"قفل لینک", callback_data=f"tog_link_{owner_id}", style=f"{status_color('link')}")
        ],
        [
            InlineKeyboardButton(f"قفل ریپلای", callback_data=f"tog_reply_{owner_id}", style=f"{status_color('reply')}"),
            InlineKeyboardButton(f"قفل عکس", callback_data=f"tog_photo_{owner_id}", style=f"{status_color('photo')}")
        ],
        [
            InlineKeyboardButton(f"قفل گیف", callback_data=f"tog_gif_{owner_id}", style=f"{status_color('gif')}"),
            InlineKeyboardButton(f"قفل استیکر", callback_data=f"tog_sticker_{owner_id}", style=f"{status_color('sticher')}")
        ],
        [
            InlineKeyboardButton(f"قفل پیوی", callback_data=f"tog_pv_{owner_id}", style=f"{status_color('pv')}"),
            InlineKeyboardButton(f"قفل فوروارد", callback_data=f"tog_forward_{owner_id}", style=f"{status_color('forward')}")
        ],
        [
            InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")
        ]
    ])

def register_panel_handler(client):
    """ثبت هندلر سلف‌بات جهت فرستادن منوی اصلی از طریق ربات ادمین"""
    # 🎯 فیکس پترن: حالا فقط وقتی کاربر دقیقاً بنویسد "*پنل" دستور اجرا می‌شود
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*پنل$'))
    async def handle_self_panel_command(event):
        bot_username = "Homa_panel_dev_bot"
        try:
            inline_results = await event.client.inline_query(bot_username, 'get_self_panel')
            if inline_results:
                await event.delete() # حذف پیام *پنل جهت تمیز ماندن چت
                await inline_results[0].click(entity=event.chat_id, reply_to=event.reply_to_msg_id)
        except asyncio.TimeoutError:
            # خنثی کردن بی‌صدای خطای تایم‌اوت شبکه تلگرام
            pass
        except Exception as e:
            # نادیده گرفتن خطاهای ناشی از تاخیر گیت‌وی تلگرام و جلوگیری از شلوغی ترمینال
            if "did not answer" in str(e) or "Timeout" in str(e):
                pass
            else:
                print(f"⚠️ Error triggering inline panel: {e}")

def get_secretary_keyboard(enabled_status: bool, owner_id: int) -> InlineKeyboardMarkup:
    """ساخت منوی منشی بر اساس وضعیت زنده سوپابیس"""
    # تغییر ظاهر و وضعیت متن دکمه شیشه‌ای منشی
    btn_style = "success" if enabled_status else "danger"
    
    keyboard = [
        # ساختار کالبک دیتا: sec_toggle_ownerId -> بخش سوم آیدی کاربر است و کرش نمی‌کند
        [InlineKeyboardButton("منشی", callback_data=f"sec_toggle_{owner_id}", style=btn_style)],
        [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_guard_keyboard(config, owner_id):
    """ساخت دکمه‌های شیشه‌ای نگهبان چت با فرمت اختصاصی علامت و پرانتز"""
    # استخراج وضعیت‌ها از کانفیگ دیتابیس (اگر فیلدی نبود، پیش‌فرض True فرض می‌شود)
    save_deleted = config.get("save_deleted", True)
    save_edited = config.get("save_edited", True)
    save_ttl = config.get("save_ttl", True)

    keyboard = [
        [
            InlineKeyboardButton(
                "ذخیره پیام حذف شده ",
                callback_data=f"grd_toggle_del_{owner_id}",
                style="success" if save_deleted else "danger",
            )
        ],
        [
            InlineKeyboardButton(
                "ذخیره ویرایش شده",
                callback_data=f"grd_toggle_edt_{owner_id}",
                style="success" if save_edited else "danger",
            )
        ],
        [
            InlineKeyboardButton(
                "ذخیره عکس تایمی",
                callback_data=f"grd_toggle_ttl_{owner_id}",
                style="success" if save_ttl else "danger",
            )
        ],
        [
            InlineKeyboardButton(
                "« بازگشت",
                callback_data=f"panel_sett_{owner_id}",
                style="primary",
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

def get_seen_keyboard(config, owner_id):
    auto_seen = config.get("auto_seen", True) if config else True
    seen_style = "success" if auto_seen else "danger"
    
    keyboard = [
        # پترن ۳ بخشی اختصاصی بدون کلمات مشترک با بخش‌های دیگر پنل تو
        [InlineKeyboardButton("سین خودکار ", callback_data=f"toggle_seen_{owner_id}", style=seen_style)],
        # دکمه بازگشت هماهنگ با پنل تنظیمات اصلی تو
        [InlineKeyboardButton("» بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_force_join_keyboard(config, channels_count, owner_id):
    is_enabled = config.get("enabled", False) if config else False
    text_style = "success" if is_enabled else "danger"
    
    keyboard = [
        [InlineKeyboardButton("عضویت اجباری", callback_data=f"fj_toggle_{owner_id}", style=text_style)],
        [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_textmode_keyboard(owner_id: int, current_mode: str) -> InlineKeyboardMarkup:
    modes = {
        "bold": "بولد", "italic": "ایتالیک", "strike": "خط‌خورده", "mono": "تک‌فاصله",
        "quote": "نقل قول", "underline": "زیرخط", "spoiler": "اسپویلر", "gradient": "تدریجی"
    }
    
    # تعیین وضعیت ضربدر یا تیک دکمه‌ها بر اساس مود فعلی دیتابیس
    st = {k: "success" if current_mode == k else "danger" for k in modes.keys()}
    
    keyboard = [
        [
            InlineKeyboardButton(f"نقل قول", callback_data=f"tmode_quote_{owner_id}", style=f"{st['quote']}"),
            InlineKeyboardButton(f"بولد", callback_data=f"tmode_bold_{owner_id}", style=f"{st['bold']}")
        ],
        [
            InlineKeyboardButton(f"زیرخط", callback_data=f"tmode_underline_{owner_id}", style=f"{st['underline']}"),
            InlineKeyboardButton(f"ایتالیک", callback_data=f"tmode_italic_{owner_id}", style=f"{st['italic']}")
        ],
        [
            InlineKeyboardButton(f"اسپویلر", callback_data=f"tmode_spoiler_{owner_id}", style=f"{st['spoiler']}"),
            InlineKeyboardButton(f"خط‌خورده", callback_data=f"tmode_strike_{owner_id}", style=f"{st['strike']}")
        ],
        [
            InlineKeyboardButton(f"تدریجی", callback_data=f"tmode_gradient_{owner_id}", style=f"{st['gradient']}"),
            InlineKeyboardButton(f"تک‌فاصله", callback_data=f"tmode_mono_{owner_id}", style=f"{st['mono']}")
        ],
        [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_action_keyboard(owner_id: int, current_action: str) -> InlineKeyboardMarkup:
    """ساخت دکمه‌های منوی تنظیمات اکشن با تیک فعال/غیرفعال (✔️/❌)"""
    
    actions = {
        "typing": "تایپ", "record-audio": "ویس",
        "record-round": "ویدیو گرد", "upload-photo": "عکس",
        "upload-video": "ویدیو", "upload-document": "سند",
        "choose-sticker": "استیکر", "playing": "بازی"
    }
    
    # ست کردن تیک ضربدر یا تیک سبز وضعیت
    st = {k: "success" if current_action == k else "danger" for k in actions.keys()}
    
    keyboard = [
        [
            InlineKeyboardButton(f"ویس", callback_data=f"action_record-audio_{owner_id}", style=f"{st['record-audio']}"),
            InlineKeyboardButton(f"تایپ ", callback_data=f"action_typing_{owner_id}", style=f"{st['typing']}")
        ],
        [
            InlineKeyboardButton(f"عکس", callback_data=f"action_upload-photo_{owner_id}", style=f"{st['upload-photo']}"),
            InlineKeyboardButton(f"ویدیو گرد", callback_data=f"action_record-round_{owner_id}", style=f"{st['record-round']}")
        ],
        [
            InlineKeyboardButton(f"سند", callback_data=f"action_upload-document_{owner_id}", style=f"{st['upload-document']}"),
            InlineKeyboardButton(f"ویدیو", callback_data=f"action_upload-video_{owner_id}", style=f"{st['upload-video']}")
        ],
        [
            InlineKeyboardButton(f"بازی ", callback_data=f"action_playing_{owner_id}", style=f"{st['playing']}"),
            InlineKeyboardButton(f"استیکر", callback_data=f"action_choose-sticker_{owner_id}", style=f"{st['choose-sticker']}")
        ],
        [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_filter_keyboard(owner_id: int, config: dict) -> InlineKeyboardMarkup:
    """ساخت دکمه‌های منوی فیلتر کلمات بر اساس الگوی تصویر پنجم"""
    is_enabled = config.get("enabled", False)
    emoji_style = "success" if is_enabled else "danger"
    
    keyboard = [
        # دکمه وضعیت اصلی سیستم فیلتر کلمات
        [InlineKeyboardButton(f"فیلتر کلمات", callback_data=f"toggle_filter_status_{owner_id}", style=emoji_style)],
        # دکمه بازگشت به منوی تنظیمات اصلی
        [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_panel_clicks(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    try:
        owner_id = int(data.split("_")[-1])
    except ValueError:
        return

    # لایه امنیت: اگر کسی غیر از فراخوانی کننده روی دکمه کلیک کرد
    if user_id != owner_id:
        await query.answer("❌ این پنل متعلق به شما نیست!", show_alert=True)
        return

    # پاسخ آنی به کالبک برای ناپدید شدن آیکون لودینگ روی دکمه
    try:
        await query.answer()
    except Exception:
        pass

    # 1️⃣ منوی اصلی: بازگشت به ریشه
    if data.startswith("panel_main_"):
        main_text = "Panel Management\n\nبه منوی مدیریت هوما خوش آمدید. لطفاً یک بخش را انتخاب کنید:"
        keyboard = [
            [
                InlineKeyboardButton("👤 اکانت من", callback_data=f"panel_acc_{owner_id}", style="primary"),
                InlineKeyboardButton("مدیریت و راهنمایی", callback_data=f"panel_sett_{owner_id}", style="success")
            ],
            [InlineKeyboardButton("❌ بستن پنل", callback_data=f"panel_close_{owner_id}", style="danger")]
        ]
        try:
            await query.edit_message_text(text=main_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass

    # 2️⃣ زیرمنوی: حساب کاربری
    elif data.startswith("panel_acc_"):
        user_name = query.from_user.first_name
        username = f"@{query.from_user.username}" if query.from_user.username else "ندارد"
        user_gold_balance = 0  
        
        try:
            from config import supabase
            clean_owner_id = int(owner_id)

            db_query = (
                supabase.table("users_diamonds")
                .select("diamonds")
                .eq("user_id", clean_owner_id)
            )

            response = await db_execute(db_query)

            if response.data:
                user_gold_balance = response.data[0].get("diamonds", 0)

        except Exception as db_error:
            print(f"⚠️ Error fetching diamonds from Supabase: {db_error}")

        toman_balance = user_gold_balance * 35
        caption_text = (
            f"<b>اطلاعات حساب کاربری</b>\n\n"
            f"<b>نام:</b> {user_name}\n"
            f"<b>یوزرنیم:</b> {username}\n"
            f"<b>آیدی عددی:</b> <code>{owner_id}</code>\n"
            f"<b>موجود طلا:</b> {user_gold_balance:,}\n"
            f"<b>معادل تومان:</b> {toman_balance:,} تومان"
        )
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_main_{owner_id}", style="primary")]]
        try:
            await query.edit_message_text(
                text=caption_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            import traceback
            traceback.print_exc()

    # 3️⃣ زیرمنوی اصلی: تنظیمات سلف
    elif data.startswith("panel_sett_"):
        settings_text = (
            "⚙️ › **تنظیمات پیشرفته سلف‌بات**\n\n"
            "با استفاده از دکمه‌های زیر می‌توانید قابلیت‌های مختلف سلف‌بات خود را مدیریت و پیکربندی کنید:"
        )
        keyboard = [
            [
                InlineKeyboardButton("نگهبان چت", callback_data=f"sett_guard_{owner_id}"),
                InlineKeyboardButton("ساعت", callback_data=f"sett_time_{owner_id}"),
                InlineKeyboardButton("حالت متن", callback_data=f"sett_textmode_{owner_id}")
            ],
            [
                InlineKeyboardButton("اکشن", callback_data=f"sett_action_{owner_id}"),
                InlineKeyboardButton("قفل‌ها", callback_data=f"sett_locks_{owner_id}"),
                # InlineKeyboardButton("لوگو", callback_data=f"sett_logo_{owner_id}"),
                InlineKeyboardButton("پینگ", callback_data=f"sett_ping_{owner_id}")
            ],
            [
                InlineKeyboardButton("فیلتر کلمات", callback_data=f"sett_filter_{owner_id}"),
                InlineKeyboardButton("منشی", callback_data=f"sett_secretary_{owner_id}"),
                InlineKeyboardButton("دوست و دشمن", callback_data=f"sett_fr_en_{owner_id}")
            ],
            [
                InlineKeyboardButton("عضویت اجباری پیوی", callback_data=f"sett_fjoin_{owner_id}"),
                InlineKeyboardButton("پاسخ خودکار", callback_data=f"sett_auto_res_{owner_id}")
            ],
            [
                InlineKeyboardButton("اسپم", callback_data=f"sett_spam_{owner_id}"),
                InlineKeyboardButton("ریکت", callback_data=f"sett_react_{owner_id}"),
                InlineKeyboardButton("دانلودر", callback_data=f"sett_down_{owner_id}")
            ],
            [
                InlineKeyboardButton("حذف", callback_data=f"sett_del_{owner_id}"),
                InlineKeyboardButton("بلاک", callback_data=f"sett_block_{owner_id}"),
                # InlineKeyboardButton("تگ", callback_data=f"sett_tag_{owner_id}"),
                # InlineKeyboardButton("اطلاعات", callback_data=f"sett_info_{owner_id}"),
                InlineKeyboardButton("سکوت", callback_data=f"sett_mute_{owner_id}")
            ],
            [
                InlineKeyboardButton("هوش مصنوعی", callback_data=f"sett_ai_{owner_id}"),
                InlineKeyboardButton("سین خودکار", callback_data=f"sett_seen_{owner_id}")
            ],
            [
                # InlineKeyboardButton("÷ / ×", callback_data=f"sett_calc_{owner_id}"),
                InlineKeyboardButton("تقلب", callback_data=f"sett_cheat_{owner_id}"),
                InlineKeyboardButton("انیمیشن", callback_data=f"sett_anim_{owner_id}"),
                InlineKeyboardButton("ترجمه", callback_data=f"sett_trans_{owner_id}")
            ],
            [
                # InlineKeyboardButton("سرچ ویس آماده", callback_data=f"sett_voice_{owner_id}"),
                InlineKeyboardButton("÷ / ×", callback_data=f"sett_calc_{owner_id}"),
                # InlineKeyboardButton("تگ", callback_data=f"sett_tag_{owner_id}"),
                InlineKeyboardButton("تبدیل متن به ویس", callback_data=f"sett_ttv_{owner_id}")
            ],
            [
                # InlineKeyboardButton("فضول پروفایل", callback_data=f"sett_stalker_{owner_id}"),
                InlineKeyboardButton("اطلاعات", callback_data=f"sett_info_{owner_id}"),
                # InlineKeyboardButton("تبچی", callback_data=f"sett_tabchi_{owner_id}"),
                InlineKeyboardButton("لوگو", callback_data=f"sett_logo_{owner_id}"),
                InlineKeyboardButton("پروکسی", callback_data=f"sett_proxy_{owner_id}")
            ],
            [
                InlineKeyboardButton("اسکرین", callback_data=f"sett_scr_{owner_id}"),
                # InlineKeyboardButton("قیمت ارز", callback_data=f"sett_currency_{owner_id}"),
                InlineKeyboardButton("کامنت اول", callback_data=f"sett_comment_{owner_id}")
            ],
            [InlineKeyboardButton("« بازگشت", callback_data=f"panel_main_{owner_id}", style="primary")]
        ]
        try:
            await query.edit_message_text(text=settings_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass

    # 4️⃣ زیرمنوی اختصاصی: پینگ (نقل‌قول با قابلیت کپی فوری دستور)
    elif data.startswith("sett_ping_"):
        ping_text = (
            "**دستورات بخش لوگو:**\n\n"
            "> دستورات\n"
            "\n"
            ">  `\*پینگ`"  
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=ping_text,
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing ping menu: {e}")
    
    elif data.startswith("sett_time_"):
        clock_text = (
            ">  دستورات\n"
            "\n"
            ">  `*ساعت نام روشن`\n"
            "\n"
            ">  `*ساعت نام خاموش`\n"
            "\n"
            ">  `*ساعت بیو روشن`\n"
            "\n"
            ">  `*ساعت بیو خاموش`\n"
            "\n"
            ">  `*فونت 2`\n"
            "\n"
            ">  فونت را از 1 تا 10 وارد کنین\n"

        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=clock_text,
                parse_mode="MarkdownV2",  # پردازش بدون نقص نقل‌قول و متون کپی‌شونده
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing clock menu: {e}")

    elif data.startswith("sett_locks_"):
        lock_text = (
            "🔐 › **تنظیمات و مدیریت قفل‌های سلف‌بات**\n\n"
            "جهت فعال یا غیرفعال‌سازی هر یک از قفل‌های حفاظتی پیوی، روی دکمه مربوطه کلیک کنید:"
        )
        try:
            await query.edit_message_text(
                text=lock_text,
                parse_mode="Markdown",
                reply_markup= await get_locks_keyboard(owner_id)
            )
        except Exception as e:
            print(f"⚠️ Error opening locks menu: {e}")

    elif data.startswith("sett_secretary_"):
        owner_id = int(data.split("_")[2])
        
        from utils import get_auto_reply_from_db
        config = await get_auto_reply_from_db(owner_id)
        
        if not config:
            config = {"enabled": False, "message": " الان آنلاین نیستم، بعداً پیام میدم!", "interval": 30, "mode": "once"}
            
        is_enabled = config.get("enabled", False)
        current_msg = config.get("message", " الان آنلاین نیستم، بعداً پیام میدم!")
        current_interval = config.get("interval", 30)
        
        secretary_text = (
            "<b>دستورات</b>\n\n"
            "<blockquote><code>*منشی پیام</code></blockquote>\n\n"
            "<blockquote><code>*منشی تایم 10</code></blockquote>\n\n"
            f"<blockquote><b>تایم فعلی:</b> {current_interval} دقیقه</blockquote>\n\n"
            f"<blockquote><b>متن فعلی: </b> {current_msg} </blockquote>\n\n"
        )
        
        reply_markup = get_secretary_keyboard(is_enabled, owner_id)
        try:
            await query.edit_message_text(text=secretary_text, parse_mode="HTML", reply_markup=reply_markup)
        except: pass
        return

    elif data.startswith("sec_toggle_"):
        parts = data.split("_")
        owner_id = int(parts[2])
        
        from utils import get_auto_reply_from_db, save_auto_reply_to_db
        config = await get_auto_reply_from_db(owner_id)
        if not config:
            config = {"enabled": False, "message": " الان آنلاین نیستم، بعداً پیام میدم!", "interval": 30, "mode": "once"}
            
        # معکوس کردن وضعیت فعلی
        new_status = not config.get("enabled", False)
        config["enabled"] = new_status
        
        # ذخیره وضعیت جدید مستقیم در سوپابیس
        await save_auto_reply_to_db(owner_id, {"enabled": new_status})
        
        # همگام‌سازی سریع با حافظه موقت تلتون
        clients_dict = context.bot_data.get("clients", {})
        client_bot = clients_dict.get(owner_id) or clients_dict.get(str(owner_id))
        if client_bot and hasattr(client_bot, 'reply_config') and client_bot.reply_config:
            client_bot.reply_config["enabled"] = new_status
            if hasattr(client_bot, 'last_reply_cache'):
                client_bot.last_reply_cache.clear()
        
        current_msg = config.get("message", " الان آنلاین نیستم، بعداً پیام میدم!")
        current_interval = config.get("interval", 30)

        secretary_text = (
            "<b>دستورات</b>\n\n"
            "<blockquote><code>*منشی پیام</code></blockquote>\n\n"
            "<blockquote><code>*منشی تایم 10</code></blockquote>\n\n"
            f"<blockquote><b>تایم فعلی:</b> {current_interval} دقیقه</blockquote>\n\n"
            f"<blockquote><b>متن فعلی: </b> {current_msg} </blockquote>\n\n"
        )
        
        # 💥 اصلاح اصلی: در این خط متغیر به new_status تغییر کرد تا ارور UnboundLocalError رفع شود
        reply_markup = get_secretary_keyboard(new_status, owner_id)
        try:
            await query.edit_message_text(text=secretary_text, parse_mode="HTML", reply_markup=reply_markup)
        except: pass
        
        status_word = "روشن" if new_status else "خاموش"
        await query.answer(f"منشی خودکار با موفقیت {status_word} شد.", show_alert=False)
        return

    elif data.startswith("tog_"):
        # استخراج نام قفل کلیک شده (مثلا: link, username)
        lock_key = data.split("_")[1]
        
        # دریافت وضعیت فعلی از دیتابیس
        current_locks = await get_user_locks_from_db(owner_id)
        if not current_locks:
            current_locks = {
                "username": False, "link": False, "reply": False, "photo": False,
                "gif": False, "sticker": False, "pv": False, "forward": False
            }
            
        # معکوس کردن وضعیت فعلی قفل (تغییر True به False و بالعکس)
        new_state = not current_locks.get(lock_key, False)
        
        # ذخیره وضعیت جدید در دیتابیس سوپابیس
        if await save_user_lock_to_db(owner_id, lock_key, new_state):
            
            # 🔥 بسیار مهم: آپدیت آنی و زنده کش کلاینت سلف‌بات در حافظه ران‌تایم برای اعمال بدون تاخیر
            try:
                from handlers.client_manager import clients
                if owner_id in clients:
                    target_client = clients[owner_id]
                    if hasattr(target_client, 'my_locks') and target_client.my_locks is not None:
                        target_client.my_locks[lock_key] = new_state
            except Exception as cache_err:
                print(f"⚠️ خطای آپدیت کش کلاینت: {cache_err}")
                
        # بروزرسانی شیک و درجا منوی دکمه‌ها بدون پرش صفحه
        lock_text = (
            "🔐 › **تنظیمات و مدیریت قفل‌های سلف‌بات**\n\n"
            "جهت فعال یا غیرفعال‌سازی هر یک از قفل‌های حفاظتی پیوی، روی دکمه مربوطه کلیک کنید:"
        )
        try:
            await query.edit_message_text(
                text=lock_text,
                parse_mode="Markdown",
                reply_markup= await get_locks_keyboard(owner_id)
            )
        except telegram.error.BadRequest:
            pass

    elif data.startswith("sett_guard_"):
        owner_id = int(data.split("_")[2])
        
        # خواندن وضعیت فعلی از سوپابیس
        config = await get_chat_guard_from_db(owner_id)
        if not config:
            config = {"user_id": owner_id, "save_deleted": True, "save_edited": True, "save_ttl": True}
        
        guard_text = (
            "<blockquote><b>🛡️ منوی تنظیمات نگهبان چت</b>\n\n"
            "با استفاده از دکمه‌های زیر می‌توانید وضعیت ذخیره‌سازی پیام‌های حذف شده، "
            "ویرایش شده و رسانه‌های تایم‌دار را مدیریت کنید.</blockquote>"
        )
        
        reply_markup = get_guard_keyboard(config, owner_id)
        try:
            await query.edit_message_text(text=guard_text, parse_mode="HTML", reply_markup=reply_markup)
        except: pass
        return

    elif data.startswith("grd_toggle_"):
        parts = data.split("_")
        field_type = parts[2]   
        owner_id = int(parts[3])
        
        config = await get_chat_guard_from_db(owner_id)
        if not config:
            config = {"user_id": owner_id, "save_deleted": True, "save_edited": True, "save_ttl": True}
        
        target_field = ""
        alert_word = ""
        
        if field_type == "del":
            target_field = "save_deleted"
            alert_word = "ذخیره پیام‌های حذف شده"
        elif field_type == "edt":
            target_field = "save_edited"
            alert_word = "ذخیره پیام‌های ویرایش شده"
        elif field_type == "ttl":
            target_field = "save_ttl"
            alert_word = "ذخیره عکس‌های تایمی"
            
        new_status = not config.get(target_field, False)
        config[target_field] = new_status
        
        await save_chat_guard_to_db(owner_id, config)
        
        clients_dict = context.bot_data.get("clients", {})
        client_bot = clients_dict.get(owner_id) or clients_dict.get(str(owner_id))
        if client_bot and hasattr(client_bot, 'guard_config') and client_bot.guard_config:
            client_bot.guard_config[target_field] = new_status
            
        guard_text = (
            "<blockquote><b>🛡️ منوی تنظیمات نگهبان چت</b>\n\n"
            "با استفاده از دکمه‌های زیر می‌توانید وضعیت ذخیره‌سازی پیام‌های حذف شده، "
            "ویرایش شده و رسانه‌های تایم‌دار را مدیریت کنید.</blockquote>"
        )
        reply_markup = get_guard_keyboard(config, owner_id)
        
        try:
            await query.edit_message_text(text=guard_text, parse_mode="HTML", reply_markup=reply_markup)
        except: pass
        
        status_word = "روشن" if new_status else "خاموش"
        await query.answer(f"{alert_word} با موفقیت {status_word} شد.", show_alert=False)
        return

    elif data.startswith("sett_seen_"):
        owner_id = int(data.split("_")[2])
        
        from utils import get_auto_seen_from_db
        config = await get_auto_seen_from_db(owner_id)
        
        # ←←← اصلاح مهم: پشتیبانی از dict و bool
        if isinstance(config, dict):
            auto_seen_status = config.get("auto_seen", False)
        else:
            auto_seen_status = bool(config)
        
        status_word = "روشن" if auto_seen_status else "خاموش"
        seen_text = f"<blockquote>وضعیت : {status_word}</blockquote>"
        
        reply_markup = get_seen_keyboard(config, owner_id)
        
        try:
            await query.edit_message_text(text=seen_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: 
            print(f"Error editing text: {e}")
        return

    elif data.startswith("toggle_seen_"):
        # دیتای ورودی: toggle_seen_6477547634 -> بخش ۲ آیدی کاربر است
        owner_id = int(data.split("_")[2])
        
        from utils import get_auto_seen_from_db, save_auto_seen_to_db
        config = await get_auto_seen_from_db(owner_id)
            
        current_status = config.get("auto_seen", True)
        new_status = not current_status
        
        # ذخیره در جدول مستقل سوپابیس
        await save_auto_seen_to_db(owner_id, new_status)
        
        # آپدیت آنی کش رم کلاینت‌ها برای سرعت بالا
        from handlers.auto_seen_handler import AUTO_SEEN_CACHE
        AUTO_SEEN_CACHE[owner_id] = new_status
        
        # بازسازی متن پنل طبق عکسی که فرستادی
        status_word = "روشن" if new_status else "خاموش"
        seen_text = f"<blockquote>وضعیت : {status_word}</blockquote>"
        
        updated_config = {"user_id": owner_id, "auto_seen": new_status}
        reply_markup = get_seen_keyboard(updated_config, owner_id)
        
        try:
            await query.edit_message_text(text=seen_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: 
            print(f"Error toggling text: {e}")
        
        await query.answer(f"وضعیت سین خودکار {status_word} شد.")
        return

    # 🔘 اتصال به دکمه "حالت متن" که فرستادی
    elif data.startswith("sett_textmode_"):
        try:
            owner_id = int(data.split("_")[-1])
        except:
            owner_id = 0
            
        current_mode = await get_user_text_mode(owner_id)
        menu_text = "⚙️ **تنظیمات حالت متن**\n\nحالت مورد نظر خود را برای فونت خودکار پیام‌ها انتخاب کنید:"
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown",
                reply_markup=build_textmode_keyboard(owner_id, current_mode)
            )
        except telegram.error.BadRequest: pass

    # 🔄 مدیریت کلیک روی تک‌تک حالت‌های فونت و تیک خوردن لوپ چت
    elif data.startswith("tmode_"):
        try:
            parts = data.split("_")
            selected_mode = parts[1]
            owner_id = int(parts[2])
        except:
            return
            
        current_mode = await get_user_text_mode(owner_id)
        
        # سوییچ کردن: اگر دوباره کلیک شد غیرفعال (none) شود، در غیر این صورت مود جدید فعال شود
        new_mode = "none" if current_mode == selected_mode else selected_mode
        await set_user_text_mode(owner_id, new_mode)
        
        menu_text = "⚙️ **تنظیمات حالت متن**\n\nحالت مورد نظر خود را برای فونت خودکار پیام‌ها انتخاب کنید:"
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown",
                reply_markup=build_textmode_keyboard(owner_id, new_mode)
            )
        except telegram.error.BadRequest:
            pass

    # 🔘 ۱. باز کردن منوی اصلی تنظیمات اکشن
    elif data.startswith("sett_action_"):
        try:
            owner_id = int(data.split("_")[-1])
        except:
            owner_id = 0
            
        current_action = await get_user_chat_action(owner_id)
        menu_text = "⚙️ **تنظیمات وضعیت اکشن چت**\n\nحالت مورد نظر خود را برای نمایش اکشن فیک انتخاب کنید:"
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown",
                reply_markup=build_action_keyboard(owner_id, current_action)
            )
        except telegram.error.BadRequest: pass

    # 🔄 ۲. تغییر مود و تیک زدن هوشمند وضعیت کلیک شده
    elif data.startswith("action_"):
        try:
            parts = data.split("_")
            selected_action = parts[1]
            owner_id = int(parts[2])
        except:
            return
            
        current_action = await get_user_chat_action(owner_id)
        
        # سوییچ وضعیت: کلیک دوباره یعنی خاموش شدن اکشن (none)
        new_action = "none" if current_action == selected_action else selected_action
        await set_user_chat_action(owner_id, new_action)
        
        menu_text = "⚙️ **تنظیمات وضعیت اکشن چت**\n\nحالت مورد نظر خود را برای نمایش اکشن فیک انتخاب کنید:"
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown",
                reply_markup=build_action_keyboard(owner_id, new_action)
            )
        except telegram.error.BadRequest:
            pass

    # 5
    elif data.startswith("sett_logo_"):
        logo_text = (
            "**دستورات بخش لوگو:**\n\n"
            "> دستورات\n"
            "\n"
            ">  `\*لوگو مهدی`"  
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=logo_text,
                parse_mode="MarkdownV2",  
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing logo menu: {e}")

# 🔘 باز کردن منوی فیلتر کلمات (اتصال به دکمه منوی اصلی تنظیمات)
    elif data.startswith("sett_filter_"):
        try:
            owner_id = int(data.split("_")[-1])
        except:
            return
            
        config = await get_user_filters_from_db(owner_id)
        words = config.get("words", []) if config.get("words") else []
        
        # متن پیش‌نمایش دایرکتوری دستورات به صورت نقل‌قول استاندارد شده HTML
        menu_text = (
            "<blockquote><b>دستورات</b></blockquote>\n\n"
            f"<blockquote><b>تعداد کلمات فیلتر:</b> <code>{len(words)}</code></blockquote>\n\n"
            "<blockquote><code>*فیلتر کلمه کلمه</code></blockquote>\n\n"
            "<blockquote><code>*حذف فیلتر کلمه</code></blockquote>\n\n"
            "<blockquote><code>*لیست فیلتر</code></blockquote>\n\n"
            "<blockquote><code>*پاکسازی فیلتر</code></blockquote>"
        )
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="HTML",
                reply_markup=build_filter_keyboard(owner_id, config)
            )
        except telegram.error.BadRequest: pass

    # 🔄 تغییر وضعیت روشن/خاموش فیلتر از داخل پنل ربات
    elif data.startswith("toggle_filter_status_"):
        try:
            owner_id = int(data.split("_")[-1])
        except:
            return
            
        config = await get_user_filters_from_db(owner_id)
        new_status = not config.get("enabled", False)
        
        # ذخیره وضعیت جدید به صورت مستقیم در سوپابیس
        if await save_user_filters_to_db(owner_id, {"enabled": new_status}):
            config["enabled"] = new_status
            
        words = config.get("words", []) if config.get("words") else []
        
        menu_text = (
            "<blockquote><b>دستورات</b></blockquote>\n\n"
            f"<blockquote><b>تعداد کلمات فیلتر:</b> <code>{len(words)}</code></blockquote>\n\n"
            "<blockquote><code>*فیلتر کلمه کلمه</code></blockquote>\n\n"
            "<blockquote><code>*حذف فیلتر کلمه</code></blockquote>\n\n"
            "<blockquote><code>*لیست فیلتر</code></blockquote>\n\n"
            "<blockquote><code>*پاکسازی فیلتر</code></blockquote>"
        )
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="HTML",
                reply_markup=build_filter_keyboard(owner_id, config)
            )
        except telegram.error.BadRequest: pass


    # 8            
    elif data.startswith("sett_react_"):
        react_text = (
            ">  دستورات\n"
            "\n"
            ">  `*😂 ریکت`\n"
            "\n"
            ">  `*لیست ریکت`\n"
            "\n"
            ">  `*پاکسازی ریکت`\n"
            "\n"
            ">  `*حذف ریکت`\n"
        )
        

        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=react_text,
                parse_mode="MarkdownV2",  # پردازش بدون نقص نقل‌قول و متون کپی‌شونده
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing react menu: {e}")

    # 9            
    elif data.startswith("sett_spam_"):
        spam_text = (
            ">  دستورات\n"
            "\n"
            ">  `*اسپم 10 سلام`\n"
            "\n"
            ">  `*اسپم سریع 10 سلام`\n"
            "\n"
            ">  `*اسپم کند 10 سلام`\n"
            "\n"
            ">  `*پایان اسپم`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=spam_text,
                parse_mode="MarkdownV2",  
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing spam menu: {e}")

    # 10            
    elif data.startswith("sett_mute_"):
        mute_text = (
            ">  دستورات\n"
            "\n"
            ">  `*سکوت`\n"
            "\n"
            ">  `*حذف سکوت`\n"
            "\n"
            ">  `*لیست سکوت`\n"
            "\n"
            ">  `*پاکسازی سکوت`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=mute_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing mute menu: {e}")
    
    elif data.startswith("sett_down_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        menu_text = "📥 **به بخش دانلودر پیشرفته خوش آمدید**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
        
        # ساخت همان دو دکمه سبز رنگ تصویر شما
        keyboard = [
            [
                InlineKeyboardButton("دانلود از چنل پرایوت", callback_data=f"down_private_{owner_id}", style="success"),
                InlineKeyboardButton("دانلود از اینستا", callback_data=f"down_insta_{owner_id}", style="danger")
            ],
            [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
        ]
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")

    # 📸 ۲. وقتی کاربر روی دکمه "دانلود از اینستا" کلیک می‌کند
    elif data.startswith("down_insta_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        insta_text = (
            ">  دستورات\n"
            "\n"
            ">  `*اینستا لینک`\n"
        )
        
        # بازگشت به منوی قبلی یعنی همان sett_down_
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"sett_down_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=insta_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")

    # 🔒 ۳. وقتی کاربر روی دکمه "دانلود از چنل پرایوت" کلیک می‌کند
    elif data.startswith("down_private_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        private_text = (
            ">  دستورات\n"
            "\n"
            ">  `*دانلود لینک`\n"
        )
        
        # بازگشت به منوی قبلی یعنی همان sett_down_
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"sett_down_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=private_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")
    
    # 👥 ۱. وقتی کاربر روی دکمه اصلی "دوست و دشمن" کلیک می‌کند
    elif data.startswith("sett_fr_en_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        menu_text = "🤝 **به بخش مدیریت دوست و دشمن خوش آمدید**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
        
        # ساخت دکمه‌های مطابق با تصویر دوم (image_a8e48a.png)
        keyboard = [
            [
                InlineKeyboardButton("دشمن ☠️", callback_data=f"fr_enemy_{owner_id}", style="danger"),
                InlineKeyboardButton("دوست 🤝", callback_data=f"fr_friend_{owner_id}", style="success")
            ],
            [InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]
        ]
        
        try:
            await query.edit_message_text(
                text=menu_text,
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")

    # 🤝 ۲. وقتی کاربر روی دکمه "دوست" کلیک می‌کند
    elif data.startswith("fr_friend_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        friend_text = (
            ">  دستورات بخش دوست\n"
            "\n"
            ">  `*دوست`\n"
            "\n"
            ">  `*حذف دوست`\n"
            "\n"
            ">  `*لیست دوستان`\n"
            "\n"
            ">  `*پاکسازی دوستان`\n"
        )
        
        # بازگشت به منوی قبلی یعنی همان sett_fr_en_
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"sett_fr_en_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=friend_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")

    # ☠️ ۳. وقتی کاربر روی دکمه "دشمن" کلیک می‌کند
    elif data.startswith("fr_enemy_"):
        try:
            owner_id = data.split("_")[-1]
        except:
            owner_id = "0"
            
        enemy_text = (
            ">  دستورات بخش دشمن\n"
            "\n"
            ">  `*دشمن`\n"
            "\n"
            ">  `*حذف دشمن`\n"
            "\n"
            ">  `*لیست دشمنان`\n"
            "\n"
            ">  `*پاکسازی دشمنان`\n"
        )
        
        # بازگشت به منوی قبلی یعنی همان sett_fr_en_
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"sett_fr_en_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=enemy_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): pass
            else: print(f"⚠️ Error: {e}")

    # 11            
    elif data.startswith("sett_info_"):
        info_text = (
            ">  دستورات\n"
            "\n"
            ">  `*آیدی`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=info_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing info menu: {e}")

    # 12            
    elif data.startswith("sett_tag_"):
        tag_text = (
            ">  دستورات\n"
            "\n"
            ">  `*تگ ادمین`\n"
            "\n"
            ">  `*تگ اعضا`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=tag_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing tag menu: {e}")

    # 13            
    elif data.startswith("sett_block_"):
        block_text = (
            ">  دستورات\n"
            "\n"
            ">  `*بلاک`\n"
            "\n"
            ">  `*آن بلاک`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=block_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing block menu: {e}")

    # 14            
    elif data.startswith("sett_del_"):
        del_text = (
            ">  دستورات\n"
            "\n"
            ">  `*حذف 50`\n"
            "\n"
            ">  توضیح\n"
            "\n"
            ">  این دستور تعداد مشخصی از پیام های اخیر را حذف می کند حد اکثار 500 پیام\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=del_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing del menu: {e}")


    elif data.startswith("sett_calc_"):
        CALC_STATE[owner_id] = "0"
        
        calc_text = (
            "🧮 › **ماشین حساب اختصاصی پنل:**\n\n"
            f"> `{CALC_STATE[owner_id]}`"
        )
        
        try:
            # ⚡ به جای edit_message_media از همان edit_message_text معمولی استفاده می‌کنیم
            await query.edit_message_text(
                text=calc_text,
                parse_mode="MarkdownV2",
                reply_markup=get_calculator_keyboard(owner_id)
            )
        except Exception as e:
            print(f"⚠️ Error opening calculator: {e}")


    elif data.startswith("clc_"):
        action = data.split("_")[1]
        
        if owner_id not in CALC_STATE:
            CALC_STATE[owner_id] = "0"
            
        current = CALC_STATE[owner_id]
        
        if action == "clear":
            CALC_STATE[owner_id] = "0"

        elif action == "equal":
            try:
                # 🔄 تبدیل همه‌جانبه انواع کاراکترهای ضرب و تقسیم به فرمت قابل فهم پایتون
                expression = current.replace("×", "*").replace("x", "*").replace("X", "*").replace("÷", "/")
                
                # 🔒 امنیت: بررسی کاراکترهای مجاز ریاضی
                if re.match(r'^[0-9.+\-*/() ]+$', expression):
                    # محاسبه نتیجه
                    result = str(eval(expression))
                    
                    # حذف اعشار بی‌مورد (مثلاً تبدیل 20.0 به 20)
                    if result.endswith(".0"):
                        result = result[:-2]
                        
                    CALC_STATE[owner_id] = result
                else:
                    CALC_STATE[owner_id] = "Error"
            except Exception:
                CALC_STATE[owner_id] = "Error"
        else:
            mapping = {"add": "+", "sub": "-", "mul": "×", "div": "÷", "dot": "."}
            char = mapping.get(action, action)
            
            if current in ["0", "Error"]:
                if char in ["+", "-", "×", "÷", "."]:
                    CALC_STATE[owner_id] = "0" + char
                else:
                    CALC_STATE[owner_id] = char
            else:
                if char in ["+", "-", "×", "÷", "."] and current[-1] in ["+", "-", "×", "÷", "."]:
                    CALC_STATE[owner_id] = current[:-1] + char
                else:
                    CALC_STATE[owner_id] += char
                    
        # 🔄 آپدیت متن صفحه نمایش بعد از هر کلیک
        calc_text = (
            "🧮 › **ماشین حساب اختصاصی پنل:**\n\n"
            f"> `{CALC_STATE[owner_id]}`"
        )
        try:
            await query.edit_message_text(
                text=calc_text,
                parse_mode="MarkdownV2",
                reply_markup=get_calculator_keyboard(owner_id)
            )
        except telegram.error.BadRequest:
            pass

    # 16            
    elif data.startswith("sett_ai_"):
        ai_text = (
            ">  دستورات\n"
            "\n"
            ">  `*ai متن سوال`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=ai_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing ai menu: {e}")

    # 17            
    elif data.startswith("sett_trans_"):
        transe_text = (
            ">  دستورات\n"
            "\n"
            ">  `*ترجمه آلمانی`\n"
            "\n"
            ">  روی پیام مورد نظر ریپلای کن و دستور را بزن\n"

        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=transe_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing transe menu: {e}")

    elif data.startswith("sett_tabchi_"):
        tabchi_text = (
            ">  دستورات\n"
            "\n"
            ">  `*تنظیم تبلیغ`\n"
            "\n"
            ">  `*روشن تبلیغ`\n"
            "\n"
            ">  `*خاموش تبلیغ`\n"
            "\n"
            ">  `*وضعیت تبلیغ`\n"

        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=tabchi_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing tabchi menu: {e}")
    
    elif data.startswith("sett_comment_"):
        comment_text = (
            ">  دستورات\n"
            "\n"
            ">  `*کامنت اول روشن`\n"
            "\n"
            ">  `*کامنت اول خاموش`\n"
            "\n"
            ">  `*متن کامنت مثلا سلام`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=comment_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing comment menu: {e}")
    

    elif data.startswith("sett_auto_res_"):
        auto_res_text = (
            ">  دستورات\n"
            "\n"
            ">  `*پاسخ روشن`\n"
            "\n"
            ">  `*پاسخ خاموش`\n"
            "\n"
            ">  `*پاسخ کلمه`\n"
            "\n"
            ">  `*ویرایش پاسخ کلمه`\n"
            "\n"
            ">  `*حذف پاسخ`\n"
            "\n"
            ">  `*لیست پاسخ`\n"
            "\n"
            ">  `*پاکسازی پاسخ`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=auto_res_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing auto_res menu: {e}")
    

    elif data.startswith("sett_fjoin_"):
        fjoin_text = (
            ">  دستورات\n"
            "\n"
            ">  `*تنظیم عضویت @channel`\n"
            "\n"
            ">  `*حذف عضویت @channel`\n"
            "\n"
            ">  `*لیست عضویت اجباری`\n"
            "\n"
            ">  `*پاکسازی عضویت اجباری`\n"
            "\n"
            ">  `*عضویت اجباری روشن`\n"
            "\n"
            ">  `*عضویت اجباری خاموش`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text= fjoin_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing auto_res menu: {e}")
    

    elif data.startswith("sett_currency_"):
        currency_text = (
            ">  دستورات\n"
            "\n"
            ">  `*قیمت دلار`\n"
            "\n"
            ">  `*قیمت یورو`\n"
            "\n"
            ">  `*قیمت پوند`\n"
            "\n"
            ">  `*قیمت درهم`\n"
            "\n"
            ">  `*قیمت لیر`\n"
            "\n"
            ">  `*قیمت یوان`\n"
            "\n"
            ">  `*قیمت ین`\n"
            "\n"
            ">  `*قیمت فرانک`\n"
            "\n"
            ">  `*قیمت دلار_کانادا`\n"
            "\n"
            ">  `*قیمت دلار_استرالیا`\n"
            "\n"
            ">  `*قیمت ریال_سعودی`\n"
            "\n"
            ">  `*قیمت دینار_کویت`\n"
            "\n"
            ">  `*قیمت روپیه`\n"
            "\n"
            ">  `*قیمت روبل`\n"
            "\n"
            ">  `*قیمت بیتکوین`\n"
            "\n"
            ">  `*قیمت اتریوم`\n"
            "\n"
            ">  `*قیمت تتر`\n"
            "\n"
            ">  `*قیمت بایننس`\n"
            "\n"
            ">  `*قیمت دوج`\n"
            "\n"
            ">  `*قیمت ریپل`\n"
        )
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=currency_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing currency menu: {e}")

    # 18            
    elif data.startswith("sett_anim_"):
        anim_text = (
            ">  دستورات\n"
            "\n"
            ">  `*قلب`\n"
            "\n"
            ">  `*متحرک`\n"
            "\n"
            ">  `*باران`\n"
            "\n"
            ">  `*لودینگ`\n"
            "\n"
            ">  `*موشک`\n"
            "\n"
            ">  `*تایپ`\n"
            "\n"
            ">  `*ماشین`\n"
            "\n"
            ">  `*هک`\n"
            "\n"
            ">  `*جادو`\n"
            "\n"
            ">  `*گربه`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=anim_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing anim menu: {e}")
        
    # 19            
    elif data.startswith("sett_ttv_"):
        ttv_text = (
            ">  دستورات\n"
            "\n"
            ">  `*ویس متن`\n"
            "\n"
            ">  مثال\n"
            "\n"
            ">  `*ویس متین`\n"

        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=ttv_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing ttv menu: {e}")

    # 20            
    elif data.startswith("sett_scr_"):
        ttv_text = (
            ">  دستور\n"
            "\n"
            ">  `*اسکرین`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=ttv_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing ttv menu: {e}")
        
    # 20            
    elif data.startswith("sett_cheat_"):
        cheat_text = (
            ">  دستور\n"
            "\n"
            ">  `*فوتبال`\n"
            "\n"
            ">  `*بسکتبال`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=cheat_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing cheat menu: {e}")
        
    # 21           
    elif data.startswith("sett_proxy_"):
        proxy_text = (
            ">  دستورات\n"
            "\n"
            ">  `*پروکسی`\n"
        )
        
        keyboard = [[InlineKeyboardButton("« بازگشت", callback_data=f"panel_sett_{owner_id}", style="primary")]]
        
        try:
            await query.edit_message_text(
                text=proxy_text,
                parse_mode="MarkdownV2", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e): 
                pass
            else:
                print(f"⚠️ Error editing proxy menu: {e}")

    # 22
    elif data.startswith("panel_close_"):
        try:
            await query.edit_message_text("❌ پنل مدیریت سلف‌بات بسته شد.")
        except Exception:
            pass

async def show_panel(update, context):
    pass