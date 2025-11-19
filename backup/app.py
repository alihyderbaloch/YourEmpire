import os
import json
import random
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'yourempire-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ADS_FOLDER'] = 'static/ads'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'mp4', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_json(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [] if filename != 'settings.json' else {
            "commission_percentage": 50,
            "min_withdrawal": 225,
            "admin_password": generate_password_hash("admin123"),
            "ads_enabled": True,
            "whatsapp_contact": "",
            "email_contact": "",
            "payment_methods": []
        }

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def generate_referral_code():
    users = load_json('users.json')
    while True:
        code = f"YE{random.randint(1000, 9999)}"
        if not any(u['referral_code'] == code for u in users):
            return code

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

def get_user_by_id(user_id):
    users = load_json('users.json')
    return next((u for u in users if u['id'] == user_id), None)

def update_user_wallet(user_id, amount):
    users = load_json('users.json')
    for user in users:
        if user['id'] == user_id:
            user['wallet'] = round(user['wallet'] + amount, 2)
            break
    save_json('users.json', users)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        ref_code = request.form.get('referral_code', '').strip()
        
        users = load_json('users.json')
        
        if any(u['email'] == email for u in users):
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))
        
        referred_by = None
        if ref_code:
            referrer = next((u for u in users if u['referral_code'] == ref_code), None)
            if referrer:
                referred_by = referrer['id']
            else:
                flash('Invalid referral code!', 'error')
                return redirect(url_for('register'))
        
        new_user = {
            'id': len(users) + 1,
            'name': name,
            'email': email,
            'password': generate_password_hash(password),
            'referral_code': generate_referral_code(),
            'wallet': 0.0,
            'referred_by': referred_by,
            'joined_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        users.append(new_user)
        save_json('users.json', users)
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    ref_code = request.args.get('ref', '')
    return render_template('register.html', ref_code=ref_code)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if email == 'admin@yourempire.com':
            settings = load_json('settings.json')
            admin_pass = settings.get('admin_password', generate_password_hash('admin123'))
            
            if check_password_hash(admin_pass, password):
                session['is_admin'] = True
                session['admin_email'] = email
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials!', 'error')
                return redirect(url_for('login'))
        
        users = load_json('users.json')
        user = next((u for u in users if u['email'] == email), None)
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            flash(f'Welcome back, {user["name"]}!', 'success')
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

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        flash('Please contact admin for password reset. Check contact details on the homepage.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/dashboard')
@login_required
def user_dashboard():
    user = get_user_by_id(session['user_id'])
    packages = load_json('packages.json')
    payments = [p for p in load_json('payments.json') if p['user_id'] == user['id']]
    withdrawals = [w for w in load_json('withdraws.json') if w['user_id'] == user['id']]
    
    ad_views = load_json('ad_views.json')
    user_ad_views = [av for av in ad_views if av['user_id'] == user['id']]
    total_ad_earnings = sum(av['reward'] for av in user_ad_views)
    
    settings = load_json('settings.json')
    ads_enabled = settings.get('ads_enabled', True)
    
    referrals = [u for u in load_json('users.json') if u.get('referred_by') == user['id']]
    
    return render_template('user_dashboard.html', 
                         user=user, 
                         packages=packages, 
                         payments=payments,
                         withdrawals=withdrawals,
                         ads_enabled=ads_enabled,
                         total_ad_earnings=total_ad_earnings,
                         referrals=referrals)

@app.route('/buy-package', methods=['GET', 'POST'])
@login_required
def buy_package():
    if request.method == 'POST':
        package_id = int(request.form.get('package_id'))
        payment_method_id = int(request.form.get('payment_method'))
        transaction_id = request.form.get('transaction_id')
        
        packages = load_json('packages.json')
        package = next((p for p in packages if p['id'] == package_id), None)
        
        settings = load_json('settings.json')
        payment_method = next((pm for pm in settings['payment_methods'] if pm['id'] == payment_method_id), None)
        
        if not package or not payment_method:
            flash('Invalid package or payment method!', 'error')
            return redirect(url_for('buy_package'))
        
        screenshot = None
        if 'screenshot' in request.files:
            file = request.files['screenshot']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                screenshot = filename
        
        payments = load_json('payments.json')
        new_payment = {
            'id': len(payments) + 1,
            'user_id': session['user_id'],
            'package_id': package_id,
            'package_name': package['name'],
            'amount': package['price'],
            'payment_method': payment_method['type'],
            'payment_account': payment_method['account_number'],
            'transaction_id': transaction_id,
            'screenshot': screenshot,
            'status': 'Pending',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        payments.append(new_payment)
        save_json('payments.json', payments)
        
        flash('Payment submitted successfully! Waiting for admin approval.', 'success')
        return redirect(url_for('user_dashboard'))
    
    packages = load_json('packages.json')
    settings = load_json('settings.json')
    payment_methods = settings.get('payment_methods', [])
    
    return render_template('buy_package.html', packages=packages, payment_methods=payment_methods)

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    user = get_user_by_id(session['user_id'])
    settings = load_json('settings.json')
    min_withdrawal = settings.get('min_withdrawal', 225)
    
    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        payment_method = request.form.get('payment_method')
        account_number = request.form.get('account_number')
        account_name = request.form.get('account_name')
        
        if amount < min_withdrawal:
            flash(f'Minimum withdrawal amount is {min_withdrawal} PKR!', 'error')
            return redirect(url_for('withdraw'))
        
        if amount > user['wallet']:
            flash('Insufficient balance!', 'error')
            return redirect(url_for('withdraw'))
        
        withdrawals = load_json('withdraws.json')
        new_withdrawal = {
            'id': len(withdrawals) + 1,
            'user_id': user['id'],
            'amount': amount,
            'payment_method': payment_method,
            'account_number': account_number,
            'account_name': account_name,
            'status': 'Pending',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        withdrawals.append(new_withdrawal)
        save_json('withdraws.json', withdrawals)
        
        flash('Withdrawal request submitted! Waiting for admin approval.', 'success')
        return redirect(url_for('user_dashboard'))
    
    return render_template('withdraw.html', user=user, min_withdrawal=min_withdrawal)

@app.route('/watch-ads')
@login_required
def watch_ads():
    settings = load_json('settings.json')
    if not settings.get('ads_enabled', True):
        flash('Ad section is currently disabled.', 'info')
        return redirect(url_for('user_dashboard'))
    
    ads = load_json('ads.json')
    ad_views = load_json('ad_views.json')
    
    today = datetime.now().strftime('%Y-%m-%d')
    user_today_views = [av for av in ad_views if av['user_id'] == session['user_id'] and av['date'].startswith(today)]
    viewed_ad_ids = [av['ad_id'] for av in user_today_views]
    
    available_ads = [ad for ad in ads if ad['id'] not in viewed_ad_ids]
    
    user_ad_history = [av for av in ad_views if av['user_id'] == session['user_id']]
    
    return render_template('watch_ads.html', ads=available_ads, ad_history=user_ad_history)

@app.route('/view-ad/<int:ad_id>')
@login_required
def view_ad(ad_id):
    ads = load_json('ads.json')
    ad = next((a for a in ads if a['id'] == ad_id), None)
    
    if not ad:
        flash('Ad not found!', 'error')
        return redirect(url_for('watch_ads'))
    
    ad_views = load_json('ad_views.json')
    today = datetime.now().strftime('%Y-%m-%d')
    
    already_viewed = any(
        av['user_id'] == session['user_id'] and 
        av['ad_id'] == ad_id and 
        av['date'].startswith(today)
        for av in ad_views
    )
    
    if already_viewed:
        flash('You have already viewed this ad today!', 'info')
        return redirect(url_for('watch_ads'))
    
    new_view = {
        'id': len(ad_views) + 1,
        'user_id': session['user_id'],
        'ad_id': ad_id,
        'reward': ad['reward'],
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    ad_views.append(new_view)
    save_json('ad_views.json', ad_views)
    
    update_user_wallet(session['user_id'], ad['reward'])
    
    flash(f'You earned {ad["reward"]} PKR for viewing this ad!', 'success')
    return redirect(url_for('watch_ads'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    users = load_json('users.json')
    payments = load_json('payments.json')
    withdrawals = load_json('withdraws.json')
    packages = load_json('packages.json')
    ads = load_json('ads.json')
    ad_views = load_json('ad_views.json')
    settings = load_json('settings.json')
    
    stats = {
        'total_users': len(users),
        'total_payments': len([p for p in payments if p['status'] == 'Approved']),
        'total_withdrawals': len([w for w in withdrawals if w['status'] == 'Approved']),
        'pending_payments': len([p for p in payments if p['status'] == 'Pending']),
        'pending_withdrawals': len([w for w in withdrawals if w['status'] == 'Pending']),
        'total_ad_views': len(ad_views),
        'total_ad_payouts': sum(av['reward'] for av in ad_views),
        'total_ads': len(ads)
    }
    
    return render_template('admin_dashboard.html', 
                         users=users, 
                         payments=payments, 
                         withdrawals=withdrawals,
                         packages=packages,
                         stats=stats,
                         settings=settings)

@app.route('/admin/approve-payment/<int:payment_id>')
@admin_required
def approve_payment(payment_id):
    payments = load_json('payments.json')
    payment = next((p for p in payments if p['id'] == payment_id), None)
    
    if payment and payment['status'] == 'Pending':
        payment['status'] = 'Approved'
        save_json('payments.json', payments)
        
        settings = load_json('settings.json')
        commission_rate = settings.get('commission_percentage', 50) / 100
        
        users = load_json('users.json')
        buyer = next((u for u in users if u['id'] == payment['user_id']), None)
        
        if buyer and buyer.get('referred_by'):
            commission = payment['amount'] * commission_rate
            update_user_wallet(buyer['referred_by'], commission)
            flash(f'Payment approved! Commission of {commission} PKR credited to referrer.', 'success')
        else:
            flash('Payment approved!', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-payment/<int:payment_id>')
@admin_required
def reject_payment(payment_id):
    payments = load_json('payments.json')
    payment = next((p for p in payments if p['id'] == payment_id), None)
    
    if payment:
        payment['status'] = 'Rejected'
        save_json('payments.json', payments)
        flash('Payment rejected!', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve-withdrawal/<int:withdrawal_id>')
@admin_required
def approve_withdrawal(withdrawal_id):
    withdrawals = load_json('withdraws.json')
    withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
    
    if withdrawal and withdrawal['status'] == 'Pending':
        user = get_user_by_id(withdrawal['user_id'])
        
        if user['wallet'] >= withdrawal['amount']:
            withdrawal['status'] = 'Approved'
            save_json('withdraws.json', withdrawals)
            
            update_user_wallet(withdrawal['user_id'], -withdrawal['amount'])
            flash('Withdrawal approved and amount deducted from wallet!', 'success')
        else:
            flash('User has insufficient balance!', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-withdrawal/<int:withdrawal_id>')
@admin_required
def reject_withdrawal(withdrawal_id):
    withdrawals = load_json('withdraws.json')
    withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
    
    if withdrawal:
        withdrawal['status'] = 'Rejected'
        save_json('withdraws.json', withdrawals)
        flash('Withdrawal rejected!', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/adjust-wallet/<int:user_id>', methods=['POST'])
@admin_required
def adjust_wallet(user_id):
    amount = float(request.form.get('amount'))
    update_user_wallet(user_id, amount)
    flash(f'Wallet adjusted by {amount} PKR!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-settings', methods=['POST'])
@admin_required
def update_settings():
    settings = load_json('settings.json')
    
    settings['commission_percentage'] = float(request.form.get('commission_percentage'))
    settings['min_withdrawal'] = float(request.form.get('min_withdrawal'))
    settings['ads_enabled'] = request.form.get('ads_enabled') == 'on'
    settings['whatsapp_contact'] = request.form.get('whatsapp_contact', '')
    settings['email_contact'] = request.form.get('email_contact', '')
    
    save_json('settings.json', settings)
    flash('Settings updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-packages', methods=['POST'])
@admin_required
def manage_packages():
    action = request.form.get('action')
    packages = load_json('packages.json')
    
    if action == 'add':
        new_package = {
            'id': max([p['id'] for p in packages], default=0) + 1,
            'name': request.form.get('name'),
            'price': float(request.form.get('price'))
        }
        packages.append(new_package)
        flash('Package added successfully!', 'success')
    
    elif action == 'edit':
        package_id = int(request.form.get('package_id'))
        package = next((p for p in packages if p['id'] == package_id), None)
        if package:
            package['name'] = request.form.get('name')
            package['price'] = float(request.form.get('price'))
            flash('Package updated successfully!', 'success')
    
    elif action == 'delete':
        package_id = int(request.form.get('package_id'))
        packages = [p for p in packages if p['id'] != package_id]
        flash('Package deleted successfully!', 'success')
    
    save_json('packages.json', packages)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-payment-methods', methods=['POST'])
@admin_required
def manage_payment_methods():
    action = request.form.get('action')
    settings = load_json('settings.json')
    
    if 'payment_methods' not in settings:
        settings['payment_methods'] = []
    
    payment_methods = settings['payment_methods']
    
    if action == 'add':
        new_method = {
            'id': max([pm['id'] for pm in payment_methods], default=0) + 1,
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
        method = next((pm for pm in payment_methods if pm['id'] == method_id), None)
        if method:
            method['type'] = request.form.get('type')
            method['account_number'] = request.form.get('account_number')
            method['account_name'] = request.form.get('account_name')
            if request.form.get('bank_name'):
                method['bank_name'] = request.form.get('bank_name')
            flash('Payment method updated successfully!', 'success')
    
    elif action == 'delete':
        method_id = int(request.form.get('method_id'))
        payment_methods = [pm for pm in payment_methods if pm['id'] != method_id]
        settings['payment_methods'] = payment_methods
        flash('Payment method deleted successfully!', 'success')
    
    settings['payment_methods'] = payment_methods
    save_json('settings.json', settings)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage-ads')
@admin_required
def manage_ads():
    ads = load_json('ads.json')
    ad_views = load_json('ad_views.json')
    
    ad_stats = []
    for ad in ads:
        views = len([av for av in ad_views if av['ad_id'] == ad['id']])
        ad_stats.append({**ad, 'views': views})
    
    return render_template('manage_ads.html', ads=ad_stats)

@app.route('/admin/add-ad', methods=['POST'])
@admin_required
def add_ad():
    title = request.form.get('title')
    description = request.form.get('description')
    reward = float(request.form.get('reward'))
    ad_type = request.form.get('ad_type')
    
    ads = load_json('ads.json')
    
    media_file = None
    link = None
    
    if ad_type in ['video', 'image']:
        if 'media_file' in request.files:
            file = request.files['media_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"ad_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['ADS_FOLDER'], filename))
                media_file = filename
    elif ad_type == 'link':
        link = request.form.get('link')
    
    new_ad = {
        'id': max([a['id'] for a in ads], default=0) + 1,
        'title': title,
        'description': description,
        'reward': reward,
        'type': ad_type,
        'media_file': media_file,
        'link': link,
        'created_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    ads.append(new_ad)
    save_json('ads.json', ads)
    
    flash('Ad added successfully!', 'success')
    return redirect(url_for('manage_ads'))

@app.route('/admin/delete-ad/<int:ad_id>')
@admin_required
def delete_ad(ad_id):
    ads = load_json('ads.json')
    ads = [a for a in ads if a['id'] != ad_id]
    save_json('ads.json', ads)
    
    flash('Ad deleted successfully!', 'success')
    return redirect(url_for('manage_ads'))

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def change_admin_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        settings = load_json('settings.json')
        
        if not check_password_hash(settings['admin_password'], current_password):
            flash('Current password is incorrect!', 'error')
            return redirect(url_for('change_admin_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match!', 'error')
            return redirect(url_for('change_admin_password'))
        
        settings['admin_password'] = generate_password_hash(new_password)
        save_json('settings.json', settings)
        
        flash('Admin password changed successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('change_admin_password.html')

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ADS_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
