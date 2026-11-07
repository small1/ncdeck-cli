#!/usr/bin/env python3
import os, sys, json, time, webbrowser
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
        if assigned_users: payload["assignedUsers"]=[{"participant":{"primaryKey":u}} for u in assigned_users]
        return self._post(f"/index.php/apps/deck/api/v1.0/boards/{board_id}/stacks/{stack_id}/cards", payload)

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
def account_add_cmd(instance_name, url):
    """Add a Nextcloud account via Login Flow v2 with board autodiscovery."""
    cfg = load_config()
    if not isinstance(cfg, dict): cfg = {}
    if 'instances' not in cfg or not isinstance(cfg['instances'], dict): cfg['instances'] = {}
    if not url: url = click.prompt("Nextcloud server URL (e.g. https://cloud.example.com)")
    url = url.rstrip('/')
    click.echo(f"\nStarting Nextcloud Login Flow v2 for {url}...")
    resp = requests.post(f"{url}/index.php/login/v2", headers={"User-Agent": "ncdeck-cli"}, timeout=30)
    resp.raise_for_status()
    flow = resp.json()
    login_url = flow['login']; poll = flow['poll']; endpoint = poll['endpoint']; token = poll['token']
    click.echo(f"\nOpening browser to authenticate...\nIf browser doesn't open, visit: {login_url}")
    try: webbrowser.open(login_url)
    except: pass
    click.echo("\nWaiting for authentication...")
    creds=None
    for _ in range(120):
        try:
            r = requests.post(endpoint, data={"token": token}, timeout=30)
            if r.status_code == 200: creds=r.json(); break
            time.sleep(2)
        except: time.sleep(2); continue
    if not creds: raise click.ClickException("Authentication timed out or failed")
    server = creds.get('server', url); login_name = creds.get('loginName') or creds.get('user'); app_password = creds.get('appPassword')
    click.echo(f"\nAuthenticated as {login_name} on {server}")
    if not instance_name:
        default_name = login_name if login_name and login_name not in cfg['instances'] else f"nc_{login_name}"
        instance_name = click.prompt("Short name for this instance", default=default_name)
    client = DeckClient({"url": server.rstrip('/'), "username": login_name, "password": app_password})
    click.echo("\nDiscovering boards...")
    boards = client.list_boards()
    boards_config={}
    if boards:
        for board in boards:
            board_id = board['id']; board_title = board['title']
            click.echo(f"\n{'='*50}\nBoard: {board_title} (id: {board_id})")
            default_key = '_'.join(filter(None, ''.join(c.lower() if c.isalnum() else '_' for c in board_title).split('_')))
            if not default_key: default_key = f"board_{board_id}"
            board_key = click.prompt("Short name for this board", default=default_key)
            board_key = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in board_key)
            stacks = client.list_stacks(board_id)
            stack_id=None; done_stack_id=None
            if stacks:
                click.echo("\nStacks:")
                for i,s in enumerate(stacks): click.echo(f"  {i+1}. {s['title']} (id: {s['id']})")
                stack_id = click.prompt("Stack ID for creating new cards", default=stacks[0]['id'], type=int)
                click.echo("\nWhich stack should be the 'done' stack?\n  0. None")
                for i,s in enumerate(stacks): click.echo(f"  {i+1}. {s['title']} (id: {s['id']})")
                done_choice = click.prompt("Done stack", default=0, type=int)
                if done_choice>0 and done_choice<=len(stacks): done_stack_id=stacks[done_choice-1]['id']
            else:
                stack_id = click.prompt("Stack ID for creating new cards", type=int)
            be={"board_id":board_id,"stack_id":stack_id}
            if done_stack_id: be["done_stack_id"]=done_stack_id
            boards_config[board_key]=be
    cfg['instances'][instance_name]={"url":server.rstrip('/'),"username":login_name,"password":app_password,"boards":boards_config}
    if not cfg.get('default_instance'): cfg['default_instance']=instance_name
    elif click.confirm(f"\nSet '{instance_name}' as default instance?", default=False): cfg['default_instance']=instance_name
    save_config(cfg)
    click.echo(f"\n{'='*50}\nConfiguration saved to {get_config_path()}\nInstance '{instance_name}' added with {len(boards_config)} board(s)\n{'='*50}")

@account.command("list")
@click.pass_context
def account_list_cmd(ctx):
    """List configured accounts/instances."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        click.echo("No accounts configured. Run `ncdeck account add` to add one."); return
    default = cfg.get('default_instance')
    click.echo(f"Configured instances (default: {default or 'none'}):")
    for name, inst in cfg.get('instances', {}).items():
        marker = " *" if name == default else ""
        click.echo(f"  {name}{marker} - {inst.get('url')} ({inst.get('username')})")
        for bk,bv in (inst.get('boards') or {}).items():
            done = f", done_stack={bv.get('done_stack_id')}" if bv.get('done_stack_id') else ""
            click.echo(f"    {bk}: board_id={bv.get('board_id')}, stack_id={bv.get('stack_id')}{done}")


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
    if not force:
        if not click.confirm(f"Delete instance '{instance_name}'?"):
            click.echo("Cancelled")
            return
    del cfg['instances'][instance_name]
    if cfg.get('default_instance') == instance_name:
        if cfg['instances']:
            new_default = next(iter(cfg['instances'].keys()))
            cfg['default_instance'] = new_default
            click.echo(f"Default instance changed to '{new_default}'")
        else:
            cfg.pop('default_instance', None)
    save_config(cfg)
    click.echo(f"Deleted instance '{instance_name}'")

@cli.command("show-config")
def show_config_cmd():
    """Show current configuration with passwords masked."""
    cfg = load_config()
    if not isinstance(cfg, dict): click.echo("No configuration found."); return
    masked = json.loads(json.dumps(cfg))
    for inst_name, inst in masked.get('instances', {}).items():
        if isinstance(inst, dict) and inst.get('password'):
            inst['password'] = '****'
    click.echo(yaml.safe_dump(masked, sort_keys=False))

@cli.command("list")
@click.option("-i","--instance")
@click.option("--boards",is_flag=True)
@click.option("--stacks",type=int)
@click.option("--labels","labels_board",metavar="BOARD_KEY")
@click.option("--cards","cards_board",metavar="BOARD_KEY")
@click.option("--stack",type=int)
@click.pass_context
def list_cmd(ctx,instance,boards,stacks,labels_board,cards_board,stack):
    """List configured boards/stacks/labels/cards or instance details."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name=instance or cfg.get("default_instance")
    if not inst_name: raise click.ClickException("No instance specified")
    inst=cfg.get("instances",{}).get(inst_name)
    if not inst: raise click.ClickException(f"Instance '{inst_name}' not found")
    client=DeckClient(inst, debug=debug)
    if boards:
        for b in client.list_boards(): 
            owner=(b.get("owner") or {}).get("uid"); click.echo(f"board_id={b['id']} title={b['title']} owner={owner}")
        return
    if stacks is not None:
        for s in client.list_stacks(stacks): click.echo(f"stack_id={s['id']} title={s['title']} order={s.get('order')}")
        return
    if cards_board:
        inst_name_res,inst_res,board=get_mapping(cfg,instance,cards_board)
        cards=client.list_cards(board["board_id"],stack_id=stack)
        click.echo(f"Cards for {inst_name_res}/{cards_board}:")
        if not cards: click.echo("  (no cards found)"); return
        for card in cards:
            card_id=card.get('id'); title=card.get('title') or '(untitled)'; st=card.get('_stack_title') or card.get('stackTitle') or ''
            ar=" [ARCHIVED]" if card.get('archived') else ""; du=card.get('duedate'); asn=card.get('assignedUsers') or card.get('assignedusers') or []
            astr=""; 
            if asn:
                ns=[]
                for a in asn:
                    if isinstance(a,dict): n=a.get('participant',{}).get('displayname') or a.get('displayname') or a.get('uid'); 
                    if n: ns.append(n)
                if ns: astr=f" @{','.join(ns)}"
            click.echo(f"  #{card_id} [{st}]{ar} {title}{astr}" if st else f"  #{card_id}{ar} {title}{astr}")
            if du: click.echo(f"    Due: {_fmt_ts(du)}")
        return
    if labels_board:
        inst_name_res,inst_res,board=get_mapping(cfg,instance,labels_board)
        try:
            labels=client.list_labels(board["board_id"])
            click.echo(f"Tags/labels for {inst_name_res}/{labels_board}:")
            if not labels: click.echo("  (no labels found)"); return
            for l in labels: click.echo(f"  - {(l.get('title') or l.get('name'))} (id={l['id']})")
        except Exception as e: click.echo(f"Error: {e}",err=True)
        return
    click.echo(f"Instance: {inst_name} ({inst['url']})")
    for k,v in inst.get("boards",{}).items():
        di=f" done_stack_id={v['done_stack_id']}" if v.get("done_stack_id") else ""
        click.echo(f"  - {k}: board_id={v['board_id']} stack_id={v['stack_id']}{di}")

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
    ct=f"[{prefix}] {title}" if prefix else title; cd=read_description(description,description_file)
    lids=resolve_label_ids(client,board["board_id"],list(tag)) if tag else []
    due_norm = _normalize_create_duedate(due_date) if due_date else None
    try:
        card=client.create_card(board["board_id"],board["stack_id"],ct,cd,duedate=due_norm,labels=lids if lids else None,assigned_users=list(assign) if assign else None)
        click.echo(f"Created card #{card['id']} '{card['title']}' in {inst_name}/{board_key}")
        if due_norm: click.echo(f"  Due: {_fmt_ts(due_norm)}")
        if tag: click.echo(f"  Tags: {', '.join(tag)}")
        if assign: click.echo(f"  Assigned: {', '.join(assign)}")
        for a in attach:
            try:
                client.upload_attachment(board["board_id"], card['id'], a)
                click.echo(f"  Attached: {Path(a).name}")
            except Exception as e:
                click.echo(f"  Failed to attach {Path(a).name}: {e}", err=True)
    except Exception as e: click.echo(f"Error: {e}",err=True); sys.exit(1)

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
    try:
        if archive: client.archive_card(board["board_id"],card_id,archived=True); click.echo(f"Archived card #{card_id}"); return
        ds=stack if stack is not None else board.get("done_stack_id")
        if ds is None: raise click.ClickException("No done stack configured")
        client.mark_card_done(board["board_id"], card_id, done=True)
        client.move_card(board["board_id"], card_id, ds)
        click.echo(f"Marked card #{card_id} as done")
    except Exception as e: click.echo(f"Error: {e}",err=True); sys.exit(1)

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
    try: client.move_card(board["board_id"],card_id,stack_id); click.echo(f"Moved card #{card_id} to stack {stack_id}")
    except Exception as e: click.echo(f"Error: {e}",err=True); sys.exit(1)

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
    try:
        if unassign: client.unassign_card(board["board_id"],card_id,user_id); click.echo(f"Unassigned card #{card_id} from {user_id}")
        else: client.assign_card(board["board_id"],card_id,user_id); click.echo(f"Assigned card #{card_id} to {user_id}")
    except Exception as e: click.echo(f"Error: {e}",err=True); sys.exit(1)


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
    try:
        client.upload_attachment(board["board_id"],card_id,file_path)
        click.echo(f"Attached {file_path.name} to card #{card_id} in {inst_name}/{board_key}")
    except Exception as e: click.echo(f"Error: {e}",err=True); sys.exit(1)

@cli.command("search")
@click.argument("board_key")
@click.argument("query")
@click.option("-i","--instance")
@click.option("--stack",type=int)
@click.option("--include-archived",is_flag=True)
@click.pass_context
def search_cmd(ctx,board_key,query,instance,stack,include_archived):
    """Search cards by keyword in title or description."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg=load_config(); inst_name,inst,board=get_mapping(cfg,instance,board_key); client=DeckClient(inst, debug=debug)
    cards=client.list_cards(board["board_id"],stack_id=stack)
    ql=query.lower(); res=[]
    for c in cards:
        if not include_archived and c.get('archived'): continue
        if ql in (c.get('title') or '').lower() or ql in (c.get('description') or '').lower(): res.append(c)
    if not res: click.echo(f"No cards found matching '{query}'"); return
    click.echo(f"Found {len(res)} card(s):")
    for c in res:
        cid=c.get('id'); t=c.get('title'); st=c.get('_stack_title') or c.get('stackTitle') or ''; ar=" [ARCHIVED]" if c.get('archived') else ""
        click.echo(f"  #{cid} [{st}]{ar} {t}" if st else f"  #{cid}{ar} {t}")
        if c.get('duedate'): click.echo(f"    Due: {_fmt_ts(c['duedate'])}")

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
    click.echo("="*60); click.echo(f"Card #{card.get('id')}: {card.get('title')}"); click.echo("="*60)
    click.echo(f"Board: {inst_name}/{board_key}")
    st=card.get('_stack_title') or card.get('stackTitle'); click.echo(f"Stack: {st}" if st else f"Stack ID: {card.get('stackId')}")
    done_ts = card.get('done')
    status = 'Archived' if card.get('archived') else 'Active'
    if done_ts: status += f" (Done: {_fmt_ts(done_ts)})"
    click.echo(f"Status: {status}")
    click.echo(f"Due Date: {_fmt_ts(card.get('duedate')) if card.get('duedate') else 'None'}")
    labels=card.get('labels') or []
    if labels:
        ns=[l.get('title') or l.get('name') for l in labels if l.get('title') or l.get('name')]
        click.echo(f"Labels: {', '.join(ns) if ns else 'None'}")
    else: click.echo("Labels: None")
    asn=card.get('assignedUsers') or card.get('assignedusers') or []
    if asn:
        ns=[]
        for a in asn:
            if isinstance(a,dict): n=a.get('participant',{}).get('displayname') or a.get('displayname') or a.get('uid'); 
            if n: ns.append(n)
        click.echo(f"Assignees: {', '.join(ns) if ns else 'None'}")
    else: click.echo("Assignees: None")
    click.echo(f"Created: {_fmt_ts(card.get('createdAt'))}")
    click.echo(f"Last Modified: {_fmt_ts(card.get('lastModified'))}")
    click.echo("="*60); click.echo("Description:"); click.echo(card.get('description') or "(empty)"); click.echo("="*60)

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

def _gather_agenda(cfg, instance_name, all_instances, start, end, debug=False, include_done=True):
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
            for c in cards:
                if c.get('archived'): continue
                if not include_done and c.get('done'):
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
@click.option("--desc-width", default=50, show_default=True, help="Max width for short description")
@click.pass_context
def agenda_cmd(ctx, period, instance, all_instances, desc_width):
    """Show cards by due date (today, tomorrow, week, month)."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        raise click.ClickException("No accounts configured. Run `ncdeck account add` to add one.")
    start, end, p = _agenda_range(period)
    items = _gather_agenda(cfg, instance, all_instances, start, end, debug=debug)
    scope = "all instances" if all_instances else (instance or cfg.get('default_instance') or '?')
    header = f"Agenda: {p}  ({start.strftime('%Y-%m-%d')} → {(end - timedelta(seconds=1)).strftime('%Y-%m-%d')})  [{scope}]"
    click.echo()
    click.echo(click.style(header, bold=True))
    click.echo(click.style('─' * min(max(len(header), 72), 100), fg='blue'))
    if not items:
        click.echo(click.style("  No cards with due dates in this period.", dim=True))
        click.echo()
        return
    for it in items:
        due_s = it['due'].strftime('%a %Y-%m-%d %H:%M')
        title = it['title']
        desc = _short_desc(it['desc'], desc_width)
        loc = f"{it['instance']} / {it['board']} / {it['stack']}"
        click.echo(click.style(f"  ● {title}", bold=True) + click.style(f"  (#{it['id']})", dim=True))
        if desc:
            click.echo(f"    {click.style('Desc:', fg='cyan')}   {desc}")
        click.echo(f"    {click.style('Due:', fg='yellow')}    {due_s}")
        click.echo(f"    {click.style('Where:', fg='green')}  {loc}")
        click.echo()
    click.echo(click.style(f"Total: {len(items)} card(s)", dim=True))
    click.echo()

def _resolve_completed_refs(refs_text, items):
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
            errors.append(f"Not found in today's agenda: {r}"); continue
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
        errors.append(f"Not found in today's agenda: {r}")
    # dedupe by (instance, board, id)
    seen = set(); out = []
    for it in resolved:
        k = (it['instance'], it['board'], it['id'])
        if k not in seen: seen.add(k); out.append(it)
    return out, errors

@cli.command("completed")
@click.option("-i", "--instance")
@click.option("-A", "--all-instances", is_flag=True, help="Show agenda from all configured instances")
@click.option("--archive", is_flag=True, help="Archive cards instead of moving to done stack")
@click.option("--stack", type=int, help="Move to specific stack ID instead of done stack")
@click.option("--desc-width", default=40, show_default=True, help="Max width for short description")
@click.pass_context
def completed_cmd(ctx, instance, all_instances, archive, stack, desc_width):
    """List today's agenda, mark selected cards as done, and move the rest to the next day."""
    debug = ctx.obj.get('debug') if ctx.obj else False
    cfg = load_config()
    if not isinstance(cfg, dict) or not cfg.get('instances'):
        raise click.ClickException("No accounts configured. Run `ncdeck account add` to add one.")
    start, end, p = _agenda_range('today')
    items = _gather_agenda(cfg, instance, all_instances, start, end, debug=debug, include_done=False)
    scope = "all instances" if all_instances else (instance or cfg.get('default_instance') or '?')
    header = f"Today's agenda ({start.strftime('%Y-%m-%d')}) [{scope}]"
    click.echo()
    click.echo(click.style(header, bold=True))
    click.echo(click.style('─' * min(max(len(header), 72), 100), fg='blue'))
    if not items:
        click.echo(click.style("  No cards with due dates today.", dim=True))
        click.echo()
        return
    for it in items:
        due_s = it['due'].strftime('%H:%M')
        desc = _short_desc(it['desc'], desc_width)
        ref = f"{it['instance']}/{it['board']}#{it['id']}"
        click.echo(click.style(f"  ● {it['title']}", bold=True) + click.style(f"  [{ref}]", fg='magenta'))
        if desc:
            click.echo(f"    {desc}")
        click.echo(f"    {click.style('Due', fg='yellow')} {due_s}  {click.style('Where', fg='green')} {it['instance']} / {it['board']} / {it['stack']}")
        click.echo()
    click.echo("Enter completed cards as instance:cardid or instance/board:cardid (comma/space separated).")
    click.echo("Example: mync:20  or  mync/personal:20")
    refs = click.prompt("Completed", default="", show_default=False)
    resolved = []
    errors = []
    if refs.strip():
        resolved, errors = _resolve_completed_refs(refs, items)
        for e in errors:
            click.echo(click.style(f"  Warning: {e}", fg='yellow'), err=True)
    completed_ok = []
    completed_keys = set()
    for it in resolved:
        inst_name = it['instance']; board_key = it['board']; card_id = it['id']
        try:
            _, inst, board = get_mapping(cfg, inst_name, board_key)
            client = DeckClient(inst, debug=debug)
            if archive:
                client.archive_card(board['board_id'], card_id, archived=True)
                click.echo(f"Archived #{card_id} ({inst_name}/{board_key}) - {it['title']}")
            else:
                ds = stack if stack is not None else board.get('done_stack_id')
                if ds is None:
                    click.echo(click.style(f"  Skipped #{card_id} ({inst_name}/{board_key}): no done stack configured", fg='yellow'), err=True)
                    continue
                client.mark_card_done(board['board_id'], card_id, done=True)
                client.move_card(board['board_id'], card_id, ds)
                click.echo(f"Done #{card_id} ({inst_name}/{board_key}) - {it['title']}")
            completed_ok.append(it)
            completed_keys.add((inst_name, board_key, card_id))
        except Exception as e:
            click.echo(click.style(f"  Error completing #{card_id} ({inst_name}/{board_key}): {e}", fg='red'), err=True)
    moved = []
    move_errors = []
    for it in items:
        k = (it['instance'], it['board'], it['id'])
        if k in completed_keys:
            continue
        try:
            _, inst, board = get_mapping(cfg, it['instance'], it['board'])
            client = DeckClient(inst, debug=debug)
            new_due = (it['due'] + timedelta(days=1)).isoformat()
            client.update_card_duedate(board['board_id'], it['id'], new_due)
            moved.append((it, new_due))
            click.echo(f"Moved to next day #{it['id']} ({it['instance']}/{it['board']}) - {it['title']} -> {_fmt_ts(new_due)}")
        except Exception as e:
            move_errors.append((it, e))
            click.echo(click.style(f"  Error moving #{it['id']} ({it['instance']}/{it['board']}): {e}", fg='red'), err=True)
    click.echo()
    click.echo(click.style("Summary", bold=True))
    click.echo(click.style("─" * 40, fg='blue'))
    click.echo(f"  Completed: {len(completed_ok)}")
    for it in completed_ok:
        click.echo(f"    - #{it['id']} {it['instance']}/{it['board']}: {it['title']}")
    click.echo(f"  Moved to next day: {len(moved)}")
    for it, nd in moved:
        click.echo(f"    - #{it['id']} {it['instance']}/{it['board']}: {it['title']} (due {_fmt_ts(nd)})")
    if move_errors:
        click.echo(f"  Move errors: {len(move_errors)}")
    click.echo()

if __name__ == "__main__":
    cli()
