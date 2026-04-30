from fastmcp import FastMCP
import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker-Pro")

# DATE NORMALIZER (accepts "today", "yesterday" or "YYYY-MM-DD")
def normalize_date(date_str):
    if not date_str:
        return datetime.today().strftime("%Y-%m-%d")

    date_str = str(date_str).lower()

    if date_str == "today":
        return datetime.today().strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        return (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    return date_str


# DB INIT 
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        # Expenses table
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT '',
                type TEXT DEFAULT 'expense'
            )
        """)

        # Fix old DB schema
        try:
            c.execute("ALTER TABLE expenses ADD COLUMN type TEXT DEFAULT 'expense'")
        except:
            pass

        # Debts table (for borrow/lend)
        c.execute("""
            CREATE TABLE IF NOT EXISTS debts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,   -- borrow or lend
                date TEXT NOT NULL,
                note TEXT DEFAULT '',
                status TEXT DEFAULT 'pending'
            )
        """)

init_db()


# ADD EXPENSE
@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    """
    Use this tool when user wants to add or record an expense.

    Examples:
    - "Add expense of 500 for food today"
    - "I spent 200 on travel"
    - "Add 1000 rupees shopping expense"

    Always extract:
    - date (default: today)
    - amount
    - category (food, travel, shopping etc.)
    """
    date = normalize_date(date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """INSERT INTO expenses(date, amount, category, subcategory, note, type)
               VALUES (?,?,?,?,?, 'expense')""",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}


# ADD CREDIT
@mcp.tool()
def add_credit(date, amount, category="Income", note=""):
    date = normalize_date(date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """INSERT INTO expenses(date, amount, category, subcategory, note, type)
               VALUES (?,?,?,?,?, 'credit')""",
            (date, amount, category, "", note)
        )
        return {"status": "ok", "id": cur.lastrowid}


# EDIT EXPENSE
@mcp.tool()
def edit_expense(id, date=None, amount=None, category=None, subcategory=None, note=None):
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "SELECT date, amount, category, subcategory, note FROM expenses WHERE id=?",
            (id,)
        )
        row = cur.fetchone()

        if not row:
            return {"error": "Expense not found"}

        updated_data = (
            normalize_date(date) if date is not None else row[0],
            amount if amount is not None else row[1],
            category if category is not None else row[2],
            subcategory if subcategory is not None else row[3],
            note if note is not None else row[4],
            id
        )

        c.execute("""
            UPDATE expenses
            SET date=?, amount=?, category=?, subcategory=?, note=?
            WHERE id=?
        """, updated_data)

        return {"status": "updated"}


# DELETE EXPENSE
@mcp.tool()
def delete_expense(id):
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("DELETE FROM expenses WHERE id=?", (id,))
        if cur.rowcount == 0:
            return {"error": "Expense not found"}
        return {"status": "deleted"}


# LIST EXPENSES
@mcp.tool()
def list_expenses(start_date, end_date):
    start_date = normalize_date(start_date)
    end_date = normalize_date(end_date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            SELECT id, date, amount, category, subcategory, note, type
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (start_date, end_date))

        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# SUMMARY
@mcp.tool()
def summarize(start_date, end_date, category=None):
    start_date = normalize_date(start_date)
    end_date = normalize_date(end_date)

    with sqlite3.connect(DB_PATH) as c:
        query = """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE type='expense' AND date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if category:
            query += " AND category=?"
            params.append(category)

        query += " GROUP BY category ORDER BY total_amount DESC"

        cur = c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# BALANCE
@mcp.tool()
def get_balance(start_date, end_date):
    start_date = normalize_date(start_date)
    end_date = normalize_date(end_date)

    with sqlite3.connect(DB_PATH) as c:
        income = c.execute(
            "SELECT SUM(amount) FROM expenses WHERE type='credit' AND date BETWEEN ? AND ?",
            (start_date, end_date)
        ).fetchone()[0] or 0

        expense = c.execute(
            "SELECT SUM(amount) FROM expenses WHERE type='expense' AND date BETWEEN ? AND ?",
            (start_date, end_date)
        ).fetchone()[0] or 0

        return {
            "income": income,
            "expense": expense,
            "balance": income - expense
        }


# MONTHLY GRAPH
@mcp.tool()
def monthly_graph():
    today = datetime.today()
    last_month = today - timedelta(days=30)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            SELECT date, SUM(amount)
            FROM expenses
            WHERE type='expense' AND date BETWEEN ? AND ?
            GROUP BY date
            ORDER BY date ASC
        """, (
            last_month.strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d")
        ))

        data = [{"date": r[0], "total": r[1]} for r in cur.fetchall()]

        return {
            "type": "line_chart",
            "title": "Last 30 Days Spending",
            "data": data,
            "x": "date",
            "y": "total"
        }


# CLEAR ALL EXPENSES
@mcp.tool()
def clear_all_expenses():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("DELETE FROM expenses")
    return {"status": "all expenses cleared"}


# RESET DATABASE (THIS WILL DELETE ALL DATA)
@mcp.tool()
def reset_database():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    return {"status": "database reset completely"}


# TOP CATEGORY 
@mcp.tool()
def top_category(start_date, end_date):
    start_date = normalize_date(start_date)
    end_date = normalize_date(end_date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE type='expense' AND date BETWEEN ? AND ?
            GROUP BY category
            ORDER BY total DESC
            LIMIT 1
        """, (start_date, end_date))

        row = cur.fetchone()
        if not row:
            return {"message": "No data"}

        return {"top_category": row[0], "amount": row[1]}


# DEBT SYSTEM 

# Borrow
@mcp.tool()
def borrow_money(person, amount, date, note=""):
    date = normalize_date(date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            INSERT INTO debts(person, amount, type, date, note)
            VALUES (?, ?, 'borrow', ?, ?)
        """, (person, amount, date, note))

        return {"status": "borrow recorded", "id": cur.lastrowid}


# Lend
@mcp.tool()
def lend_money(person, amount, date, note=""):
    date = normalize_date(date)

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            INSERT INTO debts(person, amount, type, date, note)
            VALUES (?, ?, 'lend', ?, ?)
        """, (person, amount, date, note))

        return {"status": "lend recorded", "id": cur.lastrowid}


# Settle
@mcp.tool()
def settle_debt(person, amount=None):
    with sqlite3.connect(DB_PATH) as c:
        if amount:
            cur = c.execute("""
                UPDATE debts
                SET status='settled'
                WHERE person=? AND amount=? AND status='pending'
            """, (person, amount))
        else:
            cur = c.execute("""
                UPDATE debts
                SET status='settled'
                WHERE person=? AND status='pending'
            """, (person,))

        if cur.rowcount == 0:
            return {"error": "No pending debt found"}

        return {"status": "debt settled"}


# List debts
@mcp.tool()
def list_debts():
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            SELECT id, person, amount, type, date, status
            FROM debts
            ORDER BY date ASC
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# Pending balance
@mcp.tool()
def pending_balance():
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("""
            SELECT person,
                   SUM(CASE WHEN type='borrow' THEN amount ELSE 0 END),
                   SUM(CASE WHEN type='lend' THEN amount ELSE 0 END)
            FROM debts
            WHERE status='pending'
            GROUP BY person
        """)

        result = []
        for row in cur.fetchall():
            result.append({
                "person": row[0],
                "you_owe": row[1] or 0,
                "they_owe": row[2] or 0
            })

        return result


# RESOURCE 
@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()


# RUN 
if __name__ == "__main__":
    mcp.run()