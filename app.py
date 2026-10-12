
import os
import hmac
import shutil
import threading

import chess
import chess.engine
from flask import Flask, jsonify, request

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "")
ENGINE_PATH = shutil.which("stockfish") or "/usr/games/stockfish"

engine = None
engine_lock = threading.Lock()


def get_engine():
    global engine

    if engine is None:
        engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)

    return engine


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/move")
def get_move():
    if not API_KEY:
        return jsonify({"error": "Server key is not configured"}), 503

    supplied_key = request.headers.get("X-API-Key", "")

    if not hmac.compare_digest(supplied_key, API_KEY):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    fen = data.get("fen")
    level = data.get("level", 5)

    if not isinstance(fen, str) or len(fen) > 200:
        return jsonify({"error": "Invalid FEN"}), 400

    if isinstance(level, bool) or not isinstance(level, int):
        return jsonify({"error": "Invalid level"}), 400

    level = max(1, min(20, level))

    try:
        board = chess.Board(fen)

        if not board.is_valid():
            return jsonify({"error": "Invalid chess position"}), 400

        if board.is_game_over():
            return jsonify({"error": "Game is over"}), 400

        with engine_lock:
            chess_engine = get_engine()
            chess_engine.configure({"Skill Level": level})
            result = chess_engine.play(
                board,
                chess.engine.Limit(time=0.5)
            )

        return jsonify({
            "move": result.move.uci(),
            "fen": board.fen(),
            "level": level
        })

    except ValueError:
        return jsonify({"error": "Invalid chess position"}), 400
    except Exception:
        app.logger.exception("Stockfish request failed")
        return jsonify({"error": "Engine unavailable"}), 500
