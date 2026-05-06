# Prode API Endpoints

Base URL (development): `http://localhost:8000`

All endpoints returning data use JSON. Timestamps are ISO 8601.

---

## Authentication

### Register
- **POST** `/api/users/register/`
- **Auth:** None
- **Body:**
  ```json
  {
    "username": "string",
    "email": "string",
    "password": "string"
  }
  ```
- **Response:** `201 Created`
  ```json
  {
    "user": "username",
    "message": "Usuario creado exitosamente. Ahora puedes acceder."
  }
  ```

### Login
- **POST** `/api/users/login/`
- **Auth:** None
- **Body:**
  ```json
  {
    "username": "string",
    "password": "string",
    "remember_me": false
  }
  ```
- **Response:** `200 OK`
  ```json
  {
    "access": "<access_token>",
    "refresh": "<refresh_token>",
    "user": {
      "id": 1,
      "username": "string",
      "email": "string"
    }
  }
  ```
- **Cookies set:**
  - `access_token` — HttpOnly, SameSite=Lax, 15 min
  - `refresh_token` — HttpOnly, SameSite=Lax, 1 day (30 days if `remember_me: true`)

### Refresh Token
- **POST** `/api/token/refresh/`
- **Auth:** None (uses refresh cookie or body)
- **Body (optional):**
  ```json
  { "refresh": "<refresh_token>" }
  ```
- **Response:** `200 OK`
  ```json
  {
    "access": "<new_access_token>",
    "refresh": "<new_refresh_token>"
  }
  ```
- **Note:** If `refresh` is omitted from the body, the server reads it from the `refresh_token` cookie automatically. The cookie is rotated on every refresh.

---

## Tournaments

All endpoints require `Authorization: Bearer <access_token>`.

### List My Tournaments
- **GET** `/api/prode/tournaments/`
- **Response:** `200 OK`
  ```json
  [
    {
      "id": 1,
      "name": "World Cup 2026",
      "description": "Office pool",
      "invitation_code": "ABC123DEF",
      "is_private": true,
      "created_at": "2026-05-01T12:00:00Z",
      "owner": 1,
      "participants": [1, 2, 3]
    }
  ]
  ```

### Create Tournament
- **POST** `/api/prode/tournaments/`
- **Body:**
  ```json
  { "name": "string", "description": "string (optional)" }
  ```
- **Response:** `201 Created`
- **Note:** `invitation_code` is auto-generated.

### Retrieve Tournament
- **GET** `/api/prode/tournaments/{id}/`

### Update Tournament
- **PUT** / **PATCH** `/api/prode/tournaments/{id}/`

### Delete Tournament
- **DELETE** `/api/prode/tournaments/{id}/`

### Join by Code
- **POST** `/api/prode/tournaments/join_by_code/`
- **Body:**
  ```json
  { "invitation_code": "ABC123DEF" }
  ```
- **Response:** `200 OK`
  ```json
  { "detail": "Joined World Cup 2026" }
  ```

### Leaderboard
- **GET** `/api/prode/tournaments/{id}/leaderboard/`
- **Response:** `200 OK`
  ```json
  [
    {
      "user__id": 1,
      "user__username": "alice",
      "total_points": 42
    }
  ]
  ```
- **Note:** Sorted by `total_points` descending.

---

## Matches

All endpoints require `Authorization: Bearer <access_token>`.

### List Matches
- **GET** `/api/prode/matches/`
- **Query params:**
  - `?tournament={id}` — filter matches belonging to a tournament
- **Response:** `200 OK`

### Create Match (raw)
- **POST** `/api/prode/matches/`

### Retrieve Match
- **GET** `/api/prode/matches/{id}/`

### Update Match
- **PUT** / **PATCH** `/api/prode/matches/{id}/`

### Delete Match
- **DELETE** `/api/prode/matches/{id}/`

### Create Match in Tournament
- **POST** `/api/prode/matches/create_in_tournament/`
- **Body:**
  ```json
  {
    "tournament_id": 1,
    "home_team": "Argentina",
    "away_team": "Brazil",
    "match_date": "2026-06-15T15:00:00Z",
    "stage": "Final"
  }
  ```
- **Response:** `201 Created`
- **Note:** Only the tournament **owner** can create matches this way. The match is automatically linked to the tournament.

---

## Predictions

All endpoints require `Authorization: Bearer <access_token>`. Results are scoped to the **authenticated user**.

### List My Predictions
- **GET** `/api/prode/predictions/`
- **Query params:**
  - `?tournament={id}` — filter by tournament
- **Response:** `200 OK`

### Create Prediction
- **POST** `/api/prode/predictions/`
- **Body:**
  ```json
  {
    "tournament": 1,
    "match": 5,
    "home_score_guess": 2,
    "away_score_guess": 1
  }
  ```
- **Response:** `201 Created`
- **Note:** The `user` field is force-set server-side. A user can only have one prediction per match per tournament.

### Retrieve Prediction
- **GET** `/api/prode/predictions/{id}/`

### Update Prediction
- **PUT** / **PATCH** `/api/prode/predictions/{id}/`

### Delete Prediction
- **DELETE** `/api/prode/predictions/{id}/`

---

## Token / Session Characteristics

| Setting | Value |
|---|---|
| Access token lifetime | 15 minutes |
| Refresh token lifetime | 7 days |
| Rotate refresh tokens | Yes |
| Blacklist old refresh tokens | Yes |
| `access_token` cookie | HttpOnly, SameSite=Lax, 15 min |
| `refresh_token` cookie | HttpOnly, SameSite=Lax, 1 day (30 days with "Keep me logged in") |
| CORS credentials | Enabled |

---

## Django Admin

- **URL:** `/admin/`
- Standard Django admin panel for managing users, tournaments, matches, and predictions.
