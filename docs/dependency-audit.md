# Dependency audit

This audit records the final dependency classification after migration from
`requirements.txt` to `uv`. It is based on Python imports, Django settings,
project scripts and documentation, installed distribution metadata, and the
locked dependency graph. Packages installed in the existing `.venv` are not
automatically project dependencies.

## Direct runtime dependencies

| Distribution | Why it is direct |
| --- | --- |
| `Django` | Framework, ORM, settings, management commands, and tests. |
| `djangorestframework` | API views, serializers, routers, pagination, and tests. |
| `djangorestframework-simplejwt` | JWT authentication, token views, and blacklist app. |
| `django-cors-headers` | Installed app and CORS middleware/settings. |
| `drf-spectacular` | Schema generation, endpoint annotations, and documentation views. |
| `python-dotenv` | Provides the imported `dotenv.load_dotenv` API. |
| `whitenoise` | Static-files middleware and storage backend. |
| `cloudinary` | Installed app and directly imported upload API. |
| `django-cloudinary-storage` | Configured media-storage backends. |
| `google-api-python-client` | Directly imported Drive client and download APIs. |
| `google-auth` | Provides the directly imported service-account credentials API. |
| `Pillow` | Required by Django `ImageField` and imported by image-upload tests. |
| `uuid6` | Provides the `uuid7` model defaults used by library and community models. |

These packages are declared in `[project].dependencies`. `python-dotenv` is an
explicit runtime dependency, rather than an incidental transitive installation.

## Development dependencies

`ipython==9.12.0` is declared in `[dependency-groups].dev`. A default `uv sync`
installs it, while `uv sync --no-dev` omits it. IPython's support packages are
development transitives recorded in `uv.lock`; they are not runtime or direct
project dependencies.

The test suite directly imports Pillow, but Pillow is already a runtime
dependency because Django's `ImageField` requires it. No separate test-only
dependency is currently needed.

## Constrained transitive dependencies

The following packages are not used directly by Quorum. They remain constrained
to verified versions because declared runtime dependencies require them:

| Distribution | Dependency path |
| --- | --- |
| `httplib2==0.32.0` | `google-api-python-client` requires it directly and through `google-auth-httplib2`. |
| `proto-plus==1.29.0` | Required by `google-api-core`. |
| `protobuf==7.36.2` | Required by `google-api-core`, `proto-plus`, and `googleapis-common-protos`. |
| `pyparsing==3.3.3` | Required by `httplib2`. |

They belong in the resolved and constrained transitive graph, not in
`[project].dependencies`, unless Quorum begins using their APIs directly.

Other retained runtime transitives follow the same rule: a package need not be
imported by application code when it is required by a declared dependency.

## Excluded unused packages

No code, settings, script, or documented workflow uses these package groups,
and no remaining declared dependency requires them. They are not retained only
for possible future features:

| Unused top-level package or group | Packages pulled in only for that group |
| --- | --- |
| `celery` | `amqp`, `billiard`, `click-didyoumean`, `click-plugins`, `click-repl`, `kombu`, `python-dateutil`, `tzlocal`, `vine`, and their otherwise unneeded support packages. |
| `channels` / `channels-redis` | `redis` and `msgpack`; no channel layer, routing, or Channels app is configured. |
| `daphne` | `autobahn`, `cbor2`, `Twisted`, `txaio`, `ujson`, `py-ubjson`, and the otherwise unneeded Twisted support stack. |
| `dotenv` | A distribution distinct from `python-dotenv`. It only depends on `python-dotenv` and is unnecessary because Quorum declares `python-dotenv` directly. |

Before exact synchronization, the old environment also contained packages from
those excluded groups. `uv sync` pruned them because they are not present in
`pyproject.toml` or `uv.lock`.

## Removed environment-only packages

| Distribution | Verified result |
| --- | --- |
| `pyOpenSSL==26.0.0` | Previously installed as a top-level package. No package in the locked runtime or development graph requires it, and exact synchronization removed it. |
| `service-identity==24.2.0` | Previously installed as a top-level package. No package in the locked runtime or development graph requires it, and exact synchronization removed it. |

This conclusion comes from both sides of the dependency graph: installed-package
metadata reports them as roots, and the complete locked graph contains neither
distribution. Their exclusion is therefore not based solely on the absence of
application imports.

`dotenv==0.9.9` was likewise an environment-only package and was removed by
exact synchronization. The project instead declares `python-dotenv==1.2.4`,
which provides the imported `dotenv` module and `load_dotenv` function.

`pip` and `uv` are environment-management tools and are intentionally not
application dependencies. Standard-library modules and local project modules
also do not belong in the dependency manifest.

## Version policy

Runtime and development direct dependencies are explicitly pinned. Runtime
transitive constraints preserve the verified migration versions, while
`uv.lock` records the complete resolution, including IPython's development-only
transitives.

## Migration verification

- `uv lock --check` confirmed that `uv.lock` is synchronized with
  `pyproject.toml`, including the default development group.
- The locked graph resolves 61 packages including the local project, with
  `ipython==9.12.0` marked as belonging to the `dev` group.
- Default and `--no-dev` synchronization plans were checked to confirm that
  IPython is included only in the default development environment.
- Exact `uv sync` completed, and a subsequent dry run reported that it would
  make no changes.
- `uv pip check` reported that all installed packages are compatible.
- `uv run --active --offline --locked python manage.py check`
  reported no issues using the active project settings.
- The complete 149-test suite passed with the repository's documented isolated
  test settings: `uv run python manage.py test --settings=accounts.tests.settings`.

The synchronized `.venv` no longer contains the excluded application-package
residue. `pip` and `uv` remain environment-management tools rather than project
dependencies.
