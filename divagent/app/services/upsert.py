from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


async def bulk_upsert(session: AsyncSession, model, values: list[dict]) -> int:
    """Insert rows, updating existing ones on primary-key conflict.

    No deletes: rows missing from the source (e.g. delisted) are left as-is.
    """
    if not values:
        return 0

    table = model.__table__
    pk_cols = {c.name for c in table.primary_key.columns}

    # Dedupe within the batch (last occurrence wins); ON CONFLICT cannot touch
    # the same row twice in one statement.
    deduped: dict[tuple, dict] = {}
    for row in values:
        deduped[tuple(row[c] for c in pk_cols)] = row
    values = list(deduped.values())

    # Only update columns actually supplied, so a partial upsert (e.g. enriching
    # a subset of columns) doesn't null out the ones it left out.
    supplied = set().union(*(row.keys() for row in values))

    # asyncpg caps a statement at 32767 bind params; chunk so cols*rows stays under.
    n_cols = max(len(row) for row in values)
    chunk = max(1, 32767 // n_cols)

    for i in range(0, len(values), chunk):
        batch = values[i : i + chunk]
        stmt = pg_insert(table).values(batch)
        update_cols = {
            c.name: getattr(stmt.excluded, c.name)
            for c in table.columns
            if c.name not in pk_cols and c.name in supplied
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=list(pk_cols),
            set_=update_cols,
        )
        await session.execute(stmt)

    return len(values)
