from pair import redact

SECRETS = [
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_" + "a" * 36,
    "xoxb-1234567890-abc",
]


def test_every_pattern_is_found_and_masked():
    for secret in SECRETS:
        text = f"line before\n{secret}\nline after"
        assert redact.findall(text), secret
        assert secret not in redact.redact(text), secret
        assert redact.MASK in redact.redact(text)


def test_an_assignment_keeps_its_label_but_loses_the_value():
    out = redact.redact('password = "hunter2hunter2hunter2"')
    assert out.startswith("password = ")
    assert "hunter2" not in out
    assert redact.MASK in out


def test_the_assignment_pattern_is_case_insensitive_and_covers_api_key_spellings():
    for label in ["SECRET", "Token", "api_key", "API-KEY", "apikey"]:
        assert redact.findall(f"{label}: abcdefghijklmnop"), label


def test_a_short_value_is_not_treated_as_a_secret():
    assert redact.findall("password = short") == []


def test_ordinary_text_is_left_alone():
    text = "14 passed in 0.32s\nsrc/money.py 96%\n"
    assert redact.redact(text) == text
    assert redact.findall(text) == []


def test_findall_names_the_pattern():
    names = dict(redact.findall("AKIAIOSFODNN7EXAMPLE"))
    assert "AKIAIOSFODNN7EXAMPLE" in names.values() or names
    assert [n for n, _ in redact.findall("AKIAIOSFODNN7EXAMPLE")] == ["aws-key-id"]


def test_redaction_of_none_and_empty_is_safe():
    assert redact.redact(None) == ""
    assert redact.redact("") == ""
    assert redact.findall(None) == []
