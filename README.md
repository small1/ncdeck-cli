# ncdeck

A lightweight CLI for [Nextcloud Deck](https://apps.nextcloud.com/apps/deck) that lets you create and manage cards across multiple Nextcloud instances without leaving the terminal.

## What it can do

- **Create rich cards** — titles with prefixes, due dates (`today`, `tomorrow`, `2026-11-11`, or full timestamps), tags by name, descriptions from inline text / files / stdin, assignees, and file attachments.
- **Work with existing cards** — mark done (and move to a done stack), move between stacks, assign/unassign users, add comments, set or amend descriptions, and attach files.
- **See everything at a glance** — `list --cards`, `search`, and `show` display assignees, due dates, colored label chips, task-list counters (`[done/total]`), comment counters (`[💬 n]`), dependencies (`[🔗 #id]`), and prominent `OVERDUE` / `DONE` status. In a terminal, `show` also renders descriptions and comments as Markdown (use `--raw` for the source).
- **Plan your day** — `agenda yesterday|today|tomorrow|week|month` (with `-A` for all instances) and the interactive `completed` review that marks cards done or pushes the rest to the next day.
- **Multiple instances** — one config, short board/instance names, per-instance theme colors, cached labels (with colors), and shared-board filtering.
- **Bulk cleanup** — `archive BOARD BEFORE_DATE` to archive old done cards.

## Quick Start

### Installation

```bash
pip install .
```

Or for development:

```bash
pip install -e .
```

### Configuration

There are two ways to add accounts.

**1. Automatic — `ncdeck account add` (primary and easiest)**

This is the recommended way. It uses Nextcloud Login Flow v2: a browser opens for you to approve the login, then `ncdeck` auto-discovers boards, stacks, labels (with colors), the done stack, and the instance theme color. It prompts you for short names and merges everything into your config — no manual ID hunting and no app password to paste.

```bash
ncdeck account add

# Optionally pre-fill the server URL and short instance name
ncdeck account add --url https://cloud.example.com -i work
```

**2. Manual**

Create `~/.config/ncdeck/config.yaml` yourself (see [config.example.yaml](config.example.yaml)):

```yaml
default_instance: work
instances:
  work:
    url: https://nextcloud.example.com
    username: alice
    password: app-password-here
    boards:
      inbox:
        board_id: 1
        stack_id: 5
        done_stack_id: 10
      bugs:
        board_id: 2
        stack_id: 9
```

See [README_FULL.md](README_FULL.md) for every config option, `ncdeck account list/delete`, and `ncdeck config color`.

### Usage

```bash
# See what is configured
ncdeck account list
ncdeck labels inbox

# Create a card
ncdeck create inbox "Fix login bug" -p "[BUG]" -t bug --due-date tomorrow
```

## More examples

### Cards

```bash
# Prefix, due date, tags, description, and assignee
ncdeck create inbox "Fix login bug" -p "[BUG]" --due-date 2026-11-11 -t bug -t critical -d "Fails on Safari" -a alice

# Description from a Markdown file, plus an attachment
ncdeck create bugs "Crash on upload" -f ./crash-report.md --attach ./debug.log

# Inspect
ncdeck list --cards inbox
ncdeck show inbox 123
ncdeck search inbox "login"

# Update
ncdeck description inbox 123 --amend "Follow-up: fixed in 18.1"
ncdeck comment inbox 123 "Waiting on QA"
ncdeck assign inbox 123 bob
ncdeck attach inbox 123 ./screenshot.png
ncdeck move inbox 123 7
ncdeck done inbox 123
```

### Agenda and planning

```bash
# Review what was due yesterday (handy for items you forgot to close or move)
ncdeck agenda yesterday

# Due today on the default instance
ncdeck agenda today

# Tomorrow, the next 7 days, or the next 30 days
ncdeck agenda tomorrow
ncdeck agenda week
ncdeck agenda month

# Across every configured instance / include unassigned cards on shared boards
ncdeck agenda today -A
ncdeck agenda week --all

# Focus on one instance
ncdeck agenda today -i work

# Interactive daily review: mark selected cards done, push the rest to tomorrow
ncdeck completed
ncdeck completed -A

# Archive done cards older than a date
ncdeck archive inbox 2026-01-01 -y
```

See [README_FULL.md](README_FULL.md) for complete documentation.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
