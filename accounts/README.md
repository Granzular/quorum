# Accounts and profiles

Quorum uses one CustomUser account and one Profile per member. Profile categories
describe membership; Django Groups and permissions control authorization.

## Account lifecycle

1. An administrator provisions an account with a complete profile and, for a
   student, an initial level.
2. The account is inactive and has no usable password. The administrator receives
   an activation uid and token to share privately with the user.
3. The user submits the uid, token, and a new password to activate the account.
   The JWT endpoints then provide login, token refresh, and refresh-token logout.

There is no public registration. No email delivery, approval state, role field,
or automatic group assignment is involved. Activation preserves any memberships
and permissions that an administrator assigned beforehand.

Provisioning through Django admin also requires a valid profile. It displays
activation credentials after creation. The CustomUser action **Issue activation
credentials for pending accounts** can issue fresh credentials if needed;
it requires change permission on CustomUser.

Tokens use Django's password-reset token utility and PASSWORD_RESET_TIMEOUT
(default: three days). Setting the password consumes the token; concurrent or
subsequent activation requests cannot reuse it. Passwords must satisfy the
configured Django password validators. A disabled existing account with a usable
password cannot use this activation flow to reactivate itself.

JWT access tokens last 30 minutes and refresh tokens last one day. Refresh rotates
the token and blacklists the submitted token. Changing an account password revokes
both existing access and refresh tokens. Logout blacklists the submitted refresh
token; its already-issued access token remains valid until its normal expiry.

## Profile fields

| Field | Student | Alumni | Staff |
| --- | --- | --- | --- |
| profile_type | student | alumni | staff |
| matric_no | Required, unique | Required, unique | Inapplicable |
| level | Required | Inapplicable | Inapplicable |
| graduation_year | Inapplicable | Required | Inapplicable |
| job_title | Inapplicable | Inapplicable | Required |
| dept | Defaults to Computer Science | Same | Same |
| avatar, bio, linkedin_url | Optional | Optional | Optional |

Levels are integers: 100, 200, 300, 400, or 500, matching the levels used by the
library. Administrators manage level changes manually. Graduation years are
integers from 1 through 9999. Job titles allow up to 128 characters, departments
64, and LinkedIn URLs 200. A LinkedIn URL uses ordinary URL validation.

Matriculation numbers retain both formats, CSC/00/0000 and 202412345678AB.
The CSC prefix is uppercase; the two final letters in the numeric format may
use either case. The matric_no name, 14-character maximum, and uniqueness
constraint are preserved. Staff profiles store NULL for the absent number,
allowing multiple staff accounts.

Model validation checks the complete category combination. API validation also
rejects explicitly supplied inapplicable fields, including null or empty values,
with errors keyed by the offending field.

## API

All paths below start with /api/accounts/.

| Method and path | Behavior and permissions |
| --- | --- |
| POST provision/ | Requires JWT, accounts.add_customuser, and accounts.add_profile. Creates an inactive account and profile. |
| POST student/register/ | Deprecated alias for administrative provisioning. |
| POST student/register/{freshman}/ | Deprecated alias with the same provisioning rules; the legacy path argument has no effect. |
| POST activate/ | Accepts uid, token, and password; no JWT required. |
| POST auth/token/ | Existing JWT login; inactive accounts cannot log in. |
| POST auth/token/refresh/ | Existing JWT refresh. |
| POST auth/logout/ | Requires JWT and the current account's refresh token; blacklists that refresh token. |
| GET student/manage-profile/ | Returns the authenticated account and nested profile. |
| PATCH student/manage-profile/{user_id}/ | Partially updates account fields and a nested profile object. |
| GET student/manage-profile/{user_id}/current/ | Legacy current-account action; always returns the authenticated account. |
| GET student/manage-profile/avatar/ | Returns the current avatar URL. |
| PUT student/manage-profile/avatar/ | Partially updates the current profile using multipart/form-data or form data. |

The student paths support every profile category. Current-profile and avatar
responses retain their status/data envelopes. PATCH retains its unwrapped
account response. Avatar files still use the avatar field and accounts/
upload directory. Existing read-only email and phone behavior is preserved.

Ordinary users may update only their own account/profile. To edit another
profile or change a level, the caller needs accounts.change_profile, either
directly or through a Group. Changing another account's username, first name,
or last name additionally requires accounts.change_customuser. Merely having a
staff profile, or setting CustomUser.is_staff, does not grant these API permissions.

Category changes use Django admin. The administrator must explicitly clear fields
belonging to the old category and provide the new required fields. API requests
cannot change an existing category. The same restrictions apply through the avatar
endpoint.

Django admin additionally requires an active account with is_staff. Profile
edits use its standard model permissions. Adding a CustomUser through UserAdmin
requires add_customuser, change_customuser, and add_profile. Group and permission
editing uses the existing Django authorization model.

### Provision a student

POST /api/accounts/provision/ with an authorized administrator's JWT:

~~~json
{
  "username": "member",
  "profile_type": "student",
  "matric_no": "CSC/24/1234",
  "level": 200,
  "bio": "Interested in distributed systems."
}
~~~

The 201 response is:

~~~json
{
  "username": "member",
  "activation": {
    "uid": "<encoded account id>",
    "token": "<activation token>"
  }
}
~~~

The response has Cache-Control: no-store. Supplying password during provisioning
returns a field error; the user chooses it during activation. For alumni, replace
level with graduation_year. For staff, omit matric_no and level and supply
job_title.

### Activate

POST /api/accounts/activate/:

~~~json
{
  "uid": "<encoded account id>",
  "token": "<activation token>",
  "password": "<new password>"
}
~~~

Success returns 200 with {"status": "success"}. Invalid, expired, or consumed
credentials return a token field error; invalid passwords return a password
field error. Activation does not automatically issue JWTs.

### Logout and throttling

POST /api/accounts/auth/logout/ with a valid access token:

~~~json
{
  "refresh": "<current refresh token>"
}
~~~

Success returns 204 without a response body. The refresh token must belong to the
same account as the access token. Invalid, expired, already-blacklisted, or
cross-account tokens return a refresh field error.

Authentication endpoints use scoped throttles. Development defaults are 10 login
requests/minute, 30 refresh requests/minute, 10 activation requests/minute, and
30 logout requests/minute per DRF client identity. Override them with
AUTH_LOGIN_THROTTLE_RATE, AUTH_REFRESH_THROTTLE_RATE,
AUTH_ACTIVATION_THROTTLE_RATE, and AUTH_LOGOUT_THROTTLE_RATE.

### Partial update

PATCH /api/accounts/student/manage-profile/{user_id}/:

~~~json
{
  "first_name": "Ada",
  "profile": {
    "bio": "Updated biography."
  }
}
~~~

Unchanged fields need not be resubmitted. Validation merges supplied profile
fields with stored values. An invalid profile prevents account fields from being
saved as well. Errors for the nested profile are nested under profile:

~~~json
{
  "profile": {
    "graduation_year": [
      "This field is not applicable to student profiles."
    ]
  }
}
~~~

Profile fields at the top level of this PATCH request are rejected with an
instruction to use the profile object. Avatar PUT uses flat profile fields.

## Compatibility and migration

Public signup has intentionally been replaced by administrative provisioning.
Clients must remove public registration and implement the activation request.
New provisioning requires an explicit category and its required fields, and no
longer accepts a password. Profile responses add the new fields. Frontend/mobile
applications are maintained separately and are not changed here.

Migration 0008_profile_categories adds the category fields. Migration
0009_backfill_legacy_profiles then assigns student to profiles whose profile_type
is NULL and defaults their missing level to 300. It then makes profile_type
non-nullable, so the database rejects NULL categories. Recorded levels and already
classified profiles are preserved. This is a one-time data backfill; new accounts
still require an explicit category and its required fields. Level remains nullable
for alumni and staff, where it does not apply.

Existing account relationships, passwords, activation state, matriculation
numbers, department values, avatars, and authorization data are preserved.
Migrated legacy profiles can be edited immediately. Administrators can correct
their category or level using Django admin when needed.

Reversing 0009 to 0008 retains the backfilled values and subsequent edits, because
they remain compatible with the 0008 schema and cannot safely be distinguished
from administrator-supplied values. Reapplying the migration preserves them.
Rolling back further to 0007 fails for staff profiles with NULL matric_no because
that older schema requires a matriculation number.
Scripts using the ORM directly should call full_clean(); Django save() does not
automatically run model validation.

mysite.settings uses mysite/db.sqlite3. Apply migrations with the intended runtime
settings; accounts.tests.settings uses an in-memory database and must not be used
to migrate development data. Adding the migration does not apply it automatically.
The ignored local .env file must define SECRET_KEY; deployed environments should
provide their own independently generated value through the process environment.

## Documentation and verification

The live OpenAPI schema is available at /api/schema/, with Swagger UI at
/api/docs/. The accounts-only generated schema is also stored in openapi.yaml
beside this document. It includes administrative provisioning, activation,
permission requirements, legacy aliases, and partial-update formats.

The account test settings use an in-memory SQLite database and a URL configuration
containing the real accounts routes and Django admin. They avoid importing the
unrelated Google Drive integration and do not require its credentials.

Run from the repository root:

~~~text
python manage.py test accounts --settings=accounts.tests.settings
python manage.py check --settings=accounts.tests.settings
python manage.py makemigrations accounts --check --dry-run --settings=accounts.tests.settings
python manage.py spectacular --settings=accounts.tests.settings --file accounts/openapi.yaml --validate --fail-on-warn
~~~

Tests cover API and admin provisioning, activation and JWT login, category
validation, partial updates, uniqueness, ownership, group permissions, avatars,
and migration of legacy data. No existing development records are used as test
data.

## Implementation files

| File | Purpose |
| --- | --- |
| models.py | Single categorized Profile, common fields, matriculation validator, and complete-state category validation. |
| serializers.py | Provisioning, activation, JWT refresh revocation, logout, partial-update validation, atomic account/profile writes, and response schemas. |
| permissions.py | Django model-permission checks for provisioning. |
| activation.py | Activation credential generation using Django's token utility. |
| views.py | JWT lifecycle, provisioning and activation endpoints, scoped throttles, ownership restrictions, and consistent avatar/profile validation. |
| urls.py | JWT login, refresh and logout routes, lifecycle routes, and secured legacy registration aliases. |
| admin.py | Inactive account provisioning with a required profile, activation credential issuance, and profile management. |
| migrations/0008_profile_categories.py | Additive schema changes that preserve existing profile data. |
| migrations/0009_backfill_legacy_profiles.py | Default legacy profiles to student and missing levels to 300, then disallow NULL categories. |
| ../mysite/settings.py | Enable the already installed drf-spectacular package and separate request schemas. |
| ../mysite/urls.py | Live schema and Swagger documentation routes. |
| openapi.yaml | Validated, generated accounts API contract. |
| README.md | Account lifecycle, API examples, migration guidance, and verification instructions. |
| tests/test_api.py | API validation, ownership, permissions, activation, JWT revocation/logout, throttling, and avatar regression tests. |
| tests/test_admin.py | Admin provisioning, profile category/level edits, and activation issuance permissions. |
| tests/test_models.py | Model validation, uniqueness, and account/profile relationship tests. |
| tests/test_migrations.py | Legacy defaults, account/profile preservation, JWT and profile access, and safe backfill reapplication. |
| tests/__init__.py, tests/settings.py, tests/urls.py | Test package and isolated database/URL configuration, replacing the former placeholder tests.py. |

## Verification on 2026-10-25

- All 88 account tests passed, including API, Django admin, model, and migration tests.
- The isolated Django system check reported no issues.
- The accounts migration consistency check found no missing migrations.
- The generated accounts schema validated with no warnings or errors.
- Git diff whitespace validation passed.

Remaining workspace configuration issues require separate follow-up:

- The database path differs from the populated database, as described above.
- The configured Google Drive credential path resolves to a missing file after
  the settings move. The verification override was not saved to configuration.
- mysite/asgi.py still names the removed mysite.settings.dev module.
- The project-wide migration check reports an existing, unmigrated change to
  library.Course ordering. Accounts migrations are consistent.
