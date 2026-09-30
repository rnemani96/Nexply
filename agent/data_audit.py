from database import get_connection


def main():
    connection = get_connection()

    print("=" * 70)
    print("RAJESH AI - JOB DATA AUDIT")
    print("=" * 70)

    print()
    print("REMOTE TYPE")
    print("-" * 50)

    rows = connection.execute("""
        SELECT remote_type, COUNT(*)
        FROM jobs
        GROUP BY remote_type
    """).fetchall()

    for row in rows:
        print(f"{row[0]}: {row[1]}")

    print()
    print("LOCATION CODES")
    print("-" * 50)

    rows = connection.execute("""
        SELECT
            COALESCE(location_codes, '<blank>'),
            COUNT(*)
        FROM jobs
        GROUP BY location_codes
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """).fetchall()

    for row in rows:
        print(f"{row[0]}: {row[1]}")

    print()
    print("TIMEZONE PATTERNS")
    print("-" * 50)

    rows = connection.execute("""
        SELECT
            COALESCE(timezone_restrictions, '<blank>'),
            COUNT(*)
        FROM jobs
        GROUP BY timezone_restrictions
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """).fetchall()

    for row in rows:
        print(f"{row[0]}: {row[1]}")

    print()
    print("TOTAL JOBS")
    print("-" * 50)

    row = connection.execute("""
        SELECT COUNT(*)
        FROM jobs
    """).fetchone()

    print(row[0])

    connection.close()

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()