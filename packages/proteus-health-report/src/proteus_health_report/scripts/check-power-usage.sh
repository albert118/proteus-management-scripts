#!/bin/bash
# Checks the average power profile usage based on the audit logs from the related service

# TARGET_DATE="${1:-$(date "+%Y-%m-%d")}"
TARGET_DATE="2026-09-01"
LOG_FILE="/var/log/power_profile_audit.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "Error: Audit log file not found at $LOG_FILE"
    exit 1
fi

# 1. Filter log entries strictly for the target date
DAY_LOGS=$(grep "^\[$TARGET_DATE" "$LOG_FILE")

if [ -z "$DAY_LOGS" ]; then
    echo "No data recorded for $TARGET_DATE."
    exit 0
fi

# 2. Extract seconds per profile using clean greps, summed by a simple awk command
sum_seconds() {
    echo "$DAY_LOGS" | grep -E "Time spent in $1:|Currently in $1" | awk -F '[:s]' '{sum += $(NF-1)} END {print sum+0}'
}

SAVER_SEC=$(sum_seconds "power-saver")
BALANCED_SEC=$(sum_seconds "balanced")
PERF_SEC=$(sum_seconds "performance")

TOTAL_SEC=$((SAVER_SEC + BALANCED_SEC + PERF_SEC))
[ "$TOTAL_SEC" -eq 0 ] && TOTAL_SEC=1 # Prevent division by zero

# 3. Count profile transitions
TRANSITIONS=$(echo "$DAY_LOGS" | grep -c "Profile changed from")

# 4. Print Time Spent Profile Dashboard
echo " TIME SPENT PER PROFILE:"
echo "--------------------------------------------------"
printf " * %-15s : %6.2f hours  (%5.1f%%)\n" "power-saver"  "$(bc -l <<< "$SAVER_SEC / 3600")"  "$(bc -l <<< "($SAVER_SEC / $TOTAL_SEC) * 100")"
printf " * %-15s : %6.2f hours  (%5.1f%%)\n" "balanced"     "$(bc -l <<< "$BALANCED_SEC / 3600")" "$(bc -l <<< "($BALANCED_SEC / $TOTAL_SEC) * 100")"
printf " * %-15s : %6.2f hours  (%5.1f%%)\n" "performance"  "$(bc -l <<< "$PERF_SEC / 3600")"   "$(bc -l <<< "($PERF_SEC / $TOTAL_SEC) * 100")"

# 5. Print Stability Metrics
echo -e "\n SYSTEM STABILITY & ACTIVITY SYNC:"
echo "--------------------------------------------------"
echo " * Profile Transitions Triggered : $TRANSITIONS changes"
if [ "$TRANSITIONS" -gt 150 ]; then
    echo " ! WARNING: High frequency thrashing detected. Consider raising COOLDOWN_PERIOD."
else
    echo " * Stability Rating             : Optimal"
fi

# 6. Print Activity Peaks
echo -e "\n CHRONOLOGICAL SURGES TODAY:"
echo "--------------------------------------------------"
echo "$DAY_LOGS" | grep "to performance" | head -n 3 | awk '{print " * Heavy workload peak detected at: " $2}' || true
if ! echo "$DAY_LOGS" | grep -q "to performance"; then
    echo " * No severe single-core performance surges hit the hardware today."
fi
