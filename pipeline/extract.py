"""Extract: download the public source file and check it against the column contract."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

from pipeline import config

log = logging.getLogger(__name__)

DATE_PATTERN = re.compile(r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}$")
NUMBER_PATTERN = re.compile(r"^INC\d{7}$")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_source(target: Path = config.SOURCE_FILE, url: str = config.SOURCE_URL,
                    timeout: int = 120) -> dict:
    """Download the UCI zip and unpack the CSV.

    Idempotent: if the CSV is already there (downloaded earlier or placed by hand),
    nothing is downloaded. This also makes the pipeline work offline.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        log.info("Source file already present, skipping download: %s", target)
        downloaded = False
    else:
        log.info("Downloading %s", url)
        request = urllib.request.Request(url, headers={"User-Agent": "servicedesk-bi-pipeline"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except Exception as exc:  # network errors, HTTP errors
            raise RuntimeError(
                f"Could not download the source file ({exc}). Download it manually from "
                f"{url}, unzip it and place incident_event_log.csv in {target.parent}"
            ) from exc
        _write_csv_from_payload(payload, target)
        downloaded = True

    return {
        "path": str(target),
        "downloaded": downloaded,
        "size_bytes": target.stat().st_size,
        "sha256": sha256_of(target),
    }


def _write_csv_from_payload(payload: bytes, target: Path) -> None:
    """The UCI download is a zip; accept a plain CSV too."""
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
            if not csv_members:
                raise RuntimeError(f"No CSV found in the downloaded zip: {archive.namelist()}")
            with archive.open(csv_members[0]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        target.write_bytes(payload)


def check_source_file(path: Path = config.SOURCE_FILE, sample_rows: int = 5000) -> dict:
    """File-level data contract. Fails fast before anything is loaded.

    Checks: exact header, minimum row count, incident number format and
    day-first timestamp format on a sample of rows.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if header != config.EXPECTED_COLUMNS:
            missing = sorted(set(config.EXPECTED_COLUMNS) - set(header))
            extra = sorted(set(header) - set(config.EXPECTED_COLUMNS))
            raise ValueError(f"Header does not match the contract. Missing: {missing}, unexpected: {extra}")

        idx_number = header.index("number")
        idx_opened = header.index("opened_at")
        rows = 0
        bad_numbers = 0
        bad_dates = 0
        for row in reader:
            rows += 1
            if len(row) != len(header):
                raise ValueError(f"Line {rows + 1} has {len(row)} fields, expected {len(header)}")
            if rows <= sample_rows:
                bad_numbers += not NUMBER_PATTERN.match(row[idx_number])
                bad_dates += not DATE_PATTERN.match(row[idx_opened])

    if rows < 1000:
        raise ValueError(f"Only {rows} data rows found - the file looks truncated")
    if bad_numbers or bad_dates:
        raise ValueError(f"Format errors in sample: {bad_numbers} bad incident numbers, {bad_dates} bad dates")

    log.info("Source file passed the contract: %s rows, %s columns", rows, len(header))
    return {"rows": rows, "columns": len(header)}
