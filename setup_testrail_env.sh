#!/bin/bash
# TestRail environment setup script

echo "=========================================="
echo "TestRail Environment Setup"
echo "=========================================="

# Check if credentials are already set
if [ -n "$TESTRAIL_API_KEY" ]; then
    echo "✓ TestRail credentials already configured"
    echo "  URL: $TESTRAIL_URL"
    echo "  Username: $TESTRAIL_USERNAME"
    echo "  Project ID: $TESTRAIL_PROJECT_ID"
    echo ""
    echo "To test connection, run:"
    echo "  python3 test_testrail_integration.py"
else
    echo "TestRail credentials not configured."
    echo ""
    echo "To configure, run these commands with your actual values:"
    echo ""
    echo "export TESTRAIL_URL='https://your-company.testrail.io'"
    echo "export TESTRAIL_USERNAME='your_email@example.com'"
    echo "export TESTRAIL_API_KEY='your_api_key_here'"
    echo "export TESTRAIL_PROJECT_ID='1'"
    echo ""
    echo "Optional settings:"
    echo "export TESTRAIL_SUITE_ID='1'"
    echo "export TESTRAIL_MILESTONE_ID='1'"
    echo "export TESTRAIL_BDD_SECTION_ID='1'"
    echo "export TESTRAIL_BATCH_SIZE='100'"
    echo "export TESTRAIL_ENABLE_CACHE='true'"
    echo ""
    echo "After setting credentials, run:"
    echo "  python3 test_testrail_integration.py"
fi

echo "=========================================="