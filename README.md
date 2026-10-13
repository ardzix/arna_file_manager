# Backend Quick Start

## Stack

- Django + DRF
- PostgreSQL
- S3-compatible storage via `boto3`

## Setup

1. Create a virtual environment:

```powershell
python -m venv .venv
```

2. Activate it (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Confirm Python is from the venv:

```powershell
python -c "import sys; print(sys.prefix)"
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Create `.env` from `.env.example` and set real values.
6. Ensure PostgreSQL is running.
7. Run migrations:

```bash
python manage.py migrate
```

8. Start server:

```bash
python manage.py runserver
```

## Key Endpoints

- `POST /api/files/upload`
- `POST /api/files/{file_id}/parts/presign`
- `POST /api/files/{file_id}/complete`
- `POST /api/files/{file_id}/abort`
- `GET /api/files/{file_id}`
- `PATCH /api/files/{file_id}`
- `POST /api/files/{file_id}/move`
- `POST /api/folders`
- `GET /api/folders/{folder_id}/children`
- `GET /{uuid}` stable URL resolve

## Notes

- Auth requires an SSO RS256 token with issuer `https://sso.arnatech.id` and audience
  `storage`. Humans and devices obtain it from `/api/v1/devices/resource-token/`.
- APIs are also available under `/api/v1/`; existing `/api/` routes remain aliases.
- [Device and tenant access](docs/DEVICE_TENANT_ACCESS.md) describes permissions,
  ownership, introspection credentials, migrations and isolated tests.
- If S3 credentials are not configured, presign and completion paths return development placeholder URLs and IDs.
