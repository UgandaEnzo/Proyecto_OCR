from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from urllib.parse import quote_plus

# Cargar variables desde .env si existe (sin requerirlo estrictamente)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Formato seguro: postgresql://usuario:clave@host/nombre_bd
# Recomendado: configurar `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_NAME` (o `DATABASE_URL`) en variables de entorno.
DATABASE_URL = os.getenv("DATABASE_URL")

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "pagos_db")

# Codificamos usuario y contraseña para que caracteres como '@' no rompan la URL
SQLALCHEMY_DATABASE_URL = DATABASE_URL or (
    f"postgresql://{quote_plus(DB_USER)}:{quote_plus(DB_PASS)}@{DB_HOST}:{quote_plus(DB_PORT)}/{DB_NAME}"
)

connect_args = {}

# En algunos entornos Windows/PostgreSQL, los mensajes pueden venir en WIN1252/LATIN1,
# lo que puede disparar UnicodeDecodeError durante fallos de auth. Permite configurarlo por env.
db_client_encoding = os.getenv("DB_CLIENT_ENCODING") or os.getenv("PGCLIENTENCODING")
if db_client_encoding:
    connect_args["options"] = f"-c client_encoding={db_client_encoding}"

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