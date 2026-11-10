#!/usr/bin/env python3
import os, sys, json, time, webbrowser, re
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import click, requests, yaml
from requests.auth import HTTPBasicAuth

CONFIG_PATHS = [Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ncdeck" / "config.yaml", Path.home() / ".ncdeck.yaml"]

def get_config_path():
    for p in CONFIG_PATHS:
        if p.exists(): return p
    p = CONFIG_PATHS[0]; p.parent.mkdir(parents=True, exist_ok=True); return p

def load_config():
    for p in CONFIG_PATHS:
        if p.exists():
            with p.open() as f: return yaml.safe_load(f) or {}
    return {}

def save_config(cfg):
    p = get_config_path(); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w') as f: yaml.safe_dump(cfg, f, sort_keys=False)

class DeckClient:
    def __init__(self, instance_cfg, debug=False):
        self.url = instance_cfg["url"].rstrip("/")
        self.auth = HTTPBasicAuth(instance_cfg["username"], instance_cfg["password"])
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.debug = debug

    def _log(self, method, url, **kwargs):
        if self.debug:
            click.echo(f"[DEBUG] {method} {url}", err=True)
            if kwargs.get('data'):
                click.echo(f"[DEBUG] DATA: {kwargs['data'][:200]}", err=True)
            if kwargs.get('json'):
                click.echo(f"[DEBUG] JSON: {json.dumps(kwargs['json'])[:200]}", err=True)
    def _get(self, path):
        url = f"{self.url}{path}"
        if self.debug: click.echo(f"[DEBUG] GET {url}", err=True)
        r = self.session.get(url)
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code}", err=True)
        r.raise_for_status()
        return r.json()

    def _post(self, path, data):
        url = f"{self.url}{path}"
        if self.debug:
            click.echo(f"[DEBUG] POST {url}", err=True)
            try: click.echo(f"[DEBUG] DATA {json.dumps(data)[:300]}", err=True)
            except: pass
        r = self.session.post(url, data=json.dumps(data))
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code}", err=True)
        r.raise_for_status()
        return r.json()

    def _post_file(self, path, files, data=None):
        headers = dict(self.session.headers)
        headers.pop('Content-Type', None)
        headers['OCS-APIREQUEST'] = 'true'
        url = f"{self.url}{path}"
        if self.debug: click.echo(f"[DEBUG] POST {url}", err=True)
        r = self.session.post(url, files=files, data=data, headers=headers)
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code}", err=True)
        r.raise_for_status()
        return r.json()

    def _clean_card_payload(self, data):
        if not isinstance(data, dict): return data
        payload = dict(data)
        # Remove read-only/computed fields that can cause 400 on some Deck versions
        for k in ('ETag', 'lastModified', 'lastEditor', 'createdAt', 'deletedAt',
                  'attachments', 'attachmentCount', 'commentsCount', 'commentsUnread',
                  'permissions', 'relatedStack', 'relatedBoard', 'overdue', 'id',
                  'notified', 'deletedAt'):
            payload.pop(k, None)
        # Normalize owner to uid string if object
        o = payload.get('owner')
        if isinstance(o, dict):
            payload['owner'] = o.get('uid') or o.get('primaryKey') or ''
        # Normalize duedate to UTC Z format if present
        dd = payload.get('duedate')
        if isinstance(dd, str) and dd:
            try:
                dt = _parse_duedate(dd)
                if dt:
                    payload['duedate'] = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            except Exception:
                pass
        return payload

    def _put(self, path, data):
        url = f"{self.url}{path}"
        payload = self._clean_card_payload(data)
        if self.debug:
            click.echo(f"[DEBUG] PUT {url}", err=True)
            try: click.echo(f"[DEBUG] DATA {json.dumps(payload)[:800]}", err=True)
            except: pass
        r = self.session.put(url, data=json.dumps(payload))
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code} {r.text[:500]}", err=True)
        if not r.ok:
            msg = r.text.strip()
            raise Exception(f"{r.status_code} {r.reason} for {url}: {msg[:500]}")
        try:
            return r.json()
        except Exception:
            return {}
    def list_boards(self): return self._get("/index.php/apps/deck/api/v1.0/boards")
    def get_board(self, board_id): return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}")

    def get_theming_color(self):
        """Return a hex theme color from Nextcloud capabilities, or None."""
        try:
            url = f"{self.url}/ocs/v2.php/cloud/capabilities?format=json"
            if self.debug: click.echo(f"[DEBUG] GET {url}", err=True)
            r = self.session.get(url, headers={"OCS-APIREQUEST": "true", "Accept": "application/json"})
            if self.debug: click.echo(f"[DEBUG] RESP {r.status_code}", err=True)
            if r.status_code != 200:
                return None
            data = r.json() or {}
            theming = (((data.get('ocs') or {}).get('data') or {}).get('capabilities') or {}).get('theming') or {}
            if not isinstance(theming, dict):
                return None

            def _hex(v):
                if not isinstance(v, str): return None
                s = v.strip()
                if re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', s):
                    return s
                return None

            bg = _hex(theming.get('background'))
            if bg:
                return bg
            col = _hex(theming.get('color'))
            if col:
                return col
            return None
        except Exception as e:
            if self.debug: click.echo(f"[DEBUG] theming color fetch failed: {e}", err=True)
            return None
    def list_stacks(self, board_id): return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks")
    def list_cards(self, board_id, stack_id=None):
        try:
            stacks = self.list_stacks(board_id); cards = []
            for stack in stacks:
                if stack_id is not None and stack.get('id') != int(stack_id): continue
                sc = stack.get('cards') or []
                for c in sc: c['_stack_title']=stack.get('title'); c['_stack_id']=stack.get('id')
                cards.extend(sc)
            if cards: return cards
        except: pass
        try:
            board = self.get_board(board_id)
            if board and board.get('stacks'):
                cards=[]
                for stack in board['stacks']:
                    if stack_id is None or stack.get('id')==int(stack_id):
                        sc=stack.get('cards') or []
                        for c in sc: c['_stack_title']=stack.get('title'); c['_stack_id']=stack.get('id')
                        cards.extend(sc)
                return cards
        except: pass
        return []
    def get_card(self, board_id, card_id): return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/-1/cards/{card_id}")
    def get_card_full(self, board_id, card_id):
        try: return self.get_card(board_id, card_id)
        except:
            for c in self.list_cards(board_id):
                if c.get('id')==int(card_id): return c
            raise
    def _owner_uid(self, card):
        o = card.get('owner')
        if isinstance(o, str): return o
        if isinstance(o, dict): return o.get('uid') or o.get('primaryKey') or ''
        return ''

    def _put_ocs(self, path, data):
        url = f"{self.url}{path}"
        if '?' in url:
            url += '&format=json'
        else:
            url += '?format=json'
        headers = dict(self.session.headers)
        headers['OCS-APIRequest'] = 'true'
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json'
        if self.debug:
            click.echo(f"[DEBUG] PUT {url}", err=True)
            try: click.echo(f"[DEBUG] DATA {json.dumps(data)[:800]}", err=True)
            except: pass
        r = self.session.put(url, data=json.dumps(data), headers=headers)
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code} {r.text[:500]}", err=True)
        if not r.ok:
            msg = r.text.strip()
            raise Exception(f"{r.status_code} {r.reason} for {url}: {msg[:500]}")
        try:
            j = r.json()
        except Exception:
            return {}
        if isinstance(j, dict) and 'ocs' in j:
            return (j.get('ocs') or {}).get('data') or {}
        return j

    def _ocs_data(self, j):
        if isinstance(j, dict) and 'ocs' in j:
            return (j.get('ocs') or {}).get('data')
        return j

    def _ocs_get(self, path, params=None):
        url = f"{self.url}{path}"
        if '?' in url:
            url += '&format=json'
        else:
            url += '?format=json'
        headers = dict(self.session.headers)
        headers['OCS-APIREQUEST'] = 'true'
        headers['Accept'] = 'application/json'
        headers.pop('Content-Type', None)
        if self.debug:
            click.echo(f"[DEBUG] GET {url} params={params}", err=True)
        r = self.session.get(url, params=params, headers=headers)
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code} {r.text[:500]}", err=True)
        if not r.ok:
            msg = r.text.strip()
            raise Exception(f"{r.status_code} {r.reason} for {url}: {msg[:500]}")
        try:
            j = r.json()
        except Exception:
            return {}
        return self._ocs_data(j)

    def _post_ocs(self, path, data):
        url = f"{self.url}{path}"
        if '?' in url:
            url += '&format=json'
        else:
            url += '?format=json'
        headers = dict(self.session.headers)
        headers['OCS-APIREQUEST'] = 'true'
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json'
        if self.debug:
            click.echo(f"[DEBUG] POST {url}", err=True)
            try: click.echo(f"[DEBUG] DATA {json.dumps(data)[:800]}", err=True)
            except: pass
        r = self.session.post(url, data=json.dumps(data), headers=headers)
        if self.debug: click.echo(f"[DEBUG] RESP {r.status_code} {r.text[:500]}", err=True)
        if not r.ok:
            msg = r.text.strip()
            raise Exception(f"{r.status_code} {r.reason} for {url}: {msg[:500]}")
        try:
            j = r.json()
        except Exception:
            return {}
        return self._ocs_data(j)

    def list_comments(self, card_id, limit=50, offset=0):
        return self._ocs_get(
            f"/ocs/v2.php/apps/deck/api/v1.0/cards/{card_id}/comments",
            params={'limit': int(limit), 'offset': int(offset)},
        ) or []

    def add_comment(self, card_id, message, parent_id=None):
        payload = {"message": message, "parentId": parent_id}
        return self._post_ocs(f"/ocs/v2.php/apps/deck/api/v1.0/cards/{card_id}/comments", payload)

    def reorder_card(self, board_id, card_id, target_stack_id, order=0):
        # Use OCS reorder endpoint (matches Deck web UI behavior) with full card payload
        card = self.get_card(board_id, card_id)
        payload = dict(card)
        payload['stackId'] = int(target_stack_id)
        payload['order'] = int(order)
        payload['boardId'] = int(board_id)
        return self._put_ocs(f"/ocs/v2.php/apps/deck/api/v1.0/cards/{card_id}/reorder", payload)

    def move_card(self, board_id, card_id, stack_id):
        return self.reorder_card(board_id, card_id, stack_id, order=0)

    def _card_update_payload(self, card):
        payload = {
            "title": card.get('title') or '',
            "description": card.get('description') or '',
            "type": card.get('type') or 'plain',
            "owner": self._owner_uid(card),
            "order": int(card.get('order') if card.get('order') is not None else 0),
            "duedate": card.get('duedate'),
            "archived": bool(card.get('archived')),
            "done": card.get('done'),
        }
        # Normalize duedate
        if isinstance(payload.get('duedate'), str) and payload['duedate']:
            dt = _parse_duedate(payload['duedate'])
            if dt:
                payload['duedate'] = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        # Normalize done
        if isinstance(payload.get('done'), str) and payload['done']:
            dt = _parse_duedate(payload['done'])
            if dt:
                payload['done'] = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return payload

    def update_card(self, board_id, card_id, **changes):
        card = self.get_card(board_id, card_id)
        for k, v in changes.items():
            card[k] = v
        payload = self._card_update_payload(card)
        return self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}", payload)

    def mark_card_done(self, board_id, card_id, done=True):
        val = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if done else None
        return self.update_card(board_id, card_id, done=val)

    def assign_card(self, board_id, card_id, user_id):
        card = self.get_card(board_id, card_id)
        return self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}/assignUser", {"userId": user_id})

    def unassign_card(self, board_id, card_id, user_id):
        card = self.get_card(board_id, card_id)
        return self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}/unassignUser", {"userId": user_id})

    def archive_card(self, board_id, card_id, archived=True):
        card = self.get_card(board_id, card_id)
        ep = 'archive' if archived else 'unarchive'
        return self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}/{ep}", {})

    def update_card_duedate(self, board_id, card_id, duedate):
        card = self.get_card(board_id, card_id)
        payload = self._card_update_payload(card)
        # normalize input duedate
        if isinstance(duedate, str) and duedate:
            dt = _parse_duedate(duedate)
            if dt:
                payload['duedate'] = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                payload['duedate'] = duedate
        else:
            payload['duedate'] = duedate
        return self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card.get('stackId')}/cards/{card_id}", payload)
    def list_labels(self, board_id):
        try:
            board=self.get_board(board_id)
            if isinstance(board,dict) and board.get('labels'): return board['labels']
        except: pass
        try: return self._get(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/labels")
        except: 
            try: return self._get(f"/index.php/apps/deck/api/v1.1/boards/{board_id}/labels")
            except: raise
    def create_card(self, board_id, stack_id, title, description="", duedate=None, labels=None, assigned_users=None):
        payload={"title":title,"description":description,"type":"plain","order":999}
        if duedate: payload["duedate"]=duedate
        if labels: payload["labels"]=[{"id":int(l)} for l in labels]
        card = self._post(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards", payload)
        if assigned_users:
            card_id = card.get('id')
            card_stack = card.get('stackId') or stack_id
            for u in assigned_users:
                try:
                    self._put(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{card_stack}/cards/{card_id}/assignUser", {"userId": u})
                except Exception as e:
                    if self.debug: click.echo(f"[DEBUG] assignUser failed for {u}: {e}", err=True)
                    raise
        return card

    def upload_attachment(self, board_id, card_id, file_path):
        p = Path(file_path)
        card = None
        try:
            card = self.get_card(board_id, card_id)
        except Exception:
            pass
        stack_id = (card.get('stackId') if card else None) or -1
        
        import subprocess
        # Try POST with multipart as per API docs
        try:
            result = subprocess.run([
                'curl', '-s', '-w', '\n%{http_code}', '-u', f"{self.auth.username}:{self.auth.password}",
                '-X', 'POST',
                '-H', 'OCS-APIREQUEST: true',
                '-F', f'type=file',
                '-F', f'file=@{p.absolute()};filename={p.name}',
                f"{self.url}/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/attachments"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if self.debug:
                click.echo(f"[DEBUG] POST multipart tried to /attachments, rc={result.returncode}", err=True)
            output = result.stdout.decode()
            if result.returncode == 0 and '405' not in output and '404' not in output:
                return "uploaded"
        except Exception as e:
            if self.debug:
                click.echo(f"[DEBUG] Error: {e}", err=True)
            pass
        
        # Try with deck_file type
        try:
            result = subprocess.run([
                'curl', '-s', '-w', '\n%{http_code}', '-u', f"{self.auth.username}:{self.auth.password}",
                '-X', 'POST',
                '-H', 'OCS-APIREQUEST: true',
                '-F', f'type=deck_file',
                '-F', f'file=@{p.absolute()};filename={p.name}',
                f"{self.url}/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/attachments"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if self.debug:
                click.echo(f"[DEBUG] POST multipart tried deck_file, rc={result.returncode}", err=True)
            output = result.stdout.decode()
            if result.returncode == 0 and '405' not in output:
                return "uploaded"
        except Exception:
            pass
        
        raise Exception("Failed to upload attachment")

def get_mapping(cfg, instance_name: Optional[str], board_key: str):
    inst_name = instance_name or cfg.get("default_instance")
    if not inst_name: raise click.ClickException("No instance specified and no default_instance in config")
    try: inst = cfg["instances"][inst_name]
    except KeyError: raise click.ClickException(f"Instance '{inst_name}' not found in config")
    try: board = inst["boards"][board_key]
    except KeyError: raise click.ClickException(f"Board mapping '{board_key}' not found for instance '{inst_name}'")
    return inst_name, inst, board

def read_description(description: str, description_file: Optional[Path]) -> str:
    if description_file:
        with description_file.open("r", encoding="utf-8") as f: return f.read()
    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read()
        if description: return f"{description}\n\n{stdin_data}"
        return stdin_data
    return description

def resolve_label_ids(client: DeckClient, board_id: int, tag_names: List[str]) -> List[int]:
    if not tag_names: return []
    labels = client.list_labels(board_id)
    label_map={}
    for label in labels:
        name = label.get("title") or label.get("name") or ""
        if name: label_map[name.strip().lower()]=label["id"]
    if not label_map: raise click.ClickException("No labels/tags found on this board.")
    resolved=[]; missing=[]
    for tag in tag_names:
        key=tag.strip().lower()
        if key in label_map: resolved.append(label_map[key])
        else: missing.append(tag)
    if missing: raise click.ClickException(f"Unknown tag(s): {', '.join(missing)}")
    return resolved

@click.group()
@click.version_option(version="0.2.0", prog_name="ncdeck")
@click.option('--debug', is_flag=True, hidden=True, help='Enable debug output')
@click.pass_context
def cli(ctx, debug):
    """Create Nextcloud Deck cards from the CLI."""
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug


@cli.group()
def account():
    """Manage Nextcloud accounts."""
    pass


@account.command("add")
@click.option("-i", "--instance", "instance_name", help="Short name for this instance")
@click.option("--url", help="Nextcloud server URL")
@click.option("--color", "theme_color", help="Theme color for this instance (e.g. cyan, blue, magenta, green, yellow)")
def account_add_cmd(instance_name, url, theme_color):
    """Add a Nextcloud account via Login Flow v2 with board autodiscovery."""
    cfg = load_config()
    if not isinstance(cfg, dict): cfg = {}
    if 'instances' not in cfg or not isinstance(cfg['instances'], dict): cfg['instances'] = {}
    if not url: url = click.prompt("Nextcloud server URL (e.g. https://cloud.example.com)")
    url = url.rstrip('/')
    ui_info(f"Starting Nextcloud Login Flow v2 for {url}...", 'cyan')
    resp = requests.post(f"{url}/index.php/login/v2", headers={"User-Agent": "ncdeck-cli"}, timeout=30)
    resp.raise_for_status()
    flow = resp.json()
    login_url = flow['login']; poll = flow['poll']; endpoint = poll['endpoint']; token = poll['token']
    ui_info(f"Opening browser to authenticate...\nIf browser doesn't open, visit: {login_url}", 'cyan')
    try: webbrowser.open(login_url)
    except: pass
    ui_dim("Waiting for authentication...")
    creds=None
    for _ in range(120):
        try:
            r = requests.post(endpoint, data={"token": token}, timeout=30)
            if r.status_code == 200: creds=r.json(); break
            time.sleep(2)
        except: time.sleep(2); continue
    if not creds: raise click.ClickException("Authentication timed out or failed")
    server = creds.get('server', url); login_name = creds.get('loginName') or creds.get('user'); app_password = creds.get('appPassword')
    ui_ok(f"Authenticated as {login_name} on {server}")
    if not instance_name:
        default_name = login_name if login_name and login_name not in cfg['instances'] else f"nc_{login_name}"
        instance_name = click.prompt("Short name for this instance", default=default_name)
    client = DeckClient({"url": server.rstrip('/'), "username": login_name, "password": app_password})
    detected_color = None
    if theme_color is None:
        detected_color = client.get_theming_color()
        prompt_default = detected_color or ""
        prompt_label = "Theme color (from Nextcloud theme)" if detected_color else "Theme color (blank for cyan)"
        theme_color = (click.prompt(prompt_label, default=prompt_default, show_default=bool(detected_color)) or "").strip() or None
    inst_color = _inst_color(theme_color)
    ui_info("Discovering boards...", inst_color)
    boards = client.list_boards()
    boards_config={}
    if boards:
        for board in boards:
            board_id = board['id']; board_title = board['title']
            ui_header(f"Board: {board_title} (id: {board_id})", inst_color)
            default_key = '_'.join(filter(None, ''.join(c.lower() if c.isalnum() else '_' for c in board_title).split('_')))
            if not default_key: default_key = f"board_{board_id}"
            board_key = click.prompt("Short name for this board", default=default_key)
            board_key = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in board_key)
            stacks = client.list_stacks(board_id)
            stack_id=None; done_stack_id=None
            if stacks:
                ui_kv("Stacks", "", inst_color)
                for i,s in enumerate(stacks): click.echo(f"    {_st(str(i+1)+'.', fg=inst_color)} {s['title']} {_st(f'(id: {s['id']})', dim=True)}")
                stack_id = click.prompt("Stack ID for creating new cards", default=stacks[0]['id'], type=int)
                ui_kv("Done stack", "choose 0 for none", inst_color)
                click.echo(f"    {_st('0.', fg=inst_color)} None")
                for i,s in enumerate(stacks): click.echo(f"    {_st(str(i+1)+'.', fg=inst_color)} {s['title']} {_st(f'(id: {s['id']})', dim=True)}")
                done_choice = click.prompt("Done stack", default=0, type=int)
                if done_choice>0 and done_choice<=len(stacks): done_stack_id=stacks[done_choice-1]['id']
            else:
                stack_id = click.prompt("Stack ID for creating new cards", type=int)
            be={"board_id":board_id,"stack_id":stack_id}
            if done_stack_id: be["done_stack_id"]=done_stack_id
            boards_config[board_key]=be
    inst_entry={"url":server.rstrip('/'),"username":login_name,"password":app_password,"boards":boards_config}
    if theme_color: inst_entry["color"]=theme_color
    cfg['instances'][instance_name]=inst_entry
    if not cfg.get('default_instance'): cfg['default_instance']=instance_name
    elif click.confirm(f"\nSet '{instance_name}' as default instance?", default=False): cfg['default_instance']=instance_name
    save_config(cfg)
    ui_sep(inst_color)
    ui_ok(f"Configuration saved to {get_config_path()}")
    ui_kv("Instance", f"{instance_name} ({len(boards_config)} board(s))", inst_color)

@account.command("list")
@click.pass_context
def account_list_cmd(ctx):
    """List configured accounts/instances."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        ui_warn("No accounts configured. Run `ncdeck account add` to add one."); return
    default = cfg.get('default_instance')
    ui_header(f"Configured instances (default: {default or 'none'})", 'cyan')
    for name, inst in cfg.get('instances', {}).items():
        c = _inst_color(inst)
        marker = _st(" [default]", fg=c, bold=True) if name == default else ""
        clr = f" {_st(f'({inst.get('color') or inst.get('theme_color')})', dim=True)}" if (inst.get('color') or inst.get('theme_color')) else ""
        click.echo(f"  {_st(name, fg=c, bold=True)}{marker} {_st(inst.get('url',''), dim=True)} {_st(f'@{inst.get('username')}', fg=c)}{clr}")
        for bk,bv in (inst.get('boards') or {}).items():
            done = f" {_st(f'done={bv.get('done_stack_id')}', dim=True)}" if bv.get('done_stack_id') else ""
            click.echo(f"    {_st('•', fg=c)} {_st(bk, fg=c)}  board={bv.get('board_id')} stack={bv.get('stack_id')}{done}")


@account.command("delete")
@click.argument("instance_name")
@click.option("-f", "--force", is_flag=True, help="Force deletion without confirmation")
def account_delete_cmd(instance_name, force):
    """Delete a configured account."""
    cfg = load_config()
    if not isinstance(cfg, dict):
        raise click.ClickException("No configuration found")
    if 'instances' not in cfg or instance_name not in cfg['instances']:
        raise click.ClickException(f"Instance '{instance_name}' not found in config")
    c = _inst_color(cfg['instances'].get(instance_name))
    if not force:
        if not click.confirm(f"Delete instance '{instance_name}'?"):
            ui_warn("Cancelled")
            return
    del cfg['instances'][instance_name]
    if cfg.get('default_instance') == instance_name:
        if cfg['instances']:
            new_default = next(iter(cfg['instances'].keys()))
            cfg['default_instance'] = new_default
            ui_warn(f"Default instance changed to '{new_default}'")
        else:
            cfg.pop('default_instance', None)
    save_config(cfg)
    ui_ok(f"Deleted instance '{_st(instance_name, fg=c, bold=True)}'")

@cli.group("config")
def config_group():
    """Manage configuration."""
    pass


@config_group.command("color")
@click.argument("instance_name")
@click.argument("color_value", required=False)
@click.option("--theme", "from_theme", is_flag=True, help="Fetch color from the instance's current Nextcloud theme")
@click.pass_context
def config_color_cmd(ctx, instance_name, color_value, from_theme):
    """Set an instance color manually, or fetch it from the Nextcloud theme."""
    debug = ctx.obj.get('debug') if ctx and ctx.obj else False
    if from_theme and color_value:
        raise click.ClickException("Provide either COLOR or --theme, not both")
    if not from_theme and not color_value:
        raise click.ClickException("Provide COLOR or use --theme")
    cfg = load_config()
    if not isinstance(cfg, dict) or not (cfg.get('instances') or {}).get(instance_name):
        raise click.ClickException(f"Instance '{instance_name}' not found in config")
    inst = cfg['instances'][instance_name]
    ic_before = _inst_color(inst)
    if from_theme:
        client = DeckClient(inst, debug=debug)
        ui_info(f"Fetching theme color from {inst.get('url','')}...", ic_before)
        detected = client.get_theming_color()
        if not detected:
            raise click.ClickException("Could not detect a theme color from Nextcloud capabilities (theming may be unavailable or background is an image)")
        color_value = detected
    # normalize/validate; store hex/named/r,g,b as normalized string (preserve hex/named, convert rgb tuple)
    norm = _normalize_color(color_value, default=None)
    if norm is None:
        raise click.ClickException(f"Invalid color: {color_value}")
    if isinstance(norm, tuple):
        store_val = '#%02x%02x%02x' % norm
    else:
        store_val = norm
    inst['color'] = store_val
    save_config(cfg)
    ui_ok(f"Set color for {_st(instance_name, fg=_inst_color(inst), bold=True)} to {_st(store_val, fg=_inst_color(inst))}")


@cli.command("show-config")
def show_config_cmd():
    """Show current configuration with passwords masked."""
    cfg = load_config()
    if not isinstance(cfg, dict): ui_warn("No configuration found."); return
    masked = json.loads(json.dumps(cfg))
    for inst_name, inst in masked.get('instances', {}).items():
        if isinstance(inst, dict) and inst.get('password'):
            inst['password'] = '****'
    ui_header(f"Configuration: {get_config_path()}", 'cyan')
    click.echo(yaml.safe_dump(masked, sort_keys=False))

@cli.command("list")
@click.option("-i","--instance")
@click.option("--boards",is_flag=True)
@click.option("--stacks",type=int)
@click.option("--labels","labels_board",metavar="BOARD_KEY")
@click.option("--cards","cards_board",metavar="BOARD_KEY")
@click.option("--stack",type=int)
@click.option("--all", "all_cards", is_flag=True, help="Show all cards (include unassigned on shared boards)")
@click.pass_context
def list_cmd(ctx,instance,boards,stacks,labels_board,cards_board,stack,all_cards):
    """List configured boards/stacks/labels/cards or instance details."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name=instance or cfg.get("default_instance")
    if not inst_name: raise click.ClickException("No instance specified")
    inst=cfg.get("instances",{}).get(inst_name)
    if not inst: raise click.ClickException(f"Instance '{inst_name}' not found")
    client=DeckClient(inst, debug=debug); ic=_inst_color(inst)
    if boards:
        ui_header(f"Boards on {inst_name}", ic)
        for b in client.list_boards():
            owner=(b.get("owner") or {}).get("uid"); click.echo(f"  {_st('board', fg=ic)}={b['id']} {_st(str(b['title']), bold=True)} {_st(f'owner={owner}', dim=True)}")
        return
    if stacks is not None:
        ui_header(f"Stacks for board {stacks} ({inst_name})", ic)
        for s in client.list_stacks(stacks): click.echo(f"  {_st('stack', fg=ic)}={s['id']} {_st(str(s['title']), bold=True)} {_st(f'order={s.get('order')}', dim=True)}")
        return
    if cards_board:
        inst_name_res,inst_res,board=get_mapping(cfg,instance,cards_board)
        cards=client.list_cards(board["board_id"],stack_id=stack)
        uname = inst_res.get('username'); rc=_inst_color(inst_res)
        if not all_cards and uname and _board_is_shared(client, board["board_id"], uname):
            cards = [c for c in cards if _card_assigned_to(c, uname)]
        ui_header(f"Cards: {inst_name_res}/{cards_board}", rc)
        if not cards: ui_dim("  (no cards found)"); return
        for card in cards:
            card_id=card.get('id'); title=card.get('title') or '(untitled)'; st=card.get('_stack_title') or card.get('stackTitle') or ''
            du=card.get('duedate'); asn=card.get('assignedUsers') or card.get('assignedusers') or []
            flags=[]
            if card.get('archived'): flags.append(_st('ARCHIVED', fg='yellow'))
            if card.get('done'): flags.append(_st('DONE', fg='green'))
            fstr=(' '+' '.join(f'[{f}]' for f in flags)) if flags else ''
            stack_s=f" {_st(f'[{st}]', fg=rc)}" if st else ''
            astr=""
            if asn:
                ns=[]
                for a in asn:
                    if isinstance(a,dict): n=a.get('participant',{}).get('displayname') or a.get('displayname') or a.get('uid')
                    else: n=None
                    if n: ns.append(n)
                if ns: astr=f" {_st('@'+','.join(ns), dim=True)}"
            click.echo(f"  {_st('#'+str(card_id), fg=rc, bold=True)}{stack_s}{fstr} {title}{astr}")
            if du: ui_kv("Due", _fmt_ts(du), rc, label_width=10)
        return
    if labels_board:
        inst_name_res,inst_res,board=get_mapping(cfg,instance,labels_board)
        rc=_inst_color(inst_res)
        try:
            labels=client.list_labels(board["board_id"])
            ui_header(f"Tags/labels: {inst_name_res}/{labels_board}", rc)
            if not labels: ui_dim("  (no labels found)"); return
            for l in labels: click.echo(f"  {_st('•', fg=rc)} {(l.get('title') or l.get('name'))} {_st(f'(id={l['id']})', dim=True)}")
        except Exception as e: ui_err(str(e))
        return
    ui_header(f"Instance: {inst_name}", ic)
    ui_kv("URL", inst.get('url',''), ic)
    ui_kv("User", inst.get('username',''), ic)
    if inst.get('color') or inst.get('theme_color'): ui_kv("Color", inst.get('color') or inst.get('theme_color'), ic)
    for k,v in inst.get("boards",{}).items():
        di=f" done_stack={v['done_stack_id']}" if v.get("done_stack_id") else ""
        click.echo(f"  {_st('•', fg=ic)} {_st(k, fg=ic, bold=True)}  board={v['board_id']} stack={v['stack_id']}{_st(di, dim=True)}")

@cli.command("create")
@click.argument("board_key")
@click.argument("title")
@click.option("-d","--description",default="")
@click.option("-f","--description-file",type=click.Path(exists=True,path_type=Path))
@click.option("-p","--prefix",default="")
@click.option("--due-date", help="Due date/time (e.g. 2026-06-10 13:00, 2026-06-10, today, tomorrow; date-only defaults to 17:00)")
@click.option("-t","--tag",multiple=True)
@click.option("-a","--assign",multiple=True)
@click.option("--attach",type=click.Path(exists=True,path_type=Path),multiple=True,help="Attach file(s) to the created card")
@click.option("-i","--instance")
@click.pass_context
def create_cmd(ctx,board_key,title,description,description_file,prefix,due_date,tag,assign,attach,instance):
    """Create a new card on a board."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    ct=f"[{prefix}] {title}" if prefix else title; cd=read_description(description,description_file)
    lids=resolve_label_ids(client,board["board_id"],list(tag)) if tag else []
    due_norm = _normalize_create_duedate(due_date) if due_date else None
    assigned_users = list(assign) if assign else ([inst['username']] if inst.get('username') else None)
    try:
        card=client.create_card(board["board_id"],board["stack_id"],ct,cd,duedate=due_norm,labels=lids if lids else None,assigned_users=assigned_users)
        ui_ok(f"Created card {_st('#'+str(card['id']), fg=ic, bold=True)} {_st(card['title'], bold=True)} in {_st(f'{inst_name}/{board_key}', fg=ic)}")
        if due_norm: ui_kv("Due", _fmt_ts(due_norm), ic)
        if tag: ui_kv("Tags", ', '.join(tag), ic)
        if assigned_users: ui_kv("Assigned", ', '.join(assigned_users), ic)
        for a in attach:
            try:
                client.upload_attachment(board["board_id"], card['id'], a)
                ui_kv("Attached", Path(a).name, ic)
            except Exception as e:
                ui_warn(f"Failed to attach {Path(a).name}: {e}")
    except Exception as e: ui_err(str(e)); sys.exit(1)

@cli.command("done")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.option("-i","--instance")
@click.option("--stack",type=int)
@click.option("--archive",is_flag=True)
@click.pass_context
def done_cmd(ctx,board_key,card_id,instance,stack,archive):
    """Mark a card as done and move it to the done stack (or archive it)."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    try:
        if archive:
            client.archive_card(board["board_id"],card_id,archived=True)
            ui_ok(f"Archived card {_st('#'+str(card_id), fg=ic, bold=True)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
            return
        ds=stack if stack is not None else board.get("done_stack_id")
        if ds is None: raise click.ClickException("No done stack configured")
        client.mark_card_done(board["board_id"], card_id, done=True)
        client.move_card(board["board_id"], card_id, ds)
        ui_ok(f"Marked card {_st('#'+str(card_id), fg=ic, bold=True)} as done ({_st(f'{inst_name}/{board_key}', fg=ic)})")
    except Exception as e: ui_err(str(e)); sys.exit(1)

@cli.command("move")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.argument("stack_id",type=int)
@click.option("-i","--instance")
@click.pass_context
def move_cmd(ctx,board_key,card_id,stack_id,instance):
    """Move a card to a different stack."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    try:
        client.move_card(board["board_id"],card_id,stack_id)
        ui_ok(f"Moved card {_st('#'+str(card_id), fg=ic, bold=True)} to stack {_st(str(stack_id), fg=ic)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
    except Exception as e: ui_err(str(e)); sys.exit(1)

@cli.command("assign")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.argument("user_id")
@click.option("-i","--instance")
@click.option("--unassign",is_flag=True)
@click.pass_context
def assign_cmd(ctx,board_key,card_id,user_id,instance,unassign):
    """Assign or unassign a user to/from a card."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    try:
        if unassign:
            client.unassign_card(board["board_id"],card_id,user_id)
            ui_ok(f"Unassigned {_st('#'+str(card_id), fg=ic, bold=True)} from {_st(user_id, fg=ic)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
        else:
            client.assign_card(board["board_id"],card_id,user_id)
            ui_ok(f"Assigned {_st('#'+str(card_id), fg=ic, bold=True)} to {_st(user_id, fg=ic)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
    except Exception as e: ui_err(str(e)); sys.exit(1)


@cli.command("attach")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.argument("file_path",type=click.Path(exists=True,path_type=Path))
@click.option("-i","--instance")
@click.pass_context
def attach_cmd(ctx,board_key,card_id,file_path,instance):
    """Attach a file to an existing card."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    try:
        client.upload_attachment(board["board_id"],card_id,file_path)
        ui_ok(f"Attached {_st(file_path.name, bold=True)} to {_st('#'+str(card_id), fg=ic, bold=True)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
    except Exception as e: ui_err(str(e)); sys.exit(1)

@cli.command("comment")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.argument("message")
@click.option("-i","--instance")
@click.option("--parent",type=int,help="ID of the comment to reply to")
@click.pass_context
def comment_cmd(ctx,board_key,card_id,message,instance,parent):
    """Add a comment to a card. Use '-' as MESSAGE to read from stdin."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    if message == '-':
        message = sys.stdin.read()
    message = (message or '').strip()
    if not message:
        raise click.ClickException("Comment message is empty")
    if len(message) > 1000:
        raise click.ClickException(f"Comment is too long ({len(message)} chars); maximum is 1000")
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    ic=_inst_color(inst)
    try:
        comment = client.add_comment(card_id, message, parent_id=parent)
        cid = comment.get('id') if isinstance(comment, dict) else None
        ref = f"#{cid}" if cid is not None else "comment"
        ui_ok(f"Added {_st(ref, fg=ic, bold=True)} to {_st('#'+str(card_id), fg=ic, bold=True)} ({_st(f'{inst_name}/{board_key}', fg=ic)})")
        author = (comment.get('actorDisplayName') or comment.get('actorId')) if isinstance(comment, dict) else None
        ts = _fmt_ts(comment.get('creationDateTime')) if isinstance(comment, dict) else None
        meta = ' '.join(x for x in [author, ts] if x)
        if meta:
            click.echo(f"  {_st(meta, dim=True)}")
        ui_dim(f"  {_short_desc(message, 100)}")
    except Exception as e: ui_err(str(e)); sys.exit(1)

@cli.command("search")
@click.argument("board_key")
@click.argument("query")
@click.option("-i","--instance")
@click.option("--stack",type=int)
@click.option("--include-archived",is_flag=True)
@click.option("--all", "all_cards", is_flag=True, help="Show all cards (include unassigned on shared boards)")
@click.pass_context
def search_cmd(ctx,board_key,query,instance,stack,include_archived,all_cards):
    """Search cards by keyword in title or description."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    cards=client.list_cards(board["board_id"],stack_id=stack)
    uname = inst.get('username')
    if not all_cards and uname and _board_is_shared(client, board["board_id"], uname):
        cards = [c for c in cards if _card_assigned_to(c, uname)]
    ql=query.lower(); res=[]
    for c in cards:
        if not include_archived and c.get('archived'): continue
        if ql in (c.get('title') or '').lower() or ql in (c.get('description') or '').lower(): res.append(c)
    ic = _inst_color(inst)
    if not res: ui_dim(f"No cards found matching '{query}' in {inst_name}/{board_key}"); return
    ui_header(f"Search: '{query}' in {inst_name}/{board_key} ({len(res)} match(es))", ic)
    for c in res:
        cid=c.get('id'); t=c.get('title') or '(untitled)'; st=c.get('_stack_title') or c.get('stackTitle') or ''
        flags = []
        if c.get('archived'): flags.append(_st('ARCHIVED', fg='yellow'))
        if c.get('done'): flags.append(_st('DONE', fg='green'))
        fstr = (' ' + ' '.join(f'[{f}]' for f in flags)) if flags else ''
        stack_s = f" {_st(f'[{st}]', fg=ic)}" if st else ''
        click.echo(f"  {_st('#'+str(cid), fg=ic, bold=True)}{stack_s}{fstr} {t}")
        if c.get('duedate'): ui_kv("Due", _fmt_ts(c['duedate']), ic, label_width=10)

@cli.command("show")
@click.argument("board_key")
@click.argument("card_id",type=int)
@click.option("-i","--instance")
@click.pass_context
def show_cmd(ctx,board_key,card_id,instance):
    """Show full details for a card."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    card=client.get_card_full(board["board_id"],card_id)
    ic = _inst_color(inst)
    ui_header(f"Card #{card.get('id')}: {card.get('title')}", ic)
    ui_kv("Board", f"{inst_name}/{board_key}", ic)
    st=card.get('_stack_title') or card.get('stackTitle'); ui_kv("Stack", st if st else f"ID {card.get('stackId')}", ic)
    done_ts = card.get('done')
    status = 'Archived' if card.get('archived') else ('Done' if done_ts else 'Active')
    ui_kv("Status", status, ic)
    if done_ts: ui_kv("Done at", _fmt_ts(done_ts), ic)
    ui_kv("Due", _fmt_ts(card.get('duedate')) if card.get('duedate') else 'None', ic)
    labels=card.get('labels') or []
    ns=[l.get('title') or l.get('name') for l in labels if l.get('title') or l.get('name')] if labels else []
    ui_kv("Labels", ', '.join(ns) if ns else 'None', ic)
    asn=card.get('assignedUsers') or card.get('assignedusers') or []
    ans=[]
    for a in asn:
        if isinstance(a,dict): n=a.get('participant',{}).get('displayname') or a.get('displayname') or a.get('uid')
        else: n=None
        if n: ans.append(n)
    ui_kv("Assignees", ', '.join(ans) if ans else 'None', ic)
    ui_kv("Created", _fmt_ts(card.get('createdAt')), ic)
    ui_kv("Modified", _fmt_ts(card.get('lastModified')), ic)
    ui_sep(ic)
    click.echo(_st("  Description", fg=ic, bold=True))
    click.echo(f"  {card.get('description') or '(empty)'}")
    ui_sep(ic)
    click.echo(_st("  Comments", fg=ic, bold=True))
    try:
        comments = client.list_comments(card_id)
    except Exception as e:
        comments = None
        if debug: click.echo(f"[DEBUG] comments fetch failed: {e}", err=True)
    if comments is None:
        ui_dim("  (comments unavailable)")
    elif not comments:
        ui_dim("  (none)")
    else:
        for c in comments:
            if not isinstance(c, dict):
                continue
            author = c.get('actorDisplayName') or c.get('actorId') or 'unknown'
            ts = _fmt_ts(c.get('creationDateTime'))
            cid_s = f"#{c.get('id')}" if c.get('id') is not None else ''
            head = f"  {_st('●', fg=ic)} {_st(author, bold=True)} {_st(ts, dim=True)}"
            if cid_s:
                head += f" {_st(cid_s, fg=ic)}"
            click.echo(head)
            reply_to = c.get('replyTo')
            if isinstance(reply_to, dict):
                reply_to = reply_to.get('id')
            if reply_to:
                click.echo(f"    {_st('↳ reply to #' + str(reply_to), dim=True)}")
            msg = str(c.get('message') or '')
            for line in (msg.splitlines() or ['']):
                click.echo(f"    {line}")
            click.echo()
    ui_sep(ic)

def _fmt_ts(v):
    if v is None or v == '': return 'None'
    # Unix timestamp (seconds)
    try:
        if isinstance(v, (int, float)):
            dt = datetime.fromtimestamp(float(v), tz=timezone.utc).astimezone()
            return dt.strftime('%Y-%m-%d %H:%M')
        if isinstance(v, str):
            vs = v.strip()
            if vs.isdigit():
                dt = datetime.fromtimestamp(int(vs), tz=timezone.utc).astimezone()
                return dt.strftime('%Y-%m-%d %H:%M')
            dt = _parse_duedate(vs)
            if dt:
                return dt.astimezone().strftime('%Y-%m-%d %H:%M')
            return vs
    except Exception:
        pass
    return str(v)

def _parse_duedate(s):
    if not s: return None
    s = str(s).strip()
    try:
        # Handle Z suffix
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            sl = s[:19] if 'T' in fmt or ' ' in fmt and '%H' in fmt else s[:10]
            dt = datetime.strptime(sl, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None

def _normalize_create_duedate(s):
    if not s: return None
    raw = str(s).strip()
    low = raw.lower()
    now = datetime.now().astimezone()
    local_tz = now.tzinfo
    if low == 'today':
        dt = now.replace(hour=17, minute=0, second=0, microsecond=0)
        return dt.isoformat()
    if low == 'tomorrow':
        dt = (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        return dt.isoformat()
    # If date-only, default to 17:00 local
    if len(raw) == 10 and raw[4] == '-' and raw[7] == '-':
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d").replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=local_tz)
            return dt.isoformat()
        except Exception:
            pass
    # Try parsing datetime-like inputs; if no time component, add 17:00
    try:
        s2 = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        return dt.isoformat()
    except Exception:
        pass
    for fmt, has_time in (("%Y-%m-%d %H:%M", True), ("%Y-%m-%dT%H:%M", True), ("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%dT%H:%M:%S", True)):
        try:
            dt = datetime.strptime(raw[:16] if fmt.endswith('%M') else raw[:19], fmt).replace(tzinfo=local_tz)
            return dt.isoformat()
        except Exception:
            pass
    # Fallback: return as-is
    return raw

def _agenda_range(period):
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    p = (period or 'today').lower()
    if p == 'today':
        end = start + timedelta(days=1)
    elif p == 'tomorrow':
        start = start + timedelta(days=1)
        end = start + timedelta(days=1)
    elif p == 'week':
        end = start + timedelta(days=7)
    elif p == 'month':
        end = start + timedelta(days=30)
    else:
        raise click.ClickException(f"Unknown period '{period}'. Use: today, tomorrow, week, month")
    return start, end, p

def _short_desc(text, width=50):
    if not text: return ''
    t = ' '.join(str(text).replace('\r',' ').replace('\n',' ').split())
    if len(t) <= width: return t
    return t[:width-1] + '…'



# ---- UI / theming ----
def _normalize_color(c, default='cyan'):
    if c is None or c == '':
        return default
    # RGB list/tuple from config: [139, 0, 0] or (139,0,0)
    if isinstance(c, (list, tuple)) and len(c) == 3:
        try:
            return (int(c[0]), int(c[1]), int(c[2]))
        except Exception:
            return default
    if isinstance(c, str):
        s = c.strip()
        if not s:
            return default
        # hex: #RRGGBB or #RGB
        if s.startswith('#'):
            h = s[1:]
            try:
                if len(h) == 6:
                    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                if len(h) == 3:
                    return (int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16))
            except Exception:
                return default
        # allow "r,g,b"
        if ',' in s and not s.startswith('bright_'):
            parts = [p.strip() for p in s.split(',')]
            if len(parts) == 3 and all(p.lstrip('-').isdigit() for p in parts):
                try:
                    return (int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    pass
        return s
    return default

def _inst_color(inst=None, cfg=None, inst_name=None, default='cyan'):
    if isinstance(inst, str) and inst not in ('',):
        # allow passing color directly (named/hex/rgb string)
        return _normalize_color(inst, default)
    if isinstance(inst, (list, tuple)):
        return _normalize_color(inst, default)
    if inst and isinstance(inst, dict):
        c = inst.get('color') or inst.get('theme_color')
        if c not in (None, ''): return _normalize_color(c, default)
    if cfg and inst_name:
        try:
            inst2 = (cfg.get('instances') or {}).get(inst_name) or {}
            c = inst2.get('color') or inst2.get('theme_color')
            if c not in (None, ''): return _normalize_color(c, default)
        except Exception: pass
    return default

def _st(text, fg=None, bold=False, dim=False):
    try:
        return click.style(str(text), fg=fg, bold=bold, dim=dim)
    except Exception:
        return str(text)

def ui_header(title, color='cyan'):
    line = '─' * min(max(len(str(title)), 40), 100)
    click.echo()
    click.echo(_st(title, fg=color, bold=True))
    click.echo(_st(line, fg=color))

def ui_kv(label, value, color='cyan', label_width=12):
    lab = f"{label}:".ljust(label_width)
    click.echo(f"  {_st(lab, fg=color)} {value}")

def ui_ok(msg): click.echo(_st(f"✔ {msg}", fg='green'))
def ui_warn(msg): click.echo(_st(f"⚠ {msg}", fg='yellow'), err=True)
def ui_err(msg): click.echo(_st(f"✖ {msg}", fg='red'), err=True)
def ui_info(msg, color='cyan'): click.echo(_st(msg, fg=color))
def ui_dim(msg): click.echo(_st(msg, dim=True))
def ui_sep(color='cyan', width=60): click.echo(_st('─' * width, fg=color))
def ui_card_ref(card_id, title=None, color='cyan'):
    ref = _st(f"#{card_id}", fg=color, bold=True)
    if title is not None:
        return f"{ref} {title}"
    return ref

def _card_assigned_to(card, username):
    if not username: return False
    u = str(username).lower()
    for a in (card.get('assignedUsers') or card.get('assignedusers') or []):
        if not isinstance(a, dict): continue
        p = a.get('participant') or {}
        uid = (p.get('uid') or p.get('primaryKey') or a.get('uid') or a.get('primaryKey') or '')
        if str(uid).lower() == u:
            return True
    return False

def _board_is_shared(client, board_id, username):
    try:
        b = client.get_board(board_id)
        owner = b.get('owner') or {}
        owner_uid = owner.get('uid') or owner.get('primaryKey') or ''
        if owner_uid and str(owner_uid).lower() != str(username).lower():
            return True
        # Also check if shared flag/count indicates sharing
        if b.get('shared'):
            return True
    except Exception:
        pass
    return False

def _gather_agenda(cfg, instance_name, all_instances, start, end, debug=False, include_done=True, all_cards=False):
    items = []
    if all_instances:
        inst_items = list((cfg.get('instances') or {}).items())
    else:
        iname = instance_name or cfg.get('default_instance')
        if not iname: raise click.ClickException("No instance specified and no default_instance in config")
        inst = (cfg.get('instances') or {}).get(iname)
        if not inst: raise click.ClickException(f"Instance '{iname}' not found")
        inst_items = [(iname, inst)]
    for iname, inst in inst_items:
        try:
            client = DeckClient(inst, debug=debug)
        except Exception:
            continue
        for bkey, bval in (inst.get('boards') or {}).items():
            try:
                cards = client.list_cards(bval['board_id'])
            except Exception:
                continue
            filter_username = None
            if not all_cards:
                uname = inst.get('username')
                if uname and _board_is_shared(client, bval['board_id'], uname):
                    filter_username = uname
            for c in cards:
                if c.get('archived'): continue
                if not include_done and c.get('done'):
                    continue
                if filter_username and not _card_assigned_to(c, filter_username):
                    continue
                dd = _parse_duedate(c.get('duedate'))
                if not dd: continue
                ddl = dd.astimezone()
                if start <= ddl < end:
                    st = c.get('_stack_title') or c.get('stackTitle') or f"stack {c.get('stackId','?')}"
                    items.append({
                        'due': ddl,
                        'title': c.get('title') or '(untitled)',
                        'desc': c.get('description') or '',
                        'instance': iname,
                        'board': bkey,
                        'stack': st,
                        'id': c.get('id'),
                    })
    items.sort(key=lambda x: (x['due'], x['instance'], x['board'], x['title']))
    return items

@cli.command("agenda")
@click.argument("period", default="today", required=False)
@click.option("-i", "--instance")
@click.option("-A", "--all-instances", is_flag=True, help="Show agenda from all configured instances")
@click.option("--all", "all_cards", is_flag=True, help="Show all cards (include unassigned on shared boards)")
@click.option("--desc-width", default=50, show_default=True, help="Max width for short description")
@click.pass_context
def agenda_cmd(ctx, period, instance, all_instances, all_cards, desc_width):
    """Show cards by due date (today, tomorrow, week, month)."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        raise click.ClickException("No accounts configured. Run `ncdeck account add` to add one.")
    start, end, p = _agenda_range(period)
    items = _gather_agenda(cfg, instance, all_instances, start, end, debug=debug, include_done=False, all_cards=all_cards)
    scope = "all instances" if all_instances else (instance or cfg.get('default_instance') or '?')
    hc = 'cyan' if all_instances else _inst_color(cfg.get('instances',{}).get(scope))
    header = f"Agenda: {p}  ({start.strftime('%Y-%m-%d')} → {(end - timedelta(seconds=1)).strftime('%Y-%m-%d')})  [{scope}]"
    ui_header(header, hc)
    if not items:
        ui_dim("  No cards with due dates in this period.")
        click.echo()
        return
    for it in items:
        ic = _inst_color(cfg.get('instances',{}).get(it['instance']))
        due_s = it['due'].strftime('%a %Y-%m-%d %H:%M')
        title = it['title']
        desc = _short_desc(it['desc'], desc_width)
        loc = f"{it['instance']}/{it['board']} / {it['stack']}"
        click.echo(f"  {_st('●', fg=ic)} {_st(title, bold=True)} {_st(f'(#{it["id"]})', fg=ic)}")
        if desc:
            ui_kv("Desc", desc, ic, label_width=10)
        ui_kv("Due", due_s, ic, label_width=10)
        ui_kv("Where", loc, ic, label_width=10)
        click.echo()
    ui_dim(f"Total: {len(items)} card(s)")
    click.echo()

def _resolve_completed_refs(refs_text, items, context="today's/overdue agenda"):
    # Build lookups
    by_inst_id = {}
    by_inst_board_id = {}
    by_id = {}
    for it in items:
        key = f"{it['instance']}:{it['id']}"
        by_inst_id.setdefault(key, []).append(it)
        key2 = f"{it['instance']}/{it['board']}:{it['id']}"
        key3 = f"{it['instance']}/{it['board']}#{it['id']}"
        by_inst_board_id[key2] = it
        by_inst_board_id[key3] = it
        by_id.setdefault(str(it['id']), []).append(it)
    raw = refs_text.replace(',', ' ').split()
    resolved = []
    errors = []
    for r in raw:
        r = r.strip()
        if not r: continue
        if r in by_inst_board_id:
            resolved.append(by_inst_board_id[r]); continue
        # normalize # to :
        rn = r.replace('#', ':')
        if rn in by_inst_id:
            matches = by_inst_id[rn]
            if len(matches) == 1:
                resolved.append(matches[0])
            else:
                errors.append(f"Ambiguous '{r}' (matches multiple boards); use instance/board:cardid")
            continue
        if '/' in r and ':' in r.split('/')[-1]:
            # try instance/board:cardid
            errors.append(f"Not found in {context}: {r}"); continue
        if ':' in rn:
            parts = rn.split(':', 1)
            if len(parts) == 2:
                k = f"{parts[0]}:{parts[1]}"
                if k in by_inst_id:
                    matches = by_inst_id[k]
                    if len(matches) == 1: resolved.append(matches[0])
                    else: errors.append(f"Ambiguous '{r}'; use instance/board:cardid")
                    continue
        if r.isdigit() and r in by_id:
            matches = by_id[r]
            if len(matches) == 1: resolved.append(matches[0])
            else: errors.append(f"Ambiguous card id '{r}'; use instance:cardid or instance/board:cardid")
            continue
        errors.append(f"Not found in {context}: {r}")
    # dedupe by (instance, board, id)
    seen = set(); out = []
    for it in resolved:
        k = (it['instance'], it['board'], it['id'])
        if k not in seen: seen.add(k); out.append(it)
    return out, errors

@cli.command("completed")
@click.option("-i", "--instance")
@click.option("-A", "--all-instances", is_flag=True, help="Show agenda from all configured instances")
@click.option("--all", "all_cards", is_flag=True, help="Show all cards (include unassigned on shared boards)")
@click.option("--archive", is_flag=True, help="Archive cards instead of moving to done stack")
@click.option("--stack", type=int, help="Move to specific stack ID instead of done stack")
@click.option("--desc-width", default=40, show_default=True, help="Max width for short description")
@click.pass_context
def completed_cmd(ctx, instance, all_instances, all_cards, archive, stack, desc_width):
    """List today's and overdue cards, mark selected cards as done, and move the rest to the next day."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        raise click.ClickException("No accounts configured. Run `ncdeck account add` to add one.")
    start, end, p = _agenda_range('today')
    today_items = _gather_agenda(cfg, instance, all_instances, start, end, debug=debug, include_done=False, all_cards=all_cards)
    overdue_start = start - timedelta(days=3650)
    overdue_items = _gather_agenda(cfg, instance, all_instances, overdue_start, start, debug=debug, include_done=False, all_cards=all_cards)
    for it in overdue_items:
        it['overdue'] = True
    for it in today_items:
        it['overdue'] = False
    scope = "all instances" if all_instances else (instance or cfg.get('default_instance') or '?')
    hc = 'cyan' if all_instances else _inst_color(cfg.get('instances',{}).get(scope))
    ui_header(f"Today & overdue ({start.strftime('%Y-%m-%d')}) [{scope}]", hc)

    def _print_item(it):
        ic = _inst_color(cfg.get('instances',{}).get(it['instance']))
        due_s = it['due'].strftime('%Y-%m-%d %H:%M') if it.get('overdue') else it['due'].strftime('%H:%M')
        desc = _short_desc(it['desc'], desc_width)
        ref = f"{it['instance']}/{it['board']}#{it['id']}"
        marker = _st('OVERDUE ', fg='red', bold=True) if it.get('overdue') else ''
        click.echo(f"  {_st('●', fg=ic)} {marker}{_st(it['title'], bold=True)} {_st(f'[{ref}]', fg=ic)}")
        if desc:
            click.echo(f"    {_st(desc, dim=False)}")
        click.echo(f"    {_st('Due:', fg=ic)} {due_s}  {_st('Where:', fg=ic)} {_st(f"{it['instance']}/{it['board']} / {it['stack']}", fg=ic)}")
        click.echo()

    if overdue_items:
        click.echo(_st(f"  Overdue ({len(overdue_items)})", fg='red', bold=True))
        for it in overdue_items:
            _print_item(it)
    if today_items:
        click.echo(_st(f"  Today ({len(today_items)})", fg=hc, bold=True))
        for it in today_items:
            _print_item(it)
    items = overdue_items + today_items
    if not items:
        ui_dim("  No due/overdue cards to review.")
        click.echo()
        return
    click.echo(_st("Enter completed cards as instance:cardid or instance/board:cardid (comma/space separated).", dim=True))
    click.echo(_st("Example: mync:20  or  mync/personal:20", dim=True))
    refs = click.prompt("Completed", default="", show_default=False)
    resolved = []
    errors = []
    if refs.strip():
        resolved, errors = _resolve_completed_refs(refs, items)
        for e in errors:
            ui_warn(e)
    completed_ok = []
    completed_keys = set()
    for it in resolved:
        inst_name = it['instance']; board_key = it['board']; card_id = it['id']
        ic = _inst_color(cfg.get('instances',{}).get(inst_name))
        try:
            _, inst, board = get_mapping(cfg, inst_name, board_key)
            client = DeckClient(inst, debug=debug)
            if archive:
                client.archive_card(board['board_id'], card_id, archived=True)
                ui_ok(f"Archived {_st('#'+str(card_id), fg=ic, bold=True)} ({_st(f'{inst_name}/{board_key}', fg=ic)}) - {it['title']}")
            else:
                ds = stack if stack is not None else board.get('done_stack_id')
                if ds is None:
                    ui_warn(f"Skipped #{card_id} ({inst_name}/{board_key}): no done stack configured")
                    continue
                client.mark_card_done(board['board_id'], card_id, done=True)
                client.move_card(board['board_id'], card_id, ds)
                ui_ok(f"Done {_st('#'+str(card_id), fg=ic, bold=True)} ({_st(f'{inst_name}/{board_key}', fg=ic)}) - {it['title']}")
            completed_ok.append(it)
            completed_keys.add((inst_name, board_key, card_id))
        except Exception as e:
            ui_err(f"Error completing #{card_id} ({inst_name}/{board_key}): {e}")
    moved = []
    move_errors = []
    tomorrow_start = start + timedelta(days=1)
    for it in items:
        k = (it['instance'], it['board'], it['id'])
        if k in completed_keys:
            continue
        ic = _inst_color(cfg.get('instances',{}).get(it['instance']))
        try:
            _, inst, board = get_mapping(cfg, it['instance'], it['board'])
            client = DeckClient(inst, debug=debug)
            if it.get('overdue') or it['due'] < tomorrow_start:
                nd = tomorrow_start.replace(hour=it['due'].hour, minute=it['due'].minute, second=0, microsecond=0)
            else:
                nd = it['due'] + timedelta(days=1)
            new_due = nd.isoformat()
            client.update_card_duedate(board['board_id'], it['id'], new_due)
            moved.append((it, new_due))
            ui_ok(f"Moved to next day {_st('#'+str(it['id']), fg=ic, bold=True)} ({_st(f"{it['instance']}/{it['board']}", fg=ic)}) - {it['title']} → {_fmt_ts(new_due)}")
        except Exception as e:
            move_errors.append((it, e))
            ui_err(f"Error moving #{it['id']} ({it['instance']}/{it['board']}): {e}")
    ui_header("Summary", hc)
    ui_kv("Completed", str(len(completed_ok)), hc)
    for it in completed_ok:
        ic = _inst_color(cfg.get('instances',{}).get(it['instance']))
        click.echo(f"    {_st('-', fg=ic)} {_st('#'+str(it['id']), fg=ic, bold=True)} {_st(f"{it['instance']}/{it['board']}", fg=ic)}: {it['title']}")
    ui_kv("Moved", str(len(moved)), hc)
    for it, nd in moved:
        ic = _inst_color(cfg.get('instances',{}).get(it['instance']))
        click.echo(f"    {_st('-', fg=ic)} {_st('#'+str(it['id']), fg=ic, bold=True)} {_st(f"{it['instance']}/{it['board']}", fg=ic)}: {it['title']} {_st(f'(due {_fmt_ts(nd)})', dim=True)}")
    if move_errors:
        ui_kv("Move errors", str(len(move_errors)), 'red')
    click.echo()


@cli.command("archive")
@click.argument("board_key")
@click.argument("before_date")
@click.option("-i", "--instance")
@click.option("--all-done", "all_done", is_flag=True, help="Archive all cards marked as done older than BEFORE_DATE (ignore done stack and assignee)")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation")
@click.pass_context
def archive_cmd(ctx, board_key, before_date, instance, all_done, yes):
    """Archive done cards older than BEFORE_DATE. By default: in done stack, marked done, assigned to current user. With --all-done: all cards marked done (any stack/assignee)."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config(); inst_name, inst, board = get_mapping(cfg, instance, board_key); client = DeckClient(inst, debug=debug)
    ic = _inst_color(inst)
    cutoff = _parse_duedate(before_date)
    if not cutoff:
        # try date-only
        try:
            cutoff = datetime.strptime(str(before_date).strip(), "%Y-%m-%d").replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception:
            raise click.ClickException(f"Could not parse date: {before_date}")
    cutoff = cutoff.astimezone()
    username = inst.get('username')
    if all_done:
        cards = client.list_cards(board['board_id'])
        ui_info(f"Scanning all stacks for done cards older than {_fmt_ts(cutoff)} in {inst_name}/{board_key}...", ic)
    else:
        if not username:
            raise click.ClickException("Instance has no username configured (required to filter by current user; use --all-done to ignore)")
        ds = board.get('done_stack_id')
        if ds is None:
            raise click.ClickException("No done_stack_id configured for this board (use --all-done to scan all done cards)")
        cards = client.list_cards(board['board_id'], stack_id=ds)
        ui_info(f"Scanning done stack for your done cards older than {_fmt_ts(cutoff)} in {inst_name}/{board_key}...", ic)
    targets = []
    for c in cards:
        if c.get('archived'):
            continue
        done_ts = c.get('done')
        if not done_ts:
            continue
        dt = _parse_duedate(done_ts) or _parse_duedate(c.get('lastModified')) or _parse_duedate(c.get('createdAt'))
        if not dt:
            continue
        dtl = dt.astimezone()
        if not (dtl < cutoff):
            continue
        if not all_done:
            if not username or not _card_assigned_to(c, username):
                continue
        targets.append((c, dtl))
    targets.sort(key=lambda x: (x[1], x[0].get('id', 0)))
    if not targets:
        ui_dim("No matching cards to archive.")
        return
    ui_header(f"Cards to archive ({len(targets)}) - {inst_name}/{board_key}", ic)
    for c, dtl in targets:
        cid = c.get('id'); title = c.get('title') or '(untitled)'; st = c.get('_stack_title') or c.get('stackTitle') or ''
        click.echo(f"  {_st('#'+str(cid), fg=ic, bold=True)} {_st(f'[{st}]', fg=ic) if st else ''} {title} {_st(f'(done {_fmt_ts(dtl)})', dim=True)}")
    if not yes:
        if not click.confirm(f"Archive {len(targets)} card(s)?", default=False):
            ui_warn("Cancelled")
            return
    ok = 0; errs = 0
    for c, dtl in targets:
        cid = c.get('id')
        try:
            client.archive_card(board['board_id'], cid, archived=True)
            ok += 1
            ui_ok(f"Archived {_st('#'+str(cid), fg=ic, bold=True)} {c.get('title') or ''}")
        except Exception as e:
            errs += 1
            ui_err(f"Failed to archive #{cid}: {e}")
    ui_header("Summary", ic)
    ui_kv("Archived", str(ok), ic)
    if errs: ui_kv("Errors", str(errs), 'red')


if __name__ == "__main__":
    cli()
