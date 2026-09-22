// Points the static frontend at the FastAPI backend. Override at deploy
// time (e.g. inject a different value when serving the built frontend).
window.API_BASE_URL = window.API_BASE_URL || "http://localhost:8000";
