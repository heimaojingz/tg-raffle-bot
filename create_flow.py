# Create flow state machine - smart button-driven with minimal typing

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import ContextTypes

import logging

import re

import html

from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class Step:

    TITLE = 'title'

    DESCRIPTION = 'description'

    CONTACT = 'contact'

    PROMOTE_LINK = 'promote_link'

    DRAW_TYPE = 'draw_type'

    DRAW_TIME = 'draw_time'

    DRAW_COUNT = 'draw_count'

    ADD_PRIZE = 'add_prize'

    PRIZE_COUNT = 'prize_count'

    PART_TYPE = 'part_type'

    KEYWORD = 'keyword'

    CHANNEL = 'channel'

    MEDIA = 'media'

    CONFIRM = 'confirm'


def _kb(buttons):

    return InlineKeyboardMarkup(buttons)


cancel_btn = [InlineKeyboardButton('❌ 取消', callback_data='create_cancel_btn')]


def skip_btn(cb):

    return [InlineKeyboardButton('▶ 跳过', callback_data=cb)]


def _get_bot_username(update, context=None):

    try:

        bot = update.get_bot()

        if bot and bot.username:

            return bot.username

    except Exception:

        pass

    try:

        if context and hasattr(context, 'bot') and context.bot and context.bot.username:

            return context.bot.username

    except Exception:

        pass

    return ''


def _clean_channel_link(link: str) -> str:

    link = link.strip()

    if link.startswith("https://t.me/") or link.startswith("http://t.me/"):

        return link

    if link.startswith("@"):

        return "https://t.me/" + link[1:]

    if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{3,30}$", link):

        return "https://t.me/" + link

    if re.match(r"^\+[a-zA-Z0-9_-]+$", link):

        return "https://t.me/" + link

    return link


flow_back_btn = [InlineKeyboardButton('\U0001f519 上一步', callback_data='create_back')]


def _step_text(num, total=10, label=""):

    base = '<b>\U0001f4dd 第{}/{} 步'.format(num, total)

    if label:

        base += ' — ' + label

    return base + '</b>'


async def start_create_flow(update, context, db):

    query = update.callback_query

    await query.answer()

    context.user_data.pop('create_data', None)

    context.user_data.pop('create_step', None)

    context.user_data.pop('_prize_name', None)

    context.user_data['create_data'] = {'prizes': [], 'channels': []}

    # Auto-populate default channel if set

    default_ch = await db.get_default_channel()

    if default_ch and default_ch.get('link'):

        context.user_data['create_data']['channels'].append({'name': default_ch['name'], 'link': default_ch['link']})

        logger.info('Auto-populated default channel: ' + default_ch['link'])

    context.user_data['create_step'] = Step.TITLE

    await query.edit_message_text(

        _step_text(1, 10, '标题') + '\n\n请输入抽奖标题：\n例如：天河小羊的出击福利',

        parse_mode='HTML', reply_markup=_kb([cancel_btn])

    )


async def handle_create_text(update, context, db):

    step = context.user_data.get('create_step')

    if not step:

        return False

    user_text = update.message.text.strip()


    if step == Step.TITLE:

        context.user_data['create_data']['title'] = user_text

        context.user_data['create_step'] = Step.MEDIA

        await _show_media_prompt(update, context)

        return True


    elif step == Step.DESCRIPTION:

        context.user_data['create_data']['description'] = user_text

        context.user_data['create_step'] = Step.CONTACT

        title = context.user_data.get('create_data', {}).get('title', '')

        await update.message.reply_text(

            _step_text(4, 10, '联系方式') + '\n🔆 <b>标题：</b>' + (html.escape(title) or '(未设置)') + '\n\n请输入联系方式：',

            parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_contact'), flow_back_btn, cancel_btn])

        )

        return True


    elif step == Step.CONTACT:

        context.user_data['create_data']['contact'] = user_text

        context.user_data['create_step'] = Step.CHANNEL

        await _show_channel_prompt(update, context)

        return True


    elif step == Step.DRAW_TIME:

        from datetime import datetime as dt

        try:

            dt.strptime(user_text, '%Y-%m-%d %H:%M')

        except ValueError:

            await update.message.reply_text('⚠️ 格式错误，请输入 YYYY-MM-DD HH:MM，如 2026-07-05 20:00', parse_mode='HTML', reply_markup=_kb([flow_back_btn, cancel_btn]))

            return True

        context.user_data['create_data']['draw_time'] = user_text

        context.user_data['create_step'] = Step.ADD_PRIZE

        await _show_prize_input(update, context, db, is_new=True)

        return True


    elif step == Step.DRAW_COUNT:

        try:

            context.user_data['create_data']['draw_count'] = int(user_text)

        except ValueError:

            await update.message.reply_text('请输入有效数字：', reply_markup=_kb([flow_back_btn, cancel_btn]))

            return True

        context.user_data['create_step'] = Step.ADD_PRIZE

        await _show_prize_input(update, context, db, is_new=True)

        return True


    elif step == Step.ADD_PRIZE:

        context.user_data['_prize_name'] = user_text

        context.user_data['create_step'] = Step.PRIZE_COUNT

        await update.message.reply_text(

            '奖品「' + html.escape(user_text) + '」的中奖人数：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('1', callback_data='create_pcount_1'),

                 InlineKeyboardButton('3', callback_data='create_pcount_3'),

                 InlineKeyboardButton('5', callback_data='create_pcount_5')],

                [InlineKeyboardButton('8', callback_data='create_pcount_8'),

                 InlineKeyboardButton('10', callback_data='create_pcount_10'),

                 InlineKeyboardButton('✏️ 自定义', callback_data='create_pcount_custom')],

                cancel_btn

            ])

        )

        return True


    elif step == Step.PRIZE_COUNT:

        try:

            count = int(user_text)

        except ValueError:

            await update.message.reply_text('请输入有效数字：', reply_markup=_kb([flow_back_btn, cancel_btn]))

            return True

        await _add_prize_done(update, context, count)

        return True


    elif step == Step.KEYWORD:

        context.user_data['create_data']['keyword'] = user_text

        await _show_confirm(update, context, db)

        return True


    elif step == Step.MEDIA:

        if user_text.lower() == '/skip':

            context.user_data['create_step'] = Step.DESCRIPTION

            title = context.user_data.get('create_data', {}).get('title', '')

            await update.message.reply_text(

                _step_text(3, 10, '说明') + '\n🔆 <b>标题：</b>' + (html.escape(title) or '(未设置)') + '\n\n请输入抽奖说明：',

                parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_desc'), flow_back_btn, cancel_btn])

            )

            return True

        title = context.user_data.get('create_data', {}).get('title', '')

        await update.message.reply_text(

            _step_text(2, 10, '媒体') + '\n🔆 <b>标题：</b>' + (html.escape(title) or '(未设置)') + '\n\n请发送图片或视频，或点击跳过',

            parse_mode='HTML',

            reply_markup=_kb([skip_btn('create_skip_media'), flow_back_btn, cancel_btn])

        )

        return True


    elif step == Step.CHANNEL:

        if '|' in user_text:

            parts = user_text.rsplit('|', 1)

            name = parts[0].strip() or None

            link = _clean_channel_link(parts[1].strip())

            if not name:
                resolved = await _resolve_channel_name(update, link)
                if resolved:
                    name = resolved

        else:

            name = None

            link = _clean_channel_link(user_text)

            resolved = await _resolve_channel_name(update, link)
            if resolved:
                name = resolved

        context.user_data['create_data']['channels'].append({'name': name, 'link': link})

        display_name = name or link
        display = '<a href="' + link + '">' + html.escape(display_name) + '</a>'

        await update.message.reply_text('✅ 已添加频道：' + display, parse_mode='HTML')

        await _show_channel_loop(update, context)

        return True


    return False


def _extract_username_from_link(link: str) -> str:
    """Extract @username from a channel link for getChat API"""
    link = link.strip()
    if link.startswith("https://t.me/") or link.startswith("http://t.me/"):
        path = link.split(".me/", 1)[1] if ".me/" in link else ""
        if path and not path.startswith("+") and not path.startswith("join_"):
            return "@" + path.split("/")[0].split("?")[0]
    if link.startswith("@"):
        return link
    return None


async def _resolve_channel_name(update, link: str) -> str:
    """Try to resolve channel display name via bot.get_chat()"""
    username = _extract_username_from_link(link)
    if not username:
        return None
    try:
        bot = update.get_bot()
        chat = await bot.get_chat(username)
        if chat and chat.title:
            logger.info('Resolved channel: ' + chat.title + ' from ' + username)
            return chat.title
    except Exception as e:
        logger.warning('Failed to resolve channel ' + username + ': ' + str(e))
    return None


async def _resolve_chat_id(bot, link: str) -> str:
    """Resolve a channel link to a chat_id usable by send_message.

    Returns '' if unresolvable (caller should skip).
    """
    link = link.strip()
    if link.startswith('https://t.me/+'):
        # Private invite link — resolve via get_chat.
        try:
            chat = await bot.get_chat(link)
            return str(chat.id)
        except Exception as e:
            logger.warning('Failed to resolve private link: ' + str(e))
            return ''  # Cannot resolve
    elif link.startswith('https://t.me/') or link.startswith('http://t.me/'):
        # Public link → @username format
        return '@' + link.rstrip('/').split('/')[-1].split('?')[0]
    elif link.startswith('@'):
        return link
    return ''


async def _add_prize_done(update, context, count):

    name = context.user_data.pop('_prize_name', None)

    if not name:

        return

    context.user_data['create_data']['prizes'].append({'name': name, 'count': count})

    current = context.user_data['create_data']['prizes']

    lines = '\n'.join(['  \U0001f381 ' + html.escape(p['name']) + ' × ' + str(p['count']) + '人' for p in current])

    msg = '✅ 已添加「' + html.escape(name) + '」✅' + str(count) + '人\n\n当前奖品：\n' + lines + '\n\n继续添加或点击完成？'

    kb = _kb([

        [InlineKeyboardButton('➡ 继续添加', callback_data='create_add_more'),

         InlineKeyboardButton('✅ 完成', callback_data='create_done_prizes')],

        cancel_btn

    ])

    if update.callback_query:

        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=kb)

    else:

        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=kb)


async def _show_channel_prompt(update, context):

    msg = _step_text(5, 10, '频道订阅') + '\n请输入频道链接或用户名（订阅后才可参与）：\n\n支持以下格式：\n1. 频道用户名：@channel_username\n2. 公开链接：https://t.me/channel_username\n3. 邀请链接：https://t.me/+xxxxxx\n4. 名称|链接：我的频道|https://t.me/+xxxxxx\n\n✨ 输入 @用户名 或 t.me/链接 会自动获取频道名称'

    kb = _kb([skip_btn('create_skip_link'), flow_back_btn, cancel_btn])

    if update.callback_query:

        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=kb)

    else:

        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=kb)


async def _show_channel_loop(update, context):

    chs = context.user_data['create_data']['channels']

    lines = '\n'.join(['  \U0001f517 <a href="' + ch['link'] + '">' + (html.escape(ch.get('name', '') or ch['link'])) + '</a>' for ch in chs]) if chs else '  （暂无）'

    context.user_data['create_step'] = Step.CHANNEL

    msg = '当前频道：\n' + lines + '\n\n继续添加或点击完成？'

    kb = _kb([

        [InlineKeyboardButton('➡ 继续添加', callback_data='create_add_channel'),

         InlineKeyboardButton('✅ 完成', callback_data='create_done_channels')],

        cancel_btn

    ])

    if update.callback_query:

        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=kb, disable_web_page_preview=True)

    else:

        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=kb, disable_web_page_preview=True)


async def _show_prize_input(update, context, db, is_new=True):

    prizes = await db.list_prizes()

    keyboard = []

    if prizes:

        row = []

        for p in prizes:

            row.append(InlineKeyboardButton(p['name'][:12], callback_data='create_prize_' + str(p['id'])))

            if len(row) == 2:

                keyboard.append(row)

                row = []

        if row:

            keyboard.append(row)

    keyboard.append([InlineKeyboardButton('✏️ 自定义输入', callback_data='create_prize_custom')])

    keyboard.append(cancel_btn)

    msg = (_step_text(7, 10, '奖品') + '\n选择奖品或自定义输入：') if is_new else (_step_text(7, 10, '奖品') + '\n继续添加奖品：')

    if update.callback_query:

        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=_kb(keyboard))

    else:

        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=_kb(keyboard))


async def handle_create_callback(update, context, db):

    query = update.callback_query

    data = query.data

    step = context.user_data.get('create_step')


    if data == 'create_cancel_btn':

        context.user_data.pop('create_data', None)

        context.user_data.pop('create_step', None)

        context.user_data.pop('_prize_name', None)

        await query.answer('❌ 已取消')

        from menu_system import show_main_menu

        await show_main_menu(update, context, db)

        return


    if not step:

        return


    if data == 'create_skip_desc':

        await query.answer()

        context.user_data['create_step'] = Step.CONTACT

        await query.edit_message_text(

            _step_text(4, 10, '联系方式') + '\n请输入联系方式：',

            parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_contact'), cancel_btn])

        )

    elif data == 'create_skip_contact':

        await query.answer()

        context.user_data['create_step'] = Step.CHANNEL

        await _show_channel_prompt(update, context)

    elif data == 'create_skip_link':

        await query.answer()

        context.user_data['create_step'] = Step.DRAW_TYPE

        await query.edit_message_text(

            _step_text(6, 10, '开奖方式') + '\n请选择开奖方式：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('⏰ 按时间开奖', callback_data='create_draw_time_btn'),

                 InlineKeyboardButton('\U0001f465 按人数开奖', callback_data='create_draw_count_btn')],

                cancel_btn

            ])

        )


    elif data == 'create_draw_time_btn':

        await query.answer()

        context.user_data['create_data']['draw_type'] = 1

        context.user_data['create_step'] = Step.DRAW_TIME

        now = datetime.now()

        t1 = now + timedelta(hours=1)

        t2 = now.replace(hour=20, minute=0, second=0)

        if t2 < now:

            t2 += timedelta(days=1)

        t3 = (now + timedelta(days=1)).replace(hour=20, minute=0, second=0)

        await query.edit_message_text(

            _step_text(6, 10, '开奖时间') + '\n选择开奖时间：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('⏰ 1小时后(' + t1.strftime('%H:%M') + ')', callback_data='create_time_' + t1.strftime('%Y-%m-%d %H:%M'))],

                [InlineKeyboardButton('\U0001f319 今晚 20:00', callback_data='create_time_' + t2.strftime('%Y-%m-%d 20:00'))],

                [InlineKeyboardButton('\U0001f4c5 明天 20:00', callback_data='create_time_' + t3.strftime('%Y-%m-%d 20:00'))],

                [InlineKeyboardButton('✏️ 自定义时间', callback_data='create_time_custom')],

                flow_back_btn, cancel_btn

            ])

        )

    elif data == 'create_time_custom':

        await query.answer()

        context.user_data['create_step'] = Step.DRAW_TIME

        await query.edit_message_text(

            _step_text(6, 10, '开奖时间') + '\n请输入开奖时间：\n格式：YYYY-MM-DD HH:MM\n如 2026-07-05 20:00',

            parse_mode='HTML', reply_markup=_kb([flow_back_btn, cancel_btn])

        )

    elif data.startswith('create_time_'):

        await query.answer()

        time_str = data[len('create_time_'):]

        context.user_data['create_data']['draw_time'] = time_str

        context.user_data['create_step'] = Step.ADD_PRIZE

        await _show_prize_input(update, context, db, is_new=True)


    elif data == 'create_draw_count_btn':

        await query.answer()

        context.user_data['create_data']['draw_type'] = 2

        context.user_data['create_step'] = Step.DRAW_COUNT

        await query.edit_message_text(

            _step_text(6, 10, '开奖人数') + '\n选择开奖人数：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('50', callback_data='create_dcount_50'),

                 InlineKeyboardButton('100', callback_data='create_dcount_100'),

                 InlineKeyboardButton('200', callback_data='create_dcount_200')],

                [InlineKeyboardButton('500', callback_data='create_dcount_500'),

                 InlineKeyboardButton('✏️ 自定义', callback_data='create_dcount_custom')],

                cancel_btn

            ])

        )

    elif data.startswith('create_dcount_'):

        await query.answer()

        if data == 'create_dcount_custom':

            context.user_data['create_step'] = Step.DRAW_COUNT

            await query.edit_message_text(_step_text(6, 10, '开奖人数') + '\n请输入开奖人数：\n例如：100', parse_mode='HTML', reply_markup=_kb([cancel_btn]))

        else:

            count = int(data.replace('create_dcount_', ''))

            context.user_data['create_data']['draw_count'] = count

            context.user_data['create_step'] = Step.ADD_PRIZE

            await _show_prize_input(update, context, db, is_new=True)


    elif data.startswith('create_prize_') and data != 'create_prize_custom':

        await query.answer()

        prize_id = int(data.replace('create_prize_', ''))

        prizes = await db.list_prizes()

        prize_name = None

        for p in prizes:

            if p['id'] == prize_id:

                prize_name = html.escape(p['name'])

                break

        if prize_name:

            context.user_data['_prize_name'] = prize_name

            context.user_data['create_step'] = Step.PRIZE_COUNT

            await query.edit_message_text(

                '奖品「' + html.escape(prize_name) + '」的中奖人数：',

                parse_mode='HTML', reply_markup=_kb([

                    [InlineKeyboardButton('1', callback_data='create_pcount_1'),

                     InlineKeyboardButton('3', callback_data='create_pcount_3'),

                     InlineKeyboardButton('5', callback_data='create_pcount_5')],

                    [InlineKeyboardButton('8', callback_data='create_pcount_8'),

                     InlineKeyboardButton('10', callback_data='create_pcount_10'),

                     InlineKeyboardButton('✏️ 自定义', callback_data='create_pcount_custom')],

                    cancel_btn

                ])

            )

    elif data == 'create_prize_custom':

        await query.answer()

        context.user_data['create_step'] = Step.ADD_PRIZE

        await query.edit_message_text(_step_text(7, 10, '奖品') + '\n请输入商品名称：\n例如：100元优惠券包', parse_mode='HTML', reply_markup=_kb([cancel_btn]))


    elif data.startswith('create_pcount_'):

        await query.answer()

        if data == 'create_pcount_custom':

            context.user_data['create_step'] = Step.PRIZE_COUNT

            await query.edit_message_text('奖品「' + html.escape(context.user_data.get('_prize_name', '')) + '」的中奖人数：\n请输入数字：', parse_mode='HTML', reply_markup=_kb([cancel_btn]))

        else:

            count = int(data.replace('create_pcount_', ''))

            await _add_prize_done(update, context, count)


    elif data == 'create_add_more':

        await query.answer()

        context.user_data['create_step'] = Step.ADD_PRIZE

        await _show_prize_input(update, context, db, is_new=True)

    elif data == 'create_done_prizes':

        if not context.user_data['create_data'].get('prizes'):

            await query.answer('至少需要一个奖品', show_alert=True)

            return

        context.user_data['create_step'] = Step.PART_TYPE

        await query.edit_message_text(

            _step_text(9, 10, '参与方式') + '\n请选择参与方式：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('\U0001f4ac 群内关键词触发', callback_data='create_part_keyword'),

                 InlineKeyboardButton('\U0001f4e9 私聊参与', callback_data='create_part_private')],

                cancel_btn

            ])

        )


    elif data == 'create_part_keyword':

        await query.answer()

        context.user_data['create_data']['participation_type'] = 1

        context.user_data['create_step'] = Step.KEYWORD

        await query.edit_message_text(

            _step_text(8, 10, '关键词') + '\n请输入或选择触发关键词：',

            parse_mode='HTML', reply_markup=_kb([

                [InlineKeyboardButton('\U0001f4ac 抽奖', callback_data='create_kw_抽奖'),

                 InlineKeyboardButton('\U0001f4ac 参与', callback_data='create_kw_参与')],

                [InlineKeyboardButton('\U0001f4ac 福利', callback_data='create_kw_福利'),

                 InlineKeyboardButton('\U0001f4ac 上车', callback_data='create_kw_上车')],

                [InlineKeyboardButton('✏️ 自定义关键词', callback_data='create_kw_custom')],

                cancel_btn

            ])

        )

    elif data.startswith('create_kw_'):

        await query.answer()

        if data == 'create_kw_custom':

            await query.edit_message_text(_step_text(8, 10, '关键词') + '\n请输入触发关键词：\n例如：抽奖', parse_mode='HTML', reply_markup=_kb([cancel_btn]))

        else:

            kw = data.replace('create_kw_', '')

            context.user_data['create_data']['keyword'] = kw

            context.user_data['create_step'] = Step.CHANNEL

            await _show_channel_prompt(update, context)

    elif data == 'create_part_private':

        await query.answer()

        context.user_data['create_data']['participation_type'] = 2

        context.user_data['create_data']['keyword'] = ''

        logger.info('create_part_private: calling _show_confirm, data=' + str(context.user_data.get('create_data', {})))

        await _show_confirm(update, context, db)

        logger.info('create_part_private: _show_confirm returned')

    elif data == 'create_part_button':

        await query.answer()

        context.user_data['create_data']['participation_type'] = 3

        context.user_data['create_data']['keyword'] = ''

        await _show_confirm(update, context, db)


    elif data == 'create_add_channel':

        await query.answer()

        context.user_data['create_step'] = Step.CHANNEL

        await query.edit_message_text('继续添加频道：\n可输入 @频道用户名 或链接（自动获取名称）\n格式：名称|链接\n例如：金悦小姐姐|https://t.me/+xxxxxx', parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_channel'), cancel_btn]))

    elif data == 'create_done_channels':

        await query.answer()

        data_dict = context.user_data.get('create_data', {})

        if data_dict.get('draw_type') is not None:

            await _show_confirm(update, context, db)

        else:

            context.user_data['create_step'] = Step.DRAW_TYPE

            await query.edit_message_text(

                _step_text(6, 10, '开奖方式') + '\n请选择开奖方式：',

                parse_mode='HTML', reply_markup=_kb([

                    [InlineKeyboardButton('⏰ 按时间开奖', callback_data='create_draw_time_btn'),

                     InlineKeyboardButton('\U0001f465 按人数开奖', callback_data='create_draw_count_btn')],

                    cancel_btn

                ])

            )

    elif data == 'create_skip_channel':

        await query.answer()

        data_dict = context.user_data.get('create_data', {})

        if data_dict.get('draw_type') is not None:

            await _show_confirm(update, context, db)

        else:

            context.user_data['create_step'] = Step.DRAW_TYPE

            await query.edit_message_text(

                _step_text(6, 10, '开奖方式') + '\n请选择开奖方式：',

                parse_mode='HTML', reply_markup=_kb([

                    [InlineKeyboardButton('⏰ 按时间开奖', callback_data='create_draw_time_btn'),

                     InlineKeyboardButton('\U0001f465 按人数开奖', callback_data='create_draw_count_btn')],

                    cancel_btn

                ])

            )


    elif data == 'create_skip_media':

        await query.answer()

        context.user_data['create_step'] = Step.DESCRIPTION

        await query.edit_message_text(

            _step_text(3, 10, '说明') + '\n请输入抽奖说明：',

            parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_desc'), flow_back_btn, cancel_btn])

        )


    elif data == 'create_back':

        await query.answer()

        step = context.user_data.get('create_step')

        data_dict = context.user_data.get('create_data', {})

        contactedisp = '\n\n当前联系方式：' + html.escape(contacted) + '\n\n请输入新联系方式（或直接发送覆盖）：'

        describedisp = '\n\n当前说明：' + html.escape(described) + '\n\n请输入新说明（或直接发送覆盖）：'

        titledisp = '\n\n当前标题：' + html.escape(titled) + '\n\n请输入新标题（或直接发送覆盖）：'

        contacted = data_dict.get('contact', '')

        described = data_dict.get('description', '')

        titled = data_dict.get('title', '')

        draw_type = data_dict.get('draw_type', 1)

        back_map = {

            Step.DESCRIPTION: Step.MEDIA,

            Step.CONTACT: Step.DESCRIPTION,

            Step.PROMOTE_LINK: Step.CONTACT,

            Step.DRAW_TYPE: Step.CHANNEL if data_dict.get('draw_type') is None else Step.PROMOTE_LINK,

            Step.DRAW_TIME: Step.DRAW_TYPE,

            Step.DRAW_COUNT: Step.DRAW_TYPE,

            Step.ADD_PRIZE: Step.DRAW_TIME if draw_type == 1 else Step.DRAW_COUNT,

            Step.PART_TYPE: Step.ADD_PRIZE,

            Step.KEYWORD: Step.PART_TYPE,

            Step.CHANNEL: Step.CONTACT if data_dict.get('draw_type') is None else Step.KEYWORD,

            Step.MEDIA: Step.TITLE,

        }

        prev = back_map.get(step)

        if prev:

            context.user_data['create_step'] = prev

            if prev == Step.TITLE:

                await query.edit_message_text(_step_text(1, 10, '标题') + titledisp, parse_mode='HTML', reply_markup=_kb([cancel_btn]))

            elif prev == Step.MEDIA:

                await _show_media_prompt(update, context)

            elif prev == Step.DESCRIPTION:

                await query.edit_message_text(_step_text(3, 10, '说明') + describedisp, parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_desc'), flow_back_btn, cancel_btn]))

            elif prev == Step.CONTACT:

                await query.edit_message_text(_step_text(4, 10, '联系方式') + contactedisp, parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_contact'), flow_back_btn, cancel_btn]))

            elif prev == Step.PROMOTE_LINK:

                await query.edit_message_text(_step_text(5, 10, '频道订阅') + '\n请输入订阅链接：\n格式：名称|链接\n例如：金悦小姐姐|https://t.me/+xxxxxx', parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_link'), flow_back_btn, cancel_btn]))

            elif prev == Step.DRAW_TYPE:

                await query.edit_message_text(_step_text(6, 10, '开奖方式') + '\n请选择开奖方式：', parse_mode='HTML', reply_markup=_kb([[InlineKeyboardButton('⏰ 按时间开奖', callback_data='create_draw_time_btn'), InlineKeyboardButton('\U0001f465 按人数开奖', callback_data='create_draw_count_btn')], flow_back_btn, cancel_btn]))

            elif prev == Step.DRAW_TIME:

                now = datetime.now(); t1 = now + timedelta(hours=1); t2 = now.replace(hour=20, minute=0, second=0)

                if t2 < now: t2 += timedelta(days=1)

                t3 = (now + timedelta(days=1)).replace(hour=20, minute=0, second=0)

                await query.edit_message_text(_step_text(6, 10, '开奖时间') + '\n选择开奖时间：', parse_mode='HTML', reply_markup=_kb([[InlineKeyboardButton('⏰ 1小时后(' + t1.strftime('%H:%M') + ')', callback_data='create_time_' + t1.strftime('%Y-%m-%d %H:%M'))], [InlineKeyboardButton('\U0001f319 今晚 20:00', callback_data='create_time_' + t2.strftime('%Y-%m-%d 20:00'))], [InlineKeyboardButton('\U0001f4c5 明天 20:00', callback_data='create_time_' + t3.strftime('%Y-%m-%d 20:00'))], [InlineKeyboardButton('✏️ 自定义时间', callback_data='create_time_custom')], flow_back_btn, cancel_btn]))

            elif prev == Step.DRAW_COUNT:

                await query.edit_message_text(_step_text(6, 10, '开奖人数') + '\n选择开奖人数：', parse_mode='HTML', reply_markup=_kb([[InlineKeyboardButton('50', callback_data='create_dcount_50'), InlineKeyboardButton('100', callback_data='create_dcount_100'), InlineKeyboardButton('200', callback_data='create_dcount_200')], [InlineKeyboardButton('500', callback_data='create_dcount_500'), InlineKeyboardButton('✏️ 自定义', callback_data='create_dcount_custom')], flow_back_btn, cancel_btn]))

            elif prev == Step.ADD_PRIZE:

                await _show_prize_input(update, context, db, is_new=False)

            elif prev == Step.PART_TYPE:

                await query.edit_message_text(_step_text(9, 10, '参与方式') + '\n请选择参与方式：', parse_mode='HTML', reply_markup=_kb([[InlineKeyboardButton('\U0001f4ac 群内关键词触发', callback_data='create_part_keyword'), InlineKeyboardButton('\U0001f4e9 私聊参与', callback_data='create_part_private')], flow_back_btn, cancel_btn]))

            elif prev == Step.KEYWORD:

                await query.edit_message_text(_step_text(8, 10, '关键词') + '\n请输入或选择触发关键词：', parse_mode='HTML', reply_markup=_kb([[InlineKeyboardButton('\U0001f4ac 抽奖', callback_data='create_kw_抽奖'), InlineKeyboardButton('\U0001f4ac 参与', callback_data='create_kw_参与')], [InlineKeyboardButton('\U0001f4ac 福利', callback_data='create_kw_福利'), InlineKeyboardButton('\U0001f4ac 上车', callback_data='create_kw_上车')], [InlineKeyboardButton('✏️ 自定义关键词', callback_data='create_kw_custom')], flow_back_btn, cancel_btn]))

            elif prev == Step.CHANNEL:

                chs = context.user_data['create_data'].get('channels', [])

                lines = '\n'.join(['  \U0001f517 <a href="' + ch['link'] + '">' + (html.escape(ch['name']) or ch['link']) + '</a>' for ch in chs]) if chs else '  (空)'

                await query.edit_message_text(_step_text(5, 10, '频道订阅') + '\n当前频道：\n' + lines + '\n\n格式：名称|链接\n例如：金悦小姐姐|https://t.me/+xxxxxx', parse_mode='HTML', reply_markup=_kb([skip_btn('create_skip_channel'), cancel_btn]), disable_web_page_preview=True)

        else:

            await query.answer('无法返回', show_alert=True)


    elif data == 'create_confirm_yes':

        await query.answer('✅ 发布成功！')

        data_dict = context.user_data.get('create_data', {})

        data_dict['channel_id'] = '\n'.join([ch['link'] for ch in data_dict.get('channels', [])])

        data_dict['status'] = 'active'

        activity_id = await db.create_activity(data_dict)

        context.user_data.pop('create_data', None)

        context.user_data.pop('create_step', None)

        bot_username = _get_bot_username(update, context)

        deeplink = 'https://t.me/' + bot_username + '?start=join_' + str(activity_id)


        deeplink_html = '<a href="' + deeplink + '">\U0001f517 点击参与抽奖</a>'

        deeplink_btn = InlineKeyboardButton('\U0001f517 点击参与抽奖', url=deeplink)

        prizes = data_dict.get('prizes', [])

        prize_lines = '\n'.join(['\U0001f4b0 ' + html.escape(p['name']) + ' × ' + str(p['count']) for p in prizes]) if prizes else '暂无'

        ch_list = data_dict.get('channels', [])

        activity_text = db.format_activity_broadcast(

            title=data_dict.get('title', ''),

            description=data_dict.get('description', ''),

            contact=data_dict.get('contact', ''),

            prize_lines=prize_lines,

            draw_type=data_dict.get('draw_type', 1),

            draw_time=data_dict.get('draw_time'),

            draw_count=data_dict.get('draw_count', 0),

            channel_links=ch_list,

            deeplink_html=deeplink_html,

        )

        publish_buttons = [[deeplink_btn]]

        if ch_list:

            for idx, ch in enumerate(ch_list):

                ch_name = html.escape(ch['name']) or ch['link']

                if len(ch_name) > 20:

                    ch_name = ch_name[:20] + '...'

                publish_buttons.append([InlineKeyboardButton('\U0001f4e4 发布到' + ch_name, callback_data='pub_' + str(activity_id) + '_' + str(idx))])

        publish_buttons.append([InlineKeyboardButton('\U0001f519 返回主菜单', callback_data='menu_main')])

        await query.edit_message_text('<b>✅ 活动 #' + str(activity_id) + ' 已创建！</b>\n\n' + activity_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(publish_buttons), disable_web_page_preview=True)

        # Auto-publish to default channel
        default_ch_setting = await db.get_default_channel()
        if default_ch_setting and default_ch_setting.get('link'):
            default_link = default_ch_setting['link'].strip()
            for idx, ch in enumerate(ch_list):
                ch_link = ch['link'].strip()
                if ch_link == default_link:
                    bot = update.get_bot()
                    chat_id = await _resolve_chat_id(bot, ch_link)
                    if not chat_id:
                        logger.warning(f'Auto-publish: cannot resolve chat_id for {ch_link}')
                        continue
                    bot_username = _get_bot_username(update, context)
                    auto_deeplink = 'https://t.me/' + bot_username + '?start=join_' + str(activity_id)
                    auto_btn = InlineKeyboardButton('\U0001f517 点击参与抽奖', url=auto_deeplink)
                    auto_kb = InlineKeyboardMarkup([[auto_btn]])
                    try:
                        if data_dict.get('media_file_id') and data_dict.get('media_type') == 'photo':
                            await bot.send_photo(chat_id, data_dict['media_file_id'], caption=activity_text, parse_mode='HTML', reply_markup=auto_kb)
                        elif data_dict.get('media_file_id') and data_dict.get('media_type') == 'video':
                            await bot.send_video(chat_id, data_dict['media_file_id'], caption=activity_text, parse_mode='HTML', reply_markup=auto_kb)
                        else:
                            await bot.send_message(chat_id, activity_text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=auto_kb)
                        logger.info('Auto-published activity #' + str(activity_id) + ' to default channel')
                    except Exception as e:
                        logger.error(f'Auto-publish send failed for #{activity_id}: {e}')

        ch_sub_links = '\n'.join(['  \U0001f517 <a href="' + ch['link'] + '">' + (html.escape(ch['name']) or ch['link']) + '</a>' for ch in ch_list]) if ch_list else ''

        sub_note = '\n  （订阅后才可参与抽奖）' if ch_list else ''

        share_text = '<b>✅ 发布成功！用户看到的效果：</b>\n\n\U0001f389 <b>' + data_dict.get('title', '') + '</b>\n\n' + (data_dict.get('description', '') or '') + '\n\n<b>\U0001f4e2 订阅：</b>\n' + ch_sub_links + sub_note + '\n\n<b>\U0001f381 奖品：</b>\n' + prize_lines + '\n\n\U0001f517 <b>参与：</b>\n' + deeplink_html

        media_fid = data_dict.get('media_file_id', '')

        media_type = data_dict.get('media_type', '')

        if media_fid and media_type == 'photo':

            try:

                await query.message.reply_photo(media_fid, caption=share_text, parse_mode='HTML')

            except Exception:

                await query.message.reply_text(share_text, parse_mode='HTML', disable_web_page_preview=True)

        elif media_fid and media_type == 'video':

            try:

                await query.message.reply_video(media_fid, caption=share_text, parse_mode='HTML')

            except Exception:

                await query.message.reply_text(share_text, parse_mode='HTML', disable_web_page_preview=True)

        else:

            await query.message.reply_text(share_text, parse_mode='HTML', disable_web_page_preview=True)


# Publish to specific channel handler


async def handle_publish_callback(update, context, db):

    query = update.callback_query
    data = query.data

    try:
        parts = data.replace("pub_", "").split("_")
        activity_id = int(parts[0])
        ch_index = int(parts[1])

        a = await db.get_activity(activity_id)
        if not a:
            await query.answer("活动不存在", show_alert=True)
            return

        ch_list = [ch.strip() for ch in a["channel_id"].split("\n") if ch.strip()] if a["channel_id"] else []
        if ch_index >= len(ch_list):
            await query.answer("频道不存在", show_alert=True)
            return

        ch = ch_list[ch_index]
        bot = update.get_bot()
        chat_id = await _resolve_chat_id(bot, ch)
        if not chat_id:
            await query.answer("无效的频道链接或无法解析", show_alert=True)
            return

        if chat_id.startswith("@"):
            try:
                bot_member = await bot.get_chat_member(chat_id, bot.id)
                if bot_member.status not in ["administrator", "creator", "member"]:
                    await query.answer("机器人不是 " + chat_id + " 的成员，请先将机器人加入频道并设为管理员", show_alert=True)
                    return
            except Exception:
                await query.answer("无法访问 " + chat_id + "，请确保机器人已在频道中且为管理员", show_alert=True)
                return

        bot_username = _get_bot_username(update, context)
        deeplink = "https://t.me/" + bot_username + "?start=join_" + str(activity_id)
        deeplink_btn = InlineKeyboardButton("\U0001f517 点击参与抽奖", url=deeplink)

        prizes = await db.get_activity_prizes(activity_id)
        prize_lines = "\n".join(["\U0001f4b0 " + html.escape(p["prize_name"]) + " \u00d7 " + str(p["winner_count"]) for p in prizes]) if prizes else "暂无"

        ch_list2 = [ch.strip() for ch in a["channel_id"].split("\n") if ch.strip()] if a["channel_id"] else []
        ch_links = [{"link": ch, "name": None} for ch in ch_list2]

        bcast = db.format_activity_broadcast(
            title=html.escape(a["title"]),
            description=html.escape(a.get("description", "")),
            contact=html.escape(a.get("contact", "")),
            prize_lines=prize_lines,
            draw_type=a["draw_type"],
            draw_time=a.get("draw_time"),
            draw_count=a.get("draw_count", 0),
            channel_links=ch_links,
            deeplink_html="<a href=\" + deeplink + \">\U0001f517 点击参与抽奖</a>",
        )

        reply_kb = InlineKeyboardMarkup([[deeplink_btn]])

        if a.get("media_file_id") and a.get("media_type") == "photo":
            await bot.send_photo(chat_id, a["media_file_id"], caption=bcast, parse_mode="HTML", reply_markup=reply_kb)
        elif a.get("media_file_id") and a.get("media_type") == "video":
            await bot.send_video(chat_id, a["media_file_id"], caption=bcast, parse_mode="HTML", reply_markup=reply_kb)
        else:
            await bot.send_message(chat_id, bcast, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_kb)

        await query.answer("\u2705 \u5df2\u53d1\u5e03\uff01", show_alert=True)

    except Exception as e:
        logger.error(f"publish error: {e}", exc_info=True)
        await query.answer("\u274c \u53d1\u5e03\u5931\u8d25: " + str(e), show_alert=True)

async def _show_confirm(update, context, db):

    text = ''

    try:

        data = context.user_data.get('create_data', {})

        if not data:

            if update.callback_query:

                await update.callback_query.answer('\u26a0\ufe0f 数据丢失，请重新创建活动', show_alert=True)

            return

        context.user_data['create_step'] = Step.CONFIRM

        prizes = data.get('prizes', [])

        channels = data.get('channels', [])

        prize_lines = '\n'.join(['\U0001f4b0 ' + html.escape(p['name']) + ' \u00d7 ' + str(p['count']) + '\u4eba' for p in prizes]) if prizes else '暂无'

        text = '<b>\U0001f4cb \u9884\u89c8 \u2014 \u53d1\u5e03\u540e\u7528\u6237\u770b\u5230\u7684\u6548\u679c\uff1a</b>\n\n' + db.format_activity_broadcast(

            title=html.escape(data.get('title', '')),

            description=html.escape(data.get('description', '')),

            contact=html.escape(data.get('contact', '')),

            prize_lines=prize_lines,

            draw_type=data.get('draw_type', 1),

            draw_time=data.get('draw_time'),

            draw_count=data.get('draw_count', 0),

            channel_links=channels,

            deeplink_html='',

            include_conditions_label=True,

        )

    except Exception as e:

        logger.error('_show_confirm error: ' + str(e), exc_info=True)

        if update.callback_query:

            await update.callback_query.answer('\u26a0\ufe0f \u51fa\u9519\u4e86: ' + str(e), show_alert=True)

        return


    kb = InlineKeyboardMarkup([

        [InlineKeyboardButton('\u2705 \u786e\u8ba4\u53d1\u5e03', callback_data='create_confirm_yes'),

         InlineKeyboardButton('\u274c \u53d6\u6d88', callback_data='create_cancel_btn')]

    ])

    if update.callback_query:

        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=kb, disable_web_page_preview=True)

    else:

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=kb)


async def _show_media_prompt(update, context):

    title = context.user_data.get('create_data', {}).get('title', '')

    msg = (_step_text(2, 10, '媒体')

           + '\n🔆 <b>标题：</b>' + (html.escape(title) or '(未设置)')

           + '\n\n发送一张图片或视频（可选）：')

    kb = _kb([[InlineKeyboardButton('▶ 跳过', callback_data='create_skip_media')], flow_back_btn, cancel_btn])

    if update.callback_query:

        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=kb, disable_web_page_preview=True)


    else:

        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=kb)


