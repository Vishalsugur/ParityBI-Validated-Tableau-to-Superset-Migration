"""Extract step: download/unzip and the file-level contract."""

import csv
import io
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pipeline import config, extract

GOOD_ROW = ["INC0000045", "New", "true", "0", "0", "0", "true", "Caller 2403", "Opened by  8",
            "29/2/2016 01:16", "Created by 6", "29/2/2016 01:23", "Updated by 21", "29/2/2016 01:23",
            "Phone", "Location 143", "Category 55", "Subcategory 170", "Symptom 72", "?", "2 - Medium",
            "2 - Medium", "3 - Moderate", "Group 56", "?", "true", "false", "Do Not Notify", "?", "?", "?",
            "?", "code 5", "Resolved by 149", "29/2/2016 11:29", "5/3/2016 12:00"]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_contract_accepts_valid_file(tmp_path):
    path = tmp_path / "incident_event_log.csv"
    write_csv(path, config.EXPECTED_COLUMNS, [GOOD_ROW] * 1500)
    assert extract.check_source_file(path) == {"rows": 1500, "columns": 36}


def test_contract_rejects_renamed_column(tmp_path):
    header = list(config.EXPECTED_COLUMNS)
    header[header.index("made_sla")] = "sla_made"
    path = tmp_path / "incident_event_log.csv"
    write_csv(path, header, [GOOD_ROW] * 1500)
    with pytest.raises(ValueError, match="made_sla"):
        extract.check_source_file(path)


def test_contract_rejects_truncated_file(tmp_path):
    path = tmp_path / "incident_event_log.csv"
    write_csv(path, config.EXPECTED_COLUMNS, [GOOD_ROW] * 10)
    with pytest.raises(ValueError, match="truncated"):
        extract.check_source_file(path)


def test_contract_rejects_us_style_dates(tmp_path):
    bad = list(GOOD_ROW)
    bad[config.EXPECTED_COLUMNS.index("opened_at")] = "2016-02-29T01:16:00"
    path = tmp_path / "incident_event_log.csv"
    write_csv(path, config.EXPECTED_COLUMNS, [bad] * 1500)
    with pytest.raises(ValueError, match="bad dates"):
        extract.check_source_file(path)


def test_download_unzips_the_csv(tmp_path):
    """Serve a zip like UCI's over local HTTP and check the CSV comes out."""
    served = tmp_path / "served"
    served.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("incident_event_log.csv", "number\nINC0000001\n")
    (served / "dataset.zip").write_bytes(buf.getvalue())

    handler = partial(SimpleHTTPRequestHandler, directory=str(served))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        target = tmp_path / "raw" / "incident_event_log.csv"
        url = f"http://127.0.0.1:{server.server_port}/dataset.zip"
        info = extract.download_source(target, url)
        assert info["downloaded"] is True
        assert target.read_text() == "number\nINC0000001\n"
        # second call is a no-op (idempotent)
        assert extract.download_source(target, url)["downloaded"] is False
    finally:
        server.shutdown()


def test_download_error_explains_manual_fallback(tmp_path):
    with pytest.raises(RuntimeError, match="Download it manually"):
        extract.download_source(tmp_path / "x.csv", "http://127.0.0.1:9/nothing.zip", timeout=2)
