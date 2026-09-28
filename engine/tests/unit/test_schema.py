from pair import schema
from pair.schema import Bool, Int, ListOf, Null, Num, OneOf, Str, Table


def test_a_good_table_has_no_errors():
    spec = Table({"name": Str(), "count": Int(minimum=1)}, required=("name",))
    assert schema.errors({"name": "a", "count": 2}, spec) == []


def test_a_missing_required_key_is_named():
    spec = Table({"name": Str()}, required=("name",))
    assert schema.errors({}, spec) == ["name: is required"]


def test_an_unknown_key_is_an_error_by_default():
    spec = Table({"name": Str()})
    assert schema.errors({"nmae": "a"}, spec) == ["nmae: is not a known key"]


def test_an_open_table_allows_unknown_keys():
    spec = Table({"name": Str()}, allow_unknown=True)
    assert schema.errors({"whatever": 1}, spec) == []


def test_every_problem_is_reported_not_just_the_first():
    spec = Table({"a": Int(), "b": Str()}, required=("c",))
    found = schema.errors({"a": "no", "b": 1}, spec)
    assert len(found) == 3


def test_types_are_named_in_plain_words():
    assert schema.errors({"a": "x"}, Table({"a": Int()})) == ["a: must be a whole number, got text"]
    assert schema.errors({"a": 1}, Table({"a": Str()})) == ["a: must be text, got a whole number"]
    assert schema.errors({"a": 1}, Table({"a": Bool()})) == \
        ["a: must be true or false, got a whole number"]


def test_a_bool_is_not_a_number():
    assert schema.errors({"a": True}, Table({"a": Int()}))


def test_bounds_and_const():
    assert schema.errors({"a": 0}, Table({"a": Int(minimum=1)})) == \
        ["a: must be at least 1, got 0"]
    assert schema.errors({"a": 101}, Table({"a": Num(maximum=100)})) == \
        ["a: must be at most 100, got 101"]
    assert schema.errors({"a": 2}, Table({"a": Int(const=1)})) == ["a: must be 1"]


def test_choices_and_pattern():
    spec = Table({"mode": Str(choices=("solo", "pair")), "me": Str(pattern=r"^@[\w.-]+$",
                                                                  describe="start with @")})
    assert schema.errors({"mode": "nope"}, spec) == \
        ["mode: must be one of solo, pair, got 'nope'"]
    assert schema.errors({"me": "ana"}, spec) == ["me: must start with @, got 'ana'"]


def test_nested_paths_are_dotted():
    spec = Table({"project": Table({"name": Str()}, required=("name",))})
    assert schema.errors({"project": {}}, spec) == ["project.name: is required"]


def test_list_items_are_indexed():
    spec = Table({"paths": ListOf(Str())})
    assert schema.errors({"paths": ["a", 2]}, spec) == ["paths.1: must be text, got a whole number"]


def test_a_list_can_require_entries():
    assert schema.errors({"p": []}, Table({"p": ListOf(Str(), min_items=1)})) == \
        ["p: needs at least 1 entry"]


def test_one_of_accepts_either_and_reports_both_when_neither_fits():
    spec = Table({"approval": OneOf(Null(), Table({"by": Str()}, required=("by",)))})
    assert schema.errors({"approval": None}, spec) == []
    assert schema.errors({"approval": {"by": "@ana"}}, spec) == []
    assert len(schema.errors({"approval": 7}, spec)) == 2


def test_the_line_number_is_reported_when_the_raw_text_is_given():
    text = "format = 1\n\n[project]\nnmae = \"potato\"\n"
    spec = Table({"format": Int(), "project": Table({"name": Str()})})
    found = schema.errors({"format": 1, "project": {"nmae": "potato"}}, spec, text=text)
    assert found == ["project.nmae: is not a known key (line 4)"]


def test_a_table_header_line_is_found_too():
    text = "format = 1\n\n[nope]\nx = 1\n"
    spec = Table({"format": Int()})
    found = schema.errors({"format": 1, "nope": {"x": 1}}, spec, text=text)
    assert found == ["nope: is not a known key (line 3)"]


def test_a_quoted_key_line_is_found():
    text = '[scopes."packages/billing"]\nline = 1.0\n'
    assert schema.line_of(text, 'scopes.packages/billing') == 1


def test_line_of_returns_none_when_the_key_is_absent():
    assert schema.line_of("a = 1\n", "b") is None
    assert schema.line_of("", "b") is None


def test_an_open_table_can_constrain_every_value():
    spec = Table({"scopes": Table(values=Table({"line": Num()}, required=("line",)))})
    assert schema.errors({"scopes": {"a/b": {"line": 1.0}}}, spec) == []
    assert schema.errors({"scopes": {"a/b": {}}}, spec) == ["scopes.a/b.line: is required"]


def test_a_wrong_shape_at_the_root_is_reported():
    assert schema.errors([], Table({})) == ["<root>: must be a table, got a list"]
