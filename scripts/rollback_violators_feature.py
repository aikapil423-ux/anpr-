"""
=============================================================================
ONE-CLICK ROLLBACK SCRIPT: TRAFFIC VIOLATIONS MANAGEMENT SYSTEM
=============================================================================
Usage:
    python scripts/rollback_violators_feature.py

Description:
    Instantly restores project files (app.py, static/index.html) to the
    exact state prior to the feature deployment from the latest backup.
=============================================================================
"""

import os
import shutil
import glob

def main():
    print("=" * 70)
    print("⏪ ONE-CLICK ROLLBACK TOOL")
    print("=" * 70)

    backups = sorted(glob.glob("backups/pre_violators_rollout_*"))
    if not backups:
        print("⚠️ No backup directory found in backups/! Nothing to rollback.")
        return

    latest_backup = backups[-1]
    print(f"Restoring from latest backup: {latest_backup}...")

    for root, dirs, files in os.walk(latest_backup):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, latest_backup)
            dest = rel
            shutil.copy2(src, dest)
            print(f"  [RESTORED] {dest} <- {src}")

    print("\n✅ ROLLBACK SUCCESSFUL! Project restored to pristine state.")

if __name__ == '__main__':
    main()
