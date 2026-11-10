# Existing IP HTTPS remains available; chat is canonical-domain only.
location = /api/chat {
    default_type application/json;
    add_header Cache-Control "no-store" always;
    return 404 '{"mode":"local","status":"error","answer":"Use the canonical domain for chat.","programs":[],"sources":[]}';
}
