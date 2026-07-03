import asyncio
from telethon import events
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

# ایمپورت توابع آنلاین از فایل utils شما
from utils import get_user_locks_from_db, save_user_lock_to_db

# ================== تشخیص لینک ==================
def has_link(message):
    """بررسی وجود لینک در پیام (معمولی و مخفی)"""
    if not message.text:
        return False

    if message.entities:
        for entity in message.entities:
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                return True

    text_lower = message.text.lower()
    for keyword in ['http://', 'https://', 'www.', 't.me/', 'telegram.me/']:
        if keyword in text_lower:
            return True

    return False


def register_locks(bot):
    """ثبت همه هندلرهای قفل به صورت کاملاً مجزا برای هزاران کاربر"""

    # کش داخلی کلاینت برای جلوگیری از اسپم ریکوئست به دیتابیس
    bot.my_locks = None
    bot.my_own_id = None

# ۱. اصلاح لودر اولیه کش کلاینت
    async def ensure_locks_loaded(client):
        if client.my_own_id is None:
            try:
                me = await client.get_me()
                client.my_own_id = me.id
            except Exception as e:
                print(f"⚠️ خطا در دریافت اطلاعات کلاینت در بخش قفل: {e}")
                return

        res = await get_user_locks_from_db(client.my_own_id)
        if res is not None:
            client.my_locks = res
        else:
            # جلوگیری از None شدن متغیر
            client.my_locks = {
                "username": False, "link": False, "reply": False, "photo": False,
                "gif": False, "sticker": False, "pv": False, "forward": False
            }
        print(f"[*] تنظیمات قفل کلاینت {client.my_own_id} با موفقیت بارگذاری شد.")

    # ================== هندلر اصلی برای بررسی پیام‌های ورودی ==================
    @bot.on(events.NewMessage(incoming=True))
    async def lock_handler(event):
        # 🔐 سپر امنیتی ۱: بررسی پیوی و عدم خروجی بودن قبل از هر چیزی
        if not event.is_private or event.out:
            return

        # بارگذاری امن تنظیمات در صورت خالی بودن کش
        if bot.my_locks is None:
            await ensure_locks_loaded(bot)

        # محافظت نهایی در برابر NoneType
        if bot.my_locks is None:
            bot.my_locks = {
                "username": False, "link": False, "reply": False, "photo": False,
                "gif": False, "sticker": False, "pv": False, "forward": False
            }

        locks = bot.my_locks

        # حالا با خیال راحت از get استفاده کن، چون مطمئنیم دیکشنری است
        if locks.get("pv", False):
            try: await event.delete()
            except Exception: pass
            return

        if locks.get("username", False):
            sender = await event.get_sender()
            if sender and getattr(sender, 'username', None):  
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("link", False):
            if has_link(event.message):
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("reply", False):
            if event.message.is_reply:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("photo", False):
            if event.message.photo:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("gif", False):
            if event.message.gif:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("sticker", False):
            if event.message.sticker:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("forward", False):
            if event.message.forward:
                try: await event.delete()
                except Exception: pass
                return

    # ================== هندلر اصلی برای بررسی پیام‌های ورودی ==================
    @bot.on(events.NewMessage(incoming=True))
    async def lock_handler(event):
        if not event.is_private:
            return

        if event.out:
            return

        # بارگذاری امن تنظیمات در صورت خالی بودن کش
        if bot.my_locks is None:
            await ensure_locks_loaded(bot)

        locks = bot.my_locks

        if locks.get("pv"):
            try: await event.delete()
            except Exception: pass
            return

        if locks.get("username"):
            sender = await event.get_sender()
            if sender and getattr(sender, 'username', None):  
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("link"):
            if has_link(event.message):
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("reply"):
            if event.message.is_reply:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("photo"):
            if event.message.photo:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("gif"):
            if event.message.gif:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("sticker"):
            if event.message.sticker:
                try: await event.delete()
                except Exception: pass
                return

        if locks.get("forward"):
            if event.message.forward:
                try: await event.delete()
                except Exception: pass
                return

    # ================== هندلر دستورات *قفل ==================
    @bot.on(events.NewMessage(pattern=r'\*قفل (.+)', outgoing=True))
    async def lock_command(event):
        if bot.my_locks is None:
            await ensure_locks_loaded(bot)

        # جلوگیری از تداخل مالتی‌کلاینت
        if event.sender_id != bot.my_own_id:
            return

        args = event.pattern_match.group(1).strip()
        parts = args.split()

        lock_names = {
            "یوزرنیم": "username",
            "لینک": "link",
            "ریپلای": "reply",
            "عکس": "photo",
            "گیف": "gif",
            "استیکر": "sticker",
            "پیوی": "pv",
            "فوروارد": "forward",
        }

        lock_name = parts[0]
        if lock_name not in lock_names:
            await event.edit(f"⚠️ نوع قفل نامعتبر است.\nانواع معتبر: {', '.join(lock_names.keys())}")
            return

        key = lock_names[lock_name]

        if len(parts) == 1:
            # روشن کردن قفل
            if await save_user_lock_to_db(bot.my_own_id, key, True):
                bot.my_locks[key] = True # بروزرسانی آنی کش کلاینت
                await event.edit(f"✅ <b>قفل {lock_name}</b> برای شما روشن شد")
            else:
                await event.edit("❌ خطا در ذخیره‌سازی اطلاعات در دیتابیس.")

        elif len(parts) == 2 and parts[1] == "خاموش":
            # خاموش کردن قفل
            if await save_user_lock_to_db(bot.my_own_id, key, False):
                bot.my_locks[key] = False # بروزرسانی آنی کش کلاینت
                await event.edit(f"❌ <b>قفل {lock_name}</b> برای شما خاموش شد")
            else:
                await event.edit("❌ خطا در ذخیره‌سازی اطلاعات در دیتابیس.")
        else:
            await event.edit("❓ فرمت نادرست.\nمثال:\n`*قفل یوزرنیم`\n`*قفل لینک خاموش`")

    # ================== هندلر وضعیت قفل‌ها ==================
    @bot.on(events.NewMessage(pattern=r'\*وضعیت قفل', outgoing=True))
    async def lock_status(event):
        if bot.my_locks is None:
            await ensure_locks_loaded(bot)

        if event.sender_id != bot.my_own_id:
            return

        # همگام‌سازی مجدد کش با دیتابیس برای اطمینان بیشتر در وضعیت قفل
        bot.my_locks = await get_user_locks_from_db(bot.my_own_id)
        locks = bot.my_locks

        lock_names_fa = {
            "username": "یوزرنیم",
            "link": "لینک",
            "reply": "ریپلای",
            "photo": "عکس",
            "gif": "گیف",
            "sticker": "استیکر",
            "pv": "پیوی",
            "forward": "فوروارد",
        }

        status_text = "🔐 <b>وضعیت قفل‌های پیوی اختصاصی شما:</b>\n\n"
        for key, fa_name in lock_names_fa.items():
            is_locked = locks.get(key, False)
            emoji = "🟢" if is_locked else "🔴"
            state = "روشن" if is_locked else "خاموش"
            status_text += f"{emoji} قفل {fa_name}: <b>{state}</b>\n"

        await event.edit(status_text, parse_mode="html")