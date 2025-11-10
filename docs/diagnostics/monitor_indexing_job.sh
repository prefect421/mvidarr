#!/bin/bash

# Monitor the indexing job on production server
JOB_ID="29b47baf-a681-4919-ba6a-aedb51a1c0a3"
SERVER="http://192.168.1.132:5050"
CHECK_INTERVAL=10  # Check every 10 seconds
EXPECTED_VIDEOS=2300

echo "====================================================="
echo "Monitoring Indexing Job: $JOB_ID"
echo "Expected videos: $EXPECTED_VIDEOS+"
echo "Check interval: ${CHECK_INTERVAL}s"
echo "====================================================="
echo ""

LAST_STATUS=""
LAST_PROGRESS=""
NO_CHANGE_COUNT=0
MAX_NO_CHANGE=30  # Alert if no change for 5 minutes (30 * 10s)

while true; do
    # Get job status
    RESPONSE=$(curl -s "${SERVER}/api/metadata-enrichment/job/${JOB_ID}/status")

    # Extract key fields
    STATUS=$(echo "$RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    PROGRESS=$(echo "$RESPONSE" | grep -o '"progress":[^,}]*' | cut -d':' -f2)
    READY=$(echo "$RESPONSE" | grep -o '"ready":[^,}]*' | cut -d':' -f2)
    FAILED=$(echo "$RESPONSE" | grep -o '"failed":[^,}]*' | cut -d':' -f2)

    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Check if status or progress changed
    if [ "$STATUS" != "$LAST_STATUS" ] || [ "$PROGRESS" != "$LAST_PROGRESS" ]; then
        echo "[$TIMESTAMP] Status: $STATUS | Progress: $PROGRESS | Ready: $READY | Failed: $FAILED"
        LAST_STATUS="$STATUS"
        LAST_PROGRESS="$PROGRESS"
        NO_CHANGE_COUNT=0
    else
        NO_CHANGE_COUNT=$((NO_CHANGE_COUNT + 1))

        # Warn if stuck
        if [ $NO_CHANGE_COUNT -ge $MAX_NO_CHANGE ] && [ "$STATUS" != "SUCCESS" ] && [ "$STATUS" != "FAILURE" ]; then
            echo "[$TIMESTAMP] ⚠️  WARNING: No progress for $((NO_CHANGE_COUNT * CHECK_INTERVAL)) seconds!"
            NO_CHANGE_COUNT=0  # Reset to avoid spam
        fi
    fi

    # Check completion conditions
    if [ "$READY" = "true" ]; then
        if [ "$STATUS" = "SUCCESS" ]; then
            echo "[$TIMESTAMP] ✅ Job completed successfully!"
            echo ""
            echo "Final status: $RESPONSE"
            break
        elif [ "$FAILED" = "true" ]; then
            echo "[$TIMESTAMP] ❌ Job failed!"
            echo ""
            echo "Final status: $RESPONSE"
            break
        fi
    fi

    sleep $CHECK_INTERVAL
done

echo ""
echo "Monitoring complete."
