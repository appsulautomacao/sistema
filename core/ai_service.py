import json
import os
from dataclasses import dataclass
from importlib import metadata

from models import CompanySettings
from models import Sector

DEFAULT_FALLBACK_LABEL = "Central"


@dataclass
class SectorClassificationResult:
    sector_name: str
    provider: str
    model_name: str = ""
    used_fallback: bool = False
    raw_output: str = ""
    reason: str = ""


def _normalize_label(value):
    normalized = " ".join(str(value or "").strip().lower().split())
    return normalized


def get_company_ai_sectors(company_id, include_central=False):
    query = Sector.query.filter_by(
        company_id=company_id,
        is_active=True,
    ).order_by(Sector.name.asc())

    sectors = query.all()
    if not include_central:
        sectors = [sector for sector in sectors if not sector.is_central]
    return sectors


def _pick_fallback_sector_name(company_id):
    sectors = get_company_ai_sectors(company_id, include_central=False)
    if sectors:
        return sectors[0].name

    central_sector = Sector.query.filter_by(
        company_id=company_id,
        is_central=True,
        is_active=True,
    ).order_by(Sector.id.asc()).first()

    if central_sector:
        return central_sector.name

    return DEFAULT_FALLBACK_LABEL


def _build_sector_lookup(company_id):
    sectors = get_company_ai_sectors(company_id, include_central=False)
    return {
        _normalize_label(sector.name): sector.name
        for sector in sectors
    }


def _extract_sector_name_from_response(content, lookup):
    normalized = _normalize_label(content)
    if normalized in lookup:
        return lookup[normalized]

    for piece in [normalized, normalized.replace('"', ""), normalized.replace("'", "")]:
        if piece in lookup:
            return lookup[piece]

    try:
        payload = json.loads(content)
        for candidate_key in ("sector", "setor", "category", "categoria"):
            candidate_value = payload.get(candidate_key)
            normalized_candidate = _normalize_label(candidate_value)
            if normalized_candidate in lookup:
                return lookup[normalized_candidate]
    except Exception:
        pass

    return None


def _classify_with_modern_openai(api_key, model, system_prompt, user_prompt):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content or ""


def _classify_with_legacy_openai(api_key, model, system_prompt, user_prompt):
    import openai

    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message["content"] or ""


def classify_text_to_company_sector(company_id, text):
    cleaned_text = " ".join(str(text or "").strip().split())
    fallback_name = _pick_fallback_sector_name(company_id)

    if len(cleaned_text) < 5:
        return SectorClassificationResult(
            sector_name=fallback_name,
            provider="fallback",
            used_fallback=True,
            reason="input_too_short",
        )

    sector_lookup = _build_sector_lookup(company_id)
    available_sector_names = list(sector_lookup.values())
    if not available_sector_names:
        return SectorClassificationResult(
            sector_name=fallback_name,
            provider="fallback",
            used_fallback=True,
            reason="no_company_sectors",
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return SectorClassificationResult(
            sector_name=fallback_name,
            provider="fallback",
            used_fallback=True,
            reason="missing_openai_api_key",
        )

    settings = CompanySettings.query.filter_by(company_id=company_id).first()
    model = (
        (settings.ai_classifier_model if settings and settings.ai_classifier_model else None)
        or os.getenv("OPENAI_CLASSIFIER_MODEL")
        or "gpt-4o-mini"
    )
    sector_options = "\n".join(f"- {name}" for name in available_sector_names)
    custom_prompt = (settings.ai_classifier_prompt if settings and settings.ai_classifier_prompt else "").strip()
    system_prompt = custom_prompt or (
        "Voce classifica mensagens de clientes para setores de atendimento. "
        "Responda somente com o nome exato de um dos setores permitidos."
    )
    user_prompt = (
        "Classifique a mensagem abaixo em apenas um setor da empresa.\n\n"
        "Setores permitidos:\n"
        f"{sector_options}\n\n"
        "Mensagem do cliente:\n"
        f"{cleaned_text}\n\n"
        "Responda apenas com o nome exato do setor."
    )

    last_error = None
    raw_output = ""

    try:
        raw_output = str(
            _classify_with_modern_openai(api_key, model, system_prompt, user_prompt) or ""
        ).strip()
        resolved_sector_name = _extract_sector_name_from_response(raw_output, sector_lookup)
        if resolved_sector_name:
            return SectorClassificationResult(
                sector_name=resolved_sector_name,
                provider="openai-modern",
                model_name=model,
                raw_output=raw_output,
            )
        last_error = "invalid_model_output"
    except Exception as exc:
        last_error = str(exc)

    try:
        openai_version = metadata.version("openai")
    except metadata.PackageNotFoundError:
        openai_version = ""

    if openai_version.startswith("0."):
        try:
            raw_output = str(
                _classify_with_legacy_openai(api_key, model, system_prompt, user_prompt) or ""
            ).strip()
            resolved_sector_name = _extract_sector_name_from_response(raw_output, sector_lookup)
            if resolved_sector_name:
                return SectorClassificationResult(
                    sector_name=resolved_sector_name,
                    provider="openai-legacy",
                    model_name=model,
                    raw_output=raw_output,
                )
            last_error = "invalid_model_output"
        except Exception as exc:
            last_error = str(exc)

    return SectorClassificationResult(
        sector_name=fallback_name,
        provider="fallback",
        model_name=model,
        used_fallback=True,
        raw_output=raw_output,
        reason=last_error or "invalid_model_output",
    )
