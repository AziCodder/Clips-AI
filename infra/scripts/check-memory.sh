#!/bin/bash
# Проверка использования RAM на сервере (запускать на VPS по SSH)

set -e

echo "========== Память (free -h) =========="
free -h

echo ""
echo "========== Кратко: доступно для приложений =========="
awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {printf "Всего: %.1f GB | Доступно (available): %.1f GB\n", t/1024/1024, a/1024/1024}' /proc/meminfo

echo ""
echo "========== Docker: потребление по контейнерам =========="
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""
echo "========== Топ-10 процессов по RAM =========="
ps aux --sort=-%mem | head -11
