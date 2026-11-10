# `ncdeck` - Nextcloud Deck CLI

`ncdeck` is a lightweight command-line tool to create cards in [Nextcloud Deck](https://apps.nextcloud.com/apps/deck) directly from your terminal. It supports markdown descriptions, due dates, labels/tags by name, custom prefixes, reading from files, piping from stdin, marking cards as done, and moving cards between stacks.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Commands](#commands)
- [Usage Examples](#usage-examples)
- [Tips & Notes](#tips--notes)
- [Troubleshooting](#troubleshooting)

## Features

- **Multi-instance support** - Manage multiple Nextcloud instances from a single config
- **Board shortcuts** - Use short `board_key` names instead of typing board/stack IDs every time
- **Custom prefixes** - Add any prefix to card titles on-the-fly with `-p/--prefix`
- **Markdown descriptions** - Pass descriptions directly, from a file (`-f`), or via piped stdin
- **Due dates** - Set due dates in ISO format
- **Tags/labels by name** - Use human-readable label names with `-t/--tag` instead of numeric IDs
- **Cached label discovery** - Labels (with colors) are discovered when a board is added and stored in config; list them with `ncdeck labels` or refresh with `ncdeck labels BOARD_KEY --refresh`
- **Mark as done** - Mark cards as done and automatically move them to a configured done stack
- **Move cards** - Move cards between any stacks on a board
- **Archive cards** - Optionally archive cards instead of moving to done stack
- **API version compatible** - Tries multiple endpoints when discovering labels across different Nextcloud Deck versions

## Requirements

- [Python 3.9+](https://www.python.org/)
- [Nextcloud](https://nextcloud.com/) with the [Deck](https://apps.nextcloud.com/apps/deck) app installed and enabled
- A Nextcloud account with access to the target boards
- An [App Password](https://docs.nextcloud.com/server/latest/user_manual/en/session_management.html#managing-devices) (strongly recommended, especially if 2FA is enabled)

### Python dependencies

- [`click`](https://click.palletsprojects.com/)
- [`requests`](https://requests.readthedocs.io/)
- [`PyYAML`](https://pyyaml.org/)

## Installation

1. **Install dependencies**

   ```bash
   pip install click requests pyyaml
   ```

2. **Download/install the script**

   From the project directory:
   ```bash
   pip install .
   ```
   
   Or for development:
   ```bash
   pip install -e .
   ```
   
   Or copy the script manually to a directory in your `$PATH` (e.g., `~/.local/bin/`):
   ```bash
   mkdir -p ~/.local/bin
   cp src/ncdeck/cli.py ~/.local/bin/ncdeck
   chmod +x ~/.local/bin/ncdeck
   ```

   Make sure `~/.local/bin` is in your `$PATH`. You can check with `echo $PATH` and add it to your shell rc if needed:

   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Create your config file**

   Copy the example config or see the [Configuration](#configuration) section below:
   ```bash
   mkdir -p ~/.config/ncdeck
   cp config.example.yaml ~/.config/ncdeck/config.yaml
   ```

4. **Verify**

   ```bash
   ncdeck --help
   ```

## Configuration

`ncdeck` looks for a config file in the following order:

1. `$XDG_CONFIG_HOME/ncdeck/config.yaml` (defaults to `~/.config/ncdeck/config.yaml`)
2. `~/.ncdeck.yaml`

See [config.example.yaml](config.example.yaml) for a complete example.

### Config structure

```yaml
# ~/.config/ncdeck/config.yaml

# Instance to use if none is specified with -i/--instance
default_instance: work

instances:
  work:
    url: https://nextcloud.example.com  # Required. No trailing slash
    username: alice                    # Required. Your Nextcloud username
    password: xxxx-xxxx-xxxx-xxxx     # Required. Use an App Password
    verify: true                      # Optional. Set to false for self-signed certificates (use with caution)
    boards:
      inbox:
        board_id: 1
        stack_id: 5
        done_stack_id: 10            # Optional. Stack to move cards to when marked as done
      bugs:
        board_id: 2
        stack_id: 9
        done_stack_id: 11
```

### Config options explained

| Option | Scope | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `default_instance` | Root | `string` | No | The instance key to use when `-i/--instance` is omitted. |
| `instances` | Root | `map` | Yes | Map of instance names to their connection details. |
| `url` | Instance | `string` | Yes | Full base URL to your Nextcloud instance. Do **not** include a trailing slash. |
| `username` | Instance | `string` | Yes | Your Nextcloud username. |
| `password` | Instance | `string` | Yes | Your Nextcloud password or app password. App passwords are highly recommended. |
| `verify` | Instance | `bool` | No | SSL certificate verification. Defaults to `true`. Only set to `false` if you have a self-signed/internal certificate and understand the security implications. |
| `color` | Instance | `string` | No | Theme color for decorations/output for this instance (e.g. `cyan`, `blue`, `magenta`, `green`, `yellow`; `theme_color` also accepted). |
| `boards` | Instance | `map` | Yes | Short names for boards/stacks used by `ncdeck` commands. |
| `board_id` | Board mapping | `int` | Yes | Numeric ID of the Deck board. |
| `stack_id` | Board mapping | `int` | Yes | Numeric ID of the default stack (list) to create cards in. |
| `done_stack_id` | Board mapping | `int` | No | Numeric ID of the stack to move cards to when using `ncdeck done`. Required if you want to use `done` without `--stack`. |

> **Note:** Prefixes are passed per-command with `-p/--prefix` rather than configured. Old `prefix:` entries in board mappings are ignored.

### Finding board, stack, and label IDs

If you don't know your IDs yet, use the `list` command:

```bash
# List all boards visible to the user with their IDs
ncdeck list --boards

# List all stacks and their IDs for a given board
ncdeck list --stacks 1

# List cached labels/tags for a configured board (discovers and saves once if missing)
ncdeck labels inbox
```

## Commands

### `ncdeck account add` (account wizard)

Interactive wizard to add a Nextcloud account using Nextcloud Login Flow v2. Opens a browser for authentication, auto-discovers boards, stacks, and labels (with colors), lets you assign short names to boards, select done stacks, and merges into your existing config.

```text
Usage: ncdeck account add [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `prompted` | Short name for this instance. |
| `--url TEXT` | `string` | `prompted` | Nextcloud server URL (e.g., `https://cloud.example.com`). |
| `--color TEXT` | `string` | `auto/prompted` | Theme color for this instance. If omitted, ncdeck tries to auto-detect it from the Nextcloud server theming (capabilities) and offers it as the default. |

The wizard will:
1. Start Login Flow v2 and open your browser for authentication
2. Wait for you to approve the login in Nextcloud
3. Auto-detect the server theme color (when available) and prompt for the instance color
4. Auto-discover all boards accessible to your account
5. For each board, discover its labels (with colors) and save them to config
6. For each board, ask for a short name (easy to remember)
7. Show available stacks and ask which one to use for creating cards
8. Ask which stack should be the "done" stack for `ncdeck done`
9. Ask if this should be the default instance
10. Save to your existing config (preserving other accounts)

### `ncdeck config color`

Set an instance’s theme color manually, or fetch it from the Nextcloud server theme.

```text
Usage: ncdeck config color [OPTIONS] INSTANCE_NAME [COLOR]
```

| Option/Arg | Description |
| --- | --- |
| `INSTANCE_NAME` | Configured instance name. |
| `COLOR` | Color value (named `cyan`/`bright_red`, hex `"#8b0000"` **quoted in shell**, or `139,0,0`). Omit when using `--theme`. |
| `--theme` | Fetch the color from the instance’s current Nextcloud theming (capabilities). Mutually exclusive with `COLOR`. |

### `ncdeck list`

Used to discover boards, stacks, and cached labels/tags.

```text
Usage: ncdeck list [OPTIONS]
```

| Option | Description |
| --- | --- |
| `-i, --instance TEXT` | Use a specific instance from config. Falls back to `default_instance`. |
| `--boards` | List all accessible Deck boards with `board_id`, title and owner. |
| `--stacks INTEGER` | List all stacks for the given `board_id` with `stack_id`, title and order. |
| `--labels BOARD_KEY` | List cached tags/labels for a configured board (IDs and colors). Discovers and saves them once if not yet in config. |

**Examples:**

```bash
# Show configured board mappings for default instance
ncdeck list

# List all boards
ncdeck list --boards -i work

# List stacks for board_id 1
ncdeck list --stacks 1 -i work

# List labels for the configured 'bugs' board (also available as `ncdeck labels bugs -i work`)
ncdeck list --labels bugs -i work
```

### `ncdeck labels`

List the labels cached in config for a board. Labels are discovered (with their colors) when a board is added via `ncdeck account add`, so creating cards with `-t/--tag` never needs a label lookup. Use `--refresh` after changing labels in the Deck web UI.

```text
Usage: ncdeck labels [OPTIONS] BOARD_KEY
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |
| `--refresh` | flag | `False` | Fetch labels from the server again and overwrite the cached ones in config. |

**Examples:**

```bash
# Show cached labels (discovers and saves them if the board was added before this feature)
ncdeck labels inbox

# Refresh after adding/renaming labels in the Deck web UI
ncdeck labels inbox --refresh -i mync
```

Example output:

```text
Labels: mync/inbox (3)
────────────────────────────────────────
  • [bug] (id=5, color=FF7A66)
  • [critical] (id=12, color=31CC7C)
  • [frontend] (id=14, color=317CCC)
```

For older configs that have no cached labels, the first `ncdeck labels` (or `list --labels`) call discovers them once and saves them to config.

### `ncdeck create`

Create a new card in a configured board/stack.

```text
Usage: ncdeck create [OPTIONS] BOARD_KEY TITLE
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config (e.g. `inbox`, `bugs`). |
| `TITLE` | Yes | The title of the card. The prefix (if provided) will be prepended to this. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-p, --prefix TEXT` | `string` | `""` | Prefix to prepend to the card title. Great for categorization (e.g. `[BUG]`, `[TODO]`, `[IDEA]`). |
| `-d, --description TEXT` | `string` | `""` | Card description in plain text or Markdown. |
| `-f, --description-file PATH` | `path` | `None` | Read the card description from a local Markdown/text file. The file contents are used as-is. |
| `--due-date TEXT` | `string` | `None` | Due date for the card in ISO 8601 format. Examples: `2026-10-31`, `2026-11-01T14:30:00`. |
| `-t, --tag TEXT` | `string` (multiple) | `[]` | Tag/label name to apply to the card. Can be used multiple times. Names are matched case-insensitively against labels on the target board. |
| `-a, --assign TEXT` | `string` (multiple) | `[]` | Assign card to user(s) by Nextcloud user ID. Can be used multiple times. |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use for this card. |

### `ncdeck description`

Set or amend a card's description.

```text
Usage: ncdeck description [OPTIONS] BOARD_KEY CARD_ID [TEXT]
```

By default the description is **replaced** with `TEXT`. With `--amend`, `TEXT` is appended to the end of the existing description.

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card. |
| `TEXT` | No | Description text. Use `-` to read from stdin (or pipe input when omitted). |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-f, --file PATH` | `path` | `None` | Read description text from a local file instead of `TEXT`. |
| `--amend` | flag | `False` | Append to the existing description instead of replacing it. |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |

**Examples:**

```bash
# Replace the description
ncdeck description inbox 123 "New description"

# Append to the existing description
ncdeck description inbox 123 --amend "Follow-up notes"

# Append the contents of a file
ncdeck description inbox 123 --amend -f notes.md

# Read from stdin
echo "Text from stdin" | ncdeck description inbox 123 --amend
```

### `ncdeck done`

Mark a card as done and move it to the default done stack for the board, or archive it.

```text
Usage: ncdeck done [OPTIONS] BOARD_KEY CARD_ID
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card to mark as done. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |
| `--stack INTEGER` | `int` | `None` | Override the done stack. If not provided, uses `done_stack_id` from the board config. |
| `--archive` | flag | `False` | Archive the card instead of moving it to a done stack. |

### `ncdeck move`

Move a card to a different stack on the same board.

```text
Usage: ncdeck move [OPTIONS] BOARD_KEY CARD_ID STACK_ID
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card to move. |
| `STACK_ID` | Yes | The numeric ID of the destination stack. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |

### `ncdeck assign`

Assign a card to a user or unassign it.

```text
Usage: ncdeck assign [OPTIONS] BOARD_KEY CARD_ID USER_ID
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card to assign. |
| `USER_ID` | Yes | The Nextcloud user ID to assign to (e.g., `alice`). |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |
| `--unassign` | flag | `False` | Unassign the card instead of assigning. |

**Examples:**

```bash
# Assign card to user
ncdeck assign inbox 123 alice

# Unassign card
ncdeck assign inbox 123 alice --unassign
```

### `ncdeck comment`

Add a comment to a card. Use `-` as `MESSAGE` to read the comment from stdin (useful for multi-line text).

```text
Usage: ncdeck comment [OPTIONS] BOARD_KEY CARD_ID MESSAGE
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card to comment on. |
| `MESSAGE` | Yes | Comment text (max 1000 chars). Use `-` to read from stdin. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |
| `--parent INTEGER` | `integer` | `None` | ID of the comment to reply to. |

**Examples:**

```bash
# Add a comment
ncdeck comment inbox 123 "Waiting for the vendor response"

# Reply to comment #7
ncdeck comment inbox 123 "Any update?" --parent 7

# Multi-line comment from stdin
ncdeck comment inbox 123 -
```

### `ncdeck list --cards`

List cards in a configured board with details.

```text
Usage: ncdeck list --cards BOARD_KEY [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--cards BOARD_KEY` | `string` | Required | The short key of the board mapping from your config. |
| `--stack INTEGER` | `int` | `None` | Stack ID to filter cards by. Shows all stacks if omitted. |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |

**Examples:**

```bash
# List all cards in a board
ncdeck list --cards inbox

# List cards in a specific stack
ncdeck list --cards inbox --stack 5
```

**Markdown task-list counters:** Cards whose descriptions contain Markdown task-list items are annotated with a `[done/total]` counter next to the card (green when every item is done). The same counter appears in `ncdeck agenda` and `ncdeck search`.

**Comment counter:** Cards with comments show `[💬 n]`. If a card has both a task list and comments, both counters are shown (for example `[1/3] [💬 2]`).

**Dependencies:** Cards that other cards depend on show `[🔗 #id, #id]` (from Deck's `dependentCards`). `ncdeck show` lists the dependent cards with their titles, stacks, and status.

**Labels:** Labels are shown as colored `[Label]` chips in `list --cards`, `search`, `agenda`, and `show`, using each Deck label's own color.

**Overdue and done status:** Open cards with a due date in the past show a red `[OVERDUE]` flag in `list --cards` and `search`, with the due date in red. Cards in the configured done stack show `[DONE]`. In `agenda`, overdue cards are prefixed with a red `OVERDUE` marker and the due line is red.

Supported task-list syntax:
- Bullets `- [ ]`, `* [ ]`, `+ [ ]`, or numbered items `1. [ ]`
- `[x]` / `[X]` counts as done; `[ ]` counts as open

### `ncdeck search`

Search for cards containing a keyword or string in title or description (case-insensitive).

```text
Usage: ncdeck search [OPTIONS] BOARD_KEY QUERY
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `QUERY` | Yes | Keyword or string to search for. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |
| `--stack INTEGER` | `int` | `None` | Limit search to specific stack ID. |
| `--include-archived` | flag | `False` | Include archived cards in search results. |

**Examples:**

```bash
# Search for cards containing "bug"
ncdeck search inbox bug

# Search in specific stack
ncdeck search bugs login --stack 9

# Include archived cards
ncdeck search inbox old --include-archived
```

### `ncdeck show`

Display full details of a specific card.

```text
Usage: ncdeck show [OPTIONS] BOARD_KEY CARD_ID
```

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `BOARD_KEY` | Yes | The short key of the board mapping from your config. |
| `CARD_ID` | Yes | The numeric ID of the card to display. |

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-i, --instance TEXT` | `string` | `default_instance` | Instance to use. |

**Example:**

```bash
ncdeck show inbox 123
```

**Output includes:** Card ID and title, board/instance, stack, status (active/done/overdue/archived), done timestamp (or an indication that the card is in the done stack without a timestamp), due date, labels, assignees, created/modified timestamps, dependent cards, full description, and the card's comments (author, timestamp, and message).

## Usage Examples

### Basic card creation

```bash
# Minimal card
ncdeck create inbox "Check server logs"

# With a prefix
ncdeck create inbox "Check server logs" -p "[OPS]"

# Target a different instance
ncdeck create ideas "Refactor API" -i personal -p "[IDEA]"
```

### Adding descriptions

```bash
# Inline description
ncdeck create bugs "Login fails on Safari" -p "[BUG]" -d "Occurs on version 18.0 when using passkeys."

# From a Markdown file
ncdeck create bugs "Crash on upload" -p "[BUG]" -f ./reports/crash-report.md

# From stdin
echo "# Reproduction\n1. Go to /upload\n2. Select large file\n3. Crash" | ncdeck create bugs "Crash on upload" -p "[BUG]"

# Combine inline + stdin
echo "Additional notes from logs" | ncdeck create bugs "Crash on upload" -p "[BUG]" -d "User reported this issue"
```

> **Description priority:** `-f/--description-file` takes highest priority. If reading from stdin and `-d` is also used, they are concatenated as `"<description>\n\n<stdin>"`. Otherwise stdin is used as-is.

### Adding due dates

```bash
# Date only
ncdeck create reviews "Review PR #42" -p "[REVIEW]" --due-date 2026-10-30

# Date and time
ncdeck create inbox "Submit expense report" -p "[FINANCE]" --due-date 2026-11-05T09:00:00
```

### Adding tags/labels by name

First, check the labels cached for your board (they are stored in config when the board is added):

```bash
ncdeck labels bugs -i work
```

Example output:

```text
Labels: work/bugs (4)
────────────────────────────────────────
  • [bug] (id=5, color=FF7A66)
  • [critical] (id=12, color=31CC7C)
  • [needs-repro] (id=8, color=F1DB50)
  • [frontend] (id=14, color=317CCC)
```

If labels were added or renamed in the Deck web UI, refresh the cache first:

```bash
ncdeck labels bugs -i work --refresh
```

Then use them by name:

```bash
# Single tag
ncdeck create bugs "CSS layout broken" -p "[BUG]" -t frontend

# Multiple tags
ncdeck create bugs "Auth bypass attempt" -p "[SECURITY]" -t bug -t critical
```

Tag matching is **case-insensitive**.

### Marking cards as done

```bash
# Mark as done - moves to configured done_stack_id
ncdeck done inbox 123

# Mark as done - override with specific stack
ncdeck done inbox 123 --stack 15

# Archive instead of moving
ncdeck done bugs 456 --archive

# From different instance
ncdeck done ideas 789 -i personal
```

### Moving cards

```bash
# Move card to a different stack
ncdeck move inbox 123 7

# Move card on different instance
ncdeck move bugs 456 12 -i work
```

### All options combined

```bash
ncdeck create bugs "Memory leak in worker" \
  -p "[BUG]" \
  -f ./debug/heap-trace.md \
  -t bug \
  -t backend \
  --due-date 2026-11-02T16:00:00 \
  -i work
```

## Tips & Notes

- **Use App Passwords**: Generate one at `Settings > Security > Devices & sessions > Create new app password`. Never commit your real password to version control.
- **Markdown is preserved**: Nextcloud Deck renders Markdown in card descriptions, so lists, code blocks, links, etc. will display correctly.
- **Labels are board-specific and cached**: The same label name can exist on different boards with different IDs. `ncdeck` resolves `-t/--tag` against the labels cached in config for that board (no API lookup on each create). Run `ncdeck labels BOARD_KEY --refresh` after changing labels in the Deck web UI.
- **Prefix is flexible**: Since prefix is a CLI flag, you can use different conventions per card without changing your config.
- **Piping is great for automation**: Combine with `git log`, `journalctl`, `curl`, scripts, or clipboard tools to quickly create cards.
- **Done workflow**: Configure `done_stack_id` for each board to streamline marking cards as complete. You can also use `--archive` if you prefer archiving.
- **Card IDs**: You can find card IDs from the Nextcloud Deck web UI (in the URL or by inspecting) or via API. They're required for `done` and `move` commands.
- **Self-signed certs**: If you must use `verify: false`, ensure you're on a trusted network.

## Troubleshooting

| Issue | Cause | Solution |
| --- | --- | --- |
| `No config found...` | Missing config file | Create `~/.config/ncdeck/config.yaml` using [config.example.yaml](config.example.yaml). |
| `Instance '...' not found in config` | Typo in `-i` or missing instance key | Check your config keys or set `default_instance`. |
| `Board mapping '...' not found...` | Unknown `BOARD_KEY` | Run `ncdeck list` to see valid board keys for your instance. |
| `HTTP error: 401 ...` | Wrong username/password or using main password with 2FA | Use an App Password from Nextcloud Security settings. |
| `HTTP error: 404 ...` | Wrong `url`, `board_id`, or `stack_id` | Verify IDs with `ncdeck list --boards` and `ncdeck list --stacks <board_id>`. Also ensure no trailing slash in `url`. |
| `HTTP error: 405 ...` on label discovery | API version difference | `ncdeck` tries multiple endpoints when discovering labels. Run `ncdeck labels <board_key> --refresh` to retry. |
| `Unknown tag(s): ...` | Label doesn't exist in the cached list for that board | Run `ncdeck labels <board_key>` to see exact names, or `--refresh` to pick up new labels. Matching is case-insensitive. |
| `No labels configured for this board` | Board was added before label caching, or has no labels | Run `ncdeck labels BOARD_KEY --refresh`. If the board truly has no labels, create one in the Deck web UI first. |
| Cached labels are stale after changes in the Deck web UI | Labels are read from config, not fetched on every create | Run `ncdeck labels BOARD_KEY --refresh` to re-fetch and save them. |
| `No done stack configured for board '...'` | Missing `done_stack_id` in config | Add `done_stack_id` to your board mapping in config, or use `--stack <id>`. |

## Example minimal end-to-end

```bash
# 1) Create config
mkdir -p ~/.config/ncdeck
cat > ~/.config/ncdeck/config.yaml << 'YAML'
default_instance: home
instances:
  home:
    url: https://cloud.example.com
    username: johndoe
    password: abcd-efgh-ijkl-mnop
    boards:
      inbox:
        board_id: 10
        stack_id: 42
        done_stack_id: 43
        labels:
          - id: 5
            title: reading
            color: FF7A66
YAML

# 2) Show cached labels (or refresh them)
ncdeck labels inbox
# ncdeck labels inbox --refresh

# 3) Create your first card
ncdeck create inbox "Read docs" -p "[LEARN]" -t reading --due-date 2026-10-31 -d "Go through Nextcloud Deck API notes"

# 4) Mark as done
ncdeck done inbox 123
```

**Files:**  
- Source: `src/ncdeck/cli.py`  
- Config: `~/.config/ncdeck/config.yaml`  
- Example Config: `config.example.yaml`  
- License: `LICENSE` (GPL-3.0-only)
