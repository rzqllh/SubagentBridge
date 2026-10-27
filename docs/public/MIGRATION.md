# SQLite migration: legacy naming to Simpul

Version 2 introduces native `simpul_*` tables. Earlier `orca_*` tables were historical internal names, not an embedded Cindy database or runtime dependency.

## Safe behavior

On opening a legacy file, `TeamStore` inspects legacy table objects after acquiring `BEGIN IMMEDIATE`, creates the new schema and copies compatible rows in a transaction. A separate SQLite online backup connection captures a consistent committed snapshot, validates it with `PRAGMA integrity_check`, and preserves previous backups using non-colliding filenames.

The migration compares all mapped values, checks application-level references, and rolls back if a conflict is found. Legacy compatibility SQL views are **read-only**; the Python `OrcaStore` alias can still write via the native API. A view is not a writable legacy table.

Mixed older queue schemas may include only some optional columns. Migration preserves each present `dedup_key`, `priority` and `steering_json` independently and assigns defaults only where a column is absent.

## Operator checklist

1. Stop all writers to the relevant database and independently back up the SQLite database using SQLite's backup API.
2. Install a versioned Simpul build and open the database in a controlled environment.
3. Inspect migration exceptions. A conflict is a **stop condition**, not an invitation to discard data.
4. Verify row counts, application behavior and expected team/queue entries, and retain `.pre_migration*.bak` files before production cutover.
5. Never delete `orca_*` tables or backup files manually as a shortcut, and never run forceful Git worktree cleanup against unreviewed user files.

Rollback of the migration transaction restores the pre-migration schema on error; it does not automatically undo later legitimate application writes. Restoring a saved pre-migration backup after further writes would overwrite those later changes. Have a separate restore decision and procedure.
