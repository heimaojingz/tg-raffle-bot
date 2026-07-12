# Menu system for Raffle Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import html
import io
import uuid

def _get_bot_username(update) -> str:
    """Get bot username without hardcoded fallback."""
    try:
        bot = update.get_bot()
        if bot and bot.username:
            return bot.username
    except Exception:
        pass
    return 'cjyhq_bot'

async def _edit_or_send(update: Update, text: str, markup: InlineKeyboardMarkup):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await update.callback_query.message.reply_text(
                text, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)
    else:
        await update.message.reply_text(
            text, parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)

async def show_main_menu(update: Update, context, db):
    running = await db.get_running_count()
    pool = await db.get_prize_pool_count()
    s = await db.get_stats()
    L = "\u2502"
    L1 = "\u250c" + "\u2500" * 20 + "\u2510"
    L2 = "\u2514" + "\u2500" * 20 + "\u2518"
    text = (
        '<b>    \U0001f30f \u62bd\u5956\u7ba1\u7406\u7cfb\u7edf</b>\n'
        '\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\u2502\n\n'
        '<b>\U0001f4f3 \u6570\u636e\u6982\u89c8</b>\n'
        + L1 + "\n" +
        f"  {L} \U0001f550 \u8fdb\u884c\u4e2d  <b>{running:>4}</b>  {L}\n" +
        f"  {L} \U0001f3b3 \u5956\u54c1\u6c60  <b>{pool:>4}</b>  {L}\n" +
        f"  {L} \u2705 \u5df2\u5b8c\u6210  <b>{{s[\"completed_activities\"]:>4}}</b>  {L}\n" +
        f"  {L} \U0001f443 \u603b\u53c2\u4e0e  <b>{{s[\"total_participants\"]:>4}}</b>  {L}\n" +
        L2
    )
    keyboard = [
        [InlineKeyboardButton('\U0001f388 \u521b\u5efa\u6d3b\u52a8', callback_data='menu_create'),
         InlineKeyboardButton('\U0001f4f5 \u6d3b\u52a8\u5217\u8868', callback_data='menu_activities')],
        [InlineKeyboardButton('\U0001f3b3 \u5956\u54c1\u7ba1\u7406', callback_data='menu_prizes'),
         InlineKeyboardButton('\U0001f4f3 \u6570\u636e\u7edf\u8ba1', callback_data='menu_stats')],
        [InlineKeyboardButton('\U0001f443 \u64cd\u4f5c\u5458\u7ba1\u7406', callback_data='menu_operators'),
         InlineKeyboardButton('\U0001f4c1 \u5907\u4efd', callback_data='menu_backup')],
    ]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))
