import os
from dotenv import load_dotenv

load_dotenv()

_base = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'techserenia-uptime-secret-key-change-in-production-2026'
    # Default SQLite. Override with DATABASE_URL for MySQL, e.g.
    # mysql+pymysql://user:pass@host:3306/techserenia_uptime?charset=utf8mb4
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or ('sqlite:///' + os.path.join(_base, 'tsut.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    BACKUP_FOLDER = os.path.join(_base, 'backups')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    DEFAULT_PING_INTERVAL = 5
    ALLOWED_INTERVALS = [1, 5, 10, 15, 30, 60]
