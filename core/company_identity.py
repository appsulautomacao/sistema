import re
import unicodedata

from models import Company


def slugify_company_name(value):
    raw = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        slug = "empresa"
    return slug


def generate_unique_company_slug(company_name, exclude_company_id=None):
    base_slug = slugify_company_name(company_name)
    candidate = base_slug
    suffix = 2

    while True:
        query = Company.query.filter_by(slug=candidate)
        if exclude_company_id is not None:
            query = query.filter(Company.id != exclude_company_id)
        if not query.first():
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def normalize_brand_color(value):
    color = (value or "").strip()
    if not color:
        return "#0D6EFD"

    if not color.startswith("#"):
        color = f"#{color}"

    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color.upper()

    return None
