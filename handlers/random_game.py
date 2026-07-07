import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from handlers.rps_game_handler import get_user_diamonds, update_diamonds, add_win_to_ranking, get_mention

ACTIVE_DICE_GAMES = {}
GAME_EXPIRY_SECONDS = 120  # ⏳ اگر تا ۲ دقیقه کسی join نکند، بازی خودکار باطل می‌شود


def cancel_expiry_job(context: ContextTypes.DEFAULT_TYPE, game_id: str):
    """حذف job زمان‌بندی‌شده‌ی انقضا (وقتی بازی زودتر join/cancel شود دیگر لازم نیست اجرا شود)"""
    jobs = context.job_queue.get_jobs_by_name(f"dice_expire_{game_id}")
    for job in jobs:
        job.schedule_removal()


async def expire_dice_game(context: ContextTypes.DEFAULT_TYPE):
    """⌛ اجرا می‌شود اگر بازی بعد از GAME_EXPIRY_SECONDS هنوز حریفی پیدا نکرده باشد"""
    job_data = context.job.data
    game_id = job_data["game_id"]
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]

    game = ACTIVE_DICE_GAMES.get(game_id)
    if not game or game["status"] != "waiting":
        return  # قبلاً join/cancel شده، کاری لازم نیست

    # 💰 بازگرداندن طلای بلوکه‌شده‌ی سازنده
    await update_diamonds(game["creator_id"], game["bet_amount"])
    del ACTIVE_DICE_GAMES[game_id]

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "⌛ <b>این بازی به دلیل عدم پاسخ حریف تا ۲ دقیقه، "
                "به‌صورت خودکار باطل شد.</b>\n💰 طلای شرط بازگردانده شد."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


async def start_dice_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if update.effective_chat.type == "private": return

    text = message.text
    match = re.match(r'^بازی\s+(\d+)$', text)
    if not match: return

    bet_amount = int(match.group(1))

    if bet_amount < 30:
        await message.reply_text("⚠️ حداقل شرط برای بازی ۳۰ طلا است!")
        return

    creator_diamonds = await get_user_diamonds(user.id)
    if creator_diamonds < bet_amount:
        await message.reply_text("❌ موجودی شما برای این شرط کافی نیست.")
        return

    # ۱. کسر مبلغ از سازنده بلافاصله هنگام ساخت بازی
    await update_diamonds(user.id, -bet_amount)

    game_id = f"dice_{user.id}_{message.message_id}"
    ACTIVE_DICE_GAMES[game_id] = {
        "creator_id": user.id,
        "creator_name": get_mention(user),
        "opponent_id": None,
        "opponent_name": None,
        "bet_amount": bet_amount,
        "status": "waiting"
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("قبول", callback_data=f"dice_join_{game_id}", style="success"),
        InlineKeyboardButton("لغو", callback_data=f"dice_cancel_{game_id}", style="danger")
    ]])

    sent_message = await message.reply_text(
        f"<b>درخواست بازی {bet_amount}</b>\n\n"
        f"👤 سازنده: {get_mention(user)}\n"
        f"💰 شرط: {bet_amount} طلا\n\n"
        "💬 یک نفر برای شروع بازی باید دکمه <b>« قبول »</b> را بزند!",
        reply_markup=keyboard, parse_mode="HTML"
    )

    # ⏳ زمان‌بندی ابطال خودکار بازی اگر تا ۲ دقیقه کسی join نکند
    context.job_queue.run_once(
        expire_dice_game,
        when=GAME_EXPIRY_SECONDS,
        data={"game_id": game_id, "chat_id": update.effective_chat.id, "message_id": sent_message.message_id},
        name=f"dice_expire_{game_id}"
    )


async def handle_dice_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user

    if data.startswith("dice_cancel_"):
        game_id = data.replace("dice_cancel_", "")
        game = ACTIVE_DICE_GAMES.get(game_id)

        if not game:
            await query.answer("❌ این بازی دیگر در دسترس نیست!", show_alert=True)
            return

        if game["creator_id"] != user.id:
            await query.answer("⚠️ فقط سازنده بازی می‌تواند آن را لغو کند!", show_alert=True)
            return

        if game["status"] != "waiting":
            await query.answer("⚠️ بازی شروع شده و دیگر قابل لغو نیست!", show_alert=True)
            return

        # ۲. بازگرداندن طلا به سازنده در صورت لغو
        await update_diamonds(user.id, game["bet_amount"])
        cancel_expiry_job(context, game_id)  # چون بازی دستی لغو شد، دیگر نیازی به expire خودکار نیست
        del ACTIVE_DICE_GAMES[game_id]
        await query.edit_message_text("❌ بازی توسط سازنده لغو شد و طلا به حساب شما برگشت.")
        return

    if data.startswith("dice_join_"):
        game_id = data.replace("dice_join_", "")
        game = ACTIVE_DICE_GAMES.get(game_id)

        if not game or game["status"] != "waiting":
            await query.answer("❌ این بازی دیگر در دسترس نیست!", show_alert=True)
            return

        if user.id == game["creator_id"]:
            await query.answer("شما خودتان سازنده هستید!", show_alert=True)
            return

        bet = game["bet_amount"]
        opp_diamonds = await get_user_diamonds(user.id)

        if opp_diamonds < bet:
            await query.answer("موجودی شما کافی نیست!", show_alert=True)
            return

        # ۳. کسر مبلغ از نفر دوم
        await update_diamonds(user.id, -bet)
        game["opponent_id"] = user.id
        game["opponent_name"] = get_mention(user)
        game["status"] = "finished"

        cancel_expiry_job(context, game_id)  # حریف پیدا شد، دیگر نیازی به expire خودکار نیست

        # قرعه‌کشی (مساوی هم در نظر گرفته شد: عدد ۳)
        # ۱: برد سازنده، ۲: برد حریف، ۳: مساوی
        # قرعه‌کشی: ۱: برد سازنده، ۲: برد حریف
        result = random.choice([1, 2])

        if result == 1:
            winner_id, winner_name = game["creator_id"], game["creator_name"]
            loser_id, loser_name = game["opponent_id"], game["opponent_name"]
        else:
            winner_id, winner_name = game["opponent_id"], game["opponent_name"]
            loser_id, loser_name = game["creator_id"], game["creator_name"]

        # پرداخت جایزه به برنده (مجموع دو شرط)
        await update_diamonds(winner_id, 2 * bet)
        await add_win_to_ranking(winner_id, winner_name)

        winner_balance = await get_user_diamonds(winner_id)
        loser_balance = await get_user_diamonds(loser_id)

        await query.edit_message_text(
            f"<b>بازی به پایان رسید!</b>\n\n"
            f"👑 برنده: {winner_name}\n"
            f"💰 موجودی برنده: {winner_balance}\n"
            f"💸 بازنده: {loser_name}\n"
            f"💰 موجودی بازنده: {loser_balance}",
            parse_mode="HTML"
        )

        del ACTIVE_DICE_GAMES[game_id]


def register_dice_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^بازی\s+(\d+)$'), start_dice_request))
    app.add_handler(CallbackQueryHandler(handle_dice_clicks, pattern=r'^dice_.*'))