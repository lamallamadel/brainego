#!/bin/bash
# Cost Optimization Workflow
# End-to-end workflow for analyzing and optimizing resource usage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus:9090}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-7}"
OUTPUT_DIR="${OUTPUT_DIR:-./cost-optimization-reports}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "========================================================================"
echo "Cost Optimization Workflow"
echo "========================================================================"
echo "Timestamp: $TIMESTAMP"
echo "Prometheus URL: $PROMETHEUS_URL"
echo "Lookback Period: $LOOKBACK_DAYS days"
echo "Output Directory: $OUTPUT_DIR"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Step 1: Analyze resource usage
echo "Step 1: Analyzing resource usage..."
echo "------------------------------------------------------------------------"
RECOMMENDATIONS_FILE="$OUTPUT_DIR/recommendations_${TIMESTAMP}.json"

python "$SCRIPT_DIR/analyze_resource_usage.py" \
  && echo "✓ Analysis complete" \
  || { echo "✗ Analysis failed"; exit 1; }

# Move output to timestamped file
mv resource_recommendations.json "$RECOMMENDATIONS_FILE"

echo ""

# Step 2: Generate summary
echo "Step 2: Generating recommendation summary..."
echo "------------------------------------------------------------------------"
python "$SCRIPT_DIR/apply_recommendations.py" \
  "$RECOMMENDATIONS_FILE" \
  --summary \
  && echo "✓ Summary generated" \
  || { echo "✗ Summary failed"; exit 1; }

echo ""

# Step 3: Generate Helm values patch
echo "Step 3: Generating Helm values patch..."
echo "------------------------------------------------------------------------"
HELM_PATCH_FILE="$OUTPUT_DIR/helm-values-patch_${TIMESTAMP}.yaml"

python "$SCRIPT_DIR/apply_recommendations.py" \
  "$RECOMMENDATIONS_FILE" \
  -o "$HELM_PATCH_FILE" \
  && echo "✓ Helm patch generated: $HELM_PATCH_FILE" \
  || { echo "✗ Helm patch generation failed"; exit 1; }

echo ""

# Step 4: Archive old Qdrant data (optional)
if [ "${RUN_ARCHIVAL:-false}" = "true" ]; then
  echo "Step 4: Running Qdrant archival..."
  echo "------------------------------------------------------------------------"
  python "$SCRIPT_DIR/qdrant_archival_service.py" \
    && echo "✓ Archival complete" \
    || { echo "✗ Archival failed"; exit 1; }
  echo ""
fi

# Summary
echo "========================================================================"
echo "Workflow Complete"
echo "========================================================================"
echo ""
echo "Generated files:"
echo "  - Recommendations: $RECOMMENDATIONS_FILE"
echo "  - Helm values patch: $HELM_PATCH_FILE"
echo ""
echo "Next steps:"
echo "  1. Review recommendations in: $RECOMMENDATIONS_FILE"
echo "  2. Test Helm patch in staging:"
echo "       helm upgrade ai-platform ./helm/ai-platform -f $HELM_PATCH_FILE --dry-run"
echo "  3. Apply to production:"
echo "       helm upgrade ai-platform ./helm/ai-platform -f $HELM_PATCH_FILE"
echo "  4. Monitor Cost Dashboard in Grafana:"
echo "       http://<grafana-url>/d/cost-optimization/cost-optimization-finops"
echo ""
echo "========================================================================"
