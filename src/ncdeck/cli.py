#!/usr/bin/env python3
import os
import sys
import json
import time
import webbrowser
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


def get_config_path():
    for p in CONFIG_PATHS:
        if p.exists():
            return p
    p = CONFIG_PATHS[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class DeckClient:
    def __init__(self, instance_cfg):
        self.url = instance_cfg["url"].rstrip("/")
        self.auth = HTTPBasicAuth(instance_cfg["username"], instance_cfg["password"])
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

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

    def get_card_full(self, board_id, card_id):
        try:
            card = self.get_card(board_id, card_id)
            return card
        except Exception:
            cards = self.list_cards(board_id)
            for c in cards:
                if c.get('id') == int(card_id):
                    return c
            raise

    def update_card(self, board_id, card_id, stack_id=None, title=None, description=None, duedate=None, archived=None):
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

    def assign_card(self, board_id, card_id, user_id):
        card = self.get_card(board_id, card_id)
        payload = card
        payload["assignedUsers"] = [{"participant": {"primaryKey": user_id}}]
        return self._put(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}",
            payload,
        )

    def unassign_card(self, board_id, card_id):
        card = self.get_card(board_id, card_id)
        payload = card
        payload["assignedUsers"] = []
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
        try:
            board = self.get_board(board_id)
            if isinstance(board, dict) and board.get('labels'):
                return board['labels']
        except Exception:
            pass
        try:
            return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/labels")
        except requests.HTTPError as e:
            if e.response.status_code == 405:
                try:
                    return self._get(f"/index.php/apps/deck/api/v1.1/boards/{board_id}/labels")
                except Exception:
                    pass
            raise
        return []

    def create_card(self, board_id, stack_id, title, description="", duedate=None, labels=None, assigned_users=None):
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
        if assigned_users:
            payload["assignedUsers"] = [{"participant": {"primaryKey": uid}} for uid in assigned_users]
        return self._post(
            f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards",
            payload,
        )


def load_config():
    for p in CONFIG_PATHS:
        if p.exists():
            with p.open() as f:
                return yaml.safe_load(f) or {}
    return {}


def save_config(cfg):
    p = get_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w') as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


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
        raise click.ClickException(f"Board mapping '{board_key}' not found for instance '{inst_name}'")
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
        raise click.ClickException(f"Could not fetch labels for this board: {e}")
    label_map = {}
    for label in labels:
        name = label.get("title") or label.get("name") or ""
        if name:
            label_map[name.strip().lower()] = label["id"]
    if not label_map:
        raise click.ClickException("No labels/tags found on this board.")
    resolved = []
    missing = []
    for tag in tag_names:
        key = tag.strip().lower()
        if key in label_map:
            resolved.append(label_map[key])
        else:
            missing.append(tag)
    if missing:
        raise click.ClickException(f"Unknown tag(s): {', '.join(missing)}. Run `ncdeck list --labels <board_key>` to see available tags.")
    return resolved


@click.group()
def cli():
    """Create Nextcloud Deck cards from the CLI."""
    pass


@cli.command("add-account")
@click.option("-i", "--instance", "instance_name", help="Short name for this instance")
@click.option("--url", help="Nextcloud server URL")
def add_account_cmd(instance_name, url):
    """Add a Nextcloud account via Login Flow v2 with board autodiscovery."""
    cfg = load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    if 'instances' not in cfg or not isinstance(cfg['instances'], dict):
        cfg['instances'] = {}

    if not url:
        url = click.prompt("Nextcloud server URL (e.g. https://cloud.example.com)")
    url = url.rstrip('/')

    click.echo(f"\nStarting Nextcloud Login Flow v2 for {url}...")
    try:
        resp = requests.post(f"{url}/index.php/login/v2", headers={"User-Agent": "ncdeck-cli"}, timeout=30)
        resp.raise_for_status()
        flow = resp.json()
        login_url = flow['login']
        poll = flow['poll']
        endpoint = poll['endpoint']
        token = poll['token']
    except Exception as e:
        raise click.ClickException(f"Failed to initiate login flow: {e}")

    click.echo(f"\nOpening browser to authenticate...")
    click.echo(f"If browser doesn't open, visit: {login_url}")
    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    click.echo("\nWaiting for authentication (press Ctrl+C to cancel)...")
    creds = None
    for _ in range(120):
        try:
            r = requests.post(endpoint, data={"token": token}, timeout=30)
            if r.status_code == 200:
                creds = r.json()
                break
            time.sleep(2)
        except Exception:
            time.sleep(2)
            continue

    if not creds:
        raise click.ClickException("Authentication timed out or failed")

    server = creds.get('server', url)
    login_name = creds.get('loginName') or creds.get('user')
    app_password = creds.get('appPassword')

    click.echo(f"\nAuthenticated as {login_name} on {server}")

    if not instance_name:
        if instance_name and instance_name in cfg['instances']:
            instance_name = click.prompt("Short name for this instance (already exists)", default=f"{login_name}_new")
        else:
            default_name = login_name if login_name and login_name not in cfg['instances'] else f"nc_{login_name}"
            instance_name = click.prompt("Short name for this instance", default=default_name)

    inst_cfg = {"url": server.rstrip('/'), "username": login_name, "password": app_password}
    client = DeckClient(inst_cfg)

    click.echo("\nDiscovering boards...")
    try:
        boards = client.list_boards()
    except Exception as e:
        raise click.ClickException(f"Failed to list boards: {e}")

    if not boards:
        click.echo("No boards found.")
        boards_config = {}
    else:
        click.echo(f"Found {len(boards)} board(s)")
        boards_config = {}
        for board in boards:
            board_id = board['id']
            board_title = board['title']
            click.echo(f"\n{'='*50}")
            click.echo(f"Board: {board_title} (id: {board_id})")
            default_key = ''.join(c.lower() if c.isalnum() else '_' for c in board_title)
            default_key = '_'.join(filter(None, default_key.split('_')))
            if not default_key:
                default_key = f"board_{board_id}"
            board_key = click.prompt("Short name for this board", default=default_key)
            board_key = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in board_key)
            try:
                stacks = client.list_stacks(board_id)
            except Exception as e:
                click.echo(f"Error fetching stacks: {e}")
                stacks = []
            stack_id = None
            done_stack_id = None
            if stacks:
                click.echo("\nStacks:")
                for i, s in enumerate(stacks):
                    click.echo(f"  {i+1}. {s['title']} (id: {s['id']})")
                stack_default = stacks[0]['id']
                stack_id = click.prompt("Stack ID for creating new cards", default=stack_default, type=int)
                click.echo("\nWhich stack should be the 'done' stack?")
                click.echo("  0. None")
                for i, s in enumerate(stacks):
                    click.echo(f"  {i+1}. {s['title']} (id: {s['id']})")
                done_choice = click.prompt("Done stack", default=0, type=int)
                if done_choice > 0 and done_choice <= len(stacks):
                    done_stack_id = stacks[done_choice-1]['id']
            else:
                stack_id = click.prompt("Stack ID for creating new cards", type=int)
            board_entry = {"board_id": board_id, "stack_id": stack_id}
            if done_stack_id:
                board_entry["done_stack_id"] = done_stack_id
            boards_config[board_key] = board_entry

    cfg['instances'][instance_name] = {"url": server.rstrip('/'), "username": login_name, "password": app_password, "boards": boards_config}
    if not cfg.get('default_instance'):
        cfg['default_instance'] = instance_name
        click.echo(f"\nSet '{instance_name}' as default instance")
    elif click.confirm(f"\nSet '{instance_name}' as default instance?", default=False):
        cfg['default_instance'] = instance_name

    save_config(cfg)
    click.echo(f"\n{'='*50}")
    click.echo(f"Configuration saved to {get_config_path()}")
    click.echo(f"Instance '{instance_name}' added with {len(boards_config)} board(s)")
    click.echo(f"{'='*50}")


@cli.command("list")
@click.option("-i", "--instance", help="Instance name from config")
@click.option("--boards", is_flag=True, help="List boards and their IDs")
@click.option("--stacks", type=int, help="List stacks for a given board_id")
@click.option("--labels", "labels_board", metavar="BOARD_KEY", help="List available tags/labels for a configured board")
@click.option("--cards", "cards_board", metavar="BOARD_KEY", help="List cards in a configured board")
@click.option("--stack", type=int, help="Stack ID to list cards from")
def list_cmd(instance, boards, stacks, labels_board, cards_board, stack):
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
        return
    click.echo(f"Instance: {inst_name} ({inst['url']})")
    for k, v in inst.get("boards", {}).items():
        done_info = f" done_stack_id={v['done_stack_id']}" if v.get("done_stack_id") else ""
        click.echo(f"  - {k}: board_id={v['board_id']} stack_id={v['stack_id']}{done_info}")


@cli.command("create")
@click.argument("board_key")
@click.argument("title")
@click.option("-d", "--description", default="")
@click.option("-f", "--description-file", type=click.Path(exists=True, path_type=Path))
@click.option("-p", "--prefix", default="")
@click.option("--due-date")
@click.option("-t", "--tag", multiple=True)
@click.option("-a", "--assign", multiple=True)
@click.option("-i", "--instance")
def create_cmd(board_key, title, description, description_file, prefix, due_date, tag, assign, instance):
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)
    card_title = f"{prefix}{title}" if prefix else title
    card_description = read_description(description, description_file)
    label_ids = resolve_label_ids(client, board["board_id"], list(tag)) if tag else []
    try:
        card = client.create_card(board["board_id"], board["stack_id"], card_title, card_description, duedate=due_date, labels=label_ids if label_ids else None, assigned_users=list(assign) if assign else None)
        click.echo(f"Created card #{card['id']} '{card['title']}' in {inst_name}/{board_key}")
        if due_date:
            click.echo(f"  Due: {due_date}")
        if tag:
            click.echo(f"  Tags: {', '.join(tag)}")
        if assign:
            click.echo(f"  Assigned: {', '.join(assign)}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("done")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.option("-i", "--instance")
@click.option("--stack", type=int)
@click.option("--archive", is_flag=True)
def done_cmd(board_key, card_id, instance, stack, archive):
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)
    try:
        if archive:
            client.archive_card(board["board_id"], card_id, archived=True)
            click.echo(f"Archived card #{card_id} in {inst_name}/{board_key}")
            return
        done_stack_id = stack if stack is not None else board.get("done_stack_id")
        if done_stack_id is None:
            raise click.ClickException("No done stack configured. Add 'done_stack_id' to board or use --stack.")
        client.move_card(board["board_id"], card_id, done_stack_id)
        click.echo(f"Marked card #{card_id} as done and moved to done stack in {inst_name}/{board_key}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("move")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.argument("stack_id", type=int)
@click.option("-i", "--instance")
def move_cmd(board_key, card_id, stack_id, instance):
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)
    try:
        client.move_card(board["board_id"], card_id, stack_id)
        click.echo(f"Moved card #{card_id} to stack {stack_id} in {inst_name}/{board_key}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("assign")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.argument("user_id")
@click.option("-i", "--instance")
@click.option("--unassign", is_flag=True)
def assign_cmd(board_key, card_id, user_id, instance, unassign):
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)
    try:
        if unassign:
            client.unassign_card(board["board_id"], card_id)
            click.echo(f"Unassigned card #{card_id} in {inst_name}/{board_key}")
        else:
            client.assign_card(board["board_id"], card_id, user_id)
            click.echo(f"Assigned card #{card_id} to {user_id} in {inst_name}/{board_key}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("search")
@click.argument("board_key")
@click.argument("query")
@click.option("-i", "--instance")
@click.option("--stack", type=int)
@click.option("--include-archived", is_flag=True)
def search_cmd(board_key, query, instance, stack, include_archived):
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
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("show")
@click.argument("board_key")
@click.argument("card_id", type=int)
@click.option("-i", "--instance")
def show_cmd(board_key, card_id, instance):
    cfg = load_config()
    inst_name, inst, board = get_mapping(cfg, instance, board_key)
    client = DeckClient(inst)
    try:
        card = client.get_card_full(board["board_id"], card_id)
        click.echo("=" * 60)
        click.echo(f"Card #{card.get('id')}: {card.get('title', '(untitled)')}")
        click.echo("=" * 60)
        click.echo(f"Board: {inst_name}/{board_key}")
        stack_title = card.get('_stack_title') or card.get('stackTitle')
        if stack_title:
            click.echo(f"Stack: {stack_title} (id: {card.get('stackId') or card.get('_stack_id')})")
        else:
            click.echo(f"Stack ID: {card.get('stackId')}")
        click.echo(f"Status: {'Archived' if card.get('archived') else 'Active'}")
        click.echo(f"Due Date: {card.get('duedate') or 'None'}")
        labels = card.get('labels') or []
        if labels:
            label_names = [l.get('title') or l.get('name') for l in labels if l.get('title') or l.get('name')]
            click.echo(f"Labels: {', '.join(label_names) if label_names else 'None'}")
        else:
            click.echo("Labels: None")
        assigned = card.get('assignedUsers') or card.get('assignedusers') or []
        if assigned:
            names = []
            for a in assigned:
                if isinstance(a, dict):
                    name = a.get('participant', {}).get('displayname') or a.get('displayname') or a.get('uid')
                    if name:
                        names.append(name)
            click.echo(f"Assignees: {', '.join(names) if names else 'None'}")
        else:
            click.echo("Assignees: None")
        click.echo(f"Created: {card.get('createdAt', 'Unknown')}")
        click.echo(f"Last Modified: {card.get('lastModified', 'Unknown')}")
        click.echo("=" * 60)
        desc = card.get('description') or ''
        click.echo("Description:")
        click.echo(desc if desc.strip() else "(empty)")
        click.echo("=" * 60)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()


@cli.command("list-accounts")
def list_accounts_cmd():
    """List configured accounts/instances."""
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        click.echo("No accounts configured. Run `ncdeck add-account` to add one.")
        return
    default = cfg.get('default_instance')
    click.echo(f"Configured instances (default: {default or 'none'}):")
    for name, inst in cfg.get('instances', {}).items():
        marker = " *" if name == default else ""
        click.echo(f"  {name}{marker} - {inst.get('url')} ({inst.get('username')})")
        boards = inst.get('boards', {}) or {}
        for bk, bv in boards.items():
            done = f", done_stack={bv.get('done_stack_id')}" if bv.get('done_stack_id') else ""
            click.echo(f"    {bk}: board_id={bv.get('board_id')}, stack_id={bv.get('stack_id')}{done}")


@cli.command("show-config")
def show_config_cmd():
    """Show current configuration with passwords masked."""
    cfg = load_config()
    if not isinstance(cfg, dict):
        click.echo("No configuration found.")
        return
    masked = json.loads(json.dumps(cfg))
    for inst_name, inst in masked.get('instances', {}).items():
        if isinstance(inst, dict) and inst.get('password'):
            pwd = inst['password']
            if len(pwd) > 8:
                inst['password'] = pwd[:4] + '****' + pwd[-4:]
            else:
                inst['password'] = '****'
    click.echo(yaml.safe_dump(masked, sort_keys=False))
