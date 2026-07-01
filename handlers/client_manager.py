import os
import asyncio
import logging

from telethon import TelegramClient

from config import API_ID, API_HASH, supabase

logger = logging.getLogger(__name__)

# ==========================
# Runtime Storage
# ==========================

clients: dict[int, TelegramClient] = {}
login_data: dict = {}

# Task مربوط به هر کلاینت
client_tasks: dict[int, asyncio.Task] = {}

# جلوگیری از ساخت همزمان یک کلاینت
client_locks: dict[int, asyncio.Lock] = {}

# ==========================
# Telegram Client Factory
# ==========================

def create_client(user_id: int) -> TelegramClient:

    return TelegramClient(
        session=f"new_sessions/{user_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        timeout=60,
        request_retries=5,
        connection_retries=5,
        retry_delay=3,
        flood_sleep_threshold=60,
        device_model="PC 64bit",
        system_version="Windows 12",
        app_version="5.1.1 X64",
    )


# ==========================
# Register Handlers
# ==========================

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


def register_handlers(client: TelegramClient) -> None:
    """
    ثبت تمامی هندلرهای سلف‌بات
    """
    try:
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

    except Exception:
        logger.exception("Failed to register handlers")
# ==========================
# Background Client Task
# ==========================
async def safe_run(client: TelegramClient, user_id: int):
    reconnect_delay = 5
    while True:
        try:
            if not client.is_connected():
                await client.connect()

            reconnect_delay = 5
            await client.run_until_disconnected()

        except asyncio.CancelledError:
            logger.info(f"Client {user_id} task cancelled.")
            break

        except Exception as e:
            logger.warning(
                f"Client {user_id} disconnected: {e}"
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)

    try:
        if client.is_connected():
            await client.disconnect()
    except Exception:
        logger.exception(f"Disconnect error ({user_id})")

    clients.pop(user_id, None)
    client_tasks.pop(user_id, None)
    client_locks.pop(user_id, None)

# ==========================
# Initialize Client
# ==========================
async def init_single_client(
    user_id: int,
    semaphore: asyncio.Semaphore
):
    async with semaphore:
        lock = client_locks.setdefault(
            user_id,
            asyncio.Lock()
        )
        async with lock:
            if user_id in clients:
                logger.info(
                    f"Client {user_id} already loaded."
                )
                return

            client = None

            try:
                client = create_client(user_id)
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(
                        f"Unauthorized session ({user_id})"
                    )

                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                    await asyncio.to_thread(
                        lambda: supabase.table("users_diamonds")
                        .update(
                            {
                                "is_active": False
                            }
                        )
                        .eq("user_id", user_id)
                        .execute()
                    )
                    return

                clients[user_id] = client

                register_handlers(client)

                task = asyncio.create_task(
                    safe_run(
                        client,
                        user_id
                    ),
                    name=f"client_{user_id}"
                )

                client_tasks[user_id] = task

                logger.info(
                    f"Client {user_id} loaded successfully."
                )

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.exception(
                    f"Error loading client {user_id}: {e}"
                )
                if client:

                    try:
                        await client.disconnect()
                    except Exception:
                        pass

                clients.pop(user_id, None)
                task = client_tasks.pop(
                    user_id,
                    None
                )
                if task:
                    task.cancel()
                try:

                    await asyncio.to_thread(
                        lambda: supabase.table("users_diamonds")
                        .update(
                            {
                                "is_active": False
                            }
                        )
                        .eq("user_id", user_id)
                        .execute()
                    )
                except Exception:
                    logger.exception(
                        "Failed updating Supabase."
                    )
            finally:
                await asyncio.sleep(0.05)
# ==========================
# Load Existing Sessions
# ==========================
async def load_existing_sessions():
    logger.info("Checking existing sessions...")
    session_dir = "new_sessions"
    if not os.path.isdir(session_dir):
        logger.warning("Session directory not found.")
        return

    # دریافت کاربران فعال
    try:
        response = await asyncio.to_thread(
            lambda: (
                supabase.table("users_diamonds")
                .select("user_id")
                .gt("diamonds", 0)
                .eq("is_active", True)
                .execute()
            )
        )
        valid_users = {
            int(row["user_id"])
            for row in (response.data or [])
        }

        logger.info(
            "Found %s active users in database.",
            len(valid_users)
        )
    except Exception:

        logger.exception("Failed to fetch active users.")

        return

    session_tasks = []

    # مقدار مناسب برای اکثر VPS ها
    semaphore = asyncio.Semaphore(20)
    for filename in os.listdir(session_dir):
        if not filename.endswith(".session"):
            continue
        try:
            user_id = int(filename[:-8])
        except ValueError:
            continue

        if user_id not in valid_users:
            continue

        session_tasks.append(
            init_single_client(
                user_id,
                semaphore
            )
        )

    if not session_tasks:
        logger.info("No active sessions found.")
        return

    logger.info(
        "Loading %s sessions...",
        len(session_tasks)
    )

    results = await asyncio.gather(
        *session_tasks,
        return_exceptions=True
    )

    success = 0
    failed = 0

    for result in results:
        if isinstance(result, Exception):
            failed += 1
            logger.error(result)

        else:
            success += 1

    logger.info(
        "Finished loading sessions | Success=%s | Failed=%s",
        success,
        failed
    )

# ==========================
# Stop One Client
# ==========================
async def stop_client(user_id: int):
    task = client_tasks.pop(user_id, None)

    if task:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

    client = clients.pop(user_id, None)

    if client:

        try:
            if client.is_connected():
                await client.disconnect()

        except Exception:
            logger.exception(
                "Error disconnecting client %s",
                user_id
            )

    client_locks.pop(user_id, None)

# ==========================
# Stop All Clients
# ==========================
async def shutdown_clients():

    logger.info(
        "Shutting down %s clients...",
        len(clients)
    )

    tasks = [
        stop_client(user_id)
        for user_id in list(clients.keys())
    ]

    if tasks:

        await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

    logger.info("All clients stopped.")                