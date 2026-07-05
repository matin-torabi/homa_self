import os
import asyncio
from telethon import TelegramClient, events
from config import API_HASH, API_ID
from config import supabase
from utils import db_execute  # ایمپورت تابع مدیریت ترد

# دیکشنری‌ها برای مدیریت کلاینت‌ها در وضعیت زنده
clients = {}
login_data = {}

# 🚦 وضعیت لحظه‌ای مجاز بودن هر کاربر (در حافظه، بدون هزینه‌ی دیتابیس در هر پیام)
# user_id -> bool
user_status = {}

# فاصله‌ی زمانی چک کردن موجودی از دیتابیس (ثانیه)
# روی سرور ۲ گیگ CPU / ۴ گیگ RAM با ۱۰۰۰ کاربر، مقدار پایین‌تر فشار غیرضروری
# به دیتابیس و event loop وارد می‌کنه؛ ۲۰ ثانیه تعادل خوبیه بین سرعت واکنش و مصرف منابع.
STATUS_POLL_INTERVAL = 20

# سقف تعداد کانکشن هم‌زمان تلگرام (هم برای لود اولیه، هم برای شارژهای گروهی در حین اجرا)
CONNECTION_SEMAPHORE_LIMIT = 50
_connection_semaphore = asyncio.Semaphore(CONNECTION_SEMAPHORE_LIMIT)


def create_client(user_id: int):
    return TelegramClient(
        f"new_sessions/{user_id}",
        API_ID,
        API_HASH,
        timeout=30,
        request_retries=5,
        connection_retries=5,
        system_version="Windows 12",
        device_model="PC 64bit",
        app_version="5.1.1 X64",
    )


def make_guard(user_id: int):
    """
    هندلر نگهبان اختصاصی هر کلاینت.
    فقط یک dict lookup انجام می‌ده (هزینه‌ی تقریباً صفر روی CPU)،
    اگر کاربر مجاز نباشه با StopPropagation جلوی اجرای بقیه‌ی
    هندلرهای همون ایونت رو می‌گیره - بدون نیاز به تغییر تک‌تک فایل‌های handlers.
    """
    async def _guard(event):
        if not user_status.get(user_id, False):
            raise events.StopPropagation
    return _guard


def register_guard(client: TelegramClient, user_id: int):
    """
    این تابع باید همیشه قبل از register_handlers صدا زده بشه،
    چون تلتون هندلرها رو به ترتیب ثبت‌شون اجرا می‌کنه.

    فقط event typeهایی که واقعاً در پروژه استفاده می‌شن اینجا لیست شدن.
    اگر جایی از فایل‌های handlers از event type دیگه‌ای استفاده شده
    (مثلاً events.InlineQuery یا events.Album)، همون رو هم اضافه کن.
    """
    guard = make_guard(user_id)
    for ev in (
        events.NewMessage(),
        events.CallbackQuery(),
        events.ChatAction(),
        events.MessageEdited(),
        events.MessageDeleted(),
        events.UserUpdate(),
    ):
        client.add_event_handler(guard, ev)


def activate_client(client: TelegramClient, user_id: int):
    """
    نقطه‌ی واحد و مرکزی برای «فعال‌سازی کامل» یک کلاینت.

    ⚠️ این تابع باید در تمام مسیرهایی که یک کلاینت را زنده می‌کنند صدا زده شود:
    - لود اولیه‌ی برنامه (init_single_client)
    - کلیک روی دکمه‌ی «روشن کردن سلف» در auth_handler.py
    - اتمام موفق لاگین جدید (کد یا رمز دو مرحله‌ای) در auth_handler.py

    قبلاً هرکدوم از این مسیرها جدا و به‌صورت ناقص register_handlers را صدا
    می‌زدند و register_guard را فراموش می‌کردند؛ همین باعث می‌شد کاربرانی که
    از طریق دکمه یا لاگین جدید فعال می‌شدند، هیچ‌وقت تحت کنترل موجودی نباشند.
    """
    clients[user_id] = client
    user_status[user_id] = True
    register_guard(client, user_id)   # همیشه قبل از register_handlers
    register_handlers(client)


def deactivate_client(user_id: int):
    """پاک‌سازی وضعیت در حافظه هنگام خاموش/حذف شدن کلاینت"""
    user_status.pop(user_id, None)
    clients.pop(user_id, None)


def register_handlers(client: TelegramClient):
    """
    ثبت هندلرها به صورت بهینه؛ ایمپورت‌ها فقط یک‌بار در حافظه لود می‌شوند
    """
    try:
        from handlers.chat_guard_handler import register_chat_guard
        from handlers.balance_handler import register_balance_handler
        from handlers.clock import register_clock
        from handlers.font_style import register_font_handler
        from handlers.locks import register_locks
        from handlers.mute_handler import register_mute_handlers
        from handlers.spam import register_spam_handler
        from handlers.auto_react import register_auto_react
        from handlers.instagram import register_instagram_handler
        from handlers.delete_handler import register_delete_handlers
        from handlers.block_handler import register_block_handlers
        from handlers.tagger import register_tagger
        from handlers.utils_handler import register_utils_handlers
        from handlers.animation_handler import register_animation_handlers
        from handlers.ai_handler import register_ai_handlers
        from handlers.currency_handler import register_currency_handler
        from handlers.translate_handler import register_translate_handlers
        from handlers.voice_handler import register_voice_handler
        from handlers.screen_handler import register_screen_handler
        from handlers.keyword_reply import register_keyword_reply
        from handlers.proxy_handler import register_proxy_handler
        from handlers.panel_handler import register_panel_handler
        from handlers.auto_seen_handler import register_auto_seen_handler
        from handlers.text_mode_handler import register_auto_font_engine
        from handlers.chat_action_handler import register_chat_action_engine
        from handlers.game_cheat_handler import register_game_cheat_handler
        from handlers.download_handler import register_download_handler
        from handlers.autocomment_handler import register_autocomment_handler
        from handlers.forced_membership_handler import forced_membership_handler
        from handlers.action_handler import register_action_handler
        from handlers.auto_reply import register_auto_reply
        from handlers.guard_handler import register_guard_handler
        from handlers.logo import register_logo_handler
        from handlers.ping import register_ping_handler
        from handlers.relations_handlers import register_reply_handlers
        from handlers.word_filter import register_word_filter
        from handlers.admin_game_handler import register_admin_handlers
        from handlers.variz_handler import register_variz_handler
        register_admin_handlers(client)
        register_chat_guard(client)
        register_clock(client)
        register_balance_handler(client)
        register_font_handler(client)
        register_locks(client)
        register_tagger(client)
        register_spam_handler(client)
        register_auto_react(client)
        register_instagram_handler(client)
        register_delete_handlers(client)
        register_block_handlers(client)
        register_utils_handlers(client)
        register_mute_handlers(client)
        register_animation_handlers(client)
        register_ai_handlers(client)
        register_currency_handler(client)
        register_translate_handlers(client)
        register_voice_handler(client)
        register_screen_handler(client)
        register_auto_reply(client)
        register_word_filter(client)
        register_keyword_reply(client)
        forced_membership_handler(client)
        register_ping_handler(client)
        register_logo_handler(client)
        register_action_handler(client)
        register_guard_handler(client)
        register_reply_handlers(client)
        register_proxy_handler(client)
        register_panel_handler(client)
        register_auto_seen_handler(client)
        register_auto_font_engine(client)
        register_chat_action_engine(client)
        register_game_cheat_handler(client)
        register_download_handler(client)
        register_autocomment_handler(client)
        register_variz_handler(client)
    except Exception as e:
        print(f"⚠️ خطای ریجستری ویژگی‌های سلف‌بات: {e}")


async def init_single_client(user_id: int, semaphore: asyncio.Semaphore = None):
    """
    semaphore اختیاریه: اگه پاس داده نشه از سمافور مشترک ماژول استفاده می‌شه
    (برای جلوگیری از باز شدن هم‌زمان تعداد زیاد کانکشن، چه در لود اولیه چه در حین اجرا)
    """
    sem = semaphore or _connection_semaphore
    async with sem:
        # جلوگیری از لود دوباره‌ی کلاینتی که از قبل زنده و متصله
        if user_id in clients and clients[user_id].is_connected():
            user_status[user_id] = True
            return

        try:
            client = create_client(user_id)
            await client.connect()

            if await client.is_user_authorized():
                activate_client(client, user_id)  # 👈 مسیر واحد فعال‌سازی (گارد + هندلرها + وضعیت)

                async def safe_run():
                    try:
                        await client.run_until_disconnected()
                    except Exception as loop_err:
                        print(f"⚠️ کلاینت کاربر {user_id} قطع شد: {loop_err}")
                    finally:
                        deactivate_client(user_id)
                        try:
                            query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
                            await db_execute(query)
                            print(f"📉 وضعیت کاربر {user_id} غیرفعال شد.")
                        except Exception:
                            pass

                asyncio.create_task(safe_run())
                print(f"🟢 سلف‌بات کاربر {user_id} با موفقیت لود شد.")
            else:
                await client.disconnect()
                print(f"🔴 سشن کاربر {user_id} منقضی شده بود.")
                try:
                    query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
                    await db_execute(query)
                except Exception:
                    pass

        except Exception as e:
            print(f"❌ خطا در لود سشن {user_id}: {e}")
            try:
                query = supabase.table("users_diamonds").update({"is_active": False}).eq("user_id", user_id)
                await db_execute(query)
            except Exception:
                pass

    await asyncio.sleep(0.1)


async def load_existing_sessions():
    print("🔍 در حال بررسی و لود سشن‌های موجود...")
    if not os.path.exists("new_sessions"):
        return

    valid_users = set()
    try:
        query = supabase.table("users_diamonds").select("user_id").gt("diamonds", 0).eq("is_active", True)
        response = await db_execute(query)

        if response.data:
            valid_users = {int(row["user_id"]) for row in response.data}
        print(f"💰 تعداد {len(valid_users)} کاربر مجاز دریافت شد.")
    except Exception as db_error:
        print(f"⚠️ خطای دیتابیس در خواندن اطلاعات: {db_error}")
        return

    session_tasks = []

    for filename in os.listdir("new_sessions"):
        if filename.endswith(".session"):
            user_id_str = filename.replace(".session", "")
            if user_id_str.isdigit():
                user_id = int(user_id_str)
                if user_id not in valid_users:
                    continue

                task = init_single_client(user_id, _connection_semaphore)
                session_tasks.append(task)

    if session_tasks:
        print(f"⚡ در حال لود موازی {len(session_tasks)} کلاینت...")
        await asyncio.gather(*session_tasks)
        print("✅ فرآیند بارگذاری به پایان رسید.")


async def status_watcher():
    """
    تسک پس‌زمینه‌ای که هر STATUS_POLL_INTERVAL ثانیه یک‌بار، با فقط
    یک کوئری دیتابیس، وضعیت همه‌ی کاربران رو می‌خونه:

    - اگه کلاینت کاربر از قبل زنده باشه: فقط فلگ user_status آپدیت می‌شه
      (فوری و بدون قطع/وصل شدن سشن - همون چیزی که باعث فعال‌سازی/غیرفعال‌سازی
      لحظه‌ای هندلرها می‌شه)
    - اگه کاربر تازه شارژ شده و هیچ کلاینتی براش بالا نیومده: یک کلاینت
      جدید با استفاده از سمافور مشترک زنده می‌شه (بدون اسپایک ناگهانی کانکشن)

    توجه: عمداً از یک کوئری bulk استفاده شده (نه یک کوئری به‌ازای هر کاربر)
    تا با ۱۰۰۰+ کاربر هم فشار به دیتابیس و شبکه کم بمونه.
    """
    while True:
        try:
            query = supabase.table("users_diamonds").select("user_id, diamonds, is_active")
            response = await db_execute(query)
            rows = response.data or []

            for row in rows:
                user_id = int(row["user_id"])
                allowed = bool((row.get("diamonds") or 0) > 0 and row.get("is_active"))

                if user_id in clients:
                    # کلاینت زنده‌ست؛ فقط فلگ آپدیت می‌شه -> اثر فوری روی گارد
                    user_status[user_id] = allowed
                elif allowed:
                    # کاربر تازه مجاز شده ولی کلاینتی نداره -> تلاش برای بالا آوردنش
                    session_path = os.path.join("new_sessions", f"{user_id}.session")
                    if os.path.exists(session_path):
                        asyncio.create_task(init_single_client(user_id))

        except Exception as e:
            print(f"⚠️ خطای status_watcher: {e}")

        await asyncio.sleep(STATUS_POLL_INTERVAL)