import os
import time
import json
import csv
import io
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, redirect, url_for, flash, request,
    jsonify, send_file, send_from_directory, abort, current_app
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, SelectField, IntegerField,
    TextAreaField, BooleanField, URLField
)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange, URL
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import requests
import pandas as pd

from config import Config
from models import db, User, Website, UptimeCheck, Backup

app = Flask(__name__)
app.config.from_object(Config)

@app.context_processor
def inject_globals():
    return {'current_year': datetime.utcnow().year}

os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

scheduler = BackgroundScheduler(daemon=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------- Forms --------------------
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(3, 80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[Optional(), Length(0, 150)])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create Account')


class LoginForm(FlaskForm):
    username = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class WebsiteForm(FlaskForm):
    name = StringField('Website Name', validators=[DataRequired(), Length(1, 150)])
    url = URLField('URL', validators=[DataRequired(), URL()])
    ping_interval = SelectField('Ping Interval (minutes)', coerce=int, choices=[
        (1, '1 minute'), (5, '5 minutes'), (10, '10 minutes'),
        (15, '15 minutes'), (30, '30 minutes'), (60, '60 minutes')
    ], default=5)
    expected_status = IntegerField('Expected Status Code', validators=[NumberRange(100, 599)], default=200)
    timeout = IntegerField('Timeout (seconds)', validators=[NumberRange(1, 60)], default=10)
    submit = SubmitField('Save Website')


class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[Optional(), Length(0, 150)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    dark_mode = BooleanField('Dark Mode')
    submit = SubmitField('Update Profile')


class PasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')


# -------------------- Helpers --------------------
def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not key:
            return jsonify({'error': 'API key required'}), 401
        user = User.query.filter_by(api_key=key, is_active=True).first()
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(user, *args, **kwargs)
    return decorated


def perform_check(website_id):
    with app.app_context():
        website = db.session.get(Website, website_id)
        if not website or not website.is_active:
            return
        is_up = False
        status_code = None
        response_time = None
        error_message = None
        start = time.time()
        try:
            headers = {'User-Agent': 'TechSerenia-UpTime/1.0 (+https://techserenia.com)'}
            resp = requests.get(
                website.url,
                timeout=website.timeout or 10,
                headers=headers,
                allow_redirects=True
            )
            response_time = round((time.time() - start) * 1000, 2)
            status_code = resp.status_code
            is_up = (status_code == (website.expected_status or 200))
            if not is_up:
                error_message = f'Unexpected status code: {status_code}'
        except requests.exceptions.Timeout:
            response_time = round((time.time() - start) * 1000, 2)
            error_message = 'Request timed out'
        except requests.exceptions.ConnectionError as e:
            response_time = round((time.time() - start) * 1000, 2)
            error_message = f'Connection error: {str(e)[:200]}'
        except Exception as e:
            response_time = round((time.time() - start) * 1000, 2)
            error_message = f'Error: {str(e)[:200]}'

        check = UptimeCheck(
            website_id=website.id,
            is_up=is_up,
            status_code=status_code,
            response_time=response_time,
            error_message=error_message
        )
        db.session.add(check)
        website.last_checked = datetime.utcnow()
        website.last_status = 'up' if is_up else 'down'
        website.last_response_time = response_time
        website.last_status_code = status_code
        website.last_error = error_message
        db.session.commit()


def schedule_website(website):
    job_id = f'ping_{website.id}'
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    if website.is_active:
        interval = max(1, website.ping_interval or 5)
        scheduler.add_job(
            perform_check,
            trigger=IntervalTrigger(minutes=interval),
            args=[website.id],
            id=job_id,
            replace_existing=True,
            max_instances=1
        )


def reschedule_all():
    with app.app_context():
        for w in Website.query.filter_by(is_active=True).all():
            schedule_website(w)


# -------------------- Routes --------------------
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken.', 'error')
            return render_template('register.html', form=form)
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered.', 'error')
            return render_template('register.html', form=form)
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.lower().strip(),
            full_name=form.full_name.data.strip() if form.full_name.data else None
        )
        user.set_password(form.password.data)
        user.generate_api_key()
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Account created successfully. Welcome to TechSerenia UpTime.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.username.data.lower())
        ).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('Signed in successfully.', 'success')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid username/email or password.', 'error')
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    websites = current_user.websites.order_by(Website.created_at.desc()).all()
    total = len(websites)
    up_count = sum(1 for w in websites if w.last_status == 'up')
    down_count = sum(1 for w in websites if w.last_status == 'down')
    avg_uptime = 0
    if websites:
        avg_uptime = round(sum(w.uptime_percentage() for w in websites) / total, 2)
    recent_checks = (
        UptimeCheck.query
        .join(Website)
        .filter(Website.user_id == current_user.id)
        .order_by(UptimeCheck.checked_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        'dashboard.html',
        websites=websites,
        total=total,
        up_count=up_count,
        down_count=down_count,
        avg_uptime=avg_uptime,
        recent_checks=recent_checks
    )


@app.route('/websites/add', methods=['GET', 'POST'])
@login_required
def add_website():
    form = WebsiteForm()
    if form.validate_on_submit():
        website = Website(
            user_id=current_user.id,
            name=form.name.data.strip(),
            url=form.url.data.strip(),
            ping_interval=form.ping_interval.data,
            expected_status=form.expected_status.data,
            timeout=form.timeout.data
        )
        db.session.add(website)
        db.session.commit()
        schedule_website(website)
        # immediate check
        perform_check(website.id)
        flash('Website added and first check scheduled.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('website_form.html', form=form, title='Add Website')


@app.route('/websites/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_website(id):
    website = Website.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    form = WebsiteForm(obj=website)
    if form.validate_on_submit():
        website.name = form.name.data.strip()
        website.url = form.url.data.strip()
        website.ping_interval = form.ping_interval.data
        website.expected_status = form.expected_status.data
        website.timeout = form.timeout.data
        db.session.commit()
        schedule_website(website)
        flash('Website updated.', 'success')
        return redirect(url_for('website_detail', id=website.id))
    return render_template('website_form.html', form=form, title='Edit Website', website=website)


@app.route('/websites/<int:id>')
@login_required
def website_detail(id):
    website = Website.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    page = request.args.get('page', 1, type=int)
    checks = website.checks.order_by(UptimeCheck.checked_at.desc()).paginate(page=page, per_page=20)
    uptime_7 = website.uptime_percentage(7)
    uptime_30 = website.uptime_percentage(30)
    return render_template(
        'website_detail.html',
        website=website,
        checks=checks,
        uptime_7=uptime_7,
        uptime_30=uptime_30
    )


@app.route('/websites/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_website(id):
    website = Website.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    website.is_active = not website.is_active
    db.session.commit()
    schedule_website(website)
    status = 'activated' if website.is_active else 'paused'
    flash(f'Website {status}.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/websites/<int:id>/delete', methods=['POST'])
@login_required
def delete_website(id):
    website = Website.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    job_id = f'ping_{website.id}'
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    db.session.delete(website)
    db.session.commit()
    flash('Website deleted.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/websites/<int:id>/check-now', methods=['POST'])
@login_required
def check_now(id):
    website = Website.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    perform_check(website.id)
    flash('Manual check completed.', 'success')
    return redirect(url_for('website_detail', id=id))


@app.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    website_id = request.args.get('website_id', type=int)
    status = request.args.get('status')
    query = (
        UptimeCheck.query
        .join(Website)
        .filter(Website.user_id == current_user.id)
    )
    if website_id:
        query = query.filter(UptimeCheck.website_id == website_id)
    if status == 'up':
        query = query.filter(UptimeCheck.is_up == True)
    elif status == 'down':
        query = query.filter(UptimeCheck.is_up == False)
    checks = query.order_by(UptimeCheck.checked_at.desc()).paginate(page=page, per_page=30)
    websites = current_user.websites.all()
    return render_template('history.html', checks=checks, websites=websites, selected_website=website_id, selected_status=status)


@app.route('/history/export/<fmt>')
@login_required
def export_history(fmt):
    website_id = request.args.get('website_id', type=int)
    query = (
        UptimeCheck.query
        .join(Website)
        .filter(Website.user_id == current_user.id)
    )
    if website_id:
        query = query.filter(UptimeCheck.website_id == website_id)
    checks = query.order_by(UptimeCheck.checked_at.desc()).limit(5000).all()
    rows = []
    for c in checks:
        rows.append({
            'Website': c.website.name,
            'URL': c.website.url,
            'Checked At (UTC)': c.checked_at.strftime('%Y-%m-%d %H:%M:%S'),
            'Status': 'Up' if c.is_up else 'Down',
            'Status Code': c.status_code or '',
            'Response Time (ms)': c.response_time or '',
            'Error': c.error_message or ''
        })
    df = pd.DataFrame(rows)
    if fmt == 'csv':
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'tsut_history_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    elif fmt == 'xlsx':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Uptime History')
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'tsut_history_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    abort(400)


@app.route('/analytics')
@login_required
def analytics():
    websites = current_user.websites.all()
    data = []
    for w in websites:
        last_24h = datetime.utcnow() - timedelta(hours=24)
        checks_24h = w.checks.filter(UptimeCheck.checked_at >= last_24h).all()
        up_24h = sum(1 for c in checks_24h if c.is_up)
        total_24h = len(checks_24h)
        avg_rt = 0
        if checks_24h:
            rts = [c.response_time for c in checks_24h if c.response_time is not None]
            avg_rt = round(sum(rts) / len(rts), 2) if rts else 0
        data.append({
            'website': w,
            'uptime_7': w.uptime_percentage(7),
            'uptime_30': w.uptime_percentage(30),
            'checks_24h': total_24h,
            'up_24h': up_24h,
            'avg_rt': avg_rt,
            'errors_7': w.checks.filter(
                UptimeCheck.checked_at >= datetime.utcnow() - timedelta(days=7),
                UptimeCheck.is_up == False
            ).count()
        })
    return render_template('analytics.html', data=data)


@app.route('/backups')
@login_required
def backups():
    page = request.args.get('page', 1, type=int)
    backups_list = current_user.backups.order_by(Backup.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('backups.html', backups=backups_list)


@app.route('/backups/<int:id>/download')
@login_required
def download_backup(id):
    backup = Backup.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    path = os.path.join(app.config['BACKUP_FOLDER'], backup.filename)
    if not os.path.isfile(path):
        flash('Backup file not found on server.', 'error')
        return redirect(url_for('backups'))
    return send_file(path, as_attachment=True, download_name=backup.original_name or backup.filename)


@app.route('/backups/<int:id>/delete', methods=['POST'])
@login_required
def delete_backup(id):
    backup = Backup.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    path = os.path.join(app.config['BACKUP_FOLDER'], backup.filename)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    db.session.delete(backup)
    db.session.commit()
    flash('Backup deleted.', 'success')
    return redirect(url_for('backups'))


@app.route('/backup-client')
@login_required
def backup_client():
    return render_template('backup_client.html')


@app.route('/backup-client/download/<path:filename>')
@login_required
def download_client_file(filename):
    client_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup_client')
    return send_from_directory(client_dir, filename, as_attachment=True)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    pwd_form = PasswordForm()
    if form.validate_on_submit() and 'profile' in request.form:
        current_user.full_name = form.full_name.data.strip() if form.full_name.data else None
        if form.email.data.lower() != current_user.email:
            if User.query.filter_by(email=form.email.data.lower()).first():
                flash('Email already in use.', 'error')
                return render_template('profile.html', form=form, pwd_form=pwd_form)
            current_user.email = form.email.data.lower()
        current_user.dark_mode = form.dark_mode.data
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    if pwd_form.validate_on_submit() and 'password' in request.form:
        if not current_user.check_password(pwd_form.current_password.data):
            flash('Current password is incorrect.', 'error')
        else:
            current_user.set_password(pwd_form.new_password.data)
            db.session.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('profile'))
    return render_template('profile.html', form=form, pwd_form=pwd_form)


@app.route('/regenerate-api-key', methods=['POST'])
@login_required
def regenerate_api_key():
    current_user.generate_api_key()
    db.session.commit()
    flash('API key regenerated. Update any clients using the old key.', 'success')
    return redirect(url_for('profile'))


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'sitemap.xml', mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'robots.txt', mimetype='text/plain')


# -------------------- API for backup client --------------------
@app.route('/api/v1/backup', methods=['POST'])
@api_key_required
def api_backup(user):
    if 'file' not in request.files and not request.data:
        return jsonify({'error': 'No file or data provided'}), 400
    website_id = request.form.get('website_id') or request.args.get('website_id')
    notes = request.form.get('notes') or request.args.get('notes') or ''
    source = request.form.get('source') or request.args.get('source') or 'api'
    original_name = None
    data = None
    if 'file' in request.files:
        f = request.files['file']
        if f.filename:
            original_name = secure_filename(f.filename)
            data = f.read()
    else:
        data = request.data
        original_name = request.headers.get('X-Filename') or f'backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.bin'
    if not data:
        return jsonify({'error': 'Empty payload'}), 400
    if len(data) > app.config['MAX_CONTENT_LENGTH']:
        return jsonify({'error': 'File too large'}), 413
    filename = f'{user.id}_{secrets.token_hex(8)}_{original_name or "backup.bin"}'
    path = os.path.join(app.config['BACKUP_FOLDER'], filename)
    with open(path, 'wb') as out:
        out.write(data)
    website = None
    if website_id:
        try:
            website = Website.query.filter_by(id=int(website_id), user_id=user.id).first()
        except (ValueError, TypeError):
            pass
    backup = Backup(
        user_id=user.id,
        website_id=website.id if website else None,
        filename=filename,
        original_name=original_name,
        size_bytes=len(data),
        source=source,
        notes=notes[:500] if notes else None
    )
    db.session.add(backup)
    db.session.commit()
    return jsonify({
        'success': True,
        'backup_id': backup.id,
        'filename': original_name,
        'size': backup.size_bytes,
        'created_at': backup.created_at.isoformat()
    })


@app.route('/api/v1/status')
@api_key_required
def api_status(user):
    websites = user.websites.all()
    return jsonify({
        'user': user.username,
        'websites': [
            {
                'id': w.id,
                'name': w.name,
                'url': w.url,
                'status': w.last_status,
                'last_checked': w.last_checked.isoformat() if w.last_checked else None,
                'uptime_30d': w.uptime_percentage(30)
            } for w in websites
        ]
    })


# -------------------- CLI / init --------------------
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database tables created.')


def create_app():
    with app.app_context():
        db.create_all()
        if not scheduler.running:
            scheduler.start()
            reschedule_all()
    return app


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    if not scheduler.running:
        scheduler.start()
        reschedule_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
