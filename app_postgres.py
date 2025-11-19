# (full file — copy into app_postgres.py)
import os
import json
import random
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

BASE_DIR = os.path.dirname(os.path.abspath(_file_))
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
ADS_DIR = os.path.join(BASE_DIR, 'static', 'ads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ADS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'mp4', 'webm'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(_name_, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SESSION_SECRET', 'yourempire-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['ADS_FOLDER'] = ADS_DIR

# DATABASE
DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///yourempire_local.db'
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionFactory = sessionmaker(bind=engine)
DBSession = scoped_session(SessionFactory)
Base = declarative_base()

# MODELS
class User(Base):
    _tablename_ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(512), nullable=False)
    referral_code = Column(String(20), unique=True, nullable=False)
    wallet = Column(Float, default=0.0)
    referred_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    joined_date = Column(DateTime, default=datetime.utcnow)
    referrals = relationship('User', remote_side=[id])

class Settings(Base):
    _tablename_ = 'settings'
    id = Column(Integer, primary_key=True)
    commission_percentage = Column(Float, default=50.0)
    min_withdrawal = Column(Float, default=225.0)
    admin_password = Column(String(512), nullable=False)
    ads_enabled = Column(Boolean, default=True)
    whatsapp_contact = Column(String(255), default='')
    email_contact = Column(String(255), default='')
    payment_methods = Column(Text, default='[]')

class Package(Base):
    _tablename_ = 'packages'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    price = Column(Float)

class Payment(Base):
    _tablename_ = 'payments'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    package_id = Column(Integer, ForeignKey('packages.id'), nullable=True)
    package_name = Column(String(255))
    amount = Column(Float)
    payment_method = Column(String(255))
    payment_account = Column(String(255))
    transaction_id = Column(String(255))
    screenshot = Column(String(255))
    status = Column(String(50), default='Pending')
    date = Column(DateTime, default=datetime.utcnow)

class Withdraw(Base):
    _tablename_ = 'withdraws'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    payment_method = Column(String(255))
    account_number = Column(String(255))
    account_name = Column(String(255))
    status = Column(String(50), default='Pending')
    date = Column(DateTime, default=datetime.utcnow)

class Ad(Base):
    _tablename_ = 'ads'
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    description = Column(Text)
    reward = Column(Float)
    type = Column(String(50))
    media_file = Column(String(255), nullable=True)
    link = Column(String(1024), nullable=True)
    created_date = Column(DateTime, default=datetime.utcnow)

class AdView(Base):
    _tablename_ = 'ad_views'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    ad_id = Column(Integer, ForeignKey('ads.id'))
    reward = Column(Float)
    date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# helpers
def generate_referral_code_db(db):
    while True:
        code = f"YE{random.randint(1000,9999)}"
        exists = db.query(User).filter_by(referral_code=code).first()
        if not exists:
            return code

def get_settings(db):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(admin_password=generate_password_hash('admin123'))
        db.add(settings)
        db.commit()
    return settings

def get_user_by_id_db(db, user_id):
    return db.query(User).filter_by(id=user_id).first()

def update_user_wallet_db(db, user_id, amount):
    user = get_user_by_id_db(db, user_id)
    if user:
        user.wallet = round((user.wallet or 0.0) + float(amount), 2)
        db.commit()

# decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ROUTES - keep same URLs and templates as original

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    db = DBSession()
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        ref_code = request.form.get('referral_code','').strip()

        if db.query(User).filter_by(email=email).first():
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))

        referred_by = None
        if ref_code:
            referrer = db.query(User).filter_by(referral_code=ref_code).first()
            if referrer:
                referred_by = referrer.id
            else:
                flash('Invalid referral code!', 'error')
                return redirect(url_for('register'))

        new_user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            referral_code=generate_referral_code_db(db),
            wallet=0.0,
            referred_by=referred_by,
            joined_date=datetime.utcnow()
        )
        db.add(new_user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            flash('Error creating user. Try again.', 'error')
            return redirect(url_for('register'))

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    ref_code = request.args.get('ref','')
    return render_template('register.html', ref_code=ref_code)

@app.route('/login', methods=['GET','POST'])
def login():
    db = DBSession()
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email == 'admin@yourempire.com':
            settings = get_settings(db)
            if check_password_hash(settings.admin_password, password):
                session['is_admin'] = True
                session['admin_email'] = email
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials!', 'error')
                return redirect(url_for('login'))

        user = db.query(User).filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password!', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def user_dashboard():
    db = DBSession()
    user = get_user_by_id_db(db, session['user_id'])
    packages = db.query(Package).all()
    payments = db.query(Payment).filter_by(user_id=user.id).all()
    withdrawals = db.query(Withdraw).filter_by(user_id=user.id).all()
    ad_views = db.query(AdView).filter_by(user_id=user.id).all()
    total_ad_earnings = sum(av.reward for av in ad_views)
    settings = get_settings(db)
    ads_enabled = settings.ads_enabled
    referrals = db.query(User).filter_by(referred_by=user.id).all()

    return render_template('user_dashboard.html',
                           user=user,
                           packages=packages,
                           payments=payments,
                           withdrawals=withdrawals,
                           ads_enabled=ads_enabled,
                           total_ad_earnings=total_ad_earnings,
                           referrals=referrals)

@app.route('/buy-package', methods=['GET','POST'])
@login_required
def buy_package():
    db = DBSession()
    if request.method == 'POST':
        package_id = int(request.form.get('package_id'))
        payment_method_id = int(request.form.get('payment_method'))
        transaction_id = request.form.get('transaction_id')

        package = db.query(Package).filter_by(id=package_id).first()
        settings = get_settings(db)
        payment_methods = json.loads(settings.payment_methods or '[]')
        payment_method = next((pm for pm in payment_methods if pm.get('id') == payment_method_id), None)

        if not package or not payment_method:
            flash('Invalid package or payment method!', 'error')
            return redirect(url_for('buy_package'))

        screenshot = None
        if 'screenshot' in request.files:
            file = request.files['screenshot']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{session['user_id']}{datetime.now().strftime('%Y%m%d%H%M%S')}{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                screenshot = filename

        new_payment = Payment(
            user_id=session['user_id'],
            package_id=package.id,
            package_name=package.name,
            amount=package.price,
            payment_method=payment_method.get('type'),
            payment_account=payment_method.get('account_number',''),
            transaction_id=transaction_id,
            screenshot=screenshot,
            status='Pending'
        )
        db.add(new_payment)
        db.commit()
        flash('Payment submitted successfully! Waiting for admin approval.', 'success')
        return redirect(url_for('user_dashboard'))

    packages = db.query(Package).all()
    settings = get_settings(db)
    payment_methods = json.loads(settings.payment_methods or '[]')
    return render_template('buy_package.html', packages=packages, payment_methods=payment_methods)

@app.route('/withdraw', methods=['GET','POST'])
@login_required
def withdraw():
    db = DBSession()
    user = get_user_by_id_db(db, session['user_id'])
    settings = get_settings(db)
    min_withdrawal = settings.min_withdrawal

    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        payment_method = request.form.get('payment_method')
        account_number = request.form.get('account_number')
        account_name = request.form.get('account_name')

        if amount < min_withdrawal:
            flash(f'Minimum withdrawal amount is {min_withdrawal} PKR!', 'error')
            return redirect(url_for('withdraw'))

        if amount > user.wallet:
            flash('Insufficient balance!', 'error')
            return redirect(url_for('withdraw'))

        new_withdraw = Withdraw(
            user_id=user.id,
            amount=amount,
            payment_method=payment_method,
            account_number=account_number,
            account_name=account_name,
            status='Pending'
        )
        db.add(new_withdraw)
        db.commit()
        flash('Withdrawal request submitted! Waiting for admin approval.', 'success')
        return redirect(url_for('user_dashboard'))

    return render_template('withdraw.html', user=user, min_withdrawal=min_withdrawal)

@app.route('/watch-ads')
@login_required
def watch_ads():
    db = DBSession()
    settings = get_settings(db)
    if not settings.ads_enabled:
        flash('Ad section is currently disabled.', 'info')
        return redirect(url_for('user_dashboard'))

    ads = db.query(Ad).all()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    user_today_views = db.query(AdView).filter(AdView.user_id==session['user_id']).all()
    viewed_ad_ids = [av.ad_id for av in user_today_views if av.date.strftime('%Y-%m-%d')==today]
    available_ads = [ad for ad in ads if ad.id not in viewed_ad_ids]
    user_ad_history = db.query(AdView).filter_by(user_id=session['user_id']).all()
    return render_template('watch_ads.html', ads=available_ads, ad_history=user_ad_history)

@app.route('/view-ad/<int:ad_id>')
@login_required
def view_ad(ad_id):
    db = DBSession()
    ad = db.query(Ad).filter_by(id=ad_id).first()
    if not ad:
        flash('Ad not found!', 'error')
        return redirect(url_for('watch_ads'))

    today = datetime.utcnow().strftime('%Y-%m-%d')
    already_viewed = False
    for av in db.query(AdView).filter_by(user_id=session['user_id'], ad_id=ad_id).all():
        if av.date.strftime('%Y-%m-%d') == today:
            already_viewed = True
            break

    if already_viewed:
        flash('You have already viewed this ad today!', 'info')
        return redirect(url_for('watch_ads'))

    new_view = AdView(user_id=session['user_id'], ad_id=ad.id, reward=ad.reward, date=datetime.utcnow())
    db.add(new_view)
    update_user_wallet_db(db, session['user_id'], ad.reward)
    db.commit()
    flash(f'You earned {ad.reward} PKR for viewing this ad!', 'success')
    return redirect(url_for('watch_ads'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = DBSession()
    users = db.query(User).all()
    payments = db.query(Payment).all()
    withdrawals = db.query(Withdraw).all()
    packages = db.query(Package).all()
    ads = db.query(Ad).all()
    ad_views = db.query(AdView).all()
    settings = get_settings(db)

    stats = {
        'total_users': len(users),
        'total_payments': len([p for p in payments if p.status == 'Approved']),
        'total_withdrawals': len([w for w in withdrawals if w.status == 'Approved']),
        'pending_payments': len([p for p in payments if p.status == 'Pending']),
        'pending_withdrawals': len([w for w in withdrawals if w.status == 'Pending']),
        'total_ad_views': len(ad_views),
        'total_ad_payouts': sum(av.reward for av in ad_views),
        'total_ads': len(ads)
    }
    return render_template('admin_dashboard.html', users=users, payments=payments, withdrawals=withdrawals, packages=packages, stats=stats, settings=settings)

@app.route('/admin/approve-payment/<int:payment_id>')
@admin_required
def approve_payment(payment_id):
    db = DBSession()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    if payment and payment.status == 'Pending':
        payment.status = 'Approved'
        settings = get_settings(db)
        commission_rate = settings.commission_percentage / 100.0
        buyer = db.query(User).filter_by(id=payment.user_id).first()
        if buyer and buyer.referred_by:
            commission = payment.amount * commission_rate
            update_user_wallet_db(db, buyer.referred_by, commission)
        db.commit()
        flash('Payment approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-payment/<int:payment_id>')
@admin_required
def reject_payment(payment_id):
    db = DBSession()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    if payment:
        payment.status = 'Rejected'
        db.commit()
        flash('Payment rejected!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve-withdrawal/<int:withdrawal_id>')
@admin_required
def approve_withdrawal(withdrawal_id):
    db = DBSession()
    withdrawal = db.query(Withdraw).filter_by(id=withdrawal_id).first()
    if withdrawal and withdrawal.status == 'Pending':
        user = db.query(User).filter_by(id=withdrawal.user_id).first()
        if user and user.wallet >= withdrawal.amount:
            withdrawal.status = 'Approved'
            update_user_wallet_db(db, withdrawal.user_id, -withdrawal.amount)
            db.commit()
            flash('Withdrawal approved and amount deducted from wallet!', 'success')
        else:
            flash('User has insufficient balance!', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-withdrawal/<int:withdrawal_id>')
@admin_required
def reject_withdrawal(withdrawal_id):
    db = DBSession()
    withdrawal = db.query(Withdraw).filter_by(id=withdrawal_id).first()
    if withdrawal:
        withdrawal.status = 'Rejected'
        db.commit()
        flash('Withdrawal rejected!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/adjust-wallet/<int:user_id>', methods=['POST'])
@admin_required
def adjust_wallet(user_id):
    db = DBSession()
    amount = float(request.form.get('amount'))
    update_user_wallet_db(db, user_id, amount)
    flash(f'Wallet adjusted by {amount} PKR!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-settings', methods=['POST'])
@admin_required
def update_settings():
    db = DBSession()
    settings = get_settings(db)
    settings.commission_percentage = float(request.form.get('commission_percentage'))
    settings.min_withdrawal = float(request.form.get('min_withdrawal'))
    settings.ads_enabled = request.form.get('ads_enabled') == 'on'
    settings.whatsapp_contact = request.form.get('whatsapp_contact','')
    settings.email_contact = request.form.get('email_contact','')
    payment_methods_input = request.form.get('payment_methods')
    if payment_methods_input:
        settings.payment_methods = payment_methods_input
    db.commit()
    flash('Settings updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-packages', methods=['POST'])
@admin_required
def manage_packages():
    db = DBSession()
    action = request.form.get('action')
    if action == 'add':
        new_package = Package(name=request.form.get('name'), price=float(request.form.get('price')))
        db.add(new_package)
        db.commit()
        flash('Package added successfully!', 'success')
    elif action == 'edit':
        package_id = int(request.form.get('package_id'))
        package = db.query(Package).filter_by(id=package_id).first()
        if package:
            package.name = request.form.get('name')
            package.price = float(request.form.get('price'))
            db.commit()
            flash('Package updated successfully!', 'success')
    elif action == 'delete':
        package_id = int(request.form.get('package_id'))
        package = db.query(Package).filter_by(id=package_id).first()
        if package:
            db.delete(package)
            db.commit()
            flash('Package deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-payment-methods', methods=['POST'])
@admin_required
def manage_payment_methods():
    db = DBSession()
    settings = get_settings(db)
    payment_methods = json.loads(settings.payment_methods or '[]')
    action = request.form.get('action')
    if action == 'add':
        new_method = {
            'id': max([pm.get('id',0) for pm in payment_methods], default=0) + 1,
            'type': request.form.get('type'),
            'account_number': request.form.get('account_number'),
            'account_name': request.form.get('account_name')
        }
        if request.form.get('bank_name'):
            new_method['bank_name'] = request.form.get('bank_name')
        payment_methods.append(new_method)
        flash('Payment method added successfully!', 'success')
    elif action == 'edit':
        method_id = int(request.form.get('method_id'))
        for pm in payment_methods:
            if pm.get('id') == method_id:
                pm['type'] = request.form.get('type')
                pm['account_number'] = request.form.get('account_number')
                pm['account_name'] = request.form.get('account_name')
                if request.form.get('bank_name'):
                    pm['bank_name'] = request.form.get('bank_name')
                flash('Payment method updated successfully!', 'success')
                break
    elif action == 'delete':
        method_id = int(request.form.get('method_id'))
        payment_methods = [pm for pm in payment_methods if pm.get('id') != method_id]
        flash('Payment method deleted successfully!', 'success')
    settings.payment_methods = json.dumps(payment_methods)
    db.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-ads')
@admin_required
def manage_ads():
    db = DBSession()
    ads = db.query(Ad).all()
    ad_views = db.query(AdView).all()
    ad_stats = []
    for ad in ads:
        views = len([av for av in ad_views if av.ad_id == ad.id])
        ad_stats.append({'id':ad.id,'title':ad.title,'description':ad.description,'reward':ad.reward,'type':ad.type,'media_file':ad.media_file,'link':ad.link,'created_date':ad.created_date,'views':views})
    return render_template('manage_ads.html', ads=ad_stats)

@app.route('/admin/add-ad', methods=['POST'])
@admin_required
def add_ad():
    db = DBSession()
    title = request.form.get('title')
    description = request.form.get('description')
    reward = float(request.form.get('reward'))
    ad_type = request.form.get('ad_type')
    media_file = None
    link = None
    if ad_type in ['video','image'] and 'media_file' in request.files:
        file = request.files['media_file']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"ad_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file.save(os.path.join(app.config['ADS_FOLDER'], filename))
            media_file = filename
    elif ad_type == 'link':
        link = request.form.get('link')
    new_ad = Ad(title=title, description=description, reward=reward, type=ad_type, media_file=media_file, link=link)
    db.add(new_ad)
    db.commit()
    flash('Ad added successfully!', 'success')
    return redirect(url_for('manage_ads'))

@app.route('/admin/delete-ad/<int:ad_id>')
@admin_required
def delete_ad(ad_id):
    db = DBSession()
    ad = db.query(Ad).filter_by(id=ad_id).first()
    if ad:
        db.delete(ad)
        db.commit()
        flash('Ad deleted successfully!', 'success')
    return redirect(url_for('manage_ads'))

@app.route('/admin/change-password', methods=['GET','POST'])
@admin_required
def change_admin_password():
    db = DBSession()
    settings = get_settings(db)
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not check_password_hash(settings.admin_password, current_password):
            flash('Current password is incorrect!', 'error')
            return redirect(url_for('change_admin_password'))
        if new_password != confirm_password:
            flash('New passwords do not match!', 'error')
            return redirect(url_for('change_admin_password'))
        settings.admin_password = generate_password_hash(new_password)
        db.commit()
        flash('Admin password changed successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('change_admin_password.html')

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if _name_ == '_main_':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)