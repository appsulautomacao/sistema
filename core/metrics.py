from collections import defaultdict
from datetime import datetime

from models import Conversation, ConversationHistory, ConversationRouting, Sector, User


def get_first_response_time(conversation_id):
    events = ConversationHistory.query.filter(
        ConversationHistory.conversation_id == conversation_id,
        ConversationHistory.action_type.in_(["created", "replied", "sent_message"]),
    ).order_by(ConversationHistory.created_at.asc()).all()

    created_time = None
    first_reply_time = None

    for event in events:
        if event.action_type == "created":
            created_time = event.created_at
        if event.action_type in ["replied", "sent_message"] and created_time:
            first_reply_time = event.created_at
            break

    if created_time and first_reply_time:
        return (first_reply_time - created_time).total_seconds()

    return None


def get_average_first_response_by_agent(company_id):
    histories = ConversationHistory.query.filter_by(
        company_id=company_id
    ).order_by(ConversationHistory.created_at.asc()).all()

    conversations = {}
    agent_times = defaultdict(list)

    for event in histories:
        conv_id = event.conversation_id

        if conv_id not in conversations:
            conversations[conv_id] = {
                "created": None,
                "replied": None,
                "agent_id": None,
            }

        if event.action_type == "created":
            conversations[conv_id]["created"] = event.created_at

        if event.action_type in ["replied", "sent_message"]:
            if conversations[conv_id]["created"] and not conversations[conv_id]["replied"]:
                conversations[conv_id]["replied"] = event.created_at
                conversations[conv_id]["agent_id"] = event.user_id

    for conv in conversations.values():
        if conv["created"] and conv["replied"] and conv["agent_id"]:
            seconds = (conv["replied"] - conv["created"]).total_seconds()
            agent_times[conv["agent_id"]].append(seconds)

    result = []

    for agent_id, times in agent_times.items():
        avg = sum(times) / len(times)
        user = User.query.get(agent_id)

        result.append({
            "agent_name": user.name if user else "Desconhecido",
            "average_seconds": avg,
            "total_conversations": len(times),
        })

    return result


def _to_minutes(seconds):
    if seconds is None:
        return None
    return round(seconds / 60, 1)


def _get_routing_duration_seconds(routing, now=None):
    if not routing or not routing.entered_at:
        return None

    now = now or datetime.utcnow()
    end_time = routing.left_at or now
    return max(int((end_time - routing.entered_at).total_seconds()), 0)


def _get_attention_level(sector, open_count, longest_open_seconds):
    if open_count == 0:
        return "ok"

    if not sector.sla_minutes:
        return "warning" if open_count >= 5 else "ok"

    sla_seconds = sector.sla_minutes * 60

    if longest_open_seconds >= sla_seconds:
        return "critical"

    if longest_open_seconds >= int(sla_seconds * 0.8):
        return "warning"

    return "ok"


def get_sector_routing_analytics(company_id):
    now = datetime.utcnow()
    sectors = Sector.query.filter_by(company_id=company_id).order_by(Sector.name.asc()).all()
    routings = ConversationRouting.query.filter_by(
        company_id=company_id
    ).order_by(ConversationRouting.entered_at.asc()).all()
    conversations = Conversation.query.filter_by(company_id=company_id).all()

    current_load_by_sector = defaultdict(lambda: {
        "current_total": 0,
        "current_assigned": 0,
        "current_unassigned": 0,
    })
    for conversation in conversations:
        if not conversation.current_sector_id:
            continue
        current_load_by_sector[conversation.current_sector_id]["current_total"] += 1
        if conversation.assigned_to:
            current_load_by_sector[conversation.current_sector_id]["current_assigned"] += 1
        else:
            current_load_by_sector[conversation.current_sector_id]["current_unassigned"] += 1

    analytics_by_sector = {}
    for sector in sectors:
        analytics_by_sector[sector.id] = {
            "sector_id": sector.id,
            "sector_name": sector.name,
            "is_central": sector.is_central,
            "sla_minutes": sector.sla_minutes,
            "total_routings": 0,
            "unique_conversations": set(),
            "completed_routings": 0,
            "open_routings": 0,
            "inbound_handoffs": 0,
            "completed_seconds": [],
            "open_seconds": [],
            "current_total": current_load_by_sector[sector.id]["current_total"],
            "current_assigned": current_load_by_sector[sector.id]["current_assigned"],
            "current_unassigned": current_load_by_sector[sector.id]["current_unassigned"],
        }

    for routing in routings:
        sector_data = analytics_by_sector.get(routing.sector_id)
        if not sector_data:
            continue

        sector_data["total_routings"] += 1
        sector_data["unique_conversations"].add(routing.conversation_id)

        if routing.transferred_by:
            sector_data["inbound_handoffs"] += 1

        duration_seconds = _get_routing_duration_seconds(routing, now=now)
        if routing.left_at:
            sector_data["completed_routings"] += 1
            if duration_seconds is not None:
                sector_data["completed_seconds"].append(duration_seconds)
        else:
            sector_data["open_routings"] += 1
            if duration_seconds is not None:
                sector_data["open_seconds"].append(duration_seconds)

    result = []
    totals = {
        "total_sectors": len(sectors),
        "total_routings": 0,
        "total_open_routings": 0,
        "total_completed_routings": 0,
        "total_handoffs": 0,
        "total_current_conversations": 0,
    }

    for sector in sectors:
        sector_data = analytics_by_sector[sector.id]
        completed_seconds = sector_data.pop("completed_seconds")
        open_seconds = sector_data.pop("open_seconds")
        unique_conversations = sector_data.pop("unique_conversations")

        average_completed_seconds = None
        if completed_seconds:
            average_completed_seconds = round(sum(completed_seconds) / len(completed_seconds), 2)

        average_open_seconds = None
        if open_seconds:
            average_open_seconds = round(sum(open_seconds) / len(open_seconds), 2)

        longest_open_seconds = max(open_seconds) if open_seconds else 0
        attention_level = _get_attention_level(
            sector,
            sector_data["open_routings"],
            longest_open_seconds,
        )

        item = {
            **sector_data,
            "unique_conversations": len(unique_conversations),
            "average_routing_seconds": average_completed_seconds,
            "average_routing_minutes": _to_minutes(average_completed_seconds),
            "average_open_seconds": average_open_seconds,
            "average_open_minutes": _to_minutes(average_open_seconds),
            "longest_open_seconds": longest_open_seconds,
            "longest_open_minutes": _to_minutes(longest_open_seconds),
            "attention_level": attention_level,
        }
        result.append(item)

        totals["total_routings"] += item["total_routings"]
        totals["total_open_routings"] += item["open_routings"]
        totals["total_completed_routings"] += item["completed_routings"]
        totals["total_handoffs"] += item["inbound_handoffs"]
        totals["total_current_conversations"] += item["current_total"]

    result.sort(
        key=lambda item: (
            0 if item["attention_level"] == "critical" else 1 if item["attention_level"] == "warning" else 2,
            -item["current_total"],
            item["sector_name"].lower(),
        )
    )

    return {
        "summary": totals,
        "sectors": result,
    }


def get_sector_routing_analytics_map(company_id):
    analytics = get_sector_routing_analytics(company_id)
    return {
        item["sector_id"]: item
        for item in analytics["sectors"]
    }


def get_sector_handoff_analytics(company_id):
    sectors = Sector.query.filter_by(company_id=company_id).all()
    sectors_by_id = {sector.id: sector for sector in sectors}
    central_sector = next((sector for sector in sectors if sector.is_central), None)
    now = datetime.utcnow()

    events = ConversationHistory.query.filter(
        ConversationHistory.company_id == company_id,
        ConversationHistory.action_type.in_(["sector_changed"]),
    ).order_by(ConversationHistory.created_at.desc()).all()
    routings = ConversationRouting.query.filter_by(
        company_id=company_id
    ).order_by(
        ConversationRouting.conversation_id.asc(),
        ConversationRouting.entered_at.asc(),
    ).all()

    pair_map = {}
    sector_totals = defaultdict(lambda: {
        "sector_id": None,
        "sector_name": None,
        "incoming_handoffs": 0,
        "outgoing_handoffs": 0,
        "unique_received_conversations": set(),
        "unique_sent_conversations": set(),
    })

    total_handoffs = 0

    for event in events:
        from_sector_id = event.from_sector_id
        to_sector_id = event.to_sector_id or event.sector_id

        if not from_sector_id or not to_sector_id:
            continue

        from_sector = sectors_by_id.get(from_sector_id)
        to_sector = sectors_by_id.get(to_sector_id)
        if not from_sector or not to_sector:
            continue

        total_handoffs += 1
        pair_key = (from_sector_id, to_sector_id)

        if pair_key not in pair_map:
            pair_map[pair_key] = {
                "from_sector_id": from_sector_id,
                "from_sector_name": from_sector.name,
                "to_sector_id": to_sector_id,
                "to_sector_name": to_sector.name,
                "count": 0,
                "unique_conversations": set(),
                "last_handoff_at": None,
            }

        pair_map[pair_key]["count"] += 1
        pair_map[pair_key]["unique_conversations"].add(event.conversation_id)
        from core.datetime_utils import serialize_utc
        pair_map[pair_key]["last_handoff_at"] = serialize_utc(event.created_at)

        outgoing = sector_totals[from_sector_id]
        outgoing["sector_id"] = from_sector_id
        outgoing["sector_name"] = from_sector.name
        outgoing["outgoing_handoffs"] += 1
        outgoing["unique_sent_conversations"].add(event.conversation_id)

        incoming = sector_totals[to_sector_id]
        incoming["sector_id"] = to_sector_id
        incoming["sector_name"] = to_sector.name
        incoming["incoming_handoffs"] += 1
        incoming["unique_received_conversations"].add(event.conversation_id)

    routings_by_conversation = defaultdict(list)
    for routing in routings:
        routings_by_conversation[routing.conversation_id].append(routing)

    for routing_items in routings_by_conversation.values():
        for index in range(1, len(routing_items)):
            previous_routing = routing_items[index - 1]
            current_routing = routing_items[index]

            if previous_routing.sector_id == current_routing.sector_id:
                continue

            pair_key = (previous_routing.sector_id, current_routing.sector_id)
            if pair_key not in pair_map:
                continue

            pair_item = pair_map[pair_key]
            duration_seconds = _get_routing_duration_seconds(current_routing, now=now)
            if duration_seconds is None:
                continue

            pair_item.setdefault("destination_duration_seconds", [])
            pair_item["destination_duration_seconds"].append(duration_seconds)

    pairs = []
    for item in pair_map.values():
        destination_durations = item.pop("destination_duration_seconds", [])
        average_destination_seconds = None
        if destination_durations:
            average_destination_seconds = round(
                sum(destination_durations) / len(destination_durations),
                2,
            )

        pairs.append({
            **item,
            "unique_conversations": len(item["unique_conversations"]),
            "average_destination_seconds": average_destination_seconds,
            "average_destination_minutes": _to_minutes(average_destination_seconds),
            "longest_destination_seconds": max(destination_durations) if destination_durations else None,
            "longest_destination_minutes": _to_minutes(max(destination_durations)) if destination_durations else None,
        })

    pairs.sort(
        key=lambda item: (
            -item["count"],
            item["from_sector_name"].lower(),
            item["to_sector_name"].lower(),
        )
    )

    sectors_summary = []
    for sector in sectors:
        summary = sector_totals[sector.id]
        sectors_summary.append({
            "sector_id": sector.id,
            "sector_name": sector.name,
            "incoming_handoffs": summary["incoming_handoffs"],
            "outgoing_handoffs": summary["outgoing_handoffs"],
            "unique_received_conversations": len(summary["unique_received_conversations"]),
            "unique_sent_conversations": len(summary["unique_sent_conversations"]),
            "handoff_balance": summary["incoming_handoffs"] - summary["outgoing_handoffs"],
        })

    sectors_summary.sort(
        key=lambda item: (
            -(item["incoming_handoffs"] + item["outgoing_handoffs"]),
            item["sector_name"].lower(),
        )
    )

    central_outbound_paths = []
    central_inbound_paths = []
    central_summary = {
        "sector_id": central_sector.id if central_sector else None,
        "sector_name": central_sector.name if central_sector else None,
        "outbound_handoffs": 0,
        "inbound_handoffs": 0,
        "unique_outbound_paths": 0,
        "unique_inbound_paths": 0,
        "average_outbound_destination_minutes": None,
        "average_inbound_destination_minutes": None,
    }

    if central_sector:
        central_outbound_paths = [
            item for item in pairs
            if item["from_sector_id"] == central_sector.id
        ]
        central_inbound_paths = [
            item for item in pairs
            if item["to_sector_id"] == central_sector.id
        ]

        central_summary["outbound_handoffs"] = sum(item["count"] for item in central_outbound_paths)
        central_summary["inbound_handoffs"] = sum(item["count"] for item in central_inbound_paths)
        central_summary["unique_outbound_paths"] = len(central_outbound_paths)
        central_summary["unique_inbound_paths"] = len(central_inbound_paths)

        outbound_minutes = [
            item["average_destination_minutes"]
            for item in central_outbound_paths
            if item["average_destination_minutes"] is not None
        ]
        inbound_minutes = [
            item["average_destination_minutes"]
            for item in central_inbound_paths
            if item["average_destination_minutes"] is not None
        ]

        if outbound_minutes:
            central_summary["average_outbound_destination_minutes"] = round(
                sum(outbound_minutes) / len(outbound_minutes),
                1,
            )
        if inbound_minutes:
            central_summary["average_inbound_destination_minutes"] = round(
                sum(inbound_minutes) / len(inbound_minutes),
                1,
            )

    return {
        "summary": {
            "total_handoffs": total_handoffs,
            "unique_paths": len(pairs),
            "top_path": pairs[0] if pairs else None,
        },
        "paths": pairs,
        "sectors": sectors_summary,
        "central": {
            "summary": central_summary,
            "outbound_paths": central_outbound_paths,
            "inbound_paths": central_inbound_paths,
        },
    }
