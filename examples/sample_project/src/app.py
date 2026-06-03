from fastapi import FastAPI
from src.models import Todo

app = FastAPI()

TODOS: list[Todo] = []


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/todos")
def list_todos() -> list[Todo]:
    return TODOS
