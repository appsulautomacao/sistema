from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from core.presence import heartbeat_presence, mark_presence_offline, upsert_presence


def register_socket_events(socketio):
    @socketio.on("connect")
    def on_connect():
        if not current_user.is_authenticated:
            return

        presence = upsert_presence(
            current_user.id,
            current_user.company_id,
            current_user.sector_id,
            status="online",
            socket_session_id=request.sid,
        )
        emit(
            "presence_updated",
            {
                "user_id": current_user.id,
                "status": presence.status,
                "sector_id": current_user.sector_id,
            },
            room=f"company_{current_user.company_id}",
        )

    @socketio.on("join_conversation")
    def join_conversation(data):
        join_room(f"conversation_{data['conversation_id']}")

    @socketio.on("join_company")
    def join_company(data):
        join_room(f"company_{data['company_id']}")
        if current_user.is_authenticated:
            presence = heartbeat_presence(current_user.id, socket_session_id=request.sid)
            emit(
                "presence_updated",
                {
                    "user_id": current_user.id,
                    "status": presence.status if presence else "online",
                    "sector_id": current_user.sector_id,
                },
                room=f"company_{data['company_id']}",
            )

    @socketio.on("leave_conversation")
    def leave_conversation(data):
        leave_room(f"conversation_{data['conversation_id']}")

    @socketio.on("presence_heartbeat")
    def presence_heartbeat(_data=None):
        if not current_user.is_authenticated:
            return

        presence = heartbeat_presence(current_user.id, socket_session_id=request.sid)
        emit(
            "presence_updated",
            {
                "user_id": current_user.id,
                "status": presence.status if presence else "online",
                "sector_id": current_user.sector_id,
            },
            room=f"company_{current_user.company_id}",
        )

    @socketio.on("disconnect")
    def on_disconnect():
        if not current_user.is_authenticated:
            return

        presence = mark_presence_offline(current_user.id, socket_session_id=request.sid)
        emit(
            "presence_updated",
            {
                "user_id": current_user.id,
                "status": "offline",
                "sector_id": presence.sector_id if presence else current_user.sector_id,
            },
            room=f"company_{current_user.company_id}",
        )
