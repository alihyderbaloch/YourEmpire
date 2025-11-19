# convert_json_to_db.py
import json, os
from datetime import datetime
from app_postgres import DBSession, User, Package, Payment, Withdraw, Ad, AdView, Settings
SESSION = DBSession()

def import_users():
    path = 'users.json'
    if not os.path.exists(path):
        print('users.json not found')
        return
    with open(path,'r',encoding='utf-8') as f:
        users = json.load(f)
    for u in users:
        if SESSION.query(User).filter_by(email=u.get('email')).first():
            continue
        joined_date = None
        try:
            joined_date = datetime.strptime(u.get('joined_date'), '%Y-%m-%d %H:%M:%S')
        except Exception:
            joined_date = datetime.utcnow()
        new_user = User(
            id=u.get('id'),
            name=u.get('name'),
            email=u.get('email'),
            password=u.get('password'),
            referral_code=u.get('referral_code') or None,
            wallet=float(u.get('wallet') or 0.0),
            referred_by=u.get('referred_by'),
            joined_date=joined_date
        )
        SESSION.add(new_user)
    SESSION.commit()
    print('Imported users.json')

def import_settings():
    path = 'settings.json'
    if not os.path.exists(path):
        print('settings.json not found')
        return
    with open(path,'r',encoding='utf-8') as f:
        s = json.load(f)
    settings = SESSION.query(Settings).first()
    if not settings:
        settings = Settings(
            commission_percentage=s.get('commission_percentage',50),
            min_withdrawal=s.get('min_withdrawal',225),
            admin_password=s.get('admin_password'),
            ads_enabled=s.get('ads_enabled',True),
            whatsapp_contact=s.get('whatsapp_contact',''),
            email_contact=s.get('email_contact',''),
            payment_methods=json.dumps(s.get('payment_methods',[]))
        )
        SESSION.add(settings)
    else:
        settings.commission_percentage = s.get('commission_percentage',settings.commission_percentage)
        settings.min_withdrawal = s.get('min_withdrawal',settings.min_withdrawal)
        settings.admin_password = s.get('admin_password') or settings.admin_password
        settings.ads_enabled = s.get('ads_enabled',settings.ads_enabled)
        settings.whatsapp_contact = s.get('whatsapp_contact',settings.whatsapp_contact)
        settings.email_contact = s.get('email_contact',settings.email_contact)
        settings.payment_methods = json.dumps(s.get('payment_methods',[]))
    SESSION.commit()
    print('Imported settings.json')

if __name__ == '__main__':
    import_users()
    import_settings()
    print('Import finished.')
