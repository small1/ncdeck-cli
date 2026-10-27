ncdeck - Nextcloud Deck CLI
ncdeck is a lightweight command-line tool to create cards in Nextcloud Deck directly from your terminal. It supports markdown descriptions, due dates, labels/tags by name, custom prefixes, reading from files, and piping from stdin.
Table of Contents
- Features
- Requirements
- Installation
- Configuration
- Commands
- Usage Examples
- Tips & Notes
- Troubleshooting
Features
- Multi-instance support - Manage multiple Nextcloud instances from a single config
- Board shortcuts - Use short board_key names instead of typing board/stack IDs every time
- Custom prefixes - Add any prefix to card titles on-the-fly with -p/--prefix
- Markdown descriptions - Pass descriptions directly, from a file (-f), or via piped stdin
- Due dates - Set due dates in ISO format
- Tags/labels by name - Use human-readable label names with -t/--tag instead of numeric IDs
- Label discovery - List all available labels for a board with ncdeck list --labels
- API version compatible - Tries multiple endpoints to fetch labels across different Nextcloud Deck versions
Requirements
- Python 3.9+
- Nextcloud with the Deck app installed and enabled
- A Nextcloud account with access to the target boards
- An App Password (strongly recommended, especially if 2FA is enabled)
Python dependencies
- click
- requests
- PyYAML
Installation
1. Install dependencies
pip install click requests pyyaml
2. Download the script
Save the ncdeck script to a directory in your $PATH. A common choice is ~/.local/bin/.
mkdir -p ~/.local/bin
# Put the ncdeck script here
chmod +x ~/.local/bin/ncdeck
Make sure ~/.local/bin is in your $PATH. You can check with echo $PATH and add it to your shell rc if needed:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
3. Create your config file
See the Configuration section below.
4. Verify
ncdeck --help
Configuration
ncdeck looks for a config file in the following order:
1. $XDG_CONFIG_HOME/ncdeck/config.yaml (defaults to ~/.config/ncdeck/config.yaml)
2. ~/.ncdeck.yaml
Creating the config
mkdir -p ~/.config/ncdeck
nano ~/.config/ncdeck/config.yaml
Config structure
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
      bugs:
        board_id: 2
        stack_id: 9
      reviews:
        board_id: 3
        stack_id: 12

  personal:
    url: https://cloud.personal.example
    username: bob
    password: yyyy-yyyy-yyyy-yyyy
    boards:
      ideas:
        board_id: 4
        stack_id: 7
      todo:
        board_id: 5
        stack_id: 11
Config options explained
Option	Scope	Type	Required	Description
default_instance	Root	string	No	The instance key to use when -i/--instance is omitted.
instances	Root	map	Yes	Map of instance names to their connection details.
url	Instance	string	Yes	Full base URL to your Nextcloud instance. Do not include a trailing slash.
username	Instance	string	Yes	Your Nextcloud username.
password	Instance	string	Yes	Your Nextcloud password or app password. App passwords are highly recommended.
verify	Instance	bool	No	SSL certificate verification. Defaults to true. Only set to false if you have a self-signed/internal certificate and understand the security implications.
boards	Instance	map	Yes	Short names for boards/stacks used by ncdeck create.
board_id	Board mapping	int	Yes	Numeric ID of the Deck board.
stack_id	Board mapping	int	Yes	Numeric ID of the stack (list) to create cards in.
Note: Prefixes are no longer configured here. They are passed per-command with -p/--prefix.
Finding board and stack IDs
If you don't know your board_id or stack_id yet, use the list command:
# List all boards visible to the user with their IDs
ncdeck list --boards

# List all stacks and their IDs for a given board
ncdeck list --stacks 1
Commands
ncdeck list
Used to discover boards, stacks, and labels/tags.
Usage: ncdeck list [OPTIONS]
Option	Description
-i, --instance TEXT	Use a specific instance from config. Falls back to default_instance.
--boards	List all accessible Deck boards with board_id, title and owner.
--stacks INTEGER	List all stacks for the given board_id with stack_id, title and order.
--labels BOARD_KEY	List all available tags/labels for a configured board, including their IDs. Case-insensitive matching is used when applying them.
Examples:
# Show configured board mappings for default instance
ncdeck list

# List all boards
ncdeck list --boards -i work

# List stacks for board_id 1
ncdeck list --stacks 1 -i work

# List labels for the configured 'bugs' board
ncdeck list --labels bugs -i work
ncdeck create
Create a new card in a configured board/stack.
Usage: ncdeck create [OPTIONS] BOARD_KEY TITLE
Arguments
Argument	Required	Description
BOARD_KEY	Yes	The short key of the board mapping from your config (e.g. inbox, bugs).
TITLE	Yes	The title of the card. The prefix (if provided) will be prepended to this.
Options
Option	Type	Default	Description
-p, --prefix TEXT	string	""	Prefix to prepend to the card title. Great for categorization (e.g. [BUG], [TODO], [IDEA]).
-d, --description TEXT	string	""	Card description in plain text or Markdown.
-f, --description-file PATH	path	None	Read the card description from a local Markdown/text file. The file contents are used as-is.
--due-date TEXT	string	None	Due date for the card in ISO 8601 format. Examples: 2026-10-31, 2026-11-01T14:30:00.
-t, --tag TEXT	string (multiple)	[]	Tag/label name to apply to the card. Can be used multiple times. Names are matched case-insensitively against labels on the target board.
-i, --instance TEXT	string	default_instance	Instance to use for this card.
Usage Examples
Basic card creation
# Minimal card
ncdeck create inbox "Check server logs"

# With a prefix
ncdeck create inbox "Check server logs" -p "[OPS]"

# Target a different instance
ncdeck create ideas "Refactor API" -i personal -p "[IDEA]"
Adding descriptions
# Inline description
ncdeck create bugs "Login fails on Safari" -p "[BUG]" -d "Occurs on version 18.0 when using passkeys."

# From a Markdown file
ncdeck create bugs "Crash on upload" -p "[BUG]" -f ./reports/crash-report.md

# From stdin
echo "# Reproduction\n1. Go to /upload\n2. Select large file\n3. Crash" | ncdeck create bugs "Crash on upload" -p "[BUG]"

# Combine inline + stdin (inline comes first, followed by a blank line, then stdin)
echo "Additional notes from logs" | ncdeck create bugs "Crash on upload" -p "[BUG]" -d "User reported this issue"
Description priority: -f/--description-file takes highest priority. If reading from stdin and -d is also used, they are concatenated as "<description>\n\n<stdin>". Otherwise stdin is used as-is.
Adding due dates
# Date only
ncdeck create reviews "Review PR #42" -p "[REVIEW]" --due-date 2026-10-30

# Date and time
ncdeck create inbox "Submit expense report" -p "[FINANCE]" --due-date 2026-11-05T09:00:00
Adding tags/labels by name
First, discover available labels for your board:
ncdeck list --labels bugs -i work
Example output:
Tags/labels for work/bugs (board_id=2):
  - bug (id=5)
  - critical (id=12)
  - needs-repro (id=8)
  - frontend (id=14)
Then use them by name:
# Single tag
ncdeck create bugs "CSS layout broken" -p "[BUG]" -t frontend

# Multiple tags
ncdeck create bugs "Auth bypass attempt" -p "[SECURITY]" -t bug -t critical

# Tags with description, due date and prefix
cat ./security-notes.md | ncdeck create bugs "Auth bypass attempt" -p "[SECURITY]" -t bug -t critical --due-date 2026-10-29T12:00:00
Tag matching is case-insensitive, so -t Bug, -t BUG, and -t bug all work the same.
All options combined
ncdeck create bugs "Memory leak in worker" \
  -p "[BUG]" \
  -f ./debug/heap-trace.md \
  -t bug \
  -t backend \
  --due-date 2026-11-02T16:00:00 \
  -i work
Tips & Notes
- Use App Passwords: Generate one at Settings > Security > Devices & sessions > Create new app password. Never commit your real password to version control.
- Markdown is preserved: Nextcloud Deck renders Markdown in card descriptions, so lists, code blocks, links, etc. will display correctly.
- Labels are board-specific: The same label name can exist on different boards with different IDs. ncdeck always resolves labels against the target board of the card you're creating.
- Prefix is flexible: Since prefix is a CLI flag, you can use different conventions per card without changing your config.
- Piping is great for automation: Combine with git log, journalctl, curl, scripts, or clipboard tools to quickly create cards.
- Config minimalism: Only board_id and stack_id are needed per board mapping now. Any old prefix: entries in your config are safely ignored.
- Self-signed certs: If you must use verify: false, ensure you're on a trusted network.
Troubleshooting
Issue	Cause	Solution
No config found...	Missing config file	Create ~/.config/ncdeck/config.yaml as shown above.
Instance '...' not found in config	Typo in -i or missing instance key	Check your config keys or set default_instance.
Board mapping '...' not found...	Unknown BOARD_KEY	Run ncdeck list to see valid board keys for your instance.
HTTP error: 401 ...	Wrong username/password or using main password with 2FA	Use an App Password from Nextcloud Security settings.
HTTP error: 404 ...	Wrong url, board_id, or stack_id	Verify IDs with ncdeck list --boards and ncdeck list --stacks <board_id>. Also ensure no trailing slash in url.
HTTP error: 405 ... on labels	API version difference	The updated script already handles this by fetching labels from board details first. If it still fails, run ncdeck list --labels <board_key> to see the debug output.
Unknown tag(s): ...	Label doesn't exist on that board	Run ncdeck list --labels <board_key> to see exact names. Remember matching is case-insensitive.
No labels/tags found on this board	Board has no labels created yet	Create at least one label in the Nextcloud Deck web UI first, then try again.
Could not fetch labels for this board	Permissions/network issue	Check your app password has access to that board and your instance is reachable.
Example minimal end-to-end
# 1) Create config
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
YAML

# 2) Discover labels
ncdeck list --labels inbox

# 3) Create your first card
ncdeck create inbox "Read docs" -p "[LEARN]" -t reading --due-date 2026-10-31 -d "Go through Nextcloud Deck API notes"
File: ~/.local/bin/ncdeck  
Config: ~/.config/ncdeck/config.yaml
