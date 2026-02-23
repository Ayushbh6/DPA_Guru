from __future__ import annotations

from kb_pipeline.repository import KbRepository


def test_vector_literal_and_parse_roundtrip() -> None:
    vec = [0.1, 0.2, -0.3]
    literal = KbRepository._vector_literal(vec)
    assert literal.startswith("[") and literal.endswith("]")
    parsed = KbRepository._parse_vector_text(literal)
    assert parsed is not None
    assert len(parsed) == len(vec)
    for a, b in zip(parsed, vec):
        assert abs(a - b) < 1e-6
