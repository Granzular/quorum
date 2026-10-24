# Quorum Backend — Agent Instructions

## 1. Project Overview

Quorum is an educational platform for members of a Computer Science Department.

The platform provides:

- **Library:** Academic and departmental resources currently sourced from Google Drive.
- **Community:** A blog where members can create and view posts, alongside departmental announcements, events, and related community features.

The frontend is maintained separately from the backend.

The project is under active development. Some functionality is incomplete, and some architectural or infrastructure improvements are intentionally deferred.

## 2. Technology Stack

- Python 3.13
- Django 6
- Django REST Framework
- SimpleJWT for JWT authentication
- SQLite for current development
- PostgreSQL planned for a future migration
- Google Drive API for resource indexing
- WhiteNoise

The project may contain dependencies or configuration for functionality that is not currently implemented or enabled. Inspect the existing implementation before relying on them.

## 3. Existing Application Structure

The project currently contains the following applications and configuration modules:

- `mysite/` — Django settings and root URL routing.
- `accounts/` — User accounts, authentication, profiles, and avatars.
- `library/` — Courses, academic resources, and Google Drive resource indexing.
- `community/` — Posts, comments, likes, and community-related functionality.
- `main/` — Root endpoint, resource synchronization operations, and other shared functionality.

Preserve these application boundaries unless a clear architectural reason justifies changing them.

Announcements and events belong to the `community` application unless the requirements or existing architecture provide a reason to organize them differently.

Inspect the actual source code before assuming that a feature, endpoint, dependency, or configuration is complete.

## 4. Development Principles

1. Extend the existing codebase rather than rebuilding it unnecessarily.
2. Prefer straightforward, maintainable Django and DRF solutions.
3. Follow established conventions when they are sound and appropriate.
4. Do not reproduce defective patterns merely for consistency.
5. Avoid unnecessary abstractions, premature optimization, and overengineering.
6. Do not invent requirements, business rules, API contracts, or existing functionality.
7. Do not introduce dependencies or external services without approval.
8. Preserve existing uncommitted work.
9. Do not commit, push, or discard changes unless explicitly requested.
10. Keep implementations proportionate to the project's current development stage.

## 5. Feature-Driven Development

Development proceeds feature by feature. Each task should have a clear scope, with requirements established before substantial implementation.

For substantial changes:

1. Inspect the relevant existing code and dependencies.
2. Establish the feature's requirements, expected behavior, and constraints.
3. Identify affected components, models, serializers, endpoints, and integrations.
4. Propose an implementation approach and identify significant risks.
5. Obtain approval before proceeding with substantial changes when the approach or requirements need agreement.
6. Implement the agreed solution.
7. Verify the result and review the changes.

Small, unambiguous changes may proceed directly to implementation.

Do not expand a focused task into a broad refactoring exercise.

## 6. Defects and Dependency Handling

Before implementing a feature, inspect the existing functionality on which it depends.

If a dependency contains a defect that would affect the requested feature, fix the underlying defect as part of the implementation.

### Quality of Fixes

- Investigate root causes before selecting a solution.
- Prefer maintainable fixes over superficial patches and temporary workarounds.
- Address relevant validation, data-integrity, authorization, and error-handling problems.
- Add appropriate tests or constraints to prevent regressions.
- Avoid unrelated fixes that unnecessarily expand the task.

### Architectural Problems

When an existing architecture is too tangled or fundamentally unsuitable for a sound implementation, do not continue accumulating patches.

Instead:

1. Explain the architectural problem.
2. Describe why a local fix would be inadequate.
3. Propose a suitable redesign and define its scope.
4. Identify migration, compatibility, and regression implications.
5. Obtain approval before undertaking the redesign.

Prefer the smallest architectural change that adequately addresses the underlying problem. Scalability means supporting reasonable future development without unnecessary complexity, not designing for hypothetical requirements.

### Classifying Existing Issues

Distinguish between:

- Confirmed defects in existing functionality.
- Security or data-integrity risks.
- Incomplete features.
- Intentionally deferred improvements.
- Requirements that need clarification.

Do not assume every unfinished implementation, unused dependency, or missing production configuration is a defect.

Prioritize the requested feature and its dependencies. Report significant unrelated findings rather than automatically fixing them.

## 7. Accounts, Authentication, and Permissions

The `accounts` application manages authentication and profile functionality.

Student profiles currently exist. Support for non-student profiles is planned.

Student and non-student profiles should use separate models without model inheritance, subject to reviewing the existing implementation and preserving necessary account relationships.

Use the existing JWT authentication infrastructure unless a change is required and approved.

Authentication and authorization must be enforced server-side.

- Validate ownership of user-controlled resources.
- Prevent unauthorized access to or modification of other users' data.
- Apply appropriate permissions to write operations and administrative actions.
- Do not assume that authentication alone authorizes an operation.
- Do not treat profile information supplied by a client as proof of identity or privilege.

Specific registration flows, profile fields, roles, and permission rules should be established when implementing the relevant features.

## 8. Application Responsibilities

### Library

The `library` application manages courses and academic resources, including resources indexed from Google Drive.

Preserve the existing integration where appropriate. Resource synchronization and other administrative operations must enforce appropriate authorization.

Ensure that searching, filtering, pagination, validation, and error handling behave consistently with the API contract.

Do not introduce additional storage, indexing, or synchronization infrastructure without a clear requirement.

### Community

The `community` application manages posts, comments, likes, announcements, events, and related community functionality.

Inspect the existing implementation before extending these features. Apply appropriate validation, ownership checks, permissions, and moderation rules.

Do not assume planned functionality is already implemented or invent its behavior.

## 9. API Design and Compatibility

Use Django REST Framework and follow established project conventions.

- Keep endpoint behavior and response structures consistent.
- Validate incoming data through appropriate serializers and application logic.
- Handle expected failures explicitly.
- Use suitable HTTP status codes.
- Implement filtering and pagination consistently.
- Enforce permissions at the appropriate level.
- Avoid breaking existing API contracts without an agreed reason.

The frontend is maintained separately. Before changing an endpoint, authentication flow, request format, response structure, or pagination behavior, inspect its existing contract and consider its consumers.

Identify breaking changes before implementation and coordinate any necessary frontend adjustments.

## 10. API Documentation

Use `drf-spectacular` for OpenAPI schema generation and API documentation, subject to the project's existing dependencies and configuration.

When implementing or modifying API endpoints, follow this workflow:

1. **Write meaningful docstrings** describing the endpoint's purpose and behavior.
2. **Define data structures** using serializers for request and response formats wherever appropriate.
3. **Use `@extend_schema`** to specify information that cannot be inferred reliably, such as custom parameters, request bodies, response schemas, and status codes.
4. **Generate and validate the OpenAPI schema** using the project's configured tooling.
5. **Check consistency** between the generated documentation and actual endpoint behavior, including permissions, validation, and response formats.

Do not document planned behavior as implemented functionality.

Keep API documentation accessible to developers and coding agents where the development environment permits. The machine-readable OpenAPI schema should be available for inspection and frontend integration when configured.

## 11. Database and Migrations

SQLite is the current development database. PostgreSQL is planned for a future migration.

- Prefer Django ORM features and portable database operations.
- Avoid unnecessary database-specific assumptions that would complicate migration.
- Inspect existing migrations before changing models.
- Generate migrations when model changes require them.
- Preserve existing data where possible.
- Do not casually rewrite migration history.
- Never reset or destroy existing data without explicit approval.
- Consider existing constraints, relationships, and migration implications before changing schemas.

Do not undertake the PostgreSQL migration until it is part of an agreed task.

## 12. Configuration and Security

Inspect the active settings module and environment configuration before running commands or changing deployment behavior.

Do not assume the default settings module is correctly configured.

- Keep secrets and credentials out of source control.
- Avoid exposing sensitive configuration in logs or API responses.
- Handle external service credentials and failures appropriately.
- Avoid making application startup unnecessarily dependent on external services.
- Preserve the current development workflow unless a change is required.
- Do not perform broad production hardening unless requested or necessary for the feature being developed.

Security and data integrity take priority when directly affected by the current task.

## 13. Code Comments and Docstrings

Comments and docstrings should serve as technical documentation for developers and maintainers.

- Explain purpose, intent, constraints, and non-obvious behavior.
- Explain why a non-obvious implementation exists rather than merely restating what the code does.
- Keep comments concise and accurate.
- Avoid conversational language, direct instructions to a particular developer, and references to the current conversation.
- Do not add comments that provide no meaningful information beyond the code itself.
- Update comments when the documented behavior changes.

Use meaningful names and clear code structure instead of relying on excessive comments.

## 14. Testing and Verification

Verify changes in proportion to their scope and risk.

1. Run relevant automated tests.
2. Add or update tests for new behavior and corrected defects where practical.
3. Run appropriate Django checks.
4. Check migration consistency when model changes are involved.
5. Validate generated API documentation when endpoints or schemas change.
6. Review the Git diff for regressions, unintended modifications, and unrelated changes.

Do not claim that a test, check, or verification step passed unless it was actually executed.

Because the project is under active development, do not require unrelated unfinished functionality to be completed before verifying a focused change.

## 15. Completion Report

After implementation, report:

- What changed.
- Which relevant defects were fixed.
- What checks and tests were executed and their results.
- Any remaining limitations or unfinished work.
- Any significant architectural concerns requiring a separate decision.

Keep the report factual. Clearly distinguish completed work from proposed improvements and unverified behavior.

## 16. Scope Control

Do not turn individual feature tasks into a complete rewrite, production-readiness audit, or implementation of unrelated planned functionality.

Preserve existing behavior where appropriate, fix defects that affect the requested feature, and seek approval before significant architectural changes.

The objective is to develop Quorum incrementally while maintaining correctness, security, maintainability, and a coherent architecture.