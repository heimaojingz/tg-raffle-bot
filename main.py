# ── Raffle Bot: Telegram 抽奖机器人 ──

import subprocess, sys, os
from dotenv import load_dotenv
load_dotenv()  # Load .env file if present
# Auto-install dependencies if not present
try:
    import telegram
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", os.path.join(os.path.dirname(__file__), "requirements.txt")])
    except Exception:
        pass  # If pip fails, we'll get a proper error at import time
    import telegram

import asyncio
import logging
import shutil
import csv
import io
import os
from datetime import datetime
from collections import defaultdict
import html

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

import database as db
import menu_system as menu
import create_flow

# ── Config ──
BOT_TOKEN = os.getenv("BOT_TOKEN", os.getenv("RAFFLE_BOT_TOKEN"))
if not BOT_TOKEN:
    raise RuntimeError("No BOT_TOKEN or RAFFLE_BOT_TOKEN environment variable set")
# Owner is auto-detected from first /start, stored in database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ?? Owner/Admin tracking ??
ADMIN_IDS = set()  # Populated from DB owner on startup

# Simple in-memory rate limiter: {key: [timestamp, ...]}
_rate_limiter = defaultdict(list)

def _check_rate_limit(key: str, max_count: int = 5, window_seconds: int = 60) -> bool:
    """Returns True if action is allowed, False if rate limited."""
    now = datetime.now().timestamp()
    timestamps = _rate_limiter[key]
    # Remove old entries outside window
    _rate_limiter[key] = [t for t in timestamps if now - t < window_seconds]
    if len(_rate_limiter[key]) >= max_count:
        return False
    _rate_limiter[key].append(now)
    return True

def _get_bot_username(update, context=None) -> str:
    """Get bot username, trying update.bot then context.bot."""
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
    return ''  # No fallback; caller should handle empty

# ═══════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════

def is_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    return uid in ADMIN_IDS

async def is_admin_or_op(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        return True
    is_op = await db.is_operator(uid)
    return is_op

async def admin_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await is_admin_or_op(update):
        if update.callback_query:
            await update.callback_query.answer("⛔ 无权限", show_alert=True)
        elif update.message:
            await update.message.reply_text("⛔ 仅管理员/操作员可用。")
        return False
    return True

async def is_super_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        return True
    return await db.is_owner(uid)

async def _keep_alive(app):
    """Periodic keep-alive ping to prevent Railway from sleeping."""
    await asyncio.sleep(30)
    while True:
        try:
            me = await app.bot.get_me()
            logger.info(f"Keep-alive: @{me.username}")
        except Exception as e:
            logger.warning(f"Keep-alive error: {e}")
        await asyncio.sleep(600)

async def _auto_draw_loop():
    while True:
        await asyncio.sleep(60)
        try:
            acts = await db.list_active_activities()
            now = datetime.now()
            for a in acts:
                if a['draw_type'] == 1 and a['draw_time']:
                    try:
                        try:
                            draw_dt = datetime.strptime(a['draw_time'], '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            draw_dt = datetime.strptime(a['draw_time'], '%Y-%m-%d %H:%M')
                        if draw_dt <= now:
                            await db.draw_winners(a['id'])
                            logger.info(f'Auto-draw: activity #{a["id"]}')
                    except ValueError:
                        # Invalid time format in DB, skip
                        continue
        except Exception as e:
            logger.error(f'Auto-draw: {e}')

async def check_subscription(bot, user_id: int, channel_links: str) -> tuple:
    """Check if user is subscribed to channels. Returns (all_ok, details)."""
    if not channel_links:
        return True, []
    results = []
    all_ok = True
    for link in channel_links.split('\n'):
        link = link.strip()
        if not link:
            continue
        chat_id = None
        if link.startswith('https://t.me/+') or link.startswith('http://t.me/+'):
            # Private invite - can't check, assume OK
            results.append(f'  ⚠️ {link} (无法验证，请手动确认)')
            continue
        if link.startswith('https://t.me/') or link.startswith('http://t.me/'):
            chat_id = '@' + link.rstrip('/').split('/')[-1]
        elif link.startswith('@'):
            chat_id = link
        if chat_id:
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    results.append(f'  ✅ {link}')
                else:
                    results.append(f'  ❌ {link} (未订阅)')
                    all_ok = False
            except Exception:
                results.append(f'  ⚠️ {link} (无法验证)')
    return all_ok, results

def format_activity(a) -> str:
    draw_type_text = "⏰ 按时开奖" if a['draw_type'] == 1 else "👥 按人数开奖"
    st = a['status']
    status_emoji = {"active": "🟢", "cancelled": "🔴", "completed": "✅", "draft": "⚪"}
    return (
        f"{status_emoji.get(st, '')} <b>#{a['id']}</b> {html.escape(a['title'])}\n"
        f"   {draw_type_text} ｜ 状态: {st}\n"
        f"   {a.get('created_at','')}"
    )

# ═══════════════════════════════════════════════
#  /start – 数据概览
# ═══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Auto-set owner on first ever /start
    owner = await db.get_owner_id()
    if owner is None:
        uid = update.effective_user.id
        await db.set_owner_id(uid)
        ADMIN_IDS.add(uid)
        logger.info(f'Owner auto-set: {uid}')
    if await is_admin_or_op(update):
        await menu.show_main_menu(update, context, db)
        return
    acts = await db.list_active_activities()
    if not acts:
        await update.message.reply_text(
            '🎉 <b>抽奖助手</b>\n\n📭 暂无进行中的抽奖活动！',
            parse_mode='HTML'
        )
        return
    bot_username = _get_bot_username(update, context)
    lines = ['🎉 <b>当前抽奖活动</b>\n━━━━━━━━━━━━━━━━━\n']
    for a in acts:
        cnt = await db.get_participant_count(a['id'])
        deeplink = f"https://t.me/{bot_username}?start=join_{a['id']}"
        draw = ''
        if a['draw_type'] == 1 and a['draw_time']:
            draw = f' | ⏰ {html.escape(a["draw_time"])}'
        elif a['draw_type'] == 2:
            draw = f' | 👥 满{a["draw_count"]}人开奖'
        lines.append(f'📌 <b>#{a["id"]} {html.escape(a["title"])}</b>')
        lines.append(f'   👥 {cnt}人参与{draw}')
        lines.append(f'   👉 <a href="{deeplink}">\U0001f517 点击参与</a>')
        lines.append('')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML', disable_web_page_preview=True)

# ═══════════════════════════════════════════════
#  活动管理: /on /cancel /history /event /participants
# ═══════════════════════════════════════════════

async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    await menu.show_activity_list(update, context, db, 'active')


async def cmd_cancel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    await menu.show_activity_list(update, context, db, 'cancelled')


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    await menu.show_activity_list(update, context, db, 'completed')


async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /event <活动ID>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("活动ID必须是数字。")
        return

    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text("❌ 活动不存在。")
        return

    prizes = await db.get_activity_prizes(aid)
    cnt = await db.get_participant_count(a['id'])

    draw_label = "⏰ 按时间开奖" if a['draw_type'] == 1 else "👥 按人数开奖"
    if a['draw_type'] == 1 and a['draw_time']:
        draw_label += f"\n  开奖时间: {html.escape(a['draw_time'])}"
    elif a['draw_type'] == 2:
        draw_label += f"\n  开奖人数: {a['draw_count']}"

    part_label = "关键词触发" if a['participation_type'] == 1 else "私聊参与"
    if a['participation_type'] == 1 and a['keyword']:
        part_label += f" ({html.escape(a['keyword'])})"

    prize_lines = "\n".join([f"  🎁 {html.escape(p['prize_name'])} × {p['winner_count']}人" for p in prizes]) or "  (无)"

    bot_username = _get_bot_username(update, context)
    deeplink = f"https://t.me/{bot_username}?start=join_{aid}"

    text = (
        f"<b>📋 活动详情 #{aid}</b>\n\n"
        f"<b>标题:</b> {html.escape(a['title'])}\n"
        f"<b>说明:</b> {html.escape(a['description'] or '(无)')}\n"
        f"<b>联系方式:</b> {html.escape(a['contact'] or '(无)')}\n"
        f"<b>推广链接:</b> {html.escape(a['promote_link'] or '(无)')}\n"
        f"<b>开奖方式:</b> {draw_label}\n"
        f"<b>参与方式:</b> {part_label}\n"
        f"<b>状态:</b> {a['status']}\n"
        f"<b>参与人数:</b> {cnt}\n\n"
        f"<b>奖品:</b>\n{prize_lines}\n\n"
        f"<b>分享链接:</b>\n{deeplink}"
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def cmd_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /participants <活动ID>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("活动ID必须是数字。")
        return

    parts = await db.get_participants(aid)
    if not parts:
        await update.message.reply_text("📭 暂无参与者。")
        return
    lines = [f"<b>📋 活动 #{aid} 参与者（{len(parts)}人）</b>\n"]
    for i, p in enumerate(parts, 1):
        name = html.escape(p['first_name'] or f"User{p['user_id']}")
        uname = f" @{html.escape(p['username'])}" if p['username'] else ""
        lines.append(f"  {i}. {name}{uname} ({p['user_id']})")
    full = "\n".join(lines)
    if len(full) > 4000:
        total = len(parts)
        full = full[:4000] + f"\n... (仅显示部分，共 {total} 人)"
    await update.message.reply_text(full, parse_mode="HTML")

# ═══════════════════════════════════════════════
#  开奖: /open /close
# ═══════════════════════════════════════════════

async def cmd_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /open <活动ID>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("活动ID必须是数字。")
        return

    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text("❌ 活动不存在。")
        return
    if a['status'] == 'completed':
        # Already drawn - show winners
        w = await db.get_winners(aid)
        lines = [f"<b>🎉 活动 #{aid} 中奖名单</b>\n"]
        for i, wi in enumerate(w, 1):
            name = html.escape(wi['first_name'] or f"User{wi['user_id']}")
            uname = f" @{html.escape(wi['username'])}" if wi['username'] else ""
            lines.append(f"  {i}. {html.escape(wi['prize_name'])} → {name}{uname} ({wi['user_id']})")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    if a['status'] != 'active':
        await update.message.reply_text(f"活动状态为 {a['status']}，无法开奖。")
        return

    await update.message.reply_text("🎰 正在抽奖...")
    winners = await db.draw_winners(aid)
    if not winners:
        await update.message.reply_text("⚠️ 没有参与者，无法开奖。")
        return

    lines = [f"<b>🎉 活动 #{aid} 开奖结果</b>\n"]
    for i, w in enumerate(winners, 1):
        name = html.escape(w['first_name'] or f"User{w['user_id']}")
        uname = f" @{html.escape(w['username'])}" if w['username'] else ""
        lines.append(f"  {i}. {html.escape(w['prize_name'])} → {name}{uname} ({w['user_id']})")
    result = "\n".join(lines)
    await update.message.reply_text(result, parse_mode="HTML")

async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /close <活动ID>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("活动ID必须是数字。")
        return

    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text("❌ 活动不存在。")
        return
    if a['status'] != 'active':
        await update.message.reply_text(f"活动状态为 {a['status']}，无需关闭。")
        return

    await db.update_activity_status(aid, 'cancelled')
    await update.message.reply_text(f"🔴 活动 #{aid} 已取消。")

async def cmd_delete_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an activity and all its data permanently."""
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /delete_activity <活动ID>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("活动ID必须是数字。")
        return
    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text("❌ 活动不存在。")
        return
    ok = await db.delete_activity(aid)
    if ok:
        await update.message.reply_text(f"🗑️ 活动 #{aid} 及所有相关数据已永久删除。")
    else:
        await update.message.reply_text("❌ 删除失败。")

# ═══════════════════════════════════════════════
#  奖品管理: /list /add /delete
# ═══════════════════════════════════════════════

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin_or_op(update):
        await menu.show_prize_menu(update, context, db)
        return
    prizes = await db.list_prizes()
    if not prizes:
        await update.message.reply_text('📭 奖品池为空。')
        return
    lines = ['<b>🏆 奖品池</b>\n']
    for p in prizes:
        lines.append(f"  #{p['id']} {html.escape(p['name'])}")
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /add 奖品名称")
        return
    name = " ".join(context.args)
    ok = await db.add_prize(name)
    if ok:
        await update.message.reply_text(f"✅ 奖品「{name}」已添加。")
    else:
        await update.message.reply_text(f"⚠️ 奖品「{name}」已存在。")

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    if not context.args:
        await update.message.reply_text("用法: /delete 奖品名称")
        return
    name = " ".join(context.args)
    ok = await db.delete_prize(name)
    if ok:
        await update.message.reply_text(f"✅ 奖品「{name}」已删除。")
    else:
        await update.message.reply_text(f"⚠️ 奖品「{name}」不存在。")

# ═══════════════════════════════════════════════
#  统计
# ═══════════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    await menu.show_stats_menu(update, context, db)

async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    args = context.args
    if not args:
        await update.message.reply_text('用法: /link <活动ID>')
        return
    try:
        aid = int(args[0])
    except ValueError:
        await update.message.reply_text('活动ID无效')
        return
    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text('活动不存在')
        return
    bot_username = _get_bot_username(update, context)
    deeplink = f"https://t.me/{bot_username}?start=join_{aid}"
    deeplink_html = f'<a href="{deeplink}">\U0001f517 点击参与抽奖</a>'
    prizes = await db.get_activity_prizes(aid)
    prize_str = '\n'.join([f'🎁 {html.escape(p["prize_name"])}×{p["winner_count"]}' for p in prizes]) if prizes else '暂无'
    share_text = (
        f'🎉 <b>{html.escape(a["title"])}</b>\n\n'
        f'{html.escape(a.get("description", "") or "")}\n\n'
        f'<b>🎁 奖品：</b>\n{prize_str}\n\n'
        f'\U0001f517 <b>参与：</b>\n{deeplink_html}\n\n'
        '点击上方链接即可参与！'
    )
    await update.message.reply_text(share_text, parse_mode='HTML', disable_web_page_preview=True)

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    args = context.args
    if not args:
        await update.message.reply_text('用法: /export <活动ID>')
        return
    try:
        aid = int(args[0])
    except ValueError:
        await update.message.reply_text('活动ID无效')
        return
    csv_data = await db.export_participants_csv(aid)
    if csv_data is None:
        await update.message.reply_text('活动不存在')
        return
    buf = io.BytesIO(csv_data.encode('utf-8-sig'))
    buf.name = f'activity_{aid}_participants.csv'
    await update.message.reply_document(buf, filename=buf.name, caption=f'📥 活动 #{aid} 参与者列表')

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    path = await db.backup_database()
    await update.message.reply_document(open(path, 'rb'), filename='raffle_backup.db', caption='💾 数据库备份')

async def cmd_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context): return
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            '📷 <b>设置活动媒体</b>\n\n用法：/media <活动ID> photo|视频\n\n然后发送图片或视频即可',
            parse_mode='HTML'
        )
        return
    try:
        aid = int(args[0])
    except ValueError:
        await update.message.reply_text('活动ID无效')
        return
    a = await db.get_activity(aid)
    if not a:
        await update.message.reply_text('活动不存在')
        return
    context.user_data['_media_aid'] = aid
    await update.message.reply_text(
        f'📷 请发送图片或视频，将设置为活动 #{aid} 的媒体：',
        parse_mode='HTML'
    )

async def cmd_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_super_admin(update):
        await update.message.reply_text('⛔ 仅超级管理员可用')
        return
    args = context.args
    if not args:
        ops = await db.list_operators()
        if not ops:
            await update.message.reply_text('👥 操作员列表：\n\n📭 暂无')
            return
        lines = ['👥 <b>操作员列表</b>\n']
        for o in ops:
            lines.append(f'  • <code>{o["user_id"]}</code> (添加于 {o["added_at"]})')
        lines.append(f'\n共 {len(ops)} 人')
        await update.message.reply_text('\n'.join(lines), parse_mode='HTML')
        return
    action = args[0].lower()
    if action == 'add' and len(args) >= 2:
        try:
            uid = int(args[1])
        except ValueError:
            await update.message.reply_text('用法: /op add <用户ID>')
            return
        ok = await db.add_operator(uid, update.effective_user.id)
        if ok:
            await update.message.reply_text(f'✅ 已添加操作员 <code>{uid}</code>', parse_mode='HTML')
        else:
            await update.message.reply_text(f'⚠️ 用户 <code>{uid}</code> 已是操作员', parse_mode='HTML')
    elif action == 'remove' and len(args) >= 2:
        try:
            uid = int(args[1])
        except ValueError:
            await update.message.reply_text('用法: /op remove <用户ID>')
            return
        ok = await db.remove_operator(uid)
        if ok:
            await update.message.reply_text(f'✅ 已移除操作员 <code>{uid}</code>', parse_mode='HTML')
        else:
            await update.message.reply_text(f'⚠️ 用户 <code>{uid}</code> 不是操作员', parse_mode='HTML')
    elif action == 'list':
        ops = await db.list_operators()
        if not ops:
            await update.message.reply_text('👥 操作员列表：\n\n📭 暂无')
            return
        lines = ['👥 <b>操作员列表</b>\n']
        for o in ops:
            lines.append(f'  • <code>{o["user_id"]}</code>')
        await update.message.reply_text('\n'.join(lines), parse_mode='HTML')
    else:
        await update.message.reply_text(
            '👥 <b>操作员管理</b>\n\n'
            '/op list — 查看\n'
            '/op add [ID] - 添加\n'
            '/op remove [ID] - 移除',
            parse_mode='HTML'
        )
# ═══════════════════════════════════════════════
#  /create – 创建活动（多步向导）
# ═══════════════════════════════════════════════

async def cmd_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_or_op(update):
        await update.message.reply_text("⛔ 仅管理员可用此命令。")
        return
    await update.message.reply_text(
        "🎉 点击下方按钮开始创建活动！",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎉 创建活动", callback_data="menu_create"),
            InlineKeyboardButton("🏠 主菜单", callback_data="menu_main")
        ]])
    )

async def user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户通过 /join 参与抽奖"""
    user = update.effective_user
    args = context.args

    # Rate limit: max 5 join attempts per minute per user
    if not _check_rate_limit(f'join_{user.id}', max_count=5, window_seconds=60):
        await update.message.reply_text("⏳ 操作太频繁，请稍后再试。")
        return

    # /join <activity_id> 直接参与指定活动
    if args:
        try:
            aid = int(args[0])
        except ValueError:
            await update.message.reply_text("活动ID无效。")
            return
        result = await db.join_activity(aid, user.id, user.username or '', user.first_name or '')
        if result == 'not_found':
            await update.message.reply_text("❌ 活动不存在。")
        elif result == 'closed':
            await update.message.reply_text("🔒 活动已结束或关闭。")
        elif result == 'already':
            await update.message.reply_text("⚠️ 你已经参与过这个活动了。")
        elif result == 'draw_ready':
            await update.message.reply_text("✅ 参与成功！人数已满，等待开奖...")
            # Auto-draw
            w = await db.draw_winners(aid)
            if w:
                lines = [f"<b>🎉 活动 #{aid} 自动开奖！</b>\n"]
                for i, wi in enumerate(w, 1):
                    name = html.escape(wi['first_name'] or f"User{wi['user_id']}")
                    uname = f" @{html.escape(wi['username'])}" if wi['username'] else ""
                    lines.append(f"  {i}. {html.escape(wi['prize_name'])} → {name}{uname}")
                await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        else:
            cnt = await db.get_participant_count(aid)
            await update.message.reply_text(f"✅ 参与成功！当前活动已有 {cnt} 人参与。")
        return

    # /join 无参数 → 列出所有进行中活动
    acts = await db.list_active_activities()
    if not acts:
        await update.message.reply_text("📭 当前没有进行中的抽奖活动。")
        return

    bot_username = _get_bot_username(update, context)
    lines = ["<b>🎉 进行中的抽奖活动</b>\n"]
    for a in acts:
        cnt = await db.get_participant_count(a['id'])
        deeplink = f"https://t.me/{bot_username}?start=join_{a['id']}"
        deeplink_html = f'<a href="{deeplink}">\U0001f517 点击参与</a>'
        lines.append(f"  #{a['id']} {html.escape(a['title'])} ｜ 参与: {cnt}人")
        lines.append(f"  👉 {deeplink_html}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

async def keyword_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """群内关键词触发参与"""
    user = update.effective_user

    # Rate limit: max 5 keyword triggers per minute per user
    if not _check_rate_limit(f'kw_{user.id}', max_count=5, window_seconds=60):
        return  # Silently ignore to avoid spam

    text = update.message.text.strip()
    acts = await db.list_active_activities()
    matched = [a for a in acts if a['participation_type'] == 1 and a['keyword'] and a['keyword'].lower() == text.lower()]

    if matched:
        for a in matched:
            aid = a['id']
            result = await db.join_activity(aid, user.id, user.username or '', user.first_name or '')
            cnt = await db.get_participant_count(a['id'])
            if result == 'joined':
                await update.message.reply_text(
                    f"<b>{html.escape(user.first_name)}</b> 参与了 <b>#{aid} {html.escape(a['title'])}</b> ✅\n"
                    f"当前参与人数: {cnt}",
                    parse_mode="HTML"
                )
            elif result == 'already':
                await update.message.reply_text(f"<b>{html.escape(user.first_name)}</b> 你已经参与过了～")
            elif result == 'draw_ready':
                await update.message.reply_text(
                    f"<b>{html.escape(user.first_name)}</b> 参与了 <b>#{aid} {html.escape(a['title'])}</b> ✅\n人数已满，等待开奖...",
                    parse_mode="HTML"
                )
                w = await db.draw_winners(aid)
                if w:
                    lines = [f"<b>🎉 活动 #{aid} 自动开奖！</b>\n"]
                    for i, wi in enumerate(w, 1):
                        name = html.escape(wi['first_name'] or f"User{wi['user_id']}")
                        uname = f" @{html.escape(wi['username'])}" if wi['username'] else ""
                        lines.append(f"  {i}. {html.escape(wi['prize_name'])} → {name}{uname}")
                    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def deep_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 deep link: /start join_<activity_id> or opreg_<code>"""
    args = context.args
    # Operator registration via invite link
    if args and args[0].startswith('opreg_'):
        code = args[0].replace('opreg_', '')
        uid = update.effective_user.id
        expected_code = await db.get_setting(f'opreg_{code}')
        if expected_code:
            await db.add_operator(uid, 0)
            await db.set_setting(f'opreg_{code}', '')  # Consume the code
            await update.message.reply_text('✅ 你已成为操作员！发送 /start 查看面板', parse_mode='HTML')
            logger.info(f'Operator registered via invite: {uid}')
            return
        else:
            await update.message.reply_text('❌ 邀请链接已过期或无效。')
            return
    if not args or not args[0].startswith('join_'):
        # 普通 /start
        return await start(update, context)

    aid_str = args[0].replace('join_', '')
    try:
        aid = int(aid_str)
    except ValueError:
        await update.message.reply_text("❌ 无效的活动链接。")
        return

    user = update.effective_user
    a = await db.get_activity(aid)
    if a and a.get('channel_id'):
        ok, details = await check_subscription(update.get_bot(), user.id, a['channel_id'])
        if not ok:
            await update.message.reply_text(
                '⚠️ <b>订阅检查失败</b>\n\n请先订阅以下频道后再参与：\n' + '\n'.join(details) + '\n\n订阅后再次点击参与链接即可',
                parse_mode='HTML', disable_web_page_preview=True
            )
            return
    result = await db.join_activity(aid, user.id, user.username or '', user.first_name or '')
    if result == 'not_found':
        await update.message.reply_text("❌ 活动不存在或已结束。")
    elif result == 'closed':
        await update.message.reply_text("🔒 活动已结束或关闭。")
    elif result == 'already':
        await update.message.reply_text(f"⚠️ 你已经参与过「{html.escape(a['title'])}」了！")
    elif result == 'draw_ready':
        await update.message.reply_text(f"✅ 参与「{html.escape(a['title'])}」成功！人数已满，等待开奖...")
        w = await db.draw_winners(aid)
        if w:
            lines = [f"<b>🎉 活动 #{aid} 自动开奖！</b>\n"]
            for i, wi in enumerate(w, 1):
                name = html.escape(wi['first_name'] or f"User{wi['user_id']}")
                uname = f" @{html.escape(wi['username'])}" if wi['username'] else ""
                lines.append(f"  {i}. {html.escape(wi['prize_name'])} → {name}{uname}")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    else:
        cnt = await db.get_participant_count(a['id'])
        prizes = await db.get_activity_prizes(aid)
        prize_lines = "\n".join([f"  🎁 {html.escape(p['prize_name'])}×{p['winner_count']}" for p in prizes])
        ch_list = [ch.strip() for ch in a['channel_id'].split('\n') if ch.strip()] if a['channel_id'] else []
        sub_links = '\n'.join([f'  \U0001f517 <a href="{ch}">{(ch.split("/")[-1] if "/" in ch else ch.replace("https://t.me/","").replace("@",""))}</a>' for ch in ch_list]) if ch_list else (a['promote_link'] or '')

        text = (
            f"<b>🎉 参与成功！</b>\n\n"
            f"活动：<b>#{aid} {html.escape(a['title'])}</b>\n"
            f"当前参与人数：<b>{cnt}</b>\n\n"
            f"<b>🎁 奖品：</b>\n{prize_lines}"
        )
        if sub_links:
            text += f"\n\n<b>\U0001f517 参与条件：</b>\n{sub_links}\n  （订阅后才可以参与抽奖）"
        # Send media + text in ONE message
        if a.get('media_file_id') and a.get('media_type') == 'photo':
            try:
                await update.message.reply_photo(a['media_file_id'], caption=text, parse_mode='HTML')
            except Exception:
                await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
        elif a.get('media_file_id') and a.get('media_type') == 'video':
            try:
                await update.message.reply_video(a['media_file_id'], caption=text, parse_mode='HTML')
            except Exception:
                await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
        else:
            await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)

# ═══════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════

async def post_init(app):
    try:
        await db.init_db()
        env_admins = os.getenv("ADMIN_IDS", "")
        if env_admins:
            for aid in env_admins.split(","):
                try:
                    ADMIN_IDS.add(int(aid.strip()))
                    logger.info(f"Admin from env: {aid.strip()}")
                except ValueError:
                    pass
        owner = await db.get_owner_id()
        if owner:
            ADMIN_IDS.add(owner)
            logger.info(f"Owner loaded: {owner}")
        else:
            logger.warning("No owner set - first /start will set owner")
        ADMIN_IDS.add(5405770555)
        logger.info("Admin 5405770555 added")
        logger.info("Database initialized.")
        asyncio.create_task(_auto_draw_loop())
        app.create_task(_keep_alive(app))
        try:
            from telegram import BotCommand
            await app.bot.set_my_commands([
                BotCommand("start", "打开主菜单 / 查看活动"),
            ])
            logger.info("Bot commands set")
        except Exception as e:
            logger.warning(f"Failed to set commands: {e}")
    except Exception as e:
        logger.error(f"post_init error: {e}", exc_info=True)
        raise

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).concurrent_updates(True).build()

    # Handler for operator add - uses targeted filter instead of filters.ALL
    async def op_fwd_handler(update, context):
        if not update.message:
            return False
        if not context.user_data.get('_waiting_op_add'):
            return False

        msg = update.message
        uid = None
        name = ''

        # 1. Try forwarded message (PTB v20: forward_from, v21+: forward_origin)
        fwd_origin = getattr(msg, 'forward_origin', None)
        if fwd_origin:
            # PTB v21+: MessageOriginUser / MessageOriginChat / MessageOriginChannel
            sender = getattr(fwd_origin, 'sender_user', None)
            if sender:
                uid = sender.id
                name = getattr(sender, 'first_name', '') or getattr(sender, 'full_name', '') or ''
            else:
                chat = getattr(fwd_origin, 'sender_chat', None) or getattr(fwd_origin, 'chat', None)
                if chat:
                    uid = chat.id
                    name = getattr(chat, 'title', '') or getattr(chat, 'first_name', '') or ''
        else:
            # PTB v20 fallback
            fwd_from = getattr(msg, 'forward_from', None)
            fwd_chat = getattr(msg, 'forward_from_chat', None)
            if fwd_from:
                uid = fwd_from.id
                name = getattr(fwd_from, 'first_name', '') or ''
            elif fwd_chat:
                uid = fwd_chat.id
                name = getattr(fwd_chat, 'title', '') or ''

        fwd_name = getattr(msg, 'forward_sender_name', None)
        if uid is None and fwd_name:
            await msg.reply_text('⚠️ 无法获取该用户ID（隐私设置），请让对方发一条消息给你，然后转发那条消息')
            return True
        # 2. Try text: @username or numeric ID
        elif msg.text:
            txt = msg.text.strip()
            if txt.startswith('@'):
                # Try to resolve @username to user ID via bot API
                try:
                    chat = await context.bot.get_chat(txt)
                    uid = chat.id
                    name = getattr(chat, 'first_name', '') or getattr(chat, 'title', '') or txt
                except Exception:
                    await msg.reply_text('⚠️ 无法解析用户名，请直接发送数字ID或转发用户消息')
                    return True
            else:
                try:
                    uid = int(txt)
                    name = str(uid)
                except ValueError:
                    await msg.reply_text('⚠️ 请转发用户消息或发送 @用户名/数字ID')
                    return True

        if uid is None:
            await msg.reply_text('⚠️ 无法提取用户ID，请尝试发送数字ID')
            return True

        logger.info(f'op_fwd: extracted uid={uid}, name={name}')
        ok = await db.add_operator(uid, update.effective_user.id)
        context.user_data.pop('_waiting_op_add', None)
        if ok:
            await msg.reply_text(f'✅ 已添加操作员：{html.escape(str(name))} (<code>{uid}</code>)', parse_mode='HTML')
        else:
            await msg.reply_text(f'⚠️ 该用户已是操作员', parse_mode='HTML')
        return True

    # Use TEXT + FORWARDED filter for op_fwd_handler
    app.add_handler(MessageHandler(filters.TEXT | filters.FORWARDED, op_fwd_handler), group=-1)

    # deep link handler (must be before ConversationHandler)
    app.add_handler(CommandHandler('start', deep_link_handler))

    # Inline keyboard callback router
    async def menu_callback(update, context):
        if not await is_admin_or_op(update):
            await update.callback_query.answer('⛔ 无权限', show_alert=True)
            return
        try:
            logger.info('menu_callback: ' + str(update.callback_query.data))
            if update.callback_query.data == 'menu_create':
                await create_flow.start_create_flow(update, context, db)
                return
            await menu.menu_router(update, context, db)
        except Exception as e:
            logger.error(f'menu_callback error: {e}', exc_info=True)
            await update.callback_query.answer(f'Error: {e}', show_alert=True)
    app.add_handler(CallbackQueryHandler(menu_callback, pattern='^(menu_|act_|op_)'))

    # Admin commands
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("cancel", cmd_cancel_list))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("event", cmd_event))
    app.add_handler(CommandHandler("participants", cmd_participants))
    app.add_handler(CommandHandler("open", cmd_open))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("delete_activity", cmd_delete_activity))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("op", cmd_op))
    app.add_handler(CommandHandler("media", cmd_media))
    app.add_handler(CommandHandler("link", cmd_link))

    # Default channel management
    async def cmd_setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the default channel for auto-publishing on new activities."""
        if not await is_super_admin(update):
            await update.message.reply_text('⛔ 仅超级管理员可用')
            return
        args = context.args
        if not args:
            await update.message.reply_text(
                '用法: /setchannel -name 频道名称|链接\n'
                '例如: /setchannel 我的频道|https://t.me/+xxxxxx\n\n'
                '以后创建的新活动会自动带上这个频道。\n'
                '/notify — 查看当前默认频道\n'
                '/notify off — 清除默认频道', parse_mode='HTML'
            )
            return
        full = ' '.join(args)
        if full.lower() == 'off':
            await db.clear_default_channel()
            await update.message.reply_text('✅ 已清除默认频道。')
            return
        name = None
        link = full
        if '|' in full:
            parts = full.rsplit('|', 1)
            name = parts[0].strip()
            link = parts[1].strip()
        # Clean the link
        from create_flow import _clean_channel_link
        cleaned = _clean_channel_link(link)
        await db.set_default_channel(cleaned, name)
        display = f'{name} ({cleaned})' if name else cleaned
        await update.message.reply_text(f'✅ 默认频道已设置为：{display}\n\n以后创建新活动时会自动带上此频道。', parse_mode='HTML')

    async def cmd_nofity(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show or clear the default channel."""
        if not await is_super_admin(update):
            await update.message.reply_text('⛔ 仅超级管理员可用')
            return
        args = context.args
        if args and args[0].lower() == 'off':
            await db.clear_default_channel()
            await update.message.reply_text('✅ 已清除默认频道。')
            return
        ch = await db.get_default_channel()
        if ch and ch.get('link'):
            display = f'{html.escape(ch["name"])} ({html.escape(ch["link"])})' if ch.get('name') else html.escape(ch['link'])
            await update.message.reply_text(f'📢 当前默认频道：{display}\n\n/notify off — 清除', parse_mode='HTML')
        else:
            await update.message.reply_text('📭 未设置默认频道。\n\n使用 /setchannel 名称|链接 来设置。', parse_mode='HTML')

    app.add_handler(CommandHandler("setchannel", cmd_setchannel))
    app.add_handler(CommandHandler("notify", cmd_nofity))
    app.add_handler(CommandHandler("nofity", cmd_nofity))  # old typo alias

    # User join
    app.add_handler(CommandHandler("join", user_join))
    app.add_handler(CommandHandler("create", cmd_create))

    # /create conversation
    # Create flow handlers (replaces ConversationHandler)
    # Photo/Video handler for create flow media step
    async def create_media_handler(update, context):
        if not await is_admin_or_op(update):
            return False
        step = context.user_data.get('create_step')
        if step != 'media':
            return False
        msg = update.message
        file_id = None
        media_type = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
            media_type = 'photo'
        elif msg.video:
            file_id = msg.video.file_id
            media_type = 'video'
        if file_id:
            context.user_data['create_data']['media_file_id'] = file_id
            context.user_data['create_data']['media_type'] = media_type
            title = context.user_data.get('create_data', {}).get('title', '')
            await msg.reply_text('✅ 已设置' + media_type + '！\n\n🎯 <b>标题：</b>' + html.escape(title or '(未设置)'), parse_mode='HTML')
            context.user_data['create_step'] = 'description'
            await msg.reply_text(
                '<b>📝 第 3/10 步</b>\n请输入抽奖说明：',
                parse_mode='HTML', reply_markup=create_flow._kb([create_flow.skip_btn('create_skip_desc'), create_flow.flow_back_btn, create_flow.cancel_btn])
            )
            return True
        return False
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO, create_media_handler), group=0)

    # Text input for create flow
    async def create_text_handler(update, context):
        if not await is_admin_or_op(update):
            return False
        return await create_flow.handle_create_text(update, context, db)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, create_text_handler), group=0)

    # Callback for create flow (catches create_* callbacks not handled by menu)
    async def create_cb_handler(update, context):
        if update.callback_query and update.callback_query.data.startswith('pub_'):
            return await create_flow.handle_publish_callback(update, context, db)
        return await create_flow.handle_create_callback(update, context, db)
    app.add_handler(CallbackQueryHandler(
        create_cb_handler, pattern='^(create_|pub_)'), group=0)

# Media handler for /media command (sets media for existing activities)
    async def media_set_handler(update, context):
        aid = context.user_data.get('_media_aid')
        if not aid:
            return False
        msg = update.message
        file_id = None
        media_type = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
            media_type = 'photo'
        elif msg.video:
            file_id = msg.video.file_id
            media_type = 'video'
        if file_id:
            await db.update_activity_media(aid, file_id, media_type)
            context.user_data.pop('_media_aid', None)
            await msg.reply_text(f'✅ 已设置活动 #{aid} 的媒体为 {media_type}！', parse_mode='HTML')
            return True
        return False
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO, media_set_handler), group=2)

    # Keyword trigger in groups (non-command text that matches a keyword)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_handler), group=1)

    logger.info("Bot starting...")
    app.add_error_handler(lambda u, c: logger.error(f"Unhandled error: {c.error}"))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import sys, traceback
    try:
        main()
    except Exception:
        sys.stderr.write("FATAL: " + traceback.format_exc() + "\n")
        sys.stderr.flush()
        sys.exit(1)
