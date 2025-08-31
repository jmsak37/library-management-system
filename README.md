# Library Management System

**Author:** Julius  
**Repository:** https://github.com/jmsak37/library-management-system  
**License:** MIT

---

## 📘 Overview

A simple RESTful backend API for managing library resources (Authors, Books, Borrow transactions). Built with **Django + Django REST Framework** and demonstrates authentication (JWT), CRUD operations, business logic for borrowing/returning books, and a lightweight frontend demo (`frontend.html`).

This README includes quick setup, API examples, admin notes and troubleshooting tips (including Git push problems you encountered).

---

## ✨ Key features

- User registration and JWT authentication (`djangorestframework-simplejwt`)
- CRUD for Authors and Books (unique ISBNs, copies tracking)
- Borrow & Return endpoints with business rules:
  - Only borrow if `copies_available > 0`
  - One active borrow per user per book
  - Copies count updates on borrow/return
- User borrow history (`/api/my-borrows/`) and admin listing of all borrows
- Claims handling: users can submit "saw" or "returned" claims with optional payment notes (e.g. M-Pesa code) and admins can approve/decline
- Pagination, search and filtering on books
- Simple frontend demo: `library/templates/frontend.html` or `frontend.html` in repo root
- Helpful admin flows for approving fines and marking returns

---

## 🛠 Tech stack & versions

- Python 3.12 (recommended)
- Django 4.x
- Django REST Framework
- djangorestframework-simplejwt (JWT)
- django-filter (filtering)
- drf-yasg or similar for Swagger (optional)
- SQLite for local dev (Postgres recommended for production)

Check `requirements.txt` for exact pinned versions used in the project.

---

## 🚀 Quick start (local)

1. Clone the repository (if not already):

```bash
git clone https://github.com/jmsak37/library-management-system.git
cd library-management-system
```

2. Create & activate virtual environment

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Create a `.env` (recommended) or set env variables as needed:

```
SECRET_KEY=replace-this-with-a-secret
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=127.0.0.1,localhost
```

5. Apply migrations and create superuser (if you want custom admin):
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

6. Run the dev server
```bash
python manage.py runserver
```

Open the API docs (if enabled) at `http://127.0.0.1:8000/swagger/` (or `http://127.0.0.1:8000/redoc/`).

---

### 🔑 Default Admin Login (development convenience)

> After migrations you can use this pre-set admin account to log in (only if you added it or seeded it in your database). If you did not create it, use `createsuperuser` instead.

- **Registration number:** `admin`  
- **Password:** `1234`

> ⚠️ **Security note:** Do not use these credentials in production. If you commit or share, change the password immediately in the Django admin or re-create a secure superuser.

---

## 📌 Important API endpoints (examples)

Base API root: `http://127.0.0.1:8000/api`

- Obtain JWT token: `POST /api/token/`  
  Body: `{ "username": "...", "password": "..." }` → returns `{ access, refresh }`

- Register: `POST /api/auth/register/`  
  Body: `{ "username": "...", "password": "..." }`

- Books (list/create): `GET/POST /api/books/`  
- Authors (list/create): `GET/POST /api/authors/`

- Borrow a book (user): `POST /api/borrow/`  
  Body: `{ "book_id": 1, "due_date": "YYYY-MM-DD" }`

- Return a book (user/admin): `POST /api/return/`  
  Body: `{ "borrow_id": 1 }`

- Report lost: `POST /api/report-lost/`  
  Body: `{ "borrow_id": 1 }`

- Approve fine (admin): `POST /api/approve-fine/`  
  Body: `{ "borrow_id": 1 }`

- Claims: `GET/POST /api/claims/` and approve via `POST /api/claims/<id>/approve/` or fallback `POST /api/claims/approve/` with `{ claim_id, approve }`

- My borrows (user): `GET /api/my-borrows/`

> Add `Authorization: Bearer <access_token>` header for protected endpoints.

Example `curl` to borrow a book as an authenticated user:

```bash
curl -X POST http://127.0.0.1:8000/api/borrow/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"book_id": 3, "due_date":"2025-09-01"}'
```

---

## 🧪 Running tests

Run Django tests:

```bash
python manage.py test
```

---

## 🧩 Common troubleshooting & tips

### 1) "Could not load users (backend may not expose /users/)"
The UI is a demo and tries multiple possible endpoints to list users (`/api/users/`, `/api/auth/users/`, `/api/accounts/users/`). If your backend doesn't expose a users-list endpoint, either:

- Enable or create a users list endpoint in Django REST Framework (e.g., register a `UserViewSet` under `/api/users/`), or
- Remove the UI call, or adjust frontend to the actual users endpoint in `library/templates/frontend.html` or your frontend file.

Example `urls.py` for user listing (add to your `library/urls.py` or project urls):

```py
from django.contrib.auth import get_user_model
from rest_framework import viewsets, routers, permissions
from rest_framework.serializers import ModelSerializer

User = get_user_model()

class SimpleUserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ('id','username','email','is_staff')

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.filter(is_staff=False).order_by('username')
    serializer_class = SimpleUserSerializer
    permission_classes = [permissions.IsAuthenticated]  # or IsAdminUser for admin only

# then register in urls: router.register(r'users', UserViewSet, basename='users')
```

> The project UI attempts several endpoints because different projects organize user routes differently (e.g., `dj-rest-auth`, `django-rest-auth`, or custom). Pick one and update both backend and frontend consistently.

### 2) Git push rejected (non-fast-forward)
You saw errors like `! [rejected] main -> main (fetch first)` when pushing. This means the remote has commits you don't have locally. Fix with:

```bash
# fetch remote changes and rebase your local commits on top
git fetch origin
git rebase origin/main

# if there are conflicts, resolve them, then continue rebase:
git rebase --continue

# push after rebase
git push origin main
```

If you prefer to merge instead of rebase:

```bash
git pull origin main --no-rebase  # merges remote into local
# resolve conflicts, commit, then push
git push origin main
```

**Force-push only if you understand the consequences** (it overwrites remote history):

```bash
git push --force origin main
```

### 3) Template files are missing on GitHub

If `library/templates/frontend.html` is not in the remote repository:

- Ensure it exists locally and is not ignored by `.gitignore`.
- Check `git status` and `git add path/to/file` to stage it.
- Commit and then pull first (see above) before pushing.

Example:

```bash
git add library/templates/frontend.html
git commit -m "Add frontend template"
git pull --rebase origin main  # integrate remote changes first
git push origin main
```

If Windows/OneDrive line ending warnings appear (`LF will be replaced by CRLF`), you can ignore them or set `.gitattributes` to normalize line endings.

### 4) Default admin account not created automatically
The README shows default admin credentials as a convenience note. If you did not add such a seeded user in migrations or fixtures, create superuser manually:

```bash
python manage.py createsuperuser --username admin --email you@example.com
# then set password to 1234 (or a secure password)
```

---

## ✅ Admin guidance (what admin can do)

- Create authors and books in the admin or via API.
- Add copies to existing books by updating `copies_available` (example endpoint: `PATCH /api/books/{id}/`).
- Review & approve claims in `/api/claims/` (approve clears/adjusts fines and may mark borrowed -> returned).
- Use the frontend demo to view claims and all borrows (admin only).

---

## 📞 Contact & support

If you need help, email: `jmsak37@gmail.com` (as requested).

---

## ⚖️ License

This project is released under the MIT License. See `LICENSE` for details.
