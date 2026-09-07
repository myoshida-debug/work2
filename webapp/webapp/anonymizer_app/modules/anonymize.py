"""Compatibility wrapper for the shared anonymizer package.

The Django app keeps this module so existing imports continue to work, while
all anonymization, restoration, and prompt payload logic lives in the shared
top-level ``anonymizer`` package.
"""

from anonymizer.modules.anonymize import (  # noqa: F401
    AnonymizationResult,
    anonymize_text,
    build_prompt_payload,
    build_result_payload,
    restore_text,
)

