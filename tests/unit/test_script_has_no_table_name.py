import pytest

from pre_commit_dbt.check_script_has_no_table_name import has_table_name
from pre_commit_dbt.check_script_has_no_table_name import main
from pre_commit_dbt.check_script_has_no_table_name import prev_cur_next_iter
from pre_commit_dbt.check_script_has_no_table_name import replace_comments

# Input, expected return value, expected output
TESTS = (  # type: ignore
    (
        """
    SELECT * FROM AA
    """,
        1,
        {"aa"},
    ),
    (
        """
    SELECT * FROM AA
    LEFT JOIN BB ON AA.A = BB.A
    """,
        1,
        {"aa", "bb"},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM CC
    )
    SELECT * FROM AA
    LEFT JOIN BB ON AA.A = BB.A
    """,
        1,
        {"cc", "bb"},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    )
    SELECT * FROM AA
    LEFT JOIN BB ON AA.A = BB.A
    """,
        1,
        {"bb"},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    ),
    bb AS (
        SELECT * FROM xx
    )
    SELECT * FROM AA
    LEFT JOIN BB ON AA.A = BB.A
    """,
        1,
        {"xx"},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    ),
    bb AS (
        SELECT * FROM xx.xx.xx
    )
    SELECT * FROM AA
    LEFT JOIN BB ON AA.A = BB.A
    """,
        1,
        {"xx.xx.xx"},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    )
    SELECT * FROM AA
    LEFT JOIN {{ ref('xx') }} ON AA.A = BB.A
    """,
        0,
        {},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    )
    -- SELECT * FROM GG
    SELECT * FROM AA
    LEFT JOIN {{ ref('xx') }} ON AA.A = BB.A
    """,
        0,
        {},
    ),
    (
        """
    WITH AA AS (
        SELECT * FROM {{ source('aa') }}
    )
    /* SELECT *
    FROM GG
    */
    SELECT * FROM AA
    LEFT JOIN {{ ref('xx') }} ON AA.A = BB.A
    """,
        0,
        {},
    ),
    pytest.param(
        "with src as (select * from {{ source('aa', 'bb') }}), "
        "flat as (select * from src, lateral flatten(line_items)) "
        "select * from flat",
        0,
        set(),
        id="cte-comma-lateral-flatten-allowed",
    ),
    pytest.param(
        "with src as (select * from {{ source('aa', 'bb') }}) "
        "select * from {{ ref('cc') }} join SRC, lateral flatten(line_items)",
        0,
        set(),
        id="cte-comma-after-join-allowed",
    ),
    pytest.param(
        "with src as (select * from CC ), "
        "flat as (select * from src, lateral flatten(line_items)) "
        "select * from flat left join BB on flat.id = BB.id",
        1,
        {"cc", "bb"},
        id="cte-comma-direct-tables-detected",
    ),
    pytest.param(
        "{# from join #} "
        "with src as (select * from {{ source('aa', 'bb') }}) select * from src",
        0,
        set(),
        id="jinja-comment-ignored",
    ),
    pytest.param(
        "{# from hidden\njoin ignored #}\n"
        "with src as (select * from {{ source('aa', 'bb') }}) "
        "select * from src join {{ ref('cc') }} on src.id = cc.id",
        0,
        set(),
        id="multiline-jinja-comment-ignored",
    ),
    pytest.param(
        "{# from hidden #} SELECT * FROM AA {# join ignored #} "
        "LEFT JOIN BB ON AA.A = BB.A",
        1,
        {"aa", "bb"},
        id="jinja-comments-preserve-direct-tables-between-them",
    ),
)


@pytest.mark.parametrize(("input_s", "expected_status_code", "output"), TESTS)
def test_has_table_name(input_s, expected_status_code, output):
    ret, tables = has_table_name(input_s, "text.sql")
    diff = tables.symmetric_difference(output)
    assert not diff
    assert ret == expected_status_code


@pytest.mark.parametrize(("input_s", "expected_status_code", "output"), TESTS)
def test_has_table_name_integration(input_s, expected_status_code, output, tmpdir):
    path = tmpdir.join("file.txt")
    path.write_text(input_s, "utf-8")

    ret = main([str(path)])

    assert ret == expected_status_code


@pytest.mark.parametrize(
    ("filenames", "expected_status_code"),
    (
        (("source.sql", "ref.sql"), 0),
        (("dirty.sql", "ref.sql"), 1),
        (("source.sql", "dirty.sql"), 1),
    ),
)
def test_main_multiple_files(filenames, expected_status_code, tmpdir, capsys):
    scripts = {
        "source.sql": "SELECT * FROM {{ source('aa', 'bb') }}",
        "ref.sql": "SELECT * FROM {{ ref('aa') }}",
        "dirty.sql": "SELECT * FROM AA LEFT JOIN BB ON AA.A = BB.A",
    }
    for filename, sql in scripts.items():
        tmpdir.join(filename).write_text(sql, "utf-8")

    ret = main([str(tmpdir.join(filename)) for filename in filenames])
    assert ret == expected_status_code
    output = capsys.readouterr().out
    if expected_status_code:
        lines = output.splitlines()
        assert lines[0] == (
            f"{tmpdir.join('dirty.sql')}: "
            "does not use source() or ref() macros for tables:"
        )
        assert set(lines[1:]) == {"- aa", "- bb"}
    else:
        assert output == ""


def test_replace_comments():
    sql = "-- select * from ee"
    assert replace_comments(sql) == ""
    sql = "--- select * from ee"
    assert replace_comments(sql) == ""
    sql = "/* select * from ee*/"
    assert replace_comments(sql) == ""


def test_prev_cur_next_iter():
    txt = ["aa", "bb", "cc"]
    gen = prev_cur_next_iter(txt)
    prv, cur, nxt = next(gen)
    assert prv is None
    assert cur == "aa"
    assert nxt == "bb"
    prv, cur, nxt = next(gen)
    assert prv == "aa"
    assert cur == "bb"
    assert nxt == "cc"
    prv, cur, nxt = next(gen)
    assert prv == "bb"
    assert cur == "cc"
    assert nxt is None
