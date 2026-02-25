from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.routes import pipeline, stories, agents

app = FastAPI(title="AI Publishing House Dashboard")

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Share templates with route modules
pipeline.templates = templates
stories.templates = templates
agents.templates = templates

app.include_router(pipeline.router)
app.include_router(stories.router)
app.include_router(agents.router)
