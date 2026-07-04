import asyncio
from concurrent.futures import ThreadPoolExecutor
from cachetools import TTLCache
from config import supabase

# ============================================================================
# ⚙️ اجرای همه‌ی کوئری‌های سینکرون Supabase در یک ThreadPool اختصاصی
# دلیل مشکل اصلی پروژه‌ی قبلی همین‌جا بود: تابع db_execute تعریف شده بود
# ولی هیچ‌جا استفاده نمی‌شد و همه‌ی کوئری‌ها مستقیم و بلاک‌کننده اجرا می‌شدند،
# که با هزاران کاربر همزمان کل event loop رو قفل می‌کرد.
#
# پیش‌فرض executor پایتون خیلی کوچیکه (~ min(32, cpu_count+4)).
# با ۸۰۰۰ کاربر همزمان حتماً باید اندازه‌ش رو افزایش بدی.
# ============================================================================
DB_EXECUTOR = ThreadPoolExecutor(max_workers=100, thread_name_prefix="supabase_worker")


async def db_execute(query):
    """اجرای غیرهمزمان Queryهای سینکرون Supabase در thread pool اختصاصی"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(DB_EXECUTOR, query.execute)


async def db_rpc(func_name: str, params: dict):
    """اجرای غیرهمزمان یک تابع RPC (Postgres function) روی Supabase"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        DB_EXECUTOR, lambda: supabase.rpc(func_name, params).execute()
    )


# ============================================================================
# 🧠 کش‌های محدود با TTL (به‌جای دیکشنری‌های نامحدود قبلی)
# maxsize جلوی رشد بی‌رویه‌ی حافظه رو می‌گیره و ttl باعث میشه داده‌ی قدیمی
# خودش بعد از مدتی از حافظه پاک بشه (حتی اگه یک instance دیگه از بات هم
# دیتا رو تغییر داده باشه، خیلی طولانی stale نمی‌مونه).
# ============================================================================
CACHE_USER_LOCKS = TTLCache(maxsize=20000, ttl=1800)
CACHE_AUTO_REPLY = TTLCache(maxsize=20000, ttl=1800)
CACHE_FILTERS = TTLCache(maxsize=20000, ttl=1800)
CACHE_MUTED_USERS = TTLCache(maxsize=20000, ttl=1800)
CACHE_CHAT_GUARD = TTLCache(maxsize=20000, ttl=1800)


# --- 🔥 توابع مدیریت موجودی طلا (اتمیک و ایمن دربرابر Race Condition واقعی) ---
#
# مهم: این بخش نیاز به یک تابع Postgres در Supabase داره تا افزایش/کاهش
# موجودی به‌صورت اتمیک در خود دیتابیس انجام بشه (نه با read-then-write در پایتون).
# این SQL رو یک‌بار در Supabase SQL Editor اجرا کن:
#
# create or replace function increment_diamonds(p_user_id bigint, p_amount bigint)
# returns bigint
# language plpgsql
# as $$
# declare
#   new_balance bigint;
# begin
#   insert into users_diamonds (user_id, diamonds)
#   values (p_user_id, greatest(p_amount, 0))
#   on conflict (user_id) do update
#     set diamonds = users_diamonds.diamonds + excluded_amount(p_amount)
#   returning diamonds into new_balance;
#
#   if new_balance < 0 then
#     raise exception 'insufficient_balance';
#   end if;
#
#   return new_balance;
# end;
# $$;
#
# توجه: تابع بالا رو با توجه به نسخه‌ی دقیق Postgres شاید لازم باشه ساده‌تر
# بنویسی (excluded_amount نمونه‌ی pseudo هست) — اگه بخوای، متن SQL نهایی و
# تست‌شده رو هم برات آماده می‌کنم.

async def get_balance(user_id):
    """دریافت تعداد طلاهای کاربر از دیتابیس سوپابیس"""
    try:
        query = supabase.table("users_diamonds").select("diamonds").eq("user_id", int(user_id))
        response = await db_execute(query)
        if response.data:
            return response.data[0]["diamonds"]

        insert_query = supabase.table("users_diamonds").insert({"user_id": int(user_id), "diamonds": 0})
        await db_execute(insert_query)
        return 0
    except Exception as e:
        print(f"⚠️ خطا در دریافت طلا از سوپابیس: {e}")
        return 0


async def update_balance(user_id, amount):
    """کم یا زیاد کردن طلاها به صورت اتمیک واقعی (روی سرور دیتابیس، نه در پایتون)"""
    try:
        response = await db_rpc("increment_diamonds", {"p_user_id": int(user_id), "p_amount": int(amount)})
        return response.data is not None
    except Exception as e:
        # اگه تابع RPC موجودی منفی رو رد کنه (raise exception 'insufficient_balance')
        if "insufficient_balance" in str(e):
            return False
        print(f"⚠️ خطا در آپدیت طلا در سوپابیس: {e}")
        return False


# --- 🎮 توابع مدیریت بازی‌ها در Supabase ---

async def save_game(game_id, game_data):
    """ذخیره یا آپدیت اطلاعات یک بازی مشخص با متد upsert"""
    try:
        query = supabase.table("active_games").upsert({
            "game_id": str(game_id),
            "game_data": game_data
        })
        await db_execute(query)
    except Exception as e:
        print(f"⚠️ خطا در ذخیره بازی در سوپابیس: {e}")


async def get_game(game_id):
    """گرفتن اطلاعات یک بازی مشخص از دیتابیس"""
    try:
        query = supabase.table("active_games").select("game_data").eq("game_id", str(game_id))
        response = await db_execute(query)
        if response.data:
            return response.data[0]["game_data"]
        return None
    except Exception as e:
        print(f"⚠️ خطا در دریافت اطلاعات بازی از سوپابیس: {e}")
        return None


async def delete_game(game_id):
    """حذف بازی بعد از اتمام یا لغو شدن از دیتابیس"""
    try:
        query = supabase.table("active_games").delete().eq("game_id", str(game_id))
        await db_execute(query)
    except Exception as e:
        print(f"⚠️ خطا در حذف بازی از سوپابیس: {e}")


# --- 🤫 توابع مدیریت لیست سکوت (دارای سیستم کشینگ TTL) ---

async def get_muted_users_from_db(owner_id):
    """دریافت لیست آیدی‌های سکوت شده با اولویت کش حافظه"""
    owner_id = int(owner_id)
    if owner_id in CACHE_MUTED_USERS:
        return CACHE_MUTED_USERS[owner_id]

    try:
        query = supabase.table("muted_users").select("muted_id").eq("owner_id", owner_id)
        response = await db_execute(query)
        muted_list = [row["muted_id"] for row in response.data] if response.data else []
        CACHE_MUTED_USERS[owner_id] = muted_list
        return muted_list
    except Exception as e:
        print(f"⚠️ خطا در دریافت لیست سکوت از سوپابیس: {e}")
        return CACHE_MUTED_USERS.get(owner_id, [])


async def add_muted_user_to_db(owner_id, muted_id):
    """افزودن کاربر به لیست سکوت دیتابیس و به‌روزرسانی آنی کش"""
    owner_id = int(owner_id)
    muted_id = int(muted_id)
    try:
        query = supabase.table("muted_users").upsert({"owner_id": owner_id, "muted_id": muted_id})
        await db_execute(query)
        if owner_id in CACHE_MUTED_USERS:
            if muted_id not in CACHE_MUTED_USERS[owner_id]:
                CACHE_MUTED_USERS[owner_id].append(muted_id)
        else:
            CACHE_MUTED_USERS[owner_id] = [muted_id]
        return True
    except Exception as e:
        print(f"⚠️ خطا در افزودن به لیست سکوت سوپابیس: {e}")
        return False


async def remove_muted_user_from_db(owner_id, muted_id):
    """حذف کاربر از لیست سکوت دیتابیس و حذف از کش حافظه"""
    owner_id = int(owner_id)
    muted_id = int(muted_id)
    try:
        query = supabase.table("muted_users").delete().eq("owner_id", owner_id).eq("muted_id", muted_id)
        await db_execute(query)
        if owner_id in CACHE_MUTED_USERS and muted_id in CACHE_MUTED_USERS[owner_id]:
            CACHE_MUTED_USERS[owner_id].remove(muted_id)
        return True
    except Exception as e:
        print(f"⚠️ خطا در حذف از لیست سکوت سوپابیس: {e}")
        return False


# --- 🔒 توابع مدیریت قفل‌های کاربری ---

async def get_user_locks_from_db(user_id):
    """دریافت وضعیت قفل‌ها بدون درگیر کردن دیتابیس برای هر پیام"""
    user_id = int(user_id)
    if user_id in CACHE_USER_LOCKS:
        return CACHE_USER_LOCKS[user_id]

    default_locks = {
        "user_id": user_id, "username": False, "link": False, "reply": False,
        "photo": False, "gif": False, "sticker": False, "pv": False, "forward": False
    }
    try:
        query = supabase.table("user_locks").select("*").eq("user_id", user_id)
        response = await db_execute(query)
        if response.data and len(response.data) > 0:
            CACHE_USER_LOCKS[user_id] = response.data[0]
            return response.data[0]

        insert_query = supabase.table("user_locks").insert({"user_id": user_id})
        await db_execute(insert_query)
        CACHE_USER_LOCKS[user_id] = default_locks
        return default_locks
    except Exception as e:
        print(f"⚠️ خطا در دریافت قفل‌ها از سوپابیس برای {user_id}: {e}")
        return default_locks


async def save_user_lock_to_db(user_id, lock_key, value):
    """تغییر وضعیت قفل در دیتابیس و اِعمال آنی روی لایه کش سیستم"""
    user_id = int(user_id)
    try:
        query = supabase.table("user_locks").upsert({"user_id": user_id, lock_key: bool(value)})
        await db_execute(query)
        if user_id in CACHE_USER_LOCKS:
            CACHE_USER_LOCKS[user_id][lock_key] = bool(value)
        else:
            await get_user_locks_from_db(user_id)  # لود اولیه کش
        return True
    except Exception as e:
        print(f"⚠️ خطا در ذخیره قفل در سوپابیس: {e}")
        return False


# --- 🤖 تنظیمات منشی خودکار (Auto Reply System) ---

async def get_auto_reply_from_db(user_id):
    user_id = int(user_id)
    if user_id in CACHE_AUTO_REPLY:
        return CACHE_AUTO_REPLY[user_id]

    default_config = {
        "user_id": user_id, "enabled": False, "message": "🚫 الان آنلاین نیستم، بعداً پیام میدم!",
        "interval": 30, "mode": "once"
    }
    try:
        query = supabase.table("user_auto_reply").select("*").eq("user_id", user_id)
        response = await db_execute(query)
        if response.data and len(response.data) > 0:
            CACHE_AUTO_REPLY[user_id] = response.data[0]
            return response.data[0]

        insert_query = supabase.table("user_auto_reply").insert({"user_id": user_id})
        await db_execute(insert_query)
        CACHE_AUTO_REPLY[user_id] = default_config
        return default_config
    except Exception as e:
        print(f"⚠️ خطا در دریافت تنظیمات منشی از سوپابیس برای {user_id}: {e}")
        return default_config


async def save_auto_reply_to_db(user_id, update_data):
    user_id = int(user_id)
    try:
        update_data["user_id"] = user_id
        query = supabase.table("user_auto_reply").upsert(update_data)
        await db_execute(query)

        if user_id in CACHE_AUTO_REPLY:
            CACHE_AUTO_REPLY[user_id].update(update_data)
        else:
            CACHE_AUTO_REPLY[user_id] = update_data
        return True
    except Exception as e:
        print(f"⚠️ خطا در ذخیره تنظیمات منشی در سوپابیس: {e}")
        return False


# --- 📑 توابع فیلترینگ کلمات و متون چت ---

async def get_user_filters_from_db(user_id):
    user_id = int(user_id)
    if user_id in CACHE_FILTERS:
        return CACHE_FILTERS[user_id]

    default_data = {"user_id": user_id, "enabled": False, "words": []}
    try:
        query = supabase.table("user_filters").select("*").eq("user_id", user_id)
        response = await db_execute(query)
        if response.data and len(response.data) > 0:
            data = response.data[0]
            if data.get("words") is None:
                data["words"] = []
            CACHE_FILTERS[user_id] = data
            return data

        insert_query = supabase.table("user_filters").insert({"user_id": user_id})
        await db_execute(insert_query)
        CACHE_FILTERS[user_id] = default_data
        return default_data
    except Exception as e:
        print(f"⚠️ خطا در دریافت فیلترها از سوپابیس برای {user_id}: {e}")
        return default_data


async def save_user_filters_to_db(user_id, update_data):
    user_id = int(user_id)
    try:
        update_data["user_id"] = user_id
        query = supabase.table("user_filters").upsert(update_data)
        await db_execute(query)

        if user_id in CACHE_FILTERS:
            CACHE_FILTERS[user_id].update(update_data)
        else:
            CACHE_FILTERS[user_id] = update_data
        return True
    except Exception as e:
        print(f"⚠️ خطا در ذخیره فیلترها در سوپابیس: {e}")
        return False


# --- 🛡️ سیستم نگهبان چت (Chat Guard) ---

async def get_chat_guard_from_db(owner_id: int):
    owner_id = int(owner_id)
    if owner_id in CACHE_CHAT_GUARD:
        return CACHE_CHAT_GUARD[owner_id]

    default_data = {"user_id": owner_id, "save_deleted": False, "save_edited": False, "save_ttl": False}
    try:
        query = supabase.table("chat_guard").select("*").eq("user_id", owner_id)
        res = await db_execute(query)
        if res and res.data:
            CACHE_CHAT_GUARD[owner_id] = res.data[0]
            return res.data[0]
    except Exception as e:
        print(f"⚠️ خطا در خواندن نگهبان چت: {e}")

    # همان shape کش‌شده رو برمی‌گردونیم تا سازگار بمونه (باگ نسخه‌ی قبلی)
    CACHE_CHAT_GUARD[owner_id] = default_data
    return default_data


async def save_chat_guard_to_db(owner_id: int, update_data: dict):
    owner_id = int(owner_id)
    try:
        select_query = supabase.table("chat_guard").select("user_id").eq("user_id", owner_id)
        res = await db_execute(select_query)
        if not res.data:
            insert_query = supabase.table("chat_guard").insert({"user_id": owner_id})
            await db_execute(insert_query)

        update_query = supabase.table("chat_guard").update(update_data).eq("user_id", owner_id)
        await db_execute(update_query)

        if owner_id in CACHE_CHAT_GUARD:
            CACHE_CHAT_GUARD[owner_id].update(update_data)
        else:
            CACHE_CHAT_GUARD[owner_id] = update_data
        return True
    except Exception as e:
        print(f"⚠️ خطا در آپدیت نگهبان چت: {e}")
        return False


# --- 👀 سیستم سین خودکار چت‌ها (Auto Seen Engine) ---

async def get_auto_seen_from_db(owner_id: int) -> dict:
    try:
        query = supabase.table("auto_seen_settings").select("*").eq("user_id", int(owner_id))
        response = await db_execute(query)
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        # پیش‌فرض: خاموش
        return {"user_id": owner_id, "auto_seen": False}
        
    except Exception as e:
        print(f"Error fetching auto seen: {e}")
        return {"user_id": owner_id, "auto_seen": False}

async def save_auto_seen_to_db(owner_id: int, status: bool):
    try:
        data = {"user_id": int(owner_id), "auto_seen": status, "updated_at": "now()"}
        query = supabase.table("auto_seen_settings").upsert(data)
        await db_execute(query)
        return True
    except Exception as e:
        print(f"Error saving auto seen: {e}")
        return False