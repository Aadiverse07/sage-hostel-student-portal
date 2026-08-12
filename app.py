from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import re
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")

# Fixed administrator credentials. Student accounts continue to use their own
# registered email/password credentials.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeThisAdminPassword!")
ADMIN_SESSION_KEY = os.environ.get("ADMIN_SESSION_KEY", "change-this-admin-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "hostel.db"))


# ==========================================
# DATABASE
# ==========================================

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(cursor, table, column, definition):
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    # Existing students table is preserved and upgraded in place.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            branch TEXT,
            year TEXT,
            room TEXT
        )
    """)

    add_column_if_missing(cursor, "students", "email", "TEXT")
    add_column_if_missing(cursor, "students", "phone", "TEXT")
    add_column_if_missing(cursor, "students", "guardian_name", "TEXT")
    add_column_if_missing(cursor, "students", "guardian_phone", "TEXT")
    add_column_if_missing(cursor, "students", "created_at", "TEXT")
    add_column_if_missing(cursor, "students", "last_login", "TEXT")
    add_column_if_missing(cursor, "students", "password_updated_at", "TEXT")

    # Password reset history is retained locally so account changes remain auditable.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            requested_at TEXT NOT NULL,
            reset_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    # Existing demo/legacy passwords may be plain text from older project versions.
    # Upgrade them in place to secure password hashes without changing the UI or accounts.
    legacy_rows = cursor.execute("SELECT id, password FROM students").fetchall()
    for legacy in legacy_rows:
        current = legacy["password"]
        if current and not current.startswith(("pbkdf2:", "scrypt:", "argon2:")):
            cursor.execute(
                "UPDATE students SET password = ?, password_updated_at = COALESCE(password_updated_at, ?) WHERE id = ?",
                (generate_password_hash(current), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), legacy["id"])
            )

    # Supporting tables are intentionally small and ready for the next modules.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            floor TEXT,
            capacity INTEGER DEFAULT 1,
            facilities TEXT,
            status TEXT DEFAULT 'Occupied'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fees(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Pending',
            due_date TEXT,
            paid_date TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_ref TEXT UNIQUE NOT NULL,
            student_id INTEGER NOT NULL,
            room_number TEXT NOT NULL,
            name TEXT NOT NULL,
            enrollment TEXT NOT NULL,
            branch TEXT,
            year TEXT,
            phone TEXT,
            email TEXT,
            guardian_name TEXT,
            booking_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Confirmed',
            receipt_no TEXT UNIQUE NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    add_column_if_missing(cursor, "room_bookings", "payment_ref", "TEXT")
    add_column_if_missing(cursor, "room_bookings", "booking_fee", "REAL DEFAULT 500")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_ref TEXT UNIQUE NOT NULL,
            student_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending Verification',
            created_at TEXT NOT NULL,
            submitted_at TEXT,
            verified_at TEXT,
            receipt_no TEXT UNIQUE NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    add_column_if_missing(cursor, "payment_records", "room_number", "TEXT")
    add_column_if_missing(cursor, "payment_records", "payment_type", "TEXT DEFAULT 'General'")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            category TEXT,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Development/demo student. INSERT OR IGNORE keeps an existing account intact.
    cursor.execute("""
        INSERT OR IGNORE INTO students
        (enrollment, password, name, branch, year, room, email, phone, guardian_name, guardian_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "DEMO230001",
        generate_password_hash("Demo@12345"),
        "Demo Student",
        "B.Tech CSE",
        "2nd Year",
        "307",
        "demo.student@example.com",
        "9000000000",
        "Demo Guardian",
        "9000000001",
    ))

    cursor.execute(
        "UPDATE students SET created_at = COALESCE(created_at, ?) WHERE created_at IS NULL OR created_at = ''",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),)
    )

    # Existing student/profile values are intentionally preserved.

    cursor.execute("""
        INSERT OR IGNORE INTO rooms (room_number, floor, capacity, facilities, status)
        VALUES ('307', '3rd Floor', 2, 'Wi-Fi, Study Table, Cupboard, Attached Bathroom', 'Occupied')
    """)

    # A small set of bookable rooms for the room-booking module. Existing room
    # records are never overwritten.
    for room_number, floor, capacity in [
        ('101', '1st Floor', 2), ('102', '1st Floor', 2),
        ('201', '2nd Floor', 2), ('202', '2nd Floor', 2),
        ('301', '3rd Floor', 2), ('302', '3rd Floor', 2),
    ]:
        cursor.execute(
            """INSERT OR IGNORE INTO rooms (room_number, floor, capacity, facilities, status)
               VALUES (?, ?, ?, ?, 'Available')""",
            (room_number, floor, capacity, 'Wi-Fi, Study Table, Cupboard, Attached Bathroom')
        )

    student = cursor.execute(
        "SELECT id FROM students WHERE enrollment = ?", ("DEMO230001",)
    ).fetchone()

    if student:
        student_id = student["id"]

        # Seed attendance only when this student has no records yet.
        existing_attendance = cursor.execute(
            "SELECT COUNT(*) AS count FROM attendance WHERE student_id = ?", (student_id,)
        ).fetchone()["count"]
        if existing_attendance == 0:
            cursor.executemany(
                "INSERT INTO attendance (student_id, attendance_date, status) VALUES (?, ?, ?)",
                [
                    (student_id, "2026-08-03", "Present"),
                    (student_id, "2026-08-04", "Present"),
                    (student_id, "2026-08-05", "Present"),
                    (student_id, "2026-08-06", "Present"),
                    (student_id, "2026-08-07", "Absent"),
                    (student_id, "2026-08-08", "Present"),
                    (student_id, "2026-08-10", "Present"),
                ],
            )

        existing_fee = cursor.execute(
            "SELECT COUNT(*) AS count FROM fees WHERE student_id = ?", (student_id,)
        ).fetchone()["count"]
        if existing_fee == 0:
            cursor.execute(
                """INSERT INTO fees (student_id, amount, status, due_date, paid_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (student_id, 25000, "Paid", "2026-07-31", "2026-07-28"),
            )

        # One genuine outstanding item is shown in the new Payment Due section.
        # It is kept separate from the historic hostel fee records.
        existing_due = cursor.execute(
            "SELECT COUNT(*) AS count FROM payment_records WHERE student_id = ? AND purpose = ? AND status != 'Paid'",
            (student_id, "Hostel Maintenance & Utility Due")
        ).fetchone()["count"]
        if existing_due == 0:
            payment_ref = f"PAY-{datetime.now().strftime('%Y%m%d')}-{student_id:04d}"
            receipt_no = f"SAGE-PAY-{datetime.now().strftime('%Y%m%d')}-{student_id:04d}"
            cursor.execute(
                """INSERT INTO payment_records
                   (payment_ref, student_id, purpose, amount, status, created_at, receipt_no)
                   VALUES (?, ?, ?, ?, 'Pending Verification', ?, ?)""",
                (payment_ref, student_id, "Hostel Maintenance & Utility Due", 1500, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), receipt_no)
            )

        existing_complaints = cursor.execute(
            "SELECT COUNT(*) AS count FROM complaints WHERE student_id = ?", (student_id,)
        ).fetchone()["count"]
        if existing_complaints == 0:
            cursor.execute(
                """INSERT INTO complaints (student_id, category, description, status)
                   VALUES (?, ?, ?, ?)""",
                (student_id, "Maintenance", "Study table light needs inspection.", "Open"),
            )

    notice_count = cursor.execute("SELECT COUNT(*) AS count FROM notices").fetchone()["count"]
    if notice_count == 0:
        cursor.executemany(
            "INSERT INTO notices (title, content, category) VALUES (?, ?, ?)",
            [
                ("Hostel Gate Timing", "Hostel gate closes at 10:00 PM.", "Important"),
                ("Mess Maintenance", "Mess maintenance is scheduled for Sunday.", "Mess"),
                ("Wi-Fi Upgrade", "Wi-Fi service has been upgraded for all hostel blocks.", "Facility"),
                ("Hostel ID", "Keep your Hostel ID with you while inside campus.", "Reminder"),
            ],
        )

    conn.commit()
    conn.close()


# Initialize the local database for both development and WSGI deployment.
initialize_database()

# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    # The same existing login UI also accepts the fixed administrator account.
    # No separate admin page or UI redesign is required.
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session.clear()
        session["admin"] = True
        session["admin_email"] = ADMIN_EMAIL
        session["admin_key"] = ADMIN_SESSION_KEY
        return redirect(url_for("admin_records"))

    conn = get_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE LOWER(email) = ?",
        (email,),
    ).fetchone()

    if student and check_password_hash(student["password"], password):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("UPDATE students SET last_login = ? WHERE id = ?", (now, student["id"]))
        conn.commit()
        conn.close()

        session.clear()
        session["student_id"] = student["id"]
        session["student"] = student["name"]
        session["enrollment"] = student["enrollment"]
        session["room"] = student["room"]
        session["branch"] = student["branch"]
        session["year"] = student["year"]
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("index.html", error="Invalid Email or Password", login_email=email)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    errors = []
    if len(name) < 2:
        errors.append("Please enter your full name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("Please enter a valid email address.")
    phone_digits = re.sub(r"\D", "", phone)
    if not 7 <= len(phone_digits) <= 15:
        errors.append("Please enter a valid phone number.")
    if len(password) < 8:
        errors.append("Password must contain at least 8 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM students WHERE LOWER(email) = ?", (email,)).fetchone()
    if existing:
        errors.append("An account with this email already exists. Please log in or reset your password.")

    if errors:
        conn.close()
        return render_template("signup.html", error=" ".join(errors), name=name, email=email, phone=phone)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Enrollment is retained only as an internal/student-record identifier; it is no longer used for login.
    year_prefix = datetime.now().strftime('%y')
    count = conn.execute("SELECT COUNT(*) AS count FROM students").fetchone()["count"] + 1
    enrollment = f"SAGE{year_prefix}{count:06d}"

    try:
        cursor = conn.execute(
            """INSERT INTO students
               (enrollment, password, name, branch, year, room, email, phone, guardian_name, guardian_phone, created_at, password_updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                enrollment,
                generate_password_hash(password),
                name,
                "Not Provided",
                "Not Provided",
                None,
                email,
                phone_digits,
                None,
                None,
                now,
                now,
            ),
        )
        conn.commit()
        student_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return render_template("signup.html", error="That email is already registered. Please use another email or reset the existing account.", name=name, email=email, phone=phone)

    # Give every new student a real initial hostel fee ledger and a current payment due.
    # This keeps Fee Status meaningful from the first login.
    try:
        conn.execute("INSERT INTO fees(student_id, amount, status, due_date, paid_date) VALUES(?,?,?,?,?)",
                     (student_id, 25000, "Paid", now[:10], now[:10]))
        pay_ref = f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{student_id:04d}"
        pay_receipt = f"SAGE-PAY-{datetime.now().strftime('%Y%m%d')}-{student_id:04d}-001"
        conn.execute("""INSERT INTO payment_records(payment_ref,student_id,purpose,amount,status,created_at,receipt_no,payment_type)
                       VALUES(?,?,?,?,?,?,?,?)""",
                     (pay_ref, student_id, "Hostel Maintenance & Utility Due", 1500, "Pending Verification", now, pay_receipt, "General"))
        conn.commit()
    finally:
        conn.close()
    session.clear()
    session["student_id"] = student_id
    session["student"] = name
    session["enrollment"] = enrollment
    session["room"] = None
    session["branch"] = "Not Provided"
    session["year"] = "Not Provided"
    return redirect(url_for("dashboard"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        return render_template("reset_password.html")

    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    phone_digits = re.sub(r"\D", "", phone)

    if len(new_password) < 8:
        return render_template("reset_password.html", error="New password must contain at least 8 characters.", email=email, phone=phone)
    if new_password != confirm_password:
        return render_template("reset_password.html", error="Passwords do not match.", email=email, phone=phone)

    conn = get_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE LOWER(email) = ? AND phone = ?",
        (email, phone_digits),
    ).fetchone()

    if not student:
        conn.close()
        return render_template("reset_password.html", error="We could not verify those details. Please use the same email and phone number used when signing up.", email=email, phone=phone)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "UPDATE students SET password = ?, password_updated_at = ? WHERE id = ?",
        (generate_password_hash(new_password), now, student["id"]),
    )
    conn.execute(
        "INSERT INTO password_resets (student_id, requested_at, reset_at) VALUES (?, ?, ?)",
        (student["id"], now, now),
    )
    conn.commit()
    conn.close()

    return render_template("index.html", success="Password reset successfully. You can now log in with your email and new password.", login_email=email)


@app.route("/dashboard")
def dashboard():
    if "student_id" not in session:
        return redirect(url_for("home"))

    conn = get_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE id = ?", (session["student_id"],)
    ).fetchone()

    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("home"))

    attendance = conn.execute(
        """
        SELECT
            ROUND(100.0 * SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 0) AS percentage
        FROM attendance
        WHERE student_id = ?
        """,
        (student["id"],),
    ).fetchone()["percentage"]

    fee = conn.execute(
        """
        SELECT status
        FROM fees
        WHERE student_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (student["id"],),
    ).fetchone()

    complaint_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM complaints
        WHERE student_id = ? AND status != 'Resolved'
        """,
        (student["id"],),
    ).fetchone()["count"]

    room_details = conn.execute(
        "SELECT * FROM rooms WHERE room_number = ?", (student["room"],)
    ).fetchone()

    notices = conn.execute(
        """
        SELECT title, content, category
        FROM notices
        WHERE is_active = 1
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 4
        """
    ).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        student=student,
        room=student["room"],
        branch=student["branch"],
        year=student["year"],
        attendance=attendance if attendance is not None else 0,
        fee_status=fee["status"] if fee else "Pending",
        complaint_count=complaint_count,
        room_details=room_details,
        notices=notices,
    )


@app.route("/attendance")
def attendance():
    if "student_id" not in session:
        return redirect(url_for("home"))

    conn = get_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (session["student_id"],)
    ).fetchone()

    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("home"))

    # Full history is always used for the overall percentage/stats/streak so
    # those numbers never shift when a month filter is applied below.
    all_records = conn.execute(
        """
        SELECT attendance_date AS date, status
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC
        """,
        (student["id"],)
    ).fetchall()

    # Distinct months present in this student's real records, for the filter dropdown.
    available_months = [
        row["month"] for row in conn.execute(
            """
            SELECT DISTINCT substr(attendance_date, 1, 7) AS month
            FROM attendance
            WHERE student_id = ?
            ORDER BY month DESC
            """,
            (student["id"],)
        ).fetchall()
    ]
    conn.close()

    selected_month = request.args.get("month", "").strip()
    if selected_month and selected_month in available_months:
        filtered = [r for r in all_records if r["date"].startswith(selected_month)]
    else:
        selected_month = ""
        filtered = all_records

    # Enrich with the real weekday name for each recorded date (the table's
    # "Day" column previously showed a slice of the date string, not the day).
    records = []
    for r in filtered:
        try:
            weekday = date.fromisoformat(r["date"]).strftime("%a")
        except ValueError:
            weekday = "—"
        records.append({"date": r["date"], "status": r["status"], "weekday": weekday})

    total = len(all_records)
    present = sum(1 for r in all_records if (r["status"] or "").lower() == "present")
    absent = sum(1 for r in all_records if (r["status"] or "").lower() == "absent")
    percentage = round((present / total) * 100, 1) if total else 0

    # Current present streak: consecutive "Present" days counting back from the
    # most recent recorded day (stops at the first Absent, if any).
    streak = 0
    for r in all_records:
        if (r["status"] or "").lower() == "present":
            streak += 1
        else:
            break

    return render_template(
        "attendance.html",
        student=student,
        records=records,
        total=total,
        present=present,
        absent=absent,
        percentage=percentage,
        streak=streak,
        available_months=available_months,
        selected_month=selected_month
    )

@app.route("/fees")
def fees():
    if "student_id" not in session:
        return redirect(url_for("home"))

    conn = get_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE id = ?", (session["student_id"],)
    ).fetchone()
    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("home"))

    fee_history = conn.execute(
        """SELECT id, amount, status, due_date, paid_date
           FROM fees WHERE student_id=?
           ORDER BY due_date DESC, id DESC""",
        (student["id"],)
    ).fetchall()
    payment_due = conn.execute(
        """SELECT * FROM payment_records WHERE student_id = ?
           AND status != 'Paid' ORDER BY id DESC LIMIT 1""",
        (student["id"],)
    ).fetchone()
    conn.close()

    total_amount = sum(float(r["amount"] or 0) for r in fee_history)
    paid_amount = sum(float(r["amount"] or 0) for r in fee_history
                      if (r["status"] or "").lower() == "paid")
    pending_amount = max(total_amount - paid_amount, 0)

    # Real overdue detection: a Pending record is overdue only if its own
    # due_date has actually passed, computed from today's date - no fake flags.
    today = date.today()

    def parse_due(value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    overdue_ids = set()
    for r in fee_history:
        if (r["status"] or "").lower() == "pending":
            due = parse_due(r["due_date"])
            if due and due < today:
                overdue_ids.add(r["id"])

    latest_fee = fee_history[0] if fee_history else None
    latest_days_until_due = None
    if latest_fee and (latest_fee["status"] or "").lower() == "pending":
        due = parse_due(latest_fee["due_date"])
        if due:
            latest_days_until_due = (due - today).days

    return render_template(
        "fees.html", student=student, fee_history=fee_history,
        latest_fee=latest_fee,
        total_amount=total_amount, paid_amount=paid_amount,
        pending_amount=pending_amount,
        overdue_ids=overdue_ids,
        latest_days_until_due=latest_days_until_due,
        payment_due=payment_due
    )

@app.route("/room", methods=["GET", "POST"])
def room_details():
    if "student_id" not in session:
        return redirect(url_for("home"))
    conn = get_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()
    if not student:
        conn.close(); session.clear(); return redirect(url_for("home"))

    if request.method == "POST":
        room_number = request.form.get("room_number", "").strip()
        try:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT * FROM students WHERE id=?", (student["id"],)).fetchone()
            if current["room"]:
                conn.rollback(); conn.close(); flash(f"You already have Room {current['room']} allotted to you.", "info"); return redirect(url_for("room_details"))
            selected = conn.execute("SELECT * FROM rooms WHERE room_number=?", (room_number,)).fetchone()
            if not selected:
                conn.rollback(); conn.close(); flash("Please select a valid available room.", "error"); return redirect(url_for("room_details"))
            occupied = conn.execute("SELECT COUNT(*) AS count FROM students WHERE room=?", (room_number,)).fetchone()["count"]
            if occupied >= (selected["capacity"] or 0) or (selected["status"] or "").lower() in {"maintenance", "unavailable"}:
                conn.rollback(); conn.close(); flash(f"Room {room_number} is no longer available. Please choose another room.", "error"); return redirect(url_for("room_details"))
            # Reuse an unpaid booking-fee payment if the student already started the checkout.
            existing = conn.execute("""SELECT * FROM payment_records WHERE student_id=? AND payment_type='Room Booking' AND room_number=? AND status != 'Paid' ORDER BY id DESC LIMIT 1""", (student["id"], room_number)).fetchone()
            if existing:
                conn.commit(); conn.close(); return redirect(url_for("room_payment", payment_ref=existing["payment_ref"]))
            now=datetime.now(); stamp=now.strftime('%Y%m%d%H%M%S%f')
            payment_ref=f"ROOMPAY-{stamp}-{student['id']:04d}"
            receipt_no=f"SAGE-ROOMPAY-{now.strftime('%Y%m%d')}-{student['id']:04d}-{conn.execute('SELECT COUNT(*) FROM payment_records').fetchone()[0]+1:03d}"
            conn.execute("""INSERT INTO payment_records(payment_ref,student_id,purpose,amount,status,created_at,receipt_no,room_number,payment_type) VALUES(?,?,?,?,?,?,?,?,?)""",
                         (payment_ref,student["id"],f"Room Booking Fee - Room {room_number}",500,"Pending Verification",now.strftime('%Y-%m-%d %H:%M:%S'),receipt_no,room_number,"Room Booking"))
            conn.commit(); conn.close()
            return redirect(url_for("room_payment", payment_ref=payment_ref))
        except sqlite3.Error:
            conn.rollback(); conn.close(); flash("We could not start the room booking payment. Please try again.", "error"); return redirect(url_for("room_details"))

    room = conn.execute("SELECT * FROM rooms WHERE room_number=?", (student["room"],)).fetchone() if student["room"] else None
    roommates=[]
    if room:
        roommates=conn.execute("SELECT name,enrollment,branch FROM students WHERE room=? AND id != ? ORDER BY name", (student["room"],student["id"])).fetchall()
    available_rooms=conn.execute("""SELECT r.*, (r.capacity-COUNT(s.id)) AS available_beds FROM rooms r LEFT JOIN students s ON s.room=r.room_number WHERE LOWER(COALESCE(r.status,'available')) NOT IN ('maintenance','unavailable') GROUP BY r.id HAVING available_beds>0 ORDER BY r.room_number""").fetchall()
    room_directory=conn.execute("""SELECT r.*, COUNT(s.id) AS occupied_beds,(r.capacity-COUNT(s.id)) AS available_beds FROM rooms r LEFT JOIN students s ON s.room=r.room_number GROUP BY r.id ORDER BY r.room_number""").fetchall()
    latest_booking=conn.execute("SELECT * FROM room_bookings WHERE student_id=? ORDER BY id DESC LIMIT 1", (student["id"],)).fetchone()
    pending_room_payment=conn.execute("SELECT * FROM payment_records WHERE student_id=? AND payment_type='Room Booking' AND status != 'Paid' ORDER BY id DESC LIMIT 1", (student["id"],)).fetchone()
    occupied_count=(len(roommates)+1) if room else 0
    available_beds=max((room["capacity"] or 0)-occupied_count,0) if room else 0
    conn.close()
    return render_template("room.html",student=student,room=room,roommates=roommates,occupied_count=occupied_count,available_beds=available_beds,available_rooms=available_rooms,room_directory=room_directory,latest_booking=latest_booking,pending_room_payment=pending_room_payment)


@app.route("/room/payment/<payment_ref>")
def room_payment(payment_ref):
    if "student_id" not in session: return redirect(url_for("home"))
    conn=get_connection(); payment=conn.execute("SELECT * FROM payment_records WHERE payment_ref=? AND student_id=? AND payment_type='Room Booking'",(payment_ref,session["student_id"])).fetchone()
    student=conn.execute("SELECT * FROM students WHERE id=?",(session["student_id"],)).fetchone()
    conn.close()
    if not payment or not student: return redirect(url_for("room_details"))
    return render_template("room_payment.html", payment=payment, student=student)


@app.route("/room/receipt/<booking_id>")
def room_receipt(booking_id):
    if "student_id" not in session:
        return redirect(url_for("home"))
    conn = get_connection()
    booking = conn.execute(
        "SELECT * FROM room_bookings WHERE booking_ref = ? AND student_id = ?",
        (booking_id, session["student_id"])
    ).fetchone()
    room = conn.execute("SELECT * FROM rooms WHERE room_number = ?", (booking["room_number"],)).fetchone() if booking else None
    conn.close()
    if not booking:
        return redirect(url_for("room_details"))
    return render_template("room_receipt.html", booking=booking, room=room)


@app.route("/payment/submit/<payment_ref>", methods=["POST"])
def submit_payment(payment_ref):
    if "student_id" not in session: return redirect(url_for("home"))
    conn=get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        payment=conn.execute("SELECT * FROM payment_records WHERE payment_ref=? AND student_id=?",(payment_ref,session["student_id"])).fetchone()
        if not payment: conn.rollback(); conn.close(); return redirect(url_for("fees"))
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if payment["status"] != "Paid":
            conn.execute("UPDATE payment_records SET status='Paid', submitted_at=? WHERE id=?",(now,payment["id"]))
            # Every successfully submitted due is also entered into the formal fee ledger.
            exists=conn.execute("SELECT id FROM fees WHERE student_id=? AND paid_date=? AND amount=? AND status='Paid'",(session["student_id"],now[:10],payment["amount"])).fetchone()
            if not exists:
                conn.execute("INSERT INTO fees(student_id,amount,status,due_date,paid_date) VALUES(?,?,?,?,?)",(session["student_id"],payment["amount"],"Paid",now[:10],now[:10]))
        if payment["payment_type"] == "Room Booking":
            current=conn.execute("SELECT * FROM students WHERE id=?",(session["student_id"],)).fetchone()
            if current["room"]:
                conn.rollback(); conn.close(); flash(f"You already have Room {current['room']} allotted.","info"); return redirect(url_for("room_details"))
            room=conn.execute("SELECT * FROM rooms WHERE room_number=?",(payment["room_number"],)).fetchone()
            occupied=conn.execute("SELECT COUNT(*) AS count FROM students WHERE room=?",(payment["room_number"],)).fetchone()["count"]
            if not room or occupied >= (room["capacity"] or 0):
                conn.rollback(); conn.close(); flash("Payment was recorded, but the selected room is no longer available. Please contact hostel administration for reassignment.","error"); return redirect(url_for("fees"))
            nowdt=datetime.now(); booking_ref=f"BOOK-{nowdt.strftime('%Y%m%d%H%M%S%f')}-{current['id']:04d}"
            next_number=conn.execute("SELECT COUNT(*) FROM room_bookings").fetchone()[0]+1
            receipt_no=f"SAGE-ROOM-{nowdt.strftime('%Y%m%d')}-{current['id']:04d}-{next_number:03d}"
            conn.execute("UPDATE students SET room=? WHERE id=? AND (room IS NULL OR room='')",(payment["room_number"],current["id"]))
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                conn.rollback(); conn.close(); flash("Room allotment could not be completed. Please try again.","error"); return redirect(url_for("room_details"))
            conn.execute("""INSERT INTO room_bookings(booking_ref,student_id,room_number,name,enrollment,branch,year,phone,email,guardian_name,booking_date,status,receipt_no,payment_ref,booking_fee) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(booking_ref,current["id"],payment["room_number"],current["name"],current["enrollment"],current["branch"],current["year"],current["phone"],current["email"],current["guardian_name"],nowdt.strftime('%Y-%m-%d %H:%M:%S'),'Confirmed',receipt_no,payment["payment_ref"],500))
            conn.commit(); conn.close(); session["room"]=payment["room_number"]; return redirect(url_for("room_receipt",booking_id=booking_ref))
        conn.commit(); payment_id=payment["id"]; conn.close(); return redirect(url_for("payment_receipt",payment_id=payment_id))
    except sqlite3.Error:
        conn.rollback(); conn.close(); flash("The payment could not be recorded. Please try again.","error"); return redirect(url_for("fees"))


@app.route("/payment/receipt/<int:payment_id>")
def payment_receipt(payment_id):
    if "student_id" not in session:
        return redirect(url_for("home"))
    conn = get_connection()
    payment = conn.execute(
        """SELECT p.*, s.name, s.enrollment, s.branch, s.year, s.room, s.phone, s.email
         FROM payment_records p JOIN students s ON s.id = p.student_id
         WHERE p.id = ? AND p.student_id = ?""",
        (payment_id, session["student_id"])
    ).fetchone()
    conn.close()
    if not payment:
        return redirect(url_for("fees"))
    return render_template("payment_receipt.html", payment=payment)


@app.route("/admin/verify-payment/<int:payment_id>", methods=["POST"])
def verify_payment(payment_id):
    # Admin login is the normal access path. The legacy key is retained only
    # for compatibility with older locally saved links.
    if not session.get("admin") and request.form.get("key") != ADMIN_SESSION_KEY:
        return "Admin verification access denied.", 403
    conn = get_connection()
    conn.execute(
        "UPDATE payment_records SET status = 'Paid', verified_at = ? WHERE id = ?",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), payment_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_records", key=ADMIN_SESSION_KEY))


@app.route("/admin/records")
def admin_records():
    # Lightweight local verification page. Data is read directly from SQLite.
    # A successful universal admin login is now the preferred access method.
    if not session.get("admin") and request.args.get("key") != ADMIN_SESSION_KEY:
        return "Admin verification access denied.", 403
    conn = get_connection()
    students = conn.execute(
        """SELECT id, enrollment, name, email, phone, room, created_at, last_login
           FROM students ORDER BY id DESC"""
    ).fetchall()
    bookings = conn.execute("SELECT * FROM room_bookings ORDER BY id DESC").fetchall()
    payments = conn.execute("""SELECT p.*, s.name, s.enrollment FROM payment_records p
                              JOIN students s ON s.id = p.student_id ORDER BY p.id DESC""").fetchall()
    conn.close()
    return render_template("admin_records.html", students=students, bookings=bookings, payments=payments)


@app.route("/profile")
def profile():
    if "student_id" not in session:
        return redirect(url_for("home"))

    conn = get_connection()

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (session["student_id"],)
    ).fetchone()

    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("home"))

    room_details = conn.execute(
        "SELECT * FROM rooms WHERE room_number = ?",
        (student["room"],)
    ).fetchone()

    attendance_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_days,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_days
        FROM attendance
        WHERE student_id = ?
        """,
        (student["id"],)
    ).fetchone()

    fee = conn.execute(
        """
        SELECT amount, status, due_date, paid_date
        FROM fees
        WHERE student_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (student["id"],)
    ).fetchone()

    complaint_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM complaints
        WHERE student_id = ? AND status != 'Resolved'
        """,
        (student["id"],)
    ).fetchone()["count"]

    conn.close()

    total_days = attendance_row["total_days"] or 0
    present_days = attendance_row["present_days"] or 0
    attendance_percentage = round((present_days / total_days) * 100) if total_days else 0

    return render_template(
        "profile.html",
        student=student,
        room_details=room_details,
        attendance=attendance_percentage,
        attendance_present=present_days,
        attendance_total=total_days,
        fee=fee,
        complaint_count=complaint_count,
    )


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    if "student_id" not in session:
        return redirect(url_for("home"))
    conn = get_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()
    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("home"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        guardian_name = request.form.get("guardian_name", "").strip()
        guardian_phone = request.form.get("guardian_phone", "").strip()
        branch = request.form.get("branch", "").strip()
        year = request.form.get("year", "").strip()
        if len(name) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            conn.close(); return render_template("profile_edit.html", student=student, error="Please enter a valid name and email address.")
        digits = re.sub(r"\D", "", phone)
        if not 7 <= len(digits) <= 15:
            conn.close(); return render_template("profile_edit.html", student=student, error="Please enter a valid mobile number.")
        duplicate = conn.execute("SELECT id FROM students WHERE LOWER(email)=? AND id != ?", (email, student["id"])).fetchone()
        if duplicate:
            conn.close(); return render_template("profile_edit.html", student=student, error="That email address is already registered to another student.")
        conn.execute("""UPDATE students SET name=?, email=?, phone=?, guardian_name=?, guardian_phone=?, branch=?, year=? WHERE id=?""",
                     (name, email, phone, guardian_name, guardian_phone, branch, year, student["id"]))
        conn.commit(); conn.close()
        session["student"] = name; session["branch"] = branch; session["year"] = year
        flash("Your student and contact details were updated successfully.", "info")
        return redirect(url_for("profile"))
    conn.close()
    return render_template("profile_edit.html", student=student)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
