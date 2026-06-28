import sqlite3
import pandas as pd
import logging
import os
from src.preprocess.text_cleaning import clean_text

logger = logging.getLogger(__name__)

DB_PATH = "src/database/products.db"
CSV_PATH = "src/data/ChatBotdataset.csv"


def remove_existing_db():
    """Deletes the old database file if it exists, so we always build fresh."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"Old database removed at {DB_PATH}")
    else:
        logger.info("No existing database found, creating a new one.")


def load_csv_to_sqlite():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV file not found at {CSV_PATH}")

    # Step 1: always remove old DB and build fresh
    remove_existing_db()

    # Step 2: read and clean CSV
    df = pd.read_csv(CSV_PATH, encoding="utf-8")
    df.columns = df.columns.str.strip()
    df = df.loc[:, df.columns.str.strip() != ""]
    df = df.loc[:, ~df.columns.str.match(r'^\.\d+$')]
    df["has_pressur"] = df["has_pressur"].astype(int)

    # NOTE: pandas marks text columns as dtype "object", not "str".
    # Using "str" here means clean_text never actually runs.
    text_columns = df.select_dtypes(include=["object"]).columns
    for col in text_columns:
        df[col] = df[col].apply(lambda x: clean_text(x) if isinstance(x, str) else x)

    # Step 3: build new DB
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("products", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

    logger.info(f"Database loaded successfully with {len(df)} products.")


if __name__ == "__main__":
    load_csv_to_sqlite()