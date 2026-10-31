# Handoff format (cross-session)

Append one block to `HANDOFF.md` at the end of each session or checkpoint. Newest block at the bottom; do not rewrite old blocks.

```
## Session YYYY-MM-DD: <topic>
- Repo / branch / HEAD (full SHA, read back with git ls-remote)
- Done: <what changed, with paths>
- Verified: <commands run and their result>; anything else NOT_VERIFIED
- Open: <blockers, risks, decisions waiting for the user>
- Next safe action: <one step>
- Local-only artifacts: <runs/... path + SHA-256 list location>
```

Rules: repo files override chat memory; keep each block under ~15 lines; long detail goes into the report the block links to.
