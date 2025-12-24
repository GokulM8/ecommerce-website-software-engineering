from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ---------------- DATABASE CONNECTION ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "parking.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- DATABASE MIGRATION ----------------
def migrate_database():
    """Add payment_platform and upi_id columns if they don't exist"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if payment_platform column exists in vehicles
    cursor.execute("PRAGMA table_info(vehicles)")
    vehicle_columns = [column[1] for column in cursor.fetchall()]
    
    if 'payment_platform' not in vehicle_columns:
        try:
            cursor.execute("ALTER TABLE vehicles ADD COLUMN payment_platform TEXT DEFAULT 'Cash'")
            conn.commit()
            print("✅ Added payment_platform column to vehicles table")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Error adding column: {e}")
    
    # Check if upi_id column exists in users
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [column[1] for column in cursor.fetchall()]
    
    if 'upi_id' not in user_columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN upi_id TEXT")
            conn.commit()
            print("✅ Added upi_id column to users table")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Error adding column: {e}")
    
    conn.close()

# Run migration on startup
migrate_database()


# ---------------- HOME ----------------
@app.route('/')
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template('home.html')


# ---------------- REGISTER (ADMIN) ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (session['user_id'],)
    ).fetchone()
    conn.close()
    
    return render_template("profile.html", user=user)


# ---------------- UPDATE PROFILE ----------------
@app.route("/profile/update", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    username = request.form.get("username")
    email = request.form.get("email")
    upi_id = request.form.get("upi_id", "").strip()
    old_password = request.form.get("old_password")
    new_password = request.form.get("password")
    
    conn = get_db()
    
    # Get current user data
    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (session['user_id'],)
    ).fetchone()
    
    # Check if email is already taken by another user
    existing = conn.execute(
        "SELECT user_id FROM users WHERE email = ? AND user_id != ?",
        (email, session['user_id'])
    ).fetchone()
    
    if existing:
        conn.close()
        return render_template(
            "profile.html",
            user=user,
            error="Email already taken by another user"
        )
    
    # If password change is requested
    if old_password or new_password:
        # Both fields must be provided
        if not old_password or not new_password:
            conn.close()
            return render_template(
                "profile.html",
                user=user,
                error="Both current password and new password are required to change password"
            )
        
        # Verify old password
        if old_password != user['password']:
            conn.close()
            return render_template(
                "profile.html",
                user=user,
                error="Current password is incorrect"
            )
        
        # Update with new password and UPI ID
        conn.execute(
            "UPDATE users SET username = ?, email = ?, password = ?, upi_id = ? WHERE user_id = ?",
            (username, email, new_password, upi_id, session['user_id'])
        )
    else:
        # Update without password change, but with UPI ID
        conn.execute(
            "UPDATE users SET username = ?, email = ?, upi_id = ? WHERE user_id = ?",
            (username, email, upi_id, session['user_id'])
        )
    
    conn.commit()
    conn.close()
    
    # Update session
    session['username'] = username
    
    return redirect(url_for("dashboard"))


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    
    # Get user details
    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (session['user_id'],)
    ).fetchone()

    # Total amount collected
    cur.execute("SELECT SUM(fee) FROM vehicles WHERE fee IS NOT NULL")
    total_amount = cur.fetchone()[0] or 0

    # Parking slots
    cur.execute("SELECT * FROM parking_slots")
    slots = cur.fetchall()

    # Vehicle records
    cur.execute("SELECT * FROM vehicles")
    vehicles = cur.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        user_email=user['email'],
        slots=slots,
        vehicles=vehicles,
        total_amount=total_amount
    )

# ---------------- VEHICLE ENTRY ----------------
@app.route("/vehicle-entry", methods=["GET", "POST"])
def vehicle_entry():
    if request.method == "POST":
        vehicle_no = request.form["vehicle_no"]
        owner_name = request.form["owner_name"]
        entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()

        # Find first available slot
        slot = conn.execute(
            "SELECT slot_id FROM parking_slots WHERE status = 'Available' LIMIT 1"
        ).fetchone()

        if slot is None:
            conn.close()
            return "No parking slots available"

        slot_id = slot["slot_id"]

        # Insert vehicle
        conn.execute(
            """
            INSERT INTO vehicles (vehicle_no, owner_name, slot_id, entry_time)
            VALUES (?, ?, ?, ?)
            """,
            (vehicle_no, owner_name, slot_id, entry_time)
        )

        # Mark slot as occupied
        conn.execute(
            "UPDATE parking_slots SET status = 'Occupied' WHERE slot_id = ?",
            (slot_id,)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("vehicle_entry.html")


# ---------------- CALCULATE FEE (AJAX) ----------------
@app.route("/calculate-fee", methods=["POST"])
def calculate_fee():
    if "user_id" not in session:
        return {"error": "Unauthorized"}, 401
    
    data = request.get_json()
    vehicle_no = data.get("vehicle_no")
    
    if not vehicle_no:
        return {"error": "Vehicle number required"}, 400
    
    conn = get_db()
    vehicle = conn.execute("""
        SELECT v.vehicle_id, v.entry_time, v.slot_id, s.slot_name
        FROM vehicles v
        JOIN parking_slots s ON v.slot_id = s.slot_id
        WHERE v.vehicle_no = ? AND v.exit_time IS NULL
    """, (vehicle_no,)).fetchone()
    
    if vehicle is None:
        conn.close()
        return {"error": "Vehicle not found or already exited"}, 404
    
    # Get user's UPI ID
    user = conn.execute(
        "SELECT upi_id FROM users WHERE user_id = ?",
        (session['user_id'],)
    ).fetchone()
    
    # Fee calculation (₹20 per hour)
    entry = datetime.strptime(vehicle["entry_time"], "%Y-%m-%d %H:%M:%S")
    exit_ = datetime.now()
    hours = max(1, int((exit_ - entry).total_seconds() // 3600 + 1))
    fee = hours * 20
    
    conn.close()
    
    return {
        "fee": fee,
        "slot_name": vehicle["slot_name"],
        "hours": hours,
        "upi_id": user['upi_id'] if user and user['upi_id'] else None
    }


# ---------------- VEHICLE EXIT ----------------
@app.route("/vehicle-exit", methods=["GET", "POST"])
def vehicle_exit():
    if request.method == "POST":
        vehicle_no = request.form["vehicle_no"]
        payment_platform = request.form.get("payment_platform", "Cash")
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()

        vehicle = conn.execute("""
            SELECT v.vehicle_id, v.entry_time, v.slot_id, s.slot_name
            FROM vehicles v
            JOIN parking_slots s ON v.slot_id = s.slot_id
            WHERE v.vehicle_no = ? AND v.exit_time IS NULL
        """, (vehicle_no,)).fetchone()

        if vehicle is None:
            conn.close()
            return render_template(
                "vehicle_exit.html",
                error="Vehicle not found or already exited"
            )

        # Fee calculation (₹20 per hour)
        entry = datetime.strptime(vehicle["entry_time"], "%Y-%m-%d %H:%M:%S")
        exit_ = datetime.strptime(exit_time, "%Y-%m-%d %H:%M:%S")
        hours = max(1, int((exit_ - entry).total_seconds() // 3600 + 1))
        fee = hours * 20

        # Update vehicle with payment platform
        conn.execute("""
            UPDATE vehicles
            SET exit_time = ?, fee = ?, payment_platform = ?
            WHERE vehicle_id = ?
        """, (exit_time, fee, payment_platform, vehicle["vehicle_id"]))

        # Free slot
        conn.execute("""
            UPDATE parking_slots
            SET status = 'Available'
            WHERE slot_id = ?
        """, (vehicle["slot_id"],))

        conn.commit()
        conn.close()

        # Redirect to vehicle exit page with success message via query params
        return redirect(url_for('vehicle_exit', 
                               success='true', 
                               vehicle_no=vehicle_no,
                               slot_name=vehicle["slot_name"],
                               fee=fee,
                               payment_platform=payment_platform))

    # Handle GET request with success parameters
    success = request.args.get('success') == 'true'
    vehicle_no = request.args.get('vehicle_no')
    slot_name = request.args.get('slot_name')
    fee = request.args.get('fee')
    payment_platform = request.args.get('payment_platform')
    
    # If no parameters, render empty form
    return render_template(
        "vehicle_exit.html",
        success=success if success else False,
        vehicle_no=vehicle_no if vehicle_no else None,
        slot_name=slot_name if slot_name else None,
        fee=fee if fee else None,
        payment_platform=payment_platform if payment_platform else None
    )


@app.route("/payments")
def payments():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Get all completed payments with details
    cur.execute("""
        SELECT v.vehicle_no, v.owner_name, v.entry_time, v.exit_time, 
               v.fee, v.payment_platform, s.slot_name
        FROM vehicles v
        JOIN parking_slots s ON v.slot_id = s.slot_id
        WHERE v.fee IS NOT NULL
        ORDER BY v.exit_time DESC
    """)
    payment_records = cur.fetchall()

    # Amount collected till now
    cur.execute("SELECT SUM(fee) FROM vehicles WHERE fee IS NOT NULL")
    collected = cur.fetchone()[0] or 0

    # Payment platform breakdown
    cur.execute("""
        SELECT payment_platform, SUM(fee) as total, COUNT(*) as count
        FROM vehicles
        WHERE fee IS NOT NULL AND payment_platform IS NOT NULL
        GROUP BY payment_platform
    """)
    platform_stats = cur.fetchall()

    # Vehicles still parked (amount to be collected)
    cur.execute("""
        SELECT entry_time FROM vehicles
        WHERE exit_time IS NULL
    """)
    active_vehicles = cur.fetchall()

    to_be_collected = 0
    now = datetime.now()

    for v in active_vehicles:
        entry = datetime.strptime(v["entry_time"], "%Y-%m-%d %H:%M:%S")
        hours = max(1, int((now - entry).total_seconds() // 3600 + 1))
        to_be_collected += hours * 20

    total_amount = collected + to_be_collected

    conn.close()

    return render_template(
        "payments.html",
        collected=collected,
        to_be_collected=to_be_collected,
        total_amount=total_amount,
        payment_records=payment_records,
        platform_stats=platform_stats
    )


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(debug=True)
