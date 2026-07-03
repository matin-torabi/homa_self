import os
import asyncio
from telethon import TelegramClient
from config import API_HASH, API_ID
from config import supabase
from utils import db_execute  # ایمپورت تابع مدیریت ترد

# دیکشنری‌ها برای مدیریت کلاینت‌ها در وضعیت زنده
clients = {}
login_data = {}

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


async def init_single_client(user_id: int, semaphore: asyncio.Semaphore):
    async with semaphore:
        try:
            client = create_client(user_id)
            await client.connect()
            
            if await client.is_user_authorized():
                clients[user_id] = client
                register_handlers(client)
                
                async def safe_run():
                    try:
                        await client.run_until_disconnected()
                    except Exception as loop_err:
                        print(f"⚠️ کلاینت کاربر {user_id} قطع شد: {loop_err}")
                    finally:
                        try:
                            # تغییر به ساختار جدید
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
        # تغییر به ساختار جدید (ایجاد کوئری و سپس await db_execute)
        query = supabase.table("users_diamonds").select("user_id").gt("diamonds", 0).eq("is_active", True)
        response = await db_execute(query)
            
        if response.data:
            valid_users = {int(row["user_id"]) for row in response.data}
        print(f"💎 تعداد {len(valid_users)} کاربر مجاز دریافت شد.")
    except Exception as db_error:
        print(f"⚠️ خطای دیتابیس در خواندن اطلاعات: {db_error}")
        return

    session_tasks = []
    connection_semaphore = asyncio.Semaphore(50) 

    for filename in os.listdir("new_sessions"):
        if filename.endswith(".session"):
            user_id_str = filename.replace(".session", "")
            if user_id_str.isdigit():
                user_id = int(user_id_str)
                if user_id not in valid_users:
                    continue

                task = init_single_client(user_id, connection_semaphore)
                session_tasks.append(task)

    if session_tasks:
        print(f"⚡ در حال لود موازی {len(session_tasks)} کلاینت...")
        await asyncio.gather(*session_tasks)
        print("✅ فرآیند بارگذاری به پایان رسید.")        