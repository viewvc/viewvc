## Database Management Tool Consolidation

The ViewVC database management functionality has been consolidated into a single `manage-database` tool that replaces the previous separate scripts.

### Summary of Changes

**Scripts Replaced:**
- `make-database` → `manage-database --create`
- `schema-migrate` → `manage-database --migrate` 
- `schema-validate` → `manage-database --validate`

**Parameter Standardization:**
- `--host` → `--hostname`
- `--user` → `--username`
- `--database` (unchanged)
- `--password` (unchanged)

**Operation Requirements:**
- All operations now require explicit specification
- Exactly one operation must be chosen: `--create`, `--migrate`, `--validate`, or `--check-version`

### Examples

```bash
# Create new database with latest schema
manage-database --create --username=root --database=ViewVC

# Check current schema version
manage-database --check-version --username=viewvc --database=ViewVC

# Migrate existing database to latest schema
manage-database --migrate --username=viewvc --database=ViewVC

# Validate database and get recommendations
manage-database --validate --username=viewvc --database=ViewVC

# Show what migration would do (dry run)
manage-database --migrate --dry-run --username=viewvc --database=ViewVC
```

### Compatibility Impact

**Breaking Changes:**
1. **Script names changed** - Automation using old script names must be updated
2. **Parameter names changed** - `--host` and `--user` are no longer valid
3. **Operation specification required** - Scripts can no longer default to checking operations

**Migration Required:**
- Update any deployment scripts, documentation, or automation
- Change parameter names in existing command-line usage
- Add explicit operation flags to existing commands

All functionality from the previous tools is preserved in the new consolidated tool.
