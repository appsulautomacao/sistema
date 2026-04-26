import os
import re
from collections import Counter

from models import Company


RAG_BASE_DIR = "files_rag"


def _normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _tokenize(value):
    normalized = _normalize_text(value)
    return re.findall(r"[a-zA-Z0-9À-ÿ]+", normalized)


def _resolve_company_rag_path(company):
    if not company or not company.rag_document_path:
        return None

    configured_path = company.rag_document_path.strip()
    if not configured_path:
        return None

    if os.path.isabs(configured_path):
        return configured_path if os.path.isfile(configured_path) else None

    relative_candidate = os.path.normpath(os.path.join(os.getcwd(), configured_path))
    if os.path.isfile(relative_candidate):
        return relative_candidate

    rag_candidate = os.path.normpath(os.path.join(os.getcwd(), RAG_BASE_DIR, configured_path))
    if os.path.isfile(rag_candidate):
        return rag_candidate

    return None


def get_company_rag_document(company_id):
    company = Company.query.get(company_id)
    if not company:
        return None

    full_path = _resolve_company_rag_path(company)
    if not full_path:
        return None

    try:
        content = open(full_path, "r", encoding="utf-8").read()
    except UnicodeDecodeError:
        content = open(full_path, "r", encoding="latin-1").read()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "configured_path": company.rag_document_path,
        "full_path": full_path,
        "content": content,
    }


def chunk_rag_text(text, max_chars=700):
    lines = [line.strip() for line in str(text or "").splitlines()]
    chunks = []
    current = []
    current_size = 0

    for line in lines:
        if not line:
            if current:
                block = "\n".join(current).strip()
                if block:
                    chunks.append(block)
                current = []
                current_size = 0
            continue

        if current_size + len(line) > max_chars and current:
            block = "\n".join(current).strip()
            if block:
                chunks.append(block)
            current = [line]
            current_size = len(line)
            continue

        current.append(line)
        current_size += len(line) + 1

    if current:
        block = "\n".join(current).strip()
        if block:
            chunks.append(block)

    return chunks


def score_rag_chunk(query, chunk):
    query_tokens = _tokenize(query)
    chunk_tokens = _tokenize(chunk)

    if not query_tokens or not chunk_tokens:
        return 0

    query_counter = Counter(query_tokens)
    chunk_counter = Counter(chunk_tokens)

    score = 0
    for token, weight in query_counter.items():
        score += min(chunk_counter.get(token, 0), 3) * weight

    normalized_query = _normalize_text(query)
    normalized_chunk = _normalize_text(chunk)
    if normalized_query and normalized_query in normalized_chunk:
        score += 5

    return score


def search_company_rag(company_id, query, limit=4):
    rag_document = get_company_rag_document(company_id)
    if not rag_document:
        return {
            "configured_path": None,
            "results": [],
        }

    chunks = chunk_rag_text(rag_document["content"])
    scored = []

    for index, chunk in enumerate(chunks, 1):
        score = score_rag_chunk(query, chunk)
        if score > 0:
            scored.append({
                "index": index,
                "score": score,
                "content": chunk,
            })

    scored.sort(key=lambda item: item["score"], reverse=True)

    return {
        "configured_path": rag_document["configured_path"],
        "results": scored[:limit],
    }
