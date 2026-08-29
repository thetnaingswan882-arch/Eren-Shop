from flask import render_template
from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from datetime import datetime

import os
import sqlite3
import requests
import json
import threading
import time

import hashlib
import hmac
import base64
import urllib.parse
import secrets
import logging

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DB_FILE = os.environ.get(
    "DB_FILE",
    "website.db"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")

FLASH_API_ID = os.environ.get("FLASH_API_ID", "")
FLASH_API_KEY = os.environ.get("FLASH_API_KEY", "")

SMILE_ONE_API_KEY = os.environ.get(
    "SMILE_ONE_API_KEY",
    ""
)

SMILE_ONE_SECRET = os.environ.get(
    "SMILE_ONE_SECRET",
    ""
)

EMAIL_HOST = os.environ.get(
    "EMAIL_HOST",
    ""
)

EMAIL_PORT = int(
    os.environ.get(
        "EMAIL_PORT",
        "587"
    )
)

EMAIL_USERNAME = os.environ.get(
    "EMAIL_USERNAME",
    ""
)

EMAIL_PASSWORD = os.environ.get(
    "EMAIL_PASSWORD",
    ""
)

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():
    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
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
            amount REAL,
            status TEXT,
            screenshot TEXT,
            transaction_number TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


def generate_order_id():
    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    random_part = secrets.token_hex(3).upper()

    return f"ORD-{timestamp}-{random_part}"


def safe_float(value, default=0):
    try:
        return float(value)
    except (
        TypeError,
        ValueError
    ):
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except (
        TypeError,
        ValueError
    ):
        return default


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def get_setting(key, default=None):
    conn = get_db()

    row = conn.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    conn.close()

    if row is None:
        return default

    return row["value"]


def set_setting(key, value):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (
            key,
            str(value)
        )
    )

    conn.commit()
    conn.close()


def send_telegram_message(
    chat_id,
    text
):
    if not BOT_TOKEN:
        logger.warning(
            "BOT_TOKEN is not configured"
        )
        return False

    if not chat_id:
        logger.warning(
            "Telegram chat_id is empty"
        )
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        response.raise_for_status()

        return True

    except Exception as exc:
        logger.exception(
            "Telegram send error: %s",
            exc
        )

        return False


def send_order_to_owner(order):
    order_id = order.get(
        "order_id",
        ""
    )

    game = order.get(
        "game",
        ""
    )

    package = order.get(
        "package",
        ""
    )

    game_id = order.get(
        "game_id",
        ""
    )

    server_id = order.get(
        "server_id",
        ""
    )

    payment = order.get(
        "payment",
        ""
    )

    amount = order.get(
        "amount",
        0
    )

    username = order.get(
        "username",
        ""
    )

    transaction_number = order.get(
        "transaction_number",
        ""
    )

    message = (
        "🛒 New Order\n\n"
        f"Order ID: {order_id}\n"
        f"Username: {username}\n"
        f"Game: {game}\n"
        f"Package: {package}\n"
        f"Game ID: {game_id}\n"
        f"Server ID: {server_id}\n"
        f"Payment: {payment}\n"
        f"Amount: {amount}\n"
        f"Transaction: {transaction_number}"
    )

    return send_telegram_message(
        OWNER_CHAT_ID,
        message
    )


init_db()

def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return user


def login_required():
    return get_current_user() is not None


@app.route("/")
def index():
    return render_template(
        "index.html"
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template(
            "login.html"
        )

    username = clean_text(
        request.form.get("username")
    )

    password = clean_text(
        request.form.get("password")
    )

    if not username or not password:
        return render_template(
            "login.html",
            error="Username and password are required."
        )

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    conn.close()

    if user is None:
        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    if not check_password_hash(
        user["password"],
        password
    ):
        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect(
        url_for("index")
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template(
            "register.html"
        )

    username = clean_text(
        request.form.get("username")
    )

    password = clean_text(
        request.form.get("password")
    )

    confirm_password = clean_text(
        request.form.get("confirm_password")
    )

    if not username or not password:
        return render_template(
            "register.html",
            error="All fields are required."
        )

    if password != confirm_password:
        return render_template(
            "register.html",
            error="Passwords do not match."
        )

    if len(password) < 6:
        return render_template(
            "register.html",
            error="Password must be at least 6 characters."
        )

    hashed_password = generate_password_hash(
        password
    )

    conn = get_db()

    try:
        cursor = conn.execute(
            """
            INSERT INTO users (
                username,
                password,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                hashed_password,
                datetime.now().isoformat()
            )
        )

        conn.commit()

        user_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.close()

        return render_template(
            "register.html",
            error="Username already exists."
        )

    conn.close()

    session["user_id"] = user_id
    session["username"] = username

    return redirect(
        url_for("index")
    )


@app.route("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("index")
    )


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(
            url_for("login")
        )

    username = session.get(
        "username",
        ""
    )

    conn = get_db()

    orders = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE username = ?
        ORDER BY id DESC
        """,
        (username,)
    ).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        orders=orders,
        username=username
    )


def validate_order_data(data):
    game = clean_text(
        data.get("game")
    )

    package = clean_text(
        data.get("package")
    )

    game_id = clean_text(
        data.get("game_id")
    )

    server_id = clean_text(
        data.get("server_id")
    )

    payment = clean_text(
        data.get("payment")
    )

    amount = safe_float(
        data.get("amount"),
        0
    )

    transaction_number = clean_text(
        data.get(
            "transaction_number"
        )
    )

    errors = []

    if not game:
        errors.append(
            "Game is required."
        )

    if not package:
        errors.append(
            "Package is required."
        )

    if not game_id:
        errors.append(
            "Game ID is required."
        )

    if not payment:
        errors.append(
            "Payment method is required."
        )

    if amount <= 0:
        errors.append(
            "Invalid amount."
        )

    if not transaction_number:
        errors.append(
            "Transaction number is required."
        )

    return errors


def save_order(
    order_id,
    username,
    game,
    package,
    game_id,
    server_id,
    payment,
    amount,
    screenshot,
    transaction_number,
    status="Pending"
):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO orders (
            order_id,
            username,
            game,
            package,
            game_id,
            server_id,
            payment,
            amount,
            status,
            screenshot,
            transaction_number,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            order_id,
            username,
            game,
            package,
            game_id,
            server_id,
            payment,
            amount,
            status,
            screenshot,
            transaction_number,
            datetime.now().isoformat()
        )
    )

    conn.commit()
    conn.close()


def get_order(order_id):
    conn = get_db()

    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE order_id = ?
        """,
        (order_id,)
    ).fetchone()

    conn.close()

    return order


@app.route("/order", methods=["POST"])
def order():
    data = request.form.to_dict()

    errors = validate_order_data(
        data
    )

    if errors:
        return {
            "success": False,
            "errors": errors
        }, 400

    username = clean_text(
        data.get("username")
        or session.get(
            "username",
            "Guest"
        )
    )

    game = clean_text(
        data.get("game")
    )

    package = clean_text(
        data.get("package")
    )

    game_id = clean_text(
        data.get("game_id")
    )

    server_id = clean_text(
        data.get("server_id")
    )

    payment = clean_text(
        data.get("payment")
    )

    amount = safe_float(
        data.get("amount")
    )

    transaction_number = clean_text(
        data.get(
            "transaction_number"
        )
    )

    screenshot_file = request.files.get(
        "screenshot"
    )

    screenshot = ""

    if screenshot_file:
        screenshot = clean_text(
            screenshot_file.filename
        )

    order_id = generate_order_id()

    save_order(
        order_id=order_id,
        username=username,
        game=game,
        package=package,
        game_id=game_id,
        server_id=server_id,
        payment=payment,
        amount=amount,
        screenshot=screenshot,
        transaction_number=transaction_number
    )

    order_data = {
        "order_id": order_id,
        "username": username,
        "game": game,
        "package": package,
        "game_id": game_id,
        "server_id": server_id,
        "payment": payment,
        "amount": amount,
        "transaction_number": transaction_number
    }

    try:
        send_order_to_owner(
            order_data
        )
    except Exception as exc:
        logger.exception(
            "Could not send order notification: %s",
            exc
        )

    return {
        "success": True,
        "order_id": order_id,
        "message": "Order submitted successfully."
    }


@app.route("/order/<order_id>")
def order_status(order_id):
    order_id = clean_text(
        order_id
    )

    order = get_order(
        order_id
    )

    if order is None:
        return {
            "success": False,
            "message": "Order not found."
        }, 404

    return {
        "success": True,
        "order": dict(order)
    }

server.login(
            EMAIL_ADDRESS,
            EMAIL_PASSWORD
        )
        server.sendmail(
            EMAIL_ADDRESS,
            email,
            msg.as_string()
        )
        server.quit()

        return True

    except Exception as e:
        print(
            "Email Error:",
            e
        )
        return False


@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():
    error = ""
    success = ""

    if request.method == "POST":
        email = request.form.get(
            "email",
            ""
        ).strip()

        if not email:
            error = "⚠️ Email ဖြည့်ပါ"

        else:
            conn = get_db()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT username
                FROM users
                WHERE email = ?
                """,
                (email,)
            )

            user = cursor.fetchone()

            if not user:
                conn.close()

                error = (
                    "❌ ဒီ Email နဲ့ Account မတွေ့ပါ"
                )

            else:
                token = secrets.token_urlsafe(
                    32
                )

                created_at = datetime.now()
                expires_at = (
                    created_at
                    + timedelta(hours=1)
                )

                cursor.execute(
                    """
                    INSERT INTO password_resets
                    (
                        email,
                        token,
                        created_at,
                        expires_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        email,
                        token,
                        created_at.isoformat(),
                        expires_at.isoformat()
                    )
                )

                conn.commit()
                conn.close()

                if send_reset_email(
                    email,
                    token
                ):
                    success = (
                        "✅ Password reset link ကို "
                        "Email ပို့ပြီးပါပြီ"
                    )
                else:
                    error = (
                        "❌ Email ပို့မရပါ"
                    )

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta
 name="viewport"
 content="width=device-width,initial-scale=1"
>
<title>Forgot Password</title>
{STYLE}
</head>

<body>

<div class="box">

<h1>🔑 Forgot Password</h1>

<form method="POST">

<input
 type="email"
 name="email"
 placeholder="📧 Your Gmail"
 required
>

<button
 class="green"
 type="submit"
>
📩 Send Reset Link
</button>

</form>

<p class="error">
{error}
</p>

<p class="success">
{success}
</p>

<p>
<a href="/login">
← Back to Login
</a>
</p>

</div>

</body>
</html>
"""


@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):
    error = ""
    success = ""

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM password_resets
        WHERE token = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (token,)
    )

    reset = cursor.fetchone()

    if not reset:
        conn.close()

        return """
        <h2>❌ Invalid reset link</h2>
        """

    try:
        expires_at = datetime.fromisoformat(
            reset["expires_at"]
        )

    except Exception:
        conn.close()

        return """
        <h2>❌ Invalid reset link</h2>
        """

    if datetime.now() > expires_at:
        conn.close()

        return """
        <h2>❌ Reset link expired</h2>
        """

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm",
            ""
        )

        if len(password) < 6:
            error = (
                "⚠️ Password အနည်းဆုံး 6 လုံး"
            )

        elif password != confirm:
            error = (
                "⚠️ Password မတူပါ"
            )

        else:
            hashed_password = (
                generate_password_hash(
                    password
                )
            )

            cursor.execute(
                """
                UPDATE users
                SET password = ?
                WHERE email = ?
                """,
                (
                    hashed_password,
                    reset["email"]
                )
            )

            cursor.execute(
                """
                DELETE FROM password_resets
                WHERE token = ?
                """,
                (token,)
            )

            conn.commit()
            conn.close()

            success = (
                "✅ Password ပြောင်းပြီးပါပြီ"
            )

            return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta
 name="viewport"
 content="width=device-width,initial-scale=1"
>
<title>Password Reset</title>
{STYLE}
</head>

<body>

<div class="box">

<h1>✅ Password Reset</h1>

<p class="success">
{success}
</p>

<p>
<a href="/login">
🔐 Login Now
</a>
</p>

</div>

</body>
</html>
"""

    conn.close()

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta
 name="viewport"
 content="width=device-width,initial-scale=1"
>
<title>Reset Password</title>
{STYLE}
</head>

<body>

<div class="box">

<h1>🔑 New Password</h1>

<form method="POST">

<input
 type="password"
 name="password"
 placeholder="🔒 New Password"
 required
>

<input
 type="password"
 name="confirm"
 placeholder="🔒 Confirm Password"
 required
>

<button
 class="green"
 type="submit"
>
🔐 Reset Password
</button>

</form>

<p class="error">
{error}
</p>

</div>

</body>
</html>
"""


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    username = session["username"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT balance
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    user = cursor.fetchone()

    balance = (
        user["balance"]
        if user
        else 0
    )

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (username,)
    )

    orders = cursor.fetchall()

    conn.close()

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<meta
 name="viewport"
 content="width=device-width,initial-scale=1"
>

<title>Dashboard</title>

{STYLE}

</head>

<body>

<div class="box">

<h1>🏠 Dashboard</h1>

<div class="card">

<h2>👤 {username}</h2>

<div class="balance">
💰 {balance:,} MMK
</div>

</div>

<div class="card">

<a href="/topup">
💎 Game Top Up
</a>

</div>

<div class="card">

<a href="/deposit">
💰 Deposit
</a>

</div>

<div class="card">

<a href="/orders">
📦 My Orders
</a>

</div>

<div class="card">

<a href="/notifications">
🔔 Notifications
</a>

</div>

<div class="card">

<a href="/logout">
🚪 Logout
</a>

</div>

</div>

</body>
</html>
"""

<a href="/packages/Smile One Code BRL"
           class="product-card"
           style="background: #f59e0b;">

            <img src="/static/smileone.png">

            <div class="name">
                Smile One Code BRL
            </div>

            <span class="sold">
                {smile_brl_sold:,} Sold
            </span>

        </a>

        <a href="/packages/Smile One Coin PHP"
           class="product-card"
           style="background: #f59e0b;">

            <img src="/static/smileone.png">

            <div class="name">
                Smile One Coin PHP
            </div>

            <span class="sold">
                {smile_php_sold:,} Sold
            </span>

        </a>

    </div>


    <div class="bottom-nav">

        <a
            href="/dashboard"
            class="active"
        >
            <span class="icon">🏠</span>
            Home
        </a>

        <a href="/orders">

            <span class="icon">
                📦
            </span>

            Orders

        </a>

        <a href="/deposit">

            <span class="icon">
                💰
            </span>

            Deposit

        </a>

        <a href="/profile">

            <span class="icon">
                👤
            </span>

            Profile

        </a>

    </div>


    <script>

        function openNotice() {

            document.getElementById(
                "noticeModal"
            ).style.display = "flex";

        }


        function closeNotice() {

            document.getElementById(
                "noticeModal"
            ).style.display = "none";

        }


        function closeNoticeOutside(event) {

            if (
                event.target.id ===
                "noticeModal"
            ) {

                closeNotice();

            }

        }

    </script>

</body>
</html>
"""


# ==================================================
# PROFILE
# ==================================================

@app.route("/profile")
def profile():

    if "username" not in session:

        return redirect(
            url_for("login")
        )

    username = session["username"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            username,
            email,
            balance,
            device_name,
            created_at
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    user = cursor.fetchone()

    conn.close()

    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>Profile</title>

{STYLE}

</head>

<body>

<div class="box">

<h1>👤 Profile</h1>

<div class="card">

<p>
👤 Username:
<strong>
{user["username"]}
</strong>
</p>

<p>
📧 Email:
<strong>
{user["email"] or "-"}
</strong>
</p>

<p>
💰 Balance:
<strong>
{int(user["balance"] or 0):,} Ks
</strong>
</p>

<p>
📱 Device:
<strong>
{user["device_name"] or "Unknown"}
</strong>
</p>

<p>
📅 Created:
<strong>
{user["created_at"]}
</strong>
</p>

</div>

<div class="card">

<a href="/change-password">
🔐 Change Password
</a>

</div>

<div class="card">

<a href="/dashboard">
⬅️ Back to Dashboard
</a>

</div>

</div>

</body>

</html>
"""


# ==================================================
# CHANGE PASSWORD
# ==================================================

@app.route(
    "/change-password",
    methods=["GET", "POST"]
)
def change_password():

    if "username" not in session:

        return redirect(
            url_for("login")
        )

    username = session["username"]

    message = ""
    error = ""

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT password
            FROM users
            WHERE username = ?
            """,
            (username,)
        )

        user = cursor.fetchone()

        if not user:

            conn.close()

            session.clear()

            return redirect(
                url_for("login")
            )

        if not check_password_hash(
            user["password"],
            current_password
        ):

            error = (
                "❌ Current Password မှားနေပါတယ်"
            )

        elif len(new_password) < 6:

            error = (
                "⚠️ Password အနည်းဆုံး 6 လုံး"
            )

        elif new_password != confirm_password:

            error = (
                "⚠️ Password မတူပါ"
            )

        else:

            hashed = generate_password_hash(
                new_password
            )

            cursor.execute(
                """
                UPDATE users
                SET password = ?
                WHERE username = ?
                """,
                (
                    hashed,
                    username
                )
            )

            conn.commit()

            message = (
                "✅ Password ပြောင်းပြီးပါပြီ"
            )

        conn.close()

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>Change Password</title>

{STYLE}

</head>

<body>

<div class="box">

<h1>🔐 Change Password</h1>

<form method="POST">

<input
    type="password"
    name="current_password"
    placeholder="🔒 Current Password"
    required
>

<input
    type="password"
    name="new_password"
    placeholder="🔒 New Password"
    required
>

<input
    type="password"
    name="confirm_password"
    placeholder="🔒 Confirm Password"
    required
>

<button
    class="green"
    type="submit"
>
    🔐 Change Password
</button>

</form>

<p class="error">
{error}
</p>

<p class="success">
{message}
</p>

<div class="card">

<a href="/profile">
⬅️ Back to Profile
</a>

</div>

</div>

</body>

</html>
"""

.tab-btn.active {
            background: #14b8a6;
            color: #fff;
        }

        .tab-btn:not(.active) {
            background: #1e293b;
            color: #94a3b8;
        }

        .pay-card {
            background: #0d1117;
            border: 1px solid #222;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .pay-card small {
            color: #94a3b8;
            display: block;
            margin-top: 4px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 7px;
            color: #cbd5e1;
            font-size: 14px;
        }

        .form-group input,
        .form-group select {
            width: 100%;
            padding: 13px;
            border-radius: 10px;
            border: 1px solid #334155;
            background: #111827;
            color: #fff;
            outline: none;
        }

        .form-group input:focus,
        .form-group select:focus {
            border-color: #14b8a6;
        }

        .submit-btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 10px;
            background: #14b8a6;
            color: #fff;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }

        .submit-btn:active {
            transform: scale(0.98);
        }

        .message {
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }

        .message.success {
            background: rgba(74, 222, 128, 0.15);
            color: #4ade80;
            border: 1px solid #166534;
        }

        .message.error {
            background: rgba(248, 113, 113, 0.15);
            color: #f87171;
            border: 1px solid #991b1b;
        }

        .payment-info {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .payment-info h3 {
            color: #14b8a6;
            margin-bottom: 10px;
        }

        .payment-info p {
            margin: 6px 0;
            color: #cbd5e1;
        }

        .payment-info strong {
            color: #fff;
        }

        .history-title {
            color: #14b8a6;
            margin: 25px 0 12px;
            font-size: 18px;
        }

        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px;
            z-index: 999;
        }

        .bottom-nav a {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }

        .bottom-nav a .icon {
            font-size: 22px;
            margin-bottom: 2px;
        }

        .bottom-nav a.active {
            color: #0d1117;
            font-weight: bold;
        }
    </style>
</head>

<body>

<div class="header">
    <h1>💰 Recharge Wallet</h1>
</div>

<div class="container">

    <div class="pay-card">
        <div>
            <small>Current Balance</small>
            <strong style="font-size:22px;">
                {wallet_balance:,} Ks
            </strong>
        </div>
    </div>

    <div class="tabs">

        <a
            href="/wallet?tab=deposit"
            class="tab-btn {
                'active'
                if active_tab == 'deposit'
                else ''
            }"
        >
            💰 Deposit
        </a>

        <a
            href="/wallet?tab=history"
            class="tab-btn {
                'active'
                if active_tab == 'history'
                else ''
            }"
        >
            📜 History
        </a>

    </div>

    {
        f'<div class="message {message_type}">{message}</div>'
        if message
        else ''
    }

    {
        '''
        <div class="payment-info">

            <h3>💳 Payment Information</h3>

            <p>
                Payment:
                <strong>KPay / Wave Money</strong>
            </p>

            <p>
                Account:
                <strong>Admin Payment</strong>
            </p>

            <p>
                Minimum Deposit:
                <strong>1,000 Ks</strong>
            </p>

        </div>

        <form
            method="POST"
            enctype="multipart/form-data"
        >

            <input
                type="hidden"
                name="action"
                value="deposit"
            >

            <div class="form-group">

                <label>
                    💵 Amount
                </label>

                <input
                    type="number"
                    name="amount"
                    min="1000"
                    placeholder="ဥပမာ - 5000"
                    required
                >

            </div>

            <div class="form-group">

                <label>
                    🔢 Transaction နောက်ဆုံး 5 လုံး
                </label>

                <input
                    type="text"
                    name="transaction"
                    maxlength="5"
                    inputmode="numeric"
                    placeholder="12345"
                    required
                >

            </div>

            <div class="form-group">

                <label>
                    📱 Telegram Username
                </label>

                <input
                    type="text"
                    name="telegram_username"
                    placeholder="@username"
                    required
                >

            </div>

            <div class="form-group">

                <label>
                    📸 Payment Screenshot
                </label>

                <input
                    type="file"
                    name="screenshot"
                    accept="image/*"
                    required
                >

            </div>

            <button
                class="submit-btn"
                type="submit"
            >
                📤 Submit Deposit
            </button>

        </form>
        '''
        if active_tab == 'deposit'
        else
        f'''
        <h2 class="history-title">
            📜 Recharge History
        </h2>

        {history_html}
        '''
    }

</div>

<div class="bottom-nav">

    <a href="/dashboard">

        <span class="icon">
            🏠
        </span>

        Shop

    </a>

    <a
        href="/wallet"
        class="active"
    >

        <span class="icon">
            💰
        </span>

        Recharge

    </a>

    <a href="/orders">

        <span class="icon">
            📦
        </span>

        Orders

    </a>

    <a href="/profile">

        <span class="icon">
            👤
        </span>

        Profile

    </a>

</div>

</body>
</html>
"""

.grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            padding: 15px;
            max-width: 500px;
            margin: auto;
        }

        .game-card {
            background: #0d1117;
            border: 1px solid #222;
            border-radius: 14px;
            padding: 15px;
            text-align: center;
            text-decoration: none;
            color: #fff;
            min-height: 130px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }

        .game-card img {
            width: 65px;
            height: 65px;
            object-fit: contain;
            margin-bottom: 8px;
            border-radius: 12px;
        }

        .game-card .name {
            font-weight: bold;
            font-size: 14px;
        }

        .game-card .sub {
            color: #94a3b8;
            font-size: 11px;
            margin-top: 4px;
        }

        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px;
            z-index: 999;
        }

        .bottom-nav a {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }

        .bottom-nav .icon {
            font-size: 22px;
            margin-bottom: 2px;
        }

        .bottom-nav a.active {
            color: #0d1117;
            font-weight: bold;
        }

        @media (max-width: 360px) {

            .grid-2 {
                gap: 7px;
                padding: 10px;
            }

            .game-card {
                min-height: 115px;
                padding: 10px;
            }

            .game-card img {
                width: 55px;
                height: 55px;
            }

        }
    </style>
</head>

<body>

<div class="grid-2">

    <a
        href="/packages/Mobile Legends"
        class="game-card"
    >
        <img src="/static/mlbb.png">

        <div class="name">
            Mobile Legends
        </div>

        <div class="sub">
            💎 Diamonds
        </div>
    </a>


    <a
        href="/packages/PUBG Mobile"
        class="game-card"
    >
        <img src="/static/pubg.png">

        <div class="name">
            PUBG Mobile
        </div>

        <div class="sub">
            🪙 UC
        </div>
    </a>


    <a
        href="/packages/Telegram Premium"
        class="game-card"
    >
        <img src="/static/telegram.png">

        <div class="name">
            Telegram Premium
        </div>

        <div class="sub">
            ⭐ Premium
        </div>
    </a>


    <a
        href="/packages/Smile One Coin PHP"
        class="game-card"
    >
        <img src="/static/smileone.png">

        <div class="name">
            Smile One PHP
        </div>

        <div class="sub">
            🪙 Coin
        </div>
    </a>


    <a
        href="/packages/Smile One Code BRL"
        class="game-card"
    >
        <img src="/static/smileone.png">

        <div class="name">
            Smile One BRL
        </div>

        <div class="sub">
            🎟️ Code
        </div>
    </a>


    <a
        href="/packages/Smile One Coin PHP"
        class="game-card"
    >
        <img src="/static/smileone.png">

        <div class="name">
            Smile One Coin PHP
        </div>

        <div class="sub">
            🪙 Coin
        </div>
    </a>

</div>


<div class="bottom-nav">

    <a
        href="/dashboard"
    >
        <span class="icon">
            🏠
        </span>
        Shop
    </a>

    <a
        href="/wallet"
    >
        <span class="icon">
            💰
        </span>
        Recharge
    </a>

    <a
        href="/order"
        class="active"
    >
        <span class="icon">
            🛒
        </span>
        Order
    </a>

    <a
        href="/profile"
    >
        <span class="icon">
            👤
        </span>
        Profile
    </a>

</div>

</body>
</html>
"""


# ==================================================
# PACKAGES
# ==================================================

@app.route(
    "/packages/<game>"
)
def packages(game):

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    game = clean_text(game)

    packages = {
        "Mobile Legends": [
            ("86 Diamonds", 4500),
            ("172 Diamonds", 9000),
            ("257 Diamonds", 19000),
            ("706 Diamonds", 40000),
            ("2195 Diamonds", 107000),
            ("3688 Diamonds", 180000),
            ("5532 Diamonds", 270000),
            ("9288 Diamonds", 450000)
        ],

        "PUBG Mobile": [
            ("60 UC", 5000),
            ("325 UC", 25000),
            ("660 UC", 50000),
            ("1800 UC", 130000)
        ],

        "Telegram Premium": [
            ("3 Months", 25000),
            ("6 Months", 45000),
            ("12 Months", 80000)
        ],

        "Smile One Coin PHP": [
            ("100 Coins", 10000),
            ("500 Coins", 50000),
            ("1000 Coins", 100000)
        ],

        "Smile One Code BRL": [
            ("10 BRL", 10000),
            ("25 BRL", 25000),
            ("50 BRL", 50000),
            ("100 BRL", 100000)
        ]
    }

    selected_packages = packages.get(
        game,
        []
    )

    if not selected_packages:
        return redirect(
            url_for("order")
        )

    package_html = ""

    for package_name, price in selected_packages:

        package_html += f"""
        <a
            href="/checkout?game={
                urllib.parse.quote(game)
            }&package={
                urllib.parse.quote(package_name)
            }&amount={price}"
            class="package-card"
        >

            <div class="package-name">
                {package_name}
            </div>

            <div class="package-price">
                {price:,} Ks
            </div>

        </a>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    {game} Packages
</title>

<style>

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    background: #000;
    color: #fff;
    font-family: Arial, sans-serif;
    padding: 15px;
}}

.container {{
    max-width: 500px;
    margin: auto;
}}

h1 {{
    text-align: center;
    margin-bottom: 20px;
    color: #14b8a6;
}}

.package-card {{
    display: block;
    background: #0d1117;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 10px;
    text-decoration: none;
    color: #fff;
}}

.package-name {{
    font-weight: bold;
    font-size: 16px;
}}

.package-price {{
    color: #4ade80;
    font-weight: bold;
    margin-top: 8px;
}}

.back {{
    display: block;
    text-align: center;
    margin-top: 20px;
    color: #14b8a6;
    text-decoration: none;
}}

</style>

</head>

<body>

<div class="container">

<h1>
    {game}
</h1>

{package_html}

<a
    class="back"
    href="/order"
>
    ← Back
</a>

</div>

</body>

</html>
"""

.card .name {
            font-weight: bold;
            font-size: 14px;
        }

        .back-btn {
            position: absolute;
            left: 15px;
            color: #fff;
            text-decoration: none;
            font-size: 18px;
        }

        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }

        .bottom-nav a {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }

        .bottom-nav a .icon {
            font-size: 22px;
            margin-bottom: 2px;
        }

        .bottom-nav a.active {
            color: #0d1117;
            font-weight: bold;
        }
    </style>
</head>

<body>

<div class="header">

    <a
        href="/order"
        class="back-btn"
    >
        ←
    </a>

    <h1>
        {display_name}
    </h1>

</div>

<div class="container">

    <div class="grid-2">

        {packages_html}

    </div>

</div>

<div class="bottom-nav">

    <a href="/dashboard">

        <span class="icon">
            🏠
        </span>

        Shop

    </a>

    <a href="/wallet">

        <span class="icon">
            💰
        </span>

        Recharge

    </a>

    <a
        href="/order"
        class="active"
    >

        <span class="icon">
            📄
        </span>

        Order

    </a>

    <a href="/orders">

        <span class="icon">
            📦
        </span>

        Order History

    </a>

    <a href="/profile">

        <span class="icon">
            👤
        </span>

        Profile

    </a>

</div>

</body>
</html>
"""


# ==================================================
# PLACE ORDER
# ==================================================

@app.route(
    "/place_order",
    methods=["GET", "POST"]
)
def place_order():

    if "username" not in session:

        return redirect(
            url_for("login")
        )

    username = session["username"]

    game = request.args.get(
        "game",
        ""
    ).strip()

    package = request.args.get(
        "package",
        ""
    ).strip()

    if request.method == "POST":

        game = request.form.get(
            "game",
            game
        ).strip()

        package = request.form.get(
            "package",
            package
        ).strip()

        game_id = request.form.get(
            "game_id",
            ""
        ).strip()

        server_id = request.form.get(
            "server_id",
            ""
        ).strip()

        telegram_username = request.form.get(
            "telegram_username",
            ""
        ).strip()

        payment = request.form.get(
            "payment",
            ""
        ).strip()

        transaction = request.form.get(
            "transaction",
            ""
        ).strip()

        if not game_id and game in [
            "ML",
            "PUBG",
            "HOK"
        ]:

            return (
                "❌ Game ID ဖြည့်ပေးပါ",
                400
            )

        if game == "ML" and not server_id:

            return (
                "❌ Server ID ဖြည့်ပေးပါ",
                400
            )

        if not payment:

            return (
                "❌ Payment Method ရွေးပေးပါ",
                400
            )

        if not transaction:

            return (
                "❌ Transaction Number ဖြည့်ပေးပါ",
                400
            )

        order_id = generate_order_id()

        order_data = {
            "order_id": order_id,
            "username": username,
            "game": game,
            "package": package,
            "game_id": game_id,
            "server_id": server_id,
            "telegram_username":
                telegram_username,
            "payment": payment,
            "transaction":
                transaction
        }

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO orders (
                order_id,
                username,
                game,
                package,
                game_id,
                server_id,
                payment,
                transaction_number,
                status,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                order_id,
                username,
                game,
                package,
                game_id,
                server_id,
                payment,
                transaction,
                "Pending",
                datetime.now().isoformat()
            )
        )

        conn.commit()

        conn.close()

        try:

            send_order_to_owner(
                order_data
            )

        except Exception as e:

            logger.exception(
                "Order notification failed: %s",
                e
            )

        return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>Order Success</title>

{STYLE}

</head>

<body>

<div class="box">

<h1>
    ✅ Order Submitted
</h1>

<div class="card">

<p>
    Order ID
</p>

<h2>
    {order_id}
</h2>

</div>

<p class="success">
    Order ကို လက်ခံရရှိပါပြီ။
</p>

<div class="card">

<a href="/orders">
    📦 View Orders
</a>

</div>

<div class="card">

<a href="/dashboard">
    🏠 Back to Shop
</a>

</div>

</div>

</body>

</html>
"""

    game_name = {
        "ML": "Mobile Legends",
        "PUBG": "PUBG Mobile",
        "HOK": "Honor Of Kings",
        "TG Pre": "Telegram Premium",
        "Smile One Code BRL":
            "Smile One BRL",
        "Smile One Coin PHP":
            "Smile One PHP"
    }.get(
        game,
        game
    )

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    Order - {game_name}
</title>

<style>

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    background: #000;
    color: #fff;
    font-family: Arial, sans-serif;
    padding-bottom: 90px;
}}

.container {{
    max-width: 500px;
    margin: auto;
    padding: 15px;
}}

.header {{
    padding: 15px;
    text-align: center;
    border-bottom: 1px solid #222;
}}

.header h1 {{
    color: #14b8a6;
    font-size: 20px;
}}

.card {{
    background: #0d1117;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 12px;
}}

label {{
    display: block;
    margin-bottom: 7px;
    color: #cbd5e1;
    font-size: 14px;
}}

input,
select {{
    width: 100%;
    padding: 13px;
    border-radius: 9px;
    border: 1px solid #334155;
    background: #111827;
    color: #fff;
    margin-bottom: 14px;
}}

button {{
    width: 100%;
    padding: 14px;
    border: none;
    border-radius: 10px;
    background: #14b8a6;
    color: #fff;
    font-weight: bold;
    font-size: 16px;
}}

.back {{
    display: block;
    text-align: center;
    margin-top: 15px;
    color: #14b8a6;
    text-decoration: none;
}}

</style>

</head>

<body>

<div class="header">

<h1>
    🛒 {game_name}
</h1>

</div>

<div class="container">

<div class="card">

<p>
    Package
</p>

<strong>
    {package}
</strong>

</div>

<form
    method="POST"
>

<input
    type="hidden"
    name="game"
    value="{game}"
>

<input
    type="hidden"
    name="package"
    value="{package}"
>

<label>
    🎮 Game ID
</label>

<input
    type="text"
    name="game_id"
    placeholder="Game ID"
>

<label>
    🆔 Server ID
</label>

<input
    type="text"
    name="server_id"
    placeholder="Server ID"
>

<label>
    📱 Telegram Username
</label>

<input
    type="text"
    name="telegram_username"
    placeholder="@username"
>

<label>
    💳 Payment Method
</label>

<select
    name="payment"
    required
>

<option value="">
    Select Payment
</option>

<option value="KPay">
    KPay
</option>

<option value="UAB Pay">
    UAB Pay
</option>

<option value="Wave Money">
    Wave Money
</option>

</select>

<label>
    🔢 Transaction Number
</label>

<input
    type="text"
    name="transaction"
    maxlength="5"
    placeholder="Last 5 digits"
    required
>

<button
    type="submit"
>
    📤 Submit Order
</button>

</form>

<a
    href="/packages/{game}"
    class="back"
>
    ← Back to Packages
</a>

</div>

</body>

</html>
"""

else:
                                message = (
                                    f"❌ Code ထုတ်မရပါ။\n"
                                    f"Error: {result['error']}"
                                )
                                message_type = "error"

                        # ==========================================
                        # TELEGRAM PREMIUM
                        # ==========================================
                        elif game == "TG Pre":

                            cursor.execute(
                                """
                                INSERT INTO orders (
                                    username,
                                    game,
                                    package,
                                    status,
                                    created_at
                                )
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    username,
                                    game,
                                    package,
                                    "Pending",
                                    now()
                                )
                            )

                            order_id = cursor.lastrowid

                            conn.commit()

                            message = (
                                "✅ Telegram Premium Order "
                                "လက်ခံပြီးပါပြီ။\n"
                                "Admin မှ ဆက်လက်ဆောင်ရွက်ပေးပါမယ်။"
                            )

                            message_type = "success"

                        # ==========================================
                        # MANUAL ORDER
                        # ==========================================
                        else:

                            cursor.execute(
                                """
                                INSERT INTO orders (
                                    username,
                                    game,
                                    package,
                                    status,
                                    created_at
                                )
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    username,
                                    game,
                                    package,
                                    "Pending",
                                    now()
                                )
                            )

                            order_id = cursor.lastrowid

                            conn.commit()

                            message = (
                                "✅ Order လက်ခံပြီးပါပြီ။\n"
                                "Admin မှ ဆက်လက်ဆောင်ရွက်ပေးပါမယ်။"
                            )

                            message_type = "success"

            except Exception as e:

                if conn:
                    conn.rollback()

                logger.exception(
                    "Place order error"
                )

                message = (
                    "❌ Order တင်ရာတွင် "
                    "အမှားတစ်ခု ဖြစ်သွားပါတယ်။"
                )

                message_type = "error"

            finally:

                if conn:
                    conn.close()

    # ==================================================
    # ORDER FORM
    # ==================================================

    game_names = {
        "ML": "Mobile Legends",
        "PUBG": "PUBG Mobile",
        "HOK": "Honor Of Kings",
        "TG Pre": "Telegram Premium",
        "Smile One Code BRL":
            "Smile One BRL",
        "Smile One Coin PHP":
            "Smile One PHP"
    }

    display_name = game_names.get(
        game,
        game
    )

    game_id_label = (
        "Game ID"
        if game != "PUBG"
        else "PUBG ID"
    )

    if game == "HOK":
        game_id_label = "Account UID"

    show_game_id = game in (
        "ML",
        "PUBG",
        "HOK"
    )

    show_server_id = game == "ML"

    show_telegram = game == "TG Pre"

    show_acc_mail = (
        game == "Smile One Coin PHP"
    )

    game_id_html = ""

    if show_game_id:

        game_id_html = f"""
        <label>
            🎮 {game_id_label}
        </label>

        <input
            type="text"
            name="game_id"
            placeholder="{game_id_label}"
            required
        >
        """

    server_id_html = ""

    if show_server_id:

        server_id_html = """
        <label>
            🆔 Server ID
        </label>

        <input
            type="text"
            name="server_id"
            placeholder="Server ID"
            required
        >
        """

    telegram_html = ""

    if show_telegram:

        telegram_html = """
        <label>
            📱 Telegram Username
        </label>

        <input
            type="text"
            name="telegram_username"
            placeholder="@username"
            required
        >
        """

    acc_mail_html = ""

    if show_acc_mail:

        acc_mail_html = """
        <label>
            📧 Account Mail
        </label>

        <input
            type="email"
            name="acc_mail"
            placeholder="Smile One Account Email"
            required
        >
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    Order - {display_name}
</title>

<style>

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    background: #000;
    color: #fff;
    font-family: Arial, sans-serif;
    padding-bottom: 90px;
}}

.header {{
    background: #0d1117;
    border-bottom: 1px solid #222;
    padding: 15px;
    text-align: center;
}}

.header h1 {{
    color: #14b8a6;
    font-size: 20px;
}}

.container {{
    max-width: 500px;
    margin: auto;
    padding: 15px;
}}

.card {{
    background: #0d1117;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 12px;
}}

.package {{
    color: #4ade80;
    font-size: 17px;
    font-weight: bold;
}}

label {{
    display: block;
    color: #cbd5e1;
    font-size: 14px;
    margin: 12px 0 7px;
}}

input,
select {{
    width: 100%;
    padding: 13px;
    border-radius: 9px;
    border: 1px solid #334155;
    background: #111827;
    color: #fff;
    outline: none;
}}

input:focus,
select:focus {{
    border-color: #14b8a6;
}}

button {{
    width: 100%;
    padding: 14px;
    margin-top: 18px;
    border: none;
    border-radius: 10px;
    background: #14b8a6;
    color: #fff;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
}}

.message {{
    white-space: pre-line;
    padding: 13px;
    border-radius: 10px;
    margin-bottom: 15px;
}}

.success {{
    background: rgba(74,222,128,.15);
    color: #4ade80;
    border: 1px solid #166534;
}}

.error {{
    background: rgba(248,113,113,.15);
    color: #f87171;
    border: 1px solid #991b1b;
}}

.back {{
    display: block;
    text-align: center;
    margin-top: 18px;
    color: #14b8a6;
    text-decoration: none;
}}

.bottom-nav {{
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #14b8a6;
    display: flex;
    justify-content: space-around;
    padding: 8px 0 12px;
    z-index: 999;
}}

.bottom-nav a {{
    display: flex;
    flex-direction: column;
    align-items: center;
    text-decoration: none;
    color: #fff;
    font-size: 11px;
}}

.bottom-nav .icon {{
    font-size: 21px;
    margin-bottom: 2px;
}}

.bottom-nav a.active {{
    color: #0d1117;
    font-weight: bold;
}}

</style>

</head>

<body>

<div class="header">

<h1>
    🛒 {display_name}
</h1>

</div>

<div class="container">

{
    f'''
    <div class="message {message_type}">
        {message}
    </div>
    '''
    if message
    else ""
}

<div class="card">

<div>
    📦 Package
</div>

<div class="package">
    {package}
</div>

</div>

<form method="POST">

<input
    type="hidden"
    name="game"
    value="{game}"
>

<input
    type="hidden"
    name="package"
    value="{package}"
>

{game_id_html}

{server_id_html}

{telegram_html}

{acc_mail_html}

<label>
    💳 Payment Method
</label>

<select
    name="payment"
    required
>

<option value="">
    Select Payment
</option>

<option value="Wallet">
    💰 Wallet Balance
</option>

<option value="KPay">
    KPay
</option>

<option value="UAB Pay">
    UAB Pay
</option>

<option value="Wave Money">
    Wave Money
</option>

</select>

<button
    type="submit"
>
    🚀 Place Order
</button>

</form>

<a
    href="/packages/{game}"
    class="back"
>
    ← Back to Packages
</a>

</div>

<div class="bottom-nav">

<a href="/dashboard">

<span class="icon">
    🏠
</span>

Shop

</a>

<a href="/wallet">

<span class="icon">
    💰
</span>

Recharge

</a>

<a
    href="/order"
    class="active"
>

<span class="icon">
    🛒
</span>

Order

</a>

<a href="/orders">

<span class="icon">
    📦
</span>

Orders

</a>

<a href="/profile">

<span class="icon">
    👤
</span>

Profile

</a>

</div>

</body>

</html>
"""

# ==================================================
# ORDER HISTORY
# ==================================================

@app.route("/orders")
def orders():

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    username = session["username"]

    search_query = request.args.get(
        "search",
        ""
    ).strip()

    conn = get_db()
    cursor = conn.cursor()

    if search_query:

        cursor.execute(
            """
            SELECT
                id,
                game,
                package,
                game_id,
                server_id,
                status,
                created_at
            FROM orders
            WHERE username = ?
            AND (
                game_id LIKE ?
                OR package LIKE ?
            )
            ORDER BY id DESC
            """,
            (
                username,
                f"%{search_query}%",
                f"%{search_query}%"
            )
        )

    else:

        cursor.execute(
            """
            SELECT
                id,
                game,
                package,
                game_id,
                server_id,
                status,
                created_at
            FROM orders
            WHERE username = ?
            ORDER BY id DESC
            """,
            (username,)
        )

    order_list = cursor.fetchall()

    conn.close()

    html = ""

    for item in order_list:

        order_id = item[0]
        game = item[1]
        package = item[2]
        game_id = item[3] or "-"
        server_id = item[4] or "-"
        status = item[5]
        date_str = item[6]

        if status in (
            "Confirmed",
            "Completed"
        ):

            badge_color = "#22c55e"
            badge_text = "success"

        elif status == "Pending":

            badge_color = "#f59e0b"
            badge_text = "pending"

        else:

            badge_color = "#ef4444"
            badge_text = "အောင်မြင်မှု မရှိ"

        html += f"""
        <div class="row-item">

            <div class="col-id">

                <div>
                    #{order_id}
                </div>

                <div
                    style="
                        font-size:10px;
                        color:#94a3b8;
                        font-weight:normal;
                    "
                >
                    ID: {game_id}
                </div>

                <div
                    style="
                        font-size:10px;
                        color:#94a3b8;
                        font-weight:normal;
                    "
                >
                    Server: {server_id}
                </div>

            </div>

            <div class="col-pkg">

                {package}

            </div>

            <div class="col-status">

                <span
                    class="status-pill"
                    style="
                        background:{badge_color};
                    "
                >
                    {badge_text}
                </span>

            </div>

        </div>
        """

    if not html:

        html = """
        <div
            class="empty"
        >
            📦 Order မရှိသေးပါ
        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    Order History
</title>

<style>

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    background: #000;
    color: #fff;
    font-family: Arial, sans-serif;
    padding-bottom: 90px;
}}

.container {{
    max-width: 600px;
    margin: auto;
    padding: 15px;
}}

h1 {{
    text-align: center;
    color: #14b8a6;
    margin-bottom: 15px;
}}

.search-box {{
    display: flex;
    gap: 8px;
    margin-bottom: 15px;
}}

.search-box input {{
    flex: 1;
    padding: 12px;
    border-radius: 9px;
    border: 1px solid #334155;
    background: #111827;
    color: #fff;
}}

.search-box button {{
    padding: 12px 16px;
    border: none;
    border-radius: 9px;
    background: #14b8a6;
    color: #fff;
    font-weight: bold;
}}

.row-item {{
    display: grid;
    grid-template-columns: 1.2fr 1.5fr .8fr;
    gap: 8px;
    align-items: center;
    background: #0d1117;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 13px;
    margin-bottom: 10px;
}}

.col-id {{
    font-size: 13px;
}}

.col-pkg {{
    font-size: 13px;
    color: #cbd5e1;
}}

.status-pill {{
    display: inline-block;
    color: #fff;
    padding: 5px 7px;
    border-radius: 7px;
    font-size: 10px;
    text-align: center;
}}

.empty {{
    text-align: center;
    color: #94a3b8;
    padding: 40px 10px;
}}

.bottom-nav {{
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #14b8a6;
    display: flex;
    justify-content: space-around;
    padding: 8px 0 12px;
}}

.bottom-nav a {{
    display: flex;
    flex-direction: column;
    align-items: center;
    color: #fff;
    text-decoration: none;
    font-size: 11px;
}}

.bottom-nav .icon {{
    font-size: 21px;
}}

.bottom-nav a.active {{
    color: #0d1117;
    font-weight: bold;
}}

</style>

</head>

<body>

<div class="container">

<h1>
    📦 Order History
</h1>

<form
    class="search-box"
    method="GET"
>

<input
    type="text"
    name="search"
    value="{search_query}"
    placeholder="🔍 Game ID / Package"
>

<button type="submit">
    Search
</button>

</form>

{html}

</div>

<div class="bottom-nav">

<a href="/dashboard">
<span class="icon">🏠</span>
Shop
</a>

<a href="/wallet">
<span class="icon">💰</span>
Recharge
</a>

<a
    href="/orders"
    class="active"
>
<span class="icon">📦</span>
Orders
</a>

<a href="/profile">
<span class="icon">👤</span>
Profile
</a>

</div>

</body>

</html>
"""


# ==================================================
# ADMIN ORDERS
# ==================================================

@app.route("/admin/orders")
def admin_orders():

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    if (
        session.get("username")
        != ADMIN_USERNAME
    ):
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        """
    )

    orders = cursor.fetchall()

    conn.close()

    order_html = ""

    for order in orders:

        status = order[9]

        if status == "Confirmed":

            status_html = (
                '<span class="status green">'
                '✅ Confirmed'
                '</span>'
            )

        elif status == "Rejected":

            status_html = (
                '<span class="status red">'
                '❌ Rejected'
                '</span>'
            )

        else:

            status_html = (
                '<span class="status">'
                '🟡 Pending'
                '</span>'
            )

        buttons = ""

        if status == "Pending":

            buttons = f"""
            <a
                href="/admin/order/{order[0]}/confirm"
            >
                <button class="green">
                    ✅ CONFIRM
                </button>
            </a>

            <a
                href="/admin/order/{order[0]}/reject"
            >
                <button class="red">
                    ❌ REJECT
                </button>
            </a>
            """

        order_html += f"""
        <div class="order-card">

            <h2>
                🛒 Order #{order[0]}
            </h2>

            <p>
                👤 User:
                <b>{order[1]}</b>
            </p>

            <p>
                🎮 Product:
                {order[2]}
            </p>

            <p>
                📦 Package:
                {order[3]}
            </p>

            <p>
                🆔 Game ID:
                {order[4] or "-"}
            </p>

            <p>
                🌎 Server ID:
                {order[5] or "-"}
            </p>

            <p>
                📱 Telegram:
                {order[6] or "-"}
            </p>

            <p>
                📧 Mail:
                {order[7] or "-"}
            </p>

            <p>
                💳 Payment:
                {order[8] or "-"}
            </p>

            <p>
                📌 Status:
                {status_html}
            </p>

            <p class="small">
                🕒 {order[10]}
            </p>

            {buttons}

        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    Admin Orders
</title>

{STYLE}

<style>

.order-card {{
    background: #0d1117;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 12px;
}}

.order-card h2 {{
    color: #14b8a6;
    margin-bottom: 10px;
}}

.order-card p {{
    margin: 7px 0;
    color: #cbd5e1;
}}

.status {{
    padding: 5px 8px;
    border-radius: 7px;
    background: #f59e0b;
    color: #fff;
    font-size: 11px;
}}

.status.green {{
    background: #22c55e;
}}

.status.red {{
    background: #ef4444;
}}

.order-card button {{
    padding: 10px 14px;
    border: none;
    border-radius: 8px;
    color: #fff;
    font-weight: bold;
    margin: 5px 3px 0 0;
}}

.order-card button.green {{
    background: #16a34a;
}}

.order-card button.red {{
    background: #dc2626;
}}

.small {{
    font-size: 11px;
    color: #64748b !important;
}}

</style>

</head>

<body>

<div class="box">

<h1>
    👑 Admin Orders
</h1>

{order_html}

<a href="/dashboard">
    <button>
        ⬅️ Dashboard
    </button>
</a>

</div>

</body>

</html>
"""

# ==================================================
# ADMIN DEPOSIT CONFIRM
# ==================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/confirm"
)
def confirm_deposit(deposit_id):

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    if session.get("username") != ADMIN_USERNAME:
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposit_requests
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if not deposit or deposit[5] != "Pending":

        conn.close()

        return (
            "⚠️ ဒီ Deposit ကို စစ်ပြီးသားပါ။",
            400
        )

    amount = deposit[2]
    username = deposit[1]

    cursor.execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE username = ?
        """,
        (
            amount,
            username
        )
    )

    cursor.execute(
        """
        UPDATE deposit_requests
        SET status = 'Confirmed'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    cursor.execute(
        """
        INSERT INTO wallet_transactions
        (
            username,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            "DEPOSIT",
            amount,
            f"Deposit #{deposit_id} Confirmed",
            now()
        )
    )

    # Website notification
    add_user_notification(
        username,
        "deposit",
        "💰 Deposit အောင်မြင်ပါပြီ",
        (
            f"သင်ဖြည့်ထားသော Deposit "
            f"{amount:,} Ks ကို Wallet ထဲထည့်ပြီးပါပြီ။"
        )
    )

    conn.commit()
    conn.close()

    send_message_to_user(
        username,
        (
            "✅ <b>Deposit Confirmed</b>\n"
            f"Deposit #{deposit_id}\n"
            f"Amount: {amount:,} Ks"
        )
    )

    return redirect(
        "/admin/deposits"
    )


# ==================================================
# ADMIN DEPOSIT REJECT
# ==================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/reject"
)
def reject_deposit(deposit_id):

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    if session.get("username") != ADMIN_USERNAME:
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposit_requests
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if not deposit or deposit[5] != "Pending":

        conn.close()

        return (
            "⚠️ ဒီ Deposit ကို စစ်ပြီးသားပါ။",
            400
        )

    username = deposit[1]

    cursor.execute(
        """
        UPDATE deposit_requests
        SET status = 'Rejected'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    conn.commit()
    conn.close()

    add_user_notification(
        username,
        "deposit",
        "❌ Deposit ပယ်ချခံရပါပြီ",
        f"Deposit #{deposit_id} ကို Admin မှ Reject လုပ်လိုက်ပါတယ်။"
    )

    send_message_to_user(
        username,
        (
            "❌ <b>Deposit Rejected</b>\n"
            f"Deposit #{deposit_id}"
        )
    )

    return redirect(
        "/admin/deposits"
    )


# ==================================================
# ADMIN ORDER CONFIRM
# ==================================================

@app.route(
    "/admin/order/<int:order_id>/confirm"
)
def confirm_order(order_id):

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    if session.get("username") != ADMIN_USERNAME:
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )

    order = cursor.fetchone()

    if not order or order[9] != "Pending":

        conn.close()

        return (
            "⚠️ ဒီ Order ကို စစ်ပြီးသားပါ။",
            400
        )

    package = order[3]
    username = order[1]

    package_price_map = {

        "10 💎 - 1,000 Ks": 1000,
        "12 💎 - 1,200 Ks": 1200,
        "20 💎 - 1,900 Ks": 1900,

        "22 💎 - 2,100 Ks": 2100,
        "33 💎 - 3,000 Ks": 3000,
        "44 💎 - 3,600 Ks": 3600,

        "55 💎 - 4,000 Ks": 4000,
        "56 💎 - 4,400 Ks": 4400,
        "86 💎 - 5,600 Ks": 5600,

        "172 💎 - 10,800 Ks": 10800,
        "257 💎 - 15,800 Ks": 15800,
        "279 💎 - 17,100 Ks": 17100,

        "343 💎 - 20,600 Ks": 20600,
        "429 💎 - 25,900 Ks": 25900,

        "Weekly Pass - 6,400 Ks": 6400,

        "60 UC - 600 Ks": 600,
        "325 UC - 3,250 Ks": 3250,
        "660 UC - 6,600 Ks": 6600,
        "1800 UC - 18,000 Ks": 18000,
        "3850 UC - 38,500 Ks": 38500,

        "3 Months - 3,000 Ks": 3000,
        "6 Months - 6,000 Ks": 6000,
        "12 Months - 12,000 Ks": 12000,

        "30 BRL - 24,500 Ks": 24500,
        "100 BRL - 85,500 Ks": 85500,
        "500 BRL - 424,000 Ks": 424000,

        "280 PHP - 22,000 Ks": 22000,
        "560 PHP - 42,000 Ks": 42000,
        "1120 PHP - 83,000 Ks": 83000,

        "60 Tokens - 1,000 Ks": 1000,
        "120 Tokens - 2,000 Ks": 2000,
        "250 Tokens - 4,000 Ks": 4000,
        "500 Tokens - 8,000 Ks": 8000,
        "1000 Tokens - 15,000 Ks": 15000,
    }

    price = package_price_map.get(
        package,
        0
    )

    if price <= 0:

        conn.close()

        return (
            "❌ Package price မတွေ့ပါ။",
            400
        )

    # Check current balance
    cursor.execute(
        """
        SELECT balance
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    user = cursor.fetchone()

    if not user:

        conn.close()

        return (
            "❌ User မတွေ့ပါ။",
            404
        )

    balance = user[0] or 0

    if balance < price:

        conn.close()

        return (
            "❌ User Wallet Balance မလုံလောက်ပါ။",
            400
        )

    # Confirm order
    cursor.execute(
        """
        UPDATE orders
        SET status = 'Confirmed'
        WHERE id = ?
        """,
        (order_id,)
    )

    # Deduct wallet
    cursor.execute(
        """
        UPDATE users
        SET balance = balance - ?
        WHERE username = ?
        """,
        (
            price,
            username
        )
    )

    # Wallet transaction
    cursor.execute(
        """
        INSERT INTO wallet_transactions
        (
            username,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            "PURCHASE",
            price,
            (
                f"Order #{order_id} Confirmed: "
                f"{order[2]} - {package}"
            ),
            now()
        )
    )

    # Website notification
    order_amount_text = get_order_amount_text(
        package
    )

    add_user_notification(
        username,
        "order",
        "🎮 Order အောင်မြင်ပါပြီ",
        (
            f"သင်ဖြည့်ထားသော "
            f"{order_amount_text or package} "
            f"ကို In Game ထဲဖြည့်ပြီးပါပြီ။"
        )
    )

    conn.commit()
    conn.close()

    send_message_to_user(
        username,
        (
            "✅ <b>Order Confirmed</b>\n"
            f"Order #{order_id}\n"
            f"Product: {order[2]}\n"
            f"Package: {package}"
        )
    )

    return redirect(
        "/admin/orders"
    )


# ==================================================
# ADMIN ORDER REJECT
# ==================================================

@app.route(
    "/admin/order/<int:order_id>/reject"
)
def reject_order(order_id):

    if "username" not in session:
        return redirect(
            url_for("login")
        )

    if session.get("username") != ADMIN_USERNAME:
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )

    order = cursor.fetchone()

    if not order or order[9] != "Pending":

        conn.close()

        return (
            "⚠️ ဒီ Order ကို စစ်ပြီးသားပါ။",
            400
        )

    cursor.execute(
        """
        UPDATE orders
        SET status = 'Rejected'
        WHERE id = ?
        """,
        (order_id,)
    )

    conn.commit()
    conn.close()

    add_user_notification(
        order[1],
        "order",
        "❌ Order ပယ်ချခံရပါပြီ",
        (
            f"Order #{order_id} ကို "
            "Admin မှ Reject လုပ်လိုက်ပါတယ်။"
        )
    )

    send_message_to_user(
        order[1],
        (
            "❌ <b>Order Rejected</b>\n"
            f"Order #{order_id}\n"
            f"Product: {order[2]}\n"
            f"Package: {order[3]}"
        )
    )

    return redirect(
        "/admin/orders"
    )

    # ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ==================================================
# ADMIN DEPOSITS
# ==================================================

@app.route("/admin/deposits")
def admin_deposits():

    if "username" not in session:

        return redirect(
            url_for("login")
        )

    if session.get("username") != ADMIN_USERNAME:

        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposit_requests
        ORDER BY id DESC
        """
    )

    deposits = cursor.fetchall()

    conn.close()

    deposit_html = ""

    for deposit in deposits:

        deposit_id = deposit[0]
        username = deposit[1]
        amount = deposit[2]
        transaction = deposit[3]
        payment = deposit[4]
        status = deposit[5]
        created_at = deposit[6]

        if status == "Confirmed":

            status_html = """
            <span class="status green">
                ✅ Confirmed
            </span>
            """

        elif status == "Rejected":

            status_html = """
            <span class="status red">
                ❌ Rejected
            </span>
            """

        else:

            status_html = """
            <span class="status">
                🟡 Pending
            </span>
            """

        buttons = ""

        if status == "Pending":

            buttons = f"""
            <div style="margin-top:12px;">

                <a
                    href="/admin/deposit/{deposit_id}/confirm"
                >
                    <button
                        class="green"
                    >
                        ✅ CONFIRM
                    </button>
                </a>

                <a
                    href="/admin/deposit/{deposit_id}/reject"
                >
                    <button
                        class="red"
                    >
                        ❌ REJECT
                    </button>
                </a>

            </div>
            """

        deposit_html += f"""
        <div class="order-card">

            <h2>
                💰 Deposit #{deposit_id}
            </h2>

            <p>
                👤 User:
                <b>{username}</b>
            </p>

            <p>
                💵 Amount:
                <b>{amount:,} Ks</b>
            </p>

            <p>
                💳 Payment:
                {payment}
            </p>

            <p>
                🔢 Transaction:
                {transaction}
            </p>

            <p>
                📌 Status:
                {status_html}
            </p>

            <p class="small">
                🕒 {created_at}
            </p>

            {buttons}

        </div>
        """

    if not deposit_html:

        deposit_html = """
        <div
            class="empty"
            style="
                text-align:center;
                padding:30px;
                color:#94a3b8;
            "
        >
            💰 Deposit Request မရှိသေးပါ
        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    Admin Deposits
</title>

{STYLE}

<style>

.order-card {{
    background:#0d1117;
    border:1px solid #222;
    border-radius:12px;
    padding:15px;
    margin-bottom:12px;
}}

.order-card h2 {{
    color:#14b8a6;
    margin-bottom:10px;
}}

.order-card p {{
    margin:7px 0;
    color:#cbd5e1;
}}

.status {{
    display:inline-block;
    background:#f59e0b;
    color:#fff;
    padding:5px 8px;
    border-radius:7px;
    font-size:11px;
}}

.status.green {{
    background:#22c55e;
}}

.status.red {{
    background:#ef4444;
}}

.order-card button {{
    border:none;
    border-radius:8px;
    padding:10px 14px;
    margin-right:5px;
    color:#fff;
    font-weight:bold;
    cursor:pointer;
}}

.order-card button.green {{
    background:#16a34a;
}}

.order-card button.red {{
    background:#dc2626;
}}

.small {{
    color:#64748b !important;
    font-size:11px;
}}

</style>

</head>

<body>

<div class="box">

<h1>
    👑 Deposit Requests
</h1>

{deposit_html}

<a href="/dashboard">

    <button>
        ⬅️ Dashboard
    </button>

</a>

</div>

</body>

</html>
"""


# ==================================================
# USER NOTIFICATION HELPER
# ==================================================

def add_user_notification(
    username,
    notification_type,
    title,
    message
):

    try:

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO notifications
            (
                username,
                type,
                title,
                message,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                notification_type,
                title,
                message,
                0,
                now()
            )
        )

        conn.commit()
        conn.close()

        return True

    except Exception as e:

        print(
            f"Notification Error "
            f"for {username}: {e}"
        )

        try:
            conn.close()
        except:
            pass

        return False


# ==================================================
# ORDER AMOUNT HELPER
# ==================================================

def get_order_amount_text(package):

    if not package:

        return ""

    return str(
        package
    ).split(" - ")[0].strip()


# ==================================================
# TELEGRAM CALLBACK MESSAGE HELPER
# ==================================================

def edit_telegram_button_message(
    chat_id,
    message_id,
    text
):

    if (
        chat_id is None
        or message_id is None
    ):

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/editMessageText"
    )

    data = {

        "chat_id": chat_id,

        "message_id": message_id,

        "text": text,

        "reply_markup": json.dumps(
            {
                "inline_keyboard": []
            }
        )
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        return (
            response.status_code == 200
        )

    except Exception as e:

        print(
            "Telegram edit error:",
            e
        )

        return False


# ==================================================
# TELEGRAM DEPOSIT CONFIRM
# ==================================================

def confirm_deposit_from_telegram(
    deposit_id,
    chat_id,
    message_id
):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposit_requests
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if (
        not deposit
        or deposit[5] != "Pending"
    ):

        conn.close()

        return

    username = deposit[1]
    amount = deposit[2]

    cursor.execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE username = ?
        """,
        (
            amount,
            username
        )
    )

    cursor.execute(
        """
        UPDATE deposit_requests
        SET status = 'Confirmed'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    cursor.execute(
        """
        INSERT INTO wallet_transactions
        (
            username,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            "DEPOSIT",
            amount,
            (
                f"Deposit #{deposit_id} "
                "Confirmed via Telegram"
            ),
            now()
        )
    )

    add_user_notification(
        username,
        "deposit",
        "💰 Deposit အောင်မြင်ပါပြီ",
        (
            f"သင်ဖြည့်ထားသော Deposit "
            f"{amount:,} Ks ကို Wallet ထဲထည့်ပြီးပါပြီ။"
        )
    )

    conn.commit()
    conn.close()

    send_message_to_user(
        username,
        (
            "✅ <b>Deposit Confirmed</b>\n"
            f"Deposit #{deposit_id}\n"
            f"Amount: {amount:,} Ks"
        )
    )

    edit_telegram_button_message(
        chat_id,
        message_id,
        (
            "✅ Deposit Confirmed\n\n"
            f"ID: #{deposit_id}\n"
            f"User: {username}\n"
            f"Amount: {amount:,} Ks"
        )

        # ==================================================
# TELEGRAM CALLBACK HELPERS
# ==================================================

def reject_deposit_from_telegram(
    deposit_id,
    chat_id,
    message_id
):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposit_requests
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if not deposit or deposit[5] != "Pending":

        conn.close()
        return False

    username = deposit[1]

    cursor.execute(
        """
        UPDATE deposit_requests
        SET status = 'Rejected'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    conn.commit()
    conn.close()

    add_user_notification(
        username,
        "deposit",
        "❌ Deposit ပယ်ချခံရပါပြီ",
        f"Deposit #{deposit_id} ကို Admin မှ Reject လုပ်လိုက်ပါတယ်။"
    )

    edit_telegram_button_message(
        chat_id,
        message_id,
        (
            f"❌ Deposit #{deposit_id} Rejected!\n"
            f"👤 User: {username}"
        )
    )

    send_message_to_user(
        username,
        (
            "❌ <b>Deposit Rejected</b>\n"
            f"Deposit #{deposit_id}"
        )
    )

    return True


# ==================================================
# TELEGRAM ORDER CONFIRM
# ==================================================

def confirm_order_from_telegram(
    order_id,
    chat_id,
    message_id
):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )

    order = cursor.fetchone()

    if not order or order[9] != "Pending":

        conn.close()
        return False

    username = order[1]
    package = order[3]

    package_price_map = {

        "10 💎 - 1,000 Ks": 1000,
        "12 💎 - 1,200 Ks": 1200,
        "20 💎 - 1,900 Ks": 1900,

        "22 💎 - 2,100 Ks": 2100,
        "33 💎 - 3,000 Ks": 3000,
        "44 💎 - 3,600 Ks": 3600,

        "55 💎 - 4,000 Ks": 4000,
        "56 💎 - 4,400 Ks": 4400,
        "86 💎 - 5,600 Ks": 5600,

        "172 💎 - 10,800 Ks": 10800,
        "257 💎 - 15,800 Ks": 15800,
        "279 💎 - 17,100 Ks": 17100,

        "343 💎 - 20,600 Ks": 20600,
        "429 💎 - 25,900 Ks": 25900,

        "Weekly Pass - 6,400 Ks": 6400,

        "60 UC - 600 Ks": 600,
        "325 UC - 3,250 Ks": 3250,
        "660 UC - 6,600 Ks": 6600,
        "1800 UC - 18,000 Ks": 18000,
        "3850 UC - 38,500 Ks": 38500,

        "3 Months - 3,000 Ks": 3000,
        "6 Months - 6,000 Ks": 6000,
        "12 Months - 12,000 Ks": 12000,

        "30 BRL - 24,500 Ks": 24500,
        "100 BRL - 85,500 Ks": 85500,
        "500 BRL - 424,000 Ks": 424000,

        "280 PHP - 22,000 Ks": 22000,
        "560 PHP - 42,000 Ks": 42000,
        "1120 PHP - 83,000 Ks": 83000,

        "60 Tokens - 1,000 Ks": 1000,
        "120 Tokens - 2,000 Ks": 2000,
        "250 Tokens - 4,000 Ks": 4000,
        "500 Tokens - 8,000 Ks": 8000,
        "1000 Tokens - 15,000 Ks": 15000
    }

    price = package_price_map.get(
        package,
        0
    )

    if price <= 0:

        conn.close()
        return False

    # Get user balance
    cursor.execute(
        """
        SELECT balance
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    user = cursor.fetchone()

    if not user:

        conn.close()
        return False

    balance = user[0] or 0

    if balance < price:

        conn.close()

        edit_telegram_button_message(
            chat_id,
            message_id,
            (
                f"❌ Order #{order_id} Failed\n"
                f"👤 User: {username}\n"
                "💰 Wallet Balance မလုံလောက်ပါ။"
            )
        )

        return False

    # Confirm order
    cursor.execute(
        """
        UPDATE orders
        SET status = 'Confirmed'
        WHERE id = ?
        """,
        (order_id,)
    )

    # Deduct wallet
    cursor.execute(
        """
        UPDATE users
        SET balance = balance - ?
        WHERE username = ?
        """,
        (
            price,
            username
        )
    )

    # Wallet transaction
    cursor.execute(
        """
        INSERT INTO wallet_transactions
        (
            username,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            "PURCHASE",
            price,
            f"Order #{order_id} Confirmed",
            now()
        )
    )

    # Website notification
    add_user_notification(
        username,
        "order",
        "🎮 Order အောင်မြင်ပါပြီ",
        (
            f"Order #{order_id} ကို "
            f"Confirm လုပ်ပြီးပါပြီ။\n"
            f"{get_order_amount_text(package)}"
        )
    )

    conn.commit()
    conn.close()

    edit_telegram_button_message(
        chat_id,
        message_id,
        (
            f"✅ Order #{order_id} Confirmed!\n"
            f"👤 User: {username}\n"
            f"🎮 Product: {order[2]}\n"
            f"💵 Deducted: {price:,} Ks"
        )
    )

    send_message_to_user(
        username,
        (
            "✅ <b>Order Confirmed</b>\n"
            f"Order #{order_id}\n"
            f"Product: {order[2]}\n"
            f"Package: {package}\n"
            f"💵 Deducted: {price:,} Ks"
        )
    )

    return True


# ==================================================
# TELEGRAM ORDER REJECT
# ==================================================

def reject_order_from_telegram(
    order_id,
    chat_id,
    message_id
):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )

    order = cursor.fetchone()

    if not order or order[9] != "Pending":

        conn.close()
        return False

    username = order[1]

    cursor.execute(
        """
        UPDATE orders
        SET status = 'Rejected'
        WHERE id = ?
        """,
        (order_id,)
    )

    conn.commit()
    conn.close()

    add_user_notification(
        username,
        "order",
        "❌ Order ပယ်ချခံရပါပြီ",
        f"Order #{order_id} ကို Admin မှ Reject လုပ်လိုက်ပါတယ်။"
    )

    edit_telegram_button_message(
        chat_id,
        message_id,
        (
            f"❌ Order #{order_id} Rejected!\n"
            f"👤 User: {username}"
        )
    )

    send_message_to_user(
        username,
        (
            "❌ <b>Order Rejected</b>\n"
            f"Order #{order_id}\n"
            f"Product: {order[2]}"
        )
    )

    return True


# ==================================================
# MAIN TELEGRAM CALLBACK
# ==================================================

@app.route(
    "/telegram_callback",
    methods=["POST"]
)
def telegram_callback():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        callback = (
            data.get("callback_query")
            or {}
        )

        callback_data = callback.get(
            "data",
            ""
        )

        callback_message = (
            callback.get("message")
            or {}
        )

        callback_message_id = (
            callback_message.get(
                "message_id"
            )
        )

        callback_chat = (
            callback_message.get("chat")
            or {}
        )

        callback_chat_id = (
            callback_chat.get("id")
        )

        callback_id = callback.get(
            "id"
        )

        # Answer Telegram callback
        if callback_id:

            requests.post(
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/"
                f"answerCallbackQuery",

                data={
                    "callback_query_id":
                        callback_id
                },

                timeout=10
            )

        # ------------------------------------------
        # DEPOSIT CALLBACKS
        # ------------------------------------------

        if callback_data.startswith(
            "confirm_deposit_"
        ):

            deposit_id = int(
                callback_data.rsplit(
                    "_",
                    1
                )[1]
            )

            confirm_deposit_from_telegram(
                deposit_id,
                callback_chat_id,
                callback_message_id
            )

        elif callback_data.startswith(
            "reject_deposit_"
        ):

            deposit_id = int(
                callback_data.rsplit(
                    "_",
                    1
                )[1]
            )

            reject_deposit_from_telegram(
                deposit_id,
                callback_chat_id,
                callback_message_id
            )

        # ------------------------------------------
        # ORDER CALLBACKS
        # ------------------------------------------

        elif callback_data.startswith(
            "confirm_order_"
        ):

            order_id = int(
                callback_data.rsplit(
                    "_",
                    1
                )[1]
            )

            confirm_order_from_telegram(
                order_id,
                callback_chat_id,
                callback_message_id
            )

        elif callback_data.startswith(
            "reject_order_"
        ):

            order_id = int(
                callback_data.rsplit(
                    "_",
                    1
                )[1]
            )

            reject_order_from_telegram(
                order_id,
                callback_chat_id,
                callback_message_id
            )

        return "OK", 200

    except Exception as e:

        logger.exception(
            "Telegram callback error"
        )

        return (
            "ERROR",
            500
        )

        # ==================================================
# TELEGRAM MESSAGE HANDLER
# ==================================================

@app.route(
    "/telegram_webhook",
    methods=["POST"]
)
def telegram_webhook():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        # ==================================================
        # CALLBACK QUERY
        # ==================================================

        callback = data.get(
            "callback_query"
        )

        if callback:

            callback_data = (
                callback.get("data", "")
            )

            callback_id = callback.get(
                "id"
            )

            message = (
                callback.get("message")
                or {}
            )

            message_id = message.get(
                "message_id"
            )

            chat = (
                message.get("chat")
                or {}
            )

            chat_id = chat.get("id")

            # Telegram loading state ပျောက်စေမယ်
            if callback_id:

                try:

                    requests.post(
                        f"https://api.telegram.org/"
                        f"bot{BOT_TOKEN}/"
                        f"answerCallbackQuery",

                        data={
                            "callback_query_id":
                                callback_id
                        },

                        timeout=10
                    )

                except Exception:
                    pass

            # ----------------------------------------------
            # DEPOSIT
            # ----------------------------------------------

            if callback_data.startswith(
                "confirm_deposit_"
            ):

                deposit_id = int(
                    callback_data.rsplit(
                        "_",
                        1
                    )[1]
                )

                confirm_deposit_from_telegram(
                    deposit_id,
                    chat_id,
                    message_id
                )

            elif callback_data.startswith(
                "reject_deposit_"
            ):

                deposit_id = int(
                    callback_data.rsplit(
                        "_",
                        1
                    )[1]
                )

                reject_deposit_from_telegram(
                    deposit_id,
                    chat_id,
                    message_id
                )

            # ----------------------------------------------
            # ORDER
            # ----------------------------------------------

            elif callback_data.startswith(
                "confirm_order_"
            ):

                order_id = int(
                    callback_data.rsplit(
                        "_",
                        1
                    )[1]
                )

                confirm_order_from_telegram(
                    order_id,
                    chat_id,
                    message_id
                )

            elif callback_data.startswith(
                "reject_order_"
            ):

                order_id = int(
                    callback_data.rsplit(
                        "_",
                        1
                    )[1]
                )

                reject_order_from_telegram(
                    order_id,
                    chat_id,
                    message_id
                )

            return "OK", 200

        # ==================================================
        # NORMAL MESSAGE
        # ==================================================

        incoming = data.get(
            "message"
        )

        if not incoming:

            return "OK", 200

        chat = (
            incoming.get("chat")
            or {}
        )

        user_chat_id = chat.get(
            "id"
        )

        message_id = incoming.get(
            "message_id"
        )

        text = (
            incoming.get("text")
            or incoming.get("caption")
            or ""
        ).strip()

        reply_to = (
            incoming.get(
                "reply_to_message"
            )
            or {}
        )

        # ==================================================
        # OWNER REPLY → CUSTOMER
        # ==================================================

        if (
            user_chat_id == OWNER_CHAT_ID
            and reply_to.get("message_id")
        ):

            owner_message_id = (
                reply_to.get(
                    "message_id"
                )
            )

            conn = get_db()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT customer_chat_id
                FROM telegram_forward_map
                WHERE owner_message_id = ?
                """,
                (
                    owner_message_id,
                )
            )

            mapped = cursor.fetchone()

            conn.close()

            if mapped and mapped[0]:

                try:

                    requests.post(
                        f"https://api.telegram.org/"
                        f"bot{BOT_TOKEN}/"
                        f"copyMessage",

                        data={
                            "chat_id": mapped[0],
                            "from_chat_id":
                                OWNER_CHAT_ID,
                            "message_id":
                                message_id
                        },

                        timeout=20
                    )

                    return "OK", 200

                except Exception as e:

                    logger.exception(
                        "Owner reply forwarding error"
                    )

                    return "ERROR", 500

        # ==================================================
        # /START
        # ==================================================

        if text == "/start":

            welcome_text = (
                "👋 Hello!\n\n"
                "🛒 <b>Eren's Shop</b> မှ "
                "ကြိုဆိုပါတယ်ဗျာ။\n\n"
                "💎 ML Diamonds\n"
                "🪙 PUBG UC\n"
                "⭐ Telegram Premium\n"
                "🎟️ Smile One Code\n\n"
                "🌐 Website ကနေ Order တင်နိုင်ပါတယ်။"
            )

            requests.post(
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/sendMessage",

                data={
                    "chat_id": user_chat_id,
                    "text": welcome_text,
                    "parse_mode": "HTML"
                },

                timeout=20
            )

            return "OK", 200

        # ==================================================
        # /BALANCE
        # ==================================================

        if text in (
            "/balance",
            "/wallet"
        ):

            username = None

            # Telegram username ရှာမယ်
            telegram_user = (
                chat.get("username")
                or ""
            ).strip()

            if telegram_user:

                telegram_user = (
                    telegram_user
                    .lstrip("@")
                )

                conn = get_db()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT username, balance
                    FROM users
                    WHERE LOWER(username) = LOWER(?)
                    """,
                    (
                        telegram_user,
                    )
                )

                user = cursor.fetchone()

                conn.close()

                if user:

                    username = user[0]
                    balance = int(
                        user[1] or 0
                    )

                    requests.post(
                        f"https://api.telegram.org/"
                        f"bot{BOT_TOKEN}/sendMessage",

                        data={
                            "chat_id":
                                user_chat_id,

                            "text":
                                (
                                    "💰 <b>Your Wallet</b>\n\n"
                                    f"👤 {username}\n"
                                    f"💵 Balance: "
                                    f"{balance:,} Ks"
                                ),

                            "parse_mode":
                                "HTML"
                        },

                        timeout=20
                    )

                    return "OK", 200

            requests.post(
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/sendMessage",

                data={
                    "chat_id":
                        user_chat_id,

                    "text":
                        (
                            "❌ Website Account "
                            "နဲ့ Telegram Account "
                            "ချိတ်ထားခြင်း မတွေ့ပါ။"
                        )
                },

                timeout=20
            )

            return "OK", 200

        # ==================================================
        # FORWARD CUSTOMER MESSAGE TO OWNER
        # ==================================================

        if (
            user_chat_id
            and user_chat_id != OWNER_CHAT_ID
        ):

            username = (
                chat.get("username")
                or chat.get("first_name")
                or "Unknown"
            )

            forward_text = (
                "📩 <b>Customer Message</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 User: @{username}\n"
                f"🆔 Chat ID: {user_chat_id}\n\n"
                f"{text}"
            )

            response = requests.post(
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/sendMessage",

                data={
                    "chat_id":
                        OWNER_CHAT_ID,

                    "text":
                        forward_text,

                    "parse_mode":
                        "HTML"
                },

                timeout=20
            )

            if response.ok:

                result = response.json()

                owner_message = (
                    result.get(
                        "result"
                    )
                    or {}
                )

                owner_message_id = (
                    owner_message.get(
                        "message_id"
                    )
                )

                if owner_message_id:

                    conn = get_db()
                    cursor = conn.cursor()

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO
                        telegram_forward_map
                        (
                            owner_message_id,
                            customer_chat_id,
                            customer_message_id,
                            created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            owner_message_id,
                            user_chat_id,
                            message_id,
                            now()
                        )
                    )

                    conn.commit()
                    conn.close()

            return "OK", 200

        return "OK", 200

    except Exception as e:

        logger.exception(
            "Telegram webhook error"
        )

        return (
            "ERROR",
            500
        )

        # ==================================================
# PRIVACY PAGE
# ==================================================

@app.route("/privacy")
def privacy_page():

    try:

        with open(
            "privacy.html",
            "r",
            encoding="utf-8"
        ) as f:

            return f.read()

    except FileNotFoundError:

        return (
            "Privacy Policy page not found.",
            404
        )

    except Exception as e:

        logger.exception(
            "Privacy page error"
        )

        return (
            "Privacy Policy error.",
            500
        )


# ==================================================
# DATABASE HEALTH CHECK
# ==================================================

@app.route("/health")
def health_check():

    try:

        conn = get_db()

        conn.execute(
            "SELECT 1"
        )

        conn.close()

        return {
            "status": "ok",
            "database": "connected"
        }, 200

    except Exception as e:

        logger.exception(
            "Health check error"
        )

        return {
            "status": "error",
            "database": "disconnected"
        }, 500


# ==================================================
# DATABASE CONFIG
# ==================================================

# Railway မှာ persistent volume ချိတ်ထားရင်
# DB_FILE environment variable ထည့်ထားနိုင်ပါတယ်။
#
# မထည့်ထားရင် app folder ထဲမှာ website.db
# ကို အသုံးပြုမယ်။

DB_FILE = os.environ.get(
    "DB_FILE",
    os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "website.db"
    )
)

db_directory = os.path.dirname(
    os.path.abspath(DB_FILE)
)

os.makedirs(
    db_directory,
    exist_ok=True
)


# ==================================================
# TELEGRAM SETTINGS
# ==================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
)

GROUP_ID = int(
    os.environ.get(
        "GROUP_ID",
        "0"
    )
)

OWNER_CHAT_ID = int(
    os.environ.get(
        "OWNER_CHAT_ID",
        "0"
    )
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Eren"
)


# ==================================================
# EMAIL SETTINGS
# ==================================================

EMAIL_ADDRESS = os.environ.get(
    "EMAIL_ADDRESS",
    ""
)

EMAIL_PASSWORD = os.environ.get(
    "EMAIL_PASSWORD",
    ""
)


# ==================================================
# FLASK SETTINGS
# ==================================================

app.secret_key = os.environ.get(
    "SECRET_KEY"
)

if not app.secret_key:

    # Production မှာ random secret
    # သုံးနိုင်အောင် fallback
    app.secret_key = os.urandom(
        32
    ).hex()

app.config[
    "MAX_CONTENT_LENGTH"
] = 10 * 1024 * 1024


# ==================================================
# DATABASE
# ==================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    try:

        # ------------------------------------------
        # USERS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password TEXT NOT NULL,
                balance INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                device_name TEXT DEFAULT 'Unknown'
            )
            """
        )

        # ------------------------------------------
        # WALLET TRANSACTIONS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # ------------------------------------------
        # ORDERS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                game TEXT,
                package TEXT,
                game_id TEXT,
                server_id TEXT,
                telegram_username TEXT,
                acc_mail TEXT,
                payment TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TEXT NOT NULL
            )
            """
        )

        # ------------------------------------------
        # DEPOSIT REQUESTS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            deposit_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                amount INTEGER NOT NULL,
                transaction_id TEXT NOT NULL,
                payment TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                created_at TEXT NOT NULL,
                telegram_username TEXT
            )
            """
        )

        # ------------------------------------------
        # PASSWORD RESETS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

        # ------------------------------------------
        # TELEGRAM FORWARD MAP
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            telegram_forward_map (
                owner_message_id INTEGER PRIMARY KEY,
                customer_chat_id INTEGER NOT NULL,
                customer_message_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )

        # ------------------------------------------
        # NOTIFICATIONS
        # ------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        # ------------------------------------------
        # MIGRATIONS
        # ------------------------------------------

        migrations = {

            "users": {
                "device_name":
                    "TEXT DEFAULT 'Unknown'"
            },

            "orders": {
                "telegram_username":
                    "TEXT",

                "acc_mail":
                    "TEXT"
            },

            "deposit_requests": {
                "telegram_username":
                    "TEXT"
            }
        }

        for table, columns in migrations.items():

            existing_columns = {
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }

            for column, definition in columns.items():

                if column not in existing_columns:

                    conn.execute(
                        f"""
                        ALTER TABLE {table}
                        ADD COLUMN {column}
                        {definition}
                        """
                    )

        conn.commit()

        print(
            "✅ Database initialized successfully"
        )

    except Exception:

        conn.rollback()

        logger.exception(
            "Database initialization failed"
        )

        raise

    finally:

        conn.close()


# ==================================================
# TIME HELPER
# ==================================================

def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ==================================================
# INITIALIZE DATABASE
# ==================================================

init_db()


# ==================================================
# WSGI APPLICATION
# ==================================================

application = app


# ==================================================
# RAILWAY STARTUP
# ==================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )

    print(
        f"🚀 Starting Flask on "
        f"0.0.0.0:{port}"
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

    
    )
    # ==================================================
# FINAL RAILWAY CONFIG
# ==================================================

application = app


# ==================================================
# ERROR HANDLERS
# ==================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <div style="
        background:#020617;
        color:white;
        min-height:100vh;
        display:flex;
        justify-content:center;
        align-items:center;
        text-align:center;
        font-family:Arial;
    ">

        <div>

            <h1 style="color:#00e5ff;">
                404
            </h1>

            <p>
                Page Not Found
            </p>

            <a
                href="/"
                style="
                    color:#00e5ff;
                    text-decoration:none;
                "
            >
                ← Home
            </a>

        </div>

    </div>
    """, 404


@app.errorhandler(500)
def internal_server_error(error):

    logger.exception(
        "Internal Server Error"
    )

    return """
    <div style="
        background:#020617;
        color:white;
        min-height:100vh;
        display:flex;
        justify-content:center;
        align-items:center;
        text-align:center;
        font-family:Arial;
    ">

        <div>

            <h1 style="color:#ef4444;">
                500
            </h1>

            <p>
                Server Error
            </p>

            <a
                href="/"
                style="
                    color:#00e5ff;
                    text-decoration:none;
                "
            >
                ← Home
            </a>

        </div>

    </div>
    """, 500


# ==================================================
# STARTUP
# ==================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )

    print(
        "===================================="
    )

    print(
        "🚀 Eren's Shop Starting..."
    )

    print(
        f"🌐 Port: {port}"
    )

    print(
        f"💾 Database: {DB_FILE}"
    )

    print(
        "===================================="
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
