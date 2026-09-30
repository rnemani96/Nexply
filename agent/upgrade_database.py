import sqlite3
from database import get_connection


def add_column_if_missing(connection, column_name, column_definition):
    columns = connection.execute("PRAGMA table_info(jobs)").fetchall()
    existing = {row[1] for row in columns}

    if column_name not in existing:
        connection.execute(
            f"ALTER TABLE jobs ADD COLUMN {column_name} {column_definition}"
        )
        print(f"Added column: {column_name}")
    else:
        print(f"Already exists: {column_name}")


def main():
    connection = get_connection()

    print("=" * 70)
    print("NEXPLY - DATABASE UPGRADE")
    print("=" * 70)

    add_column_if_missing(
        connection,
        "source_url",
        "TEXT"
    )

    add_column_if_missing(
        connection,
        "application_url",
        "TEXT"
    )

    add_column_if_missing(
        connection,
        "location_restrictions",
        "TEXT"
    )

    connection.commit()

    print()
    print("Copying existing application URLs...")
    
    connection.execute("""
        UPDATE jobs
        SET application_url = url
        WHERE application_url IS NULL
           OR application_url = ''
    """)

    print("Copying existing Himalayas listing URLs...")

    connection.execute("""
        UPDATE jobs
        SET source_url = source_job_id
        WHERE source = 'Himalayas'
          AND source_job_id LIKE 'https://himalayas.app/%'
          AND (source_url IS NULL OR source_url = '')
    """)

    connection.commit()

    print()
    print("DATABASE STATUS")
    print("-" * 50)

    columns = connection.execute(
        "PRAGMA table_info(jobs)"
    ).fetchall()

    for column in columns:
        print(f"{column[1]}: {column[2]}")

    print()
    print("Jobs:", connection.execute(
        "SELECT COUNT(*) FROM jobs"
    ).fetchone()[0])

    connection.close()

    print()
    print("=" * 70)
    print("DATABASE UPGRADE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()