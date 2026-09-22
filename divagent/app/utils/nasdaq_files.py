import httpx


async def fetch_pipe_file(url: str) -> list[dict[str, str]]:
    """Fetch a Nasdaq Trader symbol-directory file and return rows as dicts.

    These files are pipe-delimited with a header row and a trailing
    "File Creation Time: ..." footer row, which is dropped.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    header = lines[0].split("|")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        values = line.split("|")
        if len(values) != len(header):
            continue
        rows.append(dict(zip(header, values)))
    return rows


def to_bool(value: str | None) -> bool:
    return (value or "").strip().upper() == "Y"


def to_int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() else None
