import json

from auction_tape.cli import main


def test_cli_text_default_terms(capsys, tmp_path, raw_rows):
    f = tmp_path / "raw.json"
    f.write_text(json.dumps(raw_rows))
    assert main(["--from-file", str(f)]) == 0
    out = capsys.readouterr().out
    for t in ("2-Year", "5-Year", "10-Year", "30-Year"):
        assert t in out
    assert "7-Year" not in out


def test_cli_json_with_wi_and_html(capsys, tmp_path, raw_rows, curve_csv_path):
    f = tmp_path / "raw.json"
    f.write_text(json.dumps(raw_rows))
    html = tmp_path / "d.html"
    rc = main(["--from-file", str(f), "--json", "--wi", "10Y=5.31", "--approx-wi",
               "--closes-file", str(curve_csv_path), "-o", str(html)])
    assert rc == 0
    data = {d["term"]: d for d in json.loads(capsys.readouterr().out)}
    assert data["10-Year"]["tail_bp"] == -1.0
    assert data["10-Year"]["tail_word"] == "stop-through"
    assert data["10-Year"]["wi_source"] == "given"
    assert data["2-Year"]["wi_source"] in ("close", None)
    page = html.read_text()
    assert page.startswith("<!doctype html>") and "10-Year" in page and "stop-through" in page


def test_cli_markdown_all_terms(capsys, tmp_path, raw_rows):
    f = tmp_path / "raw.json"
    f.write_text(json.dumps(raw_rows))
    assert main(["--from-file", str(f), "--md", "--terms", "all"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| Term") and "7-Year" in out


def test_cli_errors(capsys, tmp_path):
    assert main(["--wi", "bogus", "--from-file", "x"]) == 2
    assert main(["--from-file", str(tmp_path / "missing.json")]) == 1
    try:
        main(["--terms", "4", "--from-file", "x"])
    except SystemExit as e:
        assert "unknown term" in str(e)
