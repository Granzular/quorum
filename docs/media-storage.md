# Cloudinary media storage

Quorum uses Django's `STORAGES` registry with `django-cloudinary-storage` 0.4.0.
The adapter is pinned in `requirements.txt` to the maintained upstream revision
that declares Django 6 compatibility. Static files remain on WhiteNoise and are
not uploaded to Cloudinary.

## Configuration

Configure either `CLOUDINARY_URL` or all three individual variables:
`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
`CLOUDINARY_API_SECRET`. The existing `load_dotenv()` setup can load them from
the ignored `.env` file. Keep all credentials outside source control.

| Storage alias | Backend | Use |
| --- | --- | --- |
| `default` | `DynamicFolderMediaCloudinaryStorage` | Profile avatar images. |
| `files` | `DynamicFolderRawMediaCloudinaryStorage` | Existing generic community and library files. |
| `staticfiles` | WhiteNoise `CompressedManifestStaticFilesStorage` | Static and admin assets. |

Generic `FileField` models use the migration-serializable
`main.media_storage.file_storage` callable to resolve the `files` alias. The
raw backend preserves the existing ability to store arbitrary file types.

`CLOUDINARY_STORAGE['PREFIX']` is empty, so the adapter does not add a
`media/` prefix to new upload paths.

## Folders and asset identity

Cloudinary is configured in dynamic folder mode. Quorum-managed media follows
the centralized `quorum/<feature>/<asset-type>/` convention:

| Category | Organizational folder |
| --- | --- |
| Account avatars | `quorum/accounts/avatars/` |
| Community post media | `quorum/community/posts/` |
| Library resource files | `quorum/library/resources/` |
| Planned library covers | `quorum/library/covers/` |

The cover path reserves the project convention; no cover field or upload flow
is implemented.

The upstream adapter derives Cloudinary's legacy `folder` upload option from
the directory portion of Django's generated upload name. Live verification
showed that this caused the organizational path to prefix the returned public
ID in the configured Dynamic Folder Mode account.

The project storage subclasses preserve the adapter's Django storage behavior
but send the directory as `asset_folder` and explicitly set
`use_asset_folder_as_public_id_prefix=False`. Cloudinary therefore handles
organizational placement independently and returns a folderless `public_id`.
Django stores that exact returned value. Retrieval and deletion continue using
the stored value without rebuilding it from an asset folder.

The storage sends `use_filename=True` without an explicit `public_id`,
`overwrite`, or `unique_filename` option. Cloudinary's default unique-filename
behavior therefore gives repeated filenames distinct identities. No upload
preset is configured by the project or current environment.

No user, record, or upload-specific folders are created. Existing community
and library fields were assigned convention-compliant folders without adding
new feature endpoints or changing their authorization behavior.

## Explicit file lifecycle

`Profile`, `Content`, and `Resource` route model saves through
`save_with_file_cleanup()`. The helper locks and reads the previous stored
reference inside the database transaction, performs the normal Django save,
and schedules deletion of a replaced or cleared file with
`transaction.on_commit()`. Unchanged fields and fields excluded by
`update_fields` are not deleted.

Those models and `CustomUser` route instance deletion through
`delete_with_file_cleanup()`. Their managers use `FileCleanupQuerySet` so
queryset deletion, admin bulk deletion, cascades, and fast-delete querysets are
also inspected before records are removed.

Cleanup calls the captured Django storage object's `delete(name)` method. It
checks all file fields using that storage before deletion and preserves names
that still have a database reference. A storage/name pair is scheduled only
once per deletion operation. URL-shaped, absolute, and traversal-like values
are rejected rather than sent to storage.

Cleanup failures do not reverse a committed database change. They are logged
through the existing structured JSON logger as `media.cleanup_failed`, using a
fingerprint instead of the original stored name. Invalid references use
`media.cleanup_invalid_reference`.

Database and storage operations cannot be fully atomic. A database rollback
prevents deletion of the old file, but a replacement uploaded before a later
rollback may be orphaned. A process failure after commit but before an
`on_commit()` callback runs may also leave an orphan. The project does not add
workers, retries, or orphan scans for these cases.

Direct `QuerySet.update()`, `bulk_update()`, raw SQL, `FieldFile.delete()`, and
direct storage calls bypass the model lifecycle helpers. Existing upload flows
use normal model saves and deletes. The one administrative legacy-avatar
cleanup intentionally used a direct database update so no storage deletion was
attempted.

## Existing media and migrations

The development database contained one obsolete avatar reference under the
legacy `accounts/` path. It was cleared without changing other profile fields
and without invoking storage deletion. No corresponding physical file was
present in either the configured media root or the repository media directory.
No community or library stored-file references were present.

The new migrations were confirmed unapplied before consolidation and were then
applied successfully to the development database. There is one media migration
per affected app:

- `accounts` records the final avatar path and cleanup-aware user manager.
- `community` records the final post-media path and raw storage callable.
- `library` records the final resource-file path and raw storage callable.

These state-only field changes do not upload, move, rename, or delete assets.

The pre-existing `library.Course` model ordering is absent from migration
state, so a project-wide migration check still proposes an unrelated
`AlterModelOptions`. That discrepancy is outside the media-storage task.

## Verification

Verification completed on 2026-10-25:

- The combined account, logging, and media suite passed all 149 tests: 119
  existing tests and 30 focused media tests.
- Django system checks passed.
- The OpenAPI schema generated and validated without warnings or errors.
- Account and community migration consistency checks passed.
- The library migration check reported only the pre-existing `Course` ordering
  discrepancy described above.
- The migration dependency graph loaded successfully with the consolidated
  migrations.
- `pip check` and `git diff --check` passed.
- The obsolete avatar reference was confirmed empty after cleanup.
- A live upload through Django storage reported the organizational folder as
  `quorum/accounts/avatars` and returned a public ID without that prefix.
- Deletion through Django storage returned success, and Cloudinary metadata
  confirmed that the disposable asset was removed.
- Retrieval through Django storage was attempted but blocked by the execution
  environment's outbound proxy (`ProxyError`).

The focused tests use dummy credentials, mocked Cloudinary operations, and
in-memory or filesystem storage. They verify `asset_folder` configuration,
explicit separation from the public ID prefix, provider-returned identities,
exact stored-name retrieval and deletion, transaction boundaries, cascades,
shared references, and structured failure logging.

## Remaining limitation

Live folder placement, public-ID separation, and deletion are verified.
Delivery and retrieval remain unverified because the execution environment's
proxy rejected the Cloudinary delivery request.
