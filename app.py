import os
import sys
import time
import traceback

from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from dotenv import load_dotenv

from oxford import find_entry_by_pos
from notion_api import (
    get_page_data,
    update_ipa,
)


# =========================================================
# UTF-8 CONSOLE CONFIGURATION
# =========================================================

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace"
        )
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace"
        )
    except Exception:
        pass


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

WEBHOOK_SECRET = os.getenv(
    "NOTION_WEBHOOK_SECRET"
)


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="Notion IPA Automation",
    description="Automatically fetch IPA from Oxford Learner's Dictionaries and update Notion.",
    version="1.0.0",
)


# =========================================================
# CONSTANTS
# =========================================================

STATUS_SUCCESS = "success"
STATUS_NOT_FOUND = "not_found"
STATUS_NETWORK_ERROR = "network_error"


# =========================================================
# LOGGING
# =========================================================

def log(message=""):
    """
    Print a log message safely on Windows.
    """

    try:
        print(
            message,
            flush=True
        )

    except UnicodeEncodeError:

        try:

            safe_message = (
                str(message)
                .encode(
                    "ascii",
                    errors="replace"
                )
                .decode("ascii")
            )

            print(
                safe_message,
                flush=True
            )

        except Exception:
            pass

    except Exception:
        pass


# =========================================================
# PAYLOAD EXTRACTION
# =========================================================

def extract_page_id(payload):
    """
    Extract the Notion page ID from the webhook payload.
    """

    try:

        return payload["data"]["id"]

    except (
        KeyError,
        TypeError
    ):

        return None


def extract_word_from_payload(payload):
    """
    Extract the Word property from the webhook payload.
    """

    try:

        return (
            payload
            .get("data", {})
            .get("properties", {})
            .get("Word", {})
            .get("title", [{}])[0]
            .get("plain_text")
        )

    except (
        IndexError,
        AttributeError,
        TypeError
    ):

        return None


def extract_pos_from_payload(payload):
    """
    Extract the Parts of Speech property from
    the webhook payload.
    """

    try:

        return (
            payload
            .get("data", {})
            .get("properties", {})
            .get("Parts of Speech", {})
            .get("select", {})
            .get("name")
        )

    except (
        AttributeError,
        TypeError
    ):

        return None


# =========================================================
# PROCESS PAGE
# =========================================================

def process_page(
    page_id,
    word=None,
    pos=None
):
    """
    Process a Notion page.

    Flow:
        Notion
          ↓
        Oxford
          ↓
        IPA
          ↓
        Notion
    """

    start_time = time.perf_counter()

    log("")
    log("=" * 60)
    log("[START] Processing page")
    log(f"Page ID : {page_id}")

    try:

        # -------------------------------------------------
        # Get current page data
        # -------------------------------------------------

        page_data = get_page_data(
            page_id
        )

        current_word = page_data.get(
            "word"
        )

        current_pos = page_data.get(
            "pos"
        )

        # Prefer values read directly from Notion.
        # This prevents stale webhook payload data.
        if current_word is not None:
            word = current_word

        if current_pos is not None:
            pos = current_pos

        log(f"Word    : {word}")
        log(f"POS     : {pos}")

        # -------------------------------------------------
        # Validate input
        # -------------------------------------------------

        if not word or not pos:

            log(
                "[SKIP] Word or Parts of Speech is empty."
            )

            return

        word = str(word).strip()
        pos = str(pos).strip()

        if not word or not pos:

            log(
                "[SKIP] Word or Parts of Speech is empty."
            )

            return

        # -------------------------------------------------
        # Oxford lookup
        # -------------------------------------------------

        log(
            "[OXFORD] Searching for matching entry..."
        )

        oxford_start = time.perf_counter()

        result = find_entry_by_pos(
            word,
            pos
        )

        oxford_time = (
            time.perf_counter()
            - oxford_start
        )

        log(
            f"[TIME] Oxford: {oxford_time:.2f}s"
        )

        # -------------------------------------------------
        # Oxford result
        # -------------------------------------------------

        status = result.get(
            "status"
        )

        # =================================================
        # SUCCESS
        # =================================================

        if status == STATUS_SUCCESS:

            log(
                "[OK] Oxford entry found."
            )

            log(
                f"Word   : {result.get('word')}"
            )

            log(
                f"POS    : {result.get('pos')}"
            )

            log(
                f"URL    : {result.get('url')}"
            )

            log(
                f"BrE    : {result.get('british')}"
            )

            log(
                f"AmE    : {result.get('american')}"
            )

            ipa = result.get(
                "ipa"
            )

            log(
                f"IPA    : {ipa}"
            )

            # -------------------------------------------------
            # Update Notion
            # -------------------------------------------------

            notion_start = time.perf_counter()

            update_success = update_ipa(
                page_id,
                ipa
            )

            notion_time = (
                time.perf_counter()
                - notion_start
            )

            log(
                f"[TIME] Notion update: "
                f"{notion_time:.2f}s"
            )

            if update_success:

                log(
                    "[NOTION] IPA updated successfully."
                )

            else:

                log(
                    "[NOTION] IPA update failed."
                )

        # =================================================
        # NOT FOUND
        # =================================================

        elif status == STATUS_NOT_FOUND:

            log(
                "[NOT FOUND] No matching Oxford entry."
            )

            log(
                "[ACTION] Clearing IPA field."
            )

            notion_start = time.perf_counter()

            update_success = update_ipa(
                page_id,
                ""
            )

            notion_time = (
                time.perf_counter()
                - notion_start
            )

            log(
                f"[TIME] Notion update: "
                f"{notion_time:.2f}s"
            )

            if update_success:

                log(
                    "[NOTION] IPA field cleared."
                )

            else:

                log(
                    "[NOTION] Failed to clear IPA field."
                )

        # =================================================
        # NETWORK ERROR
        # =================================================

        elif status == STATUS_NETWORK_ERROR:

            log(
                "[NETWORK ERROR] "
                "Could not connect to Oxford."
            )

            log(
                "[ACTION] Keeping the current IPA value."
            )

        # =================================================
        # UNKNOWN STATUS
        # =================================================

        else:

            log(
                f"[ERROR] Unknown Oxford status: {status}"
            )

            log(
                "[ACTION] Keeping the current IPA value."
            )

    except Exception as e:

        log(
            f"[ERROR] Processing failed: {e}"
        )

        log(
            traceback.format_exc()
        )

    finally:

        total_time = (
            time.perf_counter()
            - start_time
        )

        log(
            f"[TIME] Total: {total_time:.2f}s"
        )

        log(
            "[END] Processing finished."
        )

        log("=" * 60)
        log("")


# =========================================================
# WEBHOOK ENDPOINT
# =========================================================

@app.post("/webhook/notion")
async def notion_webhook(
    payload: dict,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(
        default=None
    )
):

    log("")
    log(
        "[WEBHOOK] Received webhook from Notion."
    )

    # -----------------------------------------------------
    # Verify secret
    # -----------------------------------------------------

    if WEBHOOK_SECRET:

        if x_webhook_secret != WEBHOOK_SECRET:

            log(
                "[REJECTED] Invalid webhook secret."
            )

            raise HTTPException(
                status_code=401,
                detail="Invalid webhook secret."
            )

    # -----------------------------------------------------
    # Debug payload
    # -----------------------------------------------------

    try:

        log(
            "[PAYLOAD] Webhook payload received."
        )

    except Exception:
        pass

    # -----------------------------------------------------
    # Extract data
    # -----------------------------------------------------

    page_id = extract_page_id(
        payload
    )

    word = extract_word_from_payload(
        payload
    )

    pos = extract_pos_from_payload(
        payload
    )

    log(
        f"[WEBHOOK] Page ID: {page_id}"
    )

    log(
        f"[WEBHOOK] Word: {word}"
    )

    log(
        f"[WEBHOOK] POS: {pos}"
    )

    # -----------------------------------------------------
    # Validate page ID
    # -----------------------------------------------------

    if not page_id:

        log(
            "[REJECTED] Page ID is missing."
        )

        raise HTTPException(
            status_code=400,
            detail="Page ID is missing."
        )

    # -----------------------------------------------------
    # Run processing in background
    # -----------------------------------------------------

    background_tasks.add_task(
        process_page,
        page_id,
        word,
        pos
    )

    log(
        "[ACCEPTED] Processing task added to background."
    )

    return {
        "status": "accepted",
        "message": "Processing task added to background.",
        "page_id": page_id
    }


# =========================================================
# ROOT ENDPOINT
# =========================================================

@app.get("/")
def root():

    return {
        "status": "running",
        "service": "Notion IPA Automation",
        "message": (
            "Notion IPA automation service is running."
        )
    }


# =========================================================
# TEST ENDPOINT
# =========================================================

@app.get("/test")
def test():

    return {
        "status": "ok",
        "message": (
            "Notion IPA Automation API is working."
        )
    }