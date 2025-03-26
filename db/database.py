import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from ocr_app.utils.config import get_settings

# Get settings
settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create async engine
async_engine = create_async_engine(f"sqlite+aiosqlite:///{settings.DATABASE_PATH}")
AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

@asynccontextmanager
async def get_async_session():
    """Get async database session with proper async context manager"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# Define tables
metadata = sa.MetaData()

schemas_table = sa.Table(
    "schemas",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("description", sa.String),
    sa.Column("fields", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime, default=datetime.now),
    sa.Column("updated_at", sa.DateTime, default=datetime.now)
)

extractions_table = sa.Table(
    "extractions",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("schema_id", sa.Integer, sa.ForeignKey("schemas.id")),
    sa.Column("file_name", sa.String),
    sa.Column("file_path", sa.String),
    sa.Column("model_used", sa.String),
    sa.Column("result", sa.String),
    sa.Column("created_at", sa.DateTime, default=datetime.now)
)

async def initialize_db():
    """Initialize the database with required tables"""
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)
        
        # Create tables
        async with async_engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        
        logger.info(f"Database initialized at: {settings.DATABASE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        return False

class Database:
    """Simple SQLite database for storing extraction schemas and results"""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection"""
        if db_path is None:
            db_path = get_settings().DATABASE_PATH
        
        self.db_path = db_path
        logger.info(f"Using database at: {db_path}")
        
        # Initialize database with required tables
        self._init_db()
    
    def _init_db(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create schemas table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS schemas (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            fields TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create extractions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS extractions (
            id INTEGER PRIMARY KEY,
            schema_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            model_used TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (schema_id) REFERENCES schemas (id)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_schema(self, name: str, description: str, fields: List[Dict]) -> int:
        """Create a new schema in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO schemas (name, description, fields) VALUES (?, ?, ?)",
                (name, description, json.dumps(fields))
            )
            schema_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Created schema: {name} (ID: {schema_id})")
            return schema_id
        except Exception as e:
            logger.error(f"Error creating schema: {str(e)}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_schema(self, schema_id: int) -> Optional[Dict]:
        """Get a schema by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id, name, description, fields, created_at, updated_at FROM schemas WHERE id = ?",
                (schema_id,)
            )
            row = cursor.fetchone()
            
            if row:
                schema = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "fields": json.loads(row[3]),
                    "created_at": row[4],
                    "updated_at": row[5]
                }
                return schema
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting schema: {str(e)}")
            return None
        finally:
            conn.close()
    
    def update_schema(self, schema_id: int, name: str, description: str, fields: List[Dict]) -> bool:
        """Update an existing schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE schemas SET name = ?, description = ?, fields = ?, updated_at = ? WHERE id = ?",
                (name, description, json.dumps(fields), datetime.now().isoformat(), schema_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating schema: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def delete_schema(self, schema_id: int) -> bool:
        """Delete a schema by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check if schema is in use by any extractions
            cursor.execute("SELECT COUNT(*) FROM extractions WHERE schema_id = ?", (schema_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                logger.error(f"Cannot delete schema {schema_id}: it is used by {count} extractions")
                return False
            
            cursor.execute("DELETE FROM schemas WHERE id = ?", (schema_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting schema: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_all_schemas(self) -> List[Dict]:
        """Get all schemas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT id, name, description, fields, created_at, updated_at FROM schemas ORDER BY id"
            )
            rows = cursor.fetchall()
            
            schemas = []
            for row in rows:
                schema = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "fields": json.loads(row[3]),
                    "created_at": row[4],
                    "updated_at": row[5]
                }
                schemas.append(schema)
            
            return schemas
        except Exception as e:
            logger.error(f"Error getting schemas: {str(e)}")
            return []
        finally:
            conn.close()
    
    def create_extraction(self, schema_id: int, file_name: str, file_path: str, model_used: str) -> int:
        """Create a new extraction entry"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO extractions (schema_id, file_name, file_path, model_used) VALUES (?, ?, ?, ?)",
                (schema_id, file_name, file_path, model_used)
            )
            extraction_id = cursor.lastrowid
            conn.commit()
            return extraction_id
        except Exception as e:
            logger.error(f"Error creating extraction: {str(e)}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def update_extraction_result(self, extraction_id: int, result: Dict) -> bool:
        """Update extraction result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE extractions SET result = ? WHERE id = ?",
                (json.dumps(result), extraction_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating extraction result: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_extraction(self, extraction_id: int) -> Optional[Dict]:
        """Get extraction by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT e.id, e.schema_id, e.file_name, e.file_path, e.model_used, e.result, e.created_at, s.name
                FROM extractions e 
                JOIN schemas s ON e.schema_id = s.id
                WHERE e.id = ?
                """,
                (extraction_id,)
            )
            row = cursor.fetchone()
            
            if row:
                extraction = {
                    "id": row[0],
                    "schema_id": row[1],
                    "file_name": row[2],
                    "file_path": row[3],
                    "model_used": row[4],
                    "result": json.loads(row[5]) if row[5] else None,
                    "created_at": row[6],
                    "schema_name": row[7]
                }
                return extraction
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting extraction: {str(e)}")
            return None
        finally:
            conn.close()
    
    def get_all_extractions(self) -> List[Dict]:
        """Get all extractions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT e.id, e.schema_id, e.file_name, e.file_path, e.model_used, e.result, e.created_at, s.name
                FROM extractions e 
                JOIN schemas s ON e.schema_id = s.id
                ORDER BY e.created_at DESC
                """
            )
            rows = cursor.fetchall()
            
            extractions = []
            for row in rows:
                extraction = {
                    "id": row[0],
                    "schema_id": row[1],
                    "file_name": row[2],
                    "file_path": row[3],
                    "model_used": row[4],
                    "result": json.loads(row[5]) if row[5] else None,
                    "created_at": row[6],
                    "schema_name": row[7]
                }
                extractions.append(extraction)
            
            return extractions
        except Exception as e:
            logger.error(f"Error getting extractions: {str(e)}")
            return []
        finally:
            conn.close()
    
    def delete_extraction(self, extraction_id: int) -> bool:
        """Delete an extraction by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM extractions WHERE id = ?", (extraction_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting extraction: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()

# Create a singleton instance
db = Database()

# Async SQLAlchemy database operations
class DatabaseOperations:
    """Async database operations using SQLAlchemy"""
    
    async def init_db(self):
        """Initialize the database with required tables"""
        async with async_engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
    
    # Schema operations
    async def get_schema_by_id(self, session: AsyncSession, schema_id: int) -> Optional[Dict]:
        """Get a schema by ID using SQLAlchemy"""
        query = sa.select(schemas_table).where(schemas_table.c.id == schema_id)
        result = await session.execute(query)
        schema_row = result.fetchone()
        
        if schema_row:
            return {
                "id": schema_row.id,
                "name": schema_row.name,
                "description": schema_row.description,
                "fields": json.loads(schema_row.fields),
                "created_at": schema_row.created_at,
                "updated_at": schema_row.updated_at
            }
        return None
    
    async def get_all_schemas(self, session: AsyncSession) -> List[Dict]:
        """Get all schemas using SQLAlchemy"""
        query = sa.select(schemas_table).order_by(schemas_table.c.id)
        result = await session.execute(query)
        schema_rows = result.fetchall()
        
        return [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "fields": json.loads(row.fields),
                "created_at": row.created_at,
                "updated_at": row.updated_at
            }
            for row in schema_rows
        ]
    
    async def create_schema(self, session: AsyncSession, name: str, description: str, fields: List[Dict]) -> int:
        """Create a new schema using SQLAlchemy"""
        now = datetime.now()
        insert_stmt = schemas_table.insert().values(
            name=name,
            description=description,
            fields=json.dumps(fields),
            created_at=now,
            updated_at=now
        )
        result = await session.execute(insert_stmt)
        await session.commit()
        return result.lastrowid
    
    async def update_schema(self, session: AsyncSession, schema_id: int, name: str, description: str, fields: List[Dict]) -> bool:
        """Update a schema using SQLAlchemy"""
        update_stmt = schemas_table.update().where(
            schemas_table.c.id == schema_id
        ).values(
            name=name,
            description=description,
            fields=json.dumps(fields),
            updated_at=datetime.now()
        )
        result = await session.execute(update_stmt)
        await session.commit()
        return result.rowcount > 0
    
    async def delete_schema(self, session: AsyncSession, schema_id: int) -> bool:
        """Delete a schema using SQLAlchemy"""
        delete_stmt = schemas_table.delete().where(schemas_table.c.id == schema_id)
        result = await session.execute(delete_stmt)
        await session.commit()
        return result.rowcount > 0
    
    # Extraction operations
    async def save_extraction_result(self, session: AsyncSession, file_path: str, schema_id: int, 
                                     extraction_result: str, timestamp: str = None) -> int:
        """Save an extraction result to the database"""
        try:
            # If timestamp is not provided, use current time
            if timestamp is None:
                timestamp = datetime.now()
            
            # Insert into extractions table
            insert_stmt = extractions_table.insert().values(
                schema_id=schema_id,
                file_path=file_path,
                result=extraction_result,
                created_at=timestamp
            )
            result = await session.execute(insert_stmt)
            await session.commit()
            return result.lastrowid
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving extraction result: {str(e)}")
            return None
    
    async def get_extraction_results(self, session: AsyncSession, schema_id: Optional[int] = None, 
                                    limit: int = 10) -> List[Dict]:
        """Get extraction results using SQLAlchemy"""
        query = sa.select(
            extractions_table, 
            schemas_table.c.name.label("schema_name")
        ).join(
            schemas_table, 
            extractions_table.c.schema_id == schemas_table.c.id
        ).order_by(
            extractions_table.c.created_at.desc()
        ).limit(limit)
        
        if schema_id:
            query = query.where(extractions_table.c.schema_id == schema_id)
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        return [
            {
                "id": row.id,
                "schema_id": row.schema_id,
                "schema_name": row.schema_name,
                "file_path": row.file_path,
                "extraction_result": row.result,
                "created_at": row.created_at
            }
            for row in rows
        ]

# Create database operations instance
db = DatabaseOperations() 