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
    return ''

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
        '<b>\U0001f4ca \u6570\u636e\u6982\u89c8</b>\n'
        + L1 + "\n" +
        f"  {L} \U0001f550 \u8fdb\u884c\u4e2d  <b>{running:>4}</b>  {L}\n" +
        f"  {L} \U0001f381 \u5956\u54c1\u6c60  <b>{pool:>4}</b>  {L}\n" +
        f"  {L} \u2705 \u5df2\u5b8c\u6210  <b>{s['completed_activities']:>4}</b>  {L}\n" +
        f"  {L} \U0001f465 \u603b\u53c2\u4e0e  <b>{s['total_participants']:>4}</b>  {L}\n" +
        L2
    )
    keyboard = [
        [InlineKeyboardButton('\U0001f388 \u521b\u5efa\u6d3b\u52a8', callback_data='menu_create'),
         InlineKeyboardButton('\U0001f4f5 \u6d3b\u52a8\u5217\u8868', callback_data='menu_activities')],
        [InlineKeyboardButton('\U0001f381 \u5956\u54c1\u7ba1\u7406', callback_data='menu_prizes'),
         InlineKeyboardButton('\U0001f4ca \u6570\u636e\u7edf\u8ba1', callback_data='menu_stats')],
        [InlineKeyboardButton('\U0001f465 \u64cd\u4f5c\u5458\u7ba1\u7406', callback_data='menu_operators'),
         InlineKeyboardButton('\U0001f4c1 \u5907\u4efd', callback_data='menu_backup')],
    ]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))



async def menu_router(update, context, db):
    """Route menu callback queries to appropriate handlers."""
    query = update.callback_query
    data = query.data

    try:
        if data == 'menu_main':
            await show_main_menu(update, context, db)

        elif data == 'menu_activities':
            await show_activities_menu(update, context, db)

        elif data == 'menu_prizes':
            await show_prize_menu(update, context, db)

        elif data == 'menu_stats':
            await show_stats_menu(update, context, db)

        elif data == 'menu_operators':
            await show_operators_menu(update, context, db)

        elif data == 'menu_backup':
            await show_backup_menu(update, context, db)

        elif data.startswith('op_'):
            await handle_operator_action(update, context, db)

        elif data.startswith('act_'):
            await handle_activity_action(update, context, db)

        elif data == 'menu_create':
            # Handled in main.py
            pass

        else:
            await query.answer('未知操作', show_alert=True)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'menu_router error: {e}', exc_info=True)
        await query.answer(f'\u9519\u8bef: {e}', show_alert=True)

async def show_activities_menu(update, context, db):
    """Show list of all activities."""
    query = update.callback_query
    acts = await db.list_activities()
    if not acts:
        await query.edit_message_text(
            '\ud83d\udcf1 \u6ca1\u6709\u6d3b\u52a8\u3002\n\n\u4f7f\u7528 \u521b\u5efa\u6d3b\u52a8 \u6765\u65b0\u5efa\u4e00\u4e2a\u3002',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')]])
        )
        return

    lines = ['<b>\U0001f4cb \u6d3b\u52a8\u5217\u8868</b>\n']
    for a in acts:
        st = a.get('status', 'draft')
        emoji = {'active': '\U0001f7e2', 'draft': '\u26aa', 'completed': '\u2705', 'cancelled': '\U0001f534'}.get(st, '\u26aa')
        lines.append(f'{emoji} <b>#{a["id"]}</b> {a["title"]} ({st})')
    lines.append('')
    text = '\n'.join(lines)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, text, kb)

async def show_prize_menu(update, context, db):
    """Show prize management menu."""
    prizes = await db.list_prizes()
    lines = ['<b>\U0001f381 \u5956\u54c1\u7ba1\u7406</b>']
    if prizes:
        for p in prizes:
            lines.append(f'  \U0001f4b0 {p["name"]}')
    else:
        lines.append('  (\u6682\u65e0\u5956\u54c1)')
    lines.append('')
    lines.append('\u4f7f\u7528 /add \u5956\u54c1\u540d \u6dfb\u52a0\uff0c/delete \u5956\u54c1\u540d \u5220\u9664')

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, '\n'.join(lines), kb)

async def show_stats_menu(update, context, db):
    """Show statistics."""
    s = await db.get_stats()
    text = (
        '<b>\U0001f4ca \u6570\u636e\u7edf\u8ba1</b>\n\n'
        f'\U0001f4cc \u603b\u6d3b\u52a8: {s["total_activities"]}\n'
        f'\U0001f7e2 \u8fdb\u884c\u4e2d: {s["active_activities"]}\n'
        f'\u2705 \u5df2\u5b8c\u6210: {s["completed_activities"]}\n'
        f'\U0001f534 \u5df2\u53d6\u6d88: {s["cancelled_activities"]}\n'
        f'\U0001f465 \u603b\u53c2\u4e0e: {s["total_participants"]}\n'
        f'\U0001f3c6 \u603b\u4e2d\u5956: {s["total_winners"]}\n'
        f'\U0001f381 \u5956\u54c1\u6570: {s["total_prizes"]}'
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, text, kb)

async def show_operators_menu(update, context, db):
    """Show operator management."""
    query = update.callback_query
    ops = await db.list_operators()
    lines = ['<b>\U0001f465 \u64cd\u4f5c\u5458\u7ba1\u7406</b>\n']
    if ops:
        for o in ops:
            from_user = o.get('added_by', 0)
            lines.append(f'  \U0001f464 User #{o["user_id"]} (\u6dfb\u52a0\u8005: #{from_user})')
    else:
        lines.append('  \u6682\u65e0\u64cd\u4f5c\u5458\n')
    lines.append('')
    lines.append('\u53d1\u9001 /op add <id> \u6dfb\u52a0\u64cd\u4f5c\u5458')
    lines.append('\u53d1\u9001 /op remove <id> \u5220\u9664\u64cd\u4f5c\u5458')

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, '\n'.join(lines), kb)

async def show_backup_menu(update, context, db):
    """Show backup menu."""
    text = '<b>\U0001f4c1 \u5907\u4efd</b>\n\n\u4f7f\u7528 /backup \u4e0b\u8f7d\u6570\u636e\u5e93\u5907\u4efd'
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, text, kb)

async def handle_operator_action(update, context, db):
    """Handle operator management actions."""
    await update.callback_query.answer('\u8bf7\u4f7f\u7528 /op add <id> \u6216 /op remove <id> \u547d\u4ee4', show_alert=True)

async def handle_activity_action(update, context, db):
    """Handle activity actions."""
    await update.callback_query.answer('\u5f85\u5b9e\u73b0', show_alert=True)
