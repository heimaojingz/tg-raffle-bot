import aiosqlite
import os
from datetime import datetime
import html
from typing import Union

DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(__file__))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "raffle.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable WAL mode for better concurrent read/write performance (optional)
        try:
            await db.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # WAL might fail on some filesystems, that's OK
        # Enable foreign keys
        try:
            await db.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS prizes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                contact TEXT DEFAULT '',
                promote_link TEXT DEFAULT '',
                draw_type INTEGER NOT NULL,
                draw_time TIMESTAMP,
                draw_count INTEGER DEFAULT 0,
                participation_type INTEGER DEFAULT 1,
                keyword TEXT DEFAULT '',
                channel_id TEXT DEFAULT '',
                media_file_id TEXT DEFAULT '',
                media_type TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_prizes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL,
                prize_name TEXT NOT NULL,
                winner_count INTEGER NOT NULL,
                FOREIGN KEY (activity_id) REFERENCES activities(id)
            );

            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(activity_id, user_id),
                FOREIGN KEY (activity_id) REFERENCES activities(id)
            );

            CREATE TABLE IF NOT EXISTS winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                prize_name TEXT NOT NULL,
                prize_level INTEGER DEFAULT 0,
                drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operators (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );
        """)
        await db.commit()

# ── Prize management ──

async def add_prize(name: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO prizes (name) VALUES (?)", (name,))
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False

async def delete_prize(name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM prizes WHERE name = ?", (name,))
        await db.commit()
        return cursor.rowcount > 0

async def list_prizes():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM prizes ORDER BY id")
        return await cursor.fetchall()

# ── Activity management ──

async def create_activity(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO activities (title, description, contact, promote_link,
               media_file_id, media_type, draw_type, draw_time, draw_count, participation_type, keyword,
               channel_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data['title'], data.get('description', ''), data.get('contact', ''),
             data.get('promote_link', ''), data.get('media_file_id', ''), data.get('media_type', ''),
             data['draw_type'], data.get('draw_time'),
             data.get('draw_count', 0), data.get('participation_type', 1),
             data.get('keyword', ''), data.get('channel_id', ''), 'active')
        )
        activity_id = cursor.lastrowid
        for prize in data.get('prizes', []):
            await db.execute(
                "INSERT INTO activity_prizes (activity_id, prize_name, winner_count) VALUES (?, ?, ?)",
                (activity_id, prize['name'], prize['count'])
            )
        await db.commit()
        return activity_id

async def get_activity(activity_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))
        return await cursor.fetchone()

async def get_activity_prizes(activity_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM activity_prizes WHERE activity_id = ? ORDER BY id", (activity_id,))
        return await cursor.fetchall()

async def list_activities_by_status(status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM activities WHERE status = ? ORDER BY id DESC", (status,))
        return await cursor.fetchall()

async def update_activity_media(activity_id: int, file_id: str, media_type: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE activities SET media_file_id = ?, media_type = ? WHERE id = ?", (file_id, media_type, activity_id))
        await db.commit()
        return True

async def delete_activity(activity_id: int) -> bool:
    """Delete an activity and all its associated data."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM winners WHERE activity_id = ?", (activity_id,))
        await db.execute("DELETE FROM participants WHERE activity_id = ?", (activity_id,))
        await db.execute("DELETE FROM activity_prizes WHERE activity_id = ?", (activity_id,))
        cursor = await db.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
        await db.commit()
        return cursor.rowcount > 0

async def list_active_activities():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM activities WHERE status = 'active' ORDER BY id DESC")
        return await cursor.fetchall()

async def update_activity_status(activity_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE activities SET status = ? WHERE id = ?", (status, activity_id))
        await db.commit()

async def get_running_count():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM activities WHERE status = 'active'")
        row = await cursor.fetchone()
        return row[0]

async def get_prize_pool_count():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM prizes")
        row = await cursor.fetchone()
        return row[0]

# ── Participants ──

async def join_activity(activity_id: int, user_id: int, username: str, first_name: str) -> str:
    """Returns: 'joined', 'already', 'not_found', 'closed'"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        act = await db.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))
        row = await act.fetchone()
        if not row:
            return 'not_found'
        if row['status'] != 'active':
            return 'closed'
        draw_type = row['draw_type']
        draw_count = row['draw_count'] if draw_type == 2 else 0
        # Atomic insert - if it succeeds, participant is added
        try:
            await db.execute(
                "INSERT INTO participants (activity_id, user_id, username, first_name) VALUES (?, ?, ?, ?)",
                (activity_id, user_id, username, first_name)
            )
            await db.commit()
            # After insert, check if count-based draw should trigger
            # Use >= to handle edge case of concurrent joins (slight over-count is OK)
            if draw_type == 2:
                count_cursor = await db.execute("SELECT COUNT(*) FROM participants WHERE activity_id = ?", (activity_id,))
                current = (await count_cursor.fetchone())[0]
                if current >= draw_count:
                    return 'draw_ready'
            return 'joined'
        except aiosqlite.IntegrityError:
            return 'already'

async def get_participants(activity_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM participants WHERE activity_id = ? ORDER BY joined_at", (activity_id,))
        return await cursor.fetchall()

async def get_participant_count(activity_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM participants WHERE activity_id = ?", (activity_id,))
        row = await cursor.fetchone()
        return row[0]

async def get_participant_counts_bulk(activity_ids: list) -> dict:
    if not activity_ids:
        return {}
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join(["?" for _ in activity_ids])
        cursor = await db.execute(
            f"SELECT activity_id, COUNT(*) FROM participants WHERE activity_id IN ({placeholders}) GROUP BY activity_id",
            activity_ids
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

# ── Winners / Draw ──

async def draw_winners(activity_id: int) -> list:
    """Draw winners and return list of winner dicts. Atomic: checks status before drawing."""
    import random
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check for stuck 'drawing' status and revert
        cursor = await db.execute("SELECT status FROM activities WHERE id = ?", (activity_id,))
        row = await cursor.fetchone()
        if row and row['status'] == 'drawing':
            await db.execute("UPDATE activities SET status = 'active' WHERE id = ?", (activity_id,))
            await db.commit()
            return []

        # Atomic check-and-set: only draw if status is 'active'
        cursor = await db.execute(
            "UPDATE activities SET status = 'drawing' WHERE id = ? AND status = 'active'",
            (activity_id,)
        )
        if cursor.rowcount == 0:
            # Already drawn, cancelled, or being drawn by another process
            cursor = await db.execute("SELECT status FROM activities WHERE id = ?", (activity_id,))
            row = await cursor.fetchone()
            if row and row['status'] == 'completed':
                # Return existing winners
                cursor = await db.execute(
                    "SELECT * FROM winners WHERE activity_id = ? ORDER BY prize_level, id",
                    (activity_id,)
                )
                return await cursor.fetchall()
            return []

        # Get participants
        cursor = await db.execute("SELECT * FROM participants WHERE activity_id = ?", (activity_id,))
        participants = await cursor.fetchall()
        if not participants:
            await db.execute("UPDATE activities SET status = 'active' WHERE id = ?", (activity_id,))
            await db.commit()
            return []

        # Get prize levels
        cursor = await db.execute("SELECT * FROM activity_prizes WHERE activity_id = ? ORDER BY id", (activity_id,))
        prize_levels = await cursor.fetchall()
        if not prize_levels:
            await db.execute("UPDATE activities SET status = 'active' WHERE id = ?", (activity_id,))
            await db.commit()
            return []

        available = list(participants)
        used_ids = set()
        winners = []
        try:
            for level_idx, level in enumerate(prize_levels):
                count = min(level['winner_count'], len(available))
                if count <= 0:
                    continue
                chosen = random.sample(available, count)
                for p in chosen:
                    winners.append({
                        'user_id': p['user_id'],
                        'username': p['username'],
                        'first_name': p['first_name'],
                        'prize_name': level['prize_name'],
                        'prize_level': level_idx
                    })
                    used_ids.add(p['user_id'])
                    await db.execute(
                        "INSERT INTO winners (activity_id, user_id, username, first_name, prize_name, prize_level) VALUES (?, ?, ?, ?, ?, ?)",
                        (activity_id, p['user_id'], p['username'], p['first_name'], level['prize_name'], level_idx)
                    )
                # Remove chosen participants by user_id set (O(n) instead of O(n*m))
                available = [p for p in available if p['user_id'] not in used_ids]

            await db.execute("UPDATE activities SET status = 'completed' WHERE id = ?", (activity_id,))
            await db.commit()
            return winners
        except Exception:
            cursor = await db.execute("SELECT status FROM activities WHERE id = ?", (activity_id,))
            row = await cursor.fetchone()
            if row and row['status'] == 'drawing':
                await db.execute("UPDATE activities SET status = 'active' WHERE id = ?", (activity_id,))
            await db.commit()
            raise

async def get_winners(activity_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM winners WHERE activity_id = ? ORDER BY prize_level, id", (activity_id,))
        return await cursor.fetchall()

# ── Stats ──

async def export_participants_csv(activity_id: int) -> Union[str, None]:
    """Export participants as CSV string. Returns None if activity not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        act = await db.execute("SELECT id FROM activities WHERE id = ?", (activity_id,))
        if not await act.fetchone():
            return None
        cursor = await db.execute(
            "SELECT user_id, username, first_name, joined_at FROM participants WHERE activity_id = ? ORDER BY joined_at",
            (activity_id,)
        )
        rows = await cursor.fetchall()
        import csv, io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["user_id", "username", "first_name", "joined_at"])
        for r in rows:
            writer.writerow([r["user_id"], r["username"], r["first_name"], r["joined_at"]])
        return buf.getvalue()

async def backup_database() -> str:
    """Create a consistent backup using SQLite backup API."""
    backup_path = DB_PATH + ".backup"
    import sqlite3
    async with aiosqlite.connect(DB_PATH) as src:
        dst = sqlite3.connect(backup_path)
        try:
            await src.backup(dst)
        finally:
            dst.close()
    return backup_path

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT COUNT(*) FROM activities")
        total_activities = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM activities WHERE status = 'active'")
        active_activities = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM activities WHERE status = 'completed'")
        completed_activities = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM activities WHERE status = 'cancelled'")
        cancelled_activities = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM participants")
        total_participants = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM winners")
        total_winners = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM prizes")
        total_prizes = (await cursor.fetchone())[0]

        return {
            'total_activities': total_activities,
            'active_activities': active_activities,
            'completed_activities': completed_activities,
            'cancelled_activities': cancelled_activities,
            'total_participants': total_participants,
            'total_winners': total_winners,
            'total_prizes': total_prizes
        }


# Settings / Owner

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_owner_id() -> int:
    val = await get_setting("owner_id")
    return int(val) if val else None

async def set_owner_id(user_id: int):
    await set_setting("owner_id", str(user_id))

async def is_owner(user_id: int) -> bool:
    owner = await get_owner_id()
    return owner == user_id

# Operator management

async def add_operator(user_id: int, added_by: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT 1 FROM operators WHERE user_id = ?", (user_id,))
            if await cursor.fetchone():
                return False
            await db.execute("INSERT INTO operators (user_id, added_by) VALUES (?, ?)", (user_id, added_by))
            await db.commit()
            return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'add_operator({user_id}): {e}')
        return False


async def is_operator(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM operators WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

# Default channel

async def get_default_channel() -> Union[dict, None]:
    link = await get_setting("default_channel_link")
    name = await get_setting("default_channel_name")
    if link:
        return {'link': link, 'name': name or None}
    return None

async def set_default_channel(link: str, name: Union[str, None] = None):
    await set_setting("default_channel_link", link)
    if name:
        await set_setting("default_channel_name", name)
    else:
        await set_setting("default_channel_name", "")

async def clear_default_channel():
    await set_setting("default_channel_link", "")
    await set_setting("default_channel_name", "")

# Shared activity text formatter

def format_activity_broadcast(title: str, description: str, contact: str,
                               prize_lines: str, draw_type: int, draw_time, draw_count,
                               channel_links: list, deeplink_html: str,
                               include_conditions_label: bool = True) -> str:
    parts = []
    parts.append('🎟️ <b>抽奖标题：' + html.escape(title or '') + '</b>')
    parts.append('')
    parts.append('📪 <b>抽奖说明：</b>\n' + html.escape(description or ''))
    if contact:
        parts.append('📪 联系方式：' + html.escape(contact))
    parts.append('')
    if channel_links and include_conditions_label:
        ch_lines = '\n'.join(['🎫 <a href="' + ch['link'] + '">' + html.escape(ch['name'] or ch['link']) + '</a>' for ch in channel_links])
        parts.append('🎫 <b>参与条件（需订阅）：</b>\n' + ch_lines)
        parts.append('')
    parts.append('🎁 <b>奖品内容:</b>\n' + prize_lines)
    parts.append('')
    if draw_type == 1 and draw_time:
        parts.append('📅 开奖时间：' + html.escape(str(draw_time)) + ' 自动开奖')
    elif draw_type == 2 and draw_count:
        parts.append('📅 开奖方式：满' + html.escape(str(draw_count)) + '人自动开奖')
    parts.append('')
    parts.append('👉 <b>参与抽奖：</b>\n' + deeplink_html)
    return '\n'.join(parts)

async def remove_operator(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM operators WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

async def list_operators():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM operators ORDER BY added_at")
        return await cursor.fetchall()
