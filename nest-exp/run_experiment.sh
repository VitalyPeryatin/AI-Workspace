#!/usr/bin/env bash
# Эксперимент: стоимость вложенной оркестрации (глубина 0..3) в OpenCode.
# Прогоняет одну и ту же по сложности задачу через агентов разной глубины
# и пишет метку времени старта, чтобы валидатор мог найти нужные сессии.
#
# Использование:
#   ./run_experiment.sh [--all] [--depth N] [--model provider/model]
#
# Опции:
#   --all       прогнать все 4 глубины (по умолчанию)
#   --depth N   прогнать только одну глубину (0..3)
#   --model M   модель для прогонов (по умолчанию: ollama-cloud/deepseek-v4-flash:0731)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS_DIR="$ROOT/nest-exp/tasks"
LOGS_DIR="$ROOT/nest-exp/logs"
MARKER_FILE="$ROOT/nest-exp/logs/experiment_start_ts.txt"
STARTS_HISTORY="$ROOT/nest-exp/logs/experiment_starts.txt"

MODEL="ollama-cloud/deepseek-v4-flash:0731"
DEPTHS="0 1 2 3"
ONLY_DEPTH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) DEPTHS="0 1 2 3"; shift ;;
    --depth) ONLY_DEPTH="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    *) echo "Неизвестная опция: $1"; exit 1 ;;
  esac
done

if [[ -n "$ONLY_DEPTH" ]]; then
  DEPTHS="$ONLY_DEPTH"
fi

mkdir -p "$LOGS_DIR"

# Агент для каждой глубины: 0 -> nest-direct (primary, сам решает),
# 1..3 -> nest-orch-N (subagent-оркестратор, делегирует вниз).
agent_for_depth() {
  case "$1" in
    0) echo "nest-direct" ;;
    1) echo "nest-orch-1" ;;
    2) echo "nest-orch-2" ;;
    3) echo "nest-orch-3" ;;
    *) echo "nest-direct" ;;
  esac
}

# Очистка результатов предыдущих прогонов, чтобы задачи были идентичными
rm -f "$TASKS_DIR"/task_depth*.py

# Отметка старта эксперимента: все сессии, созданные после этого
# момента (unix ms), считаются принадлежащими прогону.
# История стартов хранится в experiment_starts.txt, чтобы валидатор
# мог усреднять по нескольким прогонам.
START_TS="$(python3 -c 'import time; print(int(time.time()*1000))')"
echo "$START_TS" > "$MARKER_FILE"
echo "$START_TS" >> "$STARTS_HISTORY"
echo "Старт эксперимента: $(date '+%Y-%m-%d %H:%M:%S') (ts=$START_TS)"
echo "Модель: $MODEL"

for depth in $DEPTHS; do
  AGENT="$(agent_for_depth "$depth")"
  TASK_FILE="$TASKS_DIR/task_depth${depth}.md"
  LOG_FILE="$LOGS_DIR/depth${depth}.log"

  echo ""
  echo "=== Глубина $depth: агент $AGENT ==="
  echo "Задача: $(basename "$TASK_FILE")"

  TASK_TEXT="$(cat "$TASK_FILE")"

  # --title уникален для каждой глубины, чтобы валидатор мог
  # однозначно сопоставить сессии с прогонами.
  set +e
  opencode run \
    --agent "$AGENT" \
    --model "$MODEL" \
    --title "nest-exp-depth-${depth}" \
    --dir "$ROOT" \
    --auto \
    "$TASK_TEXT" 2>&1 | tee "$LOG_FILE"
  RC=${PIPESTATUS[0]}
  set -e

  if [[ $RC -ne 0 ]]; then
    echo "⚠️  Глубина $depth завершилась с кодом $RC (см. $LOG_FILE)"
  else
    echo "✅ Глубина $depth завершена (лог: $LOG_FILE)"
  fi
done

echo ""
echo "=== Прогон завершён ==="
echo "Запусти валидатор: python3 nest-exp/validate_tokens.py"
