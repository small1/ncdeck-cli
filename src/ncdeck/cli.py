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

    def list_boards(self):
        return self._get("/index.php/apps/deck/api/v1.0/boards")

    def get_board(self, board_id):
        return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}")

    def list_stacks(self, board_id):
        return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks")

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
def list_cmd(instance, boards, stacks, labels_board):
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
        click.echo(f"  - {k}: board_id={v['board_id']} stack_id={v['stack_id']}")


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


if __name__ == "__main__":
    cli()
