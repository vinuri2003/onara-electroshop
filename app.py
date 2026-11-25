import calendar
import os
from datetime import date, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "change_this_to_a_secure_random_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "products")
REPAIR_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "repairs")
os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)
os.makedirs(REPAIR_UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "electrical_shop_db",
    "port": 3306
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file_obj, target_dir):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        safe_name = secure_filename(file_obj.filename)
        unique_name = f"{int(datetime.now().timestamp())}_{safe_name}"
        file_obj.save(os.path.join(target_dir, unique_name))
        return unique_name
    return None


def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def ensure_schema_updates():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SHOW COLUMNS FROM products LIKE 'image_filename'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE products ADD COLUMN image_filename VARCHAR(255) NULL")

    cursor.execute("SHOW COLUMNS FROM repairs_and_feedback LIKE 'repair_photo'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE repairs_and_feedback ADD COLUMN repair_photo VARCHAR(255) NULL")

    conn.commit()
    cursor.close()
    conn.close()


def sync_product_images():
    """Automatically links image files in static/uploads/products/ to matching products."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, brand, image_filename FROM products")
    products = cursor.fetchall()

    available_files = [
        f for f in os.listdir(PRODUCT_UPLOAD_DIR)
        if allowed_file(f) and not f.lower().startswith("shop-banner")
    ]

    for prod in products:
        if not prod["image_filename"]:
            brand_l = prod["brand"].lower()
            name_words = [w.lower() for w in prod["name"].split() if len(w) > 2]
            best_file = None
            best_score = 0

            for fname in available_files:
                fname_l = fname.lower()
                name_hits = sum(1 for w in name_words if w in fname_l)
                if name_hits > 0:
                    score = name_hits + (1 if brand_l in fname_l else 0)
                    if score > best_score:
                        best_score = score
                        best_file = fname

            if best_file:
                cursor.execute(
                    "UPDATE products SET image_filename = %s WHERE id = %s",
                    (best_file, prod["id"])
                )

    conn.commit()
    cursor.close()
    conn.close()


def seed_initial_data():
    """Seeds sample data with mobile numbers as usernames only if users table is empty."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS cnt FROM users")
    if cursor.fetchone()["cnt"] == 0:
        pw_hash = generate_password_hash("123456")
        users_data = [
            ("0771000001", pw_hash, "admin", "System Admin", "0771000001", "admin@shop.com", "Shop HQ"),
            ("0771000002", pw_hash, "owner", "Shop Owner", "0771000002", "owner@shop.com", "Colombo"),
            ("0771000003", pw_hash, "worker", "Kamal (Technician)", "0771000003", "worker@shop.com", "Kandy"),
            ("0772345678", pw_hash, "customer", "John Perera", "0772345678", "john@mail.com", "45 Main St, Colombo")
        ]
        cursor.executemany("""
            INSERT INTO users (username, password_hash, role, full_name, phone, email, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, users_data)

        products_data = [
            ("Inverter Refrigerator 350L", "LG", "LG-REF-350", 185000.00, 24),
            ("Smart LED TV 55-inch", "Samsung", "SAM-TV-55", 210000.00, 12),
            ("Electric Kettle 1.7L", "Philips", "PH-KET-17", 14500.00, 6),
            ("Split Air Conditioner 12000BTU", "Innovex", "INV-AC-12", 165000.00, 36)
        ]
        cursor.executemany("""
            INSERT INTO products (name, brand, model_number, price, default_warranty_months)
            VALUES (%s, %s, %s, %s, %s)
        """, products_data)
        conn.commit()

        cursor.execute("SELECT id FROM users WHERE username = '0772345678'")
        john_id = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM users WHERE username = '0771000003'")
        worker_id = cursor.fetchone()["id"]
        cursor.execute("SELECT id, price, default_warranty_months FROM products LIMIT 1")
        prod = cursor.fetchone()

        p_date = date.today()
        w_expiry = add_months(p_date, prod["default_warranty_months"])
        cursor.execute("""
            INSERT INTO purchases
            (customer_id, product_id, sold_by_user_id, serial_number, purchase_price, payment_method, purchase_date, warranty_months, warranty_expiry)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (john_id, prod["id"], worker_id, "SN-LG-99881", prod["price"], "Card", p_date, prod["default_warranty_months"], w_expiry))
        conn.commit()

    cursor.close()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                flash("You do not have permission to perform this action.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (mobile,))
        user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            flash("Invalid mobile number or password.", "danger")
            return render_template("login.html")

        stored_pw = user["password_hash"]
        if stored_pw.startswith(("scrypt:", "pbkdf2:")):
            password_ok = check_password_hash(stored_pw, password)
        else:
            password_ok = (stored_pw == password)

        if not password_ok:
            cursor.close()
            conn.close()
            flash("Invalid mobile number or password.", "danger")
            return render_template("login.html")

        if user["role"] == "customer":
            cursor.execute("SELECT COUNT(*) AS buy_count FROM purchases WHERE customer_id = %s", (user["id"],))
            if cursor.fetchone()["buy_count"] == 0:
                cursor.close()
                conn.close()
                flash("Access Denied: Only customers who have purchased items from our shop can log in.", "danger")
                return render_template("login.html")

        cursor.close()
        conn.close()

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["full_name"] = user["full_name"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session["role"]
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    current_user = cursor.fetchone()

    if role == "customer":
        cursor.execute("""
            SELECT p.*, pr.name AS product_name, pr.brand, pr.model_number, pr.image_filename,
                   CASE WHEN p.warranty_expiry >= CURDATE() THEN 'Active' ELSE 'Expired' END AS warranty_status
            FROM purchases p
            JOIN products pr ON p.product_id = pr.id
            WHERE p.customer_id = %s
            ORDER BY p.purchase_date DESC
        """, (user_id,))
        purchases = cursor.fetchall()

        cursor.execute("""
            SELECT r.*, p.serial_number, pr.name AS product_name, pr.brand
            FROM repairs_and_feedback r
            JOIN purchases p ON r.purchase_id = p.id
            JOIN products pr ON p.product_id = pr.id
            WHERE p.customer_id = %s
            ORDER BY r.created_at DESC
        """, (user_id,))
        repairs = cursor.fetchall()

        cursor.close()
        conn.close()
        return render_template("customer_dashboard.html", current_user=current_user, purchases=purchases, repairs=repairs)

    elif role == "worker":
        cursor.execute("""
            SELECT p.*, pr.name AS product_name, pr.brand, pr.model_number,
                   u.full_name AS customer_name, u.phone AS customer_phone,
                   CASE WHEN p.warranty_expiry >= CURDATE() THEN 'Active' ELSE 'Expired' END AS warranty_status
            FROM purchases p
            JOIN products pr ON p.product_id = pr.id
            JOIN users u ON p.customer_id = u.id
            ORDER BY p.purchase_date DESC, p.id DESC
        """)
        purchases = cursor.fetchall()

        cursor.execute("""
            SELECT r.*, p.serial_number, pr.name AS product_name, u.full_name AS customer_name, u.phone AS customer_phone
            FROM repairs_and_feedback r
            JOIN purchases p ON r.purchase_id = p.id
            JOIN products pr ON p.product_id = pr.id
            JOIN users u ON p.customer_id = u.id
            ORDER BY r.created_at DESC
        """)
        repairs = cursor.fetchall()

        cursor.execute("SELECT * FROM users WHERE role = 'customer' ORDER BY full_name")
        customers = cursor.fetchall()

        cursor.execute("SELECT * FROM products ORDER BY name")
        products = cursor.fetchall()

        cursor.close()
        conn.close()
        return render_template(
            "worker_dashboard.html",
            current_user=current_user,
            purchases=purchases,
            repairs=repairs,
            customers=customers,
            products=products
        )

    elif role == "owner":
        cursor.execute("""
            SELECT COUNT(*) AS total_orders,
                   COALESCE(SUM(purchase_price), 0) AS total_revenue,
                   COALESCE(SUM(CASE WHEN warranty_expiry >= CURDATE() THEN 1 ELSE 0 END), 0) AS active_warranties,
                   COALESCE(SUM(CASE WHEN warranty_expiry < CURDATE() THEN 1 ELSE 0 END), 0) AS expired_warranties
            FROM purchases
        """)
        sales_summary = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS total_repairs,
                   COALESCE(SUM(CASE WHEN repair_status IN ('Pending', 'In Progress') THEN 1 ELSE 0 END), 0) AS open_repairs,
                   COALESCE(SUM(CASE WHEN repair_status IN ('Repaired', 'Delivered') THEN 1 ELSE 0 END), 0) AS completed_repairs,
                   ROUND(AVG(rating), 1) AS avg_rating
            FROM repairs_and_feedback
        """)
        repair_summary = cursor.fetchone()

        cursor.execute("""
            SELECT payment_method, COUNT(*) AS order_count, COALESCE(SUM(purchase_price), 0) AS method_total
            FROM purchases
            GROUP BY payment_method
            ORDER BY method_total DESC
        """)
        payment_breakdown = cursor.fetchall()

        cursor.execute("""
            SELECT u.id, u.full_name, u.username, u.phone,
                   COUNT(p.id) AS total_sales,
                   COALESCE(SUM(p.purchase_price), 0) AS total_revenue,
                   COALESCE(AVG(p.purchase_price), 0) AS avg_sale,
                   MAX(p.purchase_date) AS last_sale_date
            FROM users u
            LEFT JOIN purchases p ON u.id = p.sold_by_user_id
            WHERE u.role = 'worker'
            GROUP BY u.id, u.full_name, u.username, u.phone
            ORDER BY total_revenue DESC
        """)
        worker_performance = cursor.fetchall()

        cursor.execute("""
            SELECT r.*, pr.name AS product_name, u.full_name AS customer_name
            FROM repairs_and_feedback r
            JOIN purchases p ON r.purchase_id = p.id
            JOIN products pr ON p.product_id = pr.id
            JOIN users u ON p.customer_id = u.id
            WHERE r.customer_feedback IS NOT NULL
            ORDER BY r.created_at DESC
            LIMIT 10
        """)
        recent_feedbacks = cursor.fetchall()

        cursor.close()
        conn.close()
        return render_template(
            "owner_dashboard.html",
            current_user=current_user,
            sales_summary=sales_summary,
            repair_summary=repair_summary,
            payment_breakdown=payment_breakdown,
            worker_performance=worker_performance,
            recent_feedbacks=recent_feedbacks
        )

    elif role == "admin":
        cursor.execute("SELECT * FROM users ORDER BY FIELD(role, 'admin', 'owner', 'worker', 'customer'), created_at DESC")
        all_users = cursor.fetchall()

        cursor.execute("SELECT * FROM products ORDER BY id DESC")
        products = cursor.fetchall()

        cursor.execute("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
        role_counts = {row["role"]: row["cnt"] for row in cursor.fetchall()}

        cursor.close()
        conn.close()
        return render_template(
            "admin_dashboard.html",
            current_user=current_user,
            all_users=all_users,
            products=products,
            role_counts=role_counts
        )

    cursor.close()
    conn.close()
    flash("Unknown user role.", "danger")
    return redirect(url_for("logout"))


@app.route("/invoice/<int:purchase_id>")
@login_required
def view_invoice(purchase_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, pr.name AS product_name, pr.brand, pr.model_number, pr.image_filename,
               c.full_name AS customer_name, c.phone AS customer_phone,
               c.email AS customer_email, c.address AS customer_address,
               s.full_name AS sold_by_name,
               CASE WHEN p.warranty_expiry >= CURDATE() THEN 'Active' ELSE 'Expired' END AS warranty_status
        FROM purchases p
        JOIN products pr ON p.product_id = pr.id
        JOIN users c ON p.customer_id = c.id
        JOIN users s ON p.sold_by_user_id = s.id
        WHERE p.id = %s
    """, (purchase_id,))
    invoice = cursor.fetchone()
    cursor.close()
    conn.close()

    if not invoice:
        flash("Invoice not found.", "danger")
        return redirect(url_for("dashboard"))

    if session["role"] == "customer" and invoice["customer_id"] != session["user_id"]:
        flash("You are not authorized to view this invoice.", "danger")
        return redirect(url_for("dashboard"))

    return render_template("invoice.html", invoice=invoice)


@app.route("/add_sale", methods=["POST"])
@login_required
@roles_required("worker", "admin", "owner")
def add_sale():
    customer_mode = request.form.get("customer_mode")
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        if customer_mode == "new":
            phone = request.form["new_phone"].strip()
            username = phone
            password = request.form["new_password"]
            full_name = request.form["new_full_name"].strip()
            email = request.form["new_email"].strip()
            address = request.form["new_address"].strip()

            if not phone or not password or not full_name:
                flash("Mobile number, password, and full name are required for a new customer.", "danger")
                cursor.close()
                conn.close()
                return redirect(url_for("dashboard"))

            pw_hash = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, full_name, phone, email, address)
                VALUES (%s, %s, 'customer', %s, %s, %s, %s)
            """, (username, pw_hash, full_name, phone, email, address))
            customer_id = cursor.lastrowid
        else:
            customer_id = int(request.form["existing_customer_id"])

        product_id = int(request.form["product_id"])
        serial_number = request.form["serial_number"].strip()
        purchase_price = float(request.form["purchase_price"])
        payment_method = request.form["payment_method"]
        warranty_months = int(request.form["warranty_months"])
        purchase_date = datetime.strptime(request.form["purchase_date"], "%Y-%m-%d").date()
        warranty_expiry = add_months(purchase_date, warranty_months)

        cursor.execute("""
            INSERT INTO purchases
            (customer_id, product_id, sold_by_user_id, serial_number, purchase_price, payment_method, purchase_date, warranty_months, warranty_expiry)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (customer_id, product_id, session["user_id"], serial_number, purchase_price, payment_method, purchase_date, warranty_months, warranty_expiry))

        new_purchase_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        flash("Sale recorded successfully! Customer can log in using their mobile number.", "success")
        return redirect(url_for("view_invoice", purchase_id=new_purchase_id))

    except mysql.connector.Error as err:
        conn.rollback()
        cursor.close()
        conn.close()
        flash(f"Error recording sale: {err}", "danger")
        return redirect(url_for("dashboard"))


@app.route("/add_product", methods=["POST"])
@login_required
@roles_required("worker", "admin", "owner")
def add_product():
    name = request.form["name"].strip()
    brand = request.form["brand"].strip()
    model_number = request.form["model_number"].strip()
    price = float(request.form["price"])
    warranty_months = int(request.form["default_warranty_months"])
    image_filename = save_uploaded_image(request.files.get("product_image"), PRODUCT_UPLOAD_DIR)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, brand, model_number, price, default_warranty_months, image_filename)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, brand, model_number, price, warranty_months, image_filename))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Product added successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/customer_request_repair", methods=["POST"])
@login_required
@roles_required("customer")
def customer_request_repair():
    purchase_id = int(request.form["purchase_id"])
    issue_description = request.form["issue_description"].strip()
    repair_photo = save_uploaded_image(request.files.get("repair_photo"), REPAIR_UPLOAD_DIR)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM purchases WHERE id = %s AND customer_id = %s", (purchase_id, session["user_id"]))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        flash("Invalid item selected for repair.", "danger")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        INSERT INTO repairs_and_feedback (purchase_id, issue_description, repair_status, repair_photo)
        VALUES (%s, %s, 'Pending', %s)
    """, (purchase_id, issue_description, repair_photo))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Repair request submitted! Our technician will review it shortly.", "success")
    return redirect(url_for("dashboard"))


@app.route("/update_repair/<int:repair_id>", methods=["POST"])
@login_required
@roles_required("worker", "admin", "owner")
def update_repair(repair_id):
    repair_status = request.form["repair_status"]
    technician_notes = request.form["technician_notes"].strip()
    repaired_date = date.today() if repair_status in ("Repaired", "Delivered") else None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE repairs_and_feedback
        SET repair_status = %s, technician_notes = %s,
            repaired_date = COALESCE(%s, repaired_date)
        WHERE id = %s
    """, (repair_status, technician_notes, repaired_date, repair_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Repair ticket updated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/submit_feedback/<int:repair_id>", methods=["POST"])
@login_required
@roles_required("customer")
def submit_feedback(repair_id):
    rating = int(request.form["rating"])
    feedback = request.form["customer_feedback"].strip()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.id, r.repair_status, p.customer_id
        FROM repairs_and_feedback r
        JOIN purchases p ON r.purchase_id = p.id
        WHERE r.id = %s
    """, (repair_id,))
    rec = cursor.fetchone()

    if not rec or rec["customer_id"] != session["user_id"]:
        flash("Unauthorized feedback request.", "danger")
    elif rec["repair_status"] not in ("Repaired", "Delivered"):
        flash("Feedback can only be submitted after the product is repaired.", "warning")
    else:
        cursor.execute("""
            UPDATE repairs_and_feedback
            SET customer_feedback = %s, rating = %s
            WHERE id = %s
        """, (feedback, rating, repair_id))
        conn.commit()
        flash("Thank you! Your repair feedback has been saved.", "success")

    cursor.close()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/admin/add_user", methods=["POST"])
@login_required
@roles_required("admin")
def admin_add_user():
    phone = request.form["phone"].strip()
    username = phone
    password = request.form["password"]
    role = request.form["role"]
    full_name = request.form["full_name"].strip()
    email = request.form["email"].strip()
    address = request.form["address"].strip()

    if role not in ("admin", "owner", "worker", "customer"):
        flash("Invalid role selected.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, full_name, phone, email, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, generate_password_hash(password), role, full_name, phone, email, address))
        conn.commit()
        flash(f"User '{full_name}' ({role}) added. Login Mobile: {phone}", "success")
    except mysql.connector.Error as err:
        flash(f"Error creating user (check if mobile number already exists): {err}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@login_required
@roles_required("admin")
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        flash("You cannot delete your own active admin account.", "warning")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("User account deleted.", "info")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    try:
        ensure_schema_updates()
        seed_initial_data()
        sync_product_images()
        print("Connected to XAMPP MySQL successfully!")
        app.run(debug=True)
    except mysql.connector.Error as err:
        print(f"Database Connection Error: {err}")
        print("Make sure XAMPP MySQL is started and 'electrical_shop_db' exists.")