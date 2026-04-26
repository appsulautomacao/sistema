import os
from datetime import timedelta

from models import Message


DEFAULT_NEW_CYCLE_GAP_HOURS = 24


def get_new_cycle_gap_hours():
    try:
        return max(1, int(os.getenv("CENTRAL_NEW_CYCLE_GAP_HOURS", DEFAULT_NEW_CYCLE_GAP_HOURS)))
    except (TypeError, ValueError):
        return DEFAULT_NEW_CYCLE_GAP_HOURS


def get_conversation_cycle_messages(conversation_id, gap_hours=None):
    messages = Message.query.filter_by(
        conversation_id=conversation_id,
    ).order_by(Message.created_at.asc()).all()

    if not messages:
        return []

    threshold = timedelta(hours=gap_hours or get_new_cycle_gap_hours())
    cycle_start_index = 0

    for index in range(1, len(messages)):
        previous_message = messages[index - 1]
        current_message = messages[index]
        if current_message.created_at - previous_message.created_at >= threshold:
            cycle_start_index = index

    return messages[cycle_start_index:]


def get_conversation_cycle_started_at(conversation_id, gap_hours=None):
    cycle_messages = get_conversation_cycle_messages(conversation_id, gap_hours=gap_hours)
    if not cycle_messages:
        return None
    return cycle_messages[0].created_at


def has_agent_message_in_current_cycle(conversation_id, gap_hours=None):
    cycle_messages = get_conversation_cycle_messages(conversation_id, gap_hours=gap_hours)
    return any((message.sender_type or message.sender) == "agent" for message in cycle_messages)
