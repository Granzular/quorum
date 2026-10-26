# Quorum Backend

Backend API for **Quorum**, an academic resource-sharing and community platform designed for the Computer Science Department.

Quorum brings academic resources, departmental information, and community interactions into a single platform accessible through web and mobile applications.

## About Quorum

Academic resources and departmental communications are often distributed across multiple channels, making information difficult to organize, discover, and retrieve.

Quorum aims to address this by providing a centralized platform for students and other departmental members to access educational materials, share information, and participate in their academic community.

The platform focuses on two major areas:

### Academic Resource Library

An organized academic library powered by Google Drive.

The library provides a structured interface for discovering and accessing educational resources, with support for:

- Course listings and details
- Academic resource listings
- Resource searching
- Paginated results
- Google Drive resource indexing

Google Drive serves as the underlying file storage system, while the Quorum backend manages the application's resource indexing and API access.

### Community

A departmental community space designed for communication, information sharing, and engagement.

The community supports:

- Publishing and accessing posts
- Commenting on posts
- Liking posts

The broader product vision includes departmental announcements and information about events, helping members stay informed and connected.

## Application Ecosystem

Quorum consists of three applications that work together:

| Application | Responsibility |
|---|---|
| Backend | API services, authentication, data management, resource indexing, and community operations |
| Frontend | Web interface for accessing Quorum |
| Mobile | Mobile interface for accessing Quorum |

This repository contains the **backend application**.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.13 | Programming language |
| Django 6 | Backend framework |
| Django REST Framework | REST API development |
| SimpleJWT | JWT authentication |
| SQLite | Database |
| Google Drive API | Academic resource storage integration |
| WhiteNoise | Static file serving |

## Project Structure

The backend is organized into Django applications with distinct responsibilities.

```text
quorum-backend/
├── mysite/
├── accounts/
├── library/
├── community/
├── main/
└── manage.py
```

### Applications

**`mysite`**

Contains the Django project configuration and application-level settings.

**`accounts`**

Handles user accounts and identity-related functionality, including authentication, user profiles, and avatars.

**`library`**

Manages academic courses, resources, search, and Google Drive indexing.

**`community`**

Handles community posts and interactions, including comments and likes.

**`main`**

Provides general application functionality, including the root JSON response and administrative synchronization functionality.

## Backend Features

### Authentication and Accounts

- User account management
- JWT-based authentication
- User profiles
- Profile avatars

### Academic Library

- Course listings
- Course and resource details
- Paginated resource retrieval
- Resource search
- Google Drive indexing

### Community

- Community posts
- Post comments
- Post likes

### Administration

- Django administrative interface
- Administrative resource synchronization through `/sync/`

The synchronization endpoint is restricted to authorized administrative access.

## API Architecture

Quorum exposes a REST API using Django REST Framework.

The backend provides API functionality for accounts, academic resources, and community interactions.

JWT authentication is supported through SimpleJWT.

The API's actual routes, request and response structures, validation rules, permissions, and pagination behavior are defined by the implementation.

Refer to the project's URL configuration and API schema, where available, for authoritative endpoint documentation.

## Google Drive Integration

Quorum uses Google Drive as the underlying storage system for academic resources.

The backend integrates with the Google Drive API to index resources and make them discoverable through the academic library.

This separates file storage from the application's resource discovery and organization functionality.

## Local Development

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Git
- Access to the required project configuration and credentials

### Clone the Repository

```bash
git clone <repository-url>
cd quorum-backend
```

Replace the repository URL with the actual backend repository address.

### Install Dependencies

```bash
uv sync --locked
```

Runtime dependencies are declared in `[project].dependencies`, while
development-only tools are declared in `[dependency-groups].dev`. `uv.lock`
records the resolved dependency graph. By default, `uv sync` installs both the
runtime dependencies and the development group.

For a runtime-only environment without development tools, use:

```bash
uv sync --locked --no-dev
```

`uv` creates and synchronizes `.venv`. Run project commands through `uv run`;
activating the environment is optional.

To activate it in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On Linux/macOS:

```bash
source .venv/bin/activate
```

### Configure the Environment

Configure the required Django settings and Google Drive credentials according to the project's existing configuration.

Keep credentials, secret keys, and other sensitive values outside version control.

### Backend Logging

Backend logs use one JSON object per line on standard output. Application log
levels default to `DEBUG` in development and `INFO` when `DEBUG=false`; set
`LOG_LEVEL` in the process environment or ignored `.env` file to override them.
Each request receives a server-generated ID returned in `X-Request-ID`.

See [the logging guide](docs/logging.md) for the schema, request correlation,
safe logging conventions, configuration, and focused verification commands.

### Media Storage

Cloudinary stores profile avatars and existing community/library uploaded files
through Django's storage backends. Configure `CLOUDINARY_URL` or the individual
Cloudinary credential environment variables, then apply the new migrations.
Static files continue to use WhiteNoise.

See [the media storage guide](docs/media-storage.md) for configuration, feature
folders, explicit cleanup behavior, migration state, and verification details.

### Apply Database Migrations

```bash
uv run python manage.py migrate
```

### Start the Development Server

```bash
uv run python manage.py runserver
```

Run the full test suite with:

```bash
uv run python manage.py test --settings=accounts.tests.settings
```

By default, Django's development server is accessible at:

`http://127.0.0.1:8000/`

## Development Guidelines

Development follows a feature-by-feature workflow.

Each feature should be implemented within the existing project architecture and conventions.

When a feature depends on defective existing functionality, the underlying defect should be addressed as part of that feature's implementation.

Changes should prioritize correctness, maintainability, and scalability rather than temporary workarounds.

Significant architectural changes should be reviewed and approved before implementation.

For repository-specific development instructions and agent behavior, refer to `AGENTS.md`.

## Project Status

**Status: Active Development — Prototype**

Quorum is under active development.

The backend currently provides foundational functionality for authentication, academic resource management, Google Drive integration, and community interactions.

Additional functionality and refinements will be developed incrementally as the project progresses.

## Project Vision

Quorum aims to become a unified digital space for academic resource discovery and departmental community engagement.

By combining an organized academic library with community publishing and interaction, the platform seeks to make departmental information easier to access and academic collaboration more convenient.
