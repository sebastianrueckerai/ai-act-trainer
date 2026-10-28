from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker


def make_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        # Otherwise the driver commits pending writes before SAVEPOINT/RELEASE
        # statements, so rollback cannot undo a savepoint-scoped write.
        @event.listens_for(engine, "connect")
        def real_transactions(dbapi_connection, _record) -> None:
            dbapi_connection.isolation_level = None
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        @event.listens_for(engine, "begin")
        def begin_transaction(connection) -> None:
            connection.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
