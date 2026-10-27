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
- **Label discovery** - List all available labels for a board with `ncdeck list --labels`
- **Mark as done** - Mark cards as done and automatically move them to a configured done stack
- **Move cards** - Move cards between any stacks on a board
- **Archive cards** - Optionally archive cards instead of moving to done stack
- **API version compatible** - Tries multiple endpoints to fetch labels across different Nextcloud Deck versions

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

# List all labels/tags for a configured board
ncdeck list --labels inbox
```

## Commands

### `ncdeck list`

Used to discover boards, stacks, and labels/tags.

```text
Usage: ncdeck list [OPTIONS]
```

| Option | Description |
| --- | --- |
| `-i, --instance TEXT` | Use a specific instance from config. Falls back to `default_instance`. |
| `--boards` | List all accessible Deck boards with `board_id`, title and owner. |
| `--stacks INTEGER` | List all stacks for the given `board_id` with `stack_id`, title and order. |
| `--labels BOARD_KEY` | List all available tags/labels for a configured board, including their IDs. Case-insensitive matching is used when applying them. |

**Examples:**

```bash
# Show configured board mappings for default instance
ncdeck list

# List all boards
ncdeck list --boards -i work

# List stacks for board_id 1
ncdeck list --stacks 1 -i work

# List labels for the configured 'bugs' board
ncdeck list --labels bugs -i work
```

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

**Output includes:** Card ID and title, board/instance, stack, status (active/archived), due date, labels, assignees, created/modified timestamps, and full description.

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

First, discover available labels for your board:

```bash
ncdeck list --labels bugs -i work
```

Example output:

```text
Tags/labels for work/bugs (board_id=2):
  - bug (id=5)
  - critical (id=12)
  - needs-repro (id=8)
  - frontend (id=14)
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
- **Labels are board-specific**: The same label name can exist on different boards with different IDs. `ncdeck` always resolves labels against the target board of the card you're creating.
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
| `HTTP error: 405 ...` on labels | API version difference | The updated script already handles this by fetching labels from board details first. If it still fails, run `ncdeck list --labels <board_key>` to see the debug output. |
| `Unknown tag(s): ...` | Label doesn't exist on that board | Run `ncdeck list --labels <board_key>` to see exact names. Remember matching is case-insensitive. |
| `No labels/tags found on this board` | Board has no labels created yet | Create at least one label in the Nextcloud Deck web UI first, then try again. |
| `Could not fetch labels for this board` | Permissions/network issue | Check your app password has access to that board and your instance is reachable. |
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
YAML

# 2) Discover labels
ncdeck list --labels inbox

# 3) Create your first card
ncdeck create inbox "Read docs" -p "[LEARN]" -t reading --due-date 2026-10-31 -d "Go through Nextcloud Deck API notes"

# 4) Mark as done
ncdeck done inbox 123
```

**Files:**  
- Source: `src/ncdeck/cli.py`  
- Config: `~/.config/ncdeck/config.yaml`  
- Example Config: `config.example.yaml`
