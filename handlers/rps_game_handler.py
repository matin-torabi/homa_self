import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest
from config import supabase
from utils import db_execute  # اجرای غیرهمزمان کوئری‌های sync سوپابیس در thread pool

ACTIVE_RPS_GAMES = {}
CHOICE_EMOJIS = {"rock": "✊ سنگ", "paper": "✋ کاغذ", "scissors": "✌️ قیچی"}

def get_mention(user) -> str:
    """تشخیص نام نمایشی کاربر: اولویت اول یوزرنیم، اولویت دوم نام کامل"""
    if user.username:
        return f"@{user.username}"
    
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name if full_name else f"کاربر {user.id}"


async def get_user_diamonds(user_id: int) -> int:
    try:
        query = supabase.table("users_diamonds").select("diamonds").eq("user_id", user_id)
        res = await db_execute(query)
        return res.data[0]["diamonds"] if res.data else 0
    except Exception as e:
        print(f"Error getting diamonds for {user_id}: {e}")
        return 0


async def update_diamonds(user_id: int, amount: int):
    try:
        current = await get_user_diamonds(user_id)
        new_balance = max(0, current + amount)
        query = supabase.table("users_diamonds").upsert({"user_id": user_id, "diamonds": new_balance})
        await db_execute(query)
    except Exception as e:
        print(f"Error updating diamonds for {user_id}: {e}")


async def add_win_to_ranking(user_id: int, display_name: str):
    """ذخیره برد به همراه زیباترین نام در دسترس کاربر"""
    try:
        query = supabase.table("rps_rankings").select("wins_count").eq("user_id", user_id)
        res = await db_execute(query)
        if res.data:
            new_wins = res.data[0]["wins_count"] + 1
            query = supabase.table("rps_rankings").update(
                {"wins_count": new_wins, "username": display_name}
            ).eq("user_id", user_id)
            await db_execute(query)
        else:
            query = supabase.table("rps_rankings").insert(
                {"user_id": user_id, "username": display_name, "wins_count": 1}
            )
            await db_execute(query)
    except Exception as e:
        print(f"Error updating ranking for {user_id}: {e}")


# 🎮 شروع بازی
async def start_rps_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    match = re.match(r'^گیم\s+(\d+)$', message.text)
    if not match:
        return

    bet_amount = int(match.group(1))
    creator_id = user.id
    creator_display = get_mention(user)

    # ⚡ بررسی اینکه مبلغ شرط وارد شده کمتر از ۳۰ طلا نباشد
    if bet_amount < 30:
        await message.reply_text("⚠️ حداقل مبلغ شرط برای ساخت بازی 30 طلا می‌باشد!")
        return

    # بررسی موجودی طلا سازنده برای شرکت در بازی
    creator_diamonds = await get_user_diamonds(creator_id)
    if creator_diamonds < 30:
        await message.reply_text("❌ برای شرکت در بازی‌ها باید حداقل ۳۰ طلا داشته باشید!")
        return

    if creator_diamonds < bet_amount:
        await message.reply_text(f"❌ موجودی طلا شما کافی نیست!\nطلا شما: {creator_diamonds} | 💰 شرط: {bet_amount}")
        return

    game_id = f"{chat.id}_{message.message_id}"

    ACTIVE_RPS_GAMES[game_id] = {
        "creator_id": creator_id,
        "creator_name": creator_display,
        "opponent_id": None,
        "opponent_name": None,
        "bet_amount": bet_amount,
        "creator_choice": None,
        "opponent_choice": None,
        "status": "waiting"
    }

    text = (
        "🎮 <b>درخواست بازی سنگ، کاغذ، قیچی!</b>\n\n"
        f"👤 <b>سازنده:</b> {creator_display}\n"
        f"💰 <b>مبلغ شرط:</b> <code>{bet_amount}</code> طلا \n\n"
        "💬 یک نفر برای شروع بازی باید دکمه <b>« قبول »</b> را بزند!"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"rps_join_{game_id}"),
            InlineKeyboardButton("❌ لغو بازی", callback_data=f"rps_cancel_{game_id}")
        ]
    ])

    await message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


# 🎛️ مدیریت کلیک‌ها
async def handle_rps_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    clicker = query.from_user
    clicker_id = clicker.id
    clicker_display = get_mention(clicker)
    
    data = query.data

    async def safe_answer(text, show_alert=False):
        try:
            await query.answer(text, show_alert=show_alert)
        except BadRequest as e:
            if "Query is too old" in str(e):
                print("📌 [RPS Game] کالبک قدیمی بود.")
            else:
                raise e

    if data.startswith("rps_cancel_"):
        game_id = data.replace("rps_cancel_", "")
        if game_id not in ACTIVE_RPS_GAMES:
            await safe_answer("❌ این بازی منقضی شده است.", show_alert=True)
            return

        game = ACTIVE_RPS_GAMES[game_id]
        if clicker_id != game["creator_id"]:
            await safe_answer("⚠️ فقط سازنده بازی می‌تواند آن را لغو کند!", show_alert=True)
            return

        del ACTIVE_RPS_GAMES[game_id]
        await query.edit_message_text("❌ <b>این بازی توسط سازنده لغو شد.</b>", parse_mode="HTML")
        return

    elif data.startswith("rps_join_"):
        game_id = data.replace("rps_join_", "")
        if game_id not in ACTIVE_RPS_GAMES:
            await safe_answer("❌ این بازی منقضی شده است.", show_alert=True)
            return

        game = ACTIVE_RPS_GAMES[game_id]

        if clicker_id == game["creator_id"]:
            await safe_answer("⚠️ شما خودتان سازنده بازی هستید!", show_alert=True)
            return

        if game["status"] != "waiting":
            await safe_answer("⚠️ این بازی قبلاً شروع شده است!", show_alert=True)
            return

        opp_diamonds = await get_user_diamonds(clicker_id)
        if opp_diamonds < 30:
            await safe_answer("❌ شما برای بازی باید حداقل ۳۰ طلا داشته باشید!", show_alert=True)
            return
        if opp_diamonds < game["bet_amount"]:
            await safe_answer(f"❌ طلا شما کافی نیست! موجودی: {opp_diamonds}", show_alert=True)
            return

        game["opponent_id"] = clicker_id
        game["opponent_name"] = clicker_display
        game["status"] = "playing"

        await safe_answer("✅ شما چالش را قبول کردید!")
        await send_game_choices_markup(query, game_id, game)
        return

    elif data.startswith("rps_play_"):
        parts = data.split("_")
        choice = parts[2]
        game_id = "_".join(parts[3:])

        if game_id not in ACTIVE_RPS_GAMES:
            await safe_answer("❌ بازی یافت نشد یا پایان یافته است.", show_alert=True)
            return

        game = ACTIVE_RPS_GAMES[game_id]

        if clicker_id != game["creator_id"] and clicker_id != game["opponent_id"]:
            await safe_answer("⚠️ شما بازیکن این مسابقه نیستید!", show_alert=True)
            return

        if clicker_id == game["creator_id"]:
            if game["creator_choice"]:
                await safe_answer("⚠️ شما قبلاً انتخاب خود را انجام داده‌اید!", show_alert=True)
                return
            game["creator_choice"] = choice
            await safe_answer("✊ انتخاب شما ثبت شد!")
        else:
            if game["opponent_choice"]:
                await safe_answer("⚠️ شما قبلاً انتخاب خود را انجام داده‌اید!", show_alert=True)
                return
            game["opponent_choice"] = choice
            await safe_answer("✊ انتخاب شما ثبت شد!")

        if game["creator_choice"] and game["opponent_choice"]:
            await process_game_result(query, game_id, game)
        else:
            await send_game_choices_markup(query, game_id, game)


async def show_rps_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = supabase.table("rps_rankings").select("*").order("wins_count", desc=True).limit(10)
        res = await db_execute(query)
        if not res.data:
            await update.message.reply_text("📭 هنوز بردی در سیستم ثبت نشده است.")
            return

        lines = ["🏆 <b>برترین بازیکنان سنگ، کاغذ، قیچی</b> 🏆\n"]
        for i, row in enumerate(res.data, 1):
            lines.append(f"🏅 {i}. {row['username']} (<code>{row['user_id']}</code>) ➔ <b>{row['wins_count']} برد</b>")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text("❌ خطا در دریافت رنکینگ!")
        print(e)


async def send_game_choices_markup(query, game_id, game):
    c_status = "✅ انتخاب کرد" if game["creator_choice"] else "⏳ در حال انتخاب..."
    o_status = "✅ انتخاب کرد" if game["opponent_choice"] else "⏳ در حال انتخاب..."

    text = (
        "🎮 <b>نبرد سنگ، کاغذ، قیچی آغاز شد!</b>\n\n"
        f"👤 <b>بازیکن اول:</b> {game['creator_name']} ➔ {c_status}\n"
        f"👤 <b>بازیکن دوم:</b> {game['opponent_name']} ➔ {o_status}\n\n"
        f"💰 <b>شرط:</b> <code>{game['bet_amount']}</code> طلا \n"
        "👇 لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✊ سنگ", callback_data=f"rps_play_rock_{game_id}"),
            InlineKeyboardButton("✋ کاغذ", callback_data=f"rps_play_paper_{game_id}"),
            InlineKeyboardButton("✌️ قیچی", callback_data=f"rps_play_scissors_{game_id}")
        ]
    ])
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest as e:
        print(f"Error in send_choices: {e}")


async def process_game_result(query, game_id, game):
    c_choice = game["creator_choice"]
    o_choice = game["opponent_choice"]
    bet = game["bet_amount"]
    c_name = game["creator_name"]
    o_name = game["opponent_name"]

    if c_choice == o_choice:
        result_text = (
            "🤝 <b>بازی به تساوی کشید!</b>\n\n"
            f"👤 {c_name} ➔ {CHOICE_EMOJIS[c_choice]}\n"
            f"👤 {o_name} ➔ {CHOICE_EMOJIS[o_choice]}\n\n"
            "هیچ طلایی از حساب کسی کسر یا اضافه نشد."
        )
        try:
            await query.edit_message_text(result_text, reply_markup=None, parse_mode="HTML")
        except BadRequest:
            pass
        if game_id in ACTIVE_RPS_GAMES:
            del ACTIVE_RPS_GAMES[game_id]
        return

    if (c_choice == "rock" and o_choice == "scissors") or \
       (c_choice == "paper" and o_choice == "rock") or \
       (c_choice == "scissors" and o_choice == "paper"):
        winner = "creator"
    else:
        winner = "opponent"

    if winner == "creator":
        await update_diamonds(game["creator_id"], +bet)
        await update_diamonds(game["opponent_id"], -bet)
        await add_win_to_ranking(game["creator_id"], game["creator_name"])

        final_text = (
            "🎉 <b>بازی به پایان رسید!</b> 🎉\n\n"
            f"👑 <b>برنده:</b> {c_name} ({CHOICE_EMOJIS[c_choice]})\n"
            f"🥶 <b>بازنده:</b> {o_name} ({CHOICE_EMOJIS[o_choice]})\n\n"
            f"💰 مقدار <code>{bet}</code> طلا به حساب برنده واریز شد!\n"
        )
    else:
        await update_diamonds(game["opponent_id"], +bet)
        await update_diamonds(game["creator_id"], -bet)
        await add_win_to_ranking(game["opponent_id"], game["opponent_name"])

        final_text = (
            "🎉 <b>بازی به پایان رسید!</b> 🎉\n\n"
            f"👑 <b>برنده:</b> {o_name} ({CHOICE_EMOJIS[o_choice]})\n"
            f"🥶 <b>بازنده:</b> {c_name} ({CHOICE_EMOJIS[c_choice]})\n\n"
            f"💰 مقدار <code>{bet}</code> طلا به حساب برنده واریز شد!\n"
        )

    try:
        await query.edit_message_text(final_text, reply_markup=None, parse_mode="HTML")
    except BadRequest:
        pass
    
    if game_id in ACTIVE_RPS_GAMES:
        del ACTIVE_RPS_GAMES[game_id]


def register_rps_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^گیم\s+(\d+)$'), start_rps_request))
    app.add_handler(CallbackQueryHandler(handle_rps_clicks, pattern=r'^rps_.*'))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^🏆 رنک گیم$'), show_rps_ranking))