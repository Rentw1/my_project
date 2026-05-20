import sqlite3
import os
from datetime import date, datetime, timedelta
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "calorie_bot.db")


class Database:
    def __init__(self):
        self.path = DB_PATH
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    goal INTEGER DEFAULT 2000,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT,
                    calories INTEGER,
                    protein REAL DEFAULT 0,
                    fat REAL DEFAULT 0,
                    carbs REAL DEFAULT 0,
                    weight INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
            """)

    def ensure_user(self, user_id: int, name: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(id, name) VALUES(?, ?)",
                (user_id, name)
            )

    def get_goal(self, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT goal FROM users WHERE id=?", (user_id,)).fetchone()
            return row["goal"] if row else 2000

    def set_goal(self, user_id: int, goal: int):
        with self._conn() as conn:
            conn.execute("UPDATE users SET goal=? WHERE id=?", (goal, user_id))

    def add_meal(self, user_id: int, data: dict) -> int:
        """Returns new meal id."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO meals(user_id, name, calories, protein, fat, carbs, weight)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    user_id,
                    data.get("name", "Блюдо"),
                    int(data.get("calories", 0)),
                    float(data.get("protein", 0)),
                    float(data.get("fat", 0)),
                    float(data.get("carbs", 0)),
                    int(data.get("weight", 0)),
                )
            )
            return cur.lastrowid

    def get_meal_by_id(self, user_id: int, meal_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM meals WHERE id=? AND user_id=?", (meal_id, user_id)
            ).fetchone()
            return dict(row) if row else None

    def update_meal_calories(self, user_id: int, meal_id: int, new_calories: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE meals SET calories=? WHERE id=? AND user_id=?",
                (new_calories, meal_id, user_id)
            )

    def delete_meal_by_id(self, user_id: int, meal_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM meals WHERE id=? AND user_id=?", (meal_id, user_id)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM meals WHERE id=?", (meal_id,))
                return dict(row)
            return None

    def get_today_meals(self, user_id: int) -> list:
        today = date.today().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM meals
                   WHERE user_id=? AND date(created_at)=?
                   ORDER BY created_at ASC""",
                (user_id, today)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_today_macros(self, user_id: int) -> dict:
        today = date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT
                     COALESCE(SUM(protein),0) as protein,
                     COALESCE(SUM(fat),0) as fat,
                     COALESCE(SUM(carbs),0) as carbs
                   FROM meals WHERE user_id=? AND date(created_at)=?""",
                (user_id, today)
            ).fetchone()
            return {
                "protein": round(row["protein"]),
                "fat": round(row["fat"]),
                "carbs": round(row["carbs"]),
            } if row else {"protein": 0, "fat": 0, "carbs": 0}

    def get_recent_meals(self, user_id: int, limit: int = 10) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM meals WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_week_summary(self, user_id: int) -> list:
        seven_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT date(created_at) as date, SUM(calories) as total_calories
                   FROM meals
                   WHERE user_id=? AND date(created_at)>=?
                   GROUP BY date(created_at)
                   ORDER BY date ASC""",
                (user_id, seven_days_ago)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_last_meal(self, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM meals WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM meals WHERE id=?", (row["id"],))
                return dict(row)
            return None

    def get_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM meals WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
            if total == 0:
                return {"total_meals": 0}

            daily = conn.execute(
                """SELECT date(created_at) as d, SUM(calories) as s
                   FROM meals WHERE user_id=? GROUP BY d""",
                (user_id,)
            ).fetchall()

            sums = [r["s"] for r in daily]
            best_day_row = max(daily, key=lambda r: r["s"])

            return {
                "total_meals": total,
                "days_tracked": len(daily),
                "avg_daily": round(sum(sums) / len(sums)),
                "max_daily": max(sums),
                "min_daily": min(sums),
                "best_day": best_day_row["d"],
            }
