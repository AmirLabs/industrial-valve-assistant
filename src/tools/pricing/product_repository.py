import sqlite3
import logging
from typing import Optional
from src.tools.pricing.entities import ProductEntities

logger = logging.getLogger(__name__)

DB_PATH = "src/database/products.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_products(entities: ProductEntities) -> list[dict]:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        conditions = [
            "product_name LIKE ?",
            "inch = ?"
        ]
        params = [
            f"%{entities.product_name}%",
            entities.inch
        ]

        if entities.pressur_rating:
            conditions.append("pressur_rating = ?")
            params.append(entities.pressur_rating)

        if entities.company:
            conditions.append("company = ?")
            params.append(entities.company)

        query = f"SELECT * FROM products WHERE {' AND '.join(conditions)}"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return []

def get_available_sizes(product_name: str) -> list:
    """Returns all unique sizes (inch values) that exist for a given product name.

    This is called in Scenario B — when user gives a correct product name
    but a size that does not exist for that product in the database.
    We query only by product_name (ignoring inch) to get all available sizes.

    Args:
        product_name: The normalized product name string.

    Returns:
        A sorted list of available inch values, e.g. ["2", "3", "4", "6", "8"].
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT inch
            FROM products
            WHERE product_name LIKE ?
            AND inch IS NOT NULL
            ORDER BY CAST(inch AS REAL)
        """
        cursor.execute(query, [f"%{product_name}%"])
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    except Exception as e:
        logger.error(f"Failed to get available sizes for product [{product_name}]: {e}")
        return []


def get_unique_values(entities: ProductEntities, column: str) -> list:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = f"""
            SELECT DISTINCT {column} 
            FROM products 
            WHERE product_name LIKE ? AND inch = ?
            AND {column} IS NOT NULL
        """
        cursor.execute(query, [f"%{entities.product_name}%", entities.inch])
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    except Exception as e:
        logger.error(f"Failed to get unique values for column [{column}]: {e}")
        return []