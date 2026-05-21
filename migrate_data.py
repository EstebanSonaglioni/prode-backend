#!/usr/bin/env python3
"""
Migrate data from the backup SQLite DB to the current one,
preserving the custom users.User model.
"""
import sqlite3
import os

CURRENT_DB = "/media/alempa/LINUX STORAGE/Dev/prode/backend/db.sqlite3"
BACKUP_DB = "/media/alempa/LINUX STORAGE/Dev/prode/backend/db.sqlite3.backup.20260518_220752"

def migrate():
    print("Connecting to databases...")
    conn = sqlite3.connect(CURRENT_DB)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    # Attach backup
    cur.execute(f'ATTACH DATABASE "{BACKUP_DB}" AS backup')

    # Build content_type mapping (old_id -> new_id)
    print("Building content_type mapping...")
    cur.execute("SELECT id, app_label, model FROM backup.django_content_type")
    old_ct = { (r[1], r[2]): r[0] for r in cur.fetchall() }
    cur.execute("SELECT id, app_label, model FROM django_content_type")
    new_ct = { (r[1], r[2]): r[0] for r in cur.fetchall() }

    ct_map = {}
    for key, old_id in old_ct.items():
        if key in new_ct:
            ct_map[old_id] = new_ct[key]
        else:
            print(f"WARNING: content type {key} not found in current DB, mapping skipped")

    # Explicit mapping for the old user model -> new user model
    if ('auth', 'user') in old_ct and ('users', 'user') in new_ct:
        ct_map[old_ct[('auth', 'user')]] = new_ct[('users', 'user')]
        print(f"Explicit mapping: auth.user ({old_ct[('auth', 'user')]}) -> users.user ({new_ct[('users', 'user')]})")

    # ------------------------------------------------------------------
    # DELETE current data in reverse dependency order
    # ------------------------------------------------------------------
    tables_to_clear = [
        "prode_tournamentrankingsnapshot",
        "prode_prediction",
        "prode_match_tournaments",
        "prode_tournament_participants",
        "prode_tournament",
        "prode_templatematch",
        "prode_match",
        "prode_teamtranslation",
        "prode_predefinedtournamenttemplate",
        "prode_team",
        "token_blacklist_blacklistedtoken",
        "token_blacklist_outstandingtoken",
        "media_uploadedimage",
        "users_user",
    ]

    for tbl in tables_to_clear:
        print(f"Clearing {tbl} ...")
        cur.execute(f"DELETE FROM {tbl}")

    # ------------------------------------------------------------------
    # INSERT data from backup (parents first)
    # ------------------------------------------------------------------

    # 1. users_user  (from backup.auth_user)
    print("Migrating auth_user -> users_user ...")
    cur.execute("""
        INSERT INTO users_user (
            id, password, last_login, is_superuser, username,
            first_name, last_name, email, is_staff, is_active,
            date_joined, avatar
        )
        SELECT
            id, password, last_login, is_superuser, username,
            first_name, last_name, email, is_staff, is_active,
            date_joined, NULL
        FROM backup.auth_user
    """)

    # 2. token_blacklist_outstandingtoken
    print("Migrating token_blacklist_outstandingtoken ...")
    cur.execute("""
        INSERT INTO token_blacklist_outstandingtoken
        SELECT * FROM backup.token_blacklist_outstandingtoken
    """)

    # 3. token_blacklist_blacklistedtoken
    print("Migrating token_blacklist_blacklistedtoken ...")
    cur.execute("""
        INSERT INTO token_blacklist_blacklistedtoken
        SELECT * FROM backup.token_blacklist_blacklistedtoken
    """)

    # 4. media_uploadedimage  (map content_type_id)
    print("Migrating media_uploadedimage ...")
    cur.execute("SELECT id, image, category, uploaded_at, object_id, content_type_id, uploaded_by_id FROM backup.media_uploadedimage")
    for row in cur.fetchall():
        old_id, image, category, uploaded_at, object_id, old_ct_id, uploaded_by_id = row
        new_ct_id = ct_map.get(old_ct_id)
        if new_ct_id is None and old_ct_id is not None:
            print(f"  WARNING: skipping media_uploadedimage row {old_id} due to missing content_type mapping")
            continue
        cur.execute("""
            INSERT INTO media_uploadedimage (id, image, category, uploaded_at, object_id, content_type_id, uploaded_by_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (old_id, image, category, uploaded_at, object_id, new_ct_id, uploaded_by_id))

    # 5. prode_team  (column order differs)
    print("Migrating prode_team ...")
    cur.execute("""
        INSERT INTO prode_team (id, name, code, flag_url, is_national)
        SELECT id, name, code, flag_url, is_national
        FROM backup.prode_team
    """)

    # 6. prode_predefinedtournamenttemplate
    print("Migrating prode_predefinedtournamenttemplate ...")
    cur.execute("""
        INSERT INTO prode_predefinedtournamenttemplate
        SELECT * FROM backup.prode_predefinedtournamenttemplate
    """)

    # 7. prode_match
    print("Migrating prode_match ...")
    cur.execute("""
        INSERT INTO prode_match
        SELECT * FROM backup.prode_match
    """)

    # 8. prode_templatematch  (column order differs)
    print("Migrating prode_templatematch ...")
    cur.execute("""
        INSERT INTO prode_templatematch (id, match_date, stage, away_team_id, home_team_id, template_id)
        SELECT id, match_date, stage, away_team_id, home_team_id, template_id
        FROM backup.prode_templatematch
    """)

    # 9. prode_teamtranslation
    print("Migrating prode_teamtranslation ...")
    cur.execute("""
        INSERT INTO prode_teamtranslation
        SELECT * FROM backup.prode_teamtranslation
    """)

    # 10. prode_tournament  (column order differs)
    print("Migrating prode_tournament ...")
    cur.execute("""
        INSERT INTO prode_tournament (
            id, name, description, invitation_code, is_private, created_at,
            is_finished, finished_at, is_visible_when_finished, banner_id, owner_id
        )
        SELECT
            id, name, description, invitation_code, is_private, created_at,
            is_finished, finished_at, is_visible_when_finished, banner_id, owner_id
        FROM backup.prode_tournament
    """)

    # 11. prode_tournament_participants
    print("Migrating prode_tournament_participants ...")
    cur.execute("""
        INSERT INTO prode_tournament_participants
        SELECT * FROM backup.prode_tournament_participants
    """)

    # 12. prode_match_tournaments
    print("Migrating prode_match_tournaments ...")
    cur.execute("""
        INSERT INTO prode_match_tournaments
        SELECT * FROM backup.prode_match_tournaments
    """)

    # 13. prode_prediction
    print("Migrating prode_prediction ...")
    cur.execute("""
        INSERT INTO prode_prediction
        SELECT * FROM backup.prode_prediction
    """)

    # 14. prode_tournamentrankingsnapshot
    print("Migrating prode_tournamentrankingsnapshot ...")
    cur.execute("""
        INSERT INTO prode_tournamentrankingsnapshot
        SELECT * FROM backup.prode_tournamentrankingsnapshot
    """)

    # ------------------------------------------------------------------
    # Update sqlite_sequence for auto-increment tables
    # ------------------------------------------------------------------
    print("Updating sqlite_sequence ...")
    sequence_tables = [
        "users_user",
        "token_blacklist_outstandingtoken",
        "token_blacklist_blacklistedtoken",
        "prode_team",
        "prode_predefinedtournamenttemplate",
        "prode_match",
        "prode_templatematch",
        "prode_teamtranslation",
        "prode_tournament",
        "prode_tournament_participants",
        "prode_match_tournaments",
        "prode_prediction",
        "prode_tournamentrankingsnapshot",
    ]

    for tbl in sequence_tables:
        cur.execute(f"SELECT MAX(id) FROM {tbl}")
        max_id = cur.fetchone()[0]
        if max_id is not None:
            cur.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tbl,))
            cur.execute("INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)", (tbl, max_id))
        else:
            cur.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tbl,))

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")

    # Verify counts
    print("\n--- Verification ---")
    verify = [
        ("users_user", "backup.auth_user"),
        ("token_blacklist_outstandingtoken", "backup.token_blacklist_outstandingtoken"),
        ("token_blacklist_blacklistedtoken", "backup.token_blacklist_blacklistedtoken"),
        ("media_uploadedimage", "backup.media_uploadedimage"),
        ("prode_team", "backup.prode_team"),
        ("prode_predefinedtournamenttemplate", "backup.prode_predefinedtournamenttemplate"),
        ("prode_match", "backup.prode_match"),
        ("prode_templatematch", "backup.prode_templatematch"),
        ("prode_teamtranslation", "backup.prode_teamtranslation"),
        ("prode_tournament", "backup.prode_tournament"),
        ("prode_tournament_participants", "backup.prode_tournament_participants"),
        ("prode_match_tournaments", "backup.prode_match_tournaments"),
        ("prode_prediction", "backup.prode_prediction"),
        ("prode_tournamentrankingsnapshot", "backup.prode_tournamentrankingsnapshot"),
    ]

    for current_tbl, backup_tbl in verify:
        cur.execute(f"SELECT COUNT(*) FROM {current_tbl}")
        c = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM {backup_tbl}")
        b = cur.fetchone()[0]
        status = "OK" if c == b else "MISMATCH"
        print(f"{status}: {current_tbl}: current={c}, backup={b}")

    cur.execute("DETACH DATABASE backup")
    conn.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
