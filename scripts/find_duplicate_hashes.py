from sqlalchemy import text
from database import engine


def main():
    query = text(
        """
        SELECT file_hash, COUNT(*) AS n
        FROM pagos
        WHERE file_hash IS NOT NULL AND file_hash <> ''
        GROUP BY file_hash
        HAVING COUNT(*) > 1
        ORDER BY n DESC
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        print("OK: no hay hashes duplicados en pagos.file_hash")
        return

    print("ATENCIÓN: hashes duplicados detectados (file_hash, count):")
    for file_hash, n in rows:
        print(file_hash, n)


if __name__ == "__main__":
    main()
