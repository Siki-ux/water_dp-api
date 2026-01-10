import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.datasource import DataSource
from app.schemas.datasource import DataSourceCreate, DataSourceUpdate
from app.services.encryption_service import encryption_service

logger = logging.getLogger(__name__)


class DataSourceService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, datasource_id: UUID) -> Optional[DataSource]:
        return self.db.query(DataSource).filter(DataSource.id == datasource_id).first()

    def get_by_project(self, project_id: UUID) -> List[DataSource]:
        return (
            self.db.query(DataSource).filter(DataSource.project_id == project_id).all()
        )

    def create(self, project_id: UUID, schema: DataSourceCreate) -> DataSource:
        data = schema.model_dump()
        conn_details = data.get("connection_details", {})

        # Encrypt password if present
        if "password" in conn_details:
            conn_details["password"] = encryption_service.encrypt(
                conn_details["password"]
            )

        datasource = DataSource(
            project_id=project_id,
            name=data["name"],
            type=data["type"],
            connection_details=conn_details,
        )
        self.db.add(datasource)
        self.db.commit()
        self.db.refresh(datasource)
        return datasource

    def update(
        self, datasource_id: UUID, schema: DataSourceUpdate
    ) -> Optional[DataSource]:
        datasource = self.get(datasource_id)
        if not datasource:
            return None

        data = schema.model_dump(exclude_unset=True)

        if "connection_details" in data:
            conn_details = data["connection_details"]
            # Encrypt password if present
            if "password" in conn_details:
                conn_details["password"] = encryption_service.encrypt(
                    conn_details["password"]
                )
            # Merge with existing details if needed, but here we replace for simplicity or deep merge?
            # Usually simple replace is safer for simplicity unless partial update is required deep inside JSON.
            # We will replace the whole dict as per standard REST PUT/PATCH on 'connection_details' field.
            datasource.connection_details = conn_details

        if "name" in data:
            datasource.name = data["name"]
        if "type" in data:
            datasource.type = data["type"]

        self.db.commit()
        self.db.refresh(datasource)
        return datasource

    def delete(self, datasource_id: UUID) -> bool:
        datasource = self.get(datasource_id)
        if not datasource:
            return False
        self.db.delete(datasource)
        self.db.commit()
        return True

    def test_connection(self, datasource: DataSource) -> bool:
        """
        Test connection to the datasource.
        Currently supports Postgres databases.
        """
        details = datasource.connection_details

        if datasource.type in ["POSTGRES", "GEOSERVER", "TIMEIO"]:
            # Assume all are Postgres for now based on requirements
            host = details.get("host", "localhost")
            port = details.get("port", 5432)
            user = details.get("user", "postgres")
            dbname = details.get("database", "postgres")
            password_encrypted = details.get("password", "")

            password = encryption_service.decrypt(password_encrypted)

            # Construct connection string
            # Minimalistic approach: use sqlalchemy create_engine to test
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

            try:
                engine = create_engine(dsn)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return True
            except Exception as e:
                logger.error(
                    f"Connection test failed for datasource {datasource.id}: {e}"
                )
                return False

        return False

    def execute_query(self, datasource: DataSource, query: str) -> Dict[str, Any]:
        """
        Execute a raw SQL query on the datasource.
        WARNING: This allows arbitrary SQL execution. Ensure caller has permissions.
        """
        details = datasource.connection_details

        # Only support Postgres/Timescale/PostGIS
        if datasource.type in ["POSTGRES", "GEOSERVER", "TIMEIO"]:
            host = details.get("host", "localhost")
            port = details.get("port", 5432)
            user = details.get("user", "postgres")
            dbname = details.get("database", "postgres")
            password_encrypted = details.get("password", "")

            password = encryption_service.decrypt(password_encrypted)

            # Construct connection string
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

            try:
                engine = create_engine(dsn)
                with engine.connect() as conn:
                    # Execute
                    result = conn.execute(text(query))

                    # Fetch results if it's a SELECT (returns rows)
                    if result.returns_rows:
                        keys = list(result.keys())
                        rows = [dict(zip(keys, row)) for row in result.fetchall()]
                        return {"columns": keys, "rows": rows, "status": "success"}
                    else:
                        # Commit if it was a data modification (INSERT/UPDATE/DELETE)
                        conn.commit()
                        return {
                            "columns": [],
                            "rows": [],
                            "status": "success",
                            "message": f"Affected {result.rowcount} rows",
                        }

            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                # Return error structure
                raise Exception(f"Query failed: {str(e)}")

        raise Exception(f"Unsupported datasource type: {datasource.type}")

    def mask_credentials(self, datasource: DataSource) -> DataSource:
        """
        Return a copy or modify details to mask password.
        Since DataSource is an ORM object, we shouldn't modify it directly if attached to session.
        We return a dictionary or handle it in Schema validation.
        But for safety, let's helper method to return a dict suitable for schema.
        """
        # Actually, schemas should handle this via `connection_details_safe` property if mapped,
        # but masking in service is cleaner.
        # We can't modify the ORM object in place safely without persisting it.
        # So we verify where this is used. If we return the ORM object, Pydantic parses it.
        pass
