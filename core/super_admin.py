import os


def get_super_admin_emails():
    raw = os.getenv("SUPER_ADMIN_EMAILS", "admin@admin.com")
    emails = []
    for item in raw.split(","):
        normalized = item.strip().lower()
        if normalized:
            emails.append(normalized)
    return set(emails)


def is_super_admin_user(user):
    if not user:
        return False
    return (user.email or "").strip().lower() in get_super_admin_emails()
