from flask import Flask, request, render_template, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import csv

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ------------------- Database Connection -------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",  # change if needed
        password="harshi@123",  # your MySQL password
        database="farmer_rental"
    )

# ------------------- Home Page -------------------
@app.route('/')
def index():
    return render_template('index.html')

# ------------------- User Registration -------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed_password)
            )
            conn.commit()
            flash("Account created successfully! Please login.", "success")
            return redirect(url_for('user_login'))
        except mysql.connector.IntegrityError:
            flash("Email already exists. Try another.", "danger")
        finally:
            conn.close()
    return render_template('register.html')

# ------------------- User Login -------------------
@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = user['name']
            session['user_id'] = user['id']
            flash("Logged in successfully!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid email or password", "danger")
    return render_template('user_login.html')

# ------------------- Show Equipment (from CSV dataset) -------------------
@app.route('/home')
def home():
    query = request.args.get('search', '').strip().lower()
    sort = request.args.get('sort', 'name')

    equipment_list = []
    # Load equipment data from CSV
    with open('equipment_dataset.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            equipment_list.append({
                'id': row['id'],
                'name': row['name'],
                'category': row['category'],
                'price': int(row['price']),
                'image_url': row['image_url']
            })

    # Filter by search term
    if query:
        equipment_list = [e for e in equipment_list if query in e['name'].lower()]

    # Sort
    if sort == 'price':
        equipment_list.sort(key=lambda x: x['price'])
    else:
        equipment_list.sort(key=lambda x: x['name'].lower())

    return render_template('equipment.html', equipment_list=equipment_list, search=query, sort=sort)

# ------------------- Book Equipment -------------------
# ------------------- Book Equipment -------------------
@app.route('/book/<int:equipment_id>', methods=['POST'])
def book(equipment_id):
    if 'user' not in session or 'user_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('user_login'))

    duration = int(request.form['duration'])

    # Load equipment info from CSV
    equipment = None
    with open('equipment_dataset.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if int(row['id']) == equipment_id:
                equipment = row
                break

    if not equipment:
        return "Equipment not found", 404

    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=duration)
    total = int(equipment['price']) * duration
    username = session['user']

    booking_id = f"BKG{int(datetime.now().timestamp())}"

    # Save booking details to bookings.csv (for admin review)
    with open('bookings.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([
            booking_id,
            equipment['id'],
            equipment['name'],
            username,
            start_date,
            end_date,
            duration,
            total,
            'Pending'
        ])

    # store booking info in session
    session['last_booking'] = {
        "id": booking_id,
        "username": username,
        "name": equipment['name'],
        "duration": duration,
        "price": int(equipment['price']),
        "total": total,
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    # redirect to payment page
    return redirect(url_for('payment'))


# ------------------- Payment Page -------------------
# ------------------- Payment Page -------------------
@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'last_booking' not in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        method = request.form['method']
        session['payment_method'] = method

        booking = session['last_booking']

        # After payment, mark status as Paid in CSV
        rows = []
        with open('bookings.csv', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            rows = list(reader)

        for row in rows:
            if row and row[0] == booking["id"]:
                row[-1] = "Paid"
                break

        with open('bookings.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rows)

        # Render success popup
        return render_template('success.html', booking=booking)

    return render_template('payment.html', booking=session['last_booking'])


# ------------------- Receipt Page -------------------
@app.route('/receipt')
def receipt():
    if 'last_booking' not in session:
        return redirect(url_for('home'))

    booking = session['last_booking']
    payment_method = session.get('payment_method', 'Not Selected')

    return render_template('receipt.html', booking=booking, payment_method=payment_method)

# ------------------- Admin Login -------------------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin123':
            session['admin'] = username
            return redirect(url_for('view_bookings'))
        else:
            flash("Invalid admin credentials", "danger")
    return render_template('admin_login.html')

# ------------------- View All Bookings -------------------
@app.route('/view_bookings')
def view_bookings():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            b.id AS booking_id, 
            e.name AS equipment_name, 
            u.name AS renter_name, 
            b.start_date, 
            b.end_date, 
            b.status
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.renter_id = u.id
        ORDER BY b.start_date DESC
    """)
    bookings = cursor.fetchall()
    conn.close()

    return render_template('admin.html', bookings=bookings)

# ------------------- Logout -------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for('index'))

# ------------------- Run App -------------------
if __name__ == '__main__':
    app.run(debug=True)
