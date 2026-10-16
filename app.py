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


def authorized():
    supplied = request.headers.get("X-API-Key", "")
    return bool(API_KEY) and hmac.compare_digest(supplied, API_KEY)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/move")
def get_move():
    if not authorized():
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
            return jsonify({"error": "Invalid position"}), 400
        if board.is_game_over():
            return jsonify({"error": "Game is over"}), 400

        with engine_lock:
            chess_engine = get_engine()
            chess_engine.configure({"Skill Level": level})
            result = chess_engine.play(
                board, chess.engine.Limit(time=0.5)
            )

        return jsonify({
            "move": result.move.uci(),
            "fen": board.fen(),
            "level": level
        })

    except ValueError:
        return jsonify({"error": "Invalid position"}), 400
    except Exception:
        app.logger.exception("Stockfish request failed")
        return jsonify({"error": "Engine unavailable"}), 500


@app.post("/play")
def play_turn():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    fen = data.get("fen")
    player_move = data.get("move")
    level = data.get("level", 5)

    if not isinstance(fen, str) or len(fen) > 200:
        return jsonify({"error": "Invalid FEN"}), 400

    if isinstance(level, bool) or not isinstance(level, int):
        return jsonify({"error": "Invalid level"}), 400

    level = max(1, min(20, level))

    try:
        board = chess.Board(fen)

        if not board.is_valid():
            return jsonify({"error": "Invalid position"}), 400

        if board.is_game_over():
            return jsonify({"error": "Game is over"}), 400

        engine_move_str = None

        # Obsługa sytuacji, gdy gracz gra czarnymi i silnik ma wykonać pierwszy ruch (brak ruchu gracza)
        if player_move and player_move != "":
            if not isinstance(player_move, str) or len(player_move) > 5:
                return jsonify({"error": "Invalid move"}), 400

            move = chess.Move.from_uci(player_move)

            if move not in board.legal_moves:
                return jsonify({"error": "Illegal move"}), 400

            board.push(move)
            player_move_uci = move.uci()
        else:
            player_move_uci = None

        if board.is_game_over():
            return jsonify({
                "player_move": player_move_uci,
                "engine_move": None,
                "fen": board.fen(),
                "game_over": True,
                "result": board.result()
            })

        with engine_lock:
            chess_engine = get_engine()
            chess_engine.configure({"Skill Level": level})
            response = chess_engine.play(
                board, chess.engine.Limit(time=0.5)
            )

        board.push(response.move)
        engine_move_str = response.move.uci()

        return jsonify({
            "player_move": player_move_uci,
            "engine_move": engine_move_str,
            "fen": board.fen(),
            "game_over": board.is_game_over(),
            "result": board.result() if board.is_game_over() else None
        })

    except ValueError:
        return jsonify({"error": "Invalid move or position"}), 400
    except Exception:
        app.logger.exception("Chess turn failed")
        return jsonify({"error": "Engine unavailable"}), 500
