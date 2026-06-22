# User Import And Export

The Settings page provides an administrator-only user archive workflow. It exports and restores every column stored on the `users` table:

- `id`
- `email`
- `password_hash`
- `role`
- `is_active`
- `created_at`
- `updated_at`

This is a complete user-record archive, not a full database backup. Related broker accounts, credentials, copy groups, sessions, orders, watchlists, and trading history are not included.

## Security Boundary

Both endpoints require an authenticated `ADMIN` user. The controls are hidden from non-admin users, but backend authorization remains the enforcement boundary.

The archive contains bcrypt password hashes. Although it does not contain plaintext passwords, possession of a hash enables offline password-guessing attempts. Treat exported JSON as sensitive credential material:

- store it only in an encrypted, access-controlled location;
- do not commit it to Git;
- do not send it through chat, email, or untrusted file-sharing services;
- delete temporary browser downloads after completing a transfer;
- rotate passwords if an archive is exposed.

Export and import actions create `users.export` and `users.import` audit events. Audit metadata contains counts and archive version only; it does not contain password hashes.

## Archive Format

The file is versioned JSON:

```json
{
  "format": "sharekhan-copy-trader.users",
  "version": 1,
  "exported_at": "2026-06-22T12:00:00Z",
  "users": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "email": "operator@example.com",
      "password_hash": "$2b$...",
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Validation rules:

- format must be `sharekhan-copy-trader.users` and version must be `1`;
- archives contain between 1 and 10,000 users;
- IDs and lowercased emails must be unique within the file;
- password hashes must have the bcrypt format used by this application;
- timestamps must include a timezone and `updated_at` cannot precede `created_at`.

## API

Export all user records:

```http
GET /users/export
Authorization: Bearer {admin_token}
```

The response uses `Cache-Control: no-store` and includes a timestamped JSON attachment filename.

Import an archive:

```http
POST /users/import
Authorization: Bearer {admin_token}
Content-Type: application/json

{archive_json}
```

Response:

```json
{
  "total": 3,
  "created": 1,
  "updated": 1,
  "unchanged": 1
}
```

## Import Behavior

Import is an all-or-nothing upsert by user UUID:

- a missing UUID creates a user with every archived field preserved;
- an existing UUID updates every field when at least one value differs;
- an identical record is counted as unchanged;
- users absent from the archive are not deleted or modified;
- an email already owned by a different UUID rejects the entire import with `409`;
- duplicate IDs/emails or malformed records reject the request with `422`;
- the current administrator cannot import a record that deactivates or demotes their own account.

The final database unique constraint remains the last concurrency guard. A late uniqueness conflict rolls back the import and returns `409`.

## Frontend Workflow

1. Sign in as an administrator and open `/settings`.
2. In User Archive, select **Export Users** to download a formatted JSON file.
3. For restore or transfer, select **Choose Archive** and pick a JSON file up to 10 MB.
4. Select **Import Users** and confirm the full-field update warning.
5. Review the returned Total, Created, Updated, and Unchanged counts.

Non-admin users do not see the User Archive card and receive `403` if they call the endpoints directly.

## Verification

Automated coverage is in `apps/api/tests/test_user_archive.py`. It checks full-field export, create/update/unchanged counts, identity conflicts, current-admin protection, and schema rejection for plaintext or duplicate identities.
