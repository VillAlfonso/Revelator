#!/bin/bash
# Watch synthesis progress in real-time

TARGET=7350
while true; do
  TRAIN=$(ls -1 /c/Revelator/models/traced_indentation/synthetic/train/images 2>/dev/null | wc -l)
  VALID=$(ls -1 /c/Revelator/models/traced_indentation/synthetic/valid/images 2>/dev/null | wc -l)
  TEST=$(ls -1 /c/Revelator/models/traced_indentation/synthetic/test/images 2>/dev/null | wc -l)
  TOTAL=$((TRAIN + VALID + TEST))
  PCT=$((TOTAL * 100 / TARGET))

  clear
  echo "=== SYNTHESIS PROGRESS ==="
  echo "Train: $TRAIN"
  echo "Valid: $VALID"
  echo "Test:  $TEST"
  echo "---"
  echo "Total: $TOTAL / $TARGET ($PCT%)"
  echo ""

  if [ -f /c/Revelator/models/traced_indentation/synthetic/data.yaml ]; then
    echo "✓ SYNTHESIS COMPLETE!"
    break
  fi

  sleep 5
done
