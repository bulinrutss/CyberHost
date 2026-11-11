from calendar import monthrange
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.finance import FinanceEvent, FinanceGoal, FinanceTransaction
from app.services import finance_receipts
from app.services import finance_push

TRANSACTION_KINDS = {"income", "expense"}
GOAL_KINDS = {"savings", "monthly"}

INCOME_CATEGORY_LABELS = {
    "salario": "Salário",
    "freelance": "Freelance",
    "investimento": "Investimento",
    "reembolso": "Reembolso",
    "outro": "Outro",
}
EXPENSE_CATEGORY_LABELS = {
    "alimentacao": "Alimentação",
    "moradia": "Moradia",
    "transporte": "Transporte",
    "saude": "Saúde",
    "lazer": "Lazer",
    "assinaturas": "Assinaturas",
    "educacao": "Educação",
    "manutencao": "Manutenção",
    "impostos": "Impostos",
    "outro": "Outro",
}
EVENT_CATEGORY_LABELS = {
    "saude": "Saúde",
    "manutencao": "Manutenção",
    "pessoal": "Pessoal",
    "trabalho": "Trabalho",
    "financeiro": "Financeiro",
    "outro": "Outro",
}
PAYMENT_METHOD_LABELS = {
    "pix": "Pix",
    "cartao": "Cartão",
    "dinheiro": "Dinheiro",
    "ted": "TED / transferência",
    "boleto": "Boleto",
    "outro": "Outro",
}

INCOME_CATEGORIES = set(INCOME_CATEGORY_LABELS)
EXPENSE_CATEGORIES = set(EXPENSE_CATEGORY_LABELS)
EVENT_CATEGORIES = set(EVENT_CATEGORY_LABELS)
PAYMENT_METHODS = set(PAYMENT_METHOD_LABELS)

_MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def category_label(kind: str, category: str) -> str:
    if kind == "income":
        return INCOME_CATEGORY_LABELS.get(category, category)
    if kind == "expense":
        return EXPENSE_CATEGORY_LABELS.get(category, category)
    return EVENT_CATEGORY_LABELS.get(category, category)


def meta() -> dict:
    def opts(mapping: dict[str, str]) -> list[dict[str, str]]:
        return [{"id": key, "label": label} for key, label in mapping.items()]

    return {
        "income_categories": opts(INCOME_CATEGORY_LABELS),
        "expense_categories": opts(EXPENSE_CATEGORY_LABELS),
        "event_categories": opts(EVENT_CATEGORY_LABELS),
        "payment_methods": opts(PAYMENT_METHOD_LABELS),
        "vapid_public_key": (get_settings().vapid_public_key.strip() or None)
        if get_settings().finance_push_configured
        else None,
        "push_available": get_settings().finance_push_configured,
    }


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _month_start(ref: date, months_ago: int) -> date:
    year = ref.year
    month = ref.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _month_end(ref: date) -> date:
    return date(ref.year, ref.month, monthrange(ref.year, ref.month)[1])


def _month_label(year: int, month: int, *, short: bool = False) -> str:
    name = _MONTH_NAMES[month - 1]
    if short:
        return f"{name[:3].capitalize()}/{year % 100:02d}"
    return f"{name.capitalize()} de {year}"


def _validate_tx_category(kind: str, category: str) -> None:
    allowed = INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
    if category not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Categoria incompatível com o tipo do lançamento",
        )


def list_transactions(
    db: Session,
    user_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    kind: str | None = None,
    category: str | None = None,
    payment_method: str | None = None,
    limit: int = 200,
) -> list[FinanceTransaction]:
    query = db.query(FinanceTransaction).filter(FinanceTransaction.user_id == user_id)
    if start is not None:
        query = query.filter(FinanceTransaction.occurred_on >= start)
    if end is not None:
        query = query.filter(FinanceTransaction.occurred_on <= end)
    if kind:
        key = kind.strip().lower()
        if key not in TRANSACTION_KINDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo inválido")
        query = query.filter(FinanceTransaction.kind == key)
    if category:
        query = query.filter(FinanceTransaction.category == category.strip().lower())
    if payment_method:
        method = payment_method.strip().lower()
        if method not in PAYMENT_METHODS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Forma de pagamento inválida"
            )
        query = query.filter(FinanceTransaction.payment_method == method)
    capped = min(max(limit, 1), 500)
    return (
        query.order_by(FinanceTransaction.occurred_on.desc(), FinanceTransaction.id.desc())
        .limit(capped)
        .all()
    )


def get_owned_transaction(db: Session, user_id: int, tx_id: int) -> FinanceTransaction:
    row = db.get(FinanceTransaction, tx_id)
    if row is None or row.user_id != user_id:
        raise _not_found("Lançamento não encontrado")
    return row


def create_transaction(db: Session, user_id: int, payload) -> FinanceTransaction:
    _validate_tx_category(payload.kind, payload.category)
    row = FinanceTransaction(
        user_id=user_id,
        kind=payload.kind,
        title=payload.title,
        amount_cents=payload.amount_cents,
        category=payload.category,
        payment_method=payload.payment_method,
        notes=payload.notes or "",
        occurred_on=payload.occurred_on,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_transaction(db: Session, row: FinanceTransaction, payload) -> FinanceTransaction:
    data = payload.model_dump(exclude_unset=True)
    kind = data.get("kind", row.kind)
    category = data.get("category", row.category)
    _validate_tx_category(kind, category)
    for key, value in data.items():
        setattr(row, key, value if value is not None else getattr(row, key))
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_transaction(db: Session, row: FinanceTransaction) -> None:
    finance_receipts.delete_receipt_files(row.user_id, row.id)
    db.delete(row)
    db.commit()


def list_events(
    db: Session,
    user_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 300,
) -> list[FinanceEvent]:
    query = db.query(FinanceEvent).filter(FinanceEvent.user_id == user_id)
    if start is not None:
        query = query.filter(FinanceEvent.starts_at >= start)
    if end is not None:
        query = query.filter(FinanceEvent.starts_at <= end)
    capped = min(max(limit, 1), 500)
    return query.order_by(FinanceEvent.starts_at.asc(), FinanceEvent.id.asc()).limit(capped).all()


def get_owned_event(db: Session, user_id: int, event_id: int) -> FinanceEvent:
    row = db.get(FinanceEvent, event_id)
    if row is None or row.user_id != user_id:
        raise _not_found("Evento não encontrado")
    return row


def _normalize_event_start(starts_at: datetime, all_day: bool) -> datetime:
    if all_day:
        return datetime(starts_at.year, starts_at.month, starts_at.day)
    return starts_at.replace(second=0, microsecond=0)


def create_event(db: Session, user_id: int, payload) -> FinanceEvent:
    all_day = bool(payload.all_day)
    duration = 0 if all_day else payload.duration_min
    row = FinanceEvent(
        user_id=user_id,
        title=payload.title,
        category=payload.category,
        notes=payload.notes or "",
        starts_at=_normalize_event_start(payload.starts_at, all_day),
        duration_min=duration,
        all_day=all_day,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_event(db: Session, row: FinanceEvent, payload) -> FinanceEvent:
    data = payload.model_dump(exclude_unset=True)
    all_day = data.get("all_day", row.all_day)
    starts_at = data.get("starts_at", row.starts_at)
    duration = data.get("duration_min", row.duration_min)
    if all_day:
        duration = 0
        starts_at = _normalize_event_start(starts_at, True)
    elif "starts_at" in data:
        starts_at = _normalize_event_start(starts_at, False)
    for key, value in data.items():
        if key in {"starts_at", "duration_min", "all_day"}:
            continue
        setattr(row, key, value if value is not None else getattr(row, key))
    row.all_day = all_day
    if row.starts_at != starts_at:
        finance_push.clear_event_notices(db, row.id)
    row.starts_at = starts_at
    row.duration_min = duration
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_event(db: Session, row: FinanceEvent) -> None:
    finance_push.clear_event_notices(db, row.id)
    db.delete(row)
    db.commit()


def build_stats(db: Session, user_id: int, months: int = 6) -> dict:
    today = date.today()
    span = min(max(months, 1), 24)
    range_start = _month_start(today, span - 1)
    month_start = _month_start(today, 0)
    month_end = _month_end(today)

    txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.user_id == user_id,
            FinanceTransaction.occurred_on >= range_start,
        )
        .all()
    )
    all_txs = (
        db.query(FinanceTransaction.kind, FinanceTransaction.amount_cents)
        .filter(FinanceTransaction.user_id == user_id)
        .all()
    )

    buckets: dict[tuple[int, int], dict[str, int]] = {}
    for offset in range(span):
        start = _month_start(today, span - 1 - offset)
        buckets[(start.year, start.month)] = {"income": 0, "expense": 0}

    month_income = 0
    month_expense = 0
    month_count = 0
    by_cat: dict[tuple[str, str], int] = {}

    for tx in txs:
        key = (tx.occurred_on.year, tx.occurred_on.month)
        if key in buckets:
            buckets[key][tx.kind] += tx.amount_cents
        if month_start <= tx.occurred_on <= month_end:
            month_count += 1
            if tx.kind == "income":
                month_income += tx.amount_cents
            else:
                month_expense += tx.amount_cents
            cat_key = (tx.kind, tx.category)
            by_cat[cat_key] = by_cat.get(cat_key, 0) + tx.amount_cents

    all_time = 0
    for kind, amount in all_txs:
        all_time += amount if kind == "income" else -amount

    days_elapsed = max(today.day, 1)
    series = []
    for (year, month), totals in buckets.items():
        income = totals["income"]
        expense = totals["expense"]
        series.append(
            {
                "year": year,
                "month": month,
                "label": _month_label(year, month, short=True),
                "income_cents": income,
                "expense_cents": expense,
                "balance_cents": income - expense,
            }
        )

    upcoming_until = datetime.combine(today + timedelta(days=14), datetime.max.time()).replace(
        microsecond=0
    )
    upcoming = list_events(
        db,
        user_id,
        start=datetime.combine(today, datetime.min.time()),
        end=upcoming_until,
        limit=12,
    )

    by_category = [
        {
            "id": category,
            "label": category_label(kind, category),
            "amount_cents": amount,
            "kind": kind,
        }
        for (kind, category), amount in sorted(by_cat.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "income_cents": month_income,
        "expense_cents": month_expense,
        "balance_cents": month_income - month_expense,
        "all_time_balance_cents": all_time,
        "transaction_count": month_count,
        "avg_daily_expense_cents": month_expense // days_elapsed,
        "month_label": _month_label(today.year, today.month),
        "months": series,
        "by_category": by_category,
        "upcoming_events": upcoming,
    }


def _clamp_due(year: int, month: int, day: int) -> date:
    last = monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last))


def goal_due_on(row: FinanceGoal, today: date | None = None) -> date | None:
    ref = today or date.today()
    kind = (row.kind or "savings").strip().lower()
    if kind == "monthly" and row.due_day:
        return _clamp_due(ref.year, ref.month, row.due_day)
    return row.deadline


def _validate_goal_kind(kind: str) -> str:
    key = (kind or "savings").strip().lower()
    if key not in GOAL_KINDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de meta inválido")
    return key


def _require_due_day(due_day: int | None) -> int:
    if due_day is None or not (1 <= due_day <= 31):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe o dia do mês para concluir a meta",
        )
    return due_day


def roll_monthly_goal(db: Session, row: FinanceGoal, today: date | None = None) -> FinanceGoal:
    ref = today or date.today()
    if (row.kind or "savings") != "monthly":
        return row
    due_day = row.due_day or ref.day
    if row.period_year == ref.year and row.period_month == ref.month:
        row.deadline = _clamp_due(ref.year, ref.month, due_day)
        return row
    row.saved_cents = 0
    row.period_year = ref.year
    row.period_month = ref.month
    row.deadline = _clamp_due(ref.year, ref.month, due_day)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def serialize_goal(row: FinanceGoal) -> dict:
    remaining = max(row.target_cents - row.saved_cents, 0)
    percent = 0
    if row.target_cents > 0:
        percent = min(100, int(round((row.saved_cents * 100) / row.target_cents)))
    due_on = goal_due_on(row)
    days_left = (due_on - date.today()).days if due_on else None
    return {
        "id": row.id,
        "title": row.title,
        "kind": row.kind or "savings",
        "target_cents": row.target_cents,
        "saved_cents": row.saved_cents,
        "remaining_cents": remaining,
        "progress_percent": percent,
        "due_day": row.due_day,
        "due_on": due_on,
        "days_left": days_left,
        "deadline": row.deadline,
        "notes": row.notes or "",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_goals(db: Session, user_id: int) -> list[FinanceGoal]:
    rows = (
        db.query(FinanceGoal)
        .filter(FinanceGoal.user_id == user_id)
        .order_by(FinanceGoal.created_at.desc(), FinanceGoal.id.desc())
        .all()
    )
    return [roll_monthly_goal(db, row) for row in rows]


def get_owned_goal(db: Session, user_id: int, goal_id: int) -> FinanceGoal:
    row = db.get(FinanceGoal, goal_id)
    if row is None or row.user_id != user_id:
        raise _not_found("Meta não encontrada")
    return row


def create_goal(db: Session, user_id: int, payload) -> FinanceGoal:
    saved = min(payload.saved_cents, payload.target_cents) if payload.saved_cents else 0
    kind = _validate_goal_kind(payload.kind)
    today = date.today()
    due_day = payload.due_day
    deadline = payload.deadline
    period_year = None
    period_month = None
    if kind == "monthly":
        due_day = _require_due_day(due_day)
        deadline = _clamp_due(today.year, today.month, due_day)
        period_year = today.year
        period_month = today.month
    row = FinanceGoal(
        user_id=user_id,
        title=payload.title,
        kind=kind,
        target_cents=payload.target_cents,
        saved_cents=max(saved, 0),
        due_day=due_day,
        deadline=deadline,
        period_year=period_year,
        period_month=period_month,
        notes=payload.notes or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_goal(db: Session, row: FinanceGoal, payload) -> FinanceGoal:
    data = payload.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] is not None:
        data["kind"] = _validate_goal_kind(data["kind"])
    for key, value in data.items():
        setattr(row, key, value)
    if row.saved_cents < 0:
        row.saved_cents = 0
    kind = _validate_goal_kind(row.kind)
    row.kind = kind
    today = date.today()
    if kind == "monthly":
        row.due_day = _require_due_day(row.due_day)
        if "saved_cents" in data or row.period_year is None or row.period_month is None:
            row.period_year = today.year
            row.period_month = today.month
        row.deadline = _clamp_due(today.year, today.month, row.due_day)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return roll_monthly_goal(db, row)


def deposit_goal(db: Session, row: FinanceGoal, amount_cents: int) -> FinanceGoal:
    row = roll_monthly_goal(db, row)
    row.saved_cents = min(row.saved_cents + amount_cents, 1_000_000_000)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_goal(db: Session, row: FinanceGoal) -> None:
    db.delete(row)
    db.commit()
