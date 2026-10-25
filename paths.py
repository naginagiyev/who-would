from pathlib import Path

root_dir = Path(__file__).resolve().parent
app_dir = root_dir / "app"
templates_dir = app_dir / "templates"
schema_path = app_dir / "schema.sql"
