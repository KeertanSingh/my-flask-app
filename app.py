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

# Creates and returns a connection to the SQLite database
# row_factory allows us to access columns by name instead of index
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# Initializes the database and creates required tables if they do not exist
def init_db():
    conn = get_db()        # Establish database connection
    c = conn.cursor()      # Create cursor object to execute SQL queries


    # Owners Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            pin TEXT NOT NULL
        )
    """)

    # Customers Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            pin TEXT
        )
    """)

    # Owner-Customer Relationship Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS owner_customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            customer_id TEXT,
            is_active INTEGER DEFAULT 1,
            UNIQUE(owner_id, customer_id)
        )
    """)

    # Transactions Table
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
# CUSTOMER AUTHENTICATION
# =====================================================

@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():

    if request.method == "GET":
        mode = request.args.get("mode", "pin")
        return render_template("customer/login.html", mode=mode)

    phone = request.form["phone"]
    mode = request.form["mode"]

    conn = get_db()
    c = conn.cursor()

    if mode == "pin":
        pin = request.form["pin"]
        c.execute("SELECT * FROM customers WHERE phone=? AND pin=?", (phone, pin))
        customer = c.fetchone()

        if customer:
            session["user_id"] = customer["id"]
            session["role"] = "customer"
            session["name"] = customer["name"]
            conn.close()
            return redirect("/customer/dashboard")

        conn.close()
        return render_template(
            "customer/login.html",
            error="Invalid phone or PIN",
            mode="pin"
        )

    else:
        otp = request.form["otp"]

        if otp != "1234":
            conn.close()
            return render_template(
                "customer/login.html",
                error="Invalid OTP. Use 1234 for demo.",
                mode="otp"
            )

        c.execute("SELECT * FROM customers WHERE phone=?", (phone,))
        customer = c.fetchone()

        if not customer:
            conn.close()
            return render_template(
                "customer/login.html",
                error="No account found with this phone number.",
                mode="otp"
            )

        session["user_id"] = customer["id"]
        session["role"] = "customer"
        session["name"] = customer["name"]
        conn.close()
        return redirect("/customer/dashboard")


# =====================================================
# CUSTOMER DASHBOARD
# =====================================================

@app.route("/customer/dashboard")
def customer_dashboard():
    if session.get("role") != "customer":
        return redirect("/")

    customer_id = session["user_id"]

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT o.id as owner_id, o.name, o.phone
        FROM owner_customers oc
        JOIN owners o ON oc.owner_id = o.id
        WHERE oc.customer_id=? AND oc.is_active=1
    """, (customer_id,))

    shops = c.fetchall()
    conn.close()

    return render_template("customer/dashboard.html", shops=shops)


# =====================================================
# OWNER AUTHENTICATION
# =====================================================

@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():

    if request.method == "GET":
        mode = request.args.get("mode", "pin")
        return render_template("owner/login.html", mode=mode)

    phone = request.form["phone"]
    mode = request.form["mode"]

    conn = get_db()
    c = conn.cursor()

    if mode == "pin":
        pin = request.form["pin"]
        c.execute("SELECT * FROM owners WHERE phone=? AND pin=?", (phone, pin))
        owner = c.fetchone()

        if owner:
            session["user_id"] = owner["id"]
            session["role"] = "owner"
            session["name"] = owner["name"]
            conn.close()
            return redirect("/owner/dashboard")

        conn.close()
        return render_template(
            "owner/login.html",
            error="Invalid phone or PIN",
            mode="pin"
        )

    else:
        otp = request.form["otp"]

        if otp != "1234":
            conn.close()
            return render_template(
                "owner/login.html",
                error="Invalid OTP. Use 1234 for demo.",
                mode="otp"
            )

        c.execute("SELECT * FROM owners WHERE phone=?", (phone,))
        owner = c.fetchone()

        if not owner:
            conn.close()
            return render_template(
                "owner/login.html",
                register=True,
                phone=phone
            )

        session["user_id"] = owner["id"]
        session["role"] = "owner"
        session["name"] = owner["name"]
        conn.close()
        return redirect("/owner/dashboard")


# =====================================================
# OWNER REGISTRATION
# =====================================================

@app.route("/owner/register", methods=["POST"])
def owner_register():
    name = request.form["name"]
    phone = request.form["phone"]
    pin = request.form["pin"]

    conn = get_db()
    c = conn.cursor()

    owner_id = str(uuid.uuid4())

    c.execute("INSERT INTO owners VALUES (?, ?, ?, ?)",
              (owner_id, name, phone, pin))

    conn.commit()
    conn.close()

    session["user_id"] = owner_id
    session["role"] = "owner"
    session["name"] = name

    return redirect("/owner/dashboard")


# =====================================================
# OWNER DASHBOARD
# =====================================================

@app.route("/owner/dashboard")
def owner_dashboard():
    if session.get("role") != "owner":
        return redirect("/")

    owner_id = session["user_id"]
    filter_type = request.args.get("filter", "active")


    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT oc.id, oc.customer_id, oc.is_active, c.name, c.phone
        FROM owner_customers oc
        JOIN customers c ON oc.customer_id = c.id
        WHERE oc.owner_id=?
    """

    if filter_type == "active":
        query += " AND oc.is_active=1"
    elif filter_type == "inactive":
        query += " AND oc.is_active=0"

    c.execute(query, (owner_id,))
    customers = c.fetchall()

    c.execute("SELECT COUNT(*) FROM owner_customers WHERE owner_id=?", (owner_id,))
    total_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM owner_customers WHERE owner_id=? AND is_active=1", (owner_id,))
    active_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM owner_customers WHERE owner_id=? AND is_active=0", (owner_id,))
    inactive_count = c.fetchone()[0]

    conn.close()

    return render_template(
        "owner/dashboard.html",
        customers=customers,
        total_count=total_count,
        active_count=active_count,
        inactive_count=inactive_count,
        current_filter=filter_type
    )


# =====================================================
# OWNER ACTIONS
# =====================================================

@app.route("/owner/toggle/<int:link_id>")
def toggle_customer(link_id):
    if session.get("role") != "owner":
        return redirect("/")

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT is_active FROM owner_customers WHERE id=?", (link_id,))
    current = c.fetchone()

    if current:
        new_status = 0 if current["is_active"] else 1
        c.execute(
            "UPDATE owner_customers SET is_active=? WHERE id=?",
            (new_status, link_id)
        )
        conn.commit()

    conn.close()
    return redirect("/owner/dashboard")


@app.route("/owner/add-customer", methods=["POST"])
def add_customer():
    if session.get("role") != "owner":
        return redirect("/")

    name = request.form["name"].strip()
    phone = request.form["phone"].strip()
    pin = request.form.get("pin")

    # Basic validation
    if not phone or not phone.isdigit() or len(phone) != 10:
        return redirect("/owner/dashboard")

    conn = get_db()
    c = conn.cursor()

    # Check if phone already exists
    c.execute("SELECT id FROM customers WHERE phone=?", (phone,))
    existing = c.fetchone()

    if existing:
        conn.close()
        return redirect("/owner/dashboard?error=phone_exists")

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


@app.route("/owner/update-customer-phone/<customer_id>", methods=["POST"])
def update_customer_phone(customer_id):
    if session.get("role") != "owner":
        return redirect("/")

    new_phone = request.form["phone"]

    if not new_phone or len(new_phone) != 10 or not new_phone.isdigit():
        return redirect("/owner/dashboard")

    conn = get_db()
    c = conn.cursor()

    c.execute("UPDATE customers SET phone=? WHERE id=?",
              (new_phone, customer_id))

    conn.commit()
    conn.close()

    return redirect("/owner/dashboard")


# =====================================================
# TRANSACTIONS
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

        return redirect(f"/transactions/{customer_id}")

    return render_template("owner/add_transaction.html", customer_id=customer_id)


@app.route("/transactions/<customer_id>")
def transactions(customer_id):
    if "user_id" not in session:
        return redirect("/")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM transactions
        WHERE customer_id=?
        ORDER BY created_at DESC
    """, (customer_id,))

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

#delete customer
@app.route("/owner/delete/<int:link_id>")
def delete_customer(link_id):
    if session.get("role") != "owner":
        return redirect("/")

    conn = get_db()
    c = conn.cursor()

    # Get related customer_id
    c.execute("SELECT customer_id FROM owner_customers WHERE id=?", (link_id,))
    row = c.fetchone()

    if row:
        customer_id = row["customer_id"]

        # Delete relationship
        c.execute("DELETE FROM owner_customers WHERE id=?", (link_id,))

        # OPTIONAL: Delete customer completely if no other owners linked
        c.execute("SELECT COUNT(*) FROM owner_customers WHERE customer_id=?", (customer_id,))
        count = c.fetchone()[0]

        if count == 0:
            c.execute("DELETE FROM customers WHERE id=?", (customer_id,))

    conn.commit()
    conn.close()

    return redirect("/owner/dashboard?filter=inactive")

# =====================================================
# PIN UPDATE
# =====================================================

@app.route("/update-pin", methods=["GET", "POST"])
def update_pin():

    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":
        old_pin = request.form["old_pin"]
        new_pin = request.form["new_pin"]

        if len(new_pin) != 4 or not new_pin.isdigit():
            return redirect("/update-pin")

        conn = get_db()
        c = conn.cursor()

        table = "owners" if session.get("role") == "owner" else "customers"

        c.execute(f"SELECT pin FROM {table} WHERE id=?",
                  (session["user_id"],))
        user = c.fetchone()

        if not user or user["pin"] != old_pin:
            conn.close()
            return redirect("/update-pin")

        c.execute(f"UPDATE {table} SET pin=? WHERE id=?",
                  (new_pin, session["user_id"]))

        conn.commit()
        conn.close()

        if session.get("role") == "owner":
            return redirect("/owner/dashboard")
        else:
            return redirect("/customer/dashboard")

    return render_template("update_pin.html")


# =====================================================
# LOGOUT & CACHE CONTROL
# =====================================================

@app.route("/logout")
def logout():
    session.clear()
    response = redirect("/")
    response.headers["Cache-Control"] = "no-store"
    return response

# Adds no-cache headers to every response to prevent browser caching
# This ensures users cannot access protected pages using the back button after logout
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =====================================================
# APP START
# =====================================================

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)