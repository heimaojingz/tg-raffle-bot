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

        elif data.startswith('op_add'):
            # Set waiting state and ask for user ID
            context.user_data['_waiting_op_add'] = True
            await query.edit_message_text(
                '\U0001f464 \u8bf7\u8f93\u5165\u7528\u6237ID\uff08\u6570\u5b57\uff09\u6216\u8f6c\u53d1\u4ed6\u7684\u6d88\u606f\uff1a',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('\u274c \u53d6\u6d88', callback_data='menu_operators')
                ]])
            )

        elif data.startswith('op_del_'):
            uid = int(data.replace('op_del_', ''))
            ok = await db.remove_operator(uid)
            if ok:
                await query.answer('\u2705 \u5df2\u79fb\u9664', show_alert=True)
            else:
                await query.answer('\u274c \u79fb\u9664\u5931\u8d25', show_alert=True)
            await show_operators_menu(update, context, db)

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
    """Show list of all activities with delete buttons."""
    query = update.callback_query
    acts = await db.list_activities()
    if not acts:
        await query.edit_message_text('\U0001f4f1 \u6ca1\u6709\u6d3b\u52a8\u3002\n\n\u4f7f\u7528 \u521b\u5efa\u6d3b\u52a8 \u6765\u65b0\u5efa\u4e00\u4e2a\u3002', parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')]]))
        return

    lines = ['<b>\U0001f4cb \u6d3b\u52a8\u5217\u8868</b>\\n']
    keyboard = []
    for a in acts:
        st = a.get('status', 'draft')
        emoji = {'active': '\U0001f7e2', 'draft': '\u26aa', 'completed': '\u2705', 'cancelled': '\U0001f534'}.get(st, '\u26aa')
        lines.append(f"{emoji} <b>#{a['id']}</b> {a['title']} ({st})")
        keyboard.append([InlineKeyboardButton(emoji + ' #' + str(a['id']) + ' \u274c \u5220\u9664', callback_data='act_del_' + str(a['id']))])
    lines.append('')
    lines.append('\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u5220\u9664\u5bf9\u5e94\u6d3b\u52a8\uff08\u4e0d\u53ef\u6062\u590d\uff09')
    text = '\\n'.join(lines)
    keyboard.append([InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')])
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

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
    """Show operator management with add/delete buttons."""
    query = update.callback_query
    ops = await db.list_operators()
    lines = ['<b>👥 操作员管理</b>\n']
    keyboard = []
    if ops:
        for o in ops:
            from_user = o.get('added_by', 0)
            uid_str = html.escape(str(o['user_id']))
            adder_str = html.escape(str(from_user))
            lines.append(f'  👤 User #{uid_str} (添加者: #{adder_str})')
            keyboard.append([
                InlineKeyboardButton(f'👤 #{o["user_id"]} ❌ 删除', callback_data=f'op_del_{o["user_id"]}')
            ])
    else:
        lines.append('  暂无操作员\n')
    lines.append('')
    keyboard.append([InlineKeyboardButton('➕ 添加操作员', callback_data='op_add_btn')])
    keyboard.append([InlineKeyboardButton('🔙 返回主菜单', callback_data='menu_main')])

    await _edit_or_send(update, '\n'.join(lines), InlineKeyboardMarkup(keyboard))
async def show_backup_menu(update, context, db):
    """Show backup menu."""
    text = '<b>\U0001f4c1 \u5907\u4efd</b>\n\n\u4f7f\u7528 /backup \u4e0b\u8f7d\u6570\u636e\u5e93\u5907\u4efd'
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f519 \u8fd4\u56de\u4e3b\u83dc\u5355', callback_data='menu_main')
    ]])
    await _edit_or_send(update, text, kb)

async def handle_operator_action(update, context, db):
    """Handle operator management actions."""
    await update.callback_query.answer("请使用按钮操作", show_alert=True)

async def handle_activity_action(update, context, db):
    """Handle activity deletion with confirmation."""
    query = update.callback_query
    data = query.data
    if data.startswith('act_del_'):
        aid = int(data.replace('act_del_', ''))
        confirm_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton('\u2705 \u786e\u8ba4\u5220\u9664', callback_data='act_confirm_del_' + str(aid)),
            InlineKeyboardButton('\u274c \u53d6\u6d88', callback_data='menu_activities')
        ]])
        await query.edit_message_text(
            '\u26a0\ufe0f <b>\u786e\u8ba4\u5220\u9664\u6d3b\u52a8 #' + str(aid) + '\uff1f</b>\\n\\n\u5220\u9664\u540e\u6240\u6709\u53c2\u4e0e\u8bb0\u5f55\u3001\u5956\u54c1\u548c\u5f00\u5956\u6570\u636e\u5c06\u6c38\u4e45\u4e22\u5931\uff0c\u4e0d\u53ef\u6062\u590d\uff01',
            parse_mode='HTML',
            reply_markup=confirm_kb
        )
    elif data.startswith('act_confirm_del_'):
        aid = int(data.replace('act_confirm_del_', ''))
        ok = await db.delete_activity(aid)
        if ok:
            await query.answer('\u2705 \u6d3b\u52a8 #' + str(aid) + ' \u5df2\u6c38\u4e45\u5220\u9664', show_alert=True)
        else:
            await query.answer('\u274c \u5220\u9664\u5931\u8d25', show_alert=True)
        await show_activities_menu(update, context, db)
    else:
        await query.answer('\u5f85\u5b9e\u73b0', show_alert=True)
