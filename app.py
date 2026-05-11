from flask import Flask, render_template, request, redirect, session, send_from_directory, send_file
import sqlite3
import random
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from io import BytesIO
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'secret123'

def send_otp_email(to_email, otp):
    sender_email = "mechanotes31@gmail.com"
    app_password = "divjbkzcoiuvyguw"

    subject = "OTP Mecha Notes"
    body = f"""
    Halo!

    Kode OTP kamu untuk Mecha Notes:

    {otp}

    Jangan bagikan kode ini ke siapa pun.
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = "Mecha Notes <mechanotes31@gmail.com>"
    msg['To'] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print("Email terkirim")
    except Exception as e:
        print("Error kirim email:", e)

def add_watermark(input_pdf, username):
    packet = BytesIO()

    c = canvas.Canvas(packet)

    # ukuran halaman (A4 default)
    width, height = 595, 842  

    # transparansi
    c.setFillAlpha(0.15)

    # font besar
    c.setFont("Helvetica-Bold", 50)

    # rotate diagonal
    c.saveState()
    c.translate(width/2, height/2)
    c.rotate(45)

    # teks watermark
    text = f"MechaNotes"

    # posisikan di tengah
    c.drawCentredString(0, 0, text)

    c.restoreState()
    c.save()

    packet.seek(0)

    watermark = PdfReader(packet)
    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    for page in reader.pages:
        page.merge_page(watermark.pages[0])
        writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)

    return output

# ================= SETUP UPLOAD =================
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        expiry_date TEXT,
        status TEXT
    )
    ''')
    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        filename TEXT,
        category TEXT
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ================= HOME =================
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')

    search = request.args.get('search', '')
    category = request.args.get('category', 'Semua')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    query = "SELECT title, filename, category FROM files WHERE 1=1"
    params = []

    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")

    if category != "Semua":
        query += " AND category=?"
        params.append(category)

    c.execute(query, params)
    files = c.fetchall()

    # 🔥 BAGIAN YANG KAMU TANYA
    c.execute("SELECT expiry_date, status FROM users WHERE email=?", (session['user'],))
    user = c.fetchone()

    expired = True
    status = "inactive"

    if user:
        status = user[1]

        if user[0]:
            expiry = datetime.strptime(user[0], "%Y-%m-%d %H:%M:%S.%f")
            expired = expiry < datetime.now()

    conn.close()

    return render_template("index.html", files=files, expired=expired, status=status, search=search, role=session.get('role'))
# ================= REGISTER =================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['temp_email'] = email
        session['temp_password'] = password

        send_otp_email(email, otp)

        return redirect('/verify')

    return render_template('register.html')

# ================= VERIFY =================
@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        user_otp = request.form.get('otp')

        if user_otp == session.get('otp'):
            email = session.get('temp_email')
            password = session.get('temp_password')

            conn = sqlite3.connect('database.db')
            c = conn.cursor()

            # cek email
            c.execute("SELECT * FROM users WHERE email=?", (email,))
            if c.fetchone():
                return "Email sudah terdaftar"

            role = "user"
            if email == "mechanotes31@gmail.com":
                role = "admin"

            expiry = datetime.now()

            c.execute("INSERT INTO users (email, password, role, expiry_date, status) VALUES (?, ?, ?, ?, ?)",
                    (email, password, role, None, "inactive"))

            conn.commit()
            conn.close()

            session.clear()
            return redirect('/login')

        return "OTP salah"

    return render_template('verify.html')

# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute("SELECT email, password, role FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if user and user[1] == password:
            session['user'] = user[0]
            session['role'] = user[2]   # ✅ INI PENTING
            return redirect('/')
        else:
            return "Login gagal"

    return render_template('login.html')

# ================= SUBSCRIBE =================
@app.route('/subscribe')
def subscribe():
    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # ubah status jadi pending
    c.execute("UPDATE users SET status='pending' WHERE email=?",
              (session['user'],))

    conn.commit()
    conn.close()

    return render_template('subscribe.html')

@app.route('/pay')
def pay():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    expiry = datetime.now() + timedelta(days=30)

    c.execute("UPDATE users SET expiry_date=? WHERE email=?",
              (expiry, session['user']))

    conn.commit()
    conn.close()

    return redirect('/')

# ================= DASHBOARD ADMIN =================
@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # cek role
    c.execute("SELECT role FROM users WHERE email=?", (session['user'],))
    user = c.fetchone()

    if not user or user[0] != 'admin':
        return "Akses ditolak ❌"

    # 🔥 ambil semua file
    c.execute("SELECT id, title, filename, category FROM files")
    files = c.fetchall()

    # 🔥 ambil semua user + status
    c.execute("SELECT id, email, status FROM users")
    users = c.fetchall()

    conn.close()

    return render_template('admin.html', files=files, users=users)

# ================= UPLOAD ADMIN =================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute("SELECT role FROM users WHERE email=?", (session['user'],))
    user = c.fetchone()

    if user[0] != 'admin':
        return "Akses ditolak"

    if request.method == 'POST':
        title = request.form['title']
        category = request.form['category']
        file = request.files['file']

        filename = file.filename
        file.save(os.path.join('uploads', filename))

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute("INSERT INTO files (title, filename, category) VALUES (?, ?, ?)",
                  (title, filename, category))

        conn.commit()
        conn.close()

        return redirect('/')

    return render_template('upload.html')

# ================= DELETE =================
@app.route('/delete/<int:file_id>')
def delete(file_id):
    if session.get('role') != 'admin':
        return "Akses ditolak"

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # ambil nama file dulu
    c.execute("SELECT filename FROM files WHERE id=?", (file_id,))
    file = c.fetchone()

    if file:
        filepath = os.path.join('uploads', file[0])

        # hapus file dari folder
        if os.path.exists(filepath):
            os.remove(filepath)

        # hapus dari database
        c.execute("DELETE FROM files WHERE id=?", (file_id,))
        conn.commit()

    conn.close()

    return redirect('/admin')
# ================= FILE =================
@app.route('/file/<filename>')
def file(filename):
    if 'user' not in session:
        return redirect('/login')

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(filepath):
        return "File tidak ditemukan"

    user = session['user']

    watermarked_pdf = add_watermark(filepath, user)

    return send_file(
        watermarked_pdf,
        download_name=filename,
        mimetype='application/pdf'
    )

# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ================= PREVIEW =================
@app.route('/preview/<filename>')
def preview(filename):
    if 'user' not in session:
        return redirect('/login')

    return render_template('preview.html', filename=filename)

# ================= APPROVE USER =================
@app.route('/approve/<int:user_id>')
def approve(user_id):
    if 'user' not in session or session.get('role') != 'admin':
        return "Akses ditolak ❌"

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    expiry = datetime.now() + timedelta(days=30)

    c.execute("""
        UPDATE users 
        SET status='active', expiry_date=? 
        WHERE id=?
    """, (expiry, user_id))

    conn.commit()
    conn.close()

    return redirect('/admin')


# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)

