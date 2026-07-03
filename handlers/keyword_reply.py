import re
import datetime
from telethon import events

# ---- وارد کردن کلاینت سوپابیس از فایل کانفیگ ----
from config import supabase

# ---- استفاده از همون thread pool مشترک تعریف‌شده در db.py ----
# (به‌جای ساختن یک executor جدید و پراکنده‌کردن منابع)
from utils import db_execute
from cachetools import TTLCache

# سقف مجاز کلمات کلیدی برای هر کاربر
KEYWORD_LIMIT = 10

# ============================================================================
# 🧠 کش برای مسیر داغ (hot path):
# قبلاً «keyword_handler» روی هر پیام ورودی از هر کاربر یک کوئری جدا به
# Supabase می‌زد (هم برای وضعیت روشن/خاموش، هم برای کل لیست کلمات کلیدی).
# با ۸۰۰۰ کاربر همزمان و ترافیک پیام بالا، این دقیقاً همون نقطه‌ای بود که
# دیتابیس رو زیر فشار می‌بره. حالا این دو مورد کش می‌شن و فقط وقتی چیزی
# واقعاً تغییر کنه (یا TTL تموم بشه) دوباره از دیتابیس خونده می‌شن.
# ============================================================================
CACHE_BOT_STATUS = TTLCache(maxsize=20000, ttl=1800)   # وضعیت روشن/خاموش هر کاربر
CACHE_KEYWORDS = TTLCache(maxsize=20000, ttl=300)       # لیست کلمات کلیدی هر کاربر


async def get_bot_status(user_id: int) -> bool:
    """دریافت وضعیت پاسخ خودکار اختصاصی یک کاربر (با کش)"""
    if user_id in CACHE_BOT_STATUS:
        return CACHE_BOT_STATUS[user_id]
    try:
        query = supabase.table("user_bot_settings").select("keyword_enabled").eq("user_id", user_id)
        res = await db_execute(query)
        status = res.data[0]["keyword_enabled"] if res.data else True
    except Exception as e:
        print(f"Error fetching status for {user_id}: {e}")
        status = True  # به صورت پیش‌فرض روشن است
    CACHE_BOT_STATUS[user_id] = status
    return status


async def set_bot_status(user_id: int, status: bool):
    """تغییر وضعیت پاسخ خودکار اختصاصی یک کاربر"""
    query = supabase.table("user_bot_settings").upsert({"user_id": user_id, "keyword_enabled": status})
    await db_execute(query)
    CACHE_BOT_STATUS[user_id] = status


async def get_keywords_cached(user_id: int):
    """دریافت کل لیست کلمات کلیدی یک کاربر (با کش، برای مسیر داغ پیام‌ها)"""
    if user_id in CACHE_KEYWORDS:
        return CACHE_KEYWORDS[user_id]
    query = supabase.table("keyword_replies").select("*").eq("user_id", user_id)
    res = await db_execute(query)
    data = res.data or []
    CACHE_KEYWORDS[user_id] = data
    return data


def invalidate_keywords_cache(user_id: int):
    """باطل کردن کش کلمات کلیدی بعد از هر تغییر (افزودن/ویرایش/حذف/پاکسازی)"""
    CACHE_KEYWORDS.pop(user_id, None)


def extract_parentheses(text):
    """استخراج محتوای داخل پرانتزها"""
    return re.findall(r'\(([^)]+)\)', text)


def register_keyword_reply(bot):
    """ثبت هندلرهای پاسخ خودکار چندکاربره با محدودیت ثبت کلمه"""

    print(f"💬 سیستم پاسخ‌های خودکار چندکاربره (مقیاس بالا) بارگذاری شد.")

    # ********** هندلر روشن کردن **********
    @bot.on(events.NewMessage(pattern=r'^\*پاسخ روشن$'))
    async def enable_keyword(event):
        # فقط صاحب سلف‌بات بتواند دستور را اجرا کند
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        await set_bot_status(user_id, True)
        await event.reply("✅ **پاسخ خودکار برای شما روشن شد!**")

    # ********** هندلر خاموش کردن **********
    @bot.on(events.NewMessage(pattern=r'^\*پاسخ خاموش$'))
    async def disable_keyword(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        await set_bot_status(user_id, False)
        await event.reply("❌ **پاسخ خودکار برای شما خاموش شد!**")

    # ********** هندلر اضافه کردن پاسخ (با اعمال لیمیت) **********
    @bot.on(events.NewMessage(pattern=r'^\*پاسخ\s+\(.+\)\s+\(.+\)$'))
    async def add_keyword_reply(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        parts = extract_parentheses(event.message.text)

        if len(parts) < 2:
            await event.reply("❌ **فرمت اشتباه!**\n`*پاسخ (کلمه) (پاسخ)`")
            return

        keyword = parts[0].strip().lower()
        response = parts[1].strip()

        if not keyword or not response:
            await event.reply("❌ کلمه یا پاسخ خالی است!")
            return

        # 🛑 چک کردن محدودیت کلمه برای کاربر
        count_query = supabase.table("keyword_replies").select("id", count="exact").eq("user_id", user_id)
        count_res = await db_execute(count_query)
        current_count = count_res.count if hasattr(count_res, 'count') and count_res.count is not None else len(count_res.data)

        if current_count >= KEYWORD_LIMIT:
            await event.reply(f"🚫 **محدودیت ظرفیت!** شما حداکثر `{KEYWORD_LIMIT}` کلمه می‌توانید ثبت کنید.\n"
                              f"تعداد فعلی شما: {current_count}")
            return

        reply_type = "contains"
        if len(parts) >= 3 and parts[2].lower() in ['دقیق', 'exact']:
            reply_type = "exact"

        # بررسی موجود بودن این کلمه *فقط برای این کاربر*
        check_query = supabase.table("keyword_replies").select("id").eq("user_id", user_id).eq("keyword", keyword)
        check = await db_execute(check_query)
        if check.data:
            await event.reply(f"⚠️ کلمه `{keyword}` قبلاً توسط شما ثبت شده!\n"
                              f"برای ویرایش: `*ویرایش پاسخ ({keyword}) ({response})`")
            return

        # ذخیره با آیدی خود کاربر در Supabase
        insert_query = supabase.table("keyword_replies").insert({
            "user_id": user_id,
            "keyword": keyword,
            "response": response,
            "type": reply_type
        })
        await db_execute(insert_query)
        invalidate_keywords_cache(user_id)

        type_text = "🎯 دقیق" if reply_type == "exact" else "🔍 شامل"
        await event.reply(
            f"✅ **پاسخ جدید اضافه شد!**\n"
            f"🔑 کلمه: `{keyword}`\n"
            f"💬 پاسخ: `{response}`\n"
            f"📌 نوع: {type_text}\n"
            f"📊 ظرفیت: {current_count + 1}/{KEYWORD_LIMIT}"
        )

    # ********** هندلر ویرایش پاسخ **********
    @bot.on(events.NewMessage(pattern=r'^\*ویرایش پاسخ\s+\(.+\)\s+\(.+\)$'))
    async def edit_keyword_reply(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        parts = extract_parentheses(event.message.text)

        if len(parts) < 2:
            await event.reply("❌ فرمت اشتباه!")
            return

        keyword = parts[0].strip().lower()
        response = parts[1].strip()

        # بررسی و دریافت اطلاعات کلمه متعلق به همین کاربر
        check_query = supabase.table("keyword_replies").select("response").eq("user_id", user_id).eq("keyword", keyword)
        check = await db_execute(check_query)
        if not check.data:
            await event.reply(f"❌ کلمه `{keyword}` در لیست شما یافت نشد!")
            return

        old_response = check.data[0]['response']

        # آپدیت مشروط به آیدی کاربر
        update_query = supabase.table("keyword_replies").update({"response": response}).eq("user_id", user_id).eq("keyword", keyword)
        await db_execute(update_query)
        invalidate_keywords_cache(user_id)

        await event.reply(
            f"✏️ **پاسخ ویرایش شد!**\n"
            f"🔑 کلمه: `{keyword}`\n"
            f"📝 قبلی: `{old_response}`\n"
            f"✨ جدید: `{response}`"
        )

    # ********** هندلر حذف پاسخ **********
    @bot.on(events.NewMessage(pattern=r'^\*حذف پاسخ\s+\(.+\)$'))
    async def remove_keyword_reply(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        parts = extract_parentheses(event.message.text)

        if not parts:
            await event.reply("❌ فرمت اشتباه!")
            return

        keyword = parts[0].strip().lower()

        # حذف ایمن فقط برای کلمه خود کاربر
        delete_query = supabase.table("keyword_replies").delete().eq("user_id", user_id).eq("keyword", keyword)
        delete_res = await db_execute(delete_query)

        if not delete_res.data:
            await event.reply(f"❌ کلمه `{keyword}` در لیست شما یافت نشد!")
            return

        invalidate_keywords_cache(user_id)
        await event.reply(
            f"🗑️ **پاسخ حذف شد!**\n"
            f"🔑 کلمه: `{keyword}`\n"
            f"💬 پاسخ حذف شده: `{delete_res.data[0]['response']}`"
        )

    # ********** هندلر لیست پاسخ‌ها **********
    @bot.on(events.NewMessage(pattern=r'^\*لیست پاسخ$'))
    async def list_keywords(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        # فیلتر بر اساس کاربر
        query = supabase.table("keyword_replies").select("*").eq("user_id", user_id)
        res = await db_execute(query)
        if not res.data:
            await event.reply("📭 هیچ پاسخی ثبت نکرده‌اید!")
            return

        reply_list = []
        for i, row in enumerate(res.data, 1):
            type_emoji = "🎯" if row['type'] == 'exact' else "🔍"
            reply_list.append(
                f"{i}. {type_emoji} `{row['keyword']}`\n"
                f"   └ {row['response'][:100]}"
            )

        is_enabled = await get_bot_status(user_id)
        text = '\n\n'.join(reply_list)
        await event.reply(
            f"📋 **لیست پاسخ‌های خودکار شما** ({len(res.data)}/{KEYWORD_LIMIT} مورد):\n\n"
            f"{text}\n\n"
            f"💡 وضعیت سلف‌بات شما: {'✅ روشن' if is_enabled else '❌ خاموش'}\n"
            f"🎯 = دقیق | 🔍 = شبیه"
        )

    # ********** هندلر پاکسازی کامل کلمات یک کاربر **********
    @bot.on(events.NewMessage(pattern=r'^\*پاکسازی پاسخ$'))
    async def clear_keywords(event):
        if event.sender_id != (await bot.get_me()).id:
            return

        user_id = event.sender_id
        # فقط کلمات این کاربر حذف می‌شوند
        query = supabase.table("keyword_replies").delete().eq("user_id", user_id)
        res = await db_execute(query)
        count = len(res.data) if res.data else 0

        invalidate_keywords_cache(user_id)
        await event.reply(f"🗑️ **هر {count} پاسخ شما از دیتابیس حذف شدند!**")

    # ********** هندلر اصلی پاسخ‌دهی به پیام‌های دریافتی **********
    @bot.on(events.NewMessage(incoming=True))
    async def keyword_handler(event):
        if event.out or not event.message.text:
            return

        # 🛑 بسیار مهم: تشخیص اینکه پیام داخل اکانتِ کدام کاربر دریافت شده است
        current_bot_user = await event.client.get_me()
        bot_owner_id = current_bot_user.id

        # بررسی وضعیت روشن بودن ماژول برای صاحب این خط (از کش، نه هر بار دیتابیس)
        if not await get_bot_status(bot_owner_id):
            return

        if event.message.text.startswith('*'):
            return

        message_text = event.message.text.lower()

        # دریافت کلمات کلیدی اختصاصی صاحب این سلف‌بات (از کش، نه هر بار دیتابیس)
        keywords = await get_keywords_cached(bot_owner_id)
        if not keywords:
            return

        for row in keywords:
            keyword = row['keyword']
            should_reply = False

            if row['type'] == 'exact':
                if message_text == keyword:
                    should_reply = True
            else:
                if keyword in message_text:
                    should_reply = True

            if should_reply:
                try:
                    sender = await event.get_sender()
                    response = row['response']

                    name = sender.first_name or "کاربر"
                    username = f"@{sender.username}" if sender.username else "ندارد"
                    current_time = datetime.datetime.now().strftime("%H:%M")
                    truncated_text = event.message.text[:50]

                    response = response.replace('{name}', name)
                    response = response.replace('{username}', username)
                    response = response.replace('{time}', current_time)
                    response = response.replace('{text}', truncated_text)

                    await event.reply(response)
                    print(f"💬 [User {bot_owner_id}] پاسخ به {name}: {keyword}")
                except Exception as e:
                    print(f"خطا در پاسخ خودکار: {e}")
                break