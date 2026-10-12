# Level 3 integration validation — 2026-10-12

PR #9 incorporates the corrected Level 2 branch from PR #8 at `ddcdef51fa5c94ebd654af3e0e4642cd277849aa`, which includes `main` at `6333bbb2b5f606ef53afe9865cd7fa337cba04ef` and the merged Level 1 course from PR #4.

## Preserved behavior and scope

- Level 1 materials, first-time setup, and existing runtime/environment files match `main` exactly.
- Level 2 materials, case fixtures, BI modules, shared sidecar helper, language/link checks, and its validation record match PR #8 exactly.
- Level 3 retains Modules 12–14, publishing/audit, backup, and workload helpers, its explicit-start backup environment, and the existing corresponding tests. Its executable Notebooks and quizzes are unchanged from the previous PR #9 head.
- The full-course English check covers authored material across all three levels and the shared runtime. Existing Level 2 link checks and Level 3 material/link tests remain enabled.
- Level 3 startup guidance follows the merged Level 1 runtime: start Doris explicitly in Lab 1; connection refusal directs the learner back there.

The shared course overview is identical in both PRs. Level 3 adds its entry link in a separate paragraph away from the Level 2 navigation change. Its integration evidence is recorded here rather than modifying Level 2's newly added validation file. These choices avoid overlapping edits and add/add conflicts after a squash merge.

## Current verification

- `python -m unittest discover -s maintenance/02-data-warehousing/tests`: **173 passed**.
- Executed the actual initialization cells from Labs 8–14 with mocked SQL/Docker boundaries: **28 checks passed**, covering healthy connections, refusal codes 2002/2003 with Lab 1 guidance, and authentication-error propagation. No connection cell starts the sandbox.
- Git tree comparisons verify the preserved files listed above. All changes relative to the corrected Level 2 branch are confined to Level 3 materials/helpers/tests, its backup environment, the separate navigation paragraph, and this record.
- Whitespace checks pass against both current `main` and the corrected Level 2 branch.

## Merge previews

Local `git commit-tree` previews model both merge methods using the corrected Level 2 tree. `git merge-tree --write-tree` checks each target against the integrated Level 3 branch:

| Target state | Result |
| --- | --- |
| Current main | No conflicts; identical final Level 3 tree |
| Level 2 merged with a merge commit | No conflicts; identical final Level 3 tree |
| Level 2 squash-merged onto current main | No conflicts; identical final Level 3 tree |

The previews cover the recorded main and Level 2 revisions. New changes to either branch require another check. PR #8 remains the intended first merge; PR #9 then adds Level 3 on top of it.

## Self-review conclusions

| Checkpoint | Conclusion |
| --- | --- |
| Scope and reuse | Existing Level 1/2 implementations are retained; Level 3 reuses the corrected shared runtime and sidecar helper. No new runtime feature is introduced by this integration. |
| Compatibility and failures | Actual initialization-cell checks confirm connection success and failure behavior. Existing prerequisite, resource-profile, and SQL-session recovery tests pass. |
| Lifecycle and concurrency | Existing Level 3 cleanup and workload behavior are unchanged and remain covered by the unit/material suite. No new threads, locks, or service startup paths are added. |
| Navigation and future merges | Level 3 is reachable from the course entry. Both normal and squash merge previews preserve the same integrated tree. |
| Validation limits | No live SQL Labs, Docker startup, or browser checks were rerun. Historical execution evidence remains in `ENHANCEMENTS-VALIDATION.md`; this integration does not expand those claims. |
