from datetime import date

from fastapi import HTTPException


def parse_date(value: str, param_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date for '{param_name}': '{value}'. Expected YYYY-MM-DD.",
        ) from exc
