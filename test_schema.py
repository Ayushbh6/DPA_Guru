import json
from google import genai
from google.genai import types

client = genai.Client()

schema = {
  "type": "object",
  "properties": {
    "check_id": {"type": "string"},
    "status": {"type": "string", "enum": ["COMPLIANT", "NON_COMPLIANT", "PARTIAL", "UNKNOWN"]},
    "risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
    "confidence": {"type": "number"},
    "evidence_quotes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "page": {"type": "integer"},
          "quote": {"type": "string"}
        },
        "required": ["page", "quote"]
      }
    },
    "kb_citations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_id": {"type": "string"},
          "source_ref": {"type": "string"},
          "source_excerpt": {"type": "string"}
        },
        "required": ["source_id", "source_ref", "source_excerpt"]
      }
    },
    "missing_elements": {
      "type": "array",
      "items": {"type": "string"}
    },
    "risk_rationale": {"type": "string"},
    "abstained": {"type": "boolean"},
    "abstain_reason": {"type": "string"}
  },
  "required": ["check_id", "status", "risk", "confidence", "risk_rationale"]
}

try:
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema,
    )
    print("Schema accepted by GenerateContentConfig!")
except Exception as e:
    print(f"Error: {e}")
