"""
Asset Manager — Technical Intent
===================================
Provides direct download links to official catalog PDFs.
Used as fallback when RAG and web search can't find an exact answer.

PDFs are served via FastAPI StaticFiles mount:
    app.mount("/catalogs", StaticFiles(directory="src/data/catalog"))

So final URL becomes:
    https://yourdomain.com/catalogs/cim-catalog.pdf
"""

import logging
from pathlib import Path
from typing import Optional
from src.config.setting import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

CATALOG_DIR = Path("src/data/catalog")

# Maps brand name → actual PDF filename
BRAND_FILE_MAP = {
    "CIM": "cim-catalog.pdf",
    "FARAB": "farab-catalog.pdf",
    "MIRAB": "mirab-catalog.pdf",
    "KIZIRAN": "kiziran-catalog.pdf",
}

# Base URL — change this to your actual domain when deployed
# Read from settings if available, otherwise fallback to relative path
BASE_URL = getattr(settings, "BASE_URL", "")
CATALOG_ROUTE = "/catalogs"


# ─────────────────────────────────────────────
# Core Functions
# ─────────────────────────────────────────────

def get_catalog_link(brand: str) -> Optional[str]:
    """
    Returns direct download URL for a brand's catalog PDF.

    Args:
        brand: brand name e.g. "CIM", "FARAB", "MIRAB", "KIZIRAN"

    Returns:
        Full URL string, or None if brand not found / file missing
    """
    brand_upper = brand.upper().strip()
    filename = BRAND_FILE_MAP.get(brand_upper)

    if not filename:
        logger.warning(f"AssetManager: Unknown brand [{brand}]")
        return None

    # Verify file actually exists on disk
    file_path = CATALOG_DIR / filename
    if not file_path.exists():
        logger.error(f"AssetManager: File not found at [{file_path}]")
        return None

    url = f"{BASE_URL}{CATALOG_ROUTE}/{filename}"
    logger.info(f"AssetManager: Generated link for [{brand_upper}] → [{url}]")
    return url


def get_all_catalog_links() -> dict[str, str]:
    """
    Returns links for all available brand catalogs.
    Useful when we don't know which specific brand the user needs.
    """
    links = {}
    for brand in BRAND_FILE_MAP.keys():
        link = get_catalog_link(brand)
        if link:
            links[brand] = link
    return links


def build_fallback_message(brand: Optional[str] = None) -> str:
    """
    Builds a friendly Persian message with catalog download link(s).
    Used as the final fallback when RAG + web search both fail.

    Args:
        brand: specific brand if known, otherwise shows all catalogs

    Returns:
        Persian message string with download link(s)
    """
    if brand:
        link = get_catalog_link(brand)
        if link:
            return (
                f"متأسفانه پاسخ دقیقی برای این سوال پیدا نکردم.\n"
                f"می‌توانید کاتالوگ رسمی برند {brand} را از لینک زیر دانلود کنید:\n"
                f"{link}"
            )

    # Fallback — show all catalogs
    all_links = get_all_catalog_links()
    if not all_links:
        return (
            "متأسفانه پاسخ دقیقی برای این سوال پیدا نکردم. "
            "لطفاً با پشتیبانی تماس بگیرید."
        )

    message = "متأسفانه پاسخ دقیقی برای این سوال پیدا نکردم.\n"
    message += "می‌توانید کاتالوگ‌های رسمی را از لینک‌های زیر دانلود کنید:\n\n"
    for brand_name, link in all_links.items():
        message += f"• {brand_name}: {link}\n"

    return message