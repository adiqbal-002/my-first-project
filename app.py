from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "finance.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_error: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            fname TEXT NOT NULL,
            class_year TEXT NOT NULL,
            faculty TEXT NOT NULL,
            gender TEXT NOT NULL,
            contact_number TEXT NOT NULL,
            guardian_contact_number TEXT NOT NULL,
            address TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER UNIQUE NOT NULL,
            registration_fee REAL NOT NULL DEFAULT 0,
            college_fee REAL NOT NULL DEFAULT 0,
            exam_fee REAL NOT NULL DEFAULT 0,
            hostel_fee REAL NOT NULL DEFAULT 0,
            promotion_fee REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_mode TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            notes TEXT,
            receipt_no TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS hostel_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            fname TEXT NOT NULL,
            address TEXT NOT NULL,
            contact_number TEXT NOT NULL,
            guardian_contact_number TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostel_student_id INTEGER NOT NULL,
            invoice_no TEXT NOT NULL UNIQUE,
            invoice_date TEXT NOT NULL,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            month_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(hostel_student_id) REFERENCES hostel_students(id) ON DELETE CASCADE
        );
        """
    )
    db.commit()
    db.close()


def to_float(value: str) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def month_name(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B")


def get_students_with_fee(filters: dict[str, str] | None = None) -> list[sqlite3.Row]:
    db = get_db()
    query = (
        """
        SELECT s.*, f.registration_fee, f.college_fee, f.exam_fee, f.hostel_fee, f.promotion_fee,
               COALESCE(f.registration_fee,0)+COALESCE(f.college_fee,0)+COALESCE(f.exam_fee,0)+COALESCE(f.hostel_fee,0)+COALESCE(f.promotion_fee,0) AS assigned_total,
               COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.student_id=s.id),0) AS paid_total
        FROM students s
        LEFT JOIN fees f ON s.id=f.student_id
        WHERE 1=1
        """
    )
    params: list[Any] = []
    if filters:
        if filters.get("name"):
            query += " AND s.name LIKE ?"
            params.append(f"%{filters['name']}%")
        if filters.get("fname"):
            query += " AND s.fname LIKE ?"
            params.append(f"%{filters['fname']}%")
        if filters.get("class_year"):
            query += " AND s.class_year = ?"
            params.append(filters["class_year"])
        if filters.get("faculty"):
            query += " AND s.faculty = ?"
            params.append(filters["faculty"])
    query += " ORDER BY s.id DESC"
    return db.execute(query, params).fetchall()


@app.route("/")
def dashboard() -> str:
    db = get_db()
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "hostel_students": db.execute("SELECT COUNT(*) FROM hostel_students").fetchone()[0],
        "collected": db.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0],
        "invoices": db.execute("SELECT COALESCE(SUM(price),0) FROM invoices").fetchone()[0],
    }
    return render_template("dashboard.html", stats=stats)


@app.route("/students", methods=["GET", "POST"])
def students() -> str:
    db = get_db()
    if request.method == "POST":
        data = [request.form[k] for k in ["name", "fname", "class_year", "faculty", "gender", "contact_number", "guardian_contact_number", "address"]]
        db.execute(
            """
            INSERT INTO students(name, fname, class_year, faculty, gender, contact_number, guardian_contact_number, address)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            data,
        )
        db.commit()
        flash("Student registered successfully.")
        return redirect(url_for("students"))

    filters = {
        "name": request.args.get("name", "").strip(),
        "fname": request.args.get("fname", "").strip(),
        "class_year": request.args.get("class_year", "").strip(),
        "faculty": request.args.get("faculty", "").strip(),
    }
    return render_template("students.html", students=get_students_with_fee(filters), filters=filters)


@app.route("/students/<int:student_id>/update", methods=["POST"])
def update_student(student_id: int):
    db = get_db()
    db.execute(
        """
        UPDATE students
        SET name=?, fname=?, class_year=?, faculty=?, gender=?, contact_number=?, guardian_contact_number=?, address=?
        WHERE id=?
        """,
        [
            request.form["name"],
            request.form["fname"],
            request.form["class_year"],
            request.form["faculty"],
            request.form["gender"],
            request.form["contact_number"],
            request.form["guardian_contact_number"],
            request.form["address"],
            student_id,
        ],
    )
    db.commit()
    flash("Student updated.")
    return redirect(url_for("students"))


@app.route("/students/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id: int):
    db = get_db()
    db.execute("DELETE FROM students WHERE id=?", (student_id,))
    db.commit()
    flash("Student deleted.")
    return redirect(url_for("students"))


@app.route("/fees/assign/<int:student_id>", methods=["GET", "POST"])
def assign_fee(student_id: int):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        flash("Student not found.")
        return redirect(url_for("students"))

    if request.method == "POST":
        values = [
            to_float(request.form.get("registration_fee", "0")),
            to_float(request.form.get("college_fee", "0")),
            to_float(request.form.get("exam_fee", "0")),
            to_float(request.form.get("hostel_fee", "0")),
            to_float(request.form.get("promotion_fee", "0")),
        ]
        db.execute(
            """
            INSERT INTO fees(student_id, registration_fee, college_fee, exam_fee, hostel_fee, promotion_fee, updated_at)
            VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(student_id) DO UPDATE SET
                registration_fee=excluded.registration_fee,
                college_fee=excluded.college_fee,
                exam_fee=excluded.exam_fee,
                hostel_fee=excluded.hostel_fee,
                promotion_fee=excluded.promotion_fee,
                updated_at=CURRENT_TIMESTAMP
            """,
            [student_id, *values],
        )
        db.commit()
        flash("Fee assigned/updated successfully.")
        return redirect(url_for("students"))

    fee = db.execute("SELECT * FROM fees WHERE student_id=?", (student_id,)).fetchone()
    return render_template("assign_fee.html", student=student, fee=fee)


@app.route("/fees/collect", methods=["GET", "POST"])
def collect_fee():
    db = get_db()
    if request.method == "POST":
        student_id = int(request.form["student_id"])
        amount = to_float(request.form["amount"])
        receipt_no = f"RCPT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db.execute(
            """
            INSERT INTO payments(student_id, amount, payment_mode, payment_date, notes, receipt_no)
            VALUES(?,?,?,?,?,?)
            """,
            (
                student_id,
                amount,
                request.form["payment_mode"],
                request.form["payment_date"],
                request.form.get("notes", ""),
                receipt_no,
            ),
        )
        db.commit()
        payment_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        flash("Fee collected successfully.")
        return redirect(url_for("receipt", payment_id=payment_id))

    students_data = get_students_with_fee()
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("collect_fee.html", students=students_data, today=today)


@app.route("/receipts/<int:payment_id>")
def receipt(payment_id: int):
    db = get_db()
    payment = db.execute(
        """
        SELECT p.*, s.name, s.fname, s.class_year, s.faculty
        FROM payments p JOIN students s ON p.student_id=s.id
        WHERE p.id=?
        """,
        (payment_id,),
    ).fetchone()
    return render_template("receipt.html", payment=payment)


@app.route("/reports/student/<int:student_id>")
def student_report(student_id: int):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    payments = db.execute("SELECT * FROM payments WHERE student_id=? ORDER BY id DESC", (student_id,)).fetchall()
    assigned = db.execute(
        "SELECT COALESCE(registration_fee,0)+COALESCE(college_fee,0)+COALESCE(exam_fee,0)+COALESCE(hostel_fee,0)+COALESCE(promotion_fee,0) FROM fees WHERE student_id=?",
        (student_id,),
    ).fetchone()
    assigned_total = assigned[0] if assigned and assigned[0] is not None else 0
    paid_total = sum(p["amount"] for p in payments)
    return render_template("student_report.html", student=student, payments=payments, assigned_total=assigned_total, paid_total=paid_total)


@app.route("/reports/summary")
def summary_report():
    db = get_db()
    by_class = db.execute(
        """
        SELECT class_year, COUNT(*) AS total_students,
            COALESCE(SUM((SELECT SUM(amount) FROM payments p WHERE p.student_id=s.id)),0) AS total_collected
        FROM students s
        GROUP BY class_year
        """
    ).fetchall()
    by_faculty = db.execute(
        """
        SELECT faculty, COUNT(*) AS total_students,
            COALESCE(SUM((SELECT SUM(amount) FROM payments p WHERE p.student_id=s.id)),0) AS total_collected
        FROM students s
        GROUP BY faculty
        """
    ).fetchall()
    return render_template("summary_report.html", by_class=by_class, by_faculty=by_faculty)


@app.route("/hostel/students", methods=["GET", "POST"])
def hostel_students():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO hostel_students(name, fname, address, contact_number, guardian_contact_number) VALUES(?,?,?,?,?)",
            [request.form[k] for k in ["name", "fname", "address", "contact_number", "guardian_contact_number"]],
        )
        db.commit()
        flash("Hostel student added.")
        return redirect(url_for("hostel_students"))

    students_rows = db.execute("SELECT * FROM hostel_students ORDER BY id DESC").fetchall()
    return render_template("hostel_students.html", students=students_rows)


@app.route("/invoices", methods=["GET", "POST"])
def invoices():
    db = get_db()
    if request.method == "POST":
        date = request.form["invoice_date"]
        db.execute(
            "INSERT INTO invoices(hostel_student_id, invoice_no, invoice_date, item_name, price, month_name) VALUES(?,?,?,?,?,?)",
            (
                int(request.form["hostel_student_id"]),
                request.form["invoice_no"],
                date,
                request.form["item_name"],
                to_float(request.form["price"]),
                month_name(date),
            ),
        )
        db.commit()
        flash("Invoice recorded.")
        return redirect(url_for("invoices"))

    hostel = db.execute("SELECT * FROM hostel_students ORDER BY name").fetchall()
    rows = db.execute(
        """
        SELECT i.*, h.name AS hostel_name FROM invoices i
        JOIN hostel_students h ON h.id=i.hostel_student_id
        ORDER BY i.id DESC
        """
    ).fetchall()
    next_no = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("invoices.html", invoices=rows, hostel=hostel, next_no=next_no, today=today)


@app.route("/invoices/<int:invoice_id>/update", methods=["POST"])
def update_invoice(invoice_id: int):
    db = get_db()
    date = request.form["invoice_date"]
    db.execute(
        """
        UPDATE invoices SET item_name=?, price=?, invoice_date=?, month_name=?
        WHERE id=?
        """,
        (request.form["item_name"], to_float(request.form["price"]), date, month_name(date), invoice_id),
    )
    db.commit()
    flash("Invoice updated.")
    return redirect(url_for("invoices"))


@app.route("/invoices/<int:invoice_id>/delete", methods=["POST"])
def delete_invoice(invoice_id: int):
    db = get_db()
    db.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    db.commit()
    flash("Invoice deleted.")
    return redirect(url_for("invoices"))


@app.route("/invoices/month/<month>")
def invoices_by_month(month: str):
    db = get_db()
    rows = db.execute(
        """
        SELECT i.*, h.name AS hostel_name FROM invoices i
        JOIN hostel_students h ON h.id=i.hostel_student_id
        WHERE i.month_name=?
        ORDER BY i.invoice_date DESC
        """,
        (month,),
    ).fetchall()
    total = sum(r["price"] for r in rows)
    return render_template("month_report.html", rows=rows, month=month, total=total)


@app.route("/cashbook")
def cashbook():
    db = get_db()
    assigned = db.execute(
        "SELECT COALESCE(SUM(registration_fee+college_fee+exam_fee+hostel_fee+promotion_fee),0) FROM fees"
    ).fetchone()[0]
    collected = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
    invoice_total = db.execute("SELECT COALESCE(SUM(price),0) FROM invoices").fetchone()[0]

    ledger = db.execute(
        """
        SELECT payment_date AS txn_date, 'Fee Collected' AS txn_type, receipt_no AS ref_no, amount AS credit, 0 AS debit
        FROM payments
        UNION ALL
        SELECT invoice_date AS txn_date, 'Hostel Invoice' AS txn_type, invoice_no AS ref_no, 0 AS credit, price AS debit
        FROM invoices
        ORDER BY txn_date DESC
        """
    ).fetchall()
    return render_template(
        "cashbook.html",
        assigned=assigned,
        collected=collected,
        invoice_total=invoice_total,
        balance=collected - invoice_total,
        ledger=ledger,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
