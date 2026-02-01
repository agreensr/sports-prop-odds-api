#!/bin/bash
# Daily Accuracy Check Script
# This script runs a complete accuracy analysis workflow

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Daily Prediction Accuracy Check${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Create reports directory if it doesn't exist
mkdir -p reports
mkdir -p data/json

# Step 1: Update prediction tracking with actual results
echo -e "${YELLOW}Step 1: Updating prediction tracking...${NC}"
if python3 scripts/update_prediction_tracking.py; then
    echo -e "${GREEN}✓ Prediction tracking updated${NC}"
else
    echo -e "${RED}✗ Failed to update prediction tracking${NC}"
    exit 1
fi
echo ""

# Step 2: Generate overall accuracy report
echo -e "${YELLOW}Step 2: Generating accuracy report...${NC}"
DATE=$(date +%Y%m%d)
REPORT_FILE="reports/accuracy_${DATE}.txt"
JSON_FILE="data/json/accuracy_${DATE}.json"

if python3 scripts/test_prediction_accuracy.py --output "$REPORT_FILE"; then
    echo -e "${GREEN}✓ Report saved to: $REPORT_FILE${NC}"
else
    echo -e "${RED}✗ Failed to generate accuracy report${NC}"
    exit 1
fi
echo ""

# Step 3: Export JSON for historical tracking
echo -e "${YELLOW}Step 3: Exporting JSON data...${NC}"
if python3 scripts/test_prediction_accuracy.py --json > "$JSON_FILE"; then
    echo -e "${GREEN}✓ JSON saved to: $JSON_FILE${NC}"
else
    echo -e "${RED}✗ Failed to export JSON${NC}"
    exit 1
fi
echo ""

# Step 4: Show summary statistics
echo -e "${YELLOW}Step 4: Summary Statistics${NC}"
echo -e "${GREEN}========================================${NC}"

# Extract key metrics from report
ACCURACY=$(grep "Correct:" "$REPORT_FILE" | awk '{print $2}')
TOTAL=$(grep "Total Predictions:" "$REPORT_FILE" | awk '{print $3}')
MAE=$(grep "Mean Absolute Error:" "$REPORT_FILE" | awk '{print $4}')
CAL_ERROR=$(grep "Calibration Error:" "$REPORT_FILE" | awk '{print $3}')

echo -e "Total Predictions: ${GREEN}$TOTAL${NC}"
echo -e "Accuracy Rate: ${GREEN}$ACCURACY${NC}"
echo -e "Mean Absolute Error: ${GREEN}$MAE${NC}"
echo -e "Calibration Error: ${GREEN}$CAL_ERROR${NC}"
echo ""

# Step 5: Check for issues
echo -e "${YELLOW}Step 5: Health Check${NC}"
echo -e "${GREEN}========================================${NC}"

# Extract calibration error numeric value
CAL_NUM=$(echo "$CAL_ERROR" | sed 's/%//')
if (( $(echo "$CAL_NUM > 15" | bc -l) )); then
    echo -e "${RED}⚠ High calibration error (>15%) - Model needs recalibration${NC}"
elif (( $(echo "$CAL_NUM > 10" | bc -l) )); then
    echo -e "${YELLOW}⚠ Moderate calibration error (>10%) - Monitor closely${NC}"
else
    echo -e "${GREEN}✓ Calibration error is acceptable${NC}"
fi

# Check sample size
if [ "$TOTAL" -lt 10 ]; then
    echo -e "${YELLOW}⚠ Small sample size (<10 predictions) - Results may not be representative${NC}"
else
    echo -e "${GREEN}✓ Adequate sample size${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Daily accuracy check complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Full report: $REPORT_FILE"
echo "JSON data: $JSON_FILE"
echo ""
echo "View report:"
echo "  cat $REPORT_FILE"
echo ""
echo "View JSON:"
echo "  cat $JSON_FILE | python -m json.tool"
echo ""
