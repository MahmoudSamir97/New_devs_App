from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

from sqlalchemy import text

from app.core.database_pool import db_pool

CENTS = Decimal("0.01")


def to_money(amount) -> Decimal:
    """
    Rounds an amount to cents. Amounts are stored with 3 decimals, so they must
    be summed first and rounded once at the end (never through float).
    """
    return Decimal(str(amount or 0)).quantize(CENTS, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month.

    The month boundaries are taken in the property's local timezone, so a
    check-in at 2024-02-29 23:30 UTC in Paris (00:30 on March 1st local time)
    is counted in March.
    """

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    query = text("""
        SELECT
            COALESCE(SUM(r.total_amount), 0) as total_revenue,
            COUNT(r.id) as reservation_count
        FROM properties p
        LEFT JOIN reservations r
            ON r.property_id = p.id
            AND r.tenant_id = p.tenant_id
            AND r.check_in_date >= (CAST(:start_date AS timestamp) AT TIME ZONE p.timezone)
            AND r.check_in_date < (CAST(:end_date AS timestamp) AT TIME ZONE p.timezone)
        WHERE p.id = :property_id AND p.tenant_id = :tenant_id
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(to_money(row.total_revenue if row else 0)),
        "currency": "USD",
        "count": row.reservation_count if row else 0,
        "month": month,
        "year": year,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    query = text("""
        SELECT
            property_id,
            SUM(total_amount) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        GROUP BY property_id
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(to_money(row.total_revenue)),
            "currency": "USD",
            "count": row.reservation_count
        }

    # No reservations found for this property
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0
    }


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties that belong to a tenant.
    """
    query = text("""
        SELECT id, name, timezone
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY id
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()

    return [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows]
