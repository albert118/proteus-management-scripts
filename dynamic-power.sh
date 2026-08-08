#!/bin/bash

# Combine with a background daemon to run this dynamically
#[Unit]
#Description=Dynamic Power Profile Switcher for Threadripper
#After=power-profiles-daemon.service
#
#[Service]
#Type=simple
#ExecStart=/usr/local/bin/dynamic-power.sh
#Restart=always
#
#[Install]
#WantedBy=multi-user.target


# Configuration Thresholds
BALANCED_THRESHOLD=35    # Trigger balanced if any core > 35%
PERF_THRESHOLD=80        # Trigger performance if any core > 80%

CHECK_INTERVAL=10        # Check system state every 10 seconds
COOLDOWN_PERIOD=60       # Stay in a higher power state for at least 60 seconds before stepping down
LOG_FILE="/var/log/power_profile_audit.log"

# Tracking variables
LAST_SCALE_UP_TIME=0
LAST_STATE_CHANGE_TIME=$(date +%s)

# Ensure log file exists with proper permissions
touch "$LOG_FILE"

# Helper to capture raw per-core CPU statistics
get_cpu_stats() {
    grep '^cpu[0-9]' /proc/stat
}

while true; do
    # Capture delta snapshots
    stats1=$(get_cpu_stats)
    sleep 1
    stats2=$(get_cpu_stats)

    # Process all logical threads simultaneously using rapid AWK parallel processing
    MAX_CORE_USAGE=$(awk -v b_thresh="$BALANCED_THRESHOLD" -v p_thresh="$PERF_THRESHOLD" '
        NR==FNR {
            id1[$1] = $5 + $6
            tot1[$1] = $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9
            next
        }
        {
            id2 = $5 + $6
            tot2 = $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9
            dtot = tot2 - tot1[$1]
            if (dtot > 0) {
                usage = 100 * (dtot - (id2 - id1[$1])) / dtot
                if (usage > max) max = usage
            }
        }
        END { print int(max) }
    ' <(echo "$stats1") <(echo "$stats2"))

    # Determine desired profile based on highest core usage
    if [ "$MAX_CORE_USAGE" -gt "$PERF_THRESHOLD" ]; then
        TARGET_PROFILE="performance"
    elif [ "$MAX_CORE_USAGE" -gt "$BALANCED_THRESHOLD" ]; then
        TARGET_PROFILE="balanced"
    else
        TARGET_PROFILE="power-saver"
    fi

    # Fetch current operational profile
    CURRENT_PROFILE=$(powerprofilesctl get)
    CURRENT_TIME=$(date +%s)

    # Map profile priority weightings for structural hierarchy comparison
    declare -A profile_weight=( ["power-saver"]=1 ["balanced"]=2 ["performance"]=3 )
    TARGET_WEIGHT=${profile_weight[$TARGET_PROFILE]}
    CURRENT_WEIGHT=${profile_weight[$CURRENT_PROFILE]}

    # Execute state change evaluation
    NEW_PROFILE="$CURRENT_PROFILE"
    if [ "$TARGET_WEIGHT" -gt "$CURRENT_WEIGHT" ]; then
        powerprofilesctl set "$TARGET_PROFILE"
        NEW_PROFILE="$TARGET_PROFILE"
        LAST_SCALE_UP_TIME=$CURRENT_TIME
    elif [ "$TARGET_WEIGHT" -lt "$CURRENT_WEIGHT" ]; then
        ELAPSED_TIME=$((CURRENT_TIME - LAST_SCALE_UP_TIME))
        if [ "$ELAPSED_TIME" -ge "$COOLDOWN_PERIOD" ]; then
            powerprofilesctl set "$TARGET_PROFILE"
            NEW_PROFILE="$TARGET_PROFILE"
        fi
    fi

    # If the profile actually changed, log the duration spent in the PREVIOUS profile
    if [ "$NEW_PROFILE" != "$CURRENT_PROFILE" ]; then
        DURATION=$((CURRENT_TIME - LAST_STATE_CHANGE_TIME))
        TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
        echo "[$TIMESTAMP] Profile changed from $CURRENT_PROFILE to $NEW_PROFILE. Time spent in $CURRENT_PROFILE: ${DURATION}s" >> "$LOG_FILE"
        LAST_STATE_CHANGE_TIME=$CURRENT_TIME
    fi

    # Periodically append a current profile heartbeat every hour to ensure data continuity
    if [ $((CURRENT_TIME % 3600)) -lt "$CHECK_INTERVAL" ]; then
        DURATION=$((CURRENT_TIME - LAST_STATE_CHANGE_TIME))
        TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
        echo "[$TIMESTAMP] Hourly Heartbeat. Currently in $NEW_PROFILE for ${DURATION}s" >> "$LOG_FILE"
    fi

    # Adjust sleep execution time to offset the 1-second sample delay
    sleep $((CHECK_INTERVAL - 1))
done