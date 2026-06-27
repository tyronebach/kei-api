import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import entities, snapshots, summary, transactions
from schemas import EntityCreate, ItemAdjust, ItemCreate, ListItemCreate, TransactionCreate


def test_transaction_amount_must_be_positive():
    with pytest.raises(ValidationError):
        TransactionCreate(
            scope="salon",
            type="income",
            amount=0,
            category="haircut",
            date="2026-02-01",
        )


def test_transaction_date_must_be_iso():
    with pytest.raises(ValidationError):
        TransactionCreate(
            scope="salon",
            type="income",
            amount=10,
            category="haircut",
            date="02-01-2026",
        )


def test_whitespace_only_names_rejected():
    with pytest.raises(ValidationError):
        EntityCreate(scope="salon", name="   ")


def test_whitespace_only_list_content_rejected():
    with pytest.raises(ValidationError):
        ListItemCreate(scope="home", list="shopping", content="   ")


def test_item_quantity_must_be_non_negative():
    with pytest.raises(ValidationError):
        ItemCreate(scope="salon", name="Foil", quantity=-1)


def test_item_adjust_quantity_rules():
    with pytest.raises(ValidationError):
        ItemAdjust(type="out", quantity=0)

    valid = ItemAdjust(type="adjustment", quantity=0)
    assert valid.quantity == 0


def test_tags_normalized_and_deduplicated():
    model = EntityCreate(scope="salon", name="Amy", tags=[" vip ", "vip", "new"])
    assert model.tags == ["vip", "new"]

    with pytest.raises(ValidationError):
        EntityCreate(scope="salon", name="Amy", tags=["valid", "  "])


def test_summary_invalid_custom_dates_raise_422(db_session, admin_agent):
    with pytest.raises(HTTPException) as exc:
        summary.get_summary(
            scope="salon",
            period="custom",
            from_date="not-a-date",
            to_date="2026-02-01",
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_summary_invalid_period_raises_422(db_session, admin_agent):
    with pytest.raises(HTTPException) as exc:
        summary.get_summary(
            scope="salon",
            period="quarter",
            from_date=None,
            to_date=None,
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_summary_invalid_source_raises_422(db_session, admin_agent):
    with pytest.raises(HTTPException) as exc:
        summary.get_summary(
            scope="salon",
            period="month",
            from_date=None,
            to_date=None,
            source="bnak",
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_summary_invalid_category_type_raises_422(db_session, admin_agent):
    with pytest.raises(HTTPException) as exc:
        summary.get_by_category(
            scope="salon",
            period="month",
            from_date=None,
            to_date=None,
            type="profit",
            limit=20,
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_transaction_invalid_date_filters_raise_422(db_session, admin_agent):
    for invalid_date in ("not-a-date", "20260320", "2026-W12-5"):
        with pytest.raises(HTTPException) as exc:
            transactions.list_transactions(
                scope="salon",
                from_date=invalid_date,
                to_date=None,
                sort="date",
                limit=50,
                offset=0,
                agent=admin_agent,
                db=db_session,
            )
        assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        transactions.list_transactions(
            scope="salon",
            from_date=None,
            to_date="not-a-date",
            sort="date",
            limit=50,
            offset=0,
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_snapshot_invalid_date_filters_raise_422(db_session, admin_agent):
    for invalid_date in ("not-a-date", "20260320", "2026-W12-5"):
        with pytest.raises(HTTPException) as exc:
            snapshots.list_snapshots(
                scope="salon",
                from_date=invalid_date,
                to_date=None,
                limit=50,
                offset=0,
                agent=admin_agent,
                db=db_session,
            )
        assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        snapshots.list_snapshots(
            scope="salon",
            from_date=None,
            to_date="not-a-date",
            limit=50,
            offset=0,
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422


def test_entities_invalid_created_after_raises_422(db_session, admin_agent):
    with pytest.raises(HTTPException) as exc:
        entities.get_entity_insights(
            scope="salon",
            created_after="bad-date",
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 422
