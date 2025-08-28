# API Endpoints

## Auth
POST /api/auth/register/
POST /api/token/      # body: {"username":"", "password":""}
POST /api/token/refresh/

## Authors
GET /api/authors/
POST /api/authors/    # admin only for unsafe
...

(See swagger at /swagger/ for interactive examples)
