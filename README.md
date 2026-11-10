# ncdeck

A lightweight CLI tool to create cards in [Nextcloud Deck](https://apps.nextcloud.com/apps/deck) from your terminal.

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

Create `~/.config/ncdeck/config.yaml`:

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
      bugs:
        board_id: 2
        stack_id: 9
```

### Usage

```bash
# Discover boards and tags
ncdeck list --boards
ncdeck labels bugs

# Create a card
ncdeck create inbox "Fix login bug" -p "[BUG]" -t bug --due-date 2026-10-31
```

See [README_FULL.md](README_FULL.md) for complete documentation.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
