from flask import Flask, render_template, request, redirect, session
import sqlite3
import uuid
import os

# =====================================================
# App Configuration
# =====================================================

app = Flask(__name__)
app.secret_key = "supersecretkey"


# =====================================================
# Database Helpers
# =====================================================

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            pin TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            pin TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS owner_customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            customer_id TEXT,
            is_active INTEGER DEFAULT 1,
            UNIQUE(owner_id, customer_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            customer_id TEXT,
            type TEXT,
            amount REAL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():
    return render_template("index.html")


# =====================================================
# OWNER ADD CUSTOMER (UPDATED LOGIC)
# =====================================================

@app.route("/owner/add-customer", methods=["POST"])
def add_customer():
    if session.get("role") != "owner":
        return redirect("/")

    name = request.form["name"].strip()
    phone = request.form["phone"].strip()
    pin = request.form.get("pin")

    if not phone or not phone.isdigit() or len(phone) != 10:
        return redirect("/owner/dashboard")

    conn = get_db()
    c = conn.cursor()

    # Check if customer exists globally
    c.execute("SELECT id FROM customers WHERE phone=?", (phone,))
    existing = c.fetchone()

    if existing:
        customer_id = existing["id"]

        # Check if already linked
        c.execute("""
            SELECT id FROM owner_customers
            WHERE owner_id=? AND customer_id=?
        """, (session["user_id"], customer_id))

        link = c.fetchone()

        if link:
            conn.close()
            return redirect("/owner/dashboard?error=already_added")

        c.execute("""
            INSERT INTO owner_customers (owner_id, customer_id)
            VALUES (?, ?)
        """, (session["user_id"], customer_id))

    else:
        # Create new customer
        customer_id = str(uuid.uuid4())

        c.execute("""
            INSERT INTO customers (id, name, phone, pin)
            VALUES (?, ?, ?, ?)
        """, (customer_id, name, phone, pin if pin else None))

        c.execute("""
            INSERT INTO owner_customers (owner_id, customer_id)
            VALUES (?, ?)
        """, (session["user_id"], customer_id))

    conn.commit()
    conn.close()

    return redirect("/owner/dashboard")


# =====================================================
# ADD TRANSACTION (UPDATED REDIRECT)
# =====================================================

@app.route("/add-transaction/<customer_id>", methods=["GET", "POST"])
def add_transaction(customer_id):
    if session.get("role") != "owner":
        return redirect("/")

    if request.method == "POST":
        type_ = request.form["type"]
        amount = float(request.form["amount"])
        note = request.form["note"]

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            INSERT INTO transactions (owner_id, customer_id, type, amount, note)
            VALUES (?, ?, ?, ?, ?)
        """, (session["user_id"], customer_id, type_, amount, note))

        conn.commit()
        conn.close()

        return redirect(f"/transactions/{session['user_id']}/{customer_id}")

    return render_template("owner/add_transaction.html", customer_id=customer_id)


# =====================================================
# TRANSACTIONS (NOW SHOP-SPECIFIC)
# =====================================================

@app.route("/transactions/<owner_id>/<customer_id>")
def transactions(owner_id, customer_id):
    if "user_id" not in session:
        return redirect("/")

    # Security check for customers
    if session.get("role") == "customer":
        if session["user_id"] != customer_id:
            return redirect("/")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM transactions
        WHERE owner_id=? AND customer_id=?
        ORDER BY created_at DESC
    """, (owner_id, customer_id))

    txns = c.fetchall()

    total = 0
    for t in txns:
        if t["type"].lower() == "payment":
            total -= t["amount"]
        else:
            total += t["amount"]

    conn.close()

    return render_template(
        "customer/transactions.html",
        transactions=txns,
        total=total
    )


# =====================================================
# UPDATE CUSTOMER PHONE (SAFE)
# =====================================================

@app.route("/owner/update-customer-phone/<customer_id>", methods=["POST"])
def update_customer_phone(customer_id):
    if session.get("role") != "owner":
        return redirect("/")

    new_phone = request.form["phone"].strip()

    if not new_phone or len(new_phone) != 10 or not new_phone.isdigit():
        return redirect("/owner/dashboard")

    conn = get_db()
    c = conn.cursor()

    # Prevent duplicate global phone
    c.execute("SELECT id FROM customers WHERE phone=? AND id!=?",
              (new_phone, customer_id))

    if c.fetchone():
        conn.close()
        return redirect("/owner/dashboard?error=phone_exists")

    c.execute("UPDATE customers SET phone=? WHERE id=?",
              (new_phone, customer_id))

    conn.commit()
    conn.close()

    return redirect("/owner/dashboard")


# =====================================================
# LOGOUT + CACHE CONTROL
# =====================================================

@app.route("/logout")
def logout():
    session.clear()
    response = redirect("/")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =====================================================
# START
# =====================================================

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
