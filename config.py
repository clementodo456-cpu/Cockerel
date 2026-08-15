import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
DATABASE_PATH = os.getenv("DATABASE_PATH", "motivation_bot.db")

# Validation
if not BOT_TOKEN:
    print("CRITICAL ERROR: BOT_TOKEN environment variable is missing!", file=sys.stderr)
    sys.exit(1)

ADMIN_ID = None
if ADMIN_ID_RAW:
    try:
        ADMIN_ID = int(ADMIN_ID_RAW)
    except ValueError:
        print("WARNING: ADMIN_ID is not a valid integer. Admin commands will be disabled.")
