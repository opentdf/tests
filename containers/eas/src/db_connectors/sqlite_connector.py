"""SQLite connector."""

import logging
import os
import sqlite3

from ..eas_config import EASConfig
from ..errors import Error

logger = logging.getLogger(__name__)

eas_config = EASConfig.get_instance()
EAS_DB_PATH = eas_config.get_item("EAS_DB_PATH")


class SQLiteConnector:
    """Connector to SQLite -
    A singleton class to manage the creation and connections for the SQL database"""

    __instance = None

    @staticmethod
    def get_instance():
        if SQLiteConnector.__instance is None:
            SQLiteConnector()
        return SQLiteConnector.__instance

    def __init__(self):
        """Initialize SQLite connector."""
        if self.__instance:
            raise Error(
                message="SQLiteConnector is a singleton. Use SQLiteConnector.get_instance()"
            )

        # db path defaults to relative path "db/data/eas_database.sqlite" from defaults.json and EASConfig
        # When deploying, use EAS_DB_PATH environment variable to override.
        self.db_path = EAS_DB_PATH
        logger.debug("Creating SQLite Connector; Location = [%s]", self.db_path)
        if ":memory:" == self.db_path:
            # Creating an in-memory database
            pass
        elif os.path.isfile(self.db_path):
            if not os.access(self.db_path, os.R_OK | os.W_OK):
                logger.warning("Cannot write or read db file [%s]", self.db_path)
        else:
            db_dir_path = os.path.dirname(self.db_path)
            os.makedirs(db_dir_path, exist_ok=True)
            if not os.access(db_dir_path, os.W_OK | os.X_OK):
                logger.warning("Cannot write or execute db dir [%s]", db_dir_path)

        self.create_tables()
        SQLiteConnector.__instance = self

    def create_tables(self):
        """Create tables and other schema items if they don't exist"""
        # Provision it with auth-generated endpoints
        working_dir = os.getcwd()
        logger.debug(f"Working Dir: {working_dir}")
        create_tables_path = os.path.join(working_dir, "db/scripts/create_tables.sql")
        logger.debug("SQL Schema path: [%s]", create_tables_path)

        sql_file = open(create_tables_path)
        sql_as_string = sql_file.read()
        sqlite3.connect(self.db_path).executescript(sql_as_string)

    def check_schema(self):
        """Create tables and other schema items if they don't exist"""
        # Provision it with auth-generated endpoints
        row = None
        try:
            (major, minor, _) = sqlite3.sqlite_version_info
            stable = (
                "sqlite_schema"
                if (major > 3 or (major == 3 and minor >= 33))
                else "sqlite_master"
            )
            with sqlite3.connect(self.db_path) as con:
                cur = con.execute(
                    f"SELECT COUNT(name) FROM {stable} WHERE name='entity'"
                )
                row = cur.fetchone()
        except Exception as err:
            raise Error(message="Error connecting to database") from err
        if not row or row[0] != 1:
            raise Error(message="Database not prepared")

    def run(
        self, command: str, parameters: tuple, force_commit: bool = True
    ) -> sqlite3.Cursor:
        """Run the command then return the cursor.

        The execute method with separate command and parameters guards against SQL injection.
        The default is immediate commit - revisit if in a very high load environment.
        """
        self.log_sql(command, parameters)
        with sqlite3.connect(self.db_path) as con:
            cursor = con.cursor()
            cursor.execute(command, parameters)
            if force_commit:
                con.commit()
            return cursor

    @staticmethod
    def log_sql(command, parameters):
        """Centralize SQL logging
        Trace not to be enabled in production; could log PII"""
        logger.debug("SQL: %s parameters: %s", command, parameters)
