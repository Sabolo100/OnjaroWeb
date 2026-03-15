"""Research Extractor - AI-driven structured data extraction from raw findings."""

import json
import logging
from typing import List, Type

from pydantic import BaseModel, ValidationError

from research.config_loader import ProjectConfig
from research.connectors.connector_factory import get_connector
from research.models import RawFinding, ExtractionCandidate
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.extractor")


class ResearchExtractor:
    """Extracts structured data from raw findings using AI."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()
        self._connector = None

    def _get_connector(self):
        if self._connector is None:
            self._connector = get_connector()
        return self._connector

    def extract_from_findings(self, run_id: str, item: dict,
                              findings: List[RawFinding]) -> List[ExtractionCandidate]:
        """Extract structured data from raw findings for a research item."""
        item_id = item.get("id", "unknown")
        schema_name = item.get("schema_name", "article")

        # Load extraction prompt templates
        extract_prompts = self.config.load_extract_prompts()
        system_prompt = extract_prompts.get("extract_system_prompt", "")
        prompt_template = extract_prompts.get("extract_prompt_template", "")

        # Load Pydantic schema for validation
        schema_cls = self.config.load_schema(schema_name)

        candidates = []
        connector = self._get_connector()

        for finding in findings:
            if not finding.finding_id:
                continue

            try:
                extracted = self._extract_single(
                    finding, system_prompt, prompt_template, connector
                )

                if not extracted:
                    continue

                # Calculate confidence score
                confidence = self._calculate_confidence(extracted, schema_cls, finding)

                # Validate against schema if available
                status = "pending"
                rejection_reason = None
                if schema_cls:
                    try:
                        schema_cls(**extracted)
                    except ValidationError as ve:
                        min_confidence = item.get("min_confidence", 0.6)
                        if confidence < min_confidence:
                            status = "rejected"
                            rejection_reason = f"Schema validation failed: {ve.error_count()} errors"
                            logger.info("Rejected finding %d: %s", finding.finding_id, rejection_reason)

                # Save to DB
                candidate_id = self.repo.save_extraction_candidate(
                    run_id=run_id,
                    finding_id=finding.finding_id,
                    item_id=item_id,
                    extracted_data=extracted,
                    confidence=confidence,
                    status=status,
                )

                if status == "rejected":
                    self.repo.update_candidate_status(candidate_id, status, rejection_reason)
                    continue

                candidate = ExtractionCandidate(
                    candidate_id=candidate_id,
                    finding_id=finding.finding_id,
                    item_id=item_id,
                    extracted_data=extracted,
                    confidence=confidence,
                    status=status,
                )
                candidates.append(candidate)

            except Exception as e:
                logger.error("Extraction failed for finding %s: %s",
                             finding.finding_id, e)
                continue

        logger.info("Item '%s': extracted %d candidates from %d findings",
                    item_id, len(candidates), len(findings))
        return candidates

    def _extract_single(self, finding: RawFinding, system_prompt: str,
                        prompt_template: str, connector) -> dict:
        """Extract structured data from a single raw finding."""
        content = finding.content or finding.snippet or ""
        if not content:
            return {}

        # Build extraction prompt
        prompt = prompt_template.format(
            source_url=finding.url or "",
            title=finding.title or "",
            content=content[:3000],  # Limit content length
        ) if prompt_template else f"Extract article data from:\n{content[:3000]}"

        try:
            response = connector._get_client().chat.completions.create(
                model=connector.model,
                messages=[
                    {"role": "system", "content": system_prompt or "Extract structured data as JSON."},
                    {"role": "user", "content": prompt},
                ],
            )

            result_text = response.choices[0].message.content if response.choices else ""
            return self._parse_json_response(result_text)

        except Exception as e:
            logger.error("AI extraction call failed: %s", e)
            return {}

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from AI response text."""
        cleaned = text.strip()

        # Strip markdown code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            inner = "\n".join(lines[1:])
            if "```" in inner:
                inner = inner[:inner.rfind("```")]
            cleaned = inner.strip()

        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            pass

        # Try to find JSON object in text
        import re
        json_match = re.search(r'\{[\s\S]*\}', cleaned)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, TypeError):
                pass

        return {}

    def _calculate_confidence(self, extracted: dict, schema_cls: Type[BaseModel],
                              finding: RawFinding) -> float:
        """Calculate a confidence score for the extraction."""
        score = 0.5  # Base score

        if not extracted:
            return 0.0

        # Schema completeness (if schema available)
        if schema_cls:
            try:
                fields = schema_cls.model_fields
                required_fields = [k for k, v in fields.items()
                                   if v.is_required()]
                filled_required = sum(1 for f in required_fields
                                      if f in extracted and extracted[f])
                if required_fields:
                    completeness = filled_required / len(required_fields)
                    score = 0.3 + (completeness * 0.5)
            except Exception:
                pass

        # Content length bonus
        content = extracted.get("content", [])
        if isinstance(content, list) and len(content) >= 3:
            score += 0.1
        elif isinstance(content, str) and len(content) >= 200:
            score += 0.1

        # Title quality
        title = extracted.get("title", "")
        if title and len(title) >= 10:
            score += 0.05

        # Source trust bonus
        if finding.source_domain:
            score += 0.05

        return min(1.0, round(score, 2))
