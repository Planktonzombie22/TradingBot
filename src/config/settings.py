#cspell:words dotenv
from dotenv import load_dotenv
import os

load_dotenv()

PAPER_TRADING = os.getenv("PAPER_TRADING")

print(PAPER_TRADING)