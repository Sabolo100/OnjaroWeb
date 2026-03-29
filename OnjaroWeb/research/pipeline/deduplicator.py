"""Research Deduplicator - detect duplicates and changes."""

import logging
import re
from difflib import SequenceMatcher
from typing import List, Tuple

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate
from research.supabase_client import get_supabase_client
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.deduplicator")

# Hungarian legal form suffixes (order: longest first to strip greedily)
_LEGAL_SUFFIXES = [
    "korlátolt felelősségű társaság",
    "korlatolt felelossegu tarsasag",
    "részvénytársaság",
    "resvenytarsasag",
    "betéti társaság",
    "beteti tarsasag",
    "közkereseti társaság",
    "kozkereseti tarsasag",
    "egyéni vállalkozó",
    "egyeni vallalkozo",
    "nonprofit kft",
    "kft.",
    "kft",
    "zrt.",
    "zrt",
    "nyrt.",
    "nyrt",
    "bt.",
    "bt",
    "kkt.",
    "kkt",
    "ev.",
    "ev",
    "ltd.",
    "ltd",
    "gmbh",
    "s.r.o.",
    "s.r.o",
    "a.s.",
    "a.s",
    "llc",
    "inc.",
    "inc",
    "corp.",
    "corp",
    "plc",
    "se",
    "ag",
    "s.a.",
]

# Common Hungarian/English activity descriptor words that appear at the end
# of company names and should be stripped for dedup comparison.
# ORDER MATTERS: longest first to avoid partial matches.
_ACTIVITY_SUFFIXES = [
    # Compound facility/building type names (must be before shorter parts)
    "logisztikai és ipari park",
    "logisztikai centrum",
    "logisztikai központ",
    "logisztikai park",
    "ipari és logisztikai park",
    "ipari park",
    "business park",
    "business center",
    "business centre",
    "science park",
    "irodapark",
    "irodaház",
    "irodaközpont",
    "office park",
    "office center",
    "office centre",
    "bevásárlóközpont",
    "pláza",
    "plaza",
    "center",
    "centre",
    # Company activity descriptors (original list, longest first)
    "ingatlankezelő és szolgáltató",
    "ingatlankezelő és üzemeltető",
    "ingatlankezelő",
    "ingatlanhasznosító",
    "ingatlanfejlesztő",
    "ingatlanforgalmazó",
    "ingatlan management",
    "ingatlan menedzsment",
    "ingatlangazdálkodási",
    "üzemeltető és szolgáltató",
    "üzemeltető",
    "uzemelteto",
    "szolgáltató",
    "szolgaltato",
    "tanácsadó",
    "tanacsado",
    "property management",
    "facility management",
    "asset management",
    "facility services",
    "property services",
    "real estate",
    "management",
    "menedzsment",
    "consulting",
    "services",
    "solutions",
    "magyarország",
    "magyarorszag",
    "hungary",
    "budapest",
    "group",
    "csoport",
    "holding",
    "international",
    # Single-word generic suffixes (last, as catch-all)
    "park",
]


def normalize_company_name(name: str) -> str:
    """Normalize a company name for deduplication.

    Strips legal forms, activity descriptions, and normalizes whitespace/case.
    The result is the "core" name — the part that actually identifies the company.

    Examples:
        "First Facility Üzemeltető Kft." -> "first facility"
        "B+N Referencia Ingatlankezelő Zrt" -> "b+n referencia"
        "CBRE Kft" -> "cbre"
        "Jraft FM Szolgáltató Kft." -> "jraft fm"
    """
    if not name:
        return ""

    text = name.strip().lower()

    # Remove content in parentheses (often aliases or legal notes)
    text = re.sub(r'\([^)]*\)', '', text)

    # Strip legal suffixes first (they can appear after activity words)
    for suffix in _LEGAL_SUFFIXES:
        if text.endswith(suffix):
            text = text[:-len(suffix)].rstrip(" .,;-–")
            break  # only one legal form

    # Strip activity descriptor suffixes (can be multiple, strip iteratively).
    # Safety: only strip if the suffix is at a word boundary (preceded by a space
    # or start-of-string) and the remaining core is at least 2 chars.
    changed = True
    while changed:
        changed = False
        for suffix in _ACTIVITY_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                # Check word boundary: the char before the suffix must be a space
                prefix_end = len(text) - len(suffix)
                if prefix_end > 0 and text[prefix_end - 1] != ' ':
                    continue  # suffix is part of a compound word, skip
                candidate_core = text[:prefix_end].rstrip(" .,;-–")
                # Don't strip if it would leave us with less than 2 meaningful chars
                if len(candidate_core) >= 2:
                    text = candidate_core
                    changed = True
                    break  # restart from longest

    # Normalize unicode and whitespace
    text = re.sub(r'[.\-–—/\\]', ' ', text)  # punctuation to space
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def _names_match(name_a: str, name_b: str, threshold: float) -> Tuple[bool, float]:
    """Compare two entity names with smart matching.

    Returns (is_match, similarity_score).
    """
    if not name_a or not name_b:
        return False, 0.0

    # Exact match on normalized
    if name_a == name_b:
        return True, 1.0

    # Prefix match: if the shorter is entirely the start of the longer
    # and the shorter has at least 3 characters
    shorter, longer = (name_a, name_b) if len(name_a) <= len(name_b) else (name_b, name_a)
    if len(shorter) >= 3 and longer.startswith(shorter):
        return True, 0.95

    # Token-based matching: check if all tokens of the shorter name
    # appear in the longer name (handles word reordering).
    # Require at least 2 meaningful tokens to match — single-token subsets
    # cause false positives on generic type words.
    tokens_a = set(name_a.split())
    tokens_b = set(name_b.split())
    if tokens_a and tokens_b:
        shorter_tokens, longer_tokens = (
            (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b)
            else (tokens_b, tokens_a)
        )
        if shorter_tokens.issubset(longer_tokens) and len(shorter_tokens) >= 2:
            return True, 0.92

    # SequenceMatcher fallback
    similarity = SequenceMatcher(None, name_a, name_b).ratio()
    if similarity >= threshold:
        return True, similarity

    return False, similarity


class ResearchDeduplicator:
    """Checks extracted candidates against existing records for duplicates."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()

    def dedupe(self, run_id: str, item: dict,
               candidates: List[ExtractionCandidate]) -> Tuple[List[ExtractionCandidate], int]:
        """Check candidates for duplicates.

        Performs two-phase dedup:
        1. Intra-batch: remove duplicates within the current candidate set
        2. Against DB: check remaining candidates against existing Supabase records

        Returns:
            (to_persist, skipped_count)
        """
        target_table = item.get("target_table", "articles")
        policies = self.config.load_policies()
        dedupe_policy = policies.dedupe
        mappings = self.config.load_mappings()
        table_config = mappings.get(target_table, {})

        db_keys = table_config.get("required_fields", dedupe_policy.unique_keys)
        threshold = dedupe_policy.similarity_threshold
        use_company_normalization = (target_table == "companies")

        # Phase 1: Intra-batch dedup
        candidates, intra_skipped = self._intra_batch_dedupe(
            run_id, candidates, db_keys, threshold, use_company_normalization
        )

        # Fetch existing records from Supabase
        existing = self._fetch_existing(target_table, db_keys)

        # Pre-compute normalized names for existing records
        existing_normalized = []
        for record in existing:
            norm = {}
            for key in db_keys:
                raw = str(record.get(key, ""))
                if use_company_normalization and key == "name":
                    norm[key] = normalize_company_name(raw)
                else:
                    norm[key] = raw.lower().strip()
            existing_normalized.append((record, norm))

        # Phase 2: Against existing DB records
        to_persist = []
        db_skipped = 0

        for candidate in candidates:
            action, reason = self._check_candidate(
                candidate, existing_normalized, threshold,
                db_keys, use_company_normalization
            )

            if action == "new":
                to_persist.append(candidate)
            elif action == "duplicate":
                db_skipped += 1
                self.repo.update_candidate_status(
                    candidate.candidate_id, "skipped", reason
                )
                self.repo.save_persistence_result(
                    run_id, candidate.candidate_id, "skipped",
                    target_table=target_table, reason=reason,
                )
                logger.debug("Skipped duplicate: %s", reason)
            elif action == "update_candidate":
                to_persist.append(candidate)
                candidate.extracted_data["_update_existing_id"] = reason
            elif action == "ambiguous":
                self.repo.add_to_review(
                    run_id, candidate.candidate_id,
                    candidate.confidence, f"Ambiguous duplicate: {reason}"
                )
                self.repo.update_candidate_status(
                    candidate.candidate_id, "needs_review", reason
                )
                db_skipped += 1

        total_skipped = intra_skipped + db_skipped
        logger.info("Dedupe: %d to persist, %d skipped (intra-batch: %d, vs DB: %d) out of %d total",
                    len(to_persist), total_skipped, intra_skipped, db_skipped,
                    len(to_persist) + total_skipped)
        return to_persist, total_skipped

    def _intra_batch_dedupe(
        self, run_id: str,
        candidates: List[ExtractionCandidate],
        db_keys: list, threshold: float,
        use_company_normalization: bool,
    ) -> Tuple[List[ExtractionCandidate], int]:
        """Remove duplicates within the current batch of candidates."""
        if len(candidates) <= 1:
            return candidates, 0

        unique = []
        seen_normalized = []  # list of (candidate, {key: normalized_value})
        skipped = 0

        for candidate in candidates:
            data = candidate.extracted_data
            candidate_norms = {}
            for key in db_keys:
                raw = str(data.get(key, ""))
                if use_company_normalization and key == "name":
                    candidate_norms[key] = normalize_company_name(raw)
                else:
                    candidate_norms[key] = raw.lower().strip()

            is_dup = False
            for prev_candidate, prev_norms in seen_normalized:
                for key in db_keys:
                    cand_val = candidate_norms.get(key, "")
                    prev_val = prev_norms.get(key, "")
                    if cand_val and prev_val:
                        matched, sim = _names_match(cand_val, prev_val, threshold)
                        if matched:
                            is_dup = True
                            raw_name = data.get(key, "?")
                            prev_raw = prev_candidate.extracted_data.get(key, "?")
                            logger.info(
                                "Intra-batch duplicate: '%s' matches '%s' (sim=%.2f)",
                                raw_name, prev_raw, sim
                            )
                            break
                if is_dup:
                    break

            if is_dup:
                skipped += 1
                self.repo.update_candidate_status(
                    candidate.candidate_id, "skipped",
                    "Intra-batch duplicate"
                )
                self.repo.save_persistence_result(
                    run_id, candidate.candidate_id, "skipped",
                    target_table="companies",
                    reason="Intra-batch duplicate",
                )
            else:
                unique.append(candidate)
                seen_normalized.append((candidate, candidate_norms))

        if skipped > 0:
            logger.info("Intra-batch dedupe removed %d duplicates from %d candidates",
                        skipped, len(candidates))
        return unique, skipped

    def _fetch_existing(self, table: str, keys: list) -> list:
        """Fetch existing records from Supabase for deduplication."""
        client = get_supabase_client()
        if not client:
            logger.warning("No Supabase client, skipping dedupe against existing records")
            return []

        try:
            select_fields = ",".join(["id"] + keys)
            response = client.table(table).select(select_fields).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error("Failed to fetch existing records from '%s': %s", table, e)
            return []

    def _check_candidate(self, candidate: ExtractionCandidate,
                         existing_normalized: list,
                         threshold: float,
                         db_keys: list,
                         use_company_normalization: bool) -> Tuple[str, str]:
        """Check a single candidate against existing DB records.

        Returns: (action, reason)
            action: "new", "duplicate", "update_candidate", "ambiguous"
        """
        data = candidate.extracted_data

        if not existing_normalized:
            return "new", ""

        # Normalize candidate fields
        candidate_norms = {}
        for key in db_keys:
            raw = str(data.get(key, ""))
            if use_company_normalization and key == "name":
                candidate_norms[key] = normalize_company_name(raw)
            else:
                candidate_norms[key] = raw.lower().strip()

        for record, record_norms in existing_normalized:
            for key in db_keys:
                cand_val = candidate_norms.get(key, "")
                rec_val = record_norms.get(key, "")

                if not cand_val or not rec_val:
                    continue

                matched, similarity = _names_match(cand_val, rec_val, threshold)

                if matched:
                    return "duplicate", (
                        f"Match on normalized '{cand_val}' ≈ '{rec_val}' "
                        f"(sim={similarity:.2f}) with id={record.get('id')}"
                    )

                # Ambiguous zone: close but not certain
                ambiguous_threshold = threshold * 0.85
                if similarity >= ambiguous_threshold:
                    return "ambiguous", (
                        f"Near match on normalized '{cand_val}' ~ '{rec_val}' "
                        f"(sim={similarity:.2f}) with id={record.get('id')}"
                    )

        return "new", ""
