from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <!doctype html>
    <html lang=\"en\">
      <head><meta charset=\"UTF-8\"><title>Orion Trader</title></head>
      <body><h1>Orion Trader – OK</h1></body>
    </html>
    """
