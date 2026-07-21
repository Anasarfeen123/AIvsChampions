#!/usr/bin/env bash
set -e

PORT="${PORT:-8000}"
export PORT
export PSPORT="$PORT"

echo "🚀 Starting Pokémon Showdown on port $PORT..."
node pokemon-showdown start "$PORT" &
SERVER_PID=$!

echo "⏳ Waiting for Showdown server to initialize..."
sleep 3

echo "🤖 Starting Pokémon AI backend..."
python3 AI.py --provider puter --server localhost &
AI_PID=$!

wait -n $SERVER_PID $AI_PID
