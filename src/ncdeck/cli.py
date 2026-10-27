#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from typing import Optional, List

import click
import requests
import yaml
from requests.auth import HTTPBasicAuth

CONFIG_PATHS = [
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ncdeck" / "config.yaml",
    Path.home() / ".ncdeck.yaml",
]


class DeckClient:
    def __init__(self, instance_cfg):
        self.url = instance_cfg["url"].rstrip("/")
        self.auth = HTTPBasicAuth(instance_cfg["username"], instance_cfg["password"])
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        # self.session.verify = instance_cfg.get("verify", True)

    def _get(self, path):
        r = self.session.get(f"{self.url}{path}")
        r.raise_for_status()
        return r.json()

    def _post(self, path, data):
        r = self.session.post(f"{self.url}{path}", data=json.dumps(data))
        r.raise_for_status()
        return r.json()

    def _put(self, path, data):
        r = self.session.put(f"{self.url}{path}", data=json.dumps(data))
        r.raise_for_status()
        return r.json()

    def _delete(self, path):
        r = self.session.delete(f"{self.url}{path}")
        r.raise_for_status()
        return r.json()

    def list_boards(self):
        return self._get("/index.php/apps/deck/api/v1.0/boards")

    def get_board(self, board_id):
        return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}")

    def list_stacks(self, board_id):
        return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks")

    def get_stack(self, board_id, stack_id):
        stacks = self.list_stacks(board_id)
        for stack in stacks:
            if stack.get('id') == int(stack_id):
                return stack
        return None

    def list_cards(self, board_id, stack_id=None):
        # Get all stacks with their cards
        try:
            stacks = self.list_stacks(board_id)
            cards = []
            for stack in stacks:
                if stack_id is not None and stack.get('id') != int(stack_id):
                    continue
                stack_cards = stack.get('cards', []) or []
                for card in stack_cards:
                    card['_stack_title'] = stack.get('title')
                    card['_stack_id'] = stack.get('id')
                cards.extend(stack_cards)
            if cards:
                return cards
        except Exception:
            pass
        
        # Fallback: try board details
        try:
            board = self.get_board(board_id)
            if board and board.get('stacks'):
                cards = []
                for stack in board['stacks']:
                    if stack_id is None or stack.get('id') == int(stack_id):
                        stack_cards = stack.get('cards', []) or []
                        for card in stack_cards:
                            card['_stack_title'] = stack.get('title')
                            card['_stack_id'] = stack.get('id')
                        cards.extend(stack_cards)
                return cards
        except Exception:
            pass
        
        if stack_id is not None:
            try:
                stack = self.get_stack(board_id, stack_id)
                if stack and stack.get('cards'):
                    for card in stack['cards']:
                        card['_stack_title'] = stack.get('title')
                        card['_stack_id'] = stack.get('id')
                    return stack['cards']
            except Exception:
                pass
        
        return []

    def get_card(self, board_id, card_id):
        return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/-1/cards/{card_id}")

    def update_card(self, board_id, card_id, stack_id=None, title=None, description=None, duedate=None, archived=None):
        # Get current card data first
        card = self.get_card(board_id, card_id)
        payload = card
        
        if stack_id is not None:
            payload["stackId"] = int(stack_id)
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if duedate is not None:
            payload["duedate"] = duedate
        if archived is not None:
            payload["archived"] = bool(archived)
        
        return self._put(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}",
            payload,
        )

    def move_card(self, board_id, card_id, stack_id):
        card = self.get_card(board_id, card_id)
        payload = card
        payload["stackId"] = int(stack_id)
        return self._put(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}",
            payload,
        )

    def archive_card(self, board_id, card_id, archived=True):
        card = self.get_card(board_id, card_id)
        payload = card
        payload["archived"] = bool(archived)
        return self._put(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}",
            payload,
        )

    def list_labels(self, board_id):
        # Try different API endpoints for compatibility
        try:
            # Try board details first (labels often included here)
            board = self.get_board(board_id)
            if isinstance(board, dict) and board.get('labels'):
                return board['labels']
        except Exception:
            pass
        
        try:
            # Try dedicated labels endpoint
            return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/labels")
        except requests.HTTPError as e:
            if e.response.status_code == 405:
                # Try alternative endpoint
                try:
                    return self._get(f"/index.php/apps/deck/api/v1.1/boards/{board_id}/labels")
                except Exception:
                    pass
            raise
        
        return []

    def create_card(self, board_id, stack_id, title, description="", duedate=None, labels=None):
        payload = {
            "title": title,
            "description": description,
            "type": "plain",
            "order": 999,
        }

        if duedate:
            payload["duedate"] = duedate

        if labels:
            payload["labels"] = [{"id": int(label_id)} for label_id in labels]

        return self._post(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards",
            payload,
        )


def load_config():
    for p in CONFIG_PATHS:
        if p.exists():
            with p.open() as f:
                return yaml.safe_load(f)
    raise click.ClickException(
        f"No config found. Create one at {CONFIG_PATHS[0]} (see docs)."
    )


def get_mapping(cfg, instance_name: Optional[str], board_key: str):
    inst_name = instance_name or cfg.get("default_instance")
    if not inst_name:
        raise click.ClickException("No instance specified and no default_instance in config")

    try:
        inst = cfg["instances"][inst_name]
    except KeyError:
        raise click.ClickException(f"Instance '{inst_name}' not found in config")

    try:
        board = inst["boards"][board_key]
    except KeyError:
        raise click.ClickException(
            f"Board mapping '{board_key}' not found for instance '{inst_name}'"
        )

    return inst_name, inst, board


def read_description(description: str, description_file: Optional[Path]) -> str:
    if description_file:
        try:
            with description_file.open("r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise click.ClickException(f"Failed to read description file: {e}")

    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read()
            if description:
                return f"{description}\n\n{stdin_data}"
            return stdin_data
        except Exception as e:
            raise click.ClickException(f"Failed to read from stdin: {e}")

    return description


def resolve_label_ids(client: DeckClient, board_id: int, tag_names: List[str]) -> List[int]:
    if not tag_names:
        return []

    try:
        labels = client.list_labels(board_id)
    except Exception as e:
        raise click.ClickException(
            f"Could not fetch labels for this board: {e}\n"
            f"Try running `ncdeck list --labels <board_key>` to debug."
        )
    
    label_map = {}
    for label in labels:
        name = label.get("title") or label.get("name") or ""
        if name:
            label_map[name.strip().lower()] = label["id"]

    if not label_map:
        raise click.ClickException(
            "No labels/tags found on this board. "
            "You may need to create them in the Nextcloud Deck UI first, "
            "or your API version doesn't expose them via this method."
        )

    resolved = []
    missing = []

    for tag in tag_names:
        key = tag.strip().lower()
        if key in label_map:
            resolved.append(label_map[key])
        else:
            missing.append(tag)

    if missing:
        raise click.ClickException(
            f"Unknown tag(s): {', '.join(missing)}. "
            f"Run `ncdeck list --labels <board_key> -i <instance>` to see available tags."
        )

    return resolved


@click.group()
def cli():
    """Create Nextcloud Deck cards from the CLI."""
    pass


@cli.command("list")
@click.option("-i", "--instance", help="Instance name from config")
@click.option("--boards", is_flag=True, help="List boards and their IDs")
@click.option("--stacks", type=int, help="List stacks for a given board_id")
@click.option("--labels", "labels_board", metavar="BOARD_KEY", help="List available tags/labels for a configured board")
@click.option("--cards", "cards_board", metavar="BOARD_KEY", help="List cards in a configured board (all stacks or specify with --stack)")
@click.option("--stack", type=int, help="Stack ID to list cards from (used with --cards)")
def list_cmd(instance, boards, stacks, labels_board, cards_board, stack):
    """Discover boards/stacks/IDs and tags."""
    cfg = load_config()
    inst_name = instance or cfg.get("default_instance")

    if not inst_name:
        raise click.ClickException("No instance specified and no default_instance in config")

    inst = cfg.get("instances", {}).get(inst_name)
    if not inst:
        raise click.ClickException(f"Instance '{inst_name}' not found in config")

    client = DeckClient(inst)

    if boards:
        for b in client.list_boards():
            owner = b.get("owner", {}) or {}
            click.echo(f"board_id={b['id']} title={b['title']} owner={owner.get('uid')}")
        return

    if stacks is not None:
        for s in client.list_stacks(stacks):
            click.echo(f"stack_id={s['id']} title={s['title']} order={s.get('order')}")
        return

    if cards_board:
        inst_name_res, inst_res, board = get_mapping(cfg, instance, cards_board)
        try:
            cards = client.list_cards(board["board_id"], stack_id=stack)
            if stack:
                click.echo(f"Cards in stack {stack} for {inst_name_res}/{cards_board}:")
            else:
                click.echo(f"Cards for {inst_name_res}/{cards_board}:")
            if not cards:
                click.echo("  (no cards found)")
                return
            for card in cards:
                card_id = card.get('id')
                title = card.get('title', '(untitled)')
                stack_title = card.get('_stack_title') or card.get('stackTitle') or ''
                archived = card.get('archived', False)
                archived_str = " [ARCHIVED]" if archived else ""
                duedate = card.get('duedate')
                assigned = card.get('assignedUsers') or card.get('assignedusers') or []
                assignee_str = ""
                if assigned:
                    names = []
                    for a in assigned:
                        if isinstance(a, dict):
                            name = a.get('participant', {}).get('displayname') or a.get('displayname') or a.get('uid')
                            if name:
                                names.append(name)
                    if names:
                        assignee_str = f" @{','.join(names)}"
                if stack_title:
                    click.echo(f"  #{card_id} [{stack_title}]{archived_str} {title}{assignee_str}")
                else:
                    click.echo(f"  #{card_id}{archived_str} {title}{assignee_str}")
                if duedate:
                    click.echo(f"    Due: {duedate}")
        except Exception as e:
            click.echo(f"Error fetching cards: {e}", err=True)
        return

    if labels_board:
        inst_name_res, inst_res, board = get_mapping(cfg, instance, labels_board)
        try:
            labels = client.list_labels(board["board_id"])
            click.echo(f"Tags/labels for {inst_name_res}/{labels_board} (board_id={board['board_id']}):")
            if not labels:
                click.echo("  (no labels found)")
                return
            for label in labels:
                title = label.get("title") or label.get("name") or "(unnamed)"
                click.echo(f"  - {title} (id={label['id']})")
        except Exception as e:
            click.echo(f"Error fetching labels: {e}", err=True)
            click.echo("\nTrying to get board details directly...", err=True)
            try:
                board_details = client.get_board(board["board_id"])
                if board_details.get('labels'):
                    click.echo(f"Tags/labels for {inst_name_res}/{labels_board} (from board details):")
                    for label in board_details['labels']:
                        title = label.get("title") or label.get("name") or "(unnamed)"
                        click.echo(f"  - {title} (id={label['id']})")
                else:
                    click.echo("  No labels found in board details.", err=True)
            except Exception as e2:
                click.echo(f"Also failed: {e2}", err=True)
        return

    click.echo(f"Instance: {inst_name} ({inst['url']})")
    for k, v in inst.get("boards", {}).items():
        done_info = ""
        if v.get("done_stack_id"):
            done_info = f" done_stack_id={v['done_stack_id']}"
        click.echo(f"  - {k}: board_id={v['board_id']} stack_id={v['stack_id']}{done_info}")


@cli.command("create")
@click.argument("board_key")
@click.argument("title")
@click.option("-d", "--description", default="", help="Card description (plain text or markdown)")
@click.option("-f", "--description-file", type=click.Path(exists=True, path_type=Path), help="Read description from a markdown/text file")
@click.option("-p", "--prefix", default="", help="Prefix to add to the card title (e.g. '[BUG]')")
@click.option("--due-date", help="Due date in ISO format (e.g., 2026-10-28 or 2026-10-28T15:30:00)")
@click.option("-t", "--tag", multiple=True, help="Tag/label name to add to the card (can be used multiple times)")
@click.option("-i", "--instance", help="Instance name from config")
def create_cmd(board_key, title, description, description_file, prefix, due_date, tag, instance):
    """Create a card. Example: ncdeck create inbox 'Fix login bug' -p '[BUG]' -t bug"""
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)

    card_title = f"{prefix}{title}" if prefix else title
    card_description = read_description(description, description_file)
    label_ids = resolve_label_ids(client, board["board_id"], list(tag)) if tag else []

    try:
        card = client.create_card(
            board["board_id"],
            board["stack_id"],
            card_title,
            card_description,
            duedate=due_date,
            labels=label_ids if label_ids else None,
        )
        click.echo(f"Created card #{card['id']} '{card['title']}' in {inst_name}/{board_key}")
        if due_date:
            click.echo(f"  Due: {due_date}")
        if tag:
            click.echo(f"  Tags: {', '.join(tag)}")
    except requests.HTTPError as e:
        click.echo(f"HTTP error: {e} - {e.response.text}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("done")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.option("-i", "--instance", help="Instance name from config")
@click.option("--stack", type=int, help="Override done stack (default from config)")
@click.option("--archive", is_flag=True, help="Archive the card instead of moving to done stack")
def done_cmd(board_key, card_id, instance, stack, archive):
    """Mark a card as done and move to default done stack. Example: ncdeck done inbox 123"""
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)

    try:
        if archive:
            result = client.archive_card(board["board_id"], card_id, archived=True)
            click.echo(f"Archived card #{card_id} in {inst_name}/{board_key}")
            return

        done_stack_id = stack if stack is not None else board.get("done_stack_id")
        if done_stack_id is None:
            raise click.ClickException(
                f"No done stack configured for board '{board_key}'. "
                f"Add 'done_stack_id' to the board mapping in config, or use --stack."
            )

        result = client.move_card(board["board_id"], card_id, done_stack_id)
        click.echo(f"Marked card #{card_id} as done and moved to done stack in {inst_name}/{board_key}")
    except requests.HTTPError as e:
        click.echo(f"HTTP error: {e} - {e.response.text}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("move")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.argument("stack_id", type=int)
@click.option("-i", "--instance", help="Instance name from config")
def move_cmd(board_key, card_id, stack_id, instance):
    """Move a card to a different stack. Example: ncdeck move inbox 123 7"""
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)

    try:
        result = client.move_card(board["board_id"], card_id, stack_id)
        click.echo(f"Moved card #{card_id} to stack {stack_id} in {inst_name}/{board_key}")
    except requests.HTTPError as e:
        click.echo(f"HTTP error: {e} - {e.response.text}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("search")
@click.argument("board_key")
@click.argument("query")
@click.option("-i", "--instance", help="Instance name from config")
@click.option("--stack", type=int, help="Limit search to specific stack ID")
@click.option("--include-archived", is_flag=True, help="Include archived cards in search")
def search_cmd(board_key, query, instance, stack, include_archived):
    """Search for cards containing a keyword or string. Example: ncdeck search inbox bug"""
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)

    try:
        cards = client.list_cards(board["board_id"], stack_id=stack)
        query_lower = query.lower()
        results = []
        for card in cards:
            if not include_archived and card.get('archived'):
                continue
            title = card.get('title', '') or ''
            description = card.get('description', '') or ''
            if query_lower in title.lower() or query_lower in description.lower():
                results.append(card)

        if not results:
            click.echo(f"No cards found matching '{query}' in {inst_name}/{board_key}")
            return

        click.echo(f"Found {len(results)} card(s) matching '{query}' in {inst_name}/{board_key}:")
        for card in results:
            card_id = card.get('id')
            title = card.get('title', '(untitled)')
            stack_title = card.get('_stack_title') or card.get('stackTitle') or ''
            archived = card.get('archived', False)
            archived_str = " [ARCHIVED]" if archived else ""
            duedate = card.get('duedate')
            assigned = card.get('assignedUsers') or card.get('assignedusers') or []
            assignee_str = ""
            if assigned:
                names = []
                for a in assigned:
                    if isinstance(a, dict):
                        name = a.get('participant', {}).get('displayname') or a.get('displayname') or a.get('uid')
                        if name:
                            names.append(name)
                if names:
                    assignee_str = f" @{','.join(names)}"
            if stack_title:
                click.echo(f"  #{card_id} [{stack_title}]{archived_str} {title}{assignee_str}")
            else:
                click.echo(f"  #{card_id}{archived_str} {title}{assignee_str}")
            if duedate:
                click.echo(f"    Due: {duedate}")
            if assigned:
                names = []
                for a in assigned:
                    if isinstance(a, dict):
                        name = a.get('participant', {}).get('displayname') or a.get('displayname') or a.get('uid')
                        if name:
                            names.append(name)
                if names and not assignee_str:
                    click.echo(f"    Assignee: {', '.join(names)}")
    except requests.HTTPError as e:
        click.echo(f"HTTP error: {e} - {e.response.text}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
