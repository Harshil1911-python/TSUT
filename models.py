from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150))
    api_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    dark_mode = db.Column(db.Boolean, default=False)

    websites = db.relationship('Website', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    backups = db.relationship('Backup', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self):
        self.api_key = secrets.token_hex(32)

    def __repr__(self):
        return f'<User {self.username}>'


class Website(db.Model):
    __tablename__ = 'websites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    ping_interval = db.Column(db.Integer, default=5)  # minutes
    is_active = db.Column(db.Boolean, default=True)
    expected_status = db.Column(db.Integer, default=200)
    timeout = db.Column(db.Integer, default=10)  # seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime)
    last_status = db.Column(db.String(20))  # up / down / error
    last_response_time = db.Column(db.Float)  # ms
    last_status_code = db.Column(db.Integer)
    last_error = db.Column(db.Text)

    checks = db.relationship('UptimeCheck', backref='website', lazy='dynamic', cascade='all, delete-orphan')

    def uptime_percentage(self, days=30):
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(days=days)
        total = self.checks.filter(UptimeCheck.checked_at >= since).count()
        if total == 0:
            return 100.0
        up = self.checks.filter(UptimeCheck.checked_at >= since, UptimeCheck.is_up == True).count()
        return round((up / total) * 100, 2)

    def __repr__(self):
        return f'<Website {self.name}>'


class UptimeCheck(db.Model):
    __tablename__ = 'uptime_checks'
    id = db.Column(db.Integer, primary_key=True)
    website_id = db.Column(db.Integer, db.ForeignKey('websites.id'), nullable=False, index=True)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_up = db.Column(db.Boolean, default=False)
    status_code = db.Column(db.Integer)
    response_time = db.Column(db.Float)  # milliseconds
    error_message = db.Column(db.Text)

    def __repr__(self):
        return f'<UptimeCheck {self.website_id} {self.checked_at}>'


class Backup(db.Model):
    __tablename__ = 'backups'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    website_id = db.Column(db.Integer, db.ForeignKey('websites.id'), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    size_bytes = db.Column(db.Integer)
    source = db.Column(db.String(100))  # e.g. flask-client, manual
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    website = db.relationship('Website', backref='backups')

    def size_human(self):
        size = self.size_bytes or 0
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'

    def __repr__(self):
        return f'<Backup {self.filename}>'
