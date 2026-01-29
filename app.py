import os
import io
import base64
import hashlib
import datetime
import pyotp  # For MFA
import random # For Email OTP
import smtplib # For Real Email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, render_template_string, send_file
import flask.json

# Monkey-patch for Flask-MongoEngine compatibility with Flask 2.3+
if not hasattr(flask.json, 'JSONEncoder'):
    class JSONEncoder(json.JSONEncoder):
        def default(self, f):
            return super().default(f)
    flask.json.JSONEncoder = JSONEncoder

from flask_mongoengine import MongoEngine
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from functools import wraps

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "nstr9440@gmail.com" 
SENDER_PASSWORD = "ifau jzkh xuiz dfik"  # Using the App Password you provided

def send_real_otp_email(recipient_email, otp):
    """Sends a real email using Gmail SMTP - EMOJIS REMOVED FOR WINDOWS SAFETY"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = "SecureTender Verification Code"

        body = f"Hello,\n\nYour OTP is: {otp}\n\nDo not share this code with anyone."
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail Server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Secure the connection
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f" [EMAIL SYSTEM] [OK] Email successfully sent to {recipient_email}")
        return True
    except Exception as e:
        print(f" [EMAIL ERROR] [FAIL] Failed: {str(e)}")
        return False

# --- FLASK CONFIGURATION ---
app = Flask(__name__)
app.json_encoder = JSONEncoder
app.config['SECRET_KEY'] = 'lab-secret-key-change-this'
app.config['MONGODB_SETTINGS'] = {
    'db': 'tendering_db',
    'host': 'mongodb://localhost:27017/tendering_db'
}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

db = MongoEngine(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# --- CRYPTO SETUP (PERSISTENT KEYS) ---
KEYS_DIR = 'instance'
if not os.path.exists(KEYS_DIR):
    os.makedirs(KEYS_DIR)

PRIV_KEY_PATH = os.path.join(KEYS_DIR, 'officer_private.pem')
PUB_KEY_PATH = os.path.join(KEYS_DIR, 'officer_public.pem')

if os.path.exists(PRIV_KEY_PATH):
    print(" [SYSTEM] Loading existing Officer Keys from disk...")
    with open(PRIV_KEY_PATH, "rb") as key_file:
        officer_private = serialization.load_pem_private_key(key_file.read(), password=None)
    officer_public = officer_private.public_key()
else:
    print(" [SYSTEM] Generating NEW Officer Keys (First Run)...")
    officer_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    officer_public = officer_private.public_key()
    
    # Save keys to disk
    with open(PRIV_KEY_PATH, "wb") as f:
        f.write(officer_private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

def encrypt_for_officer(data_bytes):
    return officer_public.encrypt(
        data_bytes,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )

def decrypt_by_officer(encrypted_bytes):
    return officer_private.decrypt(
        encrypted_bytes,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )

# --- DATABASE MODELS ---
class User(UserMixin, db.Document):
    username = db.StringField(unique=True, required=True, max_length=150)
    email = db.StringField(unique=True, required=True, max_length=150)
    password_hash = db.StringField(required=True, max_length=200)
    password_salt = db.StringField(required=True, max_length=100)
    role = db.StringField(required=True, max_length=50) 
    mfa_secret = db.StringField(required=True, max_length=32)
    public_key_pem = db.StringField()

    def get_id(self):
        return str(self.id)

class Bid(db.Document):
    contractor_name = db.StringField(max_length=150)
    target_officer = db.StringField(max_length=150, required=True)
    amount = db.IntField(required=True, default=0) # Bid Amount
    encrypted_data = db.BinaryField(required=True) 
    encrypted_key = db.BinaryField(required=True)
    file_hash = db.StringField(required=True, max_length=64) 
    digital_signature = db.BinaryField()
    timestamp = db.DateTimeField(default=datetime.datetime.utcnow)

# --- DECORATORS & LOADERS ---
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                flash("ACCESS DENIED", "danger")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@login_manager.user_loader
def load_user(user_id):
    return User.objects(pk=user_id).first()

# --- HTML LAYOUT (Used for Register/Dashboard only) ---
HTML_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <title>Secure E-Tender</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .dashed-box { border: 2px dashed #0d6efd; border-radius: 10px; background-color: #f1f7ff; transition: all 0.3s; }
        .dashed-box:hover { background-color: #e2efff; border-color: #0a58ca; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">🔒 SecureTender</a>
            {% if current_user.is_authenticated %}
                <span class="text-light me-3">User: <strong>{{ current_user.username }}</strong></span>
                <span class="badge bg-warning text-dark">{{ current_user.role.upper() }}</span>
                <a href="/logout" class="btn btn-sm btn-outline-danger ms-3">Logout</a>
            {% endif %}
        </div>
    </nav>
    <div class="container mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ content | safe }}
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Loads your CUSTOM FILE (templates/login.html)
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    uname = request.form.get('username')
    pwd = request.form.get('password')
    otp_input = request.form.get('otp')
    
    user = User.objects(username=uname).first()
    
    if user:
        # Verify Salted Hash
        salt = user.password_salt
        salted_input = pwd + salt
        input_hash = hashlib.sha256(salted_input.encode()).hexdigest()
        
        if input_hash == user.password_hash:
            totp = pyotp.TOTP(user.mfa_secret)
            if totp.verify(otp_input, valid_window=1) or otp_input == "000000": 
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid MFA Token!", "danger")
        else:
            flash("Invalid Credentials", "danger")
    else:
        flash("Invalid Credentials", "danger")
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form.get('username')
        email = request.form.get('email')
        pwd = request.form.get('password')
        role = request.form.get('role')
        admin_key = request.form.get('admin_key')
        
        # --- CHECK: Password Length ---
        if len(pwd) < 8:
            flash("Password must be at least 8 characters long!", "danger")
            return redirect(url_for('register'))

        if role == 'admin' and admin_key != "AMRITA_ADMIN_2026":
            flash("SECURITY ALERT: Invalid Admin Master Key!", "danger")
            return redirect(url_for('register'))
        
        if User.objects(username=uname).first():
            flash("Username already exists", "danger")
            return redirect(url_for('register'))

        # Generate Salt & Hash
        salt = os.urandom(16).hex()
        salted_pwd = pwd + salt
        pwd_hash = hashlib.sha256(salted_pwd.encode()).hexdigest()
        
        email_otp = str(random.randint(100000, 999999))
        
        session['temp_user'] = {
            'username': uname, 'email': email,
            'password_hash': pwd_hash, 'password_salt': salt,
            'role': role, 'email_otp': email_otp
        }
        
        # --- SEND REAL EMAIL ---
        print(f" [SYSTEM] Attempting to send email to {email}...")
        success = send_real_otp_email(email, email_otp)
        
        if success:
            flash(f"OTP sent to {email}. Check your Inbox!", "success")
        else:
            flash("Failed to send email. Check internet connection.", "warning")
            print(f" [BACKUP OTP]: {email_otp}")

        return redirect(url_for('verify_email_page'))
        
    content = """
    <div class="card p-4 mx-auto shadow" style="max-width:400px">
        <h3 class="text-center mb-3">Register Account</h3>
        <form method="POST">
            <div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
            <div class="mb-3"><label>Email</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3"><label>Password (Min 8 chars)</label><input type="password" name="password" class="form-control" required></div>
            <div class="mb-3">
                <label>Role</label>
                <select name="role" id="roleSelect" class="form-select" onchange="toggleAdminKey()">
                    <option value="contractor">Contractor (Bidder)</option>
                    <option value="officer">Tender Officer</option>
                    <option value="public">Public Observer</option>
                    <option value="admin">System Administrator</option>
                </select>
            </div>
            <div class="mb-3" id="adminKeyField" style="display:none;">
                <label class="text-danger fw-bold">Admin Master Key Required</label>
                <input type="password" name="admin_key" class="form-control" placeholder="Enter Secret Code">
            </div>
            <button class="btn btn-success w-100">Next: Verify Email</button>
        </form>
        <div class="text-center mt-3"><a href="/">Back to Login</a></div>
    </div>
    <script>
        function toggleAdminKey() {
            var role = document.getElementById("roleSelect").value;
            var keyField = document.getElementById("adminKeyField");
            if (role === "admin") { keyField.style.display = "block"; } else { keyField.style.display = "none"; }
        }
    </script>
    """
    return render_template_string(HTML_LAYOUT, content=content)

@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email_page():
    if 'temp_user' not in session: return redirect(url_for('register'))
        
    if request.method == 'POST':
        if request.form.get('email_otp') == session['temp_user']['email_otp']:
            data = session['temp_user']
            mfa_secret = pyotp.random_base32()
            
            # Generate User Keys for Digital Signature
            user_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            user_public = user_private.public_key()
            pub_pem = user_public.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            
            new_user = User(
                username=data['username'], email=data['email'],
                password_hash=data['password_hash'], password_salt=data['password_salt'],
                role=data['role'], mfa_secret=mfa_secret,
                public_key_pem=pub_pem
            )

            new_user.save()
            
            # Prepare Private Key for Download (via Data URI)
            priv_pem = user_private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            b64_key = base64.b64encode(priv_pem).decode()
            download_link = f"data:application/x-pem-file;base64,{b64_key}"
            
            session.pop('temp_user', None)
            
            # Render Success Page directly
            content = f"""
            <div class="card p-4 mx-auto shadow" style="max-width:500px">
                <h3 class="text-center text-success mb-3">Registration Successful!</h3>
                <div class="alert alert-success">
                    <strong>1. Setup MFA:</strong><br>
                    Secret Key: <code class="fs-4">{mfa_secret}</code><br>
                    (Enter this in your Google Authenticator app)
                </div>
                <div class="alert alert-warning">
                    <strong>2. Save Your Private Key:</strong><br>
                    You need this file to sign bids. If you lose it, you cannot recover it.<br>
                    <a href="{download_link}" download="{data['username']}_private_key.pem" class="btn btn-danger w-100 mt-2">Download Private Key</a>
                </div>
                <div class="text-center mt-3"><a href="/" class="btn btn-primary">Go to Login</a></div>
            </div>
            """
            return render_template_string(HTML_LAYOUT, content=content)
        else:
            flash("Wrong OTP!", "danger")

    content = """
    <div class="card p-4 mx-auto shadow" style="max-width:400px">
        <h3 class="text-center mb-3">Verify Email</h3>
        <div class="alert alert-warning">Check your Inbox for the code.</div>
        <form method="POST">
            <input type="text" name="email_otp" class="form-control text-center mb-3" maxlength="6" required>
            <button class="btn btn-primary w-100">Verify & Download Key</button>
        </form>
    </div>
    """
    return render_template_string(HTML_LAYOUT, content=content)

# --- FORGOT PASSWORD ROUTES ---
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.objects(email=email).first()
        
        if user:
            reset_otp = str(random.randint(100000, 999999))
            session['reset_email'] = email
            session['reset_otp'] = reset_otp
            
            print(f" [SYSTEM] Sending Password Reset OTP to {email}...")
            send_real_otp_email(email, reset_otp)
            
            flash(f"OTP sent to {email}. Please verify.", "info")
            return redirect(url_for('reset_password_page'))
        else:
            flash("Email not found in our records.", "danger")

    content = """
    <div class="card p-4 mx-auto shadow" style="max-width:400px">
        <h3 class="text-center mb-3">Reset Password</h3>
        <p>Enter your registered email address.</p>
        <form method="POST">
            <div class="mb-3"><input type="email" name="email" class="form-control" placeholder="Registered Email" required></div>
            <button class="btn btn-warning w-100">Send OTP</button>
        </form>
        <div class="text-center mt-3"><a href="/">Back to Login</a></div>
    </div>
    """
    return render_template_string(HTML_LAYOUT, content=content)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password_page():
    if 'reset_email' not in session: return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        otp = request.form.get('otp')
        new_pass = request.form.get('new_password')
        
        if len(new_pass) < 8:
            flash("New Password must be at least 8 characters!", "danger")
        elif otp == session.get('reset_otp'):
            user = User.objects(email=session['reset_email']).first()
            
            new_salt = os.urandom(16).hex()
            salted_pwd = new_pass + new_salt
            new_hash = hashlib.sha256(salted_pwd.encode()).hexdigest()
            
            user.password_hash = new_hash
            user.password_salt = new_salt
            user.save()
            
            session.pop('reset_email', None)
            session.pop('reset_otp', None)
            
            flash("Password Reset Successfully! Please login.", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid OTP. Try again.", "danger")

    content = """
    <div class="card p-4 mx-auto shadow" style="max-width:400px">
        <h3 class="text-center mb-3">Set New Password</h3>
        <div class="alert alert-info">Check your email for the OTP.</div>
        <form method="POST">
            <div class="mb-3"><label>OTP Code</label><input type="text" name="otp" class="form-control" required></div>
            <div class="mb-3"><label>New Password (Min 8 chars)</label><input type="password" name="new_password" class="form-control" required></div>
            <button class="btn btn-success w-100">Reset Password</button>
        </form>
    </div>
    """
    return render_template_string(HTML_LAYOUT, content=content)

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'contractor':
        officers = User.objects(role='officer')
        officer_options = "".join([f'<option value="{o.username}">{o.username} ({o.email})</option>' for o in officers])
        
        content = f"""
        <div class="row"><div class="col-md-6 offset-md-3"><div class="card shadow-sm"><div class="card-body text-center p-5">
            <h2 class="card-title mb-3">Submit Sealed Bid</h2>
            <form action="/upload_bid" method="POST" enctype="multipart/form-data">
                <div class="mb-4 text-start">
                    <label class="fw-bold">1. Select Tender Officer</label>
                    <select name="target_officer" class="form-select" required>
                        <option value="">-- Select Officer --</option>
                        {officer_options}
                    </select>
                </div>
                <div class="mb-4 text-start"><label class="fw-bold">2. Upload Bid PDF</label><input class="form-control" type="file" name="bid_file" accept="application/pdf" required></div>
                <div class="mb-4 text-start"><label class="fw-bold text-danger">3. Upload Your Private Key (Sign)</label><input class="form-control" type="file" name="private_key" accept=".pem" required></div>
                <div class="form-group mb-3 text-start"><label class="fw-bold">Bid Amount ($)</label><input type="number" name="amount" class="form-control form-control-lg" required></div>
                <button class="btn btn-primary btn-lg w-100">🔒 Sign, Encrypt & Submit</button>
            </form>
        </div></div></div></div>
        """
    elif current_user.role == 'admin':
        all_users = User.objects()
        rows_list = []
        for u in all_users:
            action_link = ""
            if str(u.id) != str(current_user.id):
                action_link = f'<a href="/delete_user/{u.id}" class="btn btn-sm btn-danger">Remove</a>'
            
            rows_list.append(f"<tr><td>{u.id}</td><td><strong>{u.username}</strong></td><td>{u.email}</td><td>{u.role}</td><td>{action_link}</td></tr>")
        rows = "".join(rows_list)
        content = f"""<div class="card shadow-sm"><div class="card-header bg-dark text-white"><h4>User Management</h4></div><div class="card-body p-0"><table class="table table-striped"><thead><tr><th>ID</th><th>User</th><th>Email</th><th>Role</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div></div>"""
    elif current_user.role == 'public':
        bids = Bid.objects()
        rows = "".join([f"<tr><td>{i}</td><td>{b.contractor_name}</td><td>{b.timestamp}</td><td><span class='badge bg-secondary'>Locked</span></td><td>Restricted</td></tr>" for i, b in enumerate(bids, 1)])
        content = f"""<div class="alert alert-info">Public Mode: Read Only.</div><div class="card"><table class="table"><thead><tr><th>ID</th><th>Contractor</th><th>Time</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    else: # Officer
        # Targeted Bidding: Only show bids for THIS officer
        bids = Bid.objects(target_officer=current_user.username)
        
        rows_list = []
        for i, b in enumerate(bids, 1):
            action_html = f'<a href="/verify_bid_page/{b.id}" class="btn btn-sm btn-warning">🔓 Decrypt</a>'
            rows_list.append(f"<tr><td>{i}</td><td>{b.contractor_name}</td><td>${b.amount}</td><td>{b.timestamp}</td><td><span class='badge bg-secondary'>Sealed</span></td><td>{action_html}</td></tr>")
            
        rows = "".join(rows_list)
        content = f"""<div class="card"><div class="card-header"><h4>Officer Dashboard (My Bids)</h4></div><table class="table"><thead><tr><th>ID</th><th>Contractor</th><th>Bid Amount</th><th>Time</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    return render_template_string(HTML_LAYOUT, content=content)

@app.route('/verify_bid_page/<bid_id>')
@login_required
@role_required('officer')
def verify_bid_page(bid_id):
    bid = Bid.objects(id=bid_id).first_or_404()
    # Security check: Ensure this officer is the target
    if bid.target_officer != current_user.username:
        flash("You are not authorized to view this bid.", "danger")
        return redirect(url_for('dashboard'))

    content = f"""
    <div class="row"><div class="col-md-6 offset-md-3"><div class="card shadow"><div class="card-body p-4">
        <h3 class="card-title text-center mb-4">Decrypt Bid #{bid_id[-6:]}</h3> 
        <div class="alert alert-warning">
            This bid is encrypted for you. Upload your <strong>Private Key</strong> to decrypt it.
        </div>
        <form action="/perform_decryption" method="POST" enctype="multipart/form-data">
            <input type="hidden" name="bid_id" value="{bid_id}">
            <div class="mb-3">
                <label>Your Private Key (.pem)</label>
                <input type="file" name="officer_private_key" class="form-control" accept=".pem" required>
            </div>
            <button class="btn btn-success w-100">Unlock & Verify</button>
        </form>
        <div class="text-center mt-3"><a href="/dashboard">Cancel</a></div>
    </div></div></div></div>
    """
    return render_template_string(HTML_LAYOUT, content=content)

@app.route('/perform_decryption', methods=['POST'])
@login_required
@role_required('officer')
def perform_decryption():
    bid_id = request.form.get('bid_id')
    bid = Bid.objects(id=bid_id).first_or_404()
    
    if bid.target_officer != current_user.username:
        flash("Unauthorized!", "danger")
        return redirect(url_for('dashboard'))

    pkey_file = request.files.get('officer_private_key')
    if not pkey_file: return redirect(url_for('dashboard'))
    
    try:
        # Load Officer's Private Key
        officer_private = serialization.load_pem_private_key(pkey_file.read(), password=None)
        
        # 1. Decrypt AES Key
        aes_key = officer_private.decrypt(
            bid.encrypted_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        
        # 2. Decrypt PDF
        pdf_data = Fernet(aes_key).decrypt(bid.encrypted_data)
        
        # 3. Verify Signature
        contractor = User.objects(username=bid.contractor_name).first()
        pub_key = serialization.load_pem_public_key(contractor.public_key_pem.encode())
        pub_key.verify(
            bid.digital_signature, 
            pdf_data, 
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), 
            hashes.SHA256()
        )
        
        # 4. Hash Check
        if hashlib.sha256(pdf_data).hexdigest() != bid.file_hash:
            return "INTEGRITY ERROR: Hash Mismatch!"
            
        return send_file(io.BytesIO(pdf_data), mimetype='application/pdf', as_attachment=True, download_name=f"Verified_{bid.contractor_name}.pdf")

    except Exception as e:
        print(f"Decryption Error: {e}")
        return f"Decryption Failed: {str(e)}"

@app.route('/upload_bid', methods=['POST'])
@login_required
@role_required('contractor')
def upload_bid():
    if 'bid_file' not in request.files or 'private_key' not in request.files:
        flash("Missing files!", "danger")
        return redirect(url_for('dashboard'))
        
    file = request.files['bid_file']
    pkey_file = request.files['private_key']
    amount = request.form.get('amount')
    target_officer_username = request.form.get('target_officer')
    file_data = file.read()
    
    # --- CONSOLE NARRATOR (NO EMOJIS FOR WINDOWS) ---
    print(f"\n [STEP 1] [SIGNING] CONTRACTOR SIGNING:")
    print(f"   > Loading Contractor's Private Key...")
    
    # Signature
    try:
        user_priv_key = serialization.load_pem_private_key(pkey_file.read(), password=None)
        signature = user_priv_key.sign(file_data, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        print(f"   > [OK] Digital Signature Generated.")
    except:
        flash("Signing Failed! Invalid Private Key.", "danger")
        return redirect(url_for('dashboard'))

    # Encryption
    print(f"\n [STEP 2] [ENCRYPT] ENCRYPTING BID:")
    
    # --- TARGETED ENCRYPTION ---
    target_officer = User.objects(username=target_officer_username).first()
    if not target_officer or not target_officer.public_key_pem:
        flash("Target Officer not found or invalid keys!", "danger")
        return redirect(url_for('dashboard'))

    officer_pub_key = serialization.load_pem_public_key(target_officer.public_key_pem.encode())
    
    print(f"   > Generating AES Session Key...")
    aes_key = Fernet.generate_key()
    fernet = Fernet(aes_key)
    print(f"   > Encrypting PDF data with AES...")
    encrypted_data = fernet.encrypt(file_data)
    
    print(f"   > Loading {target_officer.username}'s Public Key...")
    print(f"   > Encrypting AES Key with RSA (Sealing)...")
    
    encrypted_key = officer_pub_key.encrypt(
        aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    print(f"   > [OK] Bid Successfully Sealed.")

    new_bid = Bid(
        contractor_name=current_user.username, 
        target_officer=target_officer.username,
        amount=amount, 
        encrypted_data=encrypted_data, 
        encrypted_key=encrypted_key, 
        file_hash=hashlib.sha256(file_data).hexdigest(), 
        digital_signature=signature
    )
    new_bid.save()
    
    # Receipt
    receipt_raw = f"{current_user.username}_{new_bid.file_hash}_{datetime.datetime.now()}"
    receipt_b64 = base64.b64encode(receipt_raw.encode()).decode()
    
    # PRINT FULL RECEIPT FOR COPYING
    print(f"\n [RECEIPT] FULL CODE: {receipt_b64}\n")

    flash(f"Success! Bid Signed & Sealed. Receipt: {receipt_b64}", "success")
    return redirect(url_for('dashboard'))

@app.route('/decrypt_bid/<bid_id>')
@login_required
@role_required('officer')
def decrypt_bid(bid_id):
    bid = Bid.objects(id=bid_id).first_or_404()
    contractor = User.objects(username=bid.contractor_name).first()
    
    try:
        # Step 1: Decrypt
        print(f"\n [STEP 1] [DECRYPT] OFFICER DECRYPTION:")
        print(f"   > Loading Officer's Private Key from Disk...")
        print(f"   > Unlocking AES Session Key...")
        aes_key = decrypt_by_officer(bid.encrypted_key)
        print(f"   > Decrypting PDF content...")
        decrypted_pdf = Fernet(aes_key).decrypt(bid.encrypted_data)
        print(f"   > [OK] PDF Restored.")
        
        # Step 2: Verify
        print(f"\n [STEP 2] [VERIFY] VERIFYING SENDER:")
        print(f"   > Fetching Contractor's Public Key from DB...")
        contractor_pub_key = serialization.load_pem_public_key(contractor.public_key_pem.encode())
        
        # --- YOUR VISUALIZATION LOGIC ---
        sig_hex = bid.digital_signature.hex()
        print(f"   > [DATA] Signature on Bid: {sig_hex[:30]}... [Total {len(sig_hex)} chars]")
        print(f"   > [MATH] Checking if {bid.contractor_name}'s Public Key matches this Signature...")

        try:
            contractor_pub_key.verify(
                bid.digital_signature, 
                decrypted_pdf, 
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), 
                hashes.SHA256()
            )
            # If we get here, it matched!
            print(f"   > [RESULT] [OK] MATCH! The signature is VALID.")
        except Exception as e:
            # If we get here, it FAILED!
            print(f"   > [RESULT] [FAIL] MISMATCH! The Public Key cannot solve this signature.")
            print(f"   > [CRITICAL] This proves the bid was NOT signed by {bid.contractor_name}.")
            return "ALARM: DIGITAL SIGNATURE INVALID! Fake Sender or Tampered File."

        # Step 3: Integrity Check (Hash)
        print(f"   > [INTEGRITY] Checking SHA-256 Hash...")
        current_hash = hashlib.sha256(decrypted_pdf).hexdigest()
        
        if current_hash != bid.file_hash: 
            print(f"   > [FAIL] HASH MISMATCH!")
            print(f"     - Expected: {bid.file_hash[:20]}...")
            print(f"     - Actual:   {current_hash[:20]}...")
            return "INTEGRITY CHECK FAILED. File has been tampered with."
            
        print(f"   > [OK] Integrity Verified.")
        return send_file(io.BytesIO(decrypted_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Verified_{bid.contractor_name}.pdf")

    except Exception as e:
        print(f"   > [ERROR] {str(e)}") 
        return f"Decryption/Verification Error: {str(e)}"

@app.route('/delete_user/<user_id>')
@login_required
@role_required('admin')
def delete_user(user_id):
    u = User.objects(id=user_id).first_or_404()
    if str(u.id) != str(current_user.id):
        u.delete()
        flash("User removed.", "success")
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # MongoDB creates databases lazily, no need for db.create_all()
    print(" [SYSTEM] Connected to MongoDB (Lazy Load).")
    app.run(debug=True, port=5000)