from flask import render_template, Flask, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import sqlite3
import requests
import secrets
import logging
import urllib.parse

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB_FILE = os.environ.get("DB_FILE", "website.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")

STYLE = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #000; color: #fff; font-family: Arial, sans-serif; padding: 20px; }
.box { max-width: 500px; margin: auto; background: #0d1117; padding: 20px; border-radius: 12px; border: 1px solid #222; }
input, select, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #334155; background: #111827; color: #fff; }
button { background: #14b8a6; font-weight: bold; cursor: pointer; border: none; }
a { color: #14b8a6; text-decoration: none; }
.card { background: #111827; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #222; }
</style>
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def now():
    return datetime.now().isoformat()

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password TEXT,
            balance REAL DEFAULT 0,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            username TEXT,
            game TEXT,
            package TEXT,
            game_id TEXT,
            server_id TEXT,
            payment TEXT,
            transaction_number TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def generate_order_id():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = secrets.token_hex(3).upper()
    return f"ORD-{timestamp}-{random_part}"

def clean_text(value):
    return str(value).strip() if value else ""

def send_telegram_message(chat_id, text):
    if not BOT_TOKEN or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=20)
        return res.ok
    except Exception as exc:
        logger.exception("Telegram send error: %s", exc)
        return False

def send_order_to_owner(order):
    message = (
        "🛒 <b>New Order Received</b>\n\n"
        f"Order ID: {order.get('order_id')}\n"
        f"Username: {order.get('username')}\n"
        f"Game: {order.get('game')}\n"
        f"Package: {order.get('package')}\n"
        f"Game ID: {order.get('game_id')}\n"
        f"Server ID: {order.get('server_id')}\n"
        f"Payment: {order.get('payment')}\n"
        f"Transaction: {order.get('transaction')}"
    )
    return send_telegram_message(OWNER_CHAT_ID, message)

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return f"""<!DOCTYPE html><html><head>{STYLE}</head><body>
        <div class="box"><h1>🔐 Login</h1>
        <form method="POST">
        <input type="text" name="username" placeholder="Username" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Login</button>
        </form>
        <p><a href="/register">Register New Account</a></p>
        </div></body></html>"""

    username = clean_text(request.form.get("username"))
    password = clean_text(request.form.get("password"))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))

    return f"❌ Invalid Login. <a href='/login'>Try again</a>"

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return f"""<!DOCTYPE html><html><head>{STYLE}</head><body>
        <div class="box"><h1>📝 Register</h1>
        <form method="POST">
        <input type="text" name="username" placeholder="Username" required>
        <input type="email" name="email" placeholder="Email">
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Register</button>
        </form>
        </div></body></html>"""

    username = clean_text(request.form.get("username"))
    email = clean_text(request.form.get("email"))
    password = clean_text(request.form.get("password"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password, created_at) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), now())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "Username already exists!"
    conn.close()

    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db()
    user = conn.execute("SELECT balance FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    balance = user["balance"] if user else 0

    return f"""<!DOCTYPE html><html><head>{STYLE}</head><body>
    <div class="box">
        <h1>🏠 Dashboard</h1>
        <div class="card">
            <h2>👤 {username}</h2>
            <p>💰 Balance: <strong>{balance:,.0f} Ks</strong></p>
        </div>
        <div class="card"><a href="/packages/Mobile Legends">💎 Mobile Legends</a></div>
        <div class="card"><a href="/packages/PUBG Mobile">🪙 PUBG Mobile</a></div>
        <div class="card"><a href="/orders">📦 My Orders</a></div>
        <div class="card"><a href="/profile">👤 Profile</a></div>
        <div class="card"><a href="/logout">🚪 Logout</a></div>
    </div></body></html>"""

@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db()
    user = conn.execute("SELECT username, email, balance, created_at FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    return f"""<!DOCTYPE html><html><head>{STYLE}</head><body>
    <div class="box">
        <h1>👤 Profile</h1>
        <div class="card">
            <p>Name: <strong>{user['username']}</strong></p>
            <p>Email: <strong>{user['email'] or '-'}</strong></p>
            <p>Balance: <strong>{user['balance']:,.0f} Ks</strong></p>
            <p>Joined: <strong>{user['created_at']}</strong></p>
        </div>
        <p><a href="/dashboard">← Back to Dashboard</a></p>
    </div></body></html>"""

@app.route("/packages/<game>")
def packages(game):
    if "username" not in session:
        return redirect(url_for("login"))

    game_list = {
        "Mobile Legends": [("86 Diamonds", 5600), ("172 Diamonds", 10800)],
        "PUBG Mobile": [("60 UC", 600), ("325 UC", 3250)]
    }

    selected = game_list.get(game, [])
    html = f"<h1>{game} Packages</h1>"
    for item, price in selected:
        html += f"""<div class="card">
            <strong>{item}</strong> - {price:,} Ks 
            <a href="/place_order?game={urllib.parse.quote(game)}&package={urllib.parse.quote(item)}">[Order]</a>
        </div>"""

    return f"""<!DOCTYPE html><html><head>{STYLE}</head><body><div class="box">{html}<p><a href="/dashboard">Back</a></p></div></body></html>"""

@app.route("/place_order", methods=["GET", "POST"])
def place_order():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        order_id = generate_order_id()
        game = request.form.get("game")
        package = request.form.get("package")
        game_id = request.form.get("game_id")
        server_id = request.form.get("server_id")
        payment = request.form.get("payment")
        transaction = request.form.get("transaction")

        conn = get_db()
        conn.execute("""
            INSERT INTO orders (order_id, username, game, package, game_id, server_id, payment, transaction_number, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
        """, (order_id, session["username"], game, package, game_id, server_id, payment, transaction, now()))
        conn.commit()
        conn.close()

        send_order_to_owner({
            "order_id": order_id,
            "username": session["username"],
            "game": game,
            "package": package,
            "game_id": game_id,
            "server_id": server_id,
            "payment": payment,
            "transaction": transaction
        })

        return f"""<!DOCTYPE html><html><head>{STYLE}</head><body><div class="box"><h1>✅ Order Submitted</h1><p>Order ID: {order_id}</p><a href="/orders">View Orders</a></div></body></html>"""

    game = request.args.get("game", "")
    package = request.args.get("package", "")

    return f"""<!DOCTYPE html><html><head>{STYLE}</head><body><div class="box">
    <h1>🛒 Place Order</h1>
    <form method="POST">
        <input type="hidden" name="game" value="{game}">
        <input type="hidden" name="package" value="{package}">
        <p>Selected: <strong>{game} - {package}</strong></p>
        <input type="text" name="game_id" placeholder="Game ID" required>
        <input type="text" name="server_id" placeholder="Server ID">
        <select name="payment" required>
            <option value="KPay">KPay</option>
            <option value="Wave">Wave Money</option>
        </select>
        <input type="text" name="transaction" placeholder="Transaction Last 5 digits" required>
        <button type="submit">Submit Order</button>
    </form>
    </div></body></html>"""

@app.route("/orders")
def orders():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    order_list = conn.execute("SELECT * FROM orders WHERE username = ? ORDER BY id DESC", (session["username"],)).fetchall()
    conn.close()

    items_html = ""
    for o in order_list:
        items_html += f"""<div class="card">
            <p><strong>#{o['order_id']}</strong> - {o['game']} ({o['package']})</p>
            <p>Status: <span>{o['status']}</span></p>
        </div>"""

    return f"""<!DOCTYPE html><html><head>{STYLE}</head><body><div class="box"><h1>📦 Order History</h1>{items_html or '<p>No orders yet.</p>'}<p><a href="/dashboard">Back</a></p></div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
