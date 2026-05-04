# Ralph Agent Instructions For This Repository

You are an autonomous coding agent working inside `/home/carry/project2`.

## Canonical State Files

Read these files first:

1. PRD: `/home/carry/project2/prd.json`
2. Progress log: `/home/carry/project2/progress.txt`

The project root is the current working directory. Do not read or write `scripts/ralph/prd.json` or `scripts/ralph/progress.txt`; the canonical files are at the project root.

## Core Loop

1. Read `prd.json` and identify the highest-priority story where `passes` is `false`.
2. Read `progress.txt`, especially `Codebase Patterns`, `Hard Constraints`, and the latest history entry.
3. Confirm you are on the branch from `prd.json.branchName`. If not, switch to it or create it from the best available default branch.
4. Implement exactly one story in this iteration.
5. Run only the relevant verification for that story.
6. If the story passes, commit only story-related changes with message: `feat: [Story ID] - [Story Title]`.
7. Update `prd.json` to set that story's `passes` to `true`.
8. Append a new entry to `progress.txt`.

## Hard Constraints

- Treat the repository as a dirty shared worktree.
- Do not overwrite or revert unrelated user changes.
- Do not mass-commit historical dirty changes.
- Do not use `git reset --hard`.
- Do not use `git clean -fd` or `git clean -fdx`.
- Do not delete real PDFs, databases, migrations, fixtures, lockfiles, `.env*`, keys, or current delivery evidence.
- Do not fake success by editing databases manually, editing JSON by hand to pretend tests passed, or hiding frontend errors.
- Do not turn `conflict` into `matched` automatically.
- Do not add hardcoded task, page, question, bank, or answer special-cases.

## Story-Specific Guardrail

If the next story is one of the Git hygiene stories (`US-001` to `US-005`):

- Respect the cleanup and backup rules in `prd.json` and `progress.txt`.
- Keep unknown files by default.
- Never delete tracked source files unless the story explicitly proves they are safe generated artifacts and backup requirements are satisfied.
- Do not proceed into product fixes or end-to-end testing before the Git hygiene prerequisites are met.

## Commit Discipline

- Commit only files relevant to the current story.
- If unrelated tracked or untracked changes exist, leave them alone and mention them in `progress.txt` when relevant.
- If checks fail, do not mark the story passed and do not create a misleading commit.

## Verification Defaults

Use story-specific checks first. Unless the story clearly does not touch those areas, prefer these commands:

```bash
cd /home/carry/project2/backend && node -r ts-node/register -r tsconfig-paths/register test/pdf-review-workflow.test.ts
cd /home/carry/project2/backend && npm run build
cd /home/carry/project2/admin-web && npm run build
```

If `pdf-service` has a relevant test or build command for the story, run it or explicitly record why it could not be run.

## UI Stories

For UI-related stories, browser verification is required. Use a real browser-capable tool when available. Do not claim browser verification without opening the page, interacting with it, and saving evidence.

## Evidence

- Save story evidence under `debug/ralph-e2e/<storyId>-<timestamp>/`.
- Also save any story-specific evidence paths required by the PRD.
- Reference those paths in `progress.txt`.

## Progress Entry Format

Append to `progress.txt`; never replace prior history.

```text
[timestamp] US-XXX
- 实现/测试了什么:
- 修改文件:
- 清理了什么:
- 保留了什么:
- 运行了哪些命令:
- 结果是否通过:
- 截图/trace/debug 路径:
- 发现的可复用模式:
- 仍需后续 story 处理的问题:
```

Update `Codebase Patterns` near the top of `progress.txt` only when you learn a reusable repository-wide pattern.

## Completion Signal

After finishing one story, check whether all stories in `prd.json` now have `passes: true`.

If all stories are complete, output exactly:

```text
<promise>COMPLETE</promise>
```

Otherwise end normally.
