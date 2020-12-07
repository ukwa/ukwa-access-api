import os
import json

# Get the crawler stats file:
def load_fc_analysis():
    with open(os.environ.get("ANALYSIS_SOURCE_FILE", "test/data/fc.crawled.json")) as f:
        stats = json.load(f)
    return stats


