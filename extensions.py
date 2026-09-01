from __future__ import annotations

import sqlite3

from flask_migrate import Migrate
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate(compare_type=True, render_as_batch=True)
login_manager = LoginManager()
login_manager.login_view = "admin.login"
login_manager.login_message = "Sign in to continue to the dining room desk."


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()
