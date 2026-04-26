from datetime import datetime, timedelta

from flask_login import current_user

from db import db
from models import User, UserPresence


ONLINE_TIMEOUT = timedelta(seconds=45)


def upsert_presence(user_id, company_id, sector_id=None, status="online", socket_session_id=None):
    presence = UserPresence.query.filter_by(user_id=user_id).first()
    now = datetime.utcnow()

    if not presence:
        presence = UserPresence(
            user_id=user_id,
            company_id=company_id,
            sector_id=sector_id,
        )
        db.session.add(presence)

    presence.company_id = company_id
    presence.sector_id = sector_id
    presence.status = status
    presence.socket_session_id = socket_session_id
    presence.last_heartbeat_at = now if status != "offline" else presence.last_heartbeat_at
    presence.updated_at = now

    user = db.session.get(User, user_id)
    if user:
        user.last_seen = now

    db.session.commit()
    return presence


def mark_presence_offline(user_id, socket_session_id=None):
    presence = UserPresence.query.filter_by(user_id=user_id).first()
    if not presence:
        return None

    if socket_session_id and presence.socket_session_id != socket_session_id:
        return presence

    presence.status = "offline"
    presence.socket_session_id = None
    presence.updated_at = datetime.utcnow()
    db.session.commit()
    return presence


def heartbeat_presence(user_id, socket_session_id=None):
    presence = UserPresence.query.filter_by(user_id=user_id).first()
    if not presence:
        if current_user.is_authenticated:
            return upsert_presence(
                current_user.id,
                current_user.company_id,
                current_user.sector_id,
                status="online",
                socket_session_id=socket_session_id,
            )
        return None

    if socket_session_id:
        presence.socket_session_id = socket_session_id
    presence.status = "online"
    presence.last_heartbeat_at = datetime.utcnow()
    presence.updated_at = datetime.utcnow()
    user = db.session.get(User, user_id)
    if user:
        user.last_seen = presence.last_heartbeat_at
    db.session.commit()
    return presence


def normalize_presence_status(presence):
    if not presence:
        return "offline"

    if presence.status == "offline":
        return "offline"

    if not presence.last_heartbeat_at:
        return presence.status

    if datetime.utcnow() - presence.last_heartbeat_at > ONLINE_TIMEOUT:
        return "away"

    return "online"


def get_company_presence_map(company_id):
    presences = UserPresence.query.filter_by(company_id=company_id).all()
    return {presence.user_id: normalize_presence_status(presence) for presence in presences}
