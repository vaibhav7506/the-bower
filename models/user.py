from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, String
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from .mixins import TimestampMixin


class UserRole(str, Enum):
    STAFF = "STAFF"
    ADMIN = "ADMIN"


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, native_enum=False, length=16),
        nullable=False,
        default=UserRole.STAFF,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def set_password(self, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Passwords must contain at least 12 characters.")
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_locked(self, now: datetime | None = None) -> bool:
        if self.locked_until is None:
            return False
        comparison = now or datetime.now(timezone.utc)
        locked_until = self.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return locked_until > comparison
