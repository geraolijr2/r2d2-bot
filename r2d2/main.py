# r2d2/main.py

from dotenv import load_dotenv
load_dotenv()
import argparse
from r2d2.config import CONFIG
from r2d2.live_trader import LiveTrader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live"], default="live")
    parser.add_argument("--poll", type=int, default=None, help="segundos entre polls (default: 1/3 do timeframe)")
    args = parser.parse_args()

    lt = LiveTrader(CONFIG, poll_interval=args.poll)
    lt.run()

if __name__ == "__main__":
    main()