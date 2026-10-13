import secrets
from datetime import datetime, timezone
import aiosqlite
from typing import Optional, List, Dict, Tuple, Any
from config import DATABASE_PATH, logger, ADMIN_IDS, ADMIN_USERNAMES, ADMIN_GROUP_ID

async def init_db() -> None:
    """Initialize database tables and indices."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_unique_id TEXT UNIQUE,
                file_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                caption TEXT,
                mime_type TEXT,
                message_id INTEGER,
                channel_id INTEGER,
                share_code TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_verifications (
                user_id INTEGER PRIMARY KEY,
                verified_until TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_verifications (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                target_movie_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                user_handle TEXT,
                plan_id TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                plan_days INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'PENDING',
                proof_file_id TEXT,
                utr_or_note TEXT,
                utr_number TEXT,
                admin_message_id INTEGER,
                admin_chat_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """)
        
        # Migration for existing payment_requests table if utr_number column is missing
        try:
            await db.execute("ALTER TABLE payment_requests ADD COLUMN utr_number TEXT")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_file_name ON movies(file_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_share_code ON movies(share_code)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pending_token ON pending_verifications(token)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_download_time ON user_downloads(user_id, downloaded_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_subscription_expiry ON subscriptions(expires_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_payment_requests_user ON payment_requests(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_payment_requests_status ON payment_requests(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_payment_requests_utr ON payment_requests(utr_number)")
        await db.commit()
    logger.info("Database initialized successfully.")

async def add_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> bool:
    """Register user if not exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name)
        )
        await db.commit()
        return cursor.rowcount > 0

async def get_total_users() -> int:
    """Return total registered users count."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_user_ids() -> List[int]:
    """Return list of all registered user IDs."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

def _generate_share_code() -> str:
    """Generate a clean random 8-character string for deep links."""
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]

async def save_movie(
    file_id: str,
    file_unique_id: str,
    file_name: str,
    file_size: int = 0,
    caption: Optional[str] = None,
    mime_type: Optional[str] = None,
    message_id: Optional[int] = None,
    channel_id: Optional[int] = None
) -> Tuple[int, str, bool]:
    """
    Save or update a movie file.
    Returns: (movie_id, share_code, is_new)
    """
    share_code = _generate_share_code()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if already exists by file_unique_id
        async with db.execute(
            "SELECT id, share_code FROM movies WHERE file_unique_id = ?",
            (file_unique_id,)
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                return existing[0], existing[1], False

        # Insert new movie
        cursor = await db.execute(
            """
            INSERT INTO movies (
                file_id, file_unique_id, file_name, file_size, caption,
                mime_type, message_id, channel_id, share_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                file_unique_id,
                file_name,
                file_size,
                caption,
                mime_type,
                message_id,
                channel_id,
                share_code
            )
        )
        movie_id = cursor.lastrowid
        await db.commit()
        return movie_id, share_code, True

async def get_movie_by_id(movie_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve movie record by internal ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_movie_by_code(share_code: str) -> Optional[Dict[str, Any]]:
    """Retrieve movie record by unique share code."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM movies WHERE share_code = ?", (share_code,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def search_movies(query: str, offset: int = 0, limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:
    """
    Search movies by query keywords with pagination.
    Returns: (list_of_movies, total_matches)
    """
    # Clean query and split into keywords
    keywords = [k.strip() for k in query.replace(".", " ").replace("-", " ").replace("_", " ").split() if k.strip()]
    if not keywords:
        return [], 0

    where_clauses = []
    params: List[Any] = []
    for kw in keywords:
        where_clauses.append("LOWER(file_name) LIKE ?")
        params.append(f"%{kw.lower()}%")

    where_sql = " AND ".join(where_clauses)
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Get count
        count_sql = f"SELECT COUNT(*) FROM movies WHERE {where_sql}"
        async with db.execute(count_sql, params) as cursor:
            count_row = await cursor.fetchone()
            total_count = count_row[0] if count_row else 0

        if total_count == 0:
            # Fallback to single wildcard search across file_name or caption
            fallback_sql = "SELECT COUNT(*) FROM movies WHERE LOWER(file_name) LIKE ? OR LOWER(caption) LIKE ?"
            fallback_param = f"%{query.lower().strip()}%"
            async with db.execute(fallback_sql, (fallback_param, fallback_param)) as cursor:
                count_row = await cursor.fetchone()
                total_count = count_row[0] if count_row else 0
            
            if total_count > 0:
                fetch_sql = (
                    "SELECT * FROM movies WHERE LOWER(file_name) LIKE ? OR LOWER(caption) LIKE ? "
                    "ORDER BY id DESC LIMIT ? OFFSET ?"
                )
                async with db.execute(fetch_sql, (fallback_param, fallback_param, limit, offset)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows], total_count
            return [], 0

        # Fetch records
        fetch_sql = f"SELECT * FROM movies WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
        fetch_params = params + [limit, offset]
        async with db.execute(fetch_sql, fetch_params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows], total_count

async def get_total_movies() -> int:
    """Return total indexed movies count."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM movies") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def delete_movie(movie_id: int) -> bool:
    """Delete a movie by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
        await db.commit()
        return cursor.rowcount > 0

async def is_user_verified(user_id: int) -> bool:
    """Check if user has an active, unexpired verification pass."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """
            SELECT 1 FROM user_verifications
            WHERE user_id = ? AND datetime(verified_until) > datetime('now')
            """,
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_user_verification_expiry(user_id: int) -> Optional[str]:
    """Return expiration timestamp string if user is verified."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """
            SELECT verified_until FROM user_verifications
            WHERE user_id = ? AND datetime(verified_until) > datetime('now')
            """,
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def create_pending_verification(token: str, user_id: int, target_movie_id: Optional[int] = None) -> None:
    """Store a pending verification token."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO pending_verifications (token, user_id, target_movie_id)
            VALUES (?, ?, ?)
            """,
            (token, user_id, target_movie_id)
        )
        await db.commit()

async def complete_verification(token: str, hours: int = 24) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Validate verification token, activate user pass for given hours, and clean up.
    Returns: (is_valid, target_movie_id, verified_until_string)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT user_id, target_movie_id FROM pending_verifications WHERE token = ?",
            (token,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, None, None
            user_id, target_movie_id = row

        # Set verified_until = datetime('now', '+X hours')
        await db.execute(
            f"""
            INSERT INTO user_verifications (user_id, verified_until)
            VALUES (?, datetime('now', '+{hours} hours'))
            ON CONFLICT(user_id) DO UPDATE SET
                verified_until = datetime('now', '+{hours} hours')
            """,
            (user_id,)
        )

        # Retrieve new expiry
        async with db.execute("SELECT verified_until FROM user_verifications WHERE user_id = ?", (user_id,)) as cur:
            exp_row = await cur.fetchone()
            expiry_str = exp_row[0] if exp_row else None

        # Remove used token
        await db.execute("DELETE FROM pending_verifications WHERE token = ?", (token,))
        await db.commit()
        return True, target_movie_id, expiry_str

async def record_user_download(user_id: int, movie_id: int) -> None:
    """Log a completed movie download."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO user_downloads (user_id, movie_id) VALUES (?, ?)",
            (user_id, movie_id)
        )
        await db.commit()

async def get_user_downloads_last_24h(user_id: int) -> Tuple[int, Optional[str]]:
    """
    Return (count_of_downloads, oldest_download_timestamp) in the last 24 hours.
    Used for 1 movie/day restriction and countdown calculation.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*), MIN(downloaded_at)
            FROM user_downloads
            WHERE user_id = ? AND downloaded_at > datetime('now', '-24 hours')
            """,
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                count = row[0] or 0
                oldest_time = row[1]
                return count, oldest_time
            return 0, None

async def reset_user_downloads(user_id: int) -> bool:
    """Reset download limit for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM user_downloads WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_total_downloads_today() -> int:
    """Return count of downloads in the last 24 hours across all users."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM user_downloads WHERE downloaded_at > datetime('now', '-24 hours')"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_user_downloads_today(user_id: int) -> int:
    """
    Return count of downloads by user today (since start of current calendar day).
    """
    now_local = datetime.now().astimezone()
    start_of_day = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM user_downloads
            WHERE user_id = ? AND downloaded_at >= ?
            """,
            (user_id, start_of_day_utc)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def is_user_premium(user_id: int) -> bool:
    """Check if user has an active, unexpired VIP/Premium subscription."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM subscriptions WHERE user_id = ? AND datetime(expires_at) > datetime('now')",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_user_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    """Return subscription details and remaining days if user is premium."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT expires_at,
                   CAST((julianday(expires_at) - julianday('now')) AS INTEGER) as days_left
            FROM subscriptions
            WHERE user_id = ? AND datetime(expires_at) > datetime('now')
            """,
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def add_user_subscription(user_id: int, days: int) -> str:
    """
    Grant or extend premium subscription by N days.
    Returns: new expires_at timestamp string.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if already active
        async with db.execute(
            "SELECT expires_at FROM subscriptions WHERE user_id = ? AND datetime(expires_at) > datetime('now')",
            (user_id,)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            # Extend from existing expiration
            await db.execute(
                f"""
                UPDATE subscriptions
                SET expires_at = datetime(expires_at, '+{days} days')
                WHERE user_id = ?
                """,
                (user_id,)
            )
        else:
            # Start from now
            await db.execute(
                f"""
                INSERT INTO subscriptions (user_id, expires_at)
                VALUES (?, datetime('now', '+{days} days'))
                ON CONFLICT(user_id) DO UPDATE SET
                    expires_at = datetime('now', '+{days} days')
                """,
                (user_id,)
            )

        async with db.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,)) as cur:
            res = await cur.fetchone()
            await db.commit()
            return res[0] if res else ""

async def remove_user_subscription(user_id: int) -> bool:
    """Remove VIP subscription for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_total_premium_users() -> int:
    """Return count of active premium subscribers."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE datetime(expires_at) > datetime('now')"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def create_payment_request(
    user_id: int,
    user_name: str,
    user_handle: Optional[str],
    plan_id: str,
    plan_name: str,
    plan_days: int,
    amount: float,
    proof_file_id: Optional[str] = None,
    utr_or_note: Optional[str] = None,
    utr_number: Optional[str] = None
) -> int:
    """Create a new pending payment request."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO payment_requests (
                user_id, user_name, user_handle, plan_id, plan_name,
                plan_days, amount, proof_file_id, utr_or_note, utr_number, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (user_id, user_name, user_handle, plan_id, plan_name, plan_days, amount, proof_file_id, utr_or_note, utr_number)
        )
        req_id = cursor.lastrowid
        await db.commit()
        return req_id

async def is_utr_already_submitted(utr: str) -> bool:
    """
    Check if this exact 12-digit UTR number has already been entered or submitted before.
    Guarantees strict prevention of duplicate UTR submissions.
    """
    clean_utr = utr.strip()
    if not clean_utr:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """
            SELECT 1 FROM payment_requests 
            WHERE utr_number = ? OR (utr_or_note LIKE ? AND length(utr_or_note) >= 12)
            """,
            (clean_utr, f"%{clean_utr}%")
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_payment_request(request_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve payment request by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_payment_request_status(
    request_id: int,
    status: str,
    admin_message_id: Optional[int] = None,
    admin_chat_id: Optional[int] = None
) -> bool:
    """Update payment request status (APPROVED or REJECTED) with timestamp."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE payment_requests
            SET status = ?,
                processed_at = CURRENT_TIMESTAMP,
                admin_message_id = COALESCE(?, admin_message_id),
                admin_chat_id = COALESCE(?, admin_chat_id)
            WHERE id = ?
            """,
            (status, admin_message_id, admin_chat_id, request_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def get_pending_payment_requests() -> List[Dict[str, Any]]:
    """Return all payment requests with PENDING status."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payment_requests WHERE status = 'PENDING' ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_latest_pending_user_request(user_id: int) -> Optional[Dict[str, Any]]:
    """Check if user has an existing pending payment request."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payment_requests WHERE user_id = ? AND status = 'PENDING' ORDER BY id DESC LIMIT 1",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_admin_user_ids() -> List[int]:
    """
    Get all numeric admin IDs:
    Combines configured numeric ADMIN_IDS and resolves ADMIN_USERNAMES from users table.
    """
    admin_set = set(ADMIN_IDS)
    if ADMIN_USERNAMES:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            for uname in ADMIN_USERNAMES:
                async with db.execute(
                    "SELECT user_id FROM users WHERE LOWER(username) = ?",
                    (uname.lower(),)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        admin_set.add(row[0])
    return list(admin_set)

async def get_bot_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve setting value by key."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default

async def set_bot_setting(key: str, value: str) -> None:
    """Store or update setting value."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value)
        )
        await db.commit()

async def get_effective_admin_group_id() -> Optional[int]:
    """Retrieve configured admin group ID from config or database."""
    if ADMIN_GROUP_ID:
        return ADMIN_GROUP_ID
    val = await get_bot_setting("admin_group_id")
    if val:
        try:
            return int(val)
        except ValueError:
            return None
    return None


