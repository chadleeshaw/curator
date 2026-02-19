
## Production Migration

If you have existing discovered issues with the old provider name "IA", run this migration:

```bash
python scripts/fix_discovered_issues_provider.py
```

This updates the `discovered_issues.latest_provider` field from "IA" to "internet_archive" so downloads route to the correct client.

