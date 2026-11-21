"""Copy a workspace the way the harness sees it: every file that is tracked or
untracked, but not git-ignored. Falls back to a plain copy outside git."""

import os
import shutil
import subprocess


def export_tree(src, dst):
    files = None
    if os.path.isdir(os.path.join(src, ".git")):
        r = subprocess.run(["git", "-C", src, "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True)
        if r.returncode == 0:
            files = [f for f in r.stdout.decode("utf-8", "surrogateescape").split("\0") if f]
    if files is None:
        shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        return
    os.makedirs(dst, exist_ok=True)
    for f in files:
        s, d = os.path.join(src, f), os.path.join(dst, f)
        if not os.path.lexists(s):
            continue  # tracked but deleted in the working tree
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if os.path.islink(s):
            os.symlink(os.readlink(s), d)
        elif os.path.isfile(s):
            shutil.copy2(s, d)
