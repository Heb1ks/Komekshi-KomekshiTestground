import sqlite3


class Database:
    def __init__(self, db_path="database.py"):
        try:
            self.connection = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.connection.cursor()
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")

        self.createTableUsers()
        self.createTableDeadlines()
        self.createTableNotifications()
        self.createTablePhraseTimers()  # NEW

    def createTableUsers(self):
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS users(
                                user_id INTEGER PRIMARY KEY,
                                name_tag TEXT NOT NULL
                            );""")
        self.connection.commit()

    def createTableDeadlines(self):
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS deadlines(
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER NOT NULL,
                                deadline_name TEXT NOT NULL,
                                date_start TEXT NOT NULL,
                                date_over TEXT NOT NULL,
                                FOREIGN KEY(user_id) REFERENCES users(user_id)
                            );""")
        self.connection.commit()

    def createTableNotifications(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                deadline_id INTEGER NOT NULL,
                notify_time TEXT,
                interval_hours INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(deadline_id) REFERENCES deadlines(id)
            );
        """)
        self.connection.commit()

    def createTablePhraseTimers(self):  # NEW
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS phrase_timers(
                user_id INTEGER PRIMARY KEY,
                interval_minutes INTEGER,
                custom_time TEXT
            );
        """)
        self.connection.commit()

    def addUser(self, user_id: int, name: str):
        self.cursor.execute("INSERT OR IGNORE INTO users(user_id, name_tag) VALUES (?, ?)", (user_id, name))
        self.connection.commit()

    def createDeadline(self, user_id: int, deadline_name: str, date_start: str, date_over: str):
        self.cursor.execute("INSERT INTO deadlines(user_id, deadline_name, date_start, date_over) VALUES (?, ?, ?, ?)",
                            (user_id, deadline_name, date_start, date_over))
        self.connection.commit()

    def get_latest_deadline_id(self, user_id: int):
        self.cursor.execute("SELECT id FROM deadlines WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def showDeadlines(self, user_id: int):
        self.cursor.execute("SELECT * FROM deadlines WHERE user_id = ?", (user_id,))
        return self.cursor.fetchall()

    def removeDeadline(self, user_id: int, deadline_id: int):
        self.cursor.execute("DELETE FROM deadlines WHERE id = ? AND user_id = ?", (deadline_id, user_id))
        self.connection.commit()

    def add_notification(self, user_id: int, deadline_id: int, notify_time: str, interval_hours: int):
        self.cursor.execute("INSERT INTO notifications(user_id, deadline_id, notify_time, interval_hours) VALUES (?, ?, ?, ?)",
                            (user_id, deadline_id, notify_time, interval_hours))
        self.connection.commit()

    def get_due_notifications(self, current_time: str):
        self.cursor.execute("""
            SELECT n.user_id, d.deadline_name FROM notifications n
            JOIN deadlines d ON n.deadline_id = d.id
            WHERE n.notify_time = ?
        """, (current_time,))
        exact_matches = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT n.user_id, d.deadline_name, d.date_start, d.date_over, n.interval_hours
            FROM notifications n
            JOIN deadlines d ON n.deadline_id = d.id
            WHERE n.interval_hours IS NOT NULL
        """)
        interval_matches = []
        now = sqlite3.datetime.datetime.now()
        for user_id, name, date_start, date_over, interval in self.cursor.fetchall():
            try:
                start = sqlite3.datetime.datetime.strptime(date_start, "%Y-%m-%d")
                over = sqlite3.datetime.datetime.strptime(date_over, "%Y-%m-%d")
                if start <= now <= over:
                    hours_passed = (now - start).total_seconds() / 3600
                    if abs((hours_passed % interval) * 60) < 1:
                        interval_matches.append((user_id, name))
            except:
                continue

        return exact_matches + interval_matches

    def set_phrase_timer(self, user_id: int, interval_minutes: int = None, custom_time: str = None):  # NEW
        self.cursor.execute("""
            INSERT INTO phrase_timers(user_id, interval_minutes, custom_time)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                interval_minutes = excluded.interval_minutes,
                custom_time = excluded.custom_time;
        """, (user_id, interval_minutes, custom_time))
        self.connection.commit()

    def get_due_phrase_users(self, current_time: str):  # NEW
        self.cursor.execute("SELECT user_id FROM phrase_timers WHERE custom_time = ?", (current_time,))
        exact = [row[0] for row in self.cursor.fetchall()]

        self.cursor.execute("SELECT user_id, interval_minutes FROM phrase_timers WHERE interval_minutes IS NOT NULL")
        now = sqlite3.datetime.datetime.now()
        interval_users = []
        for user_id, interval in self.cursor.fetchall():
            minutes_passed = (now.hour * 60 + now.minute)
            if minutes_passed % interval == 0:
                interval_users.append(user_id)

        return exact + interval_users
