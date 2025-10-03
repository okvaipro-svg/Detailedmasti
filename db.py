import sqlite3

def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER DEFAULT 2,
            referrals INTEGER DEFAULT 0,
            protected INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            ref_by INTEGER DEFAULT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            result TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, ref_by=None):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, ref_by) VALUES (?, ?)", (user_id, ref_by))
    conn.commit()
    conn.close()

def update_credits(user_id, delta):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()

def log_query(user_id, query, result):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, query, result) VALUES (?, ?, ?)", (user_id, query, result))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def set_ban(user_id, ban=1):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET banned = ? WHERE user_id = ?", (ban, user_id))
    conn.commit()
    conn.close()

def set_protected(user_id, val=1):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET protected = ? WHERE user_id = ?", (val, user_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM logs")
    searches = c.fetchone()[0]
    conn.close()
    return users, searches

def get_referrals(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_sudo_list():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id IN (7924074157,5294360309,7905267752)")
    lst = c.fetchall()
    conn.close()
    return [x[0] for x in lst]