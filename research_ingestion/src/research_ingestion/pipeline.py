from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .classify import ZeroCostOmniRoute, deterministic_classify
from .connectors import collect_all
from .emailer import send_digest
from .drive import upload_accepted_pdfs
from .http import PublicHttpClient
from .models import AcceptedItem, Candidate
from .pdf import download_public_pdf, extract_pdf_text
from .storage import Storage
from .redact import redact_sensitive


def _merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for item in candidates:
        key = item.identity()
        if not key:
            continue
        previous = merged.get(key)
        if previous is None:
            merged[key] = item
            continue
        if len(item.abstract) > len(previous.abstract):
            previous.abstract = item.abstract
        previous.pdf_url = previous.pdf_url or item.pdf_url
        previous.doi = previous.doi or item.doi
        previous.authors = previous.authors or item.authors
        previous.is_open_access = previous.is_open_access if previous.is_open_access is not None else item.is_open_access
        previous.license = previous.license or item.license
        previous.metadata.update({k: v for k, v in item.metadata.items() if v is not None})
    return list(merged.values())


def _rejected_record(candidate: Candidate, stage: str, reason: str, **details: Any) -> dict[str, Any]:
    return {
        "rejection_stage": stage,
        "rejection_reason": reason,
        "source": candidate.source,
        "title": candidate.title,
        "abstract": candidate.abstract,
        "canonical_url": candidate.canonical_url,
        "document_type": candidate.document_type,
        "doi": candidate.doi,
        "stable_id": candidate.stable_id,
        "published_at": candidate.published_at,
        "is_open_access": candidate.is_open_access,
        **details,
    }


def run_day(project_root: Path, config: dict[str, Any], day: dt.date, *, send_email: bool,
            sync_drive: bool = True, force: bool = False) -> dict[str, Any]:
    storage = Storage(project_root)
    day_text = day.isoformat()
    existing = storage.data / "accepted" / f"{day_text}.json"
    if existing.exists() and not force:
        storage.close()
        return {"date": day_text, "status": "already_completed", "accepted_manifest": str(existing)}

    client = PublicHttpClient()
    ai = ZeroCostOmniRoute(config["ai"])
    warnings: list[str] = []
    source_counts: dict[str, int] = {}
    rejection_counts = {"duplicate": 0, "deterministic_quality": 0, "deep_review_cap": 0, "ai_quality": 0}
    accepted: list[AcceptedItem] = []
    rejected: list[dict[str, Any]] = []
    try:
        source_results = collect_all(client, config, day)
        candidates: list[Candidate] = []
        for result in source_results:
            source_counts[result.source] = len(result.candidates)
            candidates.extend(result.candidates)
            warnings.extend(result.warnings)
        candidates = _merge_candidates(candidates)

        scored_candidates: list[tuple[int, Candidate, list[str]]] = []
        for candidate in candidates:
            if storage.contains(candidate) and not force:
                rejection_counts["duplicate"] += 1
                rejected.append(_rejected_record(
                    candidate, "duplicate", "Previously accepted item already exists in the catalogue."
                ))
                continue
            deterministic_score, deterministic_topics = deterministic_classify(candidate)
            if deterministic_score < config["deterministic_min_score"]:
                rejection_counts["deterministic_quality"] += 1
                rejected.append(_rejected_record(
                    candidate,
                    "deterministic_quality",
                    f"Deterministic score {deterministic_score} is below minimum "
                    f"{config['deterministic_min_score']}.",
                    deterministic_score=deterministic_score,
                    deterministic_topics=deterministic_topics,
                ))
                continue
            scored_candidates.append((deterministic_score, candidate, deterministic_topics))

        scored_candidates.sort(key=lambda row: (-row[0], row[1].title.lower()))
        deep_review_cap = config.get("max_candidates_for_deep_review", config["ai"]["max_calls_per_run"])
        rejection_counts["deep_review_cap"] = max(0, len(scored_candidates) - deep_review_cap)
        for deterministic_score, candidate, deterministic_topics in scored_candidates[deep_review_cap:]:
            rejected.append(_rejected_record(
                candidate,
                "deep_review_cap",
                f"Ranked outside the top {deep_review_cap} candidates selected for deep review.",
                deterministic_score=deterministic_score,
                deterministic_topics=deterministic_topics,
            ))

        for deterministic_score, candidate, deterministic_topics in scored_candidates[:deep_review_cap]:

            pdf_content, resolved_pdf_url, download_status = download_public_pdf(
                client, candidate, config["download_max_bytes"]
            )
            extracted = ""
            if pdf_content:
                try:
                    extracted = extract_pdf_text(pdf_content)
                except Exception as exc:
                    warnings.append(f"PDF extraction failed for {candidate.canonical_url}: {redact_sensitive(exc)}")
                    download_status = "downloaded_text_extraction_failed"

            ai_result = ai.classify(candidate, extracted or candidate.abstract or candidate.title)
            if ai_result.warning and ai_result.warning not in warnings:
                warnings.append(ai_result.warning)

            if ai_result.status == "classified":
                relevance = ai_result.relevance_score or 0.0
                is_accepted = bool(ai_result.accepted) and relevance >= config["quality_threshold"]
                topics = ai_result.topics or deterministic_topics
                reason = ai_result.reason
            else:
                relevance = min(0.99, 0.50 + 0.06 * deterministic_score)
                is_accepted = relevance >= config["quality_threshold"]
                topics = deterministic_topics
                reason = f"Deterministic fallback score {deterministic_score}; AI status: {ai_result.status}"
            if not is_accepted:
                rejection_counts["ai_quality"] += 1
                rejected.append(_rejected_record(
                    candidate,
                    "ai_quality",
                    reason or "AI classification did not meet the acceptance rules.",
                    deterministic_score=deterministic_score,
                    deterministic_topics=deterministic_topics,
                    ai_status=ai_result.status,
                    ai_accepted=ai_result.accepted,
                    relevance_score=relevance,
                    quality_threshold=config["quality_threshold"],
                    topics=topics,
                    download_status=download_status,
                ))
                continue

            # DOI resolver calls are deliberately acceptance-gated: rejected
            # candidate DOIs are never disclosed to OpenAlex or Unpaywall.
            if not pdf_content and config.get("public_pdf_resolution", {}).get("enabled"):
                resolved_content, oa_pdf_url, oa_download_status = download_public_pdf(
                    client,
                    candidate,
                    config["download_max_bytes"],
                    oa_config=config["public_pdf_resolution"],
                    resolver_only=True,
                )
                download_status = oa_download_status
                if resolved_content:
                    pdf_content = resolved_content
                    resolved_pdf_url = oa_pdf_url
                    try:
                        extracted = extract_pdf_text(pdf_content)
                    except Exception as exc:
                        warnings.append(
                            f"PDF extraction failed for {candidate.canonical_url}: {redact_sensitive(exc)}"
                        )
                        download_status = "downloaded_text_extraction_failed"

            local_pdf_path = None
            content_hash = None
            if pdf_content:
                local_pdf_path, content_hash = storage.save_pdf(day_text, candidate, pdf_content)
            item = AcceptedItem(
                source=candidate.source,
                title=candidate.title,
                abstract_or_title=candidate.abstract if candidate.document_type == "academic_paper" and candidate.abstract else candidate.title,
                document_type=candidate.document_type,
                canonical_url=candidate.canonical_url,
                pdf_url=resolved_pdf_url or candidate.pdf_url,
                local_pdf_path=local_pdf_path,
                doi=candidate.doi,
                stable_id=candidate.stable_id,
                authors=candidate.authors,
                published_at=candidate.published_at,
                updated_at=candidate.updated_at,
                retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                is_open_access=candidate.is_open_access,
                license=candidate.license,
                topics=topics,
                relevance_score=relevance,
                relevance_reason=reason,
                ai_status=ai_result.status,
                content_sha256=content_hash,
                pdf_text_chars=len(extracted),
                download_status=download_status,
            )
            storage.persist_item(candidate, item)
            accepted.append(item)

        accepted_path, reading_path = storage.write_manifests(day_text, accepted)
        rejected_path = storage.write_rejected_manifest(day_text, rejected)
        drive_status: dict[str, Any] | str = "disabled"
        if sync_drive and config.get("drive", {}).get("enabled"):
            try:
                drive_status = upload_accepted_pdfs(day_text, accepted, config["drive"])
            except Exception as exc:
                drive_status = {"status": "failed", "error": redact_sensitive(exc)}
                warnings.append(f"Google Drive upload failed: {redact_sensitive(exc)}")
        email_status = "disabled"
        if send_email:
            try:
                email_status = send_digest(
                    day_text, accepted, config["email_recipients"], config["email_top_n"], warnings,
                    config.get("email"),
                )
            except Exception as exc:
                email_status = f"failed: {redact_sensitive(exc)}"
                warnings.append(f"Email delivery failed: {redact_sensitive(exc)}")

        report = {
            "date": day_text,
            "status": "completed",
            "source_candidate_counts": source_counts,
            "deduplicated_candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "rejection_counts": rejection_counts,
            "pdf_count": sum(1 for item in accepted if item.local_pdf_path),
            "ai_calls": ai.calls,
            "ai_estimated_input_tokens": ai.estimated_input_tokens,
            "ai_stopped_reason": ai.stopped_reason,
            "email_status": email_status,
            "drive_status": drive_status,
            "accepted_manifest": str(accepted_path),
            "reading_manifest": str(reading_path),
            "rejected_manifest": str(rejected_path),
            "warnings": warnings,
        }
        run_path = storage.write_run_report(day_text, report)
        report["run_report"] = str(run_path)
        return report
    finally:
        client.close()
        storage.close()
