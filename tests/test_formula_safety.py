import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
import objekte_lib  # noqa: E402
import tools_lib  # noqa: E402


FORMULA_CASES = (
    ('=HYPERLINK("https://evil.example","x")', "'=HYPERLINK(\"https://evil.example\",\"x\")"),
    ('+SUM(A1:A2)', "'+SUM(A1:A2)"),
    ('-IMPORTXML("https://evil.example","//a")', "'-IMPORTXML(\"https://evil.example\",\"//a\")"),
    ('@cmd', "'@cmd"),
)

NUMERIC_CASES = ('-123.45', '+123.45', '-123,45', '+123,45')


def test_csv_safe_escapes_formula_like_values_but_preserves_numeric_literals():
    for raw, expected in FORMULA_CASES:
        assert backend._csv_safe(raw) == expected

    for raw in NUMERIC_CASES:
        assert backend._csv_safe(raw) == raw


def test_sheets_safe_escapes_formula_like_values_but_preserves_numeric_literals():
    for lib in (objekte_lib, tools_lib):
        for raw, expected in FORMULA_CASES:
            assert lib._sheets_formula_safe(raw) == expected

        for raw in NUMERIC_CASES:
            assert lib._sheets_formula_safe(raw) == raw

        assert lib._sheets_formula_safe(123.45) == 123.45
