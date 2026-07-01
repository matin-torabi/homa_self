import asyncio
from telethon import events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

# لیست اموجی‌های استاندارد و ایمن برای جلوگیری از Invalid Reaction
VALID_EMOJIS = ["👍", "❤️", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩"]

# دیکشنری برای ذخیره ریکشن‌ها در حافظه
active_reactions = {}

def register_auto_react(client):

    # ۱. هندلر ست کردن ریکشن
    @client.on(events.NewMessage(pattern=r"^\*?ریکت\s+(.+)"))
    async def set_reaction(event):
        if not event.out:
            return
        
        user_id = event.sender_id
        if user_id not in active_reactions:
            active_reactions[user_id] = {}

        text = event.pattern_match.group(1).strip()

        # حالت حذف
        if text.endswith("حذف"):
            target_str = text.replace("حذف", "").strip()
            try:
                target_user = await client.get_input_entity(target_str)
                target_id = getattr(target_user, 'user_id', None)
                if target_id in active_reactions[user_id]:
                    del active_reactions[user_id][target_id]
                    await event.reply(f"❌ ریکشن خودکار برای این کاربر غیرفعال شد.")
                else:
                    await event.reply(f"❓ کاربر در لیست فعال نبود.")
            except Exception as e:
                await event.reply(f"❌ خطا: {e}")
            return

        # حالت خاموش کردن کل لیست
        if text == "خاموش":
            active_reactions[user_id] = {}
            await event.reply("🛑 تمام ریکشن‌های خودکار شما غیرفعال شد.")
            return

        # حالت ست کردن ریکشن
        emoji = text
        if emoji not in VALID_EMOJIS:
            await event.reply(f"⚠️ اموجی نامعتبر! لطفاً از این لیست استفاده کنید:\n{' '.join(VALID_EMOJIS)}")
            return

        if not event.is_reply:
            await event.reply("⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید!")
            return

        try:
            reply_msg = await event.get_reply_message()
            target_id = reply_msg.sender_id
            active_reactions[user_id][target_id] = emoji
            await event.reply(f"✅ ریکشن {emoji} برای این کاربر ست شد.")
        except Exception as e:
            await event.reply(f"❌ خطا در ثبت: {e}")

    # ۲. هندلر مشاهده لیست
    @client.on(events.NewMessage(pattern=r"^\*?لیست ریکت$"))
    async def list_reactions(event):
        if not event.out: return
        
        user_id = event.sender_id
        user_list = active_reactions.get(user_id, {})
        if not user_list:
            await event.reply("📝 لیست ریکشن‌های خودکار شما خالی است.")
            return

        response = "📋 **لیست ریکشن‌های فعال:**\n\n"
        for t_id, emoji in user_list.items():
            response += f"👤 آیدی `{t_id}` 👈 ریکشن: {emoji}\n"
        await event.reply(response)

    # ۳. هندلر اصلی (عملکرد هوشمند)
    @client.on(events.NewMessage)
    async def incoming_message_reactor(event):
        if event.out or not event.sender_id:
            return

        try:
            me = await event.client.get_me()
            bot_user_id = me.id
            
            user_reactions = active_reactions.get(bot_user_id, {})
            if event.sender_id in user_reactions:
                chosen_emoji = user_reactions[event.sender_id]
                
                # تاخیر برای جلوگیری از Flood و اسپم نشدن اکانت
                await asyncio.sleep(1.5) 
                
                await event.client(SendReactionRequest(
                    peer=event.chat_id,
                    msg_id=event.id,
                    reaction=[ReactionEmoji(emoticon=chosen_emoji)]
                ))
        except Exception as e:
            # چاپ خطا به صورت خنثی تا عملکرد ربات مختل نشود
            if "Invalid" in str(e):
                pass 
            else:
                print(f"DEBUG: AutoReact Error: {e}")