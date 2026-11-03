import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
LEASE = int(os.getenv("LEASE", "120"))
PROTRACTION = int(os.getenv("PROTRACTION", "60"))