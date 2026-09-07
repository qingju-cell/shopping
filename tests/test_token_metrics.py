from app.metrics import extract_llm_token_usage


class FakeLLMResponse:
    usage_metadata = {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
    }


def test_extracts_real_usage_metadata():
    assert extract_llm_token_usage(FakeLLMResponse()) == {
        "input": 120,
        "output": 45,
        "total": 165,
    }


def test_does_not_estimate_when_usage_is_missing():
    assert extract_llm_token_usage(object()) is None