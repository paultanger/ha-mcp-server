A patch file is just a text description of changes to other files — not the files themselves. It records, line by line, "in this file, at this spot, these lines were removed and these were added." That's the format git diff produces, which is why hass-mcp-fork.patch is what I generated: it's the difference between voska's original code and my forked version, nothing more.
If you crack it open, the vocabulary is small:

Lines starting with --- and +++ name the old and new version of a file.
A line starting with @@ is a "hunk header." It says where the change lands, like @@ -256,7 +256,11 @@ meaning "around line 256: 7 lines in the original, 11 in the new." The hunks are the chunks of change.
Lines with a leading - are removed; leading + are added; lines with a leading space are unchanged context shown around the change so the tool (and you) can see where it fits.

That context is the clever part. A patch doesn't say "go to line 256" and blindly act — it says "find these surrounding lines, and make the change there." So even if the target file has drifted a bit, the patch can still locate the right spot.
How you use it: with git apply hass-mcp-fork.patch (or the older patch -p1 < file.patch) run from inside a fresh clone of voska/hass-mcp. Git reads the instructions and reproduces my exact edits on top of the original. The result is byte-identical to the fork I built — except it creates policy.py's changes to existing files; a brand-new file like policy.py itself is included in the patch too (shown as a diff against "nothing"). You'd typically git apply --check first to confirm it'll apply cleanly before committing.
Why people use them instead of just sending whole files:

Review. A reviewer sees only what changed, with a little surrounding context — not 1,500 unchanged lines they have to diff in their head. For your fork, the patch is ~400 lines; the full edited files would be a few thousand. The signal-to-noise is the whole point.
They travel without the codebase. A patch is small and self-contained. This is literally how Linux kernel development ran for years — contributors emailed patches to a mailing list rather than pushing whole files.
They apply on top of a moving target. Because patches locate changes by surrounding context, the same patch can often apply even after the base code has changed slightly — far more robust than "replace file X wholesale," which would clobber anyone else's edits.
They're the atom of version control. Every git commit is essentially a stored patch. git diff, code review tools, git cherry-pick — all of it is patches under the hood. You've been using them without seeing the raw form.

One caveat worth knowing: a patch can fail to apply if the base file has drifted too far from what the patch expects — the context lines no longer match. Git tells you which hunks failed and leaves .rej (reject) files so you can apply those by hand. For your case that's unlikely since you'd apply it to a fresh clone of the same repo, but it's why I suggested git apply --check first.
So in your fork workflow, the patch is the portable "here are my changes to voska's code" — and the standalone policy.py I gave you is just the convenience copy of the one entirely-new file, so you can read it without extracting it from the diff.


git clone https://github.com/voska/hass-mcp.git
cd hass-mcp
git checkout -b hermes-readonly
# dry run, confirms it'll apply clean
git apply --check ./hass-mcp-fork.patch   
git apply ./hass-mcp-fork.patch