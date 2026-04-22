class ValidationError(ValueError):
    pass


def validate_upload(*, filename: str, size_bytes: int, max_bytes: int) -> None:
    if not filename:
        raise ValidationError("filename is required")
    if size_bytes <= 0:
        raise ValidationError("file is empty")
    if size_bytes > max_bytes:
        raise ValidationError(
            f"file size {size_bytes} exceeds maximum allowed size of {max_bytes} bytes"
        )
