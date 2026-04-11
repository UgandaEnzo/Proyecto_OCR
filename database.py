from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Cargar variables desde .env si existe (sin requerirlo estrictamente)
try:
    from dotenv import load_dotenv

    base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    dotenv_path = base_dir / '.env'
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    else:
        load_dotenv()
except Exception:
    pass

# Formato seguro: postgresql://usuario:clave@host/nombre_bd
# Recomendado: configurar `DATABASE_URL` o el conjunto completo de variables DB_* en el archivo .env.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")

    missing_vars = [
        name for name, value in [
            ("DB_USER", DB_USER),
            ("DB_PASS", DB_PASS),
            ("DB_HOST", DB_HOST),
            ("DB_PORT", DB_PORT),
            ("DB_NAME", DB_NAME),
        ]
        if not value
    ]
    if missing_vars:
        raise RuntimeError(
            "Faltan variables de entorno para la base de datos: " + ", ".join(missing_vars)
        )

    # Codificamos usuario y contraseña para que caracteres como '@' no rompan la URL
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql://{quote_plus(DB_USER)}:{quote_plus(DB_PASS)}@{DB_HOST}:{quote_plus(DB_PORT)}/{DB_NAME}"
    )
else:
    SQLALCHEMY_DATABASE_URL = DATABASE_URL

connect_args = {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Función para obtener la sesión de la BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()