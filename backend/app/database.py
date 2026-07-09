import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def resolve_root_dir() -> Path:
    """exe 同目录 / 源码根目录。data_location.txt 与默认 data/ 都放这里。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包运行：以 exe 所在目录为根
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


ROOT_DIR = resolve_root_dir()

# 数据目录可由 data_location.txt（一行绝对路径）覆盖；不存在则默认 ROOT_DIR/data
_LOCATION_FILE = ROOT_DIR / "data_location.txt"


def _resolve_data_dir() -> Path:
    if _LOCATION_FILE.exists():
        line = _LOCATION_FILE.read_text(encoding="utf-8").strip()
        if line:
            p = Path(line).expanduser()
            if not p.is_absolute():
                p = (ROOT_DIR / p).resolve()
            return p
    return ROOT_DIR / "data"


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "laimiutrade.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
