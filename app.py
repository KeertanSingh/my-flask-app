from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import uuid
import socket
import os
# =====================================================
# App Configuration
# =====================================================

app = Flask(__name__)
app.secret_key = "supersecretkey" # Required for securing Flask session data


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
# Home Route
# =====================================================

@app.route("/")
def home():
    return render_template("index.html")


# =====================================================
# OWNER ADD CUSTOMER (UPDATED LOGIC ONLY)
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

    # Check if customer already exists globally
    c.execute("SELECT id FROM customers WHERE phone=?", (phone,))
    existing = c.fetchone()

    if existing:
        customer_id = existing["id"]

        # Check if already linked to this owner
        c.execute("""
            SELECT id FROM owner_customers
            WHERE owner_id=? AND customer_id=?
        """, (session["user_id"], customer_id))

        link = c.fetchone()

        if link:
            conn.close()
            return redirect("/owner/dashboard?error=already_added")

        # Link existing customer to this owner
        c.execute("""
            INSERT INTO owner_customers (owner_id, customer_id)
            VALUES (?, ?)
        """, (session["user_id"], customer_id))

    else:
        # Create new customer
        customer_id = str(uuid.uuid4())

        c.execute(
            "INSERT INTO customers (id, name, phone, pin) VALUES (?, ?, ?, ?)",
            (customer_id, name, phone, pin if pin else None)
        )

        c.execute(
            "INSERT INTO owner_customers (owner_id, customer_id) VALUES (?, ?)",
            (session["user_id"], customer_id)
        )

    conn.commit()
    conn.close()

    return redirect("/owner/dashboard")


# =====================================================
# ADD TRANSACTION (UPDATED REDIRECT ONLY)
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

        # UPDATED redirect (shop specific)
        return redirect(f"/transactions/{session['user_id']}/{customer_id}")

    return render_template("owner/add_transaction.html", customer_id=customer_id)


# =====================================================
# TRANSACTIONS (UPDATED ROUTE ONLY)
# =====================================================

@app.route("/transactions/<owner_id>/<customer_id>")
def transactions(owner_id, customer_id):
    if "user_id" not in session:
        return redirect("/")

    # Security: customer can only see their own records
    if session.get("role") == "customer":
        if session["user_id"] != customer_id:
            return redirect("/")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM transactions
        WHERE customer_id=? AND owner_id=?
        ORDER BY created_at DESC
    """, (customer_id, owner_id))

    txns = c.fetchall()

    total = 0
    for t in txns:
        if t["type"] == "Payment":
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
# REST OF YOUR FILE REMAINS EXACTLY SAME
# =====================================================

# (Everything below remains unchanged — I did not remove anything)

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


if __name__ == "__main__":
    init_db()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
