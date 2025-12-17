from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- HOME PAGE ----------------
@app.route('/')
def home():
    return render_template('home.html')

# ---------------- REGISTER (TRIAL) ----------------
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

        print("USER REGISTERED:", email)

    return render_template("register.html")

# ---------------- LOGIN (TRIAL) ----------------
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
            print("LOGIN SUCCESS:", email)
        else:
            print("LOGIN FAILED")

    return render_template("login.html")

# ---------------- RUN SERVER ----------------
if __name__ == '__main__':
    app.run(debug=True)
