import pytest

from app.utils.validation import ValidationError, validate_upload


def test_empty_file_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_upload(filename="x.txt", size_bytes=0, max_bytes=1000)


def test_oversize_rejected():
    with pytest.raises(ValidationError, match="size"):
        validate_upload(filename="x.txt", size_bytes=2000, max_bytes=1000)


def test_valid_file_passes():
    validate_upload(filename="a.js", size_bytes=500, max_bytes=1000)


def test_missing_filename_rejected():
    with pytest.raises(ValidationError, match="filename"):
        validate_upload(filename="", size_bytes=100, max_bytes=1000)
