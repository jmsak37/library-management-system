# Library Management System — Backend (Django + DRF)

**Author:** Julius  
**Repository:** https://github.com/jmsak37/library-management-system  
**License:** MIT

A simple RESTful backend API for managing library resources (Authors, Books, Borrow transactions).  
This project is a capstone backend built with **Django + Django REST Framework** and demonstrates authentication, CRUD operations, business logic for borrowing/returning books, tests, API docs (Swagger), pagination & filtering, and deployment readiness.

---

## Key features
- User registration and JWT authentication (djangorestframework-simplejwt)  
- CRUD for Authors and Books (unique ISBNs, copies tracking)  
- Borrow & Return endpoints with business rules:
  - Only borrow if `copies_available > 0`
  - One active borrow per user per book
  - Copies count updates on borrow/return
- User borrow history (`/api/my-borrows/`) and admin listing of all borrows
- Pagination, search and filtering on books
- API documentation with Swagger (drf-yasg) at `/swagger/`
- Unit tests covering main flows and edge cases
- Production-ready artifacts: `Procfile`, `requirements.txt`

---

## Repo structure
```
config/                  # Django project
library/                 # Django app (models, views, serializers, tests)
docs/
  ├─ ERD.png             # ERD diagram
  └─ api_endpoints.md
manage.py
requirements.txt
Procfile
README.md
```

**ERD image:** `docs/ERD.png` (included in repo)

---

## Tech stack & versions
- Python 3.12 (recommended)  
- Django 4.x  
- Django REST Framework  
- djangorestframework-simplejwt (JWT)  
- django-filter (filtering)  
- drf-yasg (Swagger)  
- SQLite for local dev (Postgres recommended for production)

---

## Quick start (local)

> Run these commands from the project root (where `manage.py` lives).

1. Create & activate virtual environment
```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\\Scripts\\Activate.ps1
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Create environment file (example `.env`)
```
SECRET_KEY=replace-this-with-a-secret
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=127.0.0.1,localhost
```
*(The project can read env vars with `django-environ` if configured.)*

4. Apply migrations and create superuser
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

5. Run the server
```bash
python manage.py runserver
```

Open the interactive API docs at:  
`http://127.0.0.1:8000/swagger/`

---

## Running tests
```bash
python manage.py test
```
Tests include borrow/return happy path and edge cases (no copies, double borrow attempts, invalid requests).

---

## API — quick endpoints

**Auth**
- `POST /api/auth/register/` — register user  
- `POST /api/token/` — obtain JWT (username + password)  
- `POST /api/token/refresh/` — refresh token

**Authors**
- `GET  /api/authors/`
- `POST /api/authors/` (admin for unsafe methods)
- `GET  /api/authors/{id}/`
- `PUT  /api/authors/{id}/`
- `DELETE /api/authors/{id}/` (admin only)

**Books**
- `GET  /api/books/` — filters: `?available=true`, `?search=term`, `?page=`
- `POST /api/books/` (admin for unsafe methods)
- `GET  /api/books/{id}/`
- `PUT  /api/books/{id}/`
- `DELETE /api/books/{id}/` (admin only)

**Borrow / Return**
- `POST /api/borrow/` — `{ "book_id": <id> }` (auth required)
- `POST /api/return/` — `{ "borrow_id": <id> }` (auth required)
- `GET /api/my-borrows/` — list user borrows
- `GET /api/borrows/` — admin-only: list all borrows

For full interactive docs and request/response examples use `/swagger/`.

---

## Example `curl` requests

1. Register
```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"password123"}'
```

2. Obtain JWT
```bash
curl -s -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}'
```

3. Create an author (admin)
```bash
curl -s -X POST http://127.0.0.1:8000/api/authors/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name":"George Orwell","birth_date":"1903-06-25"}'
```

4. Borrow a book
```bash
curl -s -X POST http://127.0.0.1:8000/api/borrow/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"book_id":1}'
```

---

## Deployment notes
- `Procfile` is provided for Heroku: `web: gunicorn config.wsgi --log-file -`  
- Use Postgres in production and set `DATABASE_URL`, `SECRET_KEY`, `DEBUG=False`, and `ALLOWED_HOSTS` via env vars.  
- Configure static files (WhiteNoise recommended) for production.

---

## Development & contribution
- Branch workflow: `feature/<name>`, `fix/<desc>`, `chore/<task>`  
- Commit messages should be descriptive: `feat: add book model`, `fix(borrow): prevent duplicate borrows`  
- Tests must be added for new features and bug fixes.

---

## Notes on academic integrity & AI
- This is an original capstone project. Do not copy other learners’ projects or submit code you cannot explain.  
- AI tools were used for guidance and scaffolding only — always understand and adapt suggested code.

---

## License
This project is released under the **MIT License**. See `LICENSE` for details.
