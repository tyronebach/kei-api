from datetime import date

from fastapi import HTTPException


def _is_yyyy_mm_dd(value: str) -> bool:
    return (
        len(value) == 10
        and value[4] == "-"
        and value[7] == "-"
        and value[:4].isdigit()
        and value[5:7].isdigit()
        and value[8:].isdigit()
    )


def parse_date(value: str, param_name: str) -> date:
    if not _is_yyyy_mm_dd(value):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date for '{param_name}': '{value}'. Expected YYYY-MM-DD.",
        )

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date for '{param_name}': '{value}'. Expected YYYY-MM-DD.",
        ) from exc
