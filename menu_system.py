# Menu system for Raffle Bot
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    return 'cjyhq_bot'  # Final fallback only


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
    text = (
        '<b>    馃幇 鎶藉绠＄悊绯荤粺</b>\n'
        '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n\n'
        '<b>馃搳 鏁版嵁姒傝</b>\n'
        '鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹怽n' +
        f'鈹?馃煝 杩涜涓?  <b>{running:>4}</b> 鈹俓n' +
        f'鈹?馃弳 濂栧搧姹?  <b>{pool:>4}</b> 鈹俓n' +
        f'鈹?鉁?宸插畬鎴?  <b>{s["completed_activities"]:>4}</b> 鈹俓n' +
        f'鈹?馃懃 鎬诲弬涓?  <b>{s["total_participants"]:>4}</b> 鈹俓n' +
        '鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
    )
    keyboard = [
        [InlineKeyboardButton('馃帀 鍒涘缓娲诲姩', callback_data='menu_create'),
         InlineKeyboardButton('馃搵 娲诲姩鍒楄〃', callback_data='menu_activities')],
        [InlineKeyboardButton('馃弳 濂栧搧绠＄悊', callback_data='menu_prizes'),
         InlineKeyboardButton('馃搳 鏁版嵁缁熻', callback_data='menu_stats')],
        [InlineKeyboardButton('馃懃 鎿嶄綔鍛樼鐞?, callback_data='menu_operators'),
         InlineKeyboardButton('馃捑 澶囦唤', callback_data='menu_backup')],
    ]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_activity_menu(update: Update, context, db):
    text = (
        '<b>馃搵 娲诲姩鍒楄〃</b>\n'
        '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n'
        '閫夋嫨瑕佹煡鐪嬬殑娲诲姩绫诲瀷锛?
    )
    keyboard = [
        [InlineKeyboardButton('馃煝 杩涜涓?, callback_data='act_list_active'),
         InlineKeyboardButton('馃敶 宸插彇娑?, callback_data='act_list_cancelled')],
        [InlineKeyboardButton('鉁?宸插畬鎴?, callback_data='act_list_completed')],
        [InlineKeyboardButton('馃敊 杩斿洖涓昏彍鍗?, callback_data='menu_main')],
    ]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_prize_menu(update: Update, context, db):
    prizes = await db.list_prizes()
    pool = len(prizes)
    lines = [f"  #{p['id']:>3}  {p['name']}" for p in prizes] if prizes else ['  (绌?']
    prize_text = '\n'.join(lines)
    text = (
        f'<b>馃弳 濂栧搧绠＄悊</b>\n'
        '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n'
        f'濂栧搧姹犲叡 <b>{pool}</b> 涓猏n\n'
        f'{prize_text}\n\n'
        '<b>鎿嶄綔璇存槑锛?/b>\n'
        '/add 濂栧搧鍚? 鈥?娣诲姞\n'
        '/delete 濂栧搧鍚?鈥?鍒犻櫎'
    )
    keyboard = [[InlineKeyboardButton('馃敊 杩斿洖涓昏彍鍗?, callback_data='menu_main')]]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_stats_menu(update: Update, context, db):
    s = await db.get_stats()
    text = (
        '<b>馃搳 鏁版嵁缁熻</b>\n'
        '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n\n' +
        f'馃搶 鎬绘椿鍔ㄦ暟     <b>{s["total_activities"]}</b>\n' +
        f'馃煝 杩涜涓?      <b>{s["active_activities"]}</b>\n' +
        f'鉁?宸插畬鎴?      <b>{s["completed_activities"]}</b>\n' +
        f'馃敶 宸插彇娑?      <b>{s["cancelled_activities"]}</b>\n' +
        f'馃懃 鎬诲弬涓庝汉娆?  <b>{s["total_participants"]}</b>\n' +
        f'馃巵 鎬讳腑濂栦汉娆?  <b>{s["total_winners"]}</b>\n' +
        f'馃弳 濂栧搧姹?      <b>{s["total_prizes"]}</b> 涓?
    )
    keyboard = [[InlineKeyboardButton('馃敊 杩斿洖涓昏彍鍗?, callback_data='menu_main')]]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_activity_list(update: Update, context, db, status: str):
    acts = await db.list_activities_by_status(status)
    labels = {'active': '馃煝 杩涜涓殑娲诲姩', 'cancelled': '馃敶 宸插彇娑堢殑娲诲姩', 'completed': '鉁?宸插畬鎴愮殑娲诲姩'}
    if not acts:
        text = f'<b>{labels.get(status, status)}</b>\n\n馃摥 鏆傛棤鏁版嵁銆?
        keyboard = [[InlineKeyboardButton('馃敊 杩斿洖娲诲姩鍒楄〃', callback_data='menu_activities')]]
        await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))
        return
    text = f'<b>{labels.get(status, status)}</b>\n鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n'
    keyboard = []
    activity_ids = [a['id'] for a in acts]
    counts = await db.get_participant_counts_bulk(activity_ids)
    for a in acts:
        aid = a['id']
        cnt = counts.get(aid, 0)
        draw_label = '鈴版寜鏃? if a['draw_type'] == 1 else '馃懃婊′汉'
        icon = {'active':'馃煝','cancelled':'馃敶','completed':'鉁?}.get(a['status'],'')
        text += f"\n{icon} <b>#{aid}</b> {a['title']}\n   {draw_label} 锝?鍙備笌 <b>{cnt}</b> 浜篭n"
        row = [InlineKeyboardButton(f'馃搵 #{aid} 璇︽儏', callback_data=f'act_detail_{aid}')]
        if status == 'active':
            row.append(InlineKeyboardButton(f'馃懃 #{aid} 鍚嶅崟', callback_data=f'act_parts_{aid}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton('馃敊 杩斿洖娲诲姩鍒楄〃', callback_data='menu_activities')])
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_activity_detail(update: Update, context, db, aid: int):
    a = await db.get_activity(aid)
    if not a:
        if update.callback_query:
            await update.callback_query.answer('娲诲姩涓嶅瓨鍦?, show_alert=True)
        return
    prizes = await db.get_activity_prizes(aid)
    cnt = await db.get_participant_count(aid)
    winners = await db.get_winners(aid) if a['status'] == 'completed' else []
    deeplink = f'https://t.me/{_get_bot_username(update)}?start=join_{aid}'
    deeplink_html = f'<a href="{deeplink}">\U0001f517 鐐瑰嚮鍙備笌鎶藉</a>'
    icon = {'active':'馃煝','cancelled':'馃敶','completed':'鉁?}.get(a['status'],'')
    draw_label = '鈴?鎸夋椂闂村紑濂? if a['draw_type'] == 1 else '馃懃 鎸変汉鏁板紑濂?
    if a['draw_type'] == 1 and a['draw_time']:
        draw_label += f" ({a['draw_time']})"
    elif a['draw_type'] == 2:
        draw_label += f' (婊a["draw_count"]}浜?'
    part_label = f"鍏抽敭璇嶈Е鍙?({a['keyword']})" if a['participation_type'] == 1 else '绉佽亰鍙備笌'
    ch_list = [ch.strip() for ch in a['channel_id'].split('\n') if ch.strip()] if a['channel_id'] else []
    ch_sub_links = '\n'.join([f'  \U0001f517 <a href="{ch}">{html.escape(ch.split("/")[-1] if "/" in ch else ch.replace("https://t.me/","").replace("@",""))}</a>' for ch in ch_list]) if ch_list else (a['promote_link'] or '鈥?)
    sub_note = '\n  锛堣闃呭悗鎵嶅彲浠ュ弬涓庢娊濂栵級' if (ch_list or a['promote_link']) else ''
    prize_lines = '\n'.join([f"  馃巵 {html.escape(p['prize_name'])}脳{p['winner_count']}" for p in prizes]) or '  (鏃?'
    text = (
        f'<b>馃搵 娲诲姩璇︽儏 #{aid}</b>\n'
        '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n\n' +
        f"<b>鏍囬锛?/b>{html.escape(a['title'])}\n" +
        f"<b>鐘舵€侊細</b>{icon} {a['status']}\n" +
        f"<b>璇存槑锛?/b>{a['description'] or '鈥?}\n\n" +
        f"<b>\U0001f517 鍙備笌鏉′欢锛?/b>\n{ch_sub_links}{sub_note}\n\n" +
        f'<b>鈴?寮€濂栵細</b>{draw_label}\n\n' +
        f'<b>馃巵 濂栧搧锛?/b>\n{prize_lines}\n\n' +
        f'<b>\U0001f517 鍙備笌锛?/b>\n{deeplink_html}'
    )
    if winners:
        w_lines = '\n'.join([f"  {i+1}. {html.escape(w['prize_name'])} 鈫?{html.escape(w['first_name'] or str(w['user_id']))}" for i,w in enumerate(winners)])
        text += f'\n\n<b>馃帀 涓鍚嶅崟锛?/b>\n{w_lines}'
    keyboard = []
    deeplink = f'https://t.me/{_get_bot_username(update)}?start=join_{aid}'
    keyboard.append([InlineKeyboardButton('馃摛 鍒嗕韩閾炬帴', callback_data=f'act_share_{aid}'),
                     InlineKeyboardButton('馃摜 CSV瀵煎嚭', callback_data=f'act_export_{aid}')])
    if a['status'] == 'active':
        keyboard.append([
            InlineKeyboardButton('馃幇 鎵嬪姩寮€濂?, callback_data=f'act_open_{aid}'),
            InlineKeyboardButton('馃敶 鍏抽棴娲诲姩', callback_data=f'act_close_{aid}')])
        keyboard.append([InlineKeyboardButton('馃懃 鏌ョ湅鍙備笌鑰?, callback_data=f'act_parts_{aid}')])
    keyboard.append([InlineKeyboardButton('馃敊 杩斿洖娲诲姩鍒楄〃', callback_data='menu_activities')])
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))
    # Media is shown via /link or share button

async def show_participants_list(update: Update, context, db, aid: int):
    parts = await db.get_participants(aid)
    if not parts:
        text = f'<b>馃搵 娲诲姩 #{aid} 鍙備笌鑰?/b>\n\n馃摥 鏆傛棤鍙備笌鑰呫€?
    else:
        lines = [f'<b>馃搵 娲诲姩 #{aid} 鍙備笌鑰咃紙{len(parts)}浜猴級</b>\n']
        for i, p in enumerate(parts, 1):
            name = html.escape(p['first_name'] or f"User{p['user_id']}")
            uname = f" @{html.escape(p['username'])}" if p['username'] else ''
            lines.append(f'  {i}. {name}{uname}  <code>{p["user_id"]}</code>')
        text = '\n'.join(lines)
    keyboard = [
        [InlineKeyboardButton('馃搵 杩斿洖娲诲姩璇︽儏', callback_data=f'act_detail_{aid}')],
        [InlineKeyboardButton('馃敊 杩斿洖娲诲姩鍒楄〃', callback_data='menu_activities')]]
    await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))

async def show_operator_menu(update: Update, context, db):
    try:
        ops = await db.list_operators()
        op_ids = {o['user_id'] for o in ops}
        if ops:
            lines = [f"  鈥?<code>{o['user_id']}</code>" for o in ops]
        else:
            lines = ['  (绌?']
        text = (
            '<b>馃懃 鎿嶄綔鍛樼鐞?/b>\n'
            '鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n\n'
            f'<b>褰撳墠鎿嶄綔鍛橈細</b>\n' + '\n'.join(lines) + '\n\n'
            '<b>娣诲姞鎿嶄綔鍛橈細</b>\n'
            '鐐瑰嚮涓嬫柟鎸夐挳锛岀劧鍚庤浆鍙戠洰鏍囩敤鎴风殑涓€鏉℃秷鎭嵆鍙?
        )
        keyboard = [
            [InlineKeyboardButton('鉃?娣诲姞鎿嶄綔鍛?, callback_data='op_add_start')],
            [InlineKeyboardButton('馃摠 鐢熸垚閭€璇烽摼鎺?, callback_data='op_invite_link')],
        ]
        # Add remove buttons for each operator
        for o in ops:
            keyboard.append([InlineKeyboardButton(f'鉃?绉婚櫎 {o["user_id"]}', callback_data=f'op_remove_{o["user_id"]}')])
        keyboard.append([InlineKeyboardButton('馃敊 杩斿洖涓昏彍鍗?, callback_data='menu_main')])
        await _edit_or_send(update, text, InlineKeyboardMarkup(keyboard))
    except Exception as e:
        if update.callback_query:
            await update.callback_query.answer(f'Error: {e}', show_alert=True)
        else:
            await update.message.reply_text(f'Error: {e}')

async def menu_router(update: Update, context, db):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    if data == 'menu_main':
        await show_main_menu(update, context, db)
    elif data == 'menu_activities':
        await show_activity_menu(update, context, db)
    elif data == 'menu_prizes':
        await show_prize_menu(update, context, db)
    elif data == 'menu_stats':
        await show_stats_menu(update, context, db)
    elif data == 'op_add_start':
        context.user_data['_waiting_op_add'] = True
        await query.answer('馃摠 璇疯浆鍙戠洰鏍囩敤鎴风殑涓€鏉℃秷鎭?, show_alert=True)
        await query.edit_message_text(
            '<b>馃懃 娣诲姞鎿嶄綔鍛?/b>\n\n璇疯浆鍙戠洰鏍囩敤鎴风殑涓€鏉℃秷鎭紝鎴栧彂閫?@鐢ㄦ埛鍚?,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('馃敊 杩斿洖', callback_data='menu_operators')]])
        )
    elif data.startswith('op_remove_'):
        try:
            uid = int(data.replace('op_remove_', ''))
        except ValueError:
            await query.answer('Invalid', show_alert=True)
            return
        ok = await db.remove_operator(uid)
        await query.answer('鉁?宸茬Щ闄? if ok else '鈿狅笍 澶辫触', show_alert=True)
        if ok:
            await show_operator_menu(update, context, db)

    elif data == 'op_invite_link':
        bot_username = _get_bot_username(update)
        code = uuid.uuid4().hex[:10]
        await db.set_setting(f'opreg_{code}', '1')
        link = f'https://t.me/{bot_username}?start=opreg_{code}'
        await query.answer('鉁?閾炬帴宸茬敓鎴愶紒')
        await query.edit_message_text(
            f'<b>馃摠 鎿嶄綔鍛橀個璇烽摼鎺?/b>\n\n<code>{link}</code>\n\n灏嗛摼鎺ュ彂缁欑洰鏍囩敤鎴凤紝鐐瑰嚮鍗冲彲鎴愪负鎿嶄綔鍛樸€俓n閾炬帴涓€娆℃€ф湁鏁堛€?,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('馃敊 杩斿洖', callback_data='menu_operators')]])
        )
    elif data == 'menu_operators':
        context.user_data.pop('_waiting_op_add', None)
        try:
            await show_operator_menu(update, context, db)
        except Exception as e:
            await query.answer(f'Error: {e}', show_alert=True)
    elif data == 'menu_backup':
        await query.answer('馃捑 澶囦唤涓?..')
        path = await db.backup_database()
        await query.message.reply_document(open(path, 'rb'), filename='raffle_backup.db', caption='馃捑 鏁版嵁搴撳浠?)
    elif data.startswith('act_list_'):
        await show_activity_list(update, context, db, data.replace('act_list_', ''))
    elif data.startswith('act_detail_'):
        try:
            aid = int(data.replace('act_detail_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        await show_activity_detail(update, context, db, aid)
    elif data.startswith('act_parts_'):
        try:
            aid = int(data.replace('act_parts_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        await show_participants_list(update, context, db, aid)
    elif data.startswith('act_open_'):
        try:
            aid = int(data.replace('act_open_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        a = await db.get_activity(aid)
        if not a: await query.answer('娲诲姩涓嶅瓨鍦?, show_alert=True); return
        if a['status'] != 'active': await query.answer('鏃犳硶寮€濂?, show_alert=True); return
        await query.answer('馃幇 姝ｅ湪寮€濂?..')
        winners = await db.draw_winners(aid)
        if not winners:
            await query.edit_message_text(f'<b>鈿狅笍 娲诲姩 #{aid}</b>\n\n娌℃湁鍙備笌鑰咃紝鏃犳硶寮€濂栥€?, parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('馃敊 杩斿洖', callback_data='menu_activities')]]))
            return
        lines = [f'<b>馃帀 娲诲姩 #{aid} 寮€濂栫粨鏋?/b>\n鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹乗n']
        for i,w in enumerate(winners,1):
            name = html.escape(w['first_name'] or f"User{w['user_id']}")
            uname = f" @{html.escape(w['username'])}" if html.escape(w['username']) else ''
            lines.append(f"  {i}. {w['prize_name']} 鈫?{name}{uname}")
        r = '\n'.join(lines)
        kb = [[InlineKeyboardButton('馃搵 鏌ョ湅璇︽儏', callback_data=f'act_detail_{aid}')],
              [InlineKeyboardButton('馃敊 杩斿洖', callback_data='menu_activities')]]
        await query.edit_message_text(r, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith('act_export_'):
        try:
            aid = int(data.replace('act_export_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        csv_data = await db.export_participants_csv(aid)
        if csv_data is None:
            await query.answer('娲诲姩涓嶅瓨鍦?, show_alert=True)
            return
        import io
        buf = io.BytesIO(csv_data.encode('utf-8-sig'))
        buf.name = f'activity_{aid}_participants.csv'
        await query.answer('馃摜 宸插鍑?)
        await query.message.reply_document(buf, filename=buf.name, caption=f'馃摜 娲诲姩 #{aid} 鍙備笌鑰呭垪琛?)

    elif data.startswith('act_share_'):
        try:
            aid = int(data.replace('act_share_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        a = await db.get_activity(aid)
        if not a:
            await query.answer('娲诲姩涓嶅瓨鍦?, show_alert=True)
            return
        deeplink = f'https://t.me/{_get_bot_username(update)}?start=join_{aid}'
        deeplink_html = f'<a href="{deeplink}">\U0001f517 鐐瑰嚮鍙備笌</a>'
        prizes = await db.get_activity_prizes(aid)
        prize_str = '\n'.join([f'馃巵 {html.escape(p["prize_name"])}脳{p["winner_count"]}' for p in prizes]) if prizes else '鏆傛棤'
        share_text = (
            f'馃帀 <b>{a["title"]}</b>\n\n'
            f'{a.get("description", "") or ""}\n\n'
            f'<b>馃巵 濂栧搧锛?/b>\n{prize_str}\n\n'
            f'\U0001f517 <b>鍙備笌锛?/b>\n{deeplink_html}\n\n'
            '鐐瑰嚮涓婃柟閾炬帴鍗冲彲鍙備笌锛?
        )
        await query.answer('鉁?宸茬敓鎴愬垎浜摼鎺?)
        # Send the share text as a new message (user can forward it)
        await query.message.reply_text(share_text, parse_mode='HTML', disable_web_page_preview=True)

    elif data.startswith('act_close_'):
        try:
            aid = int(data.replace('act_close_', ''))
        except ValueError:
            await query.answer('Invalid ID', show_alert=True)
            return
        a = await db.get_activity(aid)
        if not a or a['status'] != 'active': await query.answer('鏃犳硶鍏抽棴', show_alert=True); return
        await db.update_activity_status(aid, 'cancelled')
        await query.answer('馃敶 宸插叧闂?)
        await show_activity_detail(update, context, db, aid)
